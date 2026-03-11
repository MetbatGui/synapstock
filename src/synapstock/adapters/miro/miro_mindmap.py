"""Miro 마인드맵 어댑터 구현."""

from typing import cast
import requests
from synapstock.domain.models import Board, Node, Stock
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
        id_to_data = {}
        for item in items:
            id_to_data[item["id"]] = {
                "name": self._extract_text_from_item(item),
                "type": item["type"],
                "ticker": item.get("data", {}).get("description", "") if item["type"] == "card" else ""
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
            node = Node(name=data["name"], depth=depth)
            
            for child_id in parent_to_children.get(item_id, []):
                child_data = id_to_data.get(child_id)
                if not child_data:
                    continue
                
                if child_data["type"] == "card":
                    # 카드는 종목으로 인식
                    node.stocks.append(Stock(name=child_data["name"], ticker=child_data.get("ticker", "")))
                else:
                    # 그 외(shape 등)는 서브 노드로 인식
                    node.nodes.append(build_node(child_id, depth + 1))
            return node

        board = Board(name=board_name)
        board.root = build_node(root_id, 0)
        return board

    def _extract_text_from_item(self, item: dict) -> str:
        """Item 객체에서 텍스트(이름) 정보를 추출한다."""
        # Shape/Sticky 등은 data.content, Card는 data.title 사용
        content = item.get("data", {}).get("content") or item.get("data", {}).get("title") or ""
        # HTML 태그 제거
        import re
        clean = re.compile('<.*?>')
        return re.sub(clean, '', content).strip() or item.get("id", "Unknown")

    def save(self, board: Board) -> None:
        """Board 데이터를 Miro 보드에 반영한다 (증분 업데이트).

        보드 전체 데이터를 Fetch하여 도메인 트리와 비교한 뒤, 필요한 항목만 생성/삭제한다.
        """
        board_id = self._get_board_id_by_name(board.name)

        # 1. 현재 Miro 상태 Fetch (load와 유사)
        items_res = requests.get(f"{self.base_url}/boards/{board_id}/items", headers=self.headers)
        items_res.raise_for_status()
        items = items_res.json().get("data", [])

        id_to_data = {}
        for item in items:
            id_to_data[item["id"]] = {
                "name": self._extract_text_from_item(item),
                "type": item["type"],
                "ticker": item.get("data", {}).get("description", "") if item["type"] == "card" else ""
            }

        connectors_res = requests.get(f"{self.base_url}/boards/{board_id}/connectors", headers=self.headers)
        connectors_res.raise_for_status()
        connectors = connectors_res.json().get("data", [])

        parent_to_children: dict[str, list[str]] = {}
        child_to_parent: dict[str, str] = {}
        for conn in connectors:
            sid = conn.get("startItem", {}).get("id")
            eid = conn.get("endItem", {}).get("id")
            if sid and eid:
                parent_to_children.setdefault(sid, []).append(eid)
                child_to_parent[eid] = sid

        # 2. 루트 노드 찾기
        root_candidates = [iid for iid in id_to_data if iid not in child_to_parent]
        root_id = None
        for cid in root_candidates:
            if id_to_data[cid]["name"] == board.name:
                root_id = cid
                break
        
        # 루트가 없으면 생성
        if not root_id:
            payload = {
                "data": {"content": board.name},
                "style": {"fillColor": "#ffffff", "textAlign": "center"},
                "type": "shape"
            }
            res = requests.post(f"{self.base_url}/boards/{board_id}/shapes", headers=self.headers, json=payload)
            res.raise_for_status()
            root_id = res.json()["id"]

        # 3. 재귀적으로 동기화
        if board.root:
            self._sync_node(board_id, board.root, root_id, id_to_data, parent_to_children)

    def _sync_node(
        self, 
        board_id: str, 
        domain_node: Node, 
        miro_id: str, 
        id_to_data: dict, 
        parent_to_children: dict
    ) -> None:
        """도메인 노드와 Miro 아이템을 대조하여 동기화한다."""
        
        # 현재 Miro 아이템의 자식들
        miro_child_ids = parent_to_children.get(miro_id, [])
        miro_children = {cid: id_to_data[cid] for cid in miro_child_ids if cid in id_to_data}

        # 도메인 자식들 (Node + Stock)
        domain_items = []
        for n in domain_node.nodes:
            domain_items.append({"name": n.name, "type": "shape", "obj": n})
        for s in domain_node.stocks:
            domain_items.append({"name": s.name, "type": "card", "obj": s})

        matched_miro_ids = set()

        for d_item in domain_items:
            # 매칭되는 Miro 아이템 찾기 (이름과 타입이 같은 것)
            found_id = None
            for mid, m_data in miro_children.items():
                if mid not in matched_miro_ids and m_data["name"] == d_item["name"] and m_data["type"] == d_item["type"]:
                    found_id = mid
                    break
            
            if found_id:
                # 보존(Keep) 및 하위 재귀 (Node인 경우만)
                matched_miro_ids.add(found_id)
                if d_item["type"] == "shape":
                    self._sync_node(board_id, d_item["obj"], found_id, id_to_data, parent_to_children)
            else:
                # 생성(Create) 및 연결
                new_id = self._create_miro_item_by_type(board_id, d_item)
                self._connect_items(board_id, miro_id, new_id)
                if d_item["type"] == "shape":
                    # 신규 생성 후 하위도 재귀적으로 생성
                    self._sync_node(board_id, d_item["obj"], new_id, {}, {})

        # 도메인에 없는데 Miro에만 있는 것 삭제(Delete)
        for mid in miro_children:
            if mid not in matched_miro_ids:
                requests.delete(f"{self.base_url}/boards/{board_id}/items/{mid}", headers=self.headers)

    def _create_miro_item_by_type(self, board_id: str, d_item: dict) -> str:
        """도메인 아이템 타입에 맞춰 Miro 아이템을 생성한다."""
        if d_item["type"] == "shape":
            payload = {
                "data": {"content": d_item["name"]},
                "style": {"fillColor": "#ffffff", "textAlign": "center"},
                "type": "shape"
            }
            res = requests.post(f"{self.base_url}/boards/{board_id}/shapes", headers=self.headers, json=payload)
        else: # card (Stock)
            stock = d_item["obj"]
            payload = {
                "data": {"title": stock.name, "description": stock.ticker},
                "type": "card"
            }
            res = requests.post(f"{self.base_url}/boards/{board_id}/cards", headers=self.headers, json=payload)
        
        res.raise_for_status()
        return cast(str, res.json()["id"])

    def _connect_items(self, board_id: str, start_id: str, end_id: str) -> None:
        """두 아이템을 Connector로 연결한다."""
        conn_payload = {
            "startItem": {"id": start_id},
            "endItem": {"id": end_id},
            "style": {
                "strokeColor": "#000000",
                "strokeWidth": "2.0"
            }
        }
        requests.post(f"{self.base_url}/boards/{board_id}/connectors", headers=self.headers, json=conn_payload)

