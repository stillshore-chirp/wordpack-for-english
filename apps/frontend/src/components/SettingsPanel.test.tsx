import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { SettingsPanel } from './SettingsPanel';
import type { Settings } from '../SettingsContext';
import type { RefObject } from 'react';

const setSettingsMock = vi.fn();
const signOutMock = vi.fn();
let currentSettings: Settings;
let currentIsGuest = false;

vi.mock('../SettingsContext', () => ({
  useSettings: () => ({ settings: currentSettings, setSettings: setSettingsMock }),
}));

vi.mock('../AuthContext', () => ({
  useAuth: () => ({
    signOut: signOutMock,
    isAuthenticating: false,
    user: { google_sub: 'tester', email: 'tester@example.com', display_name: 'Tester' },
    error: null,
    clearError: vi.fn(),
    authBypassActive: false,
    authMode: currentIsGuest ? 'guest' : 'authenticated',
    isGuest: currentIsGuest,
    enterGuestMode: vi.fn().mockResolvedValue(undefined),
    missingClientId: false,
    googleClientId: 'test-client',
  }),
}));

describe('SettingsPanel', () => {
  beforeEach(() => {
    currentSettings = {
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
      ttsVolume: 1,
    };
    setSettingsMock.mockReset();
    signOutMock.mockReset();
    currentIsGuest = false;
  });

  it('toggle pronunciation setting from checkbox', async () => {
    const focusRef = { current: null } as RefObject<HTMLElement>;
    render(<SettingsPanel focusRef={focusRef} />);

    const user = userEvent.setup();
    const checkbox = screen.getByLabelText('発音を有効化');
    await user.click(checkbox);

    expect(setSettingsMock).toHaveBeenCalledWith({ ...currentSettings, pronunciationEnabled: false });
  });

  it('calls signOut when logout button is pressed', async () => {
    const focusRef = { current: null } as RefObject<HTMLElement>;
    render(<SettingsPanel focusRef={focusRef} />);

    const user = userEvent.setup();
    const logoutButton = screen.getByRole('button', { name: 'ログアウト（Google セッションを終了）' });
    await user.click(logoutButton);

    expect(signOutMock).toHaveBeenCalledTimes(1);
  });

  it('shows a guest-specific logout label in guest mode', () => {
    currentIsGuest = true;
    const focusRef = { current: null } as RefObject<HTMLElement>;
    render(<SettingsPanel focusRef={focusRef} />);

    expect(screen.getByRole('button', { name: 'ログアウト（ゲスト閲覧を終了）' })).toBeInTheDocument();
  });
});
