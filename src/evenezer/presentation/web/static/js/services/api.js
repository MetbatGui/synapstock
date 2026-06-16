/**
 * @fileoverview 공통 HTTP fetch 래퍼 및 에러 처리 유틸리티.
 * @module services/api
 */

/**
 * 공통 API fetch 래퍼.
 *
 * HTTP 응답이 실패(ok가 false)인 경우 서버 응답 메시지를 포함한 에러를 throw합니다.
 *
 * @param {string} url - 요청할 URL.
 * @param {RequestInit=} options - `fetch()` 에 전달할 옵션 객체. 기본값은 빈 객체.
 * @returns {Promise<*>} 파싱된 JSON 응답 본문.
 * @throws {Error} HTTP 오류 또는 네트워크 오류 발생 시.
 *
 * @example
 * const data = await apiFetch('/api/boards');
 */
export async function apiFetch(url, options = {}) {
    const response = await fetch(url, options);
    if (!response.ok) {
        const body = await response.json().catch(() => ({ message: response.statusText }));
        throw new Error(body.message || `HTTP ${response.status}`);
    }
    return response.json();
}
