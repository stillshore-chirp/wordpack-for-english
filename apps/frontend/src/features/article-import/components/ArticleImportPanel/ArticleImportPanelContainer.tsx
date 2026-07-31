import React, { useMemo, useRef, useState } from 'react';
import {
  DEFAULT_GENERATION_REQUEST_TIMEOUT_MS,
  useSettings,
} from '../../../../SettingsContext';
import { useModal } from '../../../../ModalContext';
import { useConfirmDialog } from '../../../../ConfirmDialogContext';
import { useNotifications } from '../../../../NotificationsContext';
import { ApiError } from '../../../../shared/api/ApiError';
import { fetchJson } from '../../../../shared/api/fetchJson';
import { regenerateWordPackRequest } from '../../../../lib/wordpack';
import ArticleDetailModal from '../../../../components/ArticleDetailModal';
import { SidebarPortal } from '../../../../components/SidebarPortal';
import { ARTICLE_IMPORT_TEXT_MAX_LENGTH } from '../../../../constants/article';
import { useAuth } from '../../../../AuthContext';
import { GuestLock } from '../../../../components/GuestLock';
import {
  DEFAULT_LLM_MODEL,
  DEFAULT_REASONING_EFFORT,
  DEFAULT_TEXT_VERBOSITY,
  SUPPORTED_LLM_MODELS,
  SUPPORTED_REASONING_EFFORTS,
  SUPPORTED_TEXT_VERBOSITIES,
  normalizeLlmModel,
  type ReasoningEffort,
  type TextVerbosity,
} from '../../../../lib/wordpack';
import {
  createArticleImportJob,
  deleteWordPackFromArticle,
  fetchArticleDetail,
  fetchArticleImportJob,
  type ArticleImportJobResponse,
  type ArticleDetailResponse,
} from '../../api/articleApi';
import { APP_EVENTS, dispatchAppEvent } from '../../../../shared/events/appEvents';
import {
  createCategoryGenerateImportJob,
  fetchCategoryGenerateImportJob,
} from '../../../generation/api';

interface ArticleImportPanelProps {
  showInlineControls?: boolean;
  showSidebarControls?: boolean;
}

type ControlPlacement = 'inline' | 'sidebar';
const EXAMPLE_CATEGORIES = ['Dev', 'CS', 'LLM', 'Business', 'Common'] as const;
type ExampleCategory = (typeof EXAMPLE_CATEGORIES)[number];
const ARTICLE_IMPORT_POLL_INTERVAL_MS = 1000;

