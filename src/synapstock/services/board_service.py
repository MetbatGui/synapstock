"""Board 서비스 레이어."""

from typing import Callable
from synapstock.domain.models import Board, Node, Stock
from synapstock.domain.ports import MindmapPort, BoardRepositoryPort, DisclosurePort, FinancialDataPort


class BoardService:
    """보드 도메인 유즈케이스를 조정하는 서비스 레이어입니다."""

    def __init__(self, repository: BoardRepositoryPort, mindmap: MindmapPort, disclosure: DisclosurePort = None, financial: FinancialDataPort = None) -> None:
        """필요한 어댑터들과 함께 BoardService를 초기화합니다.
        
        Args:
            repository: 보드 데이터 퍼시스턴스를 위한 포트.
            mindmap: 외부 마인드맵(예: Miro) 동기화를 위한 포트.
            disclosure: 선택사항으로, 종목 공시 정보 조회를 위한 포트.
            financial: 선택사항으로, 재무 데이터 조회를 위한 포트.
        """
        self._repository = repository
        self._mindmap = mindmap
        self._disclosure = disclosure
        self._financial = financial

    def get_disclosures(self, ticker: str) -> list[dict]:
        """지정된 티커에 대한 최근 공시 항목을 가져옵니다.
        
        Args:
            ticker: 종목 티커 심볼.
            
        Returns:
            list[dict]: 공시 기록 리스트. 공시 제공자가 설정되지 않은 경우 
                빈 리스트를 반환합니다.
        """
        if not self._disclosure:
            return []
        return self._disclosure.get_recent_disclosures(ticker)

    def get_financial_data(self, company_name: str) -> list[dict]:
        """지정된 기업명에 대한 분기별 재무 데이터를 가져옵니다.
        
        Args:
            company_name: 기업명.
            
        Returns:
            list[dict]: 분기별 재무 정보 리스트.
        """
        if not self._financial:
            return []
        return self._financial.get_financial_data(company_name)

    def load_board(self, name: str) -> Board:
        """로컬 저장소에서 보드를 불러옵니다.
        
        Args:
            name: 보드의 고유 식별 명칭.
            
        Returns:
            Board: 불러온 보드 객체.
        """
        return self._repository.load(name)

    def sync_with_miro(self, board: Board, progress_callback: Callable[[str, float], None] | None = None) -> None:
        """티커 정규화를 포함하여 보드 데이터를 Miro 마인드맵과 동기화합니다.
        
        Args:
            board: 동기화할 보드 인스턴스.
            progress_callback: 진행 상태 업데이트를 위한 선택적 콜백 (메시지, 진행률 0-1).
        """
        if progress_callback:
            progress_callback("보드 데이터 티커 정규화 중...", 0.0)
        
        # 모든 노드를 순회하며 티커가 없는 스톡 보정
        def normalize_node(n):
            for s in n.stocks:
                # 티커가 6자리가 아니거나 숫자가 아니면 검색 시도
                if not s.ticker or not s.ticker.isdigit() or len(s.ticker) != 6:
                    results = self.search_ticker(s.name)
                    if results:
                        # 첫 번째 검색 결과가 가장 정확할 확률이 높음
                        s.ticker = results[0]["ticker"]
                        if progress_callback:
                            progress_callback(f"티커 매칭 완료: {s.name} -> {s.ticker}", 0.0)
            for child in n.nodes:
                normalize_node(child)
        
        if board.root:
            normalize_node(board.root)
            
        self._mindmap.sync(board, progress_callback=progress_callback)

    def load(self, board_name: str, progress_callback: Callable[[str, float], None] | None = None) -> Board:
        """load_board의 별칭입니다. 이름을 통해 보드를 불러옵니다.
        
        Args:
            board_name: 보드 이름.
            progress_callback: 인터페이스 일관성을 위해 유지되며 사용되지 않습니다.
            
        Returns:
            Board: 불러온 보드.
        """
        return self._repository.load(board_name)

    def save(self, board: Board, progress_callback: Callable[[str, float], None] | None = None) -> None:
        """Board 데이터를 마인드맵에 반영(저장)합니다.
        
        Args:
            board: 저장할 Board 인스턴스.
            progress_callback: 진행 상태 업데이트를 위한 선택적 콜백.
        """
        self._mindmap.save(board, progress_callback=progress_callback)

    def list_boards(self) -> list[str]:
        """저장소에서 사용 가능한 모든 보드 이름을 나열합니다.
        
        Returns:
            list[str]: 발견된 보드 명칭 목록.
        """
        return self._repository.list_boards()

    def sync(self, board: Board, progress_callback: Callable[[str, float], None] | None = None) -> None:
        """Board의 변경사항을 마인드맵에 동기화합니다.
        
        Args:
            board: 동기화할 Board 인스턴스.
            progress_callback: 진행 상태 업데이트를 위한 선택적 콜백.
        """
        self._mindmap.sync(board, progress_callback=progress_callback)

    def search_ticker(self, query: str) -> list[dict[str, str]]:
        """네이버 모바일 검색 API를 사용하여 종목 티커를 검색합니다.
        
        Args:
            query: 검색어 (예: "삼성전자").
            
        Returns:
            list[dict[str, str]]: 'name'과 'ticker'를 포함하는 검색 결과 목록.
        """
        import requests
        url = "https://m.stock.naver.com/front-api/search/autoComplete"
        params = {
            "query": query,
            "target": "stock,index,marketindicator,coin,ipo"
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "Referer": "https://m.stock.naver.com/search"
        }
        try:
            response = requests.get(url, params=params, headers=headers, timeout=5)
            response.raise_for_status()
            data = response.json()
            # items는 result 객체 내부에 존재
            items = data.get("result", {}).get("items", [])
            results = []
            for item in items:
                # 새로운 API 필드명에 맞게 추출 (code, name)
                name = item.get("name")
                ticker = item.get("code")
                if name and ticker:
                    results.append({"name": name, "ticker": ticker})
            return results
        except Exception:
            return []

    def find_node_by_name(self, root: Node, name: str) -> Node | None:
        """보드 계층 구조 내에서 이름으로 노드를 재귀적으로 찾습니다.
        
        Args:
            root: 검색을 시작할 노드.
            name: 대상 노드 이름.
            
        Returns:
            Node: 찾은 노드 객체, 또는 찾지 못한 경우 None.
        """
        if root.name == name:
            return root
        for child in root.nodes:
            found = self.find_node_by_name(child, name)
            if found:
                return found
        return None

    def add_node(self, board_name: str, parent_name: str, new_node_name: str) -> bool:
        """지정된 부모 노드 아래에 새로운 하위 노드를 추가합니다.
        
        Args:
            board_name: 대상 보드 이름.
            parent_name: 부모 노드의 이름.
            new_node_name: 새 노드의 이름.
            
        Returns:
            bool: 성공 시 True, 부모 노드를 찾지 못한 경우 False.
        """
        board = self.load(board_name)
        parent = self.find_node_by_name(board.root, parent_name)
        if not parent:
            return False
        
        # 중복 체크
        if any(n.name == new_node_name for n in parent.nodes):
            return True
            
        parent.nodes.append(Node(name=new_node_name, depth=parent.depth + 1, nodes=[], stocks=[]))
        self._repository.save(board)
        return True

    def add_stock(self, board_name: str, parent_name: str, stock_name: str, ticker: str) -> bool:
        """지정된 부모 노드 아래에 새로운 종목 항목을 추가합니다.
        
        Args:
            board_name: 대상 보드 이름.
            parent_name: 부모 노드의 이름.
            stock_name: 종목명.
            ticker: 6자리 종목 티커 코드.
            
        Returns:
            bool: 성공 시 True, 부모 노드를 찾지 못한 경우 False.
        """
        board = self.load(board_name)
        parent = self.find_node_by_name(board.root, parent_name)
        if not parent:
            return False
            
        # 중복 체크
        if any(s.ticker == ticker for s in parent.stocks):
            return True
            
        parent.stocks.append(Stock(name=stock_name, ticker=ticker))
        self._repository.save(board)
        return True

    def delete_node(self, board_name: str, node_name: str) -> bool:
        """노드를 삭제하고 그 자식들을 부모 노드에 재연결합니다.
        
        Args:
            board_name: 대상 보드 이름.
            node_name: 삭제할 노드의 이름.
            
        Returns:
            bool: 성공 시 True, 루트 노드이거나 노드를 찾지 못한 경우 False.
        """
        board = self.load(board_name)
        if board.root.name == node_name:
            return False # 루트 노드는 삭제 불가
            
        # 부모 찾기 및 삭제 대상 찾기
        def find_and_delete(parent, target_name):
            for i, child in enumerate(parent.nodes):
                if child.name == target_name:
                    # 하위 요소 흡수
                    parent.nodes.extend(child.nodes)
                    parent.stocks.extend(child.stocks)
                    # 자신 삭제
                    parent.nodes.pop(i)
                    return True
                if find_and_delete(child, target_name):
                    return True
            return False
            
        success = find_and_delete(board.root, node_name)
        if success:
            self._repository.save(board)
        return success

    def delete_stock(self, board_name: str, ticker: str) -> bool:
        """보드에서 특정 티커를 가진 종목을 삭제합니다.
        
        Args:
            board_name: 대상 보드 이름.
            ticker: 삭제할 종목의 티커 코드.
            
        Returns:
            bool: 성공적으로 삭제된 경우 True.
        """
        board = self.load(board_name)
        
        def find_and_remove(node):
            orig_len = len(node.stocks)
            node.stocks = [s for s in node.stocks if s.ticker != ticker]
            if len(node.stocks) < orig_len:
                return True
            
            for child in node.nodes:
                if find_and_remove(child):
                    return True
            return False
            
        success = find_and_remove(board.root)
        if success:
            self._repository.save(board)
        return success

    def add_stock_report(self, board_name: str, ticker: str, file_content: bytes, filename: str) -> bool:
        """종목에 PDF 리포트를 추가하고 파일을 저장합니다.
        
        Args:
            board_name: 대상 보드 이름.
            ticker: 종목 티커 심볼.
            file_content: 파일 바이너리 내용.
            filename: 저장할 파일명 (PDF 검증은 외부에서 수행).
            
        Returns:
            bool: 성공적으로 추가된 경우 True.
        """
        from pathlib import Path
        
        # 1. 파일 저장 경로 설정 및 디렉토리 생성
        pdf_dir = Path("data/pdf")
        pdf_dir.mkdir(parents=True, exist_ok=True)
        target_path = pdf_dir / filename
        
        # 2. 파일 저장
        with open(target_path, "wb") as f:
            f.write(file_content)
            
        # 3. 보드 데이터 업데이트
        board = self.load(board_name)
        # 웹 환경에서의 접근을 위해 'data/'를 포함한 상대 경로 저장
        report_path = f"data/pdf/{filename}"
        
        def find_and_add_report(node):
            for s in node.stocks:
                if s.ticker == ticker:
                    if report_path not in s.reports:
                        s.reports.append(report_path)
                    return True
            for child in node.nodes:
                if find_and_add_report(child):
                    return True
            return False
            
        success = find_and_add_report(board.root)
        if success:
            self._repository.save(board)
        return success

    def remove_stock_report(self, board_name: str, ticker: str, report_path: str) -> bool:
        """종목에서 리포트 링크를 제거합니다.
        
        Args:
            board_name: 대상 보드 이름.
            ticker: 종목 티커 심볼.
            report_path: 제거할 리포트의 상대 경로.
            
        Returns:
            bool: 성공적으로 제거된 경우 True.
        """
        board = self.load(board_name)
        
        def find_and_remove_report(node):
            for s in node.stocks:
                if s.ticker == ticker:
                    if report_path in s.reports:
                        s.reports.remove(report_path)
                        return True
                    return False
            for child in node.nodes:
                if find_and_remove_report(child):
                    return True
            return False
            
        success = find_and_remove_report(board.root)
        if success:
            self._repository.save(board)
        return success

    def add_stock_news(self, board_name: str, ticker: str, title: str, date: str, url: str) -> bool:
        """종목에 뉴스 링크를 추가합니다.
        
        Args:
            board_name: 대상 보드 이름.
            ticker: 종목 티커 심볼.
            title: 뉴스 제목.
            date: 뉴스 발행일.
            url: 뉴스 원본 링크.
            
        Returns:
            bool: 성공적으로 추가된 경우 True.
        """
        board = self.load(board_name)
        news_entry = {"title": title, "date": date, "url": url}
        
        def find_and_add_news(node):
            for s in node.stocks:
                if s.ticker == ticker:
                    if not any(n["url"] == url for n in s.news):
                        s.news.append(news_entry)
                    return True
            for child in node.nodes:
                if find_and_add_news(child):
                    return True
            return False
            
        success = find_and_add_news(board.root)
        if success:
            self._repository.save(board)
        return success

    def remove_stock_news(self, board_name: str, ticker: str, url: str) -> bool:
        """종목에서 특정 뉴스 링크를 제거합니다.
        
        Args:
            board_name: 대상 보드 이름.
            ticker: 종목 티커 심볼.
            url: 제거할 뉴스의 링크 (ID 역할).
            
        Returns:
            bool: 성공적으로 제거된 경우 True.
        """
        board = self.load(board_name)
        
        def find_and_remove_news(node):
            for s in node.stocks:
                if s.ticker == ticker:
                    new_news = [n for n in s.news if n["url"] != url]
                    if len(new_news) < len(s.news):
                        s.news = new_news
                        return True
                    return False
            for child in node.nodes:
                if find_and_remove_news(child):
                    return True
            return False
            
        success = find_and_remove_news(board.root)
        if success:
            self._repository.save(board)
        return success

