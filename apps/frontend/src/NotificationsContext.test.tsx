import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { NotificationsProvider, useNotifications } from './NotificationsContext';
import { APP_EVENTS } from './shared/events/appEvents';

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
