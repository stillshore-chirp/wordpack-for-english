import { describe, expect, it, vi } from 'vitest';
import { ApiError } from './ApiError';
import { submitIdempotentJob } from './submitIdempotentJob';

describe('submitIdempotentJob', () => {
  it('通信結果不明時だけ同じ送信処理を1回再実行する', async () => {
    const submit = vi.fn()
      .mockRejectedValueOnce(new ApiError('Network error', 0))
      .mockResolvedValueOnce({ job_id: 'job:stable' });

    await expect(submitIdempotentJob(submit)).resolves.toEqual({
      job_id: 'job:stable',
    });
    expect(submit).toHaveBeenCalledTimes(2);
  });

  it('確定HTTP失敗は再実行しない', async () => {
    const error = new ApiError('validation failed', 422);
    const submit = vi.fn().mockRejectedValue(error);

    await expect(submitIdempotentJob(submit)).rejects.toBe(error);
    expect(submit).toHaveBeenCalledTimes(1);
  });

  it('再送も通信結果不明なら候補IDでの再照合用に失敗を返す', async () => {
    const error = new ApiError('Network error', 0);
    const submit = vi.fn().mockRejectedValue(error);

    await expect(submitIdempotentJob(submit)).rejects.toBe(error);
    expect(submit).toHaveBeenCalledTimes(2);
  });
});
