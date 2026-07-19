import React, { useMemo, useState } from 'react';
import { useAuth } from '../../AuthContext';
import { AppRightRail, RailCard } from '../../components/AppRightRail';
import { GuestLock } from '../../components/GuestLock';
import { WordPackPreviewModal } from '../../components/WordPackPreviewModal';
import { ApiError } from '../../shared/api/ApiError';
import { validateLemmaInput } from '../../lib/lemmaValidation';
import { APP_EVENTS, dispatchAppEvent } from '../../shared/events/appEvents';
import {
  Badge,
  Button,
  EmptyState,
  SearchBox,
  SegmentedControl,
} from '../../shared/ui';
import {
  attachRelationStatus,
  buildExploreRelations,
  filterExploreRelations,
  type ExploreMode,
  type ExploreRelation,
} from './exploreRelations';
import { useExploreData } from './useExploreData';

const modeOptions: { value: ExploreMode; label: string }[] = [
  { value: 'related', label: '関連語' },
  { value: 'collocations', label: '共起' },
  { value: 'contrast', label: '対比' },
  { value: 'examples', label: '例文' },
  { value: 'unknown', label: '未登録のみ' },
];

const statusMeta: Record<
  ExploreRelation['status'],
  { label: string; description: string; action: string }
> = {
  existing: {
    label: '保存済み',
    description: '既にWordPackがあります',
    action: 'プレビュー',
  },
  empty: {
    label: '空のWordPack',
    description: 'WordPackはありますが、内容は未登録です',
    action: '開いて育てる',
  },
  unknown: {
    label: '未登録',
    description: '対応するWordPackはまだありません',
    action: 'WordPackを作成',
  },
};

const sourceLabel = (source: string): string => {
  const exact: Record<string, string> = {
    synonym: '類義語',
    antonym: '反義語',
    pattern: '表現パターン',
    contrast: '対比',
    Dev: 'Dev例文',
    CS: 'CS例文',
    LLM: 'LLM例文',
    Business: 'Business例文',
    Common: 'Common例文',
  };
  if (exact[source]) return exact[source];
  return source
    .replace('general', '一般共起')
    .replace('academic', '専門共起')
    .replace('verb_object', '動詞と目的語')
    .replace('adj_noun', '形容詞と名詞')
    .replace('prep_noun', '前置詞句');
};

const modeHeading = (mode: ExploreMode): string => {
  const option = modeOptions.find((item) => item.value === mode);
  return option?.label ?? '接続';
};

const relationCreateBlockReason = (
  relation: ExploreRelation,
): string | null => {
  if (relation.targetWordPack) return null;
  if (relation.kind === 'examples') {
    return '例文全体は見出し語ではないため、ここからは作成できません。文中の語をLexiconで作成してください。';
  }
  if (relation.source === 'pattern') {
    return '表現パターンは見出し語ではないため、必要な語だけをLexiconで作成してください。';
  }
  const validation = validateLemmaInput(relation.label);
  return validation.valid ? null : validation.message;
};

const relationActionLabel = (
  relation: ExploreRelation,
  isGuest: boolean,
  isCreating: boolean,
  createBlockReason: string | null,
): string => {
  if (isCreating) return '作成中';
  if (relation.targetWordPack) return statusMeta[relation.status].action;
  if (createBlockReason) return '作成不可';
  if (isGuest) return 'ログインで作成';
  return statusMeta.unknown.action;
};

