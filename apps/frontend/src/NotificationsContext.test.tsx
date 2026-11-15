import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { NotificationsProvider, useNotifications } from './NotificationsContext';
import { APP_EVENTS } from './shared/events/appEvents';
import { NotificationsOverlay } from './components/NotificationsOverlay';

const Harness = () => {
  const { notifications, add, update } = useNotifications();
  const notification = notifications[0];
  return (
    <>
      <button type="button" onClick={() => add({ id: 'job-1', title: '生成中', status: 'progress' })}>
        add
      </button>
      <button type="button" onClick={() => update('job-1', { title: '生成中', status: 'progress' })}>
        same
      </button>
      <button type="button" onClick={() => update('job-1', { status: 'success' })}>
        change
      </button>
      <output data-testid="notification">{notification ? JSON.stringify(notification) : ''}</output>
    </>
  );
};

const NotificationOverlayHarness = () => {
  const { add, update } = useNotifications();
  return (
    <>
      <button
        type="button"
        onClick={() => add({
          id: 'category-job-1',
          title: '【CS】の例文生成・記事化を開始します',
          message: '関連語を選定し、例文を生成して記事化します',
          status: 'progress',
          model: 'gpt-5.6-luna',
          category: 'CS',
        })}
      >
        例文生成・記事化を開始
      </button>
      <button
        type="button"
        onClick={() => update('category-job-1', {
          title: '例文生成・記事化完了',
          message: '【delta】5件の例文から記事を作成しました',
          status: 'success',
          model: 'gpt-5.6-luna',
          category: 'CS',
        })}
      >
        例文生成・記事化を完了
      </button>
    </>
  );
};

afterEach(() => {
  vi.restoreAllMocks();
});

it('同一内容のpoll更新ではupdatedAtを進めずライブ通知の再発火を防ぐ', async () => {
  const now = vi.spyOn(Date, 'now').mockReturnValue(1000);
  const user = userEvent.setup();
  render(
    <NotificationsProvider persist={false}>
      <Harness />
    </NotificationsProvider>,
  );

  await user.click(screen.getByRole('button', { name: 'add' }));
  expect(JSON.parse(screen.getByTestId('notification').textContent || '{}').updatedAt).toBe(1000);

  now.mockReturnValue(2000);
  await user.click(screen.getByRole('button', { name: 'same' }));
  expect(JSON.parse(screen.getByTestId('notification').textContent || '{}').updatedAt).toBe(1000);

  now.mockReturnValue(3000);
  await user.click(screen.getByRole('button', { name: 'change' }));
  expect(JSON.parse(screen.getByTestId('notification').textContent || '{}').updatedAt).toBe(3000);
});

it('認証ローカルデータ消去イベントで個人通知をクリアする', async () => {
  const user = userEvent.setup();
  render(
    <NotificationsProvider persist={false}>
      <Harness />
    </NotificationsProvider>,
  );

  await user.click(screen.getByRole('button', { name: 'add' }));
  expect(screen.getByTestId('notification')).toHaveTextContent('job-1');

  await act(async () => {
    window.dispatchEvent(new CustomEvent(APP_EVENTS.localAuthDataCleared));
  });

  expect(screen.getByTestId('notification')).toHaveTextContent('');
});

it('別タブの通知ストレージ削除でも個人通知をクリアする', async () => {
  const user = userEvent.setup();
  render(
    <NotificationsProvider persist={false}>
      <Harness />
    </NotificationsProvider>,
  );

  await user.click(screen.getByRole('button', { name: 'add' }));
  expect(screen.getByTestId('notification')).toHaveTextContent('job-1');

  await act(async () => {
    window.dispatchEvent(new StorageEvent('storage', {
      key: 'wpfe.notifications.v1',
      oldValue: JSON.stringify([{ id: 'job-1' }]),
      newValue: null,
      storageArea: window.localStorage,
    }));
  });

  expect(screen.getByTestId('notification')).toHaveTextContent('');
});

it('Readerページでカテゴリ生成通知の進行時間・完了詳細を表示し閉じられる', async () => {
  const originalPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  window.history.pushState({}, '', '/reader');
  vi.useFakeTimers();
  let currentTime = 1000;
  vi.spyOn(Date, 'now').mockImplementation(() => currentTime);
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  const { unmount } = render(
    <NotificationsProvider persist={false}>
      <NotificationsOverlay />
      <NotificationOverlayHarness />
    </NotificationsProvider>,
  );

  try {
    await user.click(screen.getByRole('button', { name: '例文生成・記事化を開始' }));

    const progress = screen.getByRole('status', {
      name: '【CS】の例文生成・記事化を開始します - progress',
    });
    expect(progress).toHaveTextContent('関連語を選定し、例文を生成して記事化します');
    expect(progress).toHaveTextContent('経過 0:00 ( gpt-5.6-luna, CS )');

    currentTime = 2500;
    await act(async () => {
      vi.advanceTimersByTime(250);
    });
    expect(progress).toHaveTextContent('経過 0:01 ( gpt-5.6-luna, CS )');

    currentTime = 3_662_000;
    await act(async () => {
      vi.advanceTimersByTime(250);
    });
    expect(progress).toHaveTextContent('経過 1:01:01 ( gpt-5.6-luna, CS )');

    await user.click(screen.getByRole('button', { name: '例文生成・記事化を完了' }));

    const completed = screen.getByRole('status', { name: '例文生成・記事化完了 - success' });
    expect(completed).toHaveTextContent('【delta】5件の例文から記事を作成しました');
    expect(completed).toHaveTextContent('所要 1:01:01 ( gpt-5.6-luna, CS )');
    await user.click(within(completed).getByRole('button', { name: '閉じる' }));
    expect(screen.queryByRole('status', { name: '例文生成・記事化完了 - success' })).not.toBeInTheDocument();
  } finally {
    unmount();
    vi.useRealTimers();
    window.history.replaceState({}, '', originalPath);
  }
});
