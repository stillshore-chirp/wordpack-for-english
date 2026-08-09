import {
  type AriaRole,
  type CSSProperties,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useSettings } from '../SettingsContext';
import { useAuth } from '../AuthContext';
import { GuestLock } from './GuestLock';
import { splitTextForTts } from '../lib/tts';

type Props = {
  text: string;
  className?: string;
  icon?: ReactNode;
  label?: string;
  ariaLabel?: string;
  role?: AriaRole;
  voice?: string;
  style?: CSSProperties;
};

const createPlaybackAbortError = (): Error => {
  const error = new Error('TTS playback was cancelled');
  error.name = 'AbortError';
  return error;
};

const isPlaybackAbortError = (error: unknown): boolean => (
  error instanceof Error && error.name === 'AbortError'
);

export function TTSButton({ text, className, icon, label = '音声', ariaLabel, role, voice = 'alloy', style }: Props) {
  const { isGuest } = useAuth();
  const [loading, setLoading] = useState(false);
  const playbackSequenceRef = useRef(0);
  const requestControllerRef = useRef<AbortController | null>(null);
  const activeAudioCancelRef = useRef<(() => void) | null>(null);
  const cancelPlayback = useCallback(() => {
    playbackSequenceRef.current += 1;
    requestControllerRef.current?.abort();
    requestControllerRef.current = null;
    const cancelAudio = activeAudioCancelRef.current;
    activeAudioCancelRef.current = null;
    cancelAudio?.();
  }, []);

  // 本文の選択が変わった場合、旧本文の待機中リクエストと再生キューを破棄する。
  useEffect(() => {
    cancelPlayback();
    setLoading(false);
  }, [cancelPlayback, text]);

  // 画面遷移やモーダル終了後に、旧本文の音声・有料リクエストを継続しない。
  useEffect(() => () => {
    cancelPlayback();
  }, [cancelPlayback]);
  let contextApiBase: string | undefined;
  let contextPlaybackRate = 1;
  let contextVolume = 1;
  try {
    const { settings } = useSettings();
    contextApiBase = settings.apiBase;
    if (typeof settings.ttsPlaybackRate === 'number' && Number.isFinite(settings.ttsPlaybackRate)) {
      contextPlaybackRate = Math.min(2, Math.max(0.5, settings.ttsPlaybackRate));
    }
    if (typeof settings.ttsVolume === 'number' && Number.isFinite(settings.ttsVolume)) {
      // サイドバーで設定した音量倍率を0〜3へ丸め込み、ボリューム共有の破綻を防ぐ。
      contextVolume = Math.min(3, Math.max(0, settings.ttsVolume));
    }
  } catch (err) {
    contextApiBase = undefined;
  }
  const endpoint = useMemo(() => {
    const base = contextApiBase || '/api';
    const normalized = base.endsWith('/') ? base.slice(0, -1) : base;
    return `${normalized}/tts`;
  }, [contextApiBase]);
  const resolvedAriaLabel = ariaLabel || label;

  const speak = async () => {
    if (loading) return;
    const trimmed = text?.trim();
    if (!trimmed) return;
    if (typeof window === 'undefined' || typeof Audio === 'undefined') {
      return;
    }
    const chunks = splitTextForTts(trimmed);
    cancelPlayback();
    const playbackSequence = playbackSequenceRef.current;
    const requestController = new AbortController();
    requestControllerRef.current = requestController;
    setLoading(true);
    try {
      for (let index = 0; index < chunks.length; index += 1) {
        if (playbackSequenceRef.current !== playbackSequence) {
          throw createPlaybackAbortError();
        }
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: chunks[index], voice }),
          signal: requestController.signal,
        });
        if (playbackSequenceRef.current !== playbackSequence) {
          throw createPlaybackAbortError();
        }
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const blob = await res.blob();
        if (playbackSequenceRef.current !== playbackSequence) {
          throw createPlaybackAbortError();
        }
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        // UIで指定された再生速度と音量をAudioインスタンスに反映させ、設定の即時性を担保する。
        audio.playbackRate = contextPlaybackRate;
        const normalizedVolume = Math.min(3, Math.max(0, contextVolume));
        if (normalizedVolume <= 1) {
          audio.volume = normalizedVolume;
        } else if (
          typeof AudioContext !== 'undefined' &&
          typeof HTMLMediaElement !== 'undefined' &&
          audio instanceof HTMLMediaElement
        ) {
          // 300%までの増幅を実現するため、Web Audio API の GainNode で音量を拡張する。
          audio.volume = 1;
          try {
            const audioContext = new AudioContext();
            const source = audioContext.createMediaElementSource(audio);
            const gainNode = audioContext.createGain();
            gainNode.gain.value = normalizedVolume;
            source.connect(gainNode);
            gainNode.connect(audioContext.destination);
            const closeContext = () => {
              audioContext.close().catch(() => {
                // close失敗はユーザー操作に影響しないため握りつぶす。
              });
            };
            audio.addEventListener('ended', closeContext, { once: true });
            audio.addEventListener('error', closeContext, { once: true });
          } catch (err) {
            audio.volume = normalizedVolume;
          }
        } else {
          audio.volume = normalizedVolume;
        }

        let revoked = false;
        const revokeUrl = () => {
          if (revoked) return;
          revoked = true;
          if (typeof URL.revokeObjectURL === 'function') {
            URL.revokeObjectURL(url);
          }
        };
        const waitForCompletion = index < chunks.length - 1;
        let resolveCompletion: (() => void) | undefined;
        let rejectCompletion: ((reason?: unknown) => void) | undefined;
        const completion = waitForCompletion
          ? new Promise<void>((resolve, reject) => {
            resolveCompletion = resolve;
            rejectCompletion = reject;
          })
          : null;
        let cancelAudio: () => void;
        const clearActiveAudio = () => {
          if (activeAudioCancelRef.current === cancelAudio) {
            activeAudioCancelRef.current = null;
          }
        };
        cancelAudio = () => {
          try {
            audio.pause();
          } catch (error) {
            // テスト用Audioや既に破棄済みの要素ではpauseできない場合がある。
          }
          revokeUrl();
          clearActiveAudio();
          rejectCompletion?.(createPlaybackAbortError());
        };
        activeAudioCancelRef.current = cancelAudio;
        audio.onended = () => {
          revokeUrl();
          clearActiveAudio();
          resolveCompletion?.();
        };
        audio.onerror = () => {
          revokeUrl();
          clearActiveAudio();
          rejectCompletion?.(new Error('Audio playback failed'));
        };
        try {
          await audio.play();
          if (completion) await completion;
        } catch (error) {
          revokeUrl();
          clearActiveAudio();
          throw error;
        }
      }
    } catch (err) {
      const cancelled = playbackSequenceRef.current !== playbackSequence
        || isPlaybackAbortError(err);
      if (!cancelled) {
        console.error('[TTS] failed to fetch audio', err);
        if (typeof window !== 'undefined' && typeof window.alert === 'function') {
          window.alert('音声の取得に失敗しました');
        }
      }
    } finally {
      if (requestControllerRef.current === requestController) {
        requestControllerRef.current = null;
      }
      if (playbackSequenceRef.current === playbackSequence) {
        setLoading(false);
      }
    }
  };

  return (
    <GuestLock isGuest={isGuest}>
      <button
        type="button"
        onClick={speak}
        disabled={loading || !text?.trim()}
        className={className}
        data-testid="speak-btn"
        style={style}
        role={role}
        aria-label={loading ? `${resolvedAriaLabel}を読み上げ中` : resolvedAriaLabel}
      >
        {icon}
        {loading ? '読み上げ中…' : label}
      </button>
    </GuestLock>
  );
}
