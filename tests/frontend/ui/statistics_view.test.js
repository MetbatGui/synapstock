import { describe, it, expect, beforeEach, vi } from 'vitest';
import { statisticsView } from '@/ui/statistics/statistics_view.js';
import { statisticsService } from '@/services/statistics_service.js';

// statistics_service 모듈 모킹
vi.mock('@/services/statistics_service.js', () => {
  return {
    statisticsService: {
      getAvailableDates: vi.fn(),
      getDailySummary: vi.fn(),
      syncStatistics: vi.fn(),
    }
  };
});

describe('statisticsView UI Module', () => {
  let container;

  const mockDates = ['2026-07-06', '2026-07-05'];
  const mockSummaryData = {
    KOSPI: {
      FOREIGN: {
        items: [
          { rank: 1, name: '삼성전자', ticker: '005930', amount: 50000, consecutive_days: 5, high_price_type: '역·신', rank_change: 2, is_new: false },
          { rank: 2, name: 'SK하이닉스', ticker: '000660', amount: 30000, consecutive_days: 2, high_price_type: null, rank_change: -1, is_new: false }
        ]
      },
      INSTITUTION: {
        items: [
          { rank: 1, name: '삼성전자', ticker: '005930', amount: 20000, consecutive_days: 1, high_price_type: null, rank_change: 0, is_new: true }
        ]
      }
    },
    KOSDAQ: {
      FOREIGN: {
        items: []
      },
      INSTITUTION: {
        items: []
      }
    }
  };

  beforeEach(() => {
    vi.restoreAllMocks();

    // 가상 DOM 컨테이너 준비
    container = document.createElement('div');
    container.id = 'statistics-container';
    document.body.appendChild(container);

    // 글로벌 객체 모킹
    vi.stubGlobal('location', {
      href: '',
    });
    vi.stubGlobal('alert', vi.fn());

    // API 모킹 기본 반환값 설정
    statisticsService.getAvailableDates.mockResolvedValue(mockDates);
    statisticsService.getDailySummary.mockResolvedValue(mockSummaryData);
  });

  afterEach(() => {
    document.body.removeChild(container);
  });

  describe('init 및 기본 레이아웃 렌더링', () => {
    it('초기화 시 레이아웃 HTML이 렌더링되고 데이터 조회가 유발되어야 한다', async () => {
      await statisticsView.init(container);

      // 레이아웃 검증
      expect(container.querySelector('.stats-container')).not.toBeNull();
      expect(container.querySelector('#stats-date')).not.toBeNull();
      expect(container.querySelector('#stats-refresh')).not.toBeNull();

      // 초기 데이터 로드 API 호출 검증
      expect(statisticsService.getAvailableDates).toHaveBeenCalled();
      expect(statisticsService.getDailySummary).toHaveBeenCalledWith('2026-07-06');
    });
  });

  describe('날짜 목록 제어 (updateDateList)', () => {
    it('가용 날짜 목록이 select 박스의 option 엘리먼트로 주입되어야 한다', async () => {
      statisticsView.container = container;
      statisticsView.renderLayout();

      await statisticsView.updateDateList();

      const select = container.querySelector('#stats-date');
      expect(select.children.length).toBe(2);
      expect(select.children[0].value).toBe('2026-07-06');
      expect(select.children[1].value).toBe('2026-07-05');
    });
  });

  describe('수급 데이터 로드 및 렌더링 (loadData & renderSummaryGrid)', () => {
    it('가용 날짜가 없는 경우 빈 데이터 레이아웃이 렌더링되어야 한다', async () => {
      statisticsService.getAvailableDates.mockResolvedValue([]);
      statisticsView.container = container;
      
      await statisticsView.init(container);

      const tableContainer = container.querySelector('#stats-table-container');
      expect(tableContainer.textContent).toContain('가용한 수급 데이터가 없습니다.');
    });

    it('수급 데이터를 기반으로 요약 그리드 테이블이 알맞은 클래스 및 배지와 함께 렌더링되어야 한다', async () => {
      await statisticsView.init(container);

      const tableContainer = container.querySelector('#stats-table-container');
      expect(tableContainer.querySelector('.stats-markets-grid')).not.toBeNull();

      // 삼성전자 (KOSPI 외인 1위) 검증
      const samsungRow = tableContainer.querySelector('.stock-link[data-name="삼성전자"]').closest('tr');
      expect(samsungRow).not.toBeNull();
      expect(samsungRow.querySelector('.col-rank').textContent).toBe('1');
      expect(samsungRow.querySelector('.col-amount').textContent).toBe('50,000');
      
      // 연속일수 배지 핫 검증 (consecutive_days: 5 -> badge-consecutive-hot)
      const consecutiveBadge = samsungRow.querySelector('.badge-consecutive-hot');
      expect(consecutiveBadge).not.toBeNull();
      expect(consecutiveBadge.textContent).toContain('🔥 5');

      // 쌍끌이 배지 검증 (삼성전자는 외인/기관 랭킹에 모두 있으므로 '쌍' 배지 추가)
      const doubleBadge = samsungRow.querySelector('.badge-double');
      expect(doubleBadge).not.toBeNull();
      expect(doubleBadge.textContent).toBe('쌍');

      // 신고가 배지 hp-red 검증 (high_price_type: '역·신')
      const hpBadge = samsungRow.querySelector('.badge-highprice.hp-red');
      expect(hpBadge).not.toBeNull();
      expect(hpBadge.textContent).toBe('역·신');

      // SK하이닉스 (KOSPI 외인 2위) 검증
      const hynixRow = tableContainer.querySelector('.stock-link[data-name="SK하이닉스"]').closest('tr');
      expect(hynixRow).not.toBeNull();
      expect(hynixRow.querySelector('.col-rank').textContent).toBe('2');
      expect(hynixRow.querySelector('.col-amount').textContent).toBe('30,000');
      
      // 일반 연속일수 배지 검증 (consecutive_days: 2 -> badge-consecutive)
      const hynixConsecutive = hynixRow.querySelector('.badge-consecutive');
      expect(hynixConsecutive.classList.contains('badge-consecutive-hot')).toBe(false);
      expect(hynixConsecutive.textContent).toContain('🔥 2');
    });
  });

  describe('이벤트 및 화면 이동 인터랙션 (bindEventsAfterRender)', () => {
    it('티커가 이미 포함된 종목 링크를 클릭하면 즉시 주식 대시보드로 이동해야 한다', async () => {
      await statisticsView.init(container);

      const hynixLink = container.querySelector('.stock-link[data-name="SK하이닉스"]');
      hynixLink.click();

      expect(window.location.href).toBe('/stock/000660');
    });

    it('티커가 없는 종목 링크를 클릭하면 API 검색을 통해 티커를 획득 후 이동해야 한다', async () => {
      // 삼성전자에서 티커를 삭제한 mock 데이터 주입
      const modifiedSummary = JSON.parse(JSON.stringify(mockSummaryData));
      modifiedSummary.KOSPI.FOREIGN.items[0].ticker = '';
      statisticsService.getDailySummary.mockResolvedValue(modifiedSummary);

      // 검색 API 모킹
      const mockSearchResponse = {
        ok: true,
        json: async () => [{ name: '삼성전자', ticker: '005930' }]
      };
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockSearchResponse));

      await statisticsView.init(container);

      const samsungLink = container.querySelector('.stock-link[data-name="삼성전자"]');
      samsungLink.click();

      expect(fetch).toHaveBeenCalledWith('/api/stock/search?q=%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90');
      
      // 비동기 fetch 완료 및 location.href 업데이트 대기
      await vi.waitFor(() => {
        expect(window.location.href).toBe('/stock/005930');
      });
    });
  });

  describe('데이터 동기화 (handleSync)', () => {
    it('동기화 버튼을 클릭하면 sync API를 실행하고 스피너 클래스가 추가되어야 한다', async () => {
      statisticsService.syncStatistics.mockResolvedValue({ status: 'success' });
      await statisticsView.init(container);

      const refreshBtn = container.querySelector('#stats-refresh');
      const icon = refreshBtn.querySelector('i');

      const syncPromise = statisticsView.handleSync();

      // 동기화 중 상태 검증
      expect(refreshBtn.disabled).toBe(true);
      expect(icon.classList.contains('fa-spin')).toBe(true);

      await syncPromise;

      // 동기화 완료 후 상태 검증
      expect(refreshBtn.disabled).toBe(false);
      expect(icon.classList.contains('fa-spin')).toBe(false);
      expect(statisticsService.syncStatistics).toHaveBeenCalled();
    });
  });
});
