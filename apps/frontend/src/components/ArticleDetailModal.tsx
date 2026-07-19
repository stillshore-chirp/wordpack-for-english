import React, { useMemo, useRef } from 'react';
import { Modal } from './Modal';
import { calculateDurationMs, formatDateJst, formatDurationMs } from '../lib/date';
import { TTSButton } from './TTSButton';
import { useAuth } from '../AuthContext';
import { GuestLock } from './GuestLock';
import { SentencePairParagraphs, useSentencePairHighlight } from './SentencePairHighlighter';
import { WordPackPanel, type WordPackPreviewMeta } from './WordPackPanel';
import { buildSentenceAlignment, countSentencePairs } from '../lib/sentenceAlignment';

export interface ArticleWordPackLink {
  word_pack_id: string;
  lemma: string;
  status: 'existing' | 'created';
  is_empty?: boolean;
  warning?: string | null;
}

export interface ArticleDetailData {
  id: string;
  title_en: string;
  body_en: string;
  body_ja: string;
  notes_ja?: string | null;
  // 生成に使用したAI情報（任意）
  llm_model?: string | null;
  llm_params?: string | null;
  generation_category?: 'Dev' | 'CS' | 'LLM' | 'Business' | 'Common' | null;
  related_word_packs: ArticleWordPackLink[];
  warnings?: string[] | null;
  created_at?: string;
  updated_at?: string;
  generation_started_at?: string | null;
  generation_completed_at?: string | null;
  generation_duration_ms?: number | null;
  guest_public?: boolean;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  article: ArticleDetailData | null;
  title?: string;
  onRegenerateWordPack?: (wordPackId: string) => void;
  previewWordPackId?: string | null;
  onSelectWordPackPreview?: (wordPackId: string | null) => void;
  onWordPackGenerated?: () => void | Promise<void>;
  onDeleteWordPack?: (wordPackId: string) => void;
}

