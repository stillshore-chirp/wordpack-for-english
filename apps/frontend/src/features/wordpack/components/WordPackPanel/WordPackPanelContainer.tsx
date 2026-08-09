import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { useSettings } from '../../../../SettingsContext';
import { useModal } from '../../../../ModalContext';
import { useConfirmDialog } from '../../../../ConfirmDialogContext';
import { useWordPack, Examples, WordPack } from '../../../../hooks/useWordPack';
import { useWordPackForm } from '../../../../hooks/useWordPackForm';
import { useNotifications } from '../../../../NotificationsContext';
import { Modal } from '../../../../components/Modal';
import { formatDateJst } from '../../../../lib/date';
import { SidebarPortal } from '../../../../components/SidebarPortal';
import { LemmaExplorerPanel } from '../../../../components/LemmaExplorer/LemmaExplorerPanel';
import { LemmaLookupResponseData, useLemmaExplorer } from '../../../../components/LemmaExplorer/useLemmaExplorer';
import { useExampleActions } from '../../../../hooks/useExampleActions';
import { OverviewSection } from '../../../../components/wordpack/OverviewSection';
import { PronunciationSection } from '../../../../components/wordpack/PronunciationSection';
import { SensesSection } from '../../../../components/wordpack/SensesSection';
import { ExamplesSection } from '../../../../components/wordpack/ExamplesSection';
import { useAuth } from '../../../../AuthContext';
import { GuestLock } from '../../../../components/GuestLock';
import { validateLemmaInput } from '../../../../lib/lemmaValidation';
import {
  SUPPORTED_LLM_MODELS,
  SUPPORTED_REASONING_EFFORTS,
  SUPPORTED_TEXT_VERBOSITIES,
} from '../../../../lib/wordpack';
import { CitationsSection } from './CitationsSection';
import { CollocationsSection } from './CollocationsSection';
import { ConfidenceSection } from './ConfidenceSection';
import { ContrastSection } from './ContrastSection';
import { WordPackLoadingPlaceholder } from './WordPackLoadingPlaceholder';
import { WordPackLoadError } from './WordPackLoadError';
import { WordPackStatusMessage } from './WordPackStatusMessage';

export interface WordPackPreviewMeta {
  id: string;
  lemma: string;
  senseTitle?: string | null;
  created_at?: string;
  updated_at?: string;
}

interface Props {
  focusRef: React.RefObject<HTMLElement>;
  selectedWordPackId?: string | null;
  onWordPackGenerated?: (wordPackId: string | null) => void;
  selectedMeta?: { created_at: string; updated_at: string } | null;
  fallbackMeta?: Pick<WordPackPreviewMeta, 'id' | 'lemma' | 'senseTitle'> | null;
  onStudyProgressRecorded?: (payload: { wordPackId: string; checked_only_count: number; learned_count: number }) => void;
  creationPanelPlacement?: 'sidebar' | 'inline' | 'none';
  showDetails?: boolean;
  previewContext?: string | null;
  previewNotice?: React.ReactNode;
  revealStudyCardImmediately?: boolean;
  onRequestClose?: () => void;
}

/**
 * WordPack全体のパネル。データ取得/生成や各セクションへの責務分割を担い、
 * UI本体は小さなセクションコンポーネントへ委譲する。
 */
