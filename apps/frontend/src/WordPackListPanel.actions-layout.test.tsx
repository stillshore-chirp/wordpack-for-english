import { render, screen, waitFor, within, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { App } from './App';
import { AppProviders } from './main';

describe('WordPackListPanel card actions layout', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    (globalThis as any).fetch = vi.fn();
    try { sessionStorage.clear(); } catch {}
    try {
      localStorage.setItem(
        'wordpack.auth.v1',
        JSON.stringify({
          authMode: 'authenticated',
          user: { google_sub: 'tester', email: 'tester@example.com', display_name: 'Tester' },
        }),
      );
    } catch {}
  });

  afterEach(() => {
    try {
      localStorage.removeItem('wordpack.auth.v1');
    } catch {}
  });

  function renderWithAuth() {
    return render(
      <AppProviders googleClientId="test-client">
        <App />
      </AppProviders>,
    );
  }

  function setupFetchMocks() {
    const mock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: any, init?: any) => {
      const url = typeof input === 'string' ? input : (input as URL).toString();
      const method = init?.method ?? 'GET';

      if (url.endsWith('/api/config') && method === 'GET') {
        return new Response(
          JSON.stringify({ request_timeout_ms: 60000 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      if (url.startsWith('/api/word/packs?') && method === 'GET') {
        const now = new Date();
        const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
        return new Response(
          JSON.stringify({
            items: [
              { id: 'wp:test:1', lemma: 'delta', sense_title: 'デルタ概説', created_at: now.toISOString(), updated_at: yesterday.toISOString(), is_empty: true, checked_only_count: 0, learned_count: 0 },
              { id: 'wp:test:2', lemma: 'alpha', sense_title: 'アルファ概説', created_at: now.toISOString(), updated_at: now.toISOString(), is_empty: false, examples_count: { Dev: 1, CS: 0, LLM: 0, Business: 0, Common: 0 }, checked_only_count: 0, learned_count: 0 },
            ],
            total: 2,
            limit: 20,
            offset: 0,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      if (url.endsWith('/api/word/packs/wp:test:1/regenerate/async') && method === 'POST') {
        return new Response(JSON.stringify({ job_id: 'job:test:1', status: 'succeeded' }), { status: 202, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/word/packs/wp:test:1/regenerate/jobs/job:test:1') && method === 'GET') {
        return new Response(JSON.stringify({ job_id: 'job:test:1', status: 'succeeded' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      if (url.startsWith('/api/word/packs/wp:test:') && method === 'DELETE') {
        return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      if (url.endsWith('/api/word/packs/wp:test:1') && method === 'GET') {
        return new Response(JSON.stringify({ lemma: 'delta', sense_title: 'デルタ概説', pronunciation: null, senses: [], examples: {}, collocations: {}, contrast: [], etymology: { note: '-', confidence: 'low' }, study_card: '', citations: [], confidence: 'low' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/word/packs/wp:test:2') && method === 'GET') {
        return new Response(JSON.stringify({ lemma: 'alpha', sense_title: 'アルファ概説', pronunciation: null, senses: [], examples: {}, collocations: {}, contrast: [], etymology: { note: '-', confidence: 'low' }, study_card: '', citations: [], confidence: 'low' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      return new Response('not found', { status: 404 });
    });
    return mock;
  }

  it('カード下部に主要操作を並べ、破壊的操作はメニューに置く', async () => {
    setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();

    // WordPackタブ（既定）を表示
    await waitFor(() => expect(screen.getByRole('heading', { name: /保存済みWordPack/ })).toBeInTheDocument());
    const cards = await screen.findAllByTestId('wp-card');
    expect(cards.length).toBeGreaterThanOrEqual(2);

    // is_empty の delta カードを対象に検証
    const target = cards.find((el) => /delta/.test(el.textContent || ''))!;

    expect(within(target).getByRole('button', { name: '開く' })).toBeInTheDocument();
    expect(within(target).getByRole('button', { name: 'delta のその他の操作' })).toHaveTextContent('その他');
    expect(within(target).getByRole('button', { name: 'deltaの音声' })).toBeInTheDocument();
    expect(within(target).getByRole('button', { name: '生成' })).toBeInTheDocument();
    expect(within(target).getByRole('button', { name: '語義' })).toBeInTheDocument();

    // 非 empty カードでは生成操作を出さないこと
    const nonEmpty = cards.find((el) => /alpha/.test(el.textContent || ''))!;
    expect(within(nonEmpty).queryByRole('button', { name: '生成' })).not.toBeInTheDocument();

    await act(async () => {
      await user.click(within(target).getByRole('button', { name: 'delta のその他の操作' }));
    });
    const menu = screen.getByRole('menu', { name: 'delta の操作メニュー' });
    expect(within(menu).getByRole('menuitem', { name: '削除' })).toBeInTheDocument();

    // 動作確認（語義をクリックしてもカードが開かない＝イベント停止）
    const senseBtn = within(target).getByRole('button', { name: '語義' });
    await act(async () => { await user.click(senseBtn); });
    expect(screen.queryByRole('dialog', { name: 'WordPack プレビュー' })).not.toBeInTheDocument();
  });

  it('リスト表示は単列の意味構造と段階的な操作メニューを持つ', async () => {
    setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();

    await waitFor(() => expect(screen.getByRole('heading', { name: /保存済みWordPack/ })).toBeInTheDocument());
    await act(async () => {
      await user.click(screen.getByRole('button', { name: /^リスト$/ }));
    });

    const list = screen.getByRole('list', { name: '保存済みWordPackのリスト' });
    const items = within(list).getAllByRole('listitem');
    expect(items).toHaveLength(2);

    const target = items.find((item) => item.textContent?.includes('delta'));
    expect(target).toBeDefined();
    const targetItem = target!;
    const trigger = within(targetItem).getByRole('button', { name: 'delta のその他の操作' });

    expect(within(targetItem).getByRole('button', { name: '開く' })).toBeInTheDocument();
    expect(within(targetItem).queryByRole('button', { name: '生成' })).not.toBeInTheDocument();
    expect(within(targetItem).queryByText('公開対象のWordPackのみ、ゲスト一覧に表示されます。')).not.toBeInTheDocument();

    await act(async () => {
      await user.click(trigger);
    });

    const menu = within(targetItem).getByRole('menu', { name: 'delta の操作メニュー' });
    expect(within(menu).getByRole('menuitem', { name: '例文を生成' })).toBeInTheDocument();
    expect(within(menu).getByRole('menuitem', { name: 'deltaの音声を再生' })).toBeInTheDocument();
    expect(within(menu).getByRole('menuitemcheckbox', { name: '語義を表示' })).toBeInTheDocument();
    expect(within(menu).getByRole('menuitem', { name: 'ゲスト公開にする' })).toBeInTheDocument();
    expect(within(menu).getByRole('menuitem', { name: '削除' })).toBeInTheDocument();
    expect(trigger).toHaveTextContent('その他');

    await waitFor(() => {
      expect(within(menu).getByRole('menuitem', { name: '例文を生成' })).toHaveFocus();
      expect(within(menu).getByRole('menuitem', { name: '削除' })).toBeEnabled();
    });
    await user.keyboard('{End}');
    expect(within(menu).getByRole('menuitem', { name: '削除' })).toHaveFocus();
    await user.keyboard('{ArrowDown}');
    expect(within(menu).getByRole('menuitem', { name: '例文を生成' })).toHaveFocus();

    await act(async () => {
      await user.keyboard('{Escape}');
    });
    expect(within(targetItem).queryByRole('menu')).not.toBeInTheDocument();
    await waitFor(() => expect(trigger).toHaveFocus());
  });
});
