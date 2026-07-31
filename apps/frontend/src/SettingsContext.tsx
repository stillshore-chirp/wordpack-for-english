import React, { useCallback, useContext, useEffect, useState } from 'react';
import { useAuth } from './AuthContext';
import {
  DEFAULT_REASONING_EFFORT,
  DEFAULT_TEXT_VERBOSITY,
  normalizeLlmModel,
  type ReasoningEffort,
  type TextVerbosity,
} from './lib/wordpack';

export const DEFAULT_REQUEST_TIMEOUT_MS = 1_500_000;

export interface Settings {
  apiBase: string;
  pronunciationEnabled: boolean;
  regenerateScope: 'all' | 'examples' | 'collocations';
  autoAdvanceAfterGrade: boolean;
  requestTimeoutMs: number;
  // 選択中のLLMモデル（UI全体で共有）。未設定時はサーバの既定を同期。
  model?: string;
  reasoningEffort?: ReasoningEffort;
  textVerbosity?: TextVerbosity;
  theme: 'light' | 'dark';
  ttsPlaybackRate: number;
  ttsVolume: number;
  dictionaryInstantGenerate?: boolean;
  hoverTooltipDelayMs?: number;
  openGeneratedWordPackIn?: 'side-peek' | 'detail';
  defaultWordPackDensity?: 'shelf' | 'dense' | 'table';
  ttsEnabled?: boolean;
  autoPlayAfterGeneration?: boolean;
}

interface SettingsValue {
  settings: Settings;
  setSettings: React.Dispatch<React.SetStateAction<Settings>>;
}

const SettingsContext = React.createContext<SettingsValue | undefined>(undefined);

type SettingsStatus = 'loading' | 'ready' | 'error';

interface SettingsErrorInfo {
  message: string;
  detail?: string;
}

interface SettingsSyncNoticeProps {
  status: SettingsStatus;
  errorInfo: SettingsErrorInfo | null;
  autoRetrySecondsLeft: number | null;
  onRetry: () => void;
}

/**
 * 設定同期中の状態を「非ブロッキング通知」として表示する。
 * なぜ: 初期ロード中でもログイン導線を塞がないため。
 */
const SettingsSyncNotice: React.FC<SettingsSyncNoticeProps> = ({
  status,
  errorInfo,
  autoRetrySecondsLeft,
  onRetry,
}) => {
  if (status === 'ready') {
    return null;
  }
  const isError = status === 'error';
  const heading = isError ? 'バックエンド設定の同期に失敗しました' : 'バックエンド設定を同期中';
  return (
    <div
      role={isError ? 'alert' : 'status'}
      aria-live={isError ? 'assertive' : 'polite'}
      style={{
        position: 'fixed',
        right: '1rem',
        bottom: '1rem',
        zIndex: 1000,
        maxWidth: '360px',
        width: 'min(360px, 90vw)',
        padding: '1rem 1.1rem',
        borderRadius: '0.75rem',
        border: isError ? '1px solid #f87171' : '1px solid #cbd5e1',
        background: isError ? '#fef2f2' : '#f8fafc',
        color: '#111827',
        lineHeight: 1.6,
        boxShadow: '0 12px 30px rgba(15, 23, 42, 0.12)'
      }}
    >
      <h2 style={{ marginTop: 0, marginBottom: '0.75rem', fontSize: '1rem' }}>{heading}</h2>
      {status === 'loading' && !errorInfo ? (
        <p style={{ marginBottom: 0 }}>バックエンドの `/api/config` に接続して設定を取得しています…</p>
      ) : null}
      {isError && errorInfo ? (
        <div>
          <p style={{ marginTop: 0 }}>`/api/config` から設定を取得できませんでした。バックエンドが起動しているか、ネットワーク経路をご確認ください。</p>
          <details style={{ marginTop: '0.5rem' }}>
            <summary style={{ cursor: 'pointer' }}>詳細エラーを表示</summary>
            <p style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace', fontSize: '0.8rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word', background: '#fee2e2', padding: '0.75rem', borderRadius: '0.5rem', border: '1px solid #fecaca' }}>
              エラー: {errorInfo.message}
              {errorInfo.detail ? `\n${errorInfo.detail}` : ''}
            </p>
          </details>
          {autoRetrySecondsLeft != null ? (
            <p style={{ marginTop: '0.75rem', marginBottom: 0, color: '#b91c1c' }}>
              {autoRetrySecondsLeft > 0 ? `${autoRetrySecondsLeft}秒後に自動再試行します。` : 'まもなく自動再試行します…'}
            </p>
          ) : null}
          <button
            type="button"
            onClick={onRetry}
            style={{
              marginTop: '0.75rem',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.45rem 1.1rem',
              borderRadius: '0.5rem',
              border: '1px solid #ef4444',
              background: '#fee2e2',
              color: '#b91c1c',
              fontWeight: 600,
              cursor: 'pointer'
            }}
          >
            再試行
          </button>
        </div>
      ) : null}
    </div>
  );
};

