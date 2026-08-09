/**
 * OpenAI Speech API が1リクエストで受け取る最大文字数。
 * この値を超える本文は画面側で自動分割し、順次再生する。
 */
export const TTS_API_REQUEST_MAX_LENGTH = 4096;