export const ArticleDetailModal: React.FC<Props> = ({
  isOpen,
  onClose,
  article,
  title = '文章詳細',
  onRegenerateWordPack,
  previewWordPackId,
  onSelectWordPackPreview,
  onWordPackGenerated,
  onDeleteWordPack,
}) => {
  const { isGuest } = useAuth();
  const wordPackPreviewFocusRef = useRef<HTMLElement>(null);
  const articleAlignment = useMemo(
    () => buildSentenceAlignment(article?.body_en ?? '', article?.body_ja ?? ''),
    [article?.body_en, article?.body_ja],
  );
  const articleHighlightKey = article ? `${article.id}:${article.body_en}:${article.body_ja}` : null;
  const articleSentenceHighlight = useSentencePairHighlight(
    Boolean(article?.body_ja?.trim()) && countSentencePairs(articleAlignment) > 1,
    articleHighlightKey,
  );
  const formatDateWithFallback = (value?: string | null) => {
    if (!value) return null;
    const formatted = formatDateJst(value);
    return formatted && formatted.trim() ? formatted : value;
  };

  const generationDuration = React.useMemo(() => {
    if (!article) return null;
    const durationValue = article.generation_duration_ms;
    const hasDbDuration = typeof durationValue === 'number' && Number.isFinite(durationValue);
    if (hasDbDuration) {
      const label = formatDurationMs(durationValue as number);
      if (label && label.trim()) return label;
      if ((durationValue as number) === 0) return '0秒';
    }
    const start = article.generation_started_at || article.created_at;
    const end = article.generation_completed_at || article.updated_at;
    if (!start || !end) return null;
    const diff = calculateDurationMs(start, end);
    if (diff === null) return null;
    const label = formatDurationMs(diff);
    if (label && label.trim()) return label;
    // フォールバック計算で 0ms 相当になった場合は「計測不可」とする（DB未記録時のみ）
    if (diff === 0 && !hasDbDuration) return '計測不可';
    if (diff === 0) return '0秒';
    return null;
  }, [article]);

  const metaRows = useMemo(() => {
    if (!article) return [] as { label: string; value: string }[];
    const rows: { label: string; value: string }[] = [];
    const created = formatDateWithFallback(article.generation_started_at || article.created_at) ?? '未記録';
    const updated = formatDateWithFallback(article.generation_completed_at || article.updated_at) ?? '未記録';
    const durationLabel = generationDuration || '計測不可';
    const categoryMap: Record<'Dev' | 'CS' | 'LLM' | 'Business' | 'Common', string> = {
      Dev: 'Dev（開発）',
      CS: 'CS（コンピュータサイエンス）',
      LLM: 'LLM（大規模言語モデル）',
      Business: 'Business（ビジネス）',
      Common: 'Common（日常）',
    };
    const rawCategory = (article.generation_category || '').trim();
    const categoryLabel = rawCategory ? (categoryMap[rawCategory as keyof typeof categoryMap] || rawCategory) : '';
    const modelLabel = (article.llm_model || '').trim() || '未記録';
    const paramsLabel = (article.llm_params || '').trim() || '未記録';

    rows.push({ label: '作成', value: created });
    rows.push({ label: '更新', value: updated });
    rows.push({ label: '生成所要時間', value: durationLabel });
    rows.push({ label: '生成カテゴリ', value: (categoryLabel || '未指定') });
    rows.push({ label: 'AIモデル', value: modelLabel });
    rows.push({ label: 'AIパラメータ', value: paramsLabel });
    return rows;
  }, [article, generationDuration]);
  const previewWordPack = useMemo(
    () => article?.related_word_packs.find((link) => link.word_pack_id === previewWordPackId) ?? null,
    [article?.related_word_packs, previewWordPackId],
  );
  const previewMeta = useMemo<Pick<WordPackPreviewMeta, 'id' | 'lemma' | 'senseTitle'> | null>(() => {
    if (!previewWordPack) return null;
    return {
      id: previewWordPack.word_pack_id,
      lemma: previewWordPack.lemma,
      senseTitle: previewWordPack.is_empty ? '例文未生成' : null,
    };
  }, [previewWordPack]);

  return (
    <Modal
      isOpen={!!article && isOpen}
      onClose={onClose}
      title={title}
      closeLabel={`${title}を閉じる`}
    >
      {article ? (
        <div>
          <style>{`
            .ai-wp-grid {
              display: grid;
              grid-template-columns: 1fr;
              gap: 0.35rem;
            }
            .ai-meta-grid {
              display: grid;
              grid-template-columns: minmax(6rem, 0.45fr) 1fr;
              column-gap: 0.75rem;
              row-gap: 0.35rem;
              font-size: 0.75em;
              color: var(--color-subtle);
              margin-top: 0.75rem;
              font-variant-numeric: tabular-nums;
            }
            .ai-meta-grid dt {
              font-weight: 600;
            }
            .ai-meta-grid dd {
              margin: 0;
              white-space: pre-wrap;
              word-break: break-word;
            }
            .article-reader {
              display: grid;
              gap: 0.9rem;
              max-width: 56rem;
            }
            .article-reader__header {
              display: flex;
              gap: 0.75rem;
              align-items: flex-start;
              justify-content: space-between;
              flex-wrap: wrap;
            }
            .article-reader__header h3 {
              margin: 0;
              flex: 1 1 24rem;
              line-height: 1.25;
            }
            .article-text-block {
              display: grid;
              gap: 0.35rem;
              max-width: 48rem;
            }
            .article-text-block h4 {
              margin: 0;
              font-size: 0.95rem;
              color: var(--color-subtle);
            }
            .article-text-body {
              display: grid;
              gap: 0.65rem;
            }
            .article-text-block p,
            .article-text-paragraph {
              margin: 0;
              white-space: pre-wrap;
              line-height: 1.65;
              overflow-wrap: anywhere;
            }
            .article-notes {
              border-left: 3px solid var(--color-border);
              padding-left: 0.75rem;
              color: var(--color-subtle);
            }
            .article-detail-summary {
              margin-top: 0.9rem;
              border-top: 1px solid var(--color-border);
              padding-top: 0.75rem;
            }
            .article-detail-summary summary {
              cursor: pointer;
              font-weight: 600;
            }
            .article-related-empty {
              margin: 0.25rem 0 0;
              color: var(--color-subtle);
              line-height: 1.6;
            }
            @media (max-width: 480px) {
              .ai-meta-grid {
                grid-template-columns: minmax(5rem, 0.55fr) 1fr;
              }
            }
            @media (min-width: 480px) {
              .ai-wp-grid {
                grid-template-columns: repeat(2, 1fr);
              }
            }
            @media (min-width: 768px) {
              .ai-wp-grid { 
                grid-template-columns: repeat(3, 1fr); 
              }
            }
            .ai-card { border: 1px solid var(--color-border); border-radius: 4px; padding: 0.35rem; background: var(--color-surface); }
            .ai-badge { font-size: 0.68em; padding: 0.06rem 0.3rem; border-radius: 999px; border: 1px solid var(--color-border); }
            .ai-warnings { border: 1px solid #d6a31a; background: #fff8e1; color: #4d3600; padding: 0.5rem; border-radius: 4px; }
            .ai-warnings strong,
            .ai-warnings li { color: #4d3600; }
            .ai-warnings ul { margin: 0.25rem 0 0 1.2rem; padding: 0; }
            .ai-wp-preview-button {
              border: 0;
              background: transparent;
              color: var(--color-link);
              padding: 0;
              text-align: left;
              cursor: pointer;
              text-decoration: underline;
              font: inherit;
              flex: 1 0 100%;
            }
            .ai-wp-preview-button strong {
              font-size: 0.9rem;
            }
            .ai-wp-card-header {
              display: flex;
              align-items: center;
              gap: 0.35rem;
              flex-wrap: wrap;
            }
            .article-wordpack-preview {
              margin-top: 0.9rem;
              border: 1px solid var(--color-border);
              border-radius: 6px;
              padding: 0.75rem;
              background: var(--color-surface);
            }
            .article-wordpack-preview__header {
              display: flex;
              justify-content: space-between;
              align-items: flex-start;
              gap: 0.75rem;
              margin-bottom: 0.75rem;
            }
            .article-wordpack-preview__header h4 {
              margin: 0;
            }
            .article-wordpack-preview__header p {
              margin: 0.25rem 0 0;
              color: var(--color-subtle);
            }
            .article-wordpack-preview__close {
              min-height: 2rem;
              padding: 0.25rem 0.7rem;
            }
          `}</style>
          <section className="article-reader" aria-label="文章の本文">
            <div className="article-reader__header">
              <h3>{article.title_en}</h3>
              <TTSButton
                text={article.body_en}
                label="音声"
                ariaLabel="記事本文の音声"
                style={{ flex: '0 0 auto' }}
              />
            </div>
            <div className="article-text-block">
              <h4>英文</h4>
              <div className="article-text-body" aria-label="英文本文">
                <SentencePairParagraphs
                  paragraphs={articleAlignment.englishParagraphs}
                  language="en"
                  highlight={articleSentenceHighlight}
                  paragraphClassName="article-text-paragraph"
                  preserveWhitespaceFrom={article.body_en}
                />
              </div>
            </div>
            <div className="article-text-block">
              <h4>日本語訳</h4>
              <div className="article-text-body" aria-label="日本語訳本文">
                <SentencePairParagraphs
                  paragraphs={articleAlignment.japaneseParagraphs}
                  language="ja"
                  highlight={articleSentenceHighlight}
                  paragraphClassName="article-text-paragraph"
                  preserveWhitespaceFrom={article.body_ja}
                />
              </div>
            </div>
            {article.notes_ja ? (
              <div className="article-text-block article-notes">
                <h4>解説の要点</h4>
                <p>{article.notes_ja}</p>
              </div>
            ) : null}
          </section>
          {article.warnings && article.warnings.length > 0 ? (
            <div className="ai-warnings" role="alert" aria-label="インポート警告">
              <strong>警告</strong>
              <ul>
                {article.warnings.map((w, idx) => (
                  <li key={`warn-${idx}`}>{w}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <section aria-labelledby="article-related-wordpacks-heading" style={{ marginTop: '1rem' }}>
            <h4 id="article-related-wordpacks-heading">関連WordPack</h4>
            {article.related_word_packs.length > 0 ? (
              <div className="ai-wp-grid">
                {article.related_word_packs.map((l) => (
                  <div key={l.word_pack_id} className="ai-card">
                    <div className="ai-wp-card-header">
                      {onSelectWordPackPreview ? (
                        <button
                          type="button"
                          className="ai-wp-preview-button"
                          onClick={() => onSelectWordPackPreview(l.word_pack_id)}
                        >
                          <strong>WordPack「{l.lemma}」をプレビュー</strong>
                        </button>
                      ) : (
                        <strong style={{ fontSize: '0.9rem' }}>{l.lemma}</strong>
                      )}
                      {l.is_empty ? (
                        <span className="ai-badge" style={{ background: '#fff3cd', borderColor: '#ffe08a', color: '#7a5b00' }}>例文未生成</span>
                      ) : null}
                      {onRegenerateWordPack ? (
                        <GuestLock isGuest={isGuest}>
                          <button onClick={() => onRegenerateWordPack(l.word_pack_id)} style={{ marginLeft: 'auto', fontSize: '0.65em', padding: '0.05rem 0.2rem', borderRadius: 3 }}>例文を生成</button>
                        </GuestLock>
                      ) : null}
                      {onDeleteWordPack ? (
                        <GuestLock isGuest={isGuest}>
                          <button
                            onClick={() => onDeleteWordPack(l.word_pack_id)}
                            aria-label={`WordPack「${l.lemma}」を関連一覧から削除`}
                            style={{ marginLeft: 4, color: '#d32f2f', border: '1px solid #d32f2f', background: 'white', padding: '0.12rem 0.35rem', borderRadius: 3, fontSize: '0.78rem' }}
                          >
                            削除
                          </button>
                        </GuestLock>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="article-related-empty">
                この記事に紐づくWordPackはまだありません。必要な語句はLexiconで作成できます。
              </p>
            )}
          </section>
          {metaRows.length > 0 ? (
            <details className="article-detail-summary">
              <summary>生成・管理情報</summary>
              <dl className="ai-meta-grid" data-testid="article-meta">
                {metaRows.map((row, idx) => (
                  <React.Fragment key={`${row.label}-${idx}`}>
                    <dt>{row.label}</dt>
                    <dd>{row.value}</dd>
                  </React.Fragment>
                ))}
              </dl>
            </details>
          ) : null}
          {previewWordPackId && previewMeta ? (
            <section className="article-wordpack-preview" aria-label={`Reader内WordPackプレビュー ${previewMeta.lemma}`}>
              <div className="article-wordpack-preview__header">
                <div>
                  <h4>Reader / 関連WordPack: {previewMeta.lemma}</h4>
                  <p>記事「{article.title_en}」から開いた関連WordPackです。閉じても記事詳細は保持されます。</p>
                </div>
                <button
                  type="button"
                  className="article-wordpack-preview__close"
                  onClick={() => onSelectWordPackPreview?.(null)}
                >
                  プレビューを閉じる
                </button>
              </div>
              <WordPackPanel
                focusRef={wordPackPreviewFocusRef}
                selectedWordPackId={previewWordPackId}
                fallbackMeta={previewMeta}
                onWordPackGenerated={onWordPackGenerated}
                previewContext={`Readerの記事「${article.title_en}」から開いています。`}
                revealStudyCardImmediately
                onRequestClose={() => onSelectWordPackPreview?.(null)}
              />
            </section>
          ) : null}
        </div>
      ) : null}
    </Modal>
  );
};

export default ArticleDetailModal;
