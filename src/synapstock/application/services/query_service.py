"""보드 및 종목 정보 조회 서비스를 담당하는 유즈케이스 레이어."""


from typing import cast

from synapstock.domain.models import Board, Node, Stock
from synapstock.domain.ports import (
    BoardRepositoryPort,
    DisclosurePort,
    FinancialDataPort,
    TickerSearchPort,
)


class BoardQueryService:
    """보드와 관련된 모든 '조회(Read)' 작업을 수행하는 서비스 클래스입니다. (CQRS - Query)"""

    def __init__(
        self,
        repository: BoardRepositoryPort,
        ticker_search: TickerSearchPort,
        disclosure: DisclosurePort | None = None,
        financial: FinancialDataPort | None = None
    ) -> None:
        """필요한 조회용 어댑터로 서비스를 초기화합니다."""
        self._repository = repository
        self._ticker_search = ticker_search
        self._disclosure = disclosure
        self._financial = financial

    def list_boards(self) -> list[str]:
        """저장소의 모든 보드 이름을 나열합니다."""
        return cast(list[str], self._repository.list_boards())

    def load_board(self, name: str) -> Board:
        """이름으로 특정 보드 데이터를 로드합니다."""
        return cast(Board, self._repository.load(name))

    def get_boards_info(self) -> list[dict]:
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

    def search_ticker(self, query: str) -> list[dict[str, str]]:
        """종목 명칭으로 티커를 검색합니다."""
        return cast(list[dict[str, str]], self._ticker_search.search(query))

    def get_disclosures(self, ticker: str) -> list[dict]:
        """특정 종목의 최근 공시 정보를 조회합니다."""
        if not self._disclosure:
            return []
        return cast(list[dict], self._disclosure.get_recent_disclosures(ticker))

    def get_financial_data(self, company_name: str) -> list[dict]:
        """특정 기업의 재무 데이터를 조회합니다."""
        if not self._financial:
            return []
        return cast(list[dict], self._financial.get_financial_data(company_name))

    def find_node_by_name(self, root: Node, name: str) -> Node | None:
        """노드 트리 내에서 특정 이름의 노드를 검색합니다."""
        return root.find_node(name)

    def get_stock_by_ticker(self, ticker: str) -> tuple[Stock, str] | None:
        """모든 보드를 순회하여 일치하는 티커의 종목 정보를 찾습니다."""
        boards = self.list_boards()
        for b_name in boards:
            board = self.load_board(b_name)

            def find_recursive(node: Node) -> Stock | None:
                for s in node.stocks:
                    if s.ticker == ticker:
                        return s
                for n in node.nodes:
                    res = find_recursive(n)
                    if res:
                        return res
                return None

            stock = find_recursive(board.root)
            if stock:
                return stock, b_name
        return None

    def get_all_stocks_flat(self) -> list[dict]:
        """모든 보드의 모든 종목 정보를 평탄화된 리스트로 반환합니다."""
        boards = self.list_boards()
        all_stocks = []
        for b_name in boards:
            board = self.load_board(b_name)

            def flatten_recursive(node: Node, current_path: list[str]):
                stocks = []
                for s in node.stocks:
                    stocks.append({
                        "ticker": s.ticker,
                        "name": s.name,
                        "aliases": s.aliases,
                        "board": b_name,
                        "board_name": board.name,
                        "path": current_path
                    })
                for n in node.nodes:
                    stocks.extend(flatten_recursive(n, current_path + [n.name]))
                return stocks

            all_stocks.extend(flatten_recursive(board.root, []))
        return all_stocks

    def find_stocks_by_name(self, query: str) -> list[dict]:
        """모든 보드에서 종목명에 query가 포함된 종목들을 검색합니다 (텔레그램용)."""
        boards = self.list_boards()
        results = []
        for b_name in boards:
            board = self.load_board(b_name)

            def search_recursive(node: Node, current_path: list[str]):
                for s in node.stocks:
                    if query in s.name or any(query in alias for alias in s.aliases):
                        results.append({
                            "board": b_name,
                            "board_name": board.name,
                            "name": s.name,
                            "ticker": s.ticker,
                            "path": f"[{board.name}] " + " > ".join(current_path + [s.name])
                        })
                for n in node.nodes:
                    search_recursive(n, current_path + [n.name])

            search_recursive(board.root, [board.root.name])
        return results
