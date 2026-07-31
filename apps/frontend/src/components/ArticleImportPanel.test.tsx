import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { http, HttpResponse, delay } from 'msw';
import { server } from '../../vitest.setup';
import { AuthProvider } from '../AuthContext';
import { SettingsProvider } from '../SettingsContext';
import { ModalProvider } from '../ModalContext';
import { NotificationsProvider, useNotifications } from '../NotificationsContext';
import { ConfirmDialogProvider } from '../ConfirmDialogContext';
import { ArticleImportPanel } from './ArticleImportPanel';

const SIDEBAR_PORTAL_ID = 'app-sidebar-controls';

const NotificationProbe = () => {
  const { notifications } = useNotifications();
  return <div data-testid="notification-probe">{JSON.stringify(notifications)}</div>;
};

const createSidebarPortalContainer = () => {
  const container = document.createElement('div');
  container.id = SIDEBAR_PORTAL_ID;
  document.body.appendChild(container);
  return container;
};

const setupArticleImportHandlers = () => {
  server.use(
    http.post('/api/article/import/jobs', async () => {
      await delay(80);
      return HttpResponse.json({
        job_id: 'article-import-job:test',
        status: 'succeeded',
        article_id: 'art:abcd1234',
      }, { status: 202 });
    }),
    http.post('/api/article/generate_and_import/jobs', async () => {
      await delay(40);
      return HttpResponse.json({
        job_id: 'category-generate-import-job:test',
        job_type: 'category-generate-import',
        status: 'succeeded',
        result: {
          lemma: 'test',
          word_pack_id: 'wp:test:abcd',
          category: 'Common',
          generated_examples: 2,
          article_ids: ['art:1', 'art:2'],
        },
      }, { status: 202 });
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
    http.post('/api/article/import/jobs', async () => {
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
    http.get('/api/config', () => HttpResponse.json({
      request_timeout_ms: 30,
      generation_request_timeout_ms: 30,
    })),
    http.post('/api/article/generate_and_import/jobs', async () => {
      await delay(80);
      return HttpResponse.json({
        job_id: 'category-generate-import-job:slow',
        job_type: 'category-generate-import',
        status: 'running',
      }, { status: 202 });
    }),
    http.get('/api/article/generate_and_import/jobs/:jobId', async () => {
      await delay(80);
      return HttpResponse.json({
        job_id: 'category-generate-import-job:slow',
        job_type: 'category-generate-import',
        status: 'running',
      });
    }),
  );
};

// なぜ: 202受理後の状態確認失敗を、生成そのものの失敗と誤表示しない契約を固定するため。
const overrideAcceptedGenerateStatusFailureHandlers = () => {
  server.use(
    http.get('/api/config', () => HttpResponse.json({
      request_timeout_ms: 30,
      generation_request_timeout_ms: 30,
    })),
    http.post('/api/article/generate_and_import/jobs', () => HttpResponse.json({
      job_id: 'category-generate-import-job:accepted',
      job_type: 'category-generate-import',
      status: 'running',
    }, { status: 202 })),
    http.get('/api/article/generate_and_import/jobs/:jobId', async () => {
      await delay(80);
      return HttpResponse.json({
        job_id: 'category-generate-import-job:accepted',
        job_type: 'category-generate-import',
        status: 'running',
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
              <NotificationProbe />
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

  it('ジョブ作成前の500応答は処理継続と誤表示せず確定失敗にする', async () => {
    overrideImportFailureHandlers();
    renderWithProviders();
    const user = userEvent.setup();

    const textarea = await screen.findByPlaceholderText('文章を貼り付け（日本語/英語）');
    await user.type(textarea, 'broken import');

    const importButton = screen.getByRole('button', { name: '文章をインポート' });
    await user.click(importButton);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('インポート処理でサーバーエラーが発生しました');
    expect(screen.queryByText(
      '文章インポートはバックグラウンドで継続しています。生成キューから状態を確認してください。',
    )).not.toBeInTheDocument();

    await waitFor(() => {
      expect(importButton).toBeEnabled();
    });
  });

  it('ジョブ受付後の一時的な記事取得失敗は生成キューで再照合できる状態を保つ', async () => {
    server.use(
      http.get('/api/article/:id', () => HttpResponse.json(
        { detail: { message: '記事を一時的に取得できません' } },
        { status: 503 },
      )),
    );
    renderWithProviders();
    const user = userEvent.setup();

    const textarea = await screen.findByPlaceholderText('文章を貼り付け（日本語/英語）');
    await user.type(textarea, 'recoverable import');
    await user.click(screen.getByRole('button', { name: '文章をインポート' }));

    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent(
      '文章インポートはバックグラウンドで継続しています。生成キューから状態を確認してください。',
    );
    await waitFor(() => {
      const notifications = JSON.parse(
        screen.getByTestId('notification-probe').textContent || '[]',
      );
      expect(notifications).toEqual(expect.arrayContaining([
        expect.objectContaining({
          status: 'progress',
          jobId: 'article-import-job:test',
          jobType: 'article-import',
          articleId: 'art:abcd1234',
        }),
      ]));
    });
  });

  it('202応答が失われても送信前に採番したジョブIDで再照合できる', async () => {
    const clientJobIds: string[] = [];
    server.use(
      http.post('/api/article/import/jobs', async ({ request }) => {
        const body = await request.json() as { client_job_id?: string };
        clientJobIds.push(body.client_job_id ?? '');
        return HttpResponse.error();
      }),
    );
    renderWithProviders();
    const user = userEvent.setup();

    await user.type(
      await screen.findByPlaceholderText('文章を貼り付け（日本語/英語）'),
      'response lost after submission',
    );
    await user.click(screen.getByRole('button', { name: '文章をインポート' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      '文章インポートの送信結果を確認中です。生成キューが同じIDで受理状況を再確認します。',
    );
    expect(clientJobIds).toHaveLength(2);
    expect(new Set(clientJobIds)).toHaveProperty('size', 1);
    expect(clientJobIds[0]).toMatch(/^[0-9a-f-]{36}$/);
    await waitFor(() => {
      const notifications = JSON.parse(
        screen.getByTestId('notification-probe').textContent || '[]',
      );
      expect(notifications).toEqual(expect.arrayContaining([
        expect.objectContaining({
          status: 'progress',
          jobId: `article-import-job:${clientJobIds[0]}`,
          jobType: 'article-import',
        }),
      ]));
    });
  });

  it('例文生成・記事化の202応答がタイムアウトした後も実行中表示を解除して再照合する', async () => {
    overrideGenerateTimeoutHandlers();
    renderWithProviders();
    const user = userEvent.setup();

    const generateButton = await screen.findByRole('button', { name: '例文を生成して記事化' });
    await user.click(generateButton);

    const runningButton = await screen.findByRole('button', { name: /例文を生成して記事化（実行中/ });
    expect(runningButton).toBeInTheDocument();

    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent(
      '1カテゴリの送信結果を確認中です。生成キューが同じIDで受理状況を再確認します。',
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '例文を生成して記事化' })).toBeInTheDocument();
    });
  });

  it('202受理後の状態確認失敗は失敗表示にせず生成キューへ引き継ぐ', async () => {
    overrideAcceptedGenerateStatusFailureHandlers();
    renderWithProviders();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: '例文を生成して記事化' }));

    const status = await screen.findByRole('status', {}, { timeout: 3000 });
    expect(status).toHaveTextContent(
      '1カテゴリの例文生成・記事化をバックグラウンドで継続しています。生成キューから状態を確認できます。',
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    await waitFor(() => {
      const notifications = JSON.parse(
        screen.getByTestId('notification-probe').textContent || '[]',
      );
      expect(notifications).toEqual(expect.arrayContaining([
        expect.objectContaining({
          status: 'progress',
          jobId: 'category-generate-import-job:accepted',
          jobType: 'category-generate-import',
        }),
      ]));
    });
    expect(screen.getByRole('button', { name: '例文を生成して記事化' })).toBeInTheDocument();
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
