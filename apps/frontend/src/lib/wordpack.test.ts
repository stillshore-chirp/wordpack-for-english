import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  DEFAULT_LLM_MODEL,
  DEFAULT_REASONING_EFFORT,
  SUPPORTED_LLM_MODELS,
  SUPPORTED_REASONING_EFFORTS,
  composeModelRequestFields,
  normalizeLlmModel,
  regenerateWordPackRequest,
} from './wordpack';

describe('Luna model configuration', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('keeps a single Luna model option for future-select UI compatibility', () => {
    expect(SUPPORTED_LLM_MODELS).toEqual(['gpt-5.6-luna']);
    expect(DEFAULT_LLM_MODEL).toBe('gpt-5.6-luna');
  });

  it('normalizes legacy and unknown stored selections to Luna', () => {
    expect(normalizeLlmModel('gpt-5.4-mini')).toBe('gpt-5.6-luna');
    expect(normalizeLlmModel('gpt-5.4-nano')).toBe('gpt-5.6-luna');
    expect(normalizeLlmModel('unknown')).toBe('gpt-5.6-luna');
  });

  it('uses Luna High and medium verbosity by default', () => {
    expect(DEFAULT_REASONING_EFFORT).toBe('high');
    expect(SUPPORTED_REASONING_EFFORTS).toEqual([
      'none',
      'low',
      'medium',
      'high',
      'xhigh',
      'max',
    ]);
    expect(composeModelRequestFields({})).toEqual({
      model: 'gpt-5.6-luna',
      reasoning: { effort: 'high' },
      text: { verbosity: 'medium' },
    });
  });

  it('keeps an accepted regeneration job recoverable after its polling deadline', async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.endsWith('/regenerate/async') && init?.method === 'POST') {
        return new Response(JSON.stringify({ job_id: 'job:alpha', status: 'pending' }), {
          status: 202,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.endsWith('/regenerate/jobs/job:alpha')) {
        return new Response(JSON.stringify({ job_id: 'job:alpha', status: 'running' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response(null, { status: 404 });
    });
    const notify = {
      add: vi.fn(() => 'notification:alpha'),
      update: vi.fn(),
    };

    const request = regenerateWordPackRequest({
      apiBase: '/api',
      wordPackId: 'wp:alpha',
      lemma: 'alpha',
      model: 'gpt-5.6-luna',
      settings: {
        pronunciationEnabled: true,
        regenerateScope: 'all',
        requestTimeoutMs: 60_000,
        generationRequestTimeoutMs: 100,
      },
      notify,
    });
    await vi.runAllTimersAsync();
    await request;

    expect(notify.update).toHaveBeenLastCalledWith(
      'notification:alpha',
      expect.objectContaining({
        status: 'progress',
        jobId: 'job:alpha',
        title: '【alpha】の生成中',
      }),
    );
  });
});
