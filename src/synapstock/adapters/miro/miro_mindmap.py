"""Miro 마인드맵 어댑터 구현."""

from typing import cast
import requests
from synapstock.domain.models import Board, Node
from synapstock.domain.ports import MindmapPort

class MiroMindmapAdapter(MindmapPort):
    """Miro V2 API를 사용하는 마인드맵 어댑터.

    Miro의 Board, Shape, Connector를 사용하여 도메인 트리 구조를 매핑한다.
    """

    def __init__(self, api_token: str):
        """
        Args:
            api_token: Miro API Access Token.
        """
        self.api_token = api_token
        self.base_url = "https://api.miro.com/v2"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def list_boards(self) -> list[str]:
        """나의 Miro 보드 이름 목록을 반환한다."""
        res = requests.get(f"{self.base_url}/boards", headers=self.headers)
        res.raise_for_status()
        data = res.json()
        boards = cast(list[dict[str, str]], data.get("data", []))
        return [board["name"] for board in boards]

    def _get_board_id_by_name(self, board_name: str) -> str:
        """이름으로 보드 ID를 검색한다.

        Raises:
            FileNotFoundError: 해당 이름의 보드가 없을 때.
        """
        res = requests.get(f"{self.base_url}/boards", headers=self.headers)
        res.raise_for_status()
        data = res.json()
        boards = cast(list[dict[str, str]], data.get("data", []))
        for board in boards:
            if board["name"] == board_name:
                return cast(str, board["id"])
        raise FileNotFoundError(f"Miro board not found: {board_name}")


    def load(self, board_name: str) -> Board:
        """Miro 보드에서 트리 구조를 읽어온다.

        Miro의 Item(Shape 등)들을 노드로, Connector(연결선) 정보를 부모-자식 관계로 전환한다.
        """
        board_id = self._get_board_id_by_name(board_name)

        # 1. 모든 아이템 조회 (Shape, Sticky 등)
        items_res = requests.get(f"{self.base_url}/boards/{board_id}/items", headers=self.headers)
        items_res.raise_for_status()
        items = items_res.json().get("data", [])

        # ID -> 아이템 정보(이름, 타입 등) 매핑
        id_to_data = {
            item["id"]: {
                "name": self._extract_text_from_item(item),
                "type": item["type"]
            }
            for item in items
        }

        # 2. 모든 커넥터 조회
        connectors_res = requests.get(f"{self.base_url}/boards/{board_id}/connectors", headers=self.headers)
        connectors_res.raise_for_status()
        connectors = connectors_res.json().get("data", [])

        # 3. 부모 -> 자식 관계 매핑 (origin -> target)
        parent_to_children: dict[str, list[str]] = {}
        child_to_parent: dict[str, str] = {}
        for conn in connectors:
            start_id = conn.get("startItem", {}).get("id")
            end_id = conn.get("endItem", {}).get("id")
            if start_id and end_id:
                parent_to_children.setdefault(start_id, []).append(end_id)
                child_to_parent[end_id] = start_id

        # 4. 루트 노드 식별 (부모가 없는 노드 중 보드 이름과 일치하는 것)
        root_candidates = [iid for iid in id_to_data if iid not in child_to_parent]
        root_id = None
        for cid in root_candidates:
            if id_to_data[cid]["name"] == board_name:
                root_id = cid
                break
        
        if not root_id and root_candidates:
            # 보드 이름과 일치하는게 없으면 첫 번째 루트 후보 선택
            root_id = root_candidates[0]
        
        if not root_id:
            return Board(name=board_name)

        # 5. 재귀적으로 트리 구성
        def build_node(item_id: str, depth: int) -> Node:
            data = id_to_data[item_id]
            # TODO: Stock과 Node 구분 로직 (임시로 모두 Node 처리 혹은 특정 타입 구분)
            node = Node(name=data["name"], depth=depth)
            
            for child_id in parent_to_children.get(item_id, []):
                # 자식 노드 재귀 생성
                child_node = build_node(child_id, depth + 1)
                node.nodes.append(child_node)
            return node

        board = Board(name=board_name)
        board.root = build_node(root_id, 0)
        return board

    def _extract_text_from_item(self, item: dict) -> str:
        """Item 객체에서 텍스트(이름) 정보를 추출한다."""
        content = item.get("data", {}).get("content", "")
        # HTML 태그 제거 (Miro는 텍스트에 HTML 태그가 포함될 수 있음)
        import re
        clean = re.compile('<.*?>')
        return re.sub(clean, '', content).strip() or item.get("id", "Unknown")

    def save(self, board: Board) -> None:
        """Board 데이터를 Miro 보드에 반영한다.

        기존 보드 내의 모든 아이템을 삭제하고, 도메인 트리를 기반으로 새로운 Shape와 Connector를 생성한다.
        """
        board_id = self._get_board_id_by_name(board.name)

        # 1. 기존 아이템 삭제
        items_res = requests.get(f"{self.base_url}/boards/{board_id}/items", headers=self.headers)
        items_res.raise_for_status()
        items = items_res.json().get("data", [])

        # 삭제 가능한 아이템들 (Miro 시스템 아이템 제외 필요할 수 있으나 일단 전체 삭제 시도)
        for item in items:
            requests.delete(f"{self.base_url}/boards/{board_id}/items/{item['id']}", headers=self.headers)

        # 2. 노드 및 커넥터 생성 (재귀)
        self._create_node_recursively(board_id, board.root, None)

    def _create_node_recursively(self, board_id: str, node: Node, parent_miro_id: str | None) -> str:
        """도메인 노드를 Miro Shape로 생성하고 상위 노드와 연결한다."""
        # 1. Shape 생성
        # TODO: Node와 Stock 타입에 따라 스타일 차별화 (현재는 모두 Shape)
        payload = {
            "data": {
                "content": node.name
            },
            "style": {
                "fillColor": "#ffffff",
                "textAlign": "center"
            },
            "type": "shape"
        }
        
        # 위치 계산 logic이 복잡하므로 일단 기본 위치에 생성 (Miro가 자동으로 겹치지 않게 두지 않음)
        # TODO: 위치(x, y) 알고리즘 도입 검토
        res = requests.post(f"{self.base_url}/boards/{board_id}/shapes", headers=self.headers, json=payload)
        res.raise_for_status()
        miro_id = res.json()["id"]

        # 2. 부모가 있다면 Connector 생성
        if parent_miro_id:
            conn_payload = {
                "startItem": {"id": parent_miro_id},
                "endItem": {"id": miro_id},
                "style": {
                    "strokeColor": "#000000",
                    "strokeWidth": "2.0"
                }
            }
            requests.post(f"{self.base_url}/boards/{board_id}/connectors", headers=self.headers, json=conn_payload)

        # 3. 자식 노드 처리
        for child in node.nodes:
            self._create_node_recursively(board_id, child, miro_id)
        
        return cast(str, miro_id)

