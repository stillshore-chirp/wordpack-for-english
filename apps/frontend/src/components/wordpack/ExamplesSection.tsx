import React, { useMemo } from 'react';
import { ExampleItem, Examples, WordPack } from '../../hooks/useWordPack';
import { LemmaLookupResponseData } from '../LemmaExplorer/useLemmaExplorer';
import { TTSButton } from '../TTSButton';
import { highlightLemma } from '../../lib/highlight';
import { useLemmaTooltip } from './useLemmaTooltip';
import { useAuth } from '../../AuthContext';
import { GuestLock } from '../GuestLock';
import { buildExampleTranslationPairs, splitExampleExplanation } from '../../lib/exampleExplanation';
import { SentencePairSpan, useSentencePairHighlight } from '../SentencePairHighlighter';
import { createManualSentenceSegment } from '../../lib/sentenceAlignment';

export type ExampleCategory = keyof Examples;

interface ExamplesSectionProps {
  data: WordPack;
  currentWordPackId: string | null;
  isActionLoading: boolean;
  onGenerateExamples: (category: ExampleCategory) => Promise<void>;
  onDeleteExample: (category: ExampleCategory, index: number) => Promise<void>;
  onImportArticleFromExample: (category: ExampleCategory, index: number) => Promise<void>;
  onCopyExampleText: (category: ExampleCategory, index: number) => Promise<void>;
  onLemmaOpen: (lemmaText: string) => void;
  lookupLemmaMetadata: (lemmaText: string) => Promise<LemmaLookupResponseData>;
  triggerUnknownLemmaGeneration: (lemmaText: string) => Promise<boolean>;
  sectionId?: string;
  getCategorySectionId?: (category: ExampleCategory) => string;
}

/**
 * 例文一覧と派生操作（追加生成・削除・記事化など）をまとめるセクション。
 * レイアウト/スタイルとイベントハンドラを局所化し、上位はデータとハンドラだけを渡す。
 */