export const WordPackPanel: React.FC<Props> = ({
  focusRef,
  selectedWordPackId,
  onWordPackGenerated,
  selectedMeta,
  fallbackMeta,
  onStudyProgressRecorded,
  creationPanelPlacement = 'sidebar',
  showDetails = true,
  previewContext,
  previewNotice,
  revealStudyCardImmediately,
  onRequestClose,
}) => {
  const { isGuest } = useAuth();
  const { settings, setSettings } = useSettings();
  const { setModalOpen } = useModal();
  const { add: addNotification, update: updateNotification } = useNotifications();
  const confirmDialog = useConfirmDialog();
  const {
    apiBase,
    generationRequestTimeoutMs,
    pronunciationEnabled,
    requestTimeoutMs,
  } = settings;
  const { lemma, setLemma, lemmaValidation, model, showAdvancedModelOptions, handleChangeModel, advancedSettings } = useWordPackForm({ settings, setSettings });
  const [detailOpen, setDetailOpen] = useState(false);
  const panelInstanceId = useId();

  const {
    aiMeta,
    currentWordPackId,
    data,
    loading,
    progressUpdating,
    message,
    setStatusMessage,
    generateWordPack,
    generateDetachedWordPack,
    createEmptyWordPack,
    loadWordPack,
    regenerateWordPack,
    recordStudyProgress,
    updateGuestPublic,
  } = useWordPack({ model, onWordPackGenerated, onStudyProgressRecorded });

  const {
    explorer: lemmaExplorer,
    explorerContent,
    openLemmaExplorer: onLemmaOpen,
    openGeneratedWordPack,
    closeLemmaExplorer,
    minimizeLemmaExplorer,
    restoreLemmaExplorer,
    resizeLemmaExplorer,
    lookupLemmaMetadata,
    invalidateLemmaCache,
  } = useLemmaExplorer({ apiBase, requestTimeoutMs, onStatusMessage: setStatusMessage });

  const { examplesLoading, deleteExample, generateExamples, importArticleFromExample, copyExampleText } = useExampleActions({
    apiBase,
    requestTimeoutMs,
    generationRequestTimeoutMs,
    currentWordPackId,
    data,
    model,
    reasoningEffort: advancedSettings.reasoningEffort,
    textVerbosity: advancedSettings.textVerbosity,
    setStatusMessage,
    loadWordPack,
    notify: { add: addNotification, update: updateNotification },
    confirmDialog,
    onWordPackGenerated,
  });

  const isInModalView = Boolean(selectedWordPackId) || (Boolean(data) && detailOpen);
  const isLemmaValid = lemmaValidation.valid;
  const normalizedLemma = lemmaValidation.normalizedLemma;
  const isActionLoading = loading || examplesLoading || progressUpdating;
  const [guestPublicUpdating, setGuestPublicUpdating] = useState(false);
  const [activeSectionKey, setActiveSectionKey] = useState('overview');
  const detachedGenerationInFlightRef = useRef<Set<string>>(new Set());

  const formatDate = (dateStr?: string | null) => {
    if (!dateStr) return '-';
    return formatDateJst(dateStr);
  };

  const sectionIdPrefix = useMemo(
    () => `wp-panel-${panelInstanceId.replace(/[^a-zA-Z0-9_-]/g, '')}`,
    [panelInstanceId],
  );
  const getSectionId = useCallback(
    (key: string) => `${sectionIdPrefix}-${key}`,
    [sectionIdPrefix],
  );
  const getExampleSectionId = useCallback(
    (category: string) => getSectionId(`examples-${category}`),
    [getSectionId],
  );

  const sectionIds = useMemo(
    () => [
      { key: 'overview', id: getSectionId('overview'), label: '概要' },
      { key: 'pronunciation', id: getSectionId('pronunciation'), label: '発音' },
      { key: 'senses', id: getSectionId('senses'), label: '語義' },
      { key: 'etymology', id: getSectionId('etymology'), label: '語源' },
      { key: 'examples', id: getSectionId('examples'), label: '例文' },
      { key: 'collocations', id: getSectionId('collocations'), label: '共起' },
      { key: 'contrast', id: getSectionId('contrast'), label: '対比' },
      { key: 'citations', id: getSectionId('citations'), label: '引用' },
      { key: 'confidence', id: getSectionId('confidence'), label: '信頼度' },
    ],
    [getSectionId],
  );

  const exampleCategories = useMemo(() => (['Dev', 'CS', 'LLM', 'Business', 'Common'] as const), []);

  // モーダル表示中に本体データが未取得でも、一覧由来の最小情報で見出し語を提示する。
  const placeholderLemma = useMemo(() => {
    if (data?.lemma) return data.lemma;
    if (fallbackMeta?.lemma) return fallbackMeta.lemma;
    if (fallbackMeta?.senseTitle) return fallbackMeta.senseTitle;
    if (selectedWordPackId) return selectedWordPackId;
    return 'WordPack';
  }, [data?.lemma, fallbackMeta, selectedWordPackId]);

  useEffect(() => {
    setActiveSectionKey('overview');
  }, [selectedWordPackId, data?.lemma]);

  const exampleStats = useMemo(
    () => {
      const counts = exampleCategories.map((category) => ({
        category,
        count: data?.examples?.[category]?.length ?? 0,
      }));
      return {
        counts,
        total: counts.reduce((sum, item) => sum + item.count, 0),
      };
    },
    [data, exampleCategories],
  );

  const packCheckedCount = data?.checked_only_count ?? 0;
  const packLearnedCount = data?.learned_count ?? 0;
  const guestPublic = data?.guest_public ?? false;
  const guestPublicDisabledReason = !currentWordPackId
    ? '保存済みのWordPackのみ公開設定を切り替えできます。'
    : null;

  const triggerUnknownLemmaGeneration = useCallback(async (lemmaText: string) => {
    const validation = validateLemmaInput(lemmaText);
    const displayLemma = validation.normalizedLemma || lemmaText.trim();
    if (!validation.valid) {
      setStatusMessage({
        kind: 'alert',
        text: displayLemma
          ? `「${displayLemma}」はWordPackとして生成できません。${validation.message}`
          : validation.message,
      });
      return false;
    }
    if (isGuest) {
      setStatusMessage({
        kind: 'alert',
        text: 'ゲストモードでは例文中の未生成語をWordPack生成できません。ログインすると未生成語を追加できます。',
      });
      return false;
    }
    const lemmaToGenerate = validation.normalizedLemma;
    const inFlightKey = lemmaToGenerate.toLowerCase();
    if (detachedGenerationInFlightRef.current.has(inFlightKey)) {
      setStatusMessage({ kind: 'status', text: `${lemmaToGenerate} のWordPackを生成中です` });
      return false;
    }
    detachedGenerationInFlightRef.current.add(inFlightKey);
    try {
      const generated = await generateDetachedWordPack(lemmaToGenerate);
      if (!generated) return false;
      try {
        invalidateLemmaCache(lemmaToGenerate);
      } catch {}
      openGeneratedWordPack(generated.wordPack, generated.wordPackId);
      return true;
    } finally {
      detachedGenerationInFlightRef.current.delete(inFlightKey);
    }
  }, [generateDetachedWordPack, invalidateLemmaCache, isGuest, openGeneratedWordPack, setStatusMessage]);

  const handleGenerate = useCallback(async () => {
    if (!lemmaValidation.valid) {
      setStatusMessage({ kind: 'alert', text: lemmaValidation.message });
      return;
    }
    setLemma('');
    try { focusRef.current?.focus(); } catch {}
    await generateWordPack(normalizedLemma);
  }, [focusRef, generateWordPack, lemmaValidation, normalizedLemma, setLemma, setStatusMessage]);

  const handleCreateEmpty = useCallback(async () => {
    if (!lemmaValidation.valid) {
      setStatusMessage({ kind: 'alert', text: lemmaValidation.message });
      return;
    }
    await createEmptyWordPack(normalizedLemma);
  }, [createEmptyWordPack, lemmaValidation, normalizedLemma, setStatusMessage]);

  const handleLoadWordPack = useCallback(
    async (wordPackId: string) => {
      await loadWordPack(wordPackId);
    },
    [loadWordPack],
  );

  const handleRegenerateWordPack = useCallback(async () => {
    if (!currentWordPackId) return;
    await regenerateWordPack(currentWordPackId, data?.lemma || 'WordPack');
  }, [currentWordPackId, data?.lemma, regenerateWordPack]);

  const handleGenerateExamples = useCallback(
    async (category: keyof Examples) => {
      await generateExamples(category);
    },
    [generateExamples],
  );

  const handleGuestPublicChange = useCallback(
    async (nextValue: boolean) => {
      if (!currentWordPackId) {
        setStatusMessage({ kind: 'alert', text: '保存済みのWordPackのみ公開設定を切り替えできます。' });
        return;
      }
      // なぜ: 画面上で即時にON/OFFを反映し、ゲスト公開フローの作業負担を減らすため。
      setGuestPublicUpdating(true);
      try {
        await updateGuestPublic(currentWordPackId, nextValue);
      } finally {
        setGuestPublicUpdating(false);
      }
    },
    [currentWordPackId, setStatusMessage, updateGuestPublic],
  );

  useEffect(() => {
    if (!selectedWordPackId || selectedWordPackId === currentWordPackId) return;
    handleLoadWordPack(selectedWordPackId);
  }, [currentWordPackId, handleLoadWordPack, selectedWordPackId]);

  const canShowDetails = showDetails;

  const detailsContent = canShowDetails && data ? (
    <>
      {previewNotice ? (
        <div className="wp-preview-notice" role="status">
          {previewNotice}
        </div>
      ) : null}
      {previewContext ? (
        <p className="wp-preview-context">{previewContext}</p>
      ) : null}
      <div className="wp-container">
      {/* セクションナビゲーション: 画面内リンクで各要素へショートカット */}
      <nav className="wp-nav" aria-label="セクション">
        {sectionIds.map((s) => (
          <a
            key={s.key}
            href={`#${s.id}`}
            aria-current={activeSectionKey === s.key ? 'location' : undefined}
            onClick={() => setActiveSectionKey(s.key)}
          >
            {s.label}
          </a>
        ))}
        {exampleCategories.map((category) => (
          <a
            key={`examples-${category}`}
            href={`#${getExampleSectionId(category)}`}
            aria-current={activeSectionKey === `examples-${category}` ? 'location' : undefined}
            onClick={(e) => {
              e.preventDefault();
              setActiveSectionKey(`examples-${category}`);
              document.getElementById(getExampleSectionId(category))?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }}
          >例文: {category}</a>
        ))}
      </nav>

      <div>
        <OverviewSection
          data={data}
          selectedMeta={selectedMeta}
          aiMeta={aiMeta}
          exampleStats={exampleStats}
          currentWordPackId={currentWordPackId}
          isActionLoading={isActionLoading}
          packCheckedCount={packCheckedCount}
          packLearnedCount={packLearnedCount}
          guestPublic={guestPublic}
          guestPublicUpdating={guestPublicUpdating}
          guestPublicDisabledReason={guestPublicDisabledReason}
          onGuestPublicChange={handleGuestPublicChange}
          onRecordStudyProgress={recordStudyProgress}
          onRegenerate={handleRegenerateWordPack}
          formatDate={formatDate}
          showTtsButton={isInModalView}
          sectionId={getSectionId('overview')}
          revealStudyCardImmediately={revealStudyCardImmediately ?? false}
        />

        {pronunciationEnabled ? <PronunciationSection pronunciation={data.pronunciation} sectionId={getSectionId('pronunciation')} /> : null}
        <SensesSection senses={data.senses} sectionId={getSectionId('senses')} />

        <section id={getSectionId('etymology')} className="wp-section">
          <h3>語源</h3>
          <p>{data.etymology?.note || '-'}</p>
          <p>確度: {data.etymology?.confidence}</p>
        </section>

        <ExamplesSection
          data={data}
          currentWordPackId={currentWordPackId}
          isActionLoading={isActionLoading}
          onGenerateExamples={handleGenerateExamples}
          onDeleteExample={deleteExample}
          onImportArticleFromExample={importArticleFromExample}
          onCopyExampleText={copyExampleText}
          onLemmaOpen={onLemmaOpen}
          lookupLemmaMetadata={lookupLemmaMetadata as (lemmaText: string) => Promise<LemmaLookupResponseData>}
          triggerUnknownLemmaGeneration={triggerUnknownLemmaGeneration}
          sectionId={getSectionId('examples')}
          getCategorySectionId={getExampleSectionId}
        />

        <CollocationsSection collocations={data.collocations} onSelectLemma={setLemma} sectionId={getSectionId('collocations')} />
        <ContrastSection contrast={data.contrast} onSelectLemma={setLemma} sectionId={getSectionId('contrast')} />
        <CitationsSection citations={data.citations} sectionId={getSectionId('citations')} />
        <ConfidenceSection confidence={data.confidence} sectionId={getSectionId('confidence')} />
      </div>
    </div>
    </>
  ) : null;

  const loadError = canShowDetails && selectedWordPackId && !data && !loading && message?.kind === 'alert'
    ? message
    : null;
  const loadingPlaceholder = canShowDetails && selectedWordPackId && !data ? (
    <WordPackLoadingPlaceholder placeholderLemma={placeholderLemma} />
  ) : null;
  const loadErrorContent = loadError && selectedWordPackId ? (
    <WordPackLoadError
      placeholderLemma={placeholderLemma}
      message={loadError.text}
      onRetry={() => {
        setStatusMessage(null);
        void handleLoadWordPack(selectedWordPackId);
      }}
      onClose={onRequestClose}
    />
  ) : null;

  const creationPanel = !isInModalView && creationPanelPlacement !== 'none' ? (
    <section className="wordpack-create-panel" aria-label="新しいWordPackを作成">
      <div className="wordpack-create-panel__header">
        <h2>{creationPanelPlacement === 'inline' ? '新しいWordPackを作成' : 'WordPack生成'}</h2>
        <span className="wordpack-create-panel__badge" aria-label={`使用モデル ${model}`}>{model}</span>
      </div>
      <div className="sidebar-field wordpack-create-panel__field">
        <label htmlFor="wordpack-lemma-input">見出し語</label>
        {/* ゲストモードではAI生成に関わる入力をロックし、理由をツールチップで提示する */}
        <GuestLock isGuest={isGuest}>
          <input
            id="wordpack-lemma-input"
            ref={focusRef as React.RefObject<HTMLInputElement>}
            value={lemma}
            onChange={(e) => setLemma(e.target.value)}
            aria-describedby="wordpack-lemma-help"
            aria-invalid={isLemmaValid ? undefined : true}
            placeholder="見出し語を入力（英数字・ハイフン・アポストロフィ・半角スペースのみ）"
            disabled={isActionLoading}
          />
        </GuestLock>
        <p
          id="wordpack-lemma-help"
          aria-live="polite"
          className={`sidebar-help wordpack-create-panel__help${isLemmaValid ? '' : ' is-invalid'}`}
        >
          {isLemmaValid ? '見出し語を入力すると作成できます' : lemmaValidation.message}
        </p>
      </div>
      <div className="sidebar-actions wordpack-create-panel__actions">
        <GuestLock isGuest={isGuest}>
          <button
            type="button"
            className="wordpack-create-panel__primary"
            onClick={handleGenerate}
            disabled={!isLemmaValid || isActionLoading}
          >
            作成を開始
          </button>
        </GuestLock>
        <GuestLock isGuest={isGuest}>
          <button
            type="button"
            className="wordpack-create-panel__secondary"
            onClick={handleCreateEmpty}
            disabled={!isLemmaValid || isActionLoading}
            title="内容の生成を行わず、空のWordPackのみ保存"
          >
            WordPackのみ作成
          </button>
        </GuestLock>
      </div>
      <div className="sidebar-field wordpack-create-panel__field">
        <label htmlFor="wordpack-model-select">モデル</label>
        <GuestLock isGuest={isGuest}>
          <select
            id="wordpack-model-select"
            value={model}
            onChange={(e) => handleChangeModel(e.target.value)}
            disabled={isActionLoading}
          >
            {SUPPORTED_LLM_MODELS.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </GuestLock>
      </div>
      {showAdvancedModelOptions && (
        <div className="sidebar-inline wordpack-create-panel__advanced">
          <div className="sidebar-field wordpack-create-panel__field">
            <label htmlFor="wordpack-reasoning-select">reasoning.effort</label>
            <GuestLock isGuest={isGuest}>
              <select
                id="wordpack-reasoning-select"
                aria-label="reasoning.effort"
                value={advancedSettings.reasoningEffort}
                onChange={(e) => advancedSettings.handleChangeReasoningEffort(e.target.value as typeof advancedSettings.reasoningEffort)}
                disabled={isActionLoading}
              >
                {SUPPORTED_REASONING_EFFORTS.map((effort) => (
                  <option key={effort} value={effort}>{effort}</option>
                ))}
              </select>
            </GuestLock>
          </div>
          <div className="sidebar-field wordpack-create-panel__field">
            <label htmlFor="wordpack-verbosity-select">text.verbosity</label>
            <GuestLock isGuest={isGuest}>
              <select
                id="wordpack-verbosity-select"
                aria-label="text.verbosity"
                value={advancedSettings.textVerbosity}
                onChange={(e) => advancedSettings.handleChangeTextVerbosity(e.target.value as typeof advancedSettings.textVerbosity)}
                disabled={isActionLoading}
              >
                {SUPPORTED_TEXT_VERBOSITIES.map((verbosity) => (
                  <option key={verbosity} value={verbosity}>{verbosity}</option>
                ))}
              </select>
            </GuestLock>
          </div>
        </div>
      )}
    </section>
  ) : null;

  return (
    <>
      {/* 生成フォーム: Lexiconでは右レール、その他では従来どおりサイドバーへ描画する */}
      {creationPanelPlacement === 'sidebar' && creationPanel ? (
        <SidebarPortal>{creationPanel}</SidebarPortal>
      ) : creationPanel}

      <section>
        <style>{`
        .wp-container { display: grid; grid-template-columns: minmax(80px, 100px) 1fr; gap: 1rem; }
        .wp-nav { position: sticky; top: 0; align-self: start; display: flex; flex-direction: column; gap: 0.25rem; }
        .wp-nav a { text-decoration: none; color: var(--color-link); font-size: 0.88rem; line-height: 1.35; padding: 0.18rem 0.2rem; border-radius: 4px; }
        .wp-nav a[aria-current="location"] { background: var(--color-accent-bg); color: var(--color-accent); font-weight: 700; }
        .wp-section { padding-block: 0.25rem; border-top: 1px solid var(--color-border); }
        .blurred { filter: blur(6px); pointer-events: none; user-select: none; }
        .selfcheck { position: relative; border: 1px dashed var(--color-border); padding: 0.5rem; border-radius: 6px; }
        .selfcheck-overlay { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: var(--color-overlay-bg); cursor: pointer; font-weight: bold; border: 0; color: inherit; border-radius: 6px; min-height: 2.75rem; }
        .kv { display: grid; grid-template-columns: 10rem 1fr; row-gap: 0.25rem; }
        .wp-modal-lemma { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
        .wp-modal-tts-btn { font-size: 0.85rem; padding: 0.2rem 0.5rem; border-radius: 4px; }
        .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }
        .wp-citation-meta { white-space: pre-wrap; }
        .wp-loading-title { font-size: 1.4em; margin-bottom: 0.5rem; }
        .wp-loading-field { max-width: 30rem; }
        .wp-loading-note { margin-top: 0.4rem; }
        .wp-status-message { overflow-wrap: anywhere; word-break: break-word; }
        .wp-load-error { border-color: var(--color-danger, #b00020); }
        .wp-load-error__message { font-weight: 600; overflow-wrap: anywhere; }
        .wp-load-error__note { color: var(--color-subtle); }
        .wp-load-error__actions { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.75rem; }
        .wp-load-error__actions button { min-height: 2.25rem; padding: 0.35rem 0.8rem; }
        .wp-preview-notice { margin: 0 0 0.75rem; padding: 0.75rem; border: 1px solid var(--color-accent); background: var(--color-accent-bg); border-radius: 6px; }
        .wp-preview-context { margin: 0 0 0.75rem; color: var(--color-subtle); }
        @media (max-width: 840px) { .wp-container { grid-template-columns: 1fr; } }
      `}</style>

        {!isInModalView && <div style={{ marginBottom: '0.75rem' }} />}

        <WordPackStatusMessage message={loadError ? null : message} />

        {canShowDetails ? (
          <>
            {/* 詳細表示: モーダル/ダイレクト表示の両対応 */}
            {selectedWordPackId ? (
              data ? detailsContent : loadErrorContent ?? loadingPlaceholder
            ) : (
              <Modal
                isOpen={!!data && detailOpen}
                onClose={() => { setDetailOpen(false); try { setModalOpen(false); } catch {} }}
                title={`WordPack プレビュー: ${data?.lemma ?? 'WordPack'}`}
                closeLabel="WordPackプレビューを閉じる"
                allowWideView
              >
                {detailsContent}
              </Modal>
            )}
          </>
        ) : null}
      </section>

      {lemmaExplorer ? (
        <LemmaExplorerPanel
          explorer={lemmaExplorer}
          content={explorerContent}
          onClose={closeLemmaExplorer}
          onMinimize={minimizeLemmaExplorer}
          onRestore={restoreLemmaExplorer}
          onResize={resizeLemmaExplorer}
        />
      ) : null}
    </>
  );
};
