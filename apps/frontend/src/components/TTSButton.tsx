import { type AriaRole, type CSSProperties, type ReactNode, useMemo, useState } from 'react';
import { useSettings } from '../SettingsContext';
import { TTS_TEXT_MAX_LENGTH } from '../constants/tts';
import { useAuth } from '../AuthContext';
import { GuestLock } from './GuestLock';

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

export function TTSButton({ text, className, icon, label = '音声', ariaLabel, role, voice = 'alloy', style }: Props) {
  const { isGuest } = useAuth();
  const [loading, setLoading] = useState(false);
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
    // バックエンドと同じ閾値で事前チェックし、無駄な HTTP リクエストを避ける。
    if (trimmed.length > TTS_TEXT_MAX_LENGTH) {
      if (typeof console !== 'undefined' && typeof console.warn === 'function') {
        console.warn(
          '[TTS] text exceeds max length',
          { maxLength: TTS_TEXT_MAX_LENGTH, actualLength: trimmed.length }
        );
      }
      if (typeof window !== 'undefined' && typeof window.alert === 'function') {
        window.alert(`テキストは ${TTS_TEXT_MAX_LENGTH} 文字以内で入力してください。`);
      }
      return;
    }
    if (typeof window === 'undefined' || typeof Audio === 'undefined') {
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: trimmed, voice }),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const blob = await res.blob();
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
      audio.onended = () => {
        URL.revokeObjectURL(url);
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
      };
      await audio.play();
    } catch (err) {
      console.error('[TTS] failed to fetch audio', err);
      if (typeof window !== 'undefined' && typeof window.alert === 'function') {
        window.alert('音声の取得に失敗しました');
      }
    } finally {
      setLoading(false);
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
