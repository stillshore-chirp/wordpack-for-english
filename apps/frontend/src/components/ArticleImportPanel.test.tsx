import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { http, HttpResponse, delay } from 'msw';
import { server } from '../../vitest.setup';
import { AuthProvider } from '../AuthContext';
import { SettingsProvider } from '../SettingsContext';
import { ModalProvider } from '../ModalContext';
import { NotificationsProvider } from '../NotificationsContext';
import { ConfirmDialogProvider } from '../ConfirmDialogContext';
import { ArticleImportPanel } from './ArticleImportPanel';

const SIDEBAR_PORTAL_ID = 'app-sidebar-controls';

const createSidebarPortalContainer = () => {
  const container = document.createElement('div');
  container.id = SIDEBAR_PORTAL_ID;
  document.body.appendChild(container);
  return container;
};

const setupArticleImportHandlers = () => {
  server.use(
    http.post('/api/article/import', async () => {
      await delay(80);
      return HttpResponse.json({ id: 'art:abcd1234' });
    }),
    http.post('/api/article/generate_and_import', async () => {
      await delay(40);
      return HttpResponse.json({
        lemma: 'test',
        word_pack_id: 'wp:test:abcd',
        category: 'Common',
        generated_examples: 2,
        article_ids: ['art:1', 'art:2'],
      });
    }),
    http.get('/api/article/:id', async ({ params }) => {
      await delay(40);
      return HttpResponse.json({
        id: params.id,
        title_en: 'Title',
        body_en: 'Body EN',
        body_ja: 'Body JA',
        llm_model: 'gpt-5.6-luna',
        llm_params: 'reasoning.effort=high;text.verbosity=medium',
        related_word_packs: [
          { word_pack_id: 'wp:regen:1', lemma: 'alpha', status: 'existing', is_empty: false },
        ],
      });
    }),
  );
};

// なぜ: 500/タイムアウトを明示的に再現し、エラー時のUI復帰を安定検証するため。
const overrideImportFailureHandlers = () => {
  server.use(
    http.post('/api/article/import', async () => {
      await delay(30);
      return HttpResponse.json(
        { detail: { message: 'インポート処理でサーバーエラーが発生しました' } },
        { status: 500 },
      );
    }),
  );
};

// なぜ: 短いタイムアウト設定で例文生成・記事化失敗を素早く再現するため。
const overrideGenerateTimeoutHandlers = () => {
  server.use(
    http.get('/api/config', () => HttpResponse.json({ request_timeout_ms: 30 })),
    http.post('/api/article/generate_and_import', async () => {
      await delay(80);
      return HttpResponse.json({
        lemma: 'test',
        word_pack_id: 'wp:test:abcd',
        category: 'Common',
        generated_examples: 2,
        article_ids: ['art:1', 'art:2'],
      });
    }),
  );
};

// なぜ: 依存する全コンテキストを本番構成に寄せ、実利用時のUI遷移をテストで再現するため。
const renderWithProviders = () => {
  return render(
    <AuthProvider clientId="test-client">
      <SettingsProvider>
        <ModalProvider>
          <ConfirmDialogProvider>
            <NotificationsProvider persist={false}>
              <ArticleImportPanel />
            </NotificationsProvider>
          </ConfirmDialogProvider>
        </ModalProvider>
      </SettingsProvider>
    </AuthProvider>,
  );
};

describe('ArticleImportPanel (MSW + contexts)', () => {
  let portalContainer: HTMLElement | null = null;

  beforeEach(() => {
    setupArticleImportHandlers();
    portalContainer = createSidebarPortalContainer();
  });

  afterEach(() => {
    portalContainer?.remove();
    portalContainer = null;
  });

  it('インポート成功時にボタン無効化→成功メッセージ→モーダル表示となる', async () => {
    renderWithProviders();
    const user = userEvent.setup();

    const textarea = await screen.findByPlaceholderText('文章を貼り付け（日本語/英語）');
    await user.type(textarea, 'hello world');

    const importButton = screen.getByRole('button', { name: '文章をインポート' });
    await user.click(importButton);

    await waitFor(() => {
      expect(importButton).toBeDisabled();
    });

    const statusMessage = await screen.findByRole('status');
    expect(statusMessage).toHaveTextContent('文章をインポートしました');

    const dialog = await screen.findByRole('dialog', { name: 'インポート結果' });
    expect(dialog).toBeInTheDocument();
  });

  it('インポート失敗時にエラー表示とボタン再有効化が行われる', async () => {
    overrideImportFailureHandlers();
    renderWithProviders();
    const user = userEvent.setup();

    const textarea = await screen.findByPlaceholderText('文章を貼り付け（日本語/英語）');
    await user.type(textarea, 'broken import');

    const importButton = screen.getByRole('button', { name: '文章をインポート' });
    await user.click(importButton);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('インポート処理でサーバーエラーが発生しました');

    await waitFor(() => {
      expect(importButton).toBeEnabled();
    });
  });

  it('例文生成・記事化失敗後に実行中表示が解除される', async () => {
    overrideGenerateTimeoutHandlers();
    renderWithProviders();
    const user = userEvent.setup();

    const generateButton = await screen.findByRole('button', { name: '例文を生成して記事化' });
    await user.click(generateButton);

    const runningButton = await screen.findByRole('button', { name: /例文を生成して記事化（実行中/ });
    expect(runningButton).toBeInTheDocument();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Request aborted or timed out');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '例文を生成して記事化' })).toBeInTheDocument();
    });
  });

  it('モデル切替で reasoning/text UI が表示される', async () => {
    renderWithProviders();
    const user = userEvent.setup();

    const modelSelect = await screen.findByLabelText('モデル');
    await user.selectOptions(modelSelect, 'gpt-5.6-luna');

    expect(screen.getByLabelText('reasoning.effort')).toBeInTheDocument();
    expect(screen.getByLabelText('text.verbosity')).toBeInTheDocument();
  });
});
