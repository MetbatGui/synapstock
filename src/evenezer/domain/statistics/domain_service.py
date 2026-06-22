from evenezer.domain.models import Board, Stock
from evenezer.domain.statistics.models import NewListing


class NewListingSyncDomainService:
    """신규 상장 주식(IPO) 동기화 시 가상 보드 및 매니페스트를 갱신하는 도메인 서비스."""

    @staticmethod
    def sync_listings_to_virtual_board(
        virtual_board: Board,
        new_listings_meta: dict[str, dict],
        listings: list[NewListing],
        assigned_stocks_map: dict[str, tuple[str, list[str]]],
        now_str: str,
    ) -> tuple[Board, dict[str, dict], bool]:
        """비즈니스 규칙에 따라 가상 보드(Board) 및 매니페스트 데이터를 갱신합니다.

        Args:
            virtual_board: 가상 보드 도메인 객체.
            new_listings_meta: 매니페스트 내의 new_listings 상태 딕셔너리.
            listings: 수집된 신규 상장주 목록.
            assigned_stocks_map: 일반 보드에 기등록된 종목 맵 {ticker: (board_name, path)}.
            now_str: 현재 타임스탬프 문자열.

        Returns:
            tuple[Board, dict, bool]: 갱신된 가상 보드 객체, 갱신된 매니페스트 딕셔너리, 변경 발생 여부.
        """
        changed = False

        # 1. 가상 보드 데이터에서 2024년 미만(2020~2023) 종목 청소
        if NewListingSyncDomainService._cleanup_pre_2024_listings(virtual_board, new_listings_meta):
            changed = True

        # 2. 새로운 종목들 중 매니페스트 및 가상 보드 갱신
        for item in listings:
            if not item.ticker or item.ticker == "none":
                continue

            # 가상 보드 대기 및 매니페스트 연동은 2024년 이후(2024~2026) 종목들로만 제한
            if NewListingSyncDomainService._is_before_2024(item.listing_date):
                continue

            if NewListingSyncDomainService._sync_single_listing(
                virtual_board, new_listings_meta, item, assigned_stocks_map, now_str
            ):
                changed = True

        return virtual_board, new_listings_meta, changed

    @staticmethod
    def _cleanup_pre_2024_listings(virtual_board: Board, new_listings_meta: dict[str, dict]) -> bool:
        """가상 보드 데이터에서 2024년 미만(2020~2023) 종목을 제거합니다."""
        changed = False
        for stock in list(virtual_board.root.stocks):
            ticker = stock.ticker
            meta = new_listings_meta.get(ticker)
            if meta and meta.get("listing_date"):
                try:
                    year_val = int(meta["listing_date"][:4])
                    if year_val < 2024:
                        if virtual_board.delete_stock(ticker):
                            changed = True
                except (ValueError, TypeError):
                    pass
        return changed

    @staticmethod
    def _is_before_2024(listing_date: str | None) -> bool:
        """상장일이 2024년 이전인지 판단합니다."""
        if not listing_date:
            return False
        try:
            year_val = int(listing_date[:4])
            return year_val < 2024
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _sync_single_listing(
        virtual_board: Board,
        new_listings_meta: dict[str, dict],
        item: NewListing,
        assigned_stocks_map: dict[str, tuple[str, list[str]]],
        now_str: str,
    ) -> bool:
        """단일 신규 상장 종목에 대해 매니페스트 및 가상 보드를 동기화합니다."""
        changed = False
        ticker = item.ticker

        # 2.1. 매니페스트에 아직 등록되지 않은 경우
        if ticker not in new_listings_meta:
            res = assigned_stocks_map.get(ticker)
            if res:
                assigned_board, assigned_path = res
                new_listings_meta[ticker] = {
                    "ticker": ticker,
                    "name": item.name,
                    "listing_date": item.listing_date or "",
                    "status": "ASSIGNED",
                    "updated_at": now_str,
                    "current_board": assigned_board,
                    "current_path": assigned_path,
                }
            else:
                new_listings_meta[ticker] = {
                    "ticker": ticker,
                    "name": item.name,
                    "listing_date": item.listing_date or "",
                    "status": "PENDING",
                    "updated_at": now_str,
                    "current_board": virtual_board.id or "virtual_신규상장주",
                    "current_path": [],
                }
            changed = True
        else:
            entry = new_listings_meta[ticker]
            # 이미 등록된 항목에 listing_date가 없으면 보강
            if not entry.get("listing_date") and item.listing_date:
                entry["listing_date"] = item.listing_date
                changed = True

            # PENDING 상태인데 캐시 맵 상에서 다른 테마 보드 수록이 확인되면 ASSIGNED로 보정
            if entry.get("status") == "PENDING":
                res = assigned_stocks_map.get(ticker)
                if res:
                    assigned_board, assigned_path = res
                    entry.update(
                        {
                            "status": "ASSIGNED",
                            "current_board": assigned_board,
                            "current_path": assigned_path,
                            "updated_at": now_str,
                        }
                    )
                    changed = True

        # 2.2. 가상보드 대기 목록 제어 (PENDING 상태이고 아직 가상보드에 없는 경우 추가)
        status = new_listings_meta[ticker]["status"]
        exists_in_board = any(s.ticker == ticker for s in virtual_board.root.stocks)

        if status == "PENDING":
            if not exists_in_board:
                # 보드 애그리거트 루트의 비즈니스 메서드를 호출해 종목 추가
                # 루트 노드의 이름은 virtual_board.name과 동일함
                if virtual_board.add_stock_to_node(virtual_board.name, Stock(name=item.name, ticker=ticker)):
                    changed = True
        else:
            # PENDING이 아닌데 가상보드에 남아있다면 제거 (중복 제거 보정)
            if exists_in_board:
                if virtual_board.delete_stock(ticker):
                    changed = True

        return changed
