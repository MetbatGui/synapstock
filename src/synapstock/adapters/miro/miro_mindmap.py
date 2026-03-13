"""Miro 마인드맵 어댑터 구현."""

import re
from typing import Any, cast
import requests

from synapstock.domain.models import Board, Node, Stock
from synapstock.domain.ports import MindmapPort

class MiroMindmapAdapter(MindmapPort):
    """Miro V2 API를 사용하는 마인드맵 어댑터.

    기존 Experimental Sync 방식을 버리고, 
    Bulk Upload (create-items) 기능을 활용하여 보드 데이터를 
    좌우 밸런싱된 구조의 커스텀 Shape(Round Rectangle) 형태로 전면 덮어쓴다.
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

    def _extract_text_from_html(self, content: str) -> str:
        """HTML 형태의 텍스트에서 순수 텍스트만 추출한다."""
        clean = re.compile('<.*?>')
        return re.sub(clean, '', content).strip()

    def load(self, board_name: str) -> Board:
        """Miro 보드에서 Shape 기반 커스텀 트리 형태를 읽어서 복원한다."""
        board_id = self._get_board_id_by_name(board_name)
        
        # 1. 모든 아이템 & 커넥터 조회
        items = []
        cursor = ""
        while True:
            url = f"{self.base_url}/boards/{board_id}/items?limit=50"
            if cursor:
                url += f"&cursor={cursor}"
            res = requests.get(url, headers=self.headers)
            if not res.ok:
                break
            data = res.json()
            items.extend(data.get("data", []))
            cursor = data.get("cursor")
            if not cursor:
                break
                
        connectors = []
        cursor = ""
        while True:
            url = f"{self.base_url}/boards/{board_id}/connectors?limit=50"
            if cursor:
                url += f"&cursor={cursor}"
            res = requests.get(url, headers=self.headers)
            if not res.ok:
                break
            data = res.json()
            connectors.extend(data.get("data", []))
            cursor = data.get("cursor")
            if not cursor:
                break
                
        # 2. 분석 및 트리 구성
        item_dict = {item["id"]: item for item in items}
        adjacency: dict[str, list[str]] = {}
        incoming_counts = {item["id"]: 0 for item in items if item["type"] in ["shape", "card"]}
        
        for conn in connectors:
            start_id = conn.get("startItem", {}).get("id")
            end_id = conn.get("endItem", {}).get("id")
            if start_id in item_dict and end_id in item_dict:
                adjacency.setdefault(start_id, []).append(end_id)
                if end_id in incoming_counts:
                    incoming_counts[end_id] += 1
                    
        root_candidates = [iid for iid, count in incoming_counts.items() if count == 0 and iid in adjacency]
        if not root_candidates:
            return Board(name=board_name)
            
        root_id = root_candidates[0]
        
        # 3. 도메인 객체로 파싱
        def build_domain_node(item_id, depth) -> Node:
            item = item_dict[item_id]
            html_content = item.get("data", {}).get("content", "")
            node_name = self._extract_text_from_html(html_content)
            
            node = Node(name=node_name, depth=depth)
            
            for child_id in adjacency.get(item_id, []):
                child_item = item_dict[child_id]
                c_html = child_item.get("data", {}).get("content", "")
                c_name = self._extract_text_from_html(c_html)
                
                # HTML 주석 내부의 티커(ticker) 여부로 Stock 판단
                match = re.search(r"<!--ticker:(.*?)-->", c_html)
                if match:
                    ticker = match.group(1).strip()
                    node.stocks.append(Stock(name=c_name, ticker=ticker))
                else:
                    node.nodes.append(build_domain_node(child_id, depth + 1))
            return node
            
        board = Board(name=board_name)
        board.root = build_domain_node(root_id, 0)
        return board


    def save(self, board: Board) -> None:
        """기존 보드를 완전히 지우고 새로 그린다. (Overwrite)"""
        board_id = self._get_board_id_by_name(board.name)
        
        # 1. 초기화 (모든 아이템 삭제)
        while True:
            res = requests.get(f"{self.base_url}/boards/{board_id}/items?limit=50", headers=self.headers)
            if not res.ok:
                break
            items = res.json().get("data", [])
            if not items:
                break
            for item in items:
                requests.delete(f"{self.base_url}/boards/{board_id}/items/{item['id']}", headers=self.headers)

        if not board.root:
            return

        # 2. 레이아웃 계산 및 생성 (sync와 로직 공유를 위해 sync 호출도 가능하지만, 단순성을 위해 유지)
        self.sync(board)

    def sync(self, board: Board) -> None:
        """기존 아이템과 비교하여 변경된 부분만 PATCH/POST/DELETE 수행."""
        board_id = self._get_board_id_by_name(board.name)
        
        # 1. 가상 레이아웃 계산
        target_layout = self._calculate_balanced_layout(board.root)
        
        # 2. 현재 Miro 아이템 조회
        items = []
        cursor = ""
        while True:
            url = f"{self.base_url}/boards/{board_id}/items?limit=50"
            if cursor:
                url += f"&cursor={cursor}"
            res = requests.get(url, headers=self.headers)
            if not res.ok:
                break
            data = res.json()
            items.extend(data.get("data", []))
            cursor = data.get("cursor")
            if not cursor:
                break

        # 3. 매칭 맵 구성
        existing_map: dict[tuple[str, str, bool], list[dict]] = {}
        for item in items:
            if item["type"] != "shape":
                continue
            c_html = item.get("data", {}).get("content", "")
            name = self._extract_text_from_html(c_html)
            ticker_match = re.search(r"<!--ticker:(.*?)-->", c_html)
            ticker = ticker_match.group(1) if ticker_match else ""
            is_stk = bool(ticker)
            key = (name, ticker, is_stk)
            existing_map.setdefault(key, []).append(item)

        # 4. 동기화 루프
        item_ids = {}
        for (obj, depth, x, y, is_stock) in target_layout:
            name = obj.name
            ticker = obj.ticker if is_stock else ""
            key = (name, ticker, is_stock)
            
            if is_stock:
                link_url = f"https://finance.naver.com/item/main.nhn?code={ticker}"
                c_html = f"<p style=\"text-align: center;\"><a href=\"{link_url}\"><strong>{name}</strong></a></p><!--ticker:{ticker}-->"
            else:
                c_html = f"<p style=\"text-align: center;\"><strong>{name}</strong></p>"

            if depth == 0:
                fill_color = "#e3f2fd"
            elif depth == 1:
                fill_color = "#ede7f6"
            elif is_stock:
                fill_color = "#e8f5e9"
            else:
                fill_color = "#fff3e0"

            match = existing_map.get(key, []).pop(0) if existing_map.get(key) else None

            if match:
                m_id = match["id"]
                item_ids[id(obj)] = m_id
                m_pos = match.get("position", {})
                m_data = match.get("data", {})
                m_style = match.get("style", {})
                
                if (abs(m_pos.get("x", 0) - x) > 0.5 or abs(m_pos.get("y", 0) - y) > 0.5 or 
                    m_data.get("content") != c_html or m_style.get("fillColor", "").lower() != fill_color.lower()):
                    patch_payload = {
                        "data": {"content": c_html},
                        "position": {"x": x, "y": y},
                        "style": {"fillColor": fill_color}
                    }
                    requests.patch(f"{self.base_url}/boards/{board_id}/items/{m_id}", headers=self.headers, json=patch_payload)
            else:
                calc_width = max(100, len(name) * 16 + 40)
                post_payload = {
                    "type": "shape",
                    "data": {"content": c_html, "shape": "round_rectangle"},
                    "style": {"fillOpacity": "1.0", "fillColor": fill_color, "textAlign": "center", "textAlignVertical": "middle"},
                    "position": {"x": x, "y": y},
                    "geometry": {"width": calc_width, "height": 44}
                }
                res = requests.post(f"{self.base_url}/boards/{board_id}/shapes", headers=self.headers, json=post_payload)
                if res.ok:
                    item_ids[id(obj)] = res.json()["id"]

        # 5. 삭제 및 커넥터 재생성
        for items_to_del in existing_map.values():
            for it in items_to_del:
                requests.delete(f"{self.base_url}/boards/{board_id}/items/{it['id']}", headers=self.headers)

        self._refresh_connectors(board_id, item_ids, board.root)

    def _refresh_connectors(self, board_id: str, item_ids: dict, root_node: Node) -> None:
        """커넥터 전체 삭제 후 현재 구조에 맞게 재생성."""
        while True:
            res = requests.get(f"{self.base_url}/boards/{board_id}/connectors?limit=50", headers=self.headers)
            if not res.ok:
                break
            conns = res.json().get("data", [])
            if not conns:
                break
            for c in conns:
                requests.delete(f"{self.base_url}/boards/{board_id}/connectors/{c['id']}", headers=self.headers)

        def draw(p):
            p_id = item_ids.get(id(p))
            if not p_id:
                return
            for child in (p.nodes + p.stocks):
                c_id = item_ids.get(id(child))
                if c_id:
                    requests.post(f"{self.base_url}/boards/{board_id}/connectors", headers=self.headers, json={
                        "startItem": {"id": p_id}, "endItem": {"id": c_id},
                        "style": {"strokeColor": "#000000", "strokeWidth": "1.5"}
                    })
                if isinstance(child, Node):
                    draw(child)
        draw(root_node)

    def _calculate_balanced_layout(self, root_node: Node) -> list:
        """루트 노드의 자식들을 좌우로 균등 배치하고 x, y 좌표가 계산된 정보를 반환.
        Returns:
            list[tuple]: [(obj, depth, x, y, is_stock), ...]
        """
        def get_leaf_count(n):
            if isinstance(n, Stock):
                return 1
            if not n.nodes and not n.stocks:
                return 1
            count = sum(get_leaf_count(c) for c in n.nodes)
            count += len(n.stocks)
            return count

        top_children = root_node.nodes + root_node.stocks
        top_children.sort(key=get_leaf_count, reverse=True)
        left_kids, right_kids = [], []
        left_leaves, right_leaves = 0, 0
        
        for c in top_children:
            if left_leaves <= right_leaves:
                left_kids.append(c)
                left_leaves += get_leaf_count(c)
            else:
                right_kids.append(c)
                right_leaves += get_leaf_count(c)

        def layout_subtree(nodes, direction_x):
            layout = []
            global_y = 0
            
            def traverse(node_obj, depth):
                nonlocal global_y
                is_stk = isinstance(node_obj, Stock)
                children = [] if is_stk else (node_obj.nodes + node_obj.stocks)
                
                if not children:
                    my_y = global_y
                    global_y += 80  # 말단 노드 Y 간격
                else:
                    child_ys = []
                    for child in children:
                        cy = traverse(child, depth + 1)
                        child_ys.append(cy)
                    my_y = sum(child_ys) / len(child_ys)
                
                my_x = depth * 350 * direction_x
                layout.append((node_obj, depth, my_x, my_y, is_stk))
                return my_y

            for n in nodes:
                traverse(n, 1)
                global_y += 60 # 섹터 그룹 간 Y 간격 추가
                
            if layout:
                min_y = min(ly[3] for ly in layout)
                max_y = max(ly[3] for ly in layout)
                center_y = (min_y + max_y) / 2
                layout = [(obj, d, x, y - center_y, is_stk) for obj, d, x, y, is_stk in layout]
            return layout

        left_layout = layout_subtree(left_kids, -1)
        right_layout = layout_subtree(right_kids, 1)
        
        all_layout: list[Any] = []
        all_layout.extend(left_layout)
        all_layout.extend(right_layout)
        all_layout.append((root_node, 0, 0, 0, False)) # Root 노드
        
        return all_layout
