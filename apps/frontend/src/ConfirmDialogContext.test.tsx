import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { ConfirmDialogProvider, useConfirmDialog } from './ConfirmDialogContext';
import { APP_EVENTS } from './shared/events/appEvents';

interface ConfirmProbeProps {
  onResult: (result: boolean) => void;
}

const ConfirmProbe = ({ onResult }: ConfirmProbeProps) => {
  const confirm = useConfirmDialog();
  return (
    <button
      type="button"
      onClick={() => {
        void confirm('秘密のWordPack').then(onResult);
      }}
    >
      削除を準備
    </button>
  );
};

const renderConfirmProbe = (onResult = vi.fn()) => {
  render(
    <ConfirmDialogProvider>
      <ConfirmProbe onResult={onResult} />
    </ConfirmDialogProvider>,
  );
  return onResult;
};

describe('ConfirmDialogProvider authentication cleanup', () => {
  it('resolves a pending confirmation as false and removes its sensitive label after local auth data is cleared', async () => {
    const user = userEvent.setup();
    const onResult = renderConfirmProbe();

    await user.click(screen.getByRole('button', { name: '削除を準備' }));
    expect(screen.getByRole('dialog', { name: '削除確認' })).toHaveTextContent('秘密のWordPack');

    act(() => {
      window.dispatchEvent(new CustomEvent(APP_EVENTS.localAuthDataCleared));
    });

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: '削除確認' })).not.toBeInTheDocument();
      expect(onResult).toHaveBeenCalledWith(false);
    });
    expect(screen.queryByText('秘密のWordPack')).not.toBeInTheDocument();
  });

  it('ignores a stale confirm click after the auth cleanup event and does not resolve true', async () => {
    const user = userEvent.setup();
    const onResult = renderConfirmProbe();

    await user.click(screen.getByRole('button', { name: '削除を準備' }));
    const confirmButton = screen.getByRole('button', { name: '削除する' });

    act(() => {
      window.dispatchEvent(new CustomEvent(APP_EVENTS.localAuthDataCleared));
      fireEvent.click(confirmButton);
    });

    await waitFor(() => expect(onResult).toHaveBeenCalledWith(false));
    expect(onResult).not.toHaveBeenCalledWith(true);
  });

  it('cancels every queued confirmation when local auth data is cleared', async () => {
    const onResult = vi.fn();
    let requestConfirm: ((targetLabel: string) => Promise<boolean>) | undefined;
    const HookProbe = () => {
      requestConfirm = useConfirmDialog();
      return null;
    };

    render(
      <ConfirmDialogProvider>
        <HookProbe />
      </ConfirmDialogProvider>,
    );

    let first: Promise<boolean> | undefined;
    let second: Promise<boolean> | undefined;
    act(() => {
      first = requestConfirm?.('first secret');
      second = requestConfirm?.('second secret');
    });
    first?.then((result) => onResult('first', result));
    second?.then((result) => onResult('second', result));

    act(() => {
      window.dispatchEvent(new CustomEvent(APP_EVENTS.localAuthDataCleared));
    });

    await waitFor(() => {
      expect(onResult).toHaveBeenCalledWith('first', false);
      expect(onResult).toHaveBeenCalledWith('second', false);
    });
    expect(screen.queryByText('first secret')).not.toBeInTheDocument();
    expect(screen.queryByText('second secret')).not.toBeInTheDocument();
  });

  it('keeps the normal confirmation flow resolving true', async () => {
    const user = userEvent.setup();
    const onResult = renderConfirmProbe();

    await user.click(screen.getByRole('button', { name: '削除を準備' }));
    await user.click(screen.getByRole('button', { name: '削除する' }));

    await waitFor(() => expect(onResult).toHaveBeenCalledWith(true));
  });
});