export const ExplorePage: React.FC = () => {
  const { isGuest } = useAuth();
  const [mode, setMode] = useState<ExploreMode>('related');
  const [previewWordPackId, setPreviewWordPackId] = useState<string | null>(
    null,
  );
  const [previewNotice, setPreviewNotice] = useState<{
    title: string;
    body: string;
  } | null>(null);
  const [creatingRelationId, setCreatingRelationId] = useState<string | null>(
    null,
  );
  const [relationMessage, setRelationMessage] = useState<{
    kind: 'status' | 'alert';
    text: string;
  } | null>(null);
  const {
    applyStudyProgress,
    createEmptyWordPack,
    detailLoading,
    detailMessage,
    filteredWordPacks,
    loading,
    message,
    query,
    reload,
    selectedDetail,
    selectedWordPack,
    selectedWordPackId,
    setQuery,
    setSelectedWordPackId,
    total,
    wordPacks,
  } = useExploreData();

  const relations = useMemo(() => {
    if (!selectedDetail) return [];
    return attachRelationStatus(
      buildExploreRelations(selectedDetail),
      wordPacks,
      selectedDetail.lemma,
    );
  }, [selectedDetail, wordPacks]);
  const visibleRelations = useMemo(
    () => filterExploreRelations(relations, mode),
    [mode, relations],
  );
  const unknownCount = useMemo(
    () => relations.filter((relation) => relation.status === 'unknown').length,
    [relations],
  );
  const creatableUnknownCount = useMemo(
    () =>
      relations.filter(
        (relation) =>
          relation.status === 'unknown' && !relationCreateBlockReason(relation),
      ).length,
    [relations],
  );
  const emptyCount = useMemo(
    () => relations.filter((relation) => relation.status === 'empty').length,
    [relations],
  );
  const existingCount = relations.length - unknownCount - emptyCount;
  const selectedLabel = selectedWordPack?.lemma ?? '未選択';
  const previewNavigationIds = useMemo(
    () =>
      visibleRelations
        .map((relation) => relation.targetWordPack?.id)
        .filter((id): id is string => Boolean(id)),
    [visibleRelations],
  );

  const handleRelationAction = async (relation: ExploreRelation) => {
    setRelationMessage(null);
    if (relation.targetWordPack) {
      setPreviewNotice(null);
      setPreviewWordPackId(relation.targetWordPack.id);
      return;
    }

    if (isGuest) {
      setRelationMessage({
        kind: 'alert',
        text: 'ゲストモードではWordPackを作成できません。ログインすると未登録語を追加できます。',
      });
      return;
    }

    const blockedReason = relationCreateBlockReason(relation);
    if (blockedReason) {
      setRelationMessage({
        kind: 'alert',
        text: `「${relation.label}」はWordPackとして作成できません。${blockedReason}`,
      });
      return;
    }

    const validation = validateLemmaInput(relation.label);
    const lemma = validation.normalizedLemma;
    setCreatingRelationId(relation.id);
    setRelationMessage({
      kind: 'status',
      text: `「${lemma}」の空WordPackを作成しています。`,
    });
    try {
      const result = await createEmptyWordPack(lemma);
      await reload();
      dispatchAppEvent(APP_EVENTS.wordPackUpdated);
      setPreviewNotice({
        title: '空のWordPackを作成しました。',
        body: 'まだ例文はありません。プレビュー内の「追加生成」または「再生成」で内容を育てられます。',
      });
      setPreviewWordPackId(result.id);
      setRelationMessage({
        kind: 'status',
        text: `「${lemma}」の空WordPackを作成しました。プレビューで内容を育てられます。`,
      });
    } catch (error) {
      const text =
        error instanceof ApiError
          ? error.message
          : '空WordPackの作成に失敗しました';
      setRelationMessage({
        kind: 'alert',
        text: `「${lemma}」を作成できませんでした。通信状態を確認して、もう一度試してください。${text ? `（${text}）` : ''}`,
      });
    } finally {
      setCreatingRelationId(null);
    }
  };

  const renderEmptyWordPackList = () => {
    if (loading && wordPacks.length === 0) {
      return (
        <EmptyState>保存済みWordPackの一覧を読み込んでいます。</EmptyState>
      );
    }
    if (filteredWordPacks.length > 0) return null;
    if (query.trim()) {
      return (
        <EmptyState>
          {`「${query.trim()}」に一致するWordPackはありません。検索語を短くするか、一覧を更新してください。`}
        </EmptyState>
      );
    }
    return (
      <EmptyState>
        保存済みWordPackがまだありません。LexiconでWordPackを作ると、ここで関連語を探索できます。
      </EmptyState>
    );
  };

  const renderEmptyRelations = () => {
    if (detailLoading) {
      return (
        <EmptyState>
          {selectedWordPack
            ? `「${selectedWordPack.lemma}」の接続を読み込んでいます。`
            : '接続を読み込んでいます。'}
        </EmptyState>
      );
    }
    if (detailMessage) {
      return (
        <div role="alert" className="dictionary-empty">
          {detailMessage}。一覧を更新するか、別のWordPackを選んでください。
        </div>
      );
    }
    if (visibleRelations.length > 0) return null;
    if (!selectedWordPackId) {
      return (
        <EmptyState>
          左の一覧からWordPackを選ぶと、関連語・共起・対比・例文の接続を表示します。
        </EmptyState>
      );
    }
    if (mode === 'unknown') {
      return (
        <EmptyState>
          このWordPackに未登録の接続はありません。他の分類を見るか、別のWordPackを選んでください。
        </EmptyState>
      );
    }
    return (
      <EmptyState>
        {`「${modeHeading(mode)}」に表示できる接続はまだありません。別の分類を確認できます。`}
      </EmptyState>
    );
  };

  return (
    <div className="dictionary-main">
      <div className="dictionary-workspace explore-workspace">
        <div className="dictionary-primary">
          <div className="dictionary-page-heading">
            <div className="dictionary-page-title">
              <h2>Explore</h2>
              <p>
                保存済みWordPackのつながりを見つけ、未登録の語を追加できます。
              </p>
            </div>
            <div className="dictionary-top-actions">
              <SearchBox
                label="探索するWordPackを検索"
                placeholder="lemma や語義で検索"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
              <Button
                variant="default"
                onClick={() => {
                  void reload();
                }}
                disabled={loading}
              >
                {loading ? '更新中' : '更新'}
              </Button>
            </div>
          </div>
          <section className="dictionary-section explore-browser">
            <div className="dictionary-section-header explore-toolbar">
              <SegmentedControl<ExploreMode>
                label="接続の分類"
                value={mode}
                onChange={setMode}
                options={modeOptions}
              />
              <div
                className="explore-status-guide"
                aria-label="ステータスの意味"
              >
                <span className="explore-status-title">ステータスの意味</span>
                {(
                  [
                    'existing',
                    'empty',
                    'unknown',
                  ] as ExploreRelation['status'][]
                ).map((status) => (
                  <span key={status} className="explore-status-explain">
                    <Badge className={`explore-status-badge ${status}`}>
                      {statusMeta[status].label}
                    </Badge>
                    <span>{statusMeta[status].description}</span>
                  </span>
                ))}
              </div>
            </div>
            {relationMessage ? (
              <div
                className={`explore-feedback ${relationMessage.kind}`}
                role={relationMessage.kind === 'alert' ? 'alert' : 'status'}
              >
                {relationMessage.text}
              </div>
            ) : null}
            <div className="explore-layout">
              <section
                className="explore-column"
                aria-labelledby="explore-wordpack-heading"
              >
                <div className="explore-column-heading">
                  <div>
                    <h3 id="explore-wordpack-heading">WordPackを選ぶ</h3>
                    <p>{total}件から接続元を選びます。</p>
                  </div>
                  <Badge>{filteredWordPacks.length}件</Badge>
                </div>
                <div className="explore-list" aria-label="探索候補">
                  {message ? (
                    <div role="alert" className="dictionary-empty compact">
                      {message.text}
                    </div>
                  ) : null}
                  {!message ? renderEmptyWordPackList() : null}
                  {filteredWordPacks.map((wordPack) => (
                    <button
                      key={wordPack.id}
                      type="button"
                      className="explore-list-item"
                      aria-pressed={selectedWordPackId === wordPack.id}
                      aria-label={`${wordPack.lemma} を接続元に選ぶ`}
                      onClick={() => setSelectedWordPackId(wordPack.id)}
                    >
                      <span>
                        <strong>{wordPack.lemma}</strong>
                        <span>
                          {wordPack.sense_title || '語義タイトル未設定'}
                        </span>
                      </span>
                      <span aria-hidden="true" className="explore-list-arrow">
                        ›
                      </span>
                    </button>
                  ))}
                </div>
              </section>
              <section
                className="explore-column"
                aria-labelledby="explore-relations-heading"
              >
                <div className="explore-column-heading">
                  <div>
                    <h3 id="explore-relations-heading">
                      {selectedLabel} から見つかった{modeHeading(mode)}
                    </h3>
                    <p>
                      保存済みはプレビュー可能。未登録のうち見出し語として扱える候補だけ作成できます。
                    </p>
                  </div>
                  <Badge>{visibleRelations.length}件</Badge>
                </div>
                <div className="explore-connections" aria-label="接続カード">
                  {renderEmptyRelations()}
                  {!detailLoading &&
                    !detailMessage &&
                    visibleRelations.map((relation) => {
                      const createBlockReason =
                        relation.status === 'unknown'
                          ? relationCreateBlockReason(relation)
                          : null;
                      const guestCreateBlocked =
                        relation.status === 'unknown' &&
                        isGuest &&
                        !createBlockReason;
                      const isCreating = creatingRelationId === relation.id;
                      const actionDisabled =
                        isCreating ||
                        Boolean(createBlockReason) ||
                        guestCreateBlocked;
                      const actionHint =
                        createBlockReason ||
                        (guestCreateBlocked
                          ? 'ゲストモードではWordPackを作成できません。ログインすると未登録語を追加できます。'
                          : null);
                      const actionHintId = actionHint
                        ? `explore-action-hint-${relation.id}`
                        : undefined;
                      const actionAriaLabel = relation.targetWordPack
                        ? `「${relation.label}」のWordPackを開く`
                        : createBlockReason
                          ? `「${relation.label}」はWordPackとして作成できません`
                          : guestCreateBlocked
                            ? `「${relation.label}」はログインするとWordPackを作成できます`
                            : `「${relation.label}」のWordPackを作成`;
                      const actionButton = (
                        <Button
                          variant={
                            relation.status === 'unknown' && !actionDisabled
                              ? 'primary'
                              : 'default'
                          }
                          disabled={actionDisabled}
                          aria-describedby={actionHintId}
                          aria-label={actionAriaLabel}
                          onClick={() => {
                            void handleRelationAction(relation);
                          }}
                        >
                          {relationActionLabel(
                            relation,
                            isGuest,
                            isCreating,
                            createBlockReason,
                          )}
                        </Button>
                      );
                      return (
                        <article
                          key={relation.id}
                          className="explore-connection-card"
                        >
                          <div>
                            <div className="dictionary-meta-row">
                              <Badge>{sourceLabel(relation.source)}</Badge>
                              <Badge
                                className={`explore-status-badge ${relation.status}`}
                              >
                                {statusMeta[relation.status].label}
                              </Badge>
                            </div>
                            <h3>{relation.label}</h3>
                            {relation.description ? (
                              <p>{relation.description}</p>
                            ) : null}
                          </div>
                          <div className="explore-card-action">
                            {guestCreateBlocked ? (
                              <GuestLock isGuest>{actionButton}</GuestLock>
                            ) : (
                              actionButton
                            )}
                            {actionHint ? (
                              <p
                                id={actionHintId}
                                className="explore-action-hint"
                              >
                                {actionHint}
                              </p>
                            ) : null}
                          </div>
                        </article>
                      );
                    })}
                </div>
              </section>
              <section
                className="explore-side"
                aria-label="選択中WordPackの概要"
              >
                <div>
                  <Badge variant="accent">
                    {selectedWordPack?.lemma ?? '未選択'}
                  </Badge>
                  <h3>{selectedWordPack?.lemma ?? 'WordPack未選択'}</h3>
                  <p>
                    {selectedWordPack?.sense_title ||
                      'WordPackを選ぶと接続を表示します。'}
                  </p>
                </div>
                <div className="explore-metrics" aria-label="接続の集計">
                  <div className="explore-metric">
                    <strong>{relations.length}</strong>
                    <span>件のつながり</span>
                    <p>このWordPackから見つかった接続の総数</p>
                  </div>
                  <div className="explore-metric pending">
                    <strong>{unknownCount}</strong>
                    <span>件が未登録</span>
                    <p>
                      {isGuest
                        ? 'ログインすると追加できます'
                        : `作成可能な候補は${creatableUnknownCount}件`}
                    </p>
                  </div>
                </div>
                <Button
                  variant="primary"
                  disabled={!selectedWordPackId}
                  onClick={() => {
                    setPreviewNotice(null);
                    setPreviewWordPackId(selectedWordPackId);
                  }}
                >
                  このWordPackを開く
                </Button>
                {!selectedWordPackId ? (
                  <p className="explore-disabled-hint">
                    先に左の一覧からWordPackを選んでください。
                  </p>
                ) : null}
                <div className="explore-guidance">
                  見出し語として扱える未登録語を作ると、関連語ネットワークを広げられます。
                </div>
                <div
                  className="explore-quick-actions"
                  aria-label="クイックアクション"
                >
                  <h4>クイックアクション</h4>
                  <button
                    type="button"
                    aria-pressed={mode === 'unknown'}
                    onClick={() => setMode('unknown')}
                  >
                    未登録の語を表示
                  </button>
                  <button
                    type="button"
                    aria-pressed={mode === 'collocations'}
                    onClick={() => setMode('collocations')}
                  >
                    共起を確認
                  </button>
                  <button
                    type="button"
                    aria-pressed={mode === 'contrast'}
                    onClick={() => setMode('contrast')}
                  >
                    対比を確認
                  </button>
                  <button
                    type="button"
                    aria-pressed={mode === 'examples'}
                    onClick={() => setMode('examples')}
                  >
                    例文を確認
                  </button>
                </div>
                <div
                  className="dictionary-chip-list"
                  aria-label="ステータス別件数"
                >
                  <Badge className="explore-status-badge existing">
                    保存済み {existingCount}
                  </Badge>
                  <Badge className="explore-status-badge empty">
                    空のWordPack {emptyCount}
                  </Badge>
                  <Badge className="explore-status-badge unknown">
                    未登録 {unknownCount}
                  </Badge>
                </div>
              </section>
            </div>
          </section>
        </div>
        <AppRightRail>
          <RailCard
            title="探索サマリー"
            badge={selectedWordPack?.lemma ?? '未選択'}
          >
            <div className="dictionary-rail-metrics" aria-label="探索サマリー">
              <span>
                <strong>{relations.length}</strong>接続
              </span>
              <span>
                <strong>{unknownCount}</strong>未登録
              </span>
            </div>
            <p className="dictionary-rail-copy">
              未登録語の作成、用例生成、再生成は画面を移動しても同じキューで追跡できます。
            </p>
          </RailCard>
        </AppRightRail>
      </div>
      <WordPackPreviewModal
        isOpen={Boolean(previewWordPackId)}
        onClose={() => {
          setPreviewWordPackId(null);
          setPreviewNotice(null);
        }}
        wordPackId={previewWordPackId}
        wordPacks={wordPacks}
        contextLabel="Explore から開いた WordPack"
        contextDescription={
          selectedWordPack
            ? `Exploreで「${selectedWordPack.lemma}」から見つかった接続を開いています。`
            : 'Exploreの接続一覧から開いています。'
        }
        notice={
          previewNotice ? (
            <div>
              <strong>{previewNotice.title}</strong>
              <p style={{ margin: '0.35rem 0 0' }}>{previewNotice.body}</p>
            </div>
          ) : null
        }
        navigationIds={previewNavigationIds}
        onNavigate={(id) => {
          setPreviewNotice(null);
          setPreviewWordPackId(id);
        }}
        onWordPackUpdated={() => {
          void reload();
        }}
        onStudyProgressRecorded={applyStudyProgress}
      />
    </div>
  );
};
