import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiFetch } from '@/services/api.js';

describe('apiFetch', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('요청이 성공하면 JSON 데이터를 반환해야 한다', async () => {
    const mockData = { result: 'success' };
    const mockResponse = {
      ok: true,
      json: async () => mockData,
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockResponse));

    const result = await apiFetch('/api/test');
    expect(fetch).toHaveBeenCalledWith('/api/test', {});
    expect(result).toEqual(mockData);
  });

  it('요청이 실패하면 HTTP 에러 메시지와 함께 예외를 던져야 한다', async () => {
    const mockErrorBody = { message: '잘못된 요청입니다.' };
    const mockResponse = {
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      json: async () => mockErrorBody,
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockResponse));

    await expect(apiFetch('/api/test-fail')).rejects.toThrow('잘못된 요청입니다.');
  });

  it('요청 실패 시 에러 바디에 message가 없으나 statusText가 있는 경우 statusText를 에러 메시지로 던져야 한다', async () => {
    const mockResponse = {
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      json: async () => { throw new Error('JSON Parsing Failed'); },
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockResponse));

    await expect(apiFetch('/api/test-fail-status-text')).rejects.toThrow('Internal Server Error');
  });

  it('요청 실패 시 message와 statusText가 모두 없는 경우 HTTP 코드를 에러 메시지로 던져야 한다', async () => {
    const mockResponse = {
      ok: false,
      status: 500,
      statusText: '',
      json: async () => { throw new Error('JSON Parsing Failed'); },
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockResponse));

    await expect(apiFetch('/api/test-fail-fallback')).rejects.toThrow('HTTP 500');
  });
});
