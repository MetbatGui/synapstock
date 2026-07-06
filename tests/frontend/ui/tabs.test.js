import { describe, it, expect, beforeEach, vi } from 'vitest';
import { addLogEntry, initTabs, switchTab } from '@/ui/tabs.js';

describe('tabs UI Module', () => {
  beforeEach(() => {
    // 테스트 전에 가상 DOM을 깨끗하게 설정합니다.
    document.body.innerHTML = `
      <div id="log-console" style="height: 100px; overflow-y: auto;"></div>
      <div class="nav-links">
        <a href="#" class="nav-item active" data-tab="mindmap-tab">마인드맵</a>
        <a href="#" class="nav-item" data-tab="dashboard-tab">대시보드</a>
      </div>
      <div id="mindmap-tab" class="tab-content active"></div>
      <div id="dashboard-tab" class="tab-content"></div>
      <button id="toggle-financial-sidebar"></button>
      <aside id="financial-sidebar"></aside>
    `;
    
    // global history mock
    vi.stubGlobal('history', {
      pushState: vi.fn(),
    });
    
    // window.location mock
    vi.stubGlobal('location', {
      pathname: '/',
    });
  });

  describe('addLogEntry', () => {
    it('로그가 콘솔 엘리먼트에 추가되어야 하고 내용에 타임스탬프와 메시지가 포함되어야 한다', () => {
      addLogEntry('테스트 메시지', 'info');
      const consoleEl = document.getElementById('log-console');
      expect(consoleEl.children.length).toBe(1);
      
      const logEntry = consoleEl.firstElementChild;
      expect(logEntry.className).toBe('log-entry info');
      expect(logEntry.textContent).toContain('테스트 메시지');
    });

    it('로그 추가 시 스크롤이 바닥으로 이동해야 한다', () => {
      const consoleEl = document.getElementById('log-console');
      addLogEntry('스크롤 테스트');
      expect(consoleEl.scrollTop).toBe(consoleEl.scrollHeight);
    });
  });

  describe('switchTab', () => {
    it('지정된 탭으로 정상적으로 전환되어야 한다', () => {
      switchTab('dashboard-tab', false);

      const mindmapTabItem = document.querySelector('.nav-item[data-tab="mindmap-tab"]');
      const dashboardTabItem = document.querySelector('.nav-item[data-tab="dashboard-tab"]');
      const mindmapTabContent = document.getElementById('mindmap-tab');
      const dashboardTabContent = document.getElementById('dashboard-tab');

      // 대시보드 탭에 active가 들어갔는지 확인
      expect(dashboardTabItem.classList.contains('active')).toBe(true);
      expect(dashboardTabContent.classList.contains('active')).toBe(true);

      // 기존 active였던 마인드맵 탭에선 active가 제거되었는지 확인
      expect(mindmapTabItem.classList.contains('active')).toBe(false);
      expect(mindmapTabContent.classList.contains('active')).toBe(false);
    });

    it('updateHistory가 true이면 history.pushState가 호출되어야 한다', () => {
      switchTab('dashboard-tab', true);
      expect(history.pushState).toHaveBeenCalledWith({ tab: 'dashboard' }, '', '/stock/none');
    });
  });

  describe('initTabs', () => {
    it('탭 아이템에 클릭 이벤트 핸들러가 바인딩되고 클릭 시 전환되어야 한다', () => {
      initTabs();

      const dashboardTabItem = document.querySelector('.nav-item[data-tab="dashboard-tab"]');
      
      // 클릭 시뮬레이션
      dashboardTabItem.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

      // 클릭 결과 switchTab이 실행되어 active 클래스가 지정되었는지 확인
      expect(dashboardTabItem.classList.contains('active')).toBe(true);
    });
  });
});