export const AUTO_RETRY_INTERVAL_MS = 5000;

export const SettingsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, signOut, authMode } = useAuth();
  const [settings, setSettings] = useState<Settings>(() => {
    const savedTheme = (() => {
      try { return localStorage.getItem('wp.theme') || undefined; } catch { return undefined; }
    })();
    const savedModel = (() => {
      try { return normalizeLlmModel(localStorage.getItem('wp.model')); } catch { return undefined; }
    })();
    const savedTtsPlaybackRate = (() => {
      try {
        const raw = localStorage.getItem('wp.ttsPlaybackRate');
        if (!raw) return undefined;
        const parsed = Number(raw);
        return Number.isFinite(parsed) ? parsed : undefined;
      } catch {
        return undefined;
      }
    })();
    const savedTtsVolume = (() => {
      try {
        const raw = localStorage.getItem('wp.ttsVolume');
        if (!raw) return undefined;
        const parsed = Number(raw);
        return Number.isFinite(parsed) ? parsed : undefined;
      } catch {
        return undefined;
      }
    })();
    const normalizedTtsPlaybackRate = (() => {
      if (!savedTtsPlaybackRate) return 1;
      return Math.min(2, Math.max(0.5, savedTtsPlaybackRate));
    })();
    const normalizedTtsVolume = (() => {
      if (!savedTtsVolume && savedTtsVolume !== 0) return 1;
      return Math.min(3, Math.max(0, savedTtsVolume));
    })();
    return {
      apiBase: '/api',
      pronunciationEnabled: true,
      regenerateScope: 'all',
      autoAdvanceAfterGrade: false,
      // 初期描画直後のズレを避けるため、保守的に長めの既定値。実値は /api/config で即同期。
      requestTimeoutMs: DEFAULT_REQUEST_TIMEOUT_MS,
      model: savedModel,
      reasoningEffort: DEFAULT_REASONING_EFFORT,
      textVerbosity: DEFAULT_TEXT_VERBOSITY,
      theme: savedTheme === 'light' ? 'light' : 'dark',
      ttsPlaybackRate: normalizedTtsPlaybackRate,
      ttsVolume: normalizedTtsVolume,
      dictionaryInstantGenerate: true,
      hoverTooltipDelayMs: 180,
      openGeneratedWordPackIn: 'side-peek',
      defaultWordPackDensity: 'shelf',
      ttsEnabled: true,
      autoPlayAfterGeneration: false,
    };
  });
  const [status, setStatus] = useState<SettingsStatus>('loading');
  const [errorInfo, setErrorInfo] = useState<SettingsErrorInfo | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [autoRetrySecondsLeft, setAutoRetrySecondsLeft] = useState<number | null>(null);

  const retrySync = useCallback(() => {
    setStatus('loading');
    setErrorInfo(null);
    setReloadToken((prev) => prev + 1);
  }, []);

  // 起動時にバックエンドの実行時設定でタイムアウトを同期
  useEffect(() => {
    let aborted = false;
    (async () => {
      try {
        const res = await fetch('/api/config', { method: 'GET' });
        if (res.status === 401) {
          // 401 は「未認証またはセッション切れ」を示し、ログイン画面へ遷移させるために
          // 設定同期エラーと扱わない。ここで ready 状態へ戻すことで、SettingsProvider
          // の子要素（AuthContext 配下）がログイン UI を即時に描画できる。
          if (!aborted) {
            setStatus('ready');
            setErrorInfo(null);
            if (user) {
              // 既存ユーザーがいる場合はクライアント側の認証情報を破棄して匿名状態へ戻す。
              signOut().catch((err) => {
                // eslint-disable-next-line no-console
                console.warn('[Settings] signOut failed after 401 from /api/config', err);
              });
            }
          }
          return;
        }
        if (!res.ok) {
          const bodyText = await res.text().catch(() => '');
          const hint = bodyText ? ` body=${bodyText}` : '';
          throw new Error(`Failed to load /api/config: ${res.status}${hint}`);
        }
        const json = (await res.json()) as { request_timeout_ms?: number; llm_model?: string };
        const ms = json.request_timeout_ms;
        if (!aborted && typeof ms === 'number' && Number.isFinite(ms)) {
          setSettings((prev) => ({ ...prev, requestTimeoutMs: ms }));
        }
        const m = (json as any).llm_model;
        if (!aborted && typeof m === 'string' && m) {
          setSettings((prev) => ({ ...prev, model: prev.model || normalizeLlmModel(m) }));
        }
        if (!aborted) {
          setStatus('ready');
          setErrorInfo(null);
        }
      } catch (err) {
        if (aborted) return;
        const message = err instanceof Error ? err.message : String(err);
        const detail = err instanceof Error && err.stack ? err.stack : undefined;
        setErrorInfo({ message, detail });
        setStatus('error');
        // eslint-disable-next-line no-console
        console.error('[Settings] /api/config の取得に失敗しました。envと同期できていません。', err);
      }
    })();
    return () => {
      aborted = true;
    };
  }, [reloadToken, signOut, user]);

  useEffect(() => {
    if (status !== 'error') {
      setAutoRetrySecondsLeft(null);
      return;
    }
    setAutoRetrySecondsLeft(Math.ceil(AUTO_RETRY_INTERVAL_MS / 1000));
    const countdownInterval = window.setInterval(() => {
      setAutoRetrySecondsLeft((prev) => {
        if (prev == null) return prev;
        return prev > 0 ? prev - 1 : 0;
      });
    }, 1000);
    const timer = window.setTimeout(() => {
      retrySync();
    }, AUTO_RETRY_INTERVAL_MS);
    return () => {
      window.clearInterval(countdownInterval);
      window.clearTimeout(timer);
    };
  }, [status, retrySync]);
  // テーマの永続化
  useEffect(() => {
    try { localStorage.setItem('wp.theme', settings.theme); } catch { /* ignore */ }
  }, [settings.theme]);
  // モデルの永続化
  useEffect(() => {
    if (settings.model) {
      try { localStorage.setItem('wp.model', normalizeLlmModel(settings.model)); } catch { /* ignore */ }
    }
  }, [settings.model]);
  // 音声再生スピードの永続化
  useEffect(() => {
    try { localStorage.setItem('wp.ttsPlaybackRate', String(settings.ttsPlaybackRate)); } catch { /* ignore */ }
  }, [settings.ttsPlaybackRate]);
  // 音量の永続化。音量0〜3の範囲を維持し、音量メニューとAudio APIのブリッジを担保する。
  useEffect(() => {
    try { localStorage.setItem('wp.ttsVolume', String(settings.ttsVolume)); } catch { /* ignore */ }
  }, [settings.ttsVolume]);
  /**
   * 設定同期が完了していなくても、匿名状態ならログイン導線を優先して描画する。
   * なぜ: ログイン UI を塞がず、初期設定は既定値のまま先に体験できるようにするため。
   */
  const shouldRenderChildren = status === 'ready' || authMode === 'anonymous';

  return (
    <SettingsContext.Provider value={{ settings, setSettings }}>
      {shouldRenderChildren ? children : null}
      <SettingsSyncNotice
        status={status}
        errorInfo={errorInfo}
        autoRetrySecondsLeft={autoRetrySecondsLeft}
        onRetry={retrySync}
      />
    </SettingsContext.Provider>
  );
};

export function useSettings(): SettingsValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error('Settings context missing');
  return ctx;
}

export function useOptionalSettings(): SettingsValue | undefined {
  return useContext(SettingsContext);
}
