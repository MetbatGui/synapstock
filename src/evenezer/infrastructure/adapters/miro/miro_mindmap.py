"""Miro 마인드맵 어댑터 구현."""

import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast

import requests

logger = logging.getLogger(__name__)
from evenezer.domain.models import Board, Node, Stock
from evenezer.domain.ports import MindmapPort


class MiroMindmapAdapter(MindmapPort):
    """마인드맵 데이터를 동기화하기 위한 Miro V2 API 어댑터입니다.

    이 구현체는 대량 아이템 생성 기능을 사용하며, 균형 잡힌 레이아웃 계산을 통해
    보드를 커스텀 Shape(둥근 직사각형) 트리의 형태로 정렬합니다.
    """

    def __init__(self, api_token: str):
        """MiroMindmapAdapter를 초기화하고 HTTP 세션 및 타임아웃, 재시도 정책을 설정합니다.

        Args:
            api_token: Miro API 액세스 토큰.
        """
        self.api_token = api_token
        self.base_url = "https://api.miro.com/v2"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        # 재시도 로직 추가 (429, 500, 502, 503, 504)
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        retry_strategy = Retry(
            total=5,
            backoff_factor=1,  # 1, 2, 4, 8, 16초 대기
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def list_boards(self) -> list[str]:
        """현재 토큰으로 접근 가능한 모든 Miro 보드의 이름을 나열합니다.

        Returns:
            보드 이름 목록.
        """
        res = self.session.get(f"{self.base_url}/boards")
        res.raise_for_status()
        data = res.json()
        boards = cast(list[dict[str, str]], data.get("data", []))
        return [board["name"] for board in boards]

    def _get_or_create_board_id(self, board_name: str) -> str:
        """이름으로 보드 ID를 조회하며, 존재하지 않으면 새로 생성합니다.

        Args:
            board_name: 조회 및 생성할 대상 보드 이름.

        Returns:
            대상 Miro 보드의 고유 ID.
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
            f"{self.base_url}/boards", json={"name": board_name, "description": "Evenezer Automated Board"}
        )
        create_res.raise_for_status()
        return cast(str, create_res.json()["id"])

    def _get_board_id_by_name(self, board_name: str) -> str:
        """이름으로 기존 보드의 ID를 조회합니다.

        Args:
            board_name: 찾고자 하는 Miro 보드 이름.

        Returns:
            Miro 보드의 고유 ID.

        Raises:
            FileNotFoundError: 주어진 이름의 보드를 찾을 수 없는 경우.
        """
        res = self.session.get(f"{self.base_url}/boards")
        res.raise_for_status()
        data = res.json()
        boards = cast(list[dict[str, str]], data.get("data", []))
        for board in boards:
            if board["name"] == board_name:
                return cast(str, board["id"])
        raise FileNotFoundError(f"Miro board not found: {board_name}")

    def _extract_text_from_html(self, content: str) -> str:
        """HTML 태그와 엔티티가 포함된 문자열에서 순수 텍스트만 추출하고 정규화합니다.

        Args:
            content: 원본 HTML 문자열.

        Returns:
            HTML 태그가 제거되고 화이트스페이스가 정리된 순수 문자열.
        """
        import html

        # 태그 제거
        clean = re.compile("<.*?>")
        text = re.sub(clean, "", content)
        # HTML 엔티티 변환 (&nbsp; -> ' ', &amp; -> '&' 등)
        text = html.unescape(text)
        # 화이트스페이스 정문화 (줄바꿈 등을 공백으로)
        text = " ".join(text.split())
        return text.strip()

    def load(self, board_name: str, progress_callback: Callable[[str, float], None] | None = None) -> Board:
        """Miro 보드의 Shape와 커넥터 구조를 비동기적으로 스캔하여 Board 도메인 객체로 역직렬화합니다.

        Args:
            board_name: 복원할 Miro 보드 이름.
            progress_callback: 단계별 진행률을 알리기 위한 콜백 함수.

        Returns:
            Miro 보드 데이터로부터 재구성된 Board 도메인 객체.
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

        # 4. 도메인 객체로 파싱 (플랫 맵 빌드)
        update_progress("도메인 모델로 변환 중...", 0.8)
        nodes_dict = {}

        def build_domain_node(item_id: str, depth: int, parent_path: str | None = None) -> None:
            item = item_dict[item_id]
            html_content = item.get("data", {}).get("content", "")
            node_name = self._extract_text_from_html(html_content)

            current_path = f"{parent_path}/{node_name}" if parent_path else node_name
            node = Node(name=node_name, depth=depth, parent_path=parent_path, stocks=[])

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
                    local_match = re.search(r"/stock/([0-9]{6,8})", c_html)
                    if local_match:
                        ticker = local_match.group(1)
                    else:
                        # 3. Naver Finance URL 패턴에서 티커 추출
                        url_match = re.search(r"code(?:&#61;|=)([0-9]{6})", c_html)
                        if url_match:
                            ticker = url_match.group(1)

                if ticker:
                    node.stocks.append(Stock(name=c_name, ticker=ticker))
                else:
                    build_domain_node(child_id, depth + 1, current_path)

            nodes_dict[current_path] = node

        build_domain_node(root_id, 0, None)
        
        board = Board(id=board_name, name=board_name, nodes=nodes_dict)
        update_progress("로드 완료!", 1.0)
        return board

    def save(self, board: Board, progress_callback: Callable[[str, float], None] | None = None) -> None:
        """현재 Board 데이터로 대상 Miro 보드를 완전히 덮어씌웁니다.

        보드 내 기존의 모든 아이템을 완전히 삭제(초기화)한 후 새 구조로 동기화를 진행합니다.

        Args:
            board: 저장할 Board 도메인 인스턴스.
            progress_callback: 단계별 진행률 업데이트용 콜백.
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

        if not board.nodes:
            update_progress("보드가 비어 있어 초기화만 수행하고 종료합니다.", 1.0)
            return

        # 2. 레이아웃 계산 및 생성
        self.sync(board, progress_callback=progress_callback)

    def sync(self, board: Board, progress_callback: Callable[[str, float], None] | None = None) -> None:
        """변경된 노드 및 주식 정보만 Miro 마인드맵에 차분 동기화(Incremental Sync)합니다.

        새로운 가상 레이아웃을 계산한 뒤, 캐싱 맵을 통해 변경(이동, 내용 및 스타일 갱신), 생성, 삭제가
        필요한 노드를 선별하여 대량/병합 API 요청을 병렬로 수행합니다.

        Args:
            board: 동기화할 Board 데이터.
            progress_callback: 단계별 진행률 업데이트용 콜백.
        """

        def update_progress(msg, val):
            if progress_callback:
                progress_callback(msg, val)

        update_progress(f"보드 '{board.name}' ...", 0.05)
        board_id = self._get_or_create_board_id(board.name)

        # 1. 가상 레이아웃 계산
        update_progress("새로운 레이아웃 계산 중...", 0.1)
        target_layout = self._calculate_balanced_layout(board)

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
                    f'<p style="text-align: center;">'
                    f'<a href="{link_url}"><strong>{name}</strong></a>'
                    f"</p><!--ticker:{ticker}-->"
                )
            else:
                c_html = f'<p style="text-align: center;"><strong>{name}</strong></p>'

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
                if (
                    abs(m_pos.get("x", 0) - x) > 0.5
                    or abs(m_pos.get("y", 0) - y) > 0.5
                    or m_data.get("content") != c_html
                    or m_style.get("fillColor", "").lower() != fill_color.lower()
                ):
                    patch_payload = {
                        "data": {"content": c_html},
                        "position": {"x": x, "y": y},
                        "style": {"fillColor": fill_color},
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
                        "textAlignVertical": "middle",
                    },
                    "position": {"x": x, "y": y},
                    "geometry": {"width": calc_width, "height": 44},
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
                update_progress(f"아이템 동기화 중 ({i + 1}/{total_targets})...", 0.4 + (i + 1) / total_targets * 0.4)

        # 5. 삭제 (병렬 처리)
        update_progress("필요 없는 아이템 삭제 중 (병렬)...", 0.85)
        to_delete = [it["id"] for items_to_del in existing_map.values() for it in items_to_del]

        def delete_item(m_id):
            self.session.delete(f"{self.base_url}/boards/{board_id}/items/{m_id}")

        with ThreadPoolExecutor(max_workers=8) as executor:
            executor.map(delete_item, to_delete)

        update_progress("연결선(Connector) 정보 갱신 중...", 0.9)
        self._refresh_connectors(board_id, item_ids, board)
        update_progress("동기화 완료!", 1.0)

    def _get_current_connectors(self, board_id: str) -> list[dict]:
        """현재 Miro 보드 상에 맺어져 있는 모든 커넥터 정보를 쿼리하여 반환합니다.

        Args:
            board_id: Miro 보드 고유 ID.

        Returns:
            커넥터 딕셔너리 정보 목록.
        """
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
        return current_connectors

    def _determine_connector_snap(self, start_x: float, end_x: float) -> tuple[str, str]:
        """부모 요소와 자식 요소의 상대적 위치(X좌표)에 맞추어 연결선의 시작/끝 스냅(방향)을 계산합니다.

        Args:
            start_x: 시작 요소(부모)의 X좌표.
            end_x: 종료 요소(자식)의 X좌표.

        Returns:
            시작 스냅 방향('left'/'right')과 종료 스냅 방향의 튜플.
        """
        start_snap = "right" if end_x > start_x else "left"
        end_snap = "left" if end_x > start_x else "right"
        return start_snap, end_snap

    def _build_target_connectors(
        self, board: Board, item_ids: dict, conn_map: dict
    ) -> tuple[list[dict], set[tuple[str, str]]]:
        """도메인 보드 계층을 분석해 생성해야 할 대상 커넥터와 현재 유효한 커넥션 쌍 목록을 각각 집계합니다.

        Args:
            board: 대상 Board 도메인 모델.
            item_ids: 렌더링된 요소 객체 id와 Miro 아이템 정보 맵.
            conn_map: 기존 Miro 커넥션 쌍 정보를 맵핑해둔 딕셔너리.

        Returns:
            새롭게 생성해야 할 커넥터 정보 목록과 유효한 연결 쌍 세트의 튜플.
        """
        target_conn_data = []
        target_conns_set = set()

        for path, node in board.nodes.items():
            p_info = item_ids.get(id(node))
            if not p_info:
                continue
            p_id = p_info["id"]
            p_x = p_info["x"]

            # 1. 자식 노드들과의 연결 계산
            for c_path, child in board.nodes.items():
                if child.parent_path == path:
                    c_info = item_ids.get(id(child))
                    if c_info:
                        c_id = c_info["id"]
                        c_x = c_info["x"]

                        start_snap, end_snap = self._determine_connector_snap(p_x, c_x)
                        pair = (p_id, c_id)
                        target_conns_set.add(pair)

                        if pair not in conn_map:
                            target_conn_data.append(
                                {
                                    "startItem": {"id": p_id, "snapTo": start_snap},
                                    "endItem": {"id": c_id, "snapTo": end_snap},
                                    "style": {"strokeColor": "#000000", "strokeWidth": "1.5"},
                                }
                            )

            # 2. 자식 주식들과의 연결 계산
            for stock in node.stocks:
                c_info = item_ids.get(id(stock))
                if c_info:
                    c_id = c_info["id"]
                    c_x = c_info["x"]

                    start_snap, end_snap = self._determine_connector_snap(p_x, c_x)
                    pair = (p_id, c_id)
                    target_conns_set.add(pair)

                    if pair not in conn_map:
                        target_conn_data.append(
                            {
                                "startItem": {"id": p_id, "snapTo": start_snap},
                                "endItem": {"id": c_id, "snapTo": end_snap},
                                "style": {"strokeColor": "#000000", "strokeWidth": "1.5"},
                            }
                        )

        return target_conn_data, target_conns_set

    def _execute_connector_sync(self, board_id: str, create_targets: list[dict], delete_targets: list[str]) -> None:
        """병렬 스레드풀을 통해 보드 커넥터의 추가 및 삭제 동기화를 실제로 격격 기동합니다.

        Args:
            board_id: Miro 보드 ID.
            create_targets: 생성할 신규 커넥터 페이로드 목록.
            delete_targets: 삭제할 만료 커넥터 ID 목록.
        """
        def post_conn(payload):
            self.session.post(f"{self.base_url}/boards/{board_id}/connectors", json=payload)

        def delete_conn(c_id):
            self.session.delete(f"{self.base_url}/boards/{board_id}/connectors/{c_id}")

        with ThreadPoolExecutor(max_workers=8) as executor:
            executor.map(post_conn, create_targets)
            executor.map(delete_conn, delete_targets)

    def _refresh_connectors(self, board_id: str, item_ids: dict, board: Board) -> None:
        """현재 마인드맵 전체의 연결선(Connector) 상태를 갱신합니다.

        기존 연결 정보와 도메인의 연결 정보를 비교 분석하여 유효하지 않은 선은 병렬 삭제하고
        누락된 연결선만 추가 기동합니다.

        Args:
            board_id: Miro 보드 ID.
            item_ids: 렌더링된 요소 객체 id와 Miro 아이템 정보 맵.
            board: 기준 Board 도메인 모델.
        """
        current_connectors = self._get_current_connectors(board_id)

        # (startItem_id, endItem_id) -> connector_id 맵 구성
        conn_map = {}
        for c in current_connectors:
            s_id = c.get("startItem", {}).get("id")
            e_id = c.get("endItem", {}).get("id")
            if s_id and e_id:
                conn_map[(s_id, e_id)] = c["id"]

        # 목표 커넥터 및 유효 커넥션 연산
        target_conn_data, target_conns_set = self._build_target_connectors(board, item_ids, conn_map)

        # 삭제 대상 커넥션 ID 목록 계산
        to_delete_conns = [c_id for pair, c_id in conn_map.items() if pair not in target_conns_set]

        # 병렬 동기화 실행
        self._execute_connector_sync(board_id, target_conn_data, to_delete_conns)

    def _calculate_balanced_layout(self, board: Board) -> list:
        """보드 데이터를 바탕으로 루트 노드를 중심으로 좌우 대칭 균형(Balanced Tree) 레이아웃 좌표를 연산합니다.

        Args:
            board: 배치 레이아웃을 계산할 대상 Board.

        Returns:
            계산이 완료된 각 노드 요소 튜플들의 리스트. 튜플 구조는 (obj, depth, x, y, is_stock).
        """
        root_path = next((p for p, n in board.nodes.items() if n.parent_path is None), None)
        if not root_path:
            return []

        root_node = board.nodes[root_path]

        def get_leaf_count(path: str) -> int:
            node = board.nodes[path]
            children = [p for p, n in board.nodes.items() if n.parent_path == path]
            if not children and not node.stocks:
                return 1
            count = sum(get_leaf_count(c) for c in children)
            count += len(node.stocks)
            return count

        # 루트의 직계 자식 노드 경로들 + 루트의 직계 주식들
        top_children_paths = [p for p, n in board.nodes.items() if n.parent_path == root_path]
        top_children = []
        for p in top_children_paths:
            top_children.append((board.nodes[p], False, p))
        for s in root_node.stocks:
            top_children.append((s, True, s))

        def get_item_leaf_count(item_tuple) -> int:
            obj, is_stock, path_or_obj = item_tuple
            if is_stock:
                return 1
            return get_leaf_count(path_or_obj)

        top_children.sort(key=get_item_leaf_count, reverse=True)
        left_kids, right_kids = [], []
        left_leaves, right_leaves = 0, 0

        for item in top_children:
            count = get_item_leaf_count(item)
            if left_leaves <= right_leaves:
                left_kids.append(item)
                left_leaves += count
            else:
                right_kids.append(item)
                right_leaves += count

        def layout_subtree(top_items, direction_x):
            node_data_list: list[dict[str, Any]] = []
            global_y = 0

            def calculate_y(item_tuple, depth, parent_idx=-1):
                nonlocal global_y
                obj, is_stock, path_or_obj = item_tuple
                
                my_idx = len(node_data_list)
                children = []
                if not is_stock:
                    child_paths = [p for p, n in board.nodes.items() if n.parent_path == path_or_obj]
                    for c_path in child_paths:
                        children.append((board.nodes[c_path], False, c_path))
                    for s in obj.stocks:
                        children.append((s, True, s))

                node_data_list.append(
                    {"obj": obj, "depth": depth, "is_stk": is_stock, "parent_idx": parent_idx, "children": children}
                )

                if not children:
                    my_y = global_y
                    global_y += 55  # 리프 간 최소 간격
                else:
                    child_ys = []
                    for child in children:
                         cy = calculate_y(child, depth + 1, my_idx)
                         child_ys.append(cy)
                    my_y = sum(child_ys) / len(child_ys)
                    global_y += 40  # 하위 뭉치 간 간격

                node_data_list[my_idx]["y"] = my_y
                return my_y

            for item in top_items:
                calculate_y(item, 1, -1)
                global_y += 100

            if not node_data_list:
                return []

            # Y축 정렬
            min_y = min(nd["y"] for nd in node_data_list)
            max_y = max(nd["y"] for nd in node_data_list)
            center_y = (min_y + max_y) / 2
            for nd in node_data_list:
                nd["y"] -= center_y

            # X축 볼록 정렬
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

                    base_dx = 250 * direction_x
                    protrusion_dx = 0
                    if y_range > 0:
                        norm_dist = abs(cur_y - y_center) / (y_range / 2)
                        curve_weight = 200 + min(400, y_range * 0.15)
                        protrusion_dx = (1 - (norm_dist**2)) * curve_weight * direction_x

                    my_x = px + base_dx + protrusion_dx
                    nd["x"] = my_x
                    calculate_x_convex(idx, my_x)

            calculate_x_convex(-1, 0)

            return [(nd["obj"], nd["depth"], nd["x"], nd["y"], nd["is_stk"]) for nd in node_data_list]

        left_layout = layout_subtree(left_kids, -1)
        right_layout = layout_subtree(right_kids, 1)

        all_layout: list[Any] = []
        all_layout.extend(left_layout)
        all_layout.extend(right_layout)
        all_layout.append((root_node, 0, 0, 0, False))

        return all_layout