export const ArticleImportPanel: React.FC<ArticleImportPanelProps> = ({
  showInlineControls = true,
  showSidebarControls = true,
}) => {
  const { isGuest } = useAuth();
  const { settings, setSettings } = useSettings();
  const { setModalOpen } = useModal();
  const { add: addNotification, update: updateNotification } = useNotifications();
  const confirmDialog = useConfirmDialog();
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);
  const [genRunning, setGenRunning] = useState(0);
  const [msg, setMsg] = useState<{ kind: 'status' | 'alert'; text: string } | null>(null);
  const [article, setArticle] = useState<ArticleDetailResponse | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [wpPreviewId, setWpPreviewId] = useState<string | null>(null);
  const [selectedCategories, setSelectedCategories] = useState<ExampleCategory[]>(['Common']);
  const abortRef = useRef<AbortController | null>(null);

  const [model, setModel] = useState<string>(normalizeLlmModel(settings.model || DEFAULT_LLM_MODEL));

  const trimmedText = useMemo(() => text.trim(), [text]);
  const isTextTooLong = useMemo(
    () => trimmedText.length > ARTICLE_IMPORT_TEXT_MAX_LENGTH,
    [trimmedText],
  );
  const importDisabled = loading || !trimmedText || isTextTooLong;
  const hasSelectedCategories = selectedCategories.length > 0;
  const allCategoriesSelected = selectedCategories.length === EXAMPLE_CATEGORIES.length;
  const generateDisabled = loading || genRunning > 0 || !hasSelectedCategories;

  const showAdvancedModelOptions = useMemo(() => SUPPORTED_LLM_MODELS.includes(model as any), [model]);

  const handleChangeModel = (value: string) => {
    const normalized = normalizeLlmModel(value);
    setModel(normalized);
    setSettings((prev) => ({ ...prev, model: normalized }));
  };

  const importArticle = async () => {
    const selectedModel = model;
    const selectedCategory = selectedCategories[0] || 'Common';
    if (!trimmedText) {
      return;
    }
    if (trimmedText.length > ARTICLE_IMPORT_TEXT_MAX_LENGTH) {
      // 入力文字数超過時は即座にユーザーへ警告を返し、API呼び出しを抑止する。
      setMsg({ kind: 'alert', text: `文章は${ARTICLE_IMPORT_TEXT_MAX_LENGTH}文字以内で入力してください` });
      return;
    }
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoading(true);
    setMsg(null);
    setArticle(null);
    const notifId = addNotification({ title: '文章インポート中...', message: 'LLMで要約と語彙抽出を実行しています', status: 'progress', model: selectedModel });
    let acceptedJobId: string | undefined;
    let acceptedArticleId: string | undefined;
    let confirmedJobFailure = false;
    try {
      const body: any = { text: trimmedText, generation_category: selectedCategory };
      body.model = selectedModel;
      body.reasoning = { effort: settings.reasoningEffort || DEFAULT_REASONING_EFFORT };
      body.text_opts = { verbosity: settings.textVerbosity || DEFAULT_TEXT_VERBOSITY };
      const clientJobId = crypto.randomUUID();
      acceptedJobId = `article-import-job:${clientJobId}`;
      updateNotification(notifId, {
        message: 'バックグラウンド処理を受け付けています',
        jobId: acceptedJobId,
        jobType: 'article-import',
        pollingOwner: 'foreground',
      });
      let job: ArticleImportJobResponse = await createArticleImportJob(settings.apiBase, body, clientJobId, {
        signal: ctrl.signal,
        timeoutMs: settings.requestTimeoutMs,
      });
      acceptedJobId = job.job_id;
      updateNotification(notifId, {
        message: 'バックグラウンドで文章を処理しています',
        jobId: job.job_id,
        jobType: 'article-import',
        pollingOwner: 'foreground',
      });
      const deadlineMs = Date.now()
        + (settings.generationRequestTimeoutMs ?? DEFAULT_GENERATION_REQUEST_TIMEOUT_MS);
      while (job.status === 'queued' || job.status === 'running') {
        if (Date.now() >= deadlineMs) {
          throw new ApiError(
            '文章インポートが制限時間内に完了しませんでした。生成キューから状態を確認してください。',
            0,
          );
        }
        await new Promise<void>((resolve) => {
          window.setTimeout(resolve, ARTICLE_IMPORT_POLL_INTERVAL_MS);
        });
        if (ctrl.signal.aborted) {
          throw new ApiError('Request aborted or timed out', 0);
        }
        job = await fetchArticleImportJob(settings.apiBase, job.job_id, {
          signal: ctrl.signal,
          timeoutMs: settings.requestTimeoutMs,
        });
      }
      if (job.status === 'failed') {
        confirmedJobFailure = true;
        throw new ApiError(job.error || '文章インポートに失敗しました', 500);
      }
      if (!job.article_id) {
        confirmedJobFailure = true;
        throw new ApiError('文章インポート結果を確認できませんでした', 500);
      }
      acceptedArticleId = job.article_id;
      // 一覧カードと同じ導線: GET の結果のみで表示（フォールバックしない）
      const refreshed = await fetchArticleDetail(settings.apiBase, job.article_id, {
        signal: ctrl.signal,
        timeoutMs: settings.requestTimeoutMs,
      });
      setArticle(refreshed);
      setMsg({ kind: 'status', text: '文章をインポートしました' });
      updateNotification(notifId, {
        title: '文章インポート完了',
        status: 'success',
        message: '詳細を表示します',
        model: selectedModel,
        jobId: job.job_id,
        jobType: 'article-import',
        articleId: job.article_id,
        pollingOwner: null,
      });
      // グローバルに記事更新イベントを通知（一覧の自動更新用）
      dispatchAppEvent(APP_EVENTS.articleUpdated);
      setDetailOpen(true);
      try { setModalOpen(true); } catch {}
    } catch (e) {
      if (ctrl.signal.aborted) {
        if (acceptedJobId) {
          updateNotification(notifId, { pollingOwner: null });
        }
        return;
      }
      const m = e instanceof ApiError ? e.message : '文章インポートに失敗しました';
      if (acceptedJobId && !confirmedJobFailure) {
        setMsg({
          kind: 'status',
          text: '文章インポートはバックグラウンドで継続しています。生成キューから状態を確認してください。',
        });
        updateNotification(notifId, {
          title: '文章インポートの状態を確認中',
          status: 'progress',
          message: '一時的に状態を取得できませんでした。自動で再確認します。',
          model: selectedModel,
          jobId: acceptedJobId,
          jobType: 'article-import',
          articleId: acceptedArticleId,
          pollingOwner: null,
        });
      } else {
        setMsg({ kind: 'alert', text: m });
        updateNotification(notifId, {
          title: '文章インポート失敗',
          status: 'error',
          message: m,
          model: selectedModel,
        });
      }
    } finally {
      setLoading(false);
    }
  };

  const toggleCategory = (nextCategory: ExampleCategory, checked: boolean) => {
    setSelectedCategories((prev) => {
      if (!checked) {
        return prev.filter((categoryName) => categoryName !== nextCategory);
      }
      return [nextCategory, ...prev.filter((categoryName) => categoryName !== nextCategory)];
    });
  };

  const toggleAllCategories = (checked: boolean) => {
    setSelectedCategories(checked ? [...EXAMPLE_CATEGORIES] : []);
  };

  const generateAndImport = async () => {
    const categories = [...selectedCategories];
    if (categories.length === 0) {
      setMsg({ kind: 'alert', text: 'カテゴリを選択してください' });
      return;
    }
    const selectedModel = model;
    setMsg(null);
    setArticle(null);
    setGenRunning((n) => n + categories.length);

    const results = await Promise.allSettled(
      categories.map(async (selectedCategory) => {
        const notifId = addNotification({ title: `【${selectedCategory}】の例文生成・記事化を開始します`, message: '関連語を選定し、例文を生成して記事化します', status: 'progress', model: selectedModel, category: selectedCategory });
        let acceptedJobId: string | undefined;
        let confirmedJobFailure = false;
        try {
          const reqBody: any = { category: selectedCategory };
          reqBody.model = selectedModel;
          reqBody.reasoning = { effort: settings.reasoningEffort || DEFAULT_REASONING_EFFORT };
          reqBody.text = { verbosity: settings.textVerbosity || DEFAULT_TEXT_VERBOSITY };
          let job = await createCategoryGenerateImportJob(settings.apiBase, reqBody, {
            timeoutMs: settings.requestTimeoutMs,
          });
          acceptedJobId = job.job_id;
          updateNotification(notifId, {
            message: 'バックグラウンドで例文生成と記事化を続けています',
            jobId: job.job_id,
            jobType: 'category-generate-import',
            pollingOwner: 'foreground',
          });
          const deadlineMs = Date.now()
            + (settings.generationRequestTimeoutMs ?? DEFAULT_GENERATION_REQUEST_TIMEOUT_MS);
          while (job.status === 'queued' || job.status === 'running') {
            if (Date.now() >= deadlineMs) {
              throw new ApiError(
                '例文生成・記事化が制限時間内に完了しませんでした。生成キューから状態を確認してください。',
                0,
              );
            }
            await new Promise<void>((resolve) => window.setTimeout(resolve, ARTICLE_IMPORT_POLL_INTERVAL_MS));
            job = await fetchCategoryGenerateImportJob(settings.apiBase, job.job_id, {
              timeoutMs: settings.requestTimeoutMs,
            });
          }
          if (job.status === 'failed') {
            confirmedJobFailure = true;
            throw new ApiError(job.error || '例文生成・記事化に失敗しました', 500);
          }
          const result = job.result;
          const lemma = typeof result?.lemma === 'string' ? result.lemma : '';
          const wordPackId = typeof result?.word_pack_id === 'string' ? result.word_pack_id : '';
          const generatedExamples = typeof result?.generated_examples === 'number'
            ? result.generated_examples
            : 0;
          if (!lemma || !wordPackId) {
            confirmedJobFailure = true;
            throw new ApiError('例文生成・記事化の結果を確認できませんでした', 500);
          }
          const resultCategory = typeof result?.category === 'string'
            ? result.category
            : selectedCategory;
          updateNotification(notifId, {
            title: '例文生成・記事化完了',
            status: 'success',
            message: `【${lemma}】${generatedExamples}件の例文から記事を作成しました`,
            model: selectedModel,
            category: resultCategory,
            wordPackId,
            lemma,
            jobId: job.job_id,
            jobType: 'category-generate-import',
            pollingOwner: null,
          });
          dispatchAppEvent(APP_EVENTS.wordPackUpdated);
          dispatchAppEvent(APP_EVENTS.articleUpdated);
          return { category: selectedCategory, result };
        } catch (e) {
          const message = e instanceof ApiError ? e.message : '例文生成・記事化に失敗しました';
          if (acceptedJobId && !confirmedJobFailure) {
            updateNotification(notifId, {
              title: '例文生成・記事化の状態を確認中',
              status: 'progress',
              message: '一時的に状態を取得できませんでした。自動で再確認します。',
              model: selectedModel,
              category: selectedCategory,
              jobId: acceptedJobId,
              jobType: 'category-generate-import',
              pollingOwner: null,
            });
            return { category: selectedCategory, pending: true as const };
          } else {
            updateNotification(notifId, { title: '例文生成・記事化失敗', status: 'error', message, model: selectedModel, category: selectedCategory });
          }
          throw { category: selectedCategory, message };
        } finally {
          setGenRunning((n) => Math.max(0, n - 1));
        }
      }),
    );

    const successCount = results.filter(
      (result) => result.status === 'fulfilled' && !('pending' in result.value),
    ).length;
    const pendingCount = results.filter(
      (result) => result.status === 'fulfilled' && 'pending' in result.value,
    ).length;
    const failures = results
      .filter((result): result is PromiseRejectedResult => result.status === 'rejected')
      .map((result) => result.reason)
      .map((reason) => {
        const categoryName = typeof reason?.category === 'string' ? reason.category : 'カテゴリ';
        const message = typeof reason?.message === 'string' ? reason.message : '失敗しました';
        return `${categoryName}: ${message}`;
      });

    if (successCount > 0) {
      dispatchAppEvent(APP_EVENTS.articleUpdated);
    }
    if (failures.length > 0) {
      const prefix = successCount > 0
        ? `${successCount}カテゴリで例文生成・記事化を実行しましたが、一部失敗しました`
        : '例文生成・記事化に失敗しました';
      setMsg({ kind: 'alert', text: `${prefix}: ${failures.join(' / ')}` });
      return;
    }
    if (pendingCount > 0) {
      const completed = successCount > 0 ? `${successCount}カテゴリは完了し、` : '';
      setMsg({
        kind: 'status',
        text: `${completed}${pendingCount}カテゴリの例文生成・記事化をバックグラウンドで継続しています。生成キューから状態を確認できます。`,
      });
      return;
    }
    setMsg({ kind: 'status', text: `${successCount}カテゴリで例文生成・記事化を実行しました` });
  };

  const regenerateWordPack = async (wordPackId: string) => {
    if (!article) return;
    const lemma = (() => {
      try { return article.related_word_packs.find((l) => l.word_pack_id === wordPackId)?.lemma || 'WordPack'; } catch { return 'WordPack'; }
    })();
    const ctrl = new AbortController();
    try {
      await regenerateWordPackRequest({
        apiBase: settings.apiBase,
        wordPackId,
        settings: {
          pronunciationEnabled: settings.pronunciationEnabled,
          regenerateScope: settings.regenerateScope,
          requestTimeoutMs: settings.requestTimeoutMs,
          generationRequestTimeoutMs: settings.generationRequestTimeoutMs,
          reasoningEffort: settings.reasoningEffort,
          textVerbosity: settings.textVerbosity,
        },
        model,
        lemma,
        notify: { add: addNotification, update: updateNotification },
        abortSignal: ctrl.signal,
        messages: {
          progress: 'WordPackを再生成しています',
          success: '再生成が完了しました',
          failure: undefined, // ApiError.message を優先
        },
      });
      const refreshed = await fetchArticleDetail(settings.apiBase, article.id);
      setArticle(refreshed);
    } catch {
      // 通知は内部で完結
    }
  };

  const deleteWordPack = async (wordPackId: string) => {
    if (!article) return;
    const lemmaLabel = (() => {
      try { return article.related_word_packs.find((l) => l.word_pack_id === wordPackId)?.lemma?.trim(); }
      catch { return undefined; }
    })();
    const confirmed = await confirmDialog(lemmaLabel || 'WordPack');
    if (!confirmed) return;
    const ctrl = new AbortController();
    setLoading(true);
    setMsg(null);
    try {
      await deleteWordPackFromArticle(settings.apiBase, wordPackId, {
        signal: ctrl.signal,
        timeoutMs: settings.requestTimeoutMs,
      });
      // 記事詳細を再取得して関連WordPack一覧を最新化
      const refreshed = await fetchArticleDetail(settings.apiBase, article.id);
      setArticle(refreshed);
      setMsg({ kind: 'status', text: 'WordPackを削除しました' });
      dispatchAppEvent(APP_EVENTS.wordPackUpdated);
    } catch (e) {
      const m = e instanceof ApiError ? e.message : 'WordPackの削除に失敗しました';
      setMsg({ kind: 'alert', text: m });
    } finally {
      setLoading(false);
    }
  };

  const renderControls = (placement: ControlPlacement) => {
    const isSidebar = placement === 'sidebar';
    const suffix = isSidebar ? 'sidebar' : 'inline';
    const fieldClass = isSidebar ? 'sidebar-field' : 'article-import-field';
    const actionsClass = isSidebar ? 'sidebar-actions' : 'article-import-actions';
    const inlineClass = isSidebar ? 'sidebar-inline' : 'article-import-inline';
    const sidebarSuffix = isSidebar ? '（サイドバー）' : '';

    return (
      <div className={isSidebar ? undefined : 'article-import-form'}>
        <div className={fieldClass}>
          <label htmlFor={`article-import-text-${suffix}`}>文章{sidebarSuffix}</label>
          {/* ゲストモードではAI利用に直結する入力をロックする */}
          <GuestLock isGuest={isGuest}>
            <textarea
              id={`article-import-text-${suffix}`}
              placeholder={isSidebar ? '文章を貼り付け（サイドバー）' : '文章を貼り付け（日本語/英語）'}
              value={text}
              onChange={(e) => setText(e.target.value)}
              disabled={loading}
              className="article-import-textarea"
            />
          </GuestLock>
          {isTextTooLong ? (
            <p role="alert" className="article-import-warning">
              文章は{ARTICLE_IMPORT_TEXT_MAX_LENGTH}文字以内で入力してください（現在 {trimmedText.length} 文字）{sidebarSuffix}
            </p>
          ) : null}
          <div className={actionsClass}>
            <GuestLock isGuest={isGuest}>
              <button
                type="button"
                onClick={importArticle}
                disabled={importDisabled}
                aria-label={isSidebar ? '文章をインポート（サイドバー）' : undefined}
              >
                文章をインポート
              </button>
            </GuestLock>
          </div>
        </div>
        <fieldset className={`${fieldClass} article-import-category-field`}>
          <legend>カテゴリ{sidebarSuffix}</legend>
          <GuestLock isGuest={isGuest}>
            <div className="article-import-category-options">
              <label>
                <input
                  type="checkbox"
                  checked={allCategoriesSelected}
                  onChange={(e) => toggleAllCategories(e.target.checked)}
                  disabled={loading || genRunning > 0}
                  aria-label={isSidebar ? 'すべて（サイドバー）' : 'すべて'}
                />
                <span>すべて</span>
              </label>
              {EXAMPLE_CATEGORIES.map((categoryName) => (
                <label key={`${suffix}-${categoryName}`}>
                  <input
                    type="checkbox"
                    checked={selectedCategories.includes(categoryName)}
                    onChange={(e) => toggleCategory(categoryName, e.target.checked)}
                    disabled={loading || genRunning > 0}
                    aria-label={isSidebar ? `${categoryName}（サイドバー）` : categoryName}
                  />
                  <span>{categoryName}</span>
                </label>
              ))}
            </div>
          </GuestLock>
        </fieldset>
        <div className={`${actionsClass} article-generated-example-actions`}>
          <GuestLock isGuest={isGuest}>
            <button
              type="button"
              onClick={generateAndImport}
              disabled={generateDisabled}
              aria-label={isSidebar ? `サイドバーの例文を生成して記事化${genRunning > 0 ? `、実行中 ${genRunning}` : ''}` : undefined}
            >
              例文を生成して記事化{genRunning > 0 ? `（実行中 ${genRunning}）` : ''}
            </button>
          </GuestLock>
        </div>
        <div className={isSidebar ? inlineClass : 'article-import-llm-controls'}>
          <div className={fieldClass}>
            <label htmlFor={`article-model-select-${suffix}`}>モデル{sidebarSuffix}</label>
            <GuestLock isGuest={isGuest}>
              <select
                id={`article-model-select-${suffix}`}
                value={model}
                onChange={(e) => handleChangeModel(e.target.value)}
                disabled={loading}
              >
                {SUPPORTED_LLM_MODELS.map((name) => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
            </GuestLock>
          </div>
          {showAdvancedModelOptions && (
            <>
              <div className={fieldClass}>
                <label htmlFor={`article-reasoning-select-${suffix}`}>reasoning.effort{sidebarSuffix}</label>
                <GuestLock isGuest={isGuest}>
                  <select
                    id={`article-reasoning-select-${suffix}`}
                    aria-label={isSidebar ? 'reasoning.effort（サイドバー）' : 'reasoning.effort'}
                    value={settings.reasoningEffort || DEFAULT_REASONING_EFFORT}
                    onChange={(e) => setSettings((prev) => ({
                      ...prev,
                      reasoningEffort: e.target.value as ReasoningEffort,
                    }))}
                    disabled={loading}
                  >
                    {SUPPORTED_REASONING_EFFORTS.map((effort) => (
                      <option key={effort} value={effort}>{effort}</option>
                    ))}
                  </select>
                </GuestLock>
              </div>
              <div className={fieldClass}>
                <label htmlFor={`article-verbosity-select-${suffix}`}>text.verbosity{sidebarSuffix}</label>
                <GuestLock isGuest={isGuest}>
                  <select
                    id={`article-verbosity-select-${suffix}`}
                    aria-label={isSidebar ? 'text.verbosity（サイドバー）' : 'text.verbosity'}
                    value={settings.textVerbosity || DEFAULT_TEXT_VERBOSITY}
                    onChange={(e) => setSettings((prev) => ({
                      ...prev,
                      textVerbosity: e.target.value as TextVerbosity,
                    }))}
                    disabled={loading}
                  >
                    {SUPPORTED_TEXT_VERBOSITIES.map((verbosity) => (
                      <option key={verbosity} value={verbosity}>{verbosity}</option>
                    ))}
                  </select>
                </GuestLock>
              </div>
            </>
          )}
        </div>
      </div>
    );
  };

  return (
    <>
      {showSidebarControls ? (
        <SidebarPortal>
          <section className="sidebar-section" aria-label="文章インポート（サイドバー）">
            <h2>文章インポート</h2>
            {renderControls('sidebar')}
          </section>
        </SidebarPortal>
      ) : null}
      <section>
        <style>{`
        .article-import-form { display: grid; gap: 0.75rem; }
        .article-import-field { display: grid; gap: 0.35rem; }
        .article-import-field label { font-weight: 600; }
        .article-import-textarea {
          width: 100%;
          min-height: 8rem;
          padding: 0.65rem;
          border-radius: 6px;
          border: 1px solid var(--color-border);
          background: var(--color-surface);
          color: inherit;
          resize: vertical;
        }
        .article-import-actions {
          display: flex;
          align-items: end;
          flex-wrap: wrap;
          gap: 0.75rem;
        }
        .article-import-actions > .article-import-field {
          min-width: 9rem;
        }
        .article-import-actions button,
        .article-import-field select {
          min-height: 2.25rem;
        }
        .article-generated-example-actions button {
          max-width: 100%;
          white-space: normal;
        }
        .article-import-category-field {
          border: 0;
          margin: 0;
          padding: 0;
        }
        .article-import-category-field legend {
          font-weight: 600;
          padding: 0;
        }
        .article-import-category-options {
          display: flex;
          flex-wrap: wrap;
          gap: 0.5rem 0.75rem;
        }
        .article-import-category-options label {
          display: inline-flex;
          align-items: center;
          gap: 0.35rem;
          font-weight: 500;
        }
        .article-import-inline {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
          gap: 0.75rem;
        }
        .article-import-llm-controls {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 0.75rem;
          align-items: end;
        }
        .article-import-llm-controls select {
          width: 100%;
        }
        @media (max-width: 720px) {
          .article-import-llm-controls {
            grid-template-columns: 1fr;
          }
        }
        .article-import-warning {
          color: var(--color-danger, #b00020);
          margin: 0;
        }
        .ai-wp-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 0.5rem; }
        .ai-card { border: 1px solid var(--color-border); border-radius: 6px; padding: 0.5rem; background: var(--color-surface); }
        .ai-badge { font-size: 0.75em; padding: 0.1rem 0.4rem; border-radius: 999px; border: 1px solid var(--color-border); }
      `}</style>

        {showInlineControls ? renderControls('inline') : null}
        {msg && <div role={msg.kind}>{msg.text}</div>}

      <ArticleDetailModal
        isOpen={!!article && detailOpen}
        onClose={() => { setDetailOpen(false); setWpPreviewId(null); try { setModalOpen(false); } catch {} }}
        article={article}
        title="インポート結果"
        onRegenerateWordPack={regenerateWordPack}
        previewWordPackId={wpPreviewId}
        onSelectWordPackPreview={setWpPreviewId}
        onDeleteWordPack={deleteWordPack}
        onWordPackGenerated={async () => {
          // 詳細で再生成などがあったら記事詳細を更新
          if (article) {
            const refreshed = await fetchArticleDetail(settings.apiBase, article.id);
            setArticle(refreshed);
          }
          dispatchAppEvent(APP_EVENTS.wordPackUpdated);
        }}
      />
      </section>
    </>
  );
};
