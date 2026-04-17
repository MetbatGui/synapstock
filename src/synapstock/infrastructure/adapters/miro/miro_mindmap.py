"""Miro 마인드맵 어댑터 구현."""

import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast

import requests

logger = logging.getLogger(__name__)
from synapstock.domain.models import Board, Node, Stock
from synapstock.domain.ports import MindmapPort


class MiroMindmapAdapter(MindmapPort):
    """마인드맵 데이터를 동기화하기 위한 Miro V2 API 어댑터입니다.

    이 구현체는 대량 아이템 생성 기능을 사용하며, 균형 잡힌 레이아웃 계산을 통해
    보드를 커스텀 Shape(둥근 직사각형) 트리의 형태로 정렬합니다.
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
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        # 재시도 로직 추가 (429, 500, 502, 503, 504)
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        retry_strategy = Retry(
            total=5,
            backoff_factor=1, # 1, 2, 4, 8, 16초 대기
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def list_boards(self) -> list[str]:
        """현재 토큰으로 접근 가능한 모든 Miro 보드의 이름을 나열합니다.

        Returns:
            list[str]: 보드 이름 목록.
        """
        res = self.session.get(f"{self.base_url}/boards")
        res.raise_for_status()
        data = res.json()
        boards = cast(list[dict[str, str]], data.get("data", []))
        return [board["name"] for board in boards]

    def _get_or_create_board_id(self, board_name: str) -> str:
        """이름으로 보드 ID를 조회하며, 존재하지 않으면 새로 생성합니다.

        Args:
            board_name: 보드 이름.

        Returns:
            str: Miro 보드 ID.
        """
        res = self.session.get(f"{self.base_url}/boards")
        res.raise_for_status()
        data = res.json()
        boards = cast(list[dict[str, str]], data.get("data", []))
        for board in boards:
            if board["name"] == board_name:
                return cast(str, board["id"])

        # 보드가 없으면 생성
        logger.info(f"[*] Miro 보드 '{board_name}'가 존재하지 않아 새로 생성합니다.")
        create_res = self.session.post(
            f"{self.base_url}/boards",
            json={"name": board_name, "description": "SynapStock Automated Board"}
        )
        create_res.raise_for_status()
        return cast(str, create_res.json()["id"])

    def _get_board_id_by_name(self, board_name: str) -> str:
        """이름으로 기존 보드의 ID를 조회합니다.

        Args:
            board_name: 보드 이름.

        Returns:
            str: Miro 보드 ID.

        Raises:
            FileNotFoundError: 주어진 이름의 보드를 찾을 수 없는 경우.
        """
        # _get_or_create_board_id와 중복을 피하기 위해 내부적으로만 사용하거나 삭제 고려
        # 일단 기존 코드 호환을 위해 유지
        res = self.session.get(f"{self.base_url}/boards")
        res.raise_for_status()
        data = res.json()
        boards = cast(list[dict[str, str]], data.get("data", []))
        for board in boards:
            if board["name"] == board_name:
                return cast(str, board["id"])
        raise FileNotFoundError(f"Miro board not found: {board_name}")

    def _extract_text_from_html(self, content: str) -> str:
        """HTML 형태의 텍스트에서 순수 텍스트만 추출한다."""
        import html
        # 태그 제거
        clean = re.compile('<.*?>')
        text = re.sub(clean, '', content)
        # HTML 엔티티 변환 (&nbsp; -> ' ', &amp; -> '&' 등)
        text = html.unescape(text)
        # 화이트스페이스 정문화 (줄바꿈 등을 공백으로)
        text = " ".join(text.split())
        return text.strip()

    def load(self, board_name: str, progress_callback: Callable[[str, float], None] | None = None) -> Board:
        """Miro 보드 구조로부터 Board 도메인 객체를 복원합니다.

        Shape와 커넥터를 분석하여 계층 구조를 재구성합니다.

        Args:
            board_name: 불러올 보드의 이름.
            progress_callback: 진행 상태 업데이트를 위한 선택적 콜백.

        Returns:
            Board: 재구성된 보드 객체.
        """
        def update_progress(msg, val):
            if progress_callback:
                progress_callback(msg, val)

        update_progress(f"보드 '{board_name}' ID 조회 중...", 0.05)
        board_id = self._get_board_id_by_name(board_name)

        # 1. 모든 아이템 조회
        update_progress("Miro 아이템 목록 가져오는 중...", 0.1)
        items = []
        cursor = ""
        while True:
            url = f"{self.base_url}/boards/{board_id}/items?limit=50"
            if cursor:
                url += f"&cursor={cursor}"
            res = self.session.get(url)
            if not res.ok:
                break
            data = res.json()
            fetched = data.get("data", [])
            items.extend(fetched)
            update_progress(f"아이템 가져오는 중... (현재 {len(items)}개)", 0.1 + min(0.3, len(items) * 0.01))
            cursor = data.get("cursor")
            if not cursor:
                break

        # 2. 모든 커넥터 조회
        update_progress("Miro 커넥터(연결선) 목록 가져오는 중...", 0.4)
        connectors = []
        cursor = ""
        while True:
            url = f"{self.base_url}/boards/{board_id}/connectors?limit=50"
            if cursor:
                url += f"&cursor={cursor}"
            res = self.session.get(url)
            if not res.ok:
                break
            data = res.json()
            fetched = data.get("data", [])
            connectors.extend(fetched)
            update_progress(f"커넥터 가져오는 중... (현재 {len(connectors)}개)", 0.4 + min(0.2, len(connectors) * 0.01))
            cursor = data.get("cursor")
            if not cursor:
                break

        # 3. 분석 및 트리 구성
        update_progress("마인드맵 구조 분석 중...", 0.7)
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
            update_progress("데이터가 비어있습니다.", 1.0)
            return Board(name=board_name)

        root_id = root_candidates[0]

        # 4. 도메인 객체로 파싱
        update_progress("도메인 모델로 변환 중...", 0.8)
        def build_domain_node(item_id, depth) -> Node:
            item = item_dict[item_id]
            html_content = item.get("data", {}).get("content", "")
            node_name = self._extract_text_from_html(html_content)

            node = Node(name=node_name, depth=depth)

            for child_id in adjacency.get(item_id, []):
                child_item = item_dict[child_id]
                c_html = child_item.get("data", {}).get("content", "")
                c_name = self._extract_text_from_html(c_html)

                # 1. HTML 주석 내부의 티커(ticker) 여부 확인
                ticker = None
                comment_match = re.search(r"<!--ticker:(.*?)-->", c_html)
                if comment_match:
                    ticker = comment_match.group(1).strip()
                else:
                    # 2. 새로운 로컬 스톡 URL 패턴 확인 (/stock/TICKER)
                    local_match = re.search(r"/stock/([0-9]{6,k})", c_html)
                    if local_match:
                        ticker = local_match.group(1)
                    else:
                        # 3. Naver Finance URL 패턴에서 티커 추출 (&#61; 또는 = 대응)
                        url_match = re.search(r"code(?:&#61;|=)([0-9]{6})", c_html)
                        if url_match:
                            ticker = url_match.group(1)

                if ticker:
                    node.stocks.append(Stock(name=c_name, ticker=ticker))
                else:
                    node.nodes.append(build_domain_node(child_id, depth + 1))
            return node

        board = Board(name=board_name)
        board.root = build_domain_node(root_id, 0)
        update_progress("로드 완료!", 1.0)
        return board


    def save(self, board: Board, progress_callback: Callable[[str, float], None] | None = None) -> None:
        """현재 Board 데이터로 Miro 보드를 덮어씁니다.

        기존의 모든 아이템을 삭제하고 새로 동기화 작업을 수행합니다.

        Args:
            board: 저장할 보드 데이터.
            progress_callback: 진행 상태 업데이트를 위한 선택적 콜백.
        """
        def update_progress(msg, val):
            if progress_callback:
                progress_callback(msg, val)

        board_id = self._get_or_create_board_id(board.name)

        # 1. 초기화 (모든 아이템 삭제)
        update_progress(f"Miro 보드 '{board.name}' 초기화 중 (기존 아이템 삭제)...", 0.0)
        while True:
            res = self.session.get(f"{self.base_url}/boards/{board_id}/items?limit=50")
            if not res.ok:
                break
            items = res.json().get("data", [])
            if not items:
                break
            for item in items:
                self.session.delete(f"{self.base_url}/boards/{board_id}/items/{item['id']}")

        if not board.root:
            update_progress("보드가 비어 있어 초기화만 수행하고 종료합니다.", 1.0)
            return

        # 2. 레이아웃 계산 및 생성
        self.sync(board, progress_callback=progress_callback)

    def sync(self, board: Board, progress_callback: Callable[[str, float], None] | None = None) -> None:
        """변경된 부분만 Miro 보드에 동기화합니다.

        아이템과 커넥터의 생성, 업데이트, 삭제를 처리합니다.

        Args:
            board: 동기화할 보드 데이터.
            progress_callback: 진행 상태 업데이트를 위한 선택적 콜백.
        """
        def update_progress(msg, val):
            if progress_callback:
                progress_callback(msg, val)

        update_progress(f"보드 '{board.name}' 동기화 준비 중...", 0.05)
        board_id = self._get_or_create_board_id(board.name)

        # 1. 가상 레이아웃 계산
        update_progress("새로운 레이아웃 계산 중...", 0.1)
        target_layout = self._calculate_balanced_layout(board.root)

        # 2. 현재 Miro 아이템 조회
        update_progress("현재 Miro 보드 아이템 정보 조회 중...", 0.2)
        items = []
        cursor = ""
        while True:
            url = f"{self.base_url}/boards/{board_id}/items?limit=50"
            if cursor:
                url += f"&cursor={cursor}"
            res = self.session.get(url)
            if not res.ok:
                break
            data = res.json()
            items.extend(data.get("data", []))
            cursor = data.get("cursor")
            if not cursor:
                break
        update_progress(f"Miro 아이템 {len(items)}개 조회 완료", 0.3)

        # 3. 매칭 맵 구성
        update_progress("변경 사항 분석 중...", 0.35)
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

        # 4. 동기화 루프 (병렬 처리)
        update_progress("아이템 업데이트 및 생성 진행 중 (병렬)...", 0.4)
        item_ids = {}
        total_targets = len(target_layout)

        def process_item(item_info):
            obj, depth, x, y, is_stock = item_info
            name = obj.name
            ticker = obj.ticker if is_stock else ""
            key = (name, ticker, is_stock)

            if is_stock:
                link_url = f"http://localhost:8090/stock/{ticker}"
                c_html = (
                    f"<p style=\"text-align: center;\">"
                    f"<a href=\"{link_url}\"><strong>{name}</strong></a>"
                    f"</p><!--ticker:{ticker}-->"
                )
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
                res_info = (id(obj), m_id, x)
                m_pos = match.get("position", {})
                m_data = match.get("data", {})
                m_style = match.get("style", {})

                # 좌표 이동 허용 오차 0.5px
                if (abs(m_pos.get("x", 0) - x) > 0.5 or abs(m_pos.get("y", 0) - y) > 0.5 or
                    m_data.get("content") != c_html or m_style.get("fillColor", "").lower() != fill_color.lower()):
                    patch_payload = {
                        "data": {"content": c_html},
                        "position": {"x": x, "y": y},
                        "style": {"fillColor": fill_color}
                    }
                    res = self.session.patch(f"{self.base_url}/boards/{board_id}/items/{m_id}", json=patch_payload)
                    res.raise_for_status()
                return res_info
            else:
                calc_width = max(100, len(name) * 16 + 40)
                post_payload = {
                    "data": {"content": c_html, "shape": "round_rectangle"},
                    "style": {
                        "fillOpacity": "1.0",
                        "fillColor": fill_color,
                        "textAlign": "center",
                        "textAlignVertical": "middle"
                    },
                    "position": {"x": x, "y": y},
                    "geometry": {"width": calc_width, "height": 44}
                }
                res = self.session.post(f"{self.base_url}/boards/{board_id}/shapes", json=post_payload)
                if not res.ok:
                    raise Exception(f"Miro Shape 생성 실패: {res.status_code} {res.text}")
                return (id(obj), res.json()["id"], x)

        with ThreadPoolExecutor(max_workers=8) as executor:
            from concurrent.futures import as_completed
            futures = [executor.submit(process_item, target) for target in target_layout]
            for i, future in enumerate(as_completed(futures)):
                obj_id, m_id, x = future.result()
                item_ids[obj_id] = {"id": m_id, "x": x}
                update_progress(f"아이템 동기화 중 ({i+1}/{total_targets})...", 0.4 + (i+1)/total_targets * 0.4)

        # 5. 삭제 (병렬 처리)
        update_progress("필요 없는 아이템 삭제 중 (병렬)...", 0.85)
        to_delete = [it["id"] for items_to_del in existing_map.values() for it in items_to_del]

        def delete_item(m_id):
            self.session.delete(f"{self.base_url}/boards/{board_id}/items/{m_id}")

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(delete_item, to_delete))

        update_progress("연결선(Connector) 정보 갱신 중...", 0.9)
        self._refresh_connectors(board_id, item_ids, board.root)
        update_progress("동기화 완료!", 1.0)

    def _refresh_connectors(self, board_id: str, item_ids: dict, root_node: Node) -> None:
        """커넥터 상태를 파악하여 변경된 부분만 동기화 (차분 업데이트)."""
        # 1. 현재 커넥터 목록 조회
        current_connectors = []
        cursor = ""
        while True:
            url = f"{self.base_url}/boards/{board_id}/connectors?limit=50"
            if cursor:
                url += f"&cursor={cursor}"
            res = self.session.get(url)
            if not res.ok:
                break
            data = res.json()
            current_connectors.extend(data.get("data", []))
            cursor = data.get("cursor")
            if not cursor:
                break

        # (startItem_id, endItem_id) -> connector_id 맵 구성
        conn_map = {}
        for c in current_connectors:
            s_id = c.get("startItem", {}).get("id")
            e_id = c.get("endItem", {}).get("id")
            if s_id and e_id:
                conn_map[(s_id, e_id)] = c["id"]

        # 2. 목표 커넥터 계산
        target_conn_data = [] # list of dict for POST
        target_conns_set = set() # for tracking

        def collect_targets(p):
            p_info = item_ids.get(id(p))
            if not p_info:
                return
            p_id = p_info["id"]
            p_x = p_info["x"]

            for child in (p.nodes + p.stocks):
                c_info = item_ids.get(id(child))
                if c_info:
                    c_id = c_info["id"]
                    c_x = c_info["x"]

                    if c_x > p_x:
                        start_snap, end_snap = "right", "left"
                    else:
                        start_snap, end_snap = "left", "right"

                    pair = (p_id, c_id)
                    target_conns_set.add(pair)

                    if pair not in conn_map:
                        target_conn_data.append({
                            "startItem": {"id": p_id, "snapTo": start_snap},
                            "endItem": {"id": c_id, "snapTo": end_snap},
                            "style": {"strokeColor": "#000000", "strokeWidth": "1.5"}
                        })

                if isinstance(child, Node):
                    collect_targets(child)

        collect_targets(root_node)

        # 3. 병렬 작업 수행 (생성 및 삭제)
        def post_conn(payload):
            self.session.post(f"{self.base_url}/boards/{board_id}/connectors", json=payload)

        def delete_conn(c_id):
            self.session.delete(f"{self.base_url}/boards/{board_id}/connectors/{c_id}")

        to_delete_conns = [c_id for pair, c_id in conn_map.items() if pair not in target_conns_set]

        with ThreadPoolExecutor(max_workers=8) as executor:
            # 커넥터는 가볍고 개수가 많을 수 있으므로 worker 수를 조금 더 늘림
            executor.map(post_conn, target_conn_data)
            executor.map(delete_conn, to_delete_conns)

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

            # 1. 먼저 Y 좌표와 계층 구조를 계산 (traverse)
            # 여기서는 X 좌표를 depth 기반의 '기본 X'로 임시 저장
            node_data_list: list[dict[str, Any]] = [] # (node, depth, children_count, temp_y, temp_x, parent_idx)

            global_y = 0

            def calculate_y(node_obj, depth, parent_idx=-1):
                nonlocal global_y
                is_stk = isinstance(node_obj, Stock)
                children = [] if is_stk else (node_obj.nodes + node_obj.stocks)

                my_idx = len(node_data_list)
                node_data_list.append({
                    "obj": node_obj, "depth": depth, "is_stk": is_stk,
                    "parent_idx": parent_idx, "children": children
                })

                if not children:
                    my_y = global_y
                    global_y += 55 # 리프 간 최소 간격
                else:
                    child_ys = []
                    for child in children:
                        cy = calculate_y(child, depth + 1, my_idx)
                        child_ys.append(cy)
                    my_y = sum(child_ys) / len(child_ys)
                    # 하위 뭉치가 끝날 때 그룹 간 구분을 위해 추가 여백 부여
                    global_y += 40

                node_data_list[my_idx]["y"] = my_y
                return my_y

            for n in nodes:
                calculate_y(n, 1, -1)
                global_y += 100 # 루트 직계 자식 간의 간격 확대

            if not node_data_list:
                return []

            # 2. Y축 중앙 정렬
            min_y = min(nd["y"] for nd in node_data_list)
            max_y = max(nd["y"] for nd in node_data_list)
            center_y = (min_y + max_y) / 2
            for nd in node_data_list:
                nd["y"] -= center_y

            # 3. 재귀적으로 X 좌표 계산 (Branching/Fan-out)
            # |child_x| > |parent_x| 보장 및 '강력한 역부채꼴(Aggressive Concave)' 적용
            def calculate_x_convex(parent_idx, px):
                siblings_indices = [i for i, nd in enumerate(node_data_list) if nd["parent_idx"] == parent_idx]
                if not siblings_indices:
                    return

                s_ys = [node_data_list[idx]["y"] for idx in siblings_indices]
                min_sy = min(s_ys)
                max_sy = max(s_ys)
                y_range = max_sy - min_sy
                y_center = (min_sy + max_sy) / 2

                for idx in siblings_indices:
                    nd = node_data_list[idx]
                    cur_y = nd["y"]

                    # 다시 중앙이 돌출되는 볼록한 부채꼴(Convex)로 수정 (간격 넓히고 곡률 완화)
                    base_dx = 250 * direction_x

                    protrusion_dx = 0
                    if y_range > 0:
                        norm_dist = abs(cur_y - y_center) / (y_range / 2 if y_range > 0 else 1)
                        # 아이템이 많아질수록(y_range가 커질수록) 곡률 가중치를 동적으로 높여 평평해지는 현상 방지
                        # 기본 200px에서 시작하여 y_range의 15%를 가산 (최대 600px까지 확장)
                        curve_weight = 200 + min(400, y_range * 0.15)
                        protrusion_dx = (1 - (norm_dist ** 2)) * curve_weight * direction_x

                    my_x = px + base_dx + protrusion_dx
                    nd["x"] = my_x

                    calculate_x_convex(idx, my_x)

            calculate_x_convex(-1, 0)

            # 최종 레이아웃 결과로 변환
            return [(nd["obj"], nd["depth"], nd["x"], nd["y"], nd["is_stk"]) for nd in node_data_list]

        left_layout = layout_subtree(left_kids, -1)
        right_layout = layout_subtree(right_kids, 1)

        all_layout: list[Any] = []
        all_layout.extend(left_layout)
        all_layout.extend(right_layout)
        all_layout.append((root_node, 0, 0, 0, False)) # Root 노드

        return all_layout