export const ExamplesSection: React.FC<ExamplesSectionProps> = ({
  data,
  currentWordPackId,
  isActionLoading,
  onGenerateExamples,
  onDeleteExample,
  onImportArticleFromExample,
  onCopyExampleText,
  onLemmaOpen,
  lookupLemmaMetadata,
  triggerUnknownLemmaGeneration,
  sectionId = 'examples',
  getCategorySectionId = (category) => `examples-${category}`,
}) => {
  const { isGuest } = useAuth();
  const exampleCategories = useMemo(() => (['Dev', 'CS', 'LLM', 'Business', 'Common'] as ExampleCategory[]), []);
  const examplesHighlightKey = useMemo(
    () => [
      data.id ?? '',
      data.lemma,
      data.sense_title,
      ...exampleCategories.flatMap((category) => (
        (data.examples?.[category] ?? []).map((example) => `${category}:${example.en}\u0000${example.ja}`)
      )),
    ].join('\u0001'),
    [data.id, data.lemma, data.sense_title, data.examples, exampleCategories],
  );
  const exampleSentenceHighlight = useSentencePairHighlight(true, examplesHighlightKey);
  const styleDefinition = useMemo(
    () => `
      .ex-grid { display: grid; grid-template-columns: 1fr; gap: 0.75rem; }
      .ex-card { border: 1px solid var(--color-border); border-radius: 8px; padding: 0.75rem; background: var(--color-surface); display: grid; gap: 0.55rem; }
      .ex-block { display: grid; gap: 0.25rem; max-width: 48rem; }
      .ex-label { display: block; color: var(--color-subtle); font-size: 0.85rem; font-weight: 600; }
      .ex-en { font-weight: 600; line-height: 1.55; overflow-wrap: anywhere; }
      .ex-ja { color: var(--color-text); opacity: 0.92; line-height: 1.65; }
      .ex-sentence-list { display: inline; }
      .ex-sentence { display: inline; }
      .ex-grammar { color: var(--color-subtle); font-size: 0.92rem; line-height: 1.6; }
      .ex-grammar p { margin: 0; white-space: pre-wrap; }
      .ex-grammar details { margin-top: 0.35rem; }
      .ex-grammar summary { cursor: pointer; font-weight: 600; color: var(--color-text); }
      .ex-actions { margin-top: 0.15rem; display: inline-flex; gap: 6px; flex-wrap: wrap; }
      .ex-level { font-weight: 600; margin: 0.25rem 0; color: var(--color-level); }
      .lemma-highlight { color: var(--dict-accent); }
      .lemma-known { font-weight: 700; }
      .lemma-token { overflow-wrap: anywhere; word-break: break-word; }
      .lemma-unknown { color: #f59e0b; text-decoration: underline dotted #f59e0b; }
      .lemma-tooltip { position: fixed; z-index: 10000; max-width: min(320px, calc(100vw - 16px)); overflow-wrap: anywhere; white-space: normal; background: #212121; color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 12px; box-shadow: 0 2px 6px rgba(0,0,0,0.3); pointer-events: none; }
      .ex-en[role="button"] { cursor: pointer; }
      .ex-en[role="button"]:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }
    `,
    [],
  );
  const { handleMouseOver, handleMouseOut, detachTooltip } = useLemmaTooltip({ lookupLemmaMetadata, isGuest });

  const renderExampleEnText = (text: string, lemma: string): React.ReactNode => {
    const highlighted = highlightLemma(text, lemma, {
      spanProps: {
        'data-lemma': lemma,
      },
    });
    const nodes: React.ReactNode[] = [];
    let tokenSerial = 0;
    const wrapWords = (s: string) => {
      const parts = s.split(/([A-Za-z][A-Za-z\-']*)/g);
      for (let idx = 0; idx < parts.length; idx++) {
        const p = parts[idx];
        if (!p) continue;
        if (/^[A-Za-z][A-Za-z\-']*$/.test(p)) {
          nodes.push(
            <span key={`tok-${tokenSerial}-${idx}`} className="lemma-token" data-tok-idx={tokenSerial++}>{p}</span>,
          );
        } else {
          nodes.push(p);
        }
      }
    };
    if (Array.isArray(highlighted)) {
      highlighted.forEach((n) => {
        if (typeof n === 'string') {
          wrapWords(n);
        } else {
          nodes.push(n);
        }
      });
    } else if (typeof highlighted === 'string') {
      wrapWords(highlighted);
    } else {
      nodes.push(highlighted);
    }
    return nodes;
  };

  const handleExampleActivation = (
    event: React.MouseEvent<HTMLDivElement> | React.KeyboardEvent<HTMLDivElement>,
  ) => {
    if ('key' in event) {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
    }
    const container = event.currentTarget;
    const target = event.target as HTMLElement;
    const triggerPendingLemma = (pendingLemma: string, tokenEl?: HTMLElement | null) => {
      const trimmed = pendingLemma.trim();
      if (!trimmed) return;
      void triggerUnknownLemmaGeneration(trimmed).then((generated) => {
        if (!generated) return;
        container.removeAttribute('data-pending-lemma');
        container.removeAttribute('data-last-lemma');
        tokenEl?.removeAttribute('data-pending-lemma');
        tokenEl?.classList.remove('lemma-unknown');
        detachTooltip();
      });
    };
    const highlight = target.closest('span.lemma-highlight') as HTMLElement | null;
    if (highlight) {
      const lemmaAttr = highlight.getAttribute('data-lemma') || highlight.textContent?.trim();
      if (lemmaAttr) onLemmaOpen(lemmaAttr);
      return;
    }
    const token = target.closest('span.lemma-token') as HTMLElement | null;
    if (token) {
      const lemmaMatch = token.getAttribute('data-lemma-match');
      if (lemmaMatch) {
        onLemmaOpen(lemmaMatch);
        return;
      }
      const pendingLemma = token.getAttribute('data-pending-lemma') || container.getAttribute('data-pending-lemma');
      if (pendingLemma && pendingLemma.trim()) {
        triggerPendingLemma(pendingLemma, token);
        return;
      }
    }
    const pending = container.getAttribute('data-pending-lemma');
    if (pending && pending.trim()) {
      triggerPendingLemma(pending);
      return;
    }
    const fallback = container.getAttribute('data-last-lemma') || container.getAttribute('data-lemma');
    if (fallback) onLemmaOpen(fallback);
  };

  const totalExamples = useMemo(
    () => exampleCategories.reduce((sum, key) => sum + (data.examples?.[key]?.length || 0), 0),
    [data.examples, exampleCategories],
  );

  return (
    <section id={sectionId} className="wp-section">
      <h3>
        例文
        <span style={{ fontSize: '0.7em', fontWeight: 'normal', color: 'var(--color-subtle)', marginLeft: '0.5rem' }}>
          (総数 {totalExamples}件)
        </span>
      </h3>
      <style>{styleDefinition}</style>
      {exampleCategories.map((category) => (
        <div key={category} id={getCategorySectionId(category)} style={{ marginBottom: '0.5rem' }}>
          <div className="ex-level" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span>{category} ({data.examples?.[category]?.length || 0}件)</span>
            <GuestLock isGuest={isGuest}>
              <button
                onClick={() => onGenerateExamples(category)}
                disabled={!currentWordPackId || isActionLoading}
                aria-label={`${category}例文を2件追加生成`}
                title={!currentWordPackId ? '保存済みWordPackのみ追加生成が可能です' : undefined}
                style={{ fontSize: '0.85em', color: '#1565c0', border: '1px solid #1565c0', background: 'white', padding: '0.1rem 0.4rem', borderRadius: 4 }}
              >
                追加生成（2件）
              </button>
            </GuestLock>
          </div>
          {data.examples?.[category]?.length ? (
            <div className="ex-grid">
              {(data.examples[category] as ExampleItem[]).map((ex: ExampleItem, index: number) => {
                const explanationSections = splitExampleExplanation(ex.grammar_ja);
                const translationPairs = buildExampleTranslationPairs(ex.en, ex.ja);
                const canHighlightSentencePairs = translationPairs.length > 1;
                return (
                  <article
                    key={index}
                    className="ex-card"
                    aria-label={`${category}カテゴリの例文${index + 1}`}
                    data-testid={`example-${category}-${index}`}
                  >
                    <div
                      className="ex-block ex-en"
                      data-lemma={data.lemma}
                      data-sense-title={data.sense_title}
                      role="button"
                      tabIndex={0}
                      aria-label={`${category}カテゴリの例文${index + 1}の語句から関連WordPackを開く`}
                      onClick={handleExampleActivation}
                      onKeyDown={handleExampleActivation}
                      onMouseOver={handleMouseOver}
                      onMouseOut={handleMouseOut}
                    >
                      <span className="ex-label">[{index + 1}] 英文</span>
                      <span className="ex-sentence-list">
                        {translationPairs.map((pair, pairIndex) => {
                          const sentenceKey = `example-${category}-${index}-sentence-${pair.index}`;
                          const pairKey = canHighlightSentencePairs ? sentenceKey : null;
                          const sentence = createManualSentenceSegment(
                            `${sentenceKey}-en`,
                            pairKey,
                            pair.index,
                            pair.en,
                          );
                          return (
                            <React.Fragment key={sentence.key}>
                              <SentencePairSpan
                                sentence={sentence}
                                language="en"
                                highlight={exampleSentenceHighlight}
                                className="ex-sentence"
                                interactive={false}
                              >
                                {renderExampleEnText(pair.en, data.lemma)}
                              </SentencePairSpan>
                              {pairIndex < translationPairs.length - 1 ? ' ' : null}
                            </React.Fragment>
                          );
                        })}
                      </span>
                    </div>
                    <div className="ex-block ex-ja">
                      <span className="ex-label">日本語訳</span>
                      <span className="ex-sentence-list">
                        {translationPairs.map((pair, pairIndex) => {
                          const sentenceKey = `example-${category}-${index}-sentence-${pair.index}`;
                          const pairKey = canHighlightSentencePairs ? sentenceKey : null;
                          const sentence = createManualSentenceSegment(
                            `${sentenceKey}-ja`,
                            pairKey,
                            pair.index,
                            pair.ja,
                          );
                          return (
                            <React.Fragment key={sentence.key}>
                              <SentencePairSpan
                                sentence={sentence}
                                language="ja"
                                highlight={exampleSentenceHighlight}
                                className="ex-sentence"
                              >
                                {pair.ja}
                              </SentencePairSpan>
                              {pairIndex < translationPairs.length - 1 ? ' ' : null}
                            </React.Fragment>
                          );
                        })}
                      </span>
                    </div>
                    {ex.grammar_ja ? (
                      <div className="ex-block ex-grammar">
                        <span className="ex-label">解説</span>
                        {explanationSections.summary ? <p>{explanationSections.summary}</p> : null}
                        {explanationSections.structure ? (
                          <>
                            <span className="ex-label">構文</span>
                            <p>{explanationSections.structure}</p>
                          </>
                        ) : null}
                        {explanationSections.details ? (
                          <details>
                            <summary>品詞分解を表示</summary>
                            <p>{explanationSections.details}</p>
                          </details>
                        ) : null}
                      </div>
                    ) : null}
                    <div className="ex-actions">
                      <TTSButton
                        text={ex.en}
                        label="音声"
                        ariaLabel="英文の音声"
                        voice="alloy"
                        style={{ fontSize: '0.85em', color: '#6a1b9a', border: '1px solid #6a1b9a', background: 'white', padding: '0.1rem 0.4rem', borderRadius: 4 }}
                      />
                      {currentWordPackId ? (
                        <>
                          <GuestLock isGuest={isGuest}>
                            <button
                              onClick={() => onDeleteExample(category, index)}
                              disabled={isActionLoading}
                              aria-label={`${data.lemma}の${category}例文${index + 1}を削除`}
                              style={{ fontSize: '0.85em', color: '#d32f2f', border: '1px solid #d32f2f', background: 'white', padding: '0.1rem 0.4rem', borderRadius: 4 }}
                            >
                              削除
                            </button>
                          </GuestLock>
                          <GuestLock isGuest={isGuest}>
                            <button
                              onClick={() => onImportArticleFromExample(category, index)}
                              disabled={isActionLoading}
                              aria-label={`${data.lemma}の${category}例文${index + 1}から記事を作成`}
                              style={{ fontSize: '0.85em', color: '#2e7d32', border: '1px solid #2e7d32', background: 'white', padding: '0.1rem 0.4rem', borderRadius: 4 }}
                            >
                              記事を作成
                            </button>
                          </GuestLock>
                        </>
                      ) : null}
                      <button
                        onClick={() => onCopyExampleText(category, index)}
                        disabled={isActionLoading}
                        aria-label={`${data.lemma}の${category}例文${index + 1}をコピー`}
                        style={{ fontSize: '0.85em', color: '#1976d2', border: '1px solid #1976d2', background: 'white', padding: '0.1rem 0.4rem', borderRadius: 4 }}
                      >
                        コピー
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : <p>なし</p>}
        </div>
      ))}
    </section>
  );
};
