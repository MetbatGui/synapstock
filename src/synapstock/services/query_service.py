"""보드 및 종목 정보 조회 서비스를 담당하는 유즈케이스 레이어."""

from typing import List, Dict, Optional
from synapstock.domain.models import Board, Node
from synapstock.domain.ports import BoardRepositoryPort, TickerSearchPort, DisclosurePort, FinancialDataPort

class BoardQueryService:
    """보드와 관련된 모든 '조회(Read)' 작업을 수행하는 서비스 클래스입니다. (CQRS - Query)"""

    def __init__(
        self,
        repository: BoardRepositoryPort,
        ticker_search: TickerSearchPort,
        disclosure: Optional[DisclosurePort] = None,
        financial: Optional[FinancialDataPort] = None
    ) -> None:
        """필요한 조회용 어댑터로 서비스를 초기화합니다."""
        self._repository = repository
        self._ticker_search = ticker_search
        self._disclosure = disclosure
        self._financial = financial

    def list_boards(self) -> List[str]:
        """저장소의 모든 보드 이름을 나열합니다."""
        return self._repository.list_boards()

    def load_board(self, name: str) -> Board:
        """이름으로 특정 보드 데이터를 로드합니다."""
        return self._repository.load(name)

    def get_boards_info(self) -> List[Dict]:
        """모든 보드의 ID와 실제 이름을 조회합니다."""
        boards = self.list_boards()
        result = []
        for b in boards:
            try:
                board = self.load_board(b)
                result.append({"id": b, "name": board.name})
            except Exception:
                # 보드 로드 실패 시 파일명에서 힌트를 추출하여 폴백
                result.append({"id": b, "name": b.replace("theme_", "")})
        return result

    def search_ticker(self, query: str) -> List[Dict[str, str]]:
        """종목 명칭으로 티커를 검색합니다."""
        return self._ticker_search.search(query)

    def get_disclosures(self, ticker: str) -> List[Dict]:
        """특정 종목의 최근 공시 정보를 조회합니다."""
        if not self._disclosure:
            return []
        return self._disclosure.get_recent_disclosures(ticker)

    def get_financial_data(self, company_name: str) -> List[Dict]:
        """특정 기업의 재무 데이터를 조회합니다."""
        if not self._financial:
            return []
        return self._financial.get_financial_data(company_name)

    def find_node_by_name(self, root: Node, name: str) -> Optional[Node]:
        """노드 트리 내에서 특정 이름의 노드를 검색합니다."""
        return root.find_node(name)
