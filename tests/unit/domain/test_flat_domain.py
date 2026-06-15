"""플랫 도메인 모델(Board, Node, Stock) 단위 테스트."""

import pytest
from pydantic import ValidationError

from synapstock.domain.models import Board, Node, Stock


class TestFlatNode:
    """플랫 구조로 변경된 Node 모델 단위 테스트."""

    def test_create_node(self):
        """Node 생성 시 parent_path 및 기본 필드들이 유효해야 한다."""
        node = Node(name="반도체", depth=1, parent_path="Theme_IT")
        assert node.name == "반도체"
        assert node.depth == 1
        assert node.parent_path == "Theme_IT"
        assert node.stocks == []

    def test_node_with_stocks(self):
        """Node에 종목을 추가할 수 있어야 한다."""
        node = Node(name="소재", depth=2, parent_path="Theme_IT/반도체")
        stock = Stock(name="동진쎄미켐", ticker="005290")
        node.stocks.append(stock)
        assert len(node.stocks) == 1
        assert node.stocks[0].name == "동진쎄미켐"


class TestFlatBoard:
    """플랫 맵 구조(dict[path, Node])를 지닌 Board 모델 단위 테스트."""

    def test_create_board_auto_root(self):
        """Board 생성 시 루트 노드가 nodes 딕셔너리에 자동으로 키 경로로 등록되어야 한다."""
        # Board 생성 시 root가 없으면 Board name과 동일한 루트 노드가 nodes에 자동 적재
        board = Board(name="Theme_바이오")
        assert "Theme_바이오" in board.nodes
        root_node = board.nodes["Theme_바이오"]
        assert root_node.name == "Theme_바이오"
        assert root_node.depth == 0
        assert root_node.parent_path is None

    def test_add_node(self):
        """특정 부모 노드 경로 아래에 자식 노드가 추가되어야 한다."""
        board = Board(name="Theme_바이오")
        # parent: "Theme_바이오", new_node_name: "백신"
        success = board.add_node("Theme_바이오", "백신")
        assert success is True
        
        target_path = "Theme_바이오/백신"
        assert target_path in board.nodes
        child_node = board.nodes[target_path]
        assert child_node.name == "백신"
        assert child_node.depth == 1
        assert child_node.parent_path == "Theme_바이오"

    def test_add_node_parent_not_found(self):
        """부모 노드가 존재하지 않으면 노드 추가가 실패해야 한다."""
        board = Board(name="Theme_바이오")
        success = board.add_node("Theme_바이오/존재하지않음", "백신")
        assert success is False

    def test_add_stock_to_node(self):
        """특정 노드 경로 하위에 종목이 추가되어야 한다."""
        board = Board(name="Theme_바이오")
        board.add_node("Theme_바이오", "시밀러")
        
        stock = Stock(name="셀트리온", ticker="068270")
        success = board.add_stock_to_node("Theme_바이오/시밀러", stock)
        
        assert success is True
        node = board.nodes["Theme_바이오/시밀러"]
        assert len(node.stocks) == 1
        assert node.stocks[0].ticker == "068270"

    def test_find_node(self):
        """보드 내에서 절대 경로로 노드를 검색한다."""
        board = Board(name="Theme_바이오")
        board.add_node("Theme_바이오", "치료제")
        
        node = board.find_node("Theme_바이오/치료제")
        assert node is not None
        assert node.name == "치료제"

        # 없는 노드 검색
        assert board.find_node("Theme_바이오/없는노드") is None

    def test_find_stock(self):
        """보드 내에서 티커로 종목을 검색한다."""
        board = Board(name="Theme_바이오")
        board.add_node("Theme_바이오", "치료제")
        board.add_stock_to_node("Theme_바이오/치료제", Stock(name="유한양행", ticker="000100"))
        
        stock = board.find_stock("000100")
        assert stock is not None
        assert stock.name == "유한양행"

        # 없는 종목 검색
        assert board.find_stock("999999") is None

    def test_delete_stock(self):
        """보드 내에서 특정 종목을 찾아 삭제한다."""
        board = Board(name="Theme_바이오")
        board.add_node("Theme_바이오", "백신")
        board.add_stock_to_node("Theme_바이오/백신", Stock(name="SK바이오사이언스", ticker="302440"))
        
        # 삭제 전 존재 확인
        assert board.find_stock("302440") is not None
        
        # 삭제 집행
        success = board.delete_stock("302440")
        assert success is True
        
        # 삭제 후 확인
        assert board.find_stock("302440") is None
        assert len(board.nodes["Theme_바이오/백신"].stocks) == 0

    def test_delete_node_and_absorb_children(self):
        """노드 삭제 시, 하위 자식 노드와 종목들이 부모 노드로 갱신되며 안전하게 흡수되어야 한다."""
        board = Board(name="Theme_신재생")
        # 구조 구축: Theme_신재생 -> 태양광 -> 폴리실리콘 (종목: OCI)
        board.add_node("Theme_신재생", "태양광")
        board.add_node("Theme_신재생/태양광", "폴리실리콘")
        board.add_stock_to_node("Theme_신재생/태양광/폴리실리콘", Stock(name="OCI홀딩스", ticker="010060"))
        board.add_stock_to_node("Theme_신재생/태양광", Stock(name="한화솔루션", ticker="009830"))

        # "태양광" 노드를 삭제하고 "폴리실리콘" 노드와 종목들을 부모인 "Theme_신재생"으로 흡수
        # 삭제 대상 경로: "Theme_신재생/태양광"
        success = board.delete_node("Theme_신재생/태양광")
        assert success is True

        # "Theme_신재생/태양광" 노드는 제거되어야 함
        assert "Theme_신재생/태양광" not in board.nodes
        
        # 1. 태양광 노드 하위의 주식(한화솔루션)은 부모인 "Theme_신재생"으로 이동
        root_node = board.nodes["Theme_신재생"]
        assert any(s.ticker == "009830" for s in root_node.stocks) # 한화솔루션

        # 2. 하위 노드였던 폴리실리콘의 경로가 "Theme_신재생/폴리실리콘"으로 이동 및 depth 갱신
        target_path = "Theme_신재생/폴리실리콘"
        assert target_path in board.nodes
        child_node = board.nodes[target_path]
        assert child_node.depth == 1
        assert child_node.parent_path == "Theme_신재생"

        # 3. 폴리실리콘 노드 하위의 종목(OCI홀딩스)이 여전히 잘 있는지 확인
        assert any(s.ticker == "010060" for s in child_node.stocks)

    def test_report_management(self):
        """보드 내부 종목에 리포트를 추가하고 삭제할 수 있어야 한다."""
        board = Board(name="Theme_반도체")
        board.add_node("Theme_반도체", "디바이스")
        board.add_stock_to_node("Theme_반도체/디바이스", Stock(name="리노공업", ticker="058470"))
        
        report_path = "data/pdf/leeno_q1.pdf"
        
        # Add report
        success = board.add_report_to_stock("058470", report_path)
        assert success is True
        stock = board.find_stock("058470")
        assert report_path in stock.reports

        # Remove report
        success = board.remove_report_from_stock("058470", report_path)
        assert success is True
        assert report_path not in stock.reports
