import { ApiError } from './ApiError';

/**
 * 202 応答を受け取れなかった場合だけ、同じクライアント採番IDの POST を1回再送する。
 * サーバーの確定 HTTP エラーは再送せず、そのまま利用者へ返す。
 */
export const submitIdempotentJob = async <T>(
  submit: () => Promise<T>,
  canRetry: () => boolean = () => true,
): Promise<T> => {
  try {
    return await submit();
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 0 || !canRetry()) {
      throw error;
    }
    return submit();
  }
};
