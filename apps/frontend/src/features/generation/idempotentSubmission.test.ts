import { afterEach, describe, expect, it, vi } from 'vitest';
import { createWordPackGenerationJob } from '../wordpack/api/wordpackApi';
import {
  createCategoryGenerateImportJob,
  createExampleGenerationJob,
} from './api';

const CLIENT_JOB_ID = '11111111-1111-4111-8111-111111111111';

const expectSameClientJobIdOnReplay = async (
  submit: () => Promise<unknown>,
): Promise<void> => {
  const fetchMock = vi.spyOn(globalThis, 'fetch')
    .mockRejectedValueOnce(new TypeError('response lost'))
    .mockResolvedValueOnce(new Response(
      JSON.stringify({
        job_id: 'job:stable',
        job_type: 'wordpack-generation',
        status: 'queued',
      }),
      { status: 202, headers: { 'Content-Type': 'application/json' } },
    ));

  await submit();

  expect(fetchMock).toHaveBeenCalledTimes(2);
  const requestBodies = fetchMock.mock.calls.map(([, options]) => (
    JSON.parse(String(options?.body)) as { client_job_id?: string }
  ));
  expect(requestBodies.map((body) => body.client_job_id)).toEqual([
    CLIENT_JOB_ID,
    CLIENT_JOB_ID,
  ]);
};

describe('生成ジョブの冪等送信', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('WordPack生成は202応答喪失後も同じクライアントIDで再送する', async () => {
    await expectSameClientJobIdOnReplay(() => createWordPackGenerationJob(
      '/api',
      { lemma: 'alpha' },
      CLIENT_JOB_ID,
    ));
  });

  it('カテゴリ記事化は202応答喪失後も同じクライアントIDで再送する', async () => {
    await expectSameClientJobIdOnReplay(() => createCategoryGenerateImportJob(
      '/api',
      { category: 'Common' },
      CLIENT_JOB_ID,
    ));
  });

  it('追加例文生成は202応答喪失後も同じクライアントIDで再送する', async () => {
    await expectSameClientJobIdOnReplay(() => createExampleGenerationJob(
      '/api',
      'wp:alpha',
      'Common',
      {},
      CLIENT_JOB_ID,
    ));
  });
});
