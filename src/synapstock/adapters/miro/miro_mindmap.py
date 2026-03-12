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

        Miro의 Experimental Mindmap API를 통해 mindmap_node들을 읽어와 도메인 노드 트리로 복원한다.
        """
        board_id = self._get_board_id_by_name(board_name)

        # 1. 모든 mindmap 노드 조회
        res = requests.get(f"{self.base_url}-experimental/boards/{board_id}/mindmap_nodes", headers=self.headers)
        res.raise_for_status()
        items = res.json().get("data", [])

        # ID -> 아이템 정보 맵핑
        id_to_data = {}
        for item in items:
            raw_content = item.get("data", {}).get("nodeView", {}).get("data", {}).get("content", "")
            id_to_data[item["id"]] = {
                "name": self._extract_text_from_html(raw_content) or item["id"],
                "raw_content": raw_content,
                "parent_id": item.get("parent", {}).get("id") if item.get("parent") else None
            }

        # 2. 부모 -> 자식 관계 매핑
        parent_to_children: dict[str, list[str]] = {}
        for iid, data in id_to_data.items():
            pid = data["parent_id"]
            if pid:
                parent_to_children.setdefault(pid, []).append(iid)

        # 3. 루트 노드 식별 (부모가 없는 노드)
        root_candidates = [iid for iid, data in id_to_data.items() if not data["parent_id"]]
        root_id = None
        for r_id in root_candidates:
            if id_to_data[r_id]["name"] == board_name:
                root_id = r_id
                break
        
        if not root_id and root_candidates:
            root_id = root_candidates[0]
            
        if not root_id:
            return Board(name=board_name)

        # 4. 재귀적으로 트리 구성
        def build_node(item_id: str, depth: int) -> Node:
            data = id_to_data[item_id]
            # 카드는 '<br/>ticker: ' 등의 문자열을 포함함
            name = data["name"]
            raw_content = data["raw_content"]
            
            node = Node(name=name, depth=depth)
            
            for child_id in parent_to_children.get(item_id, []):
                child_data = id_to_data.get(child_id)
                if not child_data:
                    continue
                
                c_raw = child_data["raw_content"]
                c_name = child_data["name"]
                
                # 원시 텍스트에 숨겨진 종목 시그니처가 있으면 카드로 파싱
                if "<!--ticker:" in c_raw:
                    import re
                    match = re.search(r"<!--ticker:(.*?)-->", c_raw)
                    ticker = match.group(1).strip() if match else ""
                    node.stocks.append(Stock(name=c_name, ticker=ticker))
                else:
                    node.nodes.append(build_node(child_id, depth + 1))
            return node

        board = Board(name=board_name)
        board.root = build_node(root_id, 0)
        return board

    def _extract_text_from_html(self, content: str) -> str:
        """HTML 형태의 텍스트에서 순수 텍스트만 추출한다."""
        import re
        clean = re.compile('<.*?>')
        return re.sub(clean, '', content).strip()

    def save(self, board: Board) -> None:
        """Board 데이터를 Miro 보드의 Mindmap API를 통해 반영한다 (증분 업데이트)."""
        board_id = self._get_board_id_by_name(board.name)

        # 1. 현재 Miro 상태 Fetch
        res = requests.get(f"{self.base_url}-experimental/boards/{board_id}/mindmap_nodes", headers=self.headers)
        res.raise_for_status()
        items = res.json().get("data", [])

        id_to_data = {}
        child_to_parent = {}
        parent_to_children = {}
        for item in items:
            iid = item["id"]
            raw_content = item.get("data", {}).get("nodeView", {}).get("data", {}).get("content", "")
            pid = item.get("parent", {}).get("id") if item.get("parent") else None
            
            id_to_data[iid] = {
                "raw_content": raw_content,
                "name": self._extract_text_from_html(raw_content) or iid
            }
            if pid:
                child_to_parent[iid] = pid
                parent_to_children.setdefault(pid, []).append(iid)

        # 2. 루트 찾기
        root_candidates = [iid for iid in id_to_data if iid not in child_to_parent]
        root_id = None
        for r_id in root_candidates:
            if id_to_data[r_id]["name"] == board.name:
                root_id = r_id
                break
        
        # 루트가 없으면 생성
        if not root_id:
            payload = {"data": {"nodeView": {"data": {"content": board.name}}}}
            res = requests.post(f"{self.base_url}-experimental/boards/{board_id}/mindmap_nodes", headers=self.headers, json=payload)
            res.raise_for_status()
            root_id = res.json()["id"]
            id_to_data[root_id] = {"raw_content": board.name, "name": board.name}

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
        """도메인 노드와 Miro 마인드맵 아이템을 대조하여 동기화한다."""
        
        miro_child_ids = parent_to_children.get(miro_id, [])
        miro_children = {cid: id_to_data[cid] for cid in miro_child_ids if cid in id_to_data}

        # 도메인 자식들 데이터화 (Node + Stock)
        domain_items = []
        for n in domain_node.nodes:
            domain_items.append({"name": n.name, "raw_content": n.name, "type": "node", "obj": n})
        for s in domain_node.stocks:
            link_url = f"https://finance.naver.com/item/main.nhn?code={s.ticker}"
            card_content = f"<a href=\"{link_url}\">{s.name}</a><!--ticker:{s.ticker}-->"
            domain_items.append({"name": s.name, "raw_content": card_content, "type": "card", "obj": s})

        matched_miro_ids = set()

        for d_item in domain_items:
            found_id = None
            # 이름으로 매칭 시도 (Stock의 경우 파싱된 이름값과 비교)
            for mid, m_data in miro_children.items():
                if mid not in matched_miro_ids:
                    is_match = False
                    if d_item["type"] == "node" and m_data["name"] == d_item["name"]:
                        is_match = True
                    # 카드의 경우 ticker 정보 포함 여부로 확실히 카드임을 식별하거나 텍스트 이름으로 매칭
                    elif d_item["type"] == "card" and (str(d_item["obj"].ticker) in m_data["raw_content"] or d_item["name"] in m_data["name"]):
                        is_match = True
                        
                    if is_match:
                        found_id = mid
                        break
            
            if found_id:
                # 보존 및 하위 순회
                matched_miro_ids.add(found_id)
                if d_item["type"] == "node":
                    self._sync_node(board_id, d_item["obj"], found_id, id_to_data, parent_to_children)
            else:
                # 생성
                new_id = self._create_mindmap_node(board_id, miro_id, d_item["raw_content"])
                if d_item["type"] == "node":
                    self._sync_node(board_id, d_item["obj"], new_id, {}, {})

        # 도메인에 없는데 Miro에만 있는 것 삭제
        for mid in miro_children:
            if mid not in matched_miro_ids:
                requests.delete(f"{self.base_url}-experimental/boards/{board_id}/mindmap_nodes/{mid}", headers=self.headers)

    def _create_mindmap_node(self, board_id: str, parent_id: str, content: str) -> str:
        """새로운 자식 마인드맵 노드를 생성한다."""
        payload = {
            "data": {"nodeView": {"data": {"content": content}}},
            "parent": {"id": parent_id}
        }
        res = requests.post(f"{self.base_url}-experimental/boards/{board_id}/mindmap_nodes", headers=self.headers, json=payload)
        res.raise_for_status()
        return cast(str, res.json()["id"])
