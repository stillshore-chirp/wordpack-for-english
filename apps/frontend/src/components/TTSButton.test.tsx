import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import * as SettingsContext from '../SettingsContext';
import * as AuthContext from '../AuthContext';
import { TTSButton } from './TTSButton';
import { TTS_TEXT_MAX_LENGTH } from '../constants/tts';
import { guestLockMessage } from './GuestLock';

describe('TTSButton', () => {
  const originalFetch = global.fetch;
  const originalAudio = (global as any).Audio;
  const originalCreateObjectURL = URL.createObjectURL;
  const originalRevokeObjectURL = URL.revokeObjectURL;
  const originalAlert = window.alert;
  let authSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    authSpy = vi.spyOn(AuthContext, 'useAuth').mockReturnValue({ isGuest: false } as any);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    global.fetch = originalFetch;
    if (originalAudio) {
      (global as any).Audio = originalAudio;
    } else {
      delete (global as any).Audio;
    }
    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
    window.alert = originalAlert;
  });

  it('fetches audio, plays it, and keeps default playback speed when context is missing', async () => {
    const playMock = vi.fn().mockResolvedValue(undefined);
    const audioInstances: Array<{ onended: (() => void) | null; onerror: (() => void) | null; playbackRate: number; volume: number }> = [];
    const audioCtor = vi.fn().mockImplementation(() => {
      const instance: any = {
        play: playMock,
        onended: null as (() => void) | null,
        onerror: null as (() => void) | null,
        get playbackRate() {
          return this._rate ?? 1;
        },
        set playbackRate(value: number) {
          this._rate = value;
        },
        _rate: 1,
        get volume() {
          return this._volume ?? 1;
        },
        set volume(value: number) {
          this._volume = value;
        },
        _volume: 1,
      };
      audioInstances.push(instance);
      return instance;
    });
    (global as any).Audio = audioCtor;
    URL.createObjectURL = vi.fn().mockReturnValue('blob:mock-url');
    URL.revokeObjectURL = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue(new Response('audio-data', { status: 200 }));
    global.fetch = fetchMock as unknown as typeof fetch;

    render(<TTSButton text="Hello" />);
    const user = userEvent.setup();
    const button = screen.getByRole('button', { name: '音声' });
    await act(async () => {
      await user.click(button);
    });

    expect(fetchMock).toHaveBeenCalledWith('/api/tts', expect.objectContaining({ method: 'POST' }));
    await waitFor(() => expect(playMock).toHaveBeenCalled());
    expect(URL.createObjectURL).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole('button', { name: '音声' })).toBeEnabled());
    expect(audioInstances[0].playbackRate).toBeCloseTo(1);
    expect(audioInstances[0].volume).toBeCloseTo(1);
    act(() => {
      audioInstances[0].onended?.();
    });
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url');
  });

  it('keeps compact visible text while exposing a target-specific accessible name', () => {
    render(<TTSButton text="Hello" ariaLabel="原文の音声" />);

    expect(screen.getByRole('button', { name: '原文の音声' })).toHaveTextContent('音声');
  });

  it('alerts when fetch fails', async () => {
    (global as any).Audio = vi.fn().mockImplementation(() => ({ play: vi.fn().mockResolvedValue(undefined), onended: null, onerror: null }));
    URL.createObjectURL = vi.fn().mockReturnValue('blob:mock');
    URL.revokeObjectURL = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue(new Response('error', { status: 500 }));
    global.fetch = fetchMock as unknown as typeof fetch;
    const alertMock = vi.fn();
    window.alert = alertMock;
    const consoleMock = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(<TTSButton text="Hello" />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '音声' }));

    await waitFor(() => expect(alertMock).toHaveBeenCalledWith('音声の取得に失敗しました'));
    expect(consoleMock).toHaveBeenCalled();
  });

  it('alerts and blocks fetch when text exceeds the maximum length', async () => {
    const alertMock = vi.fn();
    window.alert = alertMock;
    const fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;

    const overLimit = 'a'.repeat(TTS_TEXT_MAX_LENGTH + 1);

    render(<TTSButton text={overLimit} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '音声' }));

    expect(alertMock).toHaveBeenCalledWith(
      `テキストは ${TTS_TEXT_MAX_LENGTH} 文字以内で入力してください。`
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('applies playback rate from settings context when available', async () => {
    const playMock = vi.fn().mockResolvedValue(undefined);
    const audioInstances: Array<{ playbackRate: number; onended: (() => void) | null; onerror: (() => void) | null; volume: number }> = [];
    const audioCtor = vi.fn().mockImplementation(() => {
      const instance: any = {
        play: playMock,
        onended: null as (() => void) | null,
        onerror: null as (() => void) | null,
        get playbackRate() {
          return this._rate ?? 1;
        },
        set playbackRate(value: number) {
          this._rate = value;
        },
        _rate: 1,
        get volume() {
          return this._volume ?? 1;
        },
        set volume(value: number) {
          this._volume = value;
        },
        _volume: 1,
      };
      audioInstances.push(instance);
      return instance;
    });
    (global as any).Audio = audioCtor;
    URL.createObjectURL = vi.fn().mockReturnValue('blob:mock-url');
    URL.revokeObjectURL = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue(new Response('audio-data', { status: 200 }));
    global.fetch = fetchMock as unknown as typeof fetch;

    const settingsSpy = vi.spyOn(SettingsContext, 'useSettings').mockReturnValue({
      settings: {
        apiBase: '/api',
        pronunciationEnabled: true,
        regenerateScope: 'all',
        autoAdvanceAfterGrade: false,
        requestTimeoutMs: 360000,
        model: 'gpt-5.6-luna',
        reasoningEffort: 'high',
        textVerbosity: 'medium',
        theme: 'dark',
        ttsPlaybackRate: 1.75,
        ttsVolume: 0.4,
      },
      setSettings: vi.fn(),
    });

    render(<TTSButton text="Speed check" />);
    const user = userEvent.setup();
    const button = screen.getByRole('button', { name: '音声' });
    await act(async () => {
      await user.click(button);
    });

    expect(settingsSpy).toHaveBeenCalled();
    await waitFor(() => expect(playMock).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole('button', { name: '音声' })).toBeEnabled());
    expect(audioInstances[0].playbackRate).toBeCloseTo(1.75);
    expect(audioInstances[0].volume).toBeCloseTo(0.4);
  });

  it('supports boosted volume selection up to 300 percent', async () => {
    const playMock = vi.fn().mockResolvedValue(undefined);
    const audioInstances: Array<{ playbackRate: number; onended: (() => void) | null; onerror: (() => void) | null; volume: number }> = [];
    const audioCtor = vi.fn().mockImplementation(() => {
      const instance: any = {
        play: playMock,
        onended: null as (() => void) | null,
        onerror: null as (() => void) | null,
        get playbackRate() {
          return this._rate ?? 1;
        },
        set playbackRate(value: number) {
          this._rate = value;
        },
        _rate: 1,
        get volume() {
          return this._volume ?? 1;
        },
        set volume(value: number) {
          this._volume = value;
        },
        _volume: 1,
      };
      audioInstances.push(instance);
      return instance;
    });
    (global as any).Audio = audioCtor;
    URL.createObjectURL = vi.fn().mockReturnValue('blob:mock-url');
    URL.revokeObjectURL = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue(new Response('audio-data', { status: 200 }));
    global.fetch = fetchMock as unknown as typeof fetch;

    const settingsSpy = vi.spyOn(SettingsContext, 'useSettings').mockReturnValue({
      settings: {
        apiBase: '/api',
        pronunciationEnabled: true,
        regenerateScope: 'all',
        autoAdvanceAfterGrade: false,
        requestTimeoutMs: 360000,
        model: 'gpt-5.6-luna',
        reasoningEffort: 'high',
        textVerbosity: 'medium',
        theme: 'dark',
        ttsPlaybackRate: 1,
        ttsVolume: 2.5,
      },
      setSettings: vi.fn(),
    });

    render(<TTSButton text="Boosted" />);
    const user = userEvent.setup();
    await act(async () => {
      await user.click(screen.getByRole('button', { name: '音声' }));
    });

    expect(settingsSpy).toHaveBeenCalled();
    await waitFor(() => expect(playMock).toHaveBeenCalled());
    expect(audioInstances[0].volume).toBeCloseTo(2.5);
  });

  it('disables the button and shows the guest tooltip after a short hover delay', () => {
    authSpy.mockReturnValue({ isGuest: true } as any);
    vi.useFakeTimers();

    render(<TTSButton text="Hello" />);

    const button = screen.getByRole('button', { name: '音声' });
    const wrapper = button.parentElement as HTMLElement;

    expect(button).toBeDisabled();

    act(() => {
      fireEvent.mouseEnter(wrapper);
    });
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(screen.getByRole('tooltip')).toHaveTextContent(guestLockMessage);

    act(() => {
      fireEvent.mouseLeave(wrapper);
    });
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();

    vi.useRealTimers();
  });
});
