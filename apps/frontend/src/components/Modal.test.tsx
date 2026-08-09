import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { useState } from 'react';
import { vi } from 'vitest';
import { axe } from 'vitest-axe';
import { Modal } from './Modal';

describe('Modal width constraint', () => {
  it('sets max width to 90% of main content width (with viewport cap)', () => {
    render(
      <Modal isOpen onClose={() => {}} title="Test">
        <div>content</div>
      </Modal>
    );

    const dialog = screen.getByRole('dialog');
    const container = dialog.querySelector('div > div') as HTMLDivElement | null;
    expect(container).not.toBeNull();
    // 期待値: min(96vw, calc(var(--main-max-width, 1000px) * 0.90))
    expect(container!.style.maxWidth).toBe('min(96vw, calc(var(--main-max-width, 1000px) * 0.90))');
    // 可読性のため、width は 100% であることも確認
    expect(container!.style.width).toBe('100%');
  });

  it('allows overriding max width when specified', () => {
    render(
      <Modal
        isOpen
        onClose={() => {}}
        title="Test"
        maxWidth="480px"
      >
        <div>content</div>
      </Modal>
    );

    const dialog = screen.getByRole('dialog');
    const container = dialog.querySelector('div > div') as HTMLDivElement | null;
    expect(container).not.toBeNull();
    expect(container!.style.maxWidth).toBe('480px');
  });

  it('toggles an opted-in detail modal between the standard and exactly doubled width', async () => {
    const user = userEvent.setup();
    render(
      <Modal isOpen onClose={() => {}} title="詳細プレビュー" allowWideView>
        <div>content</div>
      </Modal>
    );

    const dialog = screen.getByRole('dialog', { name: '詳細プレビュー' });
    const panel = dialog.querySelector('[data-modal-panel="true"]') as HTMLDivElement | null;
    const widthToggle = screen.getByRole('button', { name: 'ワイド表示' });
    expect(panel).not.toBeNull();
    expect(panel!.style.maxWidth).toBe('min(96vw, calc(var(--main-max-width, 1000px) * 0.90))');
    expect(panel).toHaveAttribute('data-modal-wide-view', 'false');
    expect(widthToggle).toHaveAttribute('aria-pressed', 'false');

    await act(async () => {
      await user.click(widthToggle);
    });

    expect(panel!.style.maxWidth).toBe('min(96vw, calc(var(--main-max-width, 1000px) * 1.80))');
    expect(panel).toHaveAttribute('data-modal-wide-view', 'true');
    expect(widthToggle).toHaveAttribute('aria-pressed', 'true');
    expect(await axe(document.body, { rules: { 'color-contrast': { enabled: false } } })).toHaveNoViolations();

    await act(async () => {
      await user.click(widthToggle);
    });

    expect(panel!.style.maxWidth).toBe('min(96vw, calc(var(--main-max-width, 1000px) * 0.90))');
    expect(panel).toHaveAttribute('data-modal-wide-view', 'false');
    expect(widthToggle).toHaveAttribute('aria-pressed', 'false');
  });

  it('resets an opted-in detail modal to the standard width when reopened', async () => {
    const user = userEvent.setup();
    const Harness = () => {
      const [open, setOpen] = useState(true);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>再度開く</button>
          <Modal isOpen={open} onClose={() => setOpen(false)} title="詳細プレビュー" allowWideView>
            <div>content</div>
          </Modal>
        </>
      );
    };

    render(<Harness />);

    await user.click(screen.getByRole('button', { name: 'ワイド表示' }));
    expect(screen.getByRole('button', { name: 'ワイド表示' })).toHaveAttribute('aria-pressed', 'true');
    await user.click(screen.getByRole('button', { name: '詳細プレビューを閉じる' }));
    await user.click(screen.getByRole('button', { name: '再度開く' }));

    expect(screen.getByRole('button', { name: 'ワイド表示' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('does not show the width toggle for modals that did not opt in', () => {
    render(
      <Modal isOpen onClose={() => {}} title="確認">
        <div>content</div>
      </Modal>
    );

    expect(screen.queryByRole('button', { name: 'ワイド表示' })).not.toBeInTheDocument();
  });
});

describe('Modal close interactions', () => {
  it('renders dialog with title', () => {
    render(
      <Modal isOpen onClose={() => {}} title="確認">
        <div>content</div>
      </Modal>
    );

    expect(screen.getByRole('dialog', { name: '確認' })).toBeInTheDocument();
  });

  it('keeps aria attributes and passes a11y checks', async () => {
    const { container } = render(
      <Modal isOpen onClose={() => {}} title="確認">
        <div>content</div>
      </Modal>
    );

    // a11y: モーダルの aria-labelledby/aria-modal が維持されていることを担保する。
    const dialog = screen.getByRole('dialog', { name: '確認' });
    const title = screen.getByText('確認');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-labelledby', title.id);
    expect(await axe(container, { rules: { 'color-contrast': { enabled: false } } })).toHaveNoViolations();
  });

  it('calls onClose when pressing Escape', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();

    render(
      <Modal isOpen onClose={onClose} title="確認">
        <div>content</div>
      </Modal>
    );

    await act(async () => {
      await user.keyboard('{Escape}');
    });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when clicking the backdrop wrapper', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();

    render(
      <Modal isOpen onClose={onClose} title="確認">
        <div>content</div>
      </Modal>
    );

    const dialog = screen.getByRole('dialog', { name: '確認' });
    // 背景クリック判定はラッパー自身へのクリックで行う。
    await user.click(dialog);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when clicking the close button', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();

    render(
      <Modal isOpen onClose={onClose} title="確認">
        <div>content</div>
      </Modal>
    );

    // ユーザー操作として「閉じる」ボタンをクリックする。
    await user.click(screen.getByRole('button', { name: '確認を閉じる' }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('keeps keyboard focus inside the dialog', async () => {
    const user = userEvent.setup();

    render(
      <Modal isOpen onClose={() => {}} title="確認">
        <button type="button">最初の操作</button>
        <button type="button">最後の操作</button>
      </Modal>
    );

    const closeButton = screen.getByRole('button', { name: '確認を閉じる' });
    await waitFor(() => expect(closeButton).toHaveFocus());

    await user.tab({ shift: true });

    expect(screen.getByRole('button', { name: '最後の操作' })).toHaveFocus();
  });

  it('skips visually hidden controls when wrapping keyboard focus', () => {
    render(
      <Modal isOpen onClose={() => {}} title="確認">
        <button type="button" style={{ display: 'none' }}>非表示の操作</button>
        <button type="button">最後の可視操作</button>
      </Modal>
    );

    const lastVisibleButton = screen.getByRole('button', { name: '最後の可視操作' });
    lastVisibleButton.focus();
    fireEvent.keyDown(window, { key: 'Tab' });

    expect(screen.getByRole('button', { name: '確認を閉じる' })).toHaveFocus();
  });

  it('keeps the topmost concurrently opened modal accessible', async () => {
    const user = userEvent.setup();

    const Harness = () => {
      const [baseOpen, setBaseOpen] = useState(false);
      const [topOpen, setTopOpen] = useState(false);
      return (
        <>
          <button
            type="button"
            onClick={() => {
              setBaseOpen(true);
              setTopOpen(true);
            }}
          >
            同時に開く
          </button>
          <Modal isOpen={baseOpen} onClose={() => setBaseOpen(false)} title="ベースモーダル">
            <button type="button">ベース操作</button>
          </Modal>
          <Modal isOpen={topOpen} onClose={() => setTopOpen(false)} title="上位モーダル">
            <button type="button">上位操作</button>
          </Modal>
        </>
      );
    };

    render(<Harness />);

    await act(async () => {
      await user.click(screen.getByRole('button', { name: '同時に開く' }));
    });

    const topDialog = await screen.findByRole('dialog', { name: '上位モーダル' });
    expect(topDialog).not.toHaveAttribute('aria-hidden');
    expect((topDialog as HTMLElement & { inert?: boolean }).inert).not.toBe(true);
    await waitFor(() => expect(screen.getByRole('button', { name: '上位モーダルを閉じる' })).toHaveFocus());

    await act(async () => {
      fireEvent.keyDown(window, { key: 'Escape' });
    });

    expect(screen.queryByRole('dialog', { name: '上位モーダル' })).not.toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: 'ベースモーダル' })).toBeInTheDocument();
  });

  it('returns focus to the opener after closing', async () => {
    const user = userEvent.setup();

    const Harness = () => {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>開く</button>
          <Modal isOpen={open} onClose={() => setOpen(false)} title="確認">
            <button type="button">中の操作</button>
          </Modal>
        </>
      );
    };

    render(<Harness />);

    const opener = screen.getByRole('button', { name: '開く' });
    await act(async () => {
      await user.click(opener);
    });
    await act(async () => {
      await user.click(await screen.findByRole('button', { name: '確認を閉じる' }));
    });

    await waitFor(() => expect(opener).toHaveFocus());
  });
});


