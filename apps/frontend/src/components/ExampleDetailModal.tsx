import React, { useEffect, useId, useState } from 'react';
import { Modal } from './Modal';
import { TTSButton } from './TTSButton';
import { useSettings } from '../SettingsContext';
import { fetchJson, ApiError } from '../lib/fetcher';
import { useAuth } from '../AuthContext';
import { GuestLock } from './GuestLock';
import { formatDateJst } from '../lib/date';
import { buildExampleTranslationPairs, splitExampleExplanation } from '../lib/exampleExplanation';
import { SentencePairSpan, useSentencePairHighlight } from './SentencePairHighlighter';
import { createManualSentenceSegment } from '../lib/sentenceAlignment';

export interface ExampleItemData {
  id: number;
  word_pack_id: string;
  lemma: string;
  category: 'Dev' | 'CS' | 'LLM' | 'Business' | 'Common';
  en: string;
  ja: string;
  grammar_ja?: string | null;
  created_at: string;
  word_pack_updated_at?: string | null;
  checked_only_count?: number;
  learned_count?: number;
  transcription_typing_count?: number;
}

interface ExampleDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  item: ExampleItemData | null;
  onStudyProgressRecorded?: (payload: {
    id: number;
    word_pack_id: string;
    checked_only_count: number;
    learned_count: number;
  }) => void;
  onTranscriptionTypingRecorded?: (payload: {
    id: number;
    word_pack_id: string;
    transcription_typing_count: number;
  }) => void;
}

export const ExampleDetailModal: React.FC<ExampleDetailModalProps> = ({
  isOpen,
  onClose,
  item,
  onStudyProgressRecorded,
  onTranscriptionTypingRecorded,
}) => {
  const { isGuest } = useAuth();
  const { settings } = useSettings();
  const [progressUpdating, setProgressUpdating] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [localCounts, setLocalCounts] = useState<{ checked: number; learned: number; transcriptionTyping: number }>({
    checked: 0,
    learned: 0,
    transcriptionTyping: 0,
  });
  const [transcriptionFormVisible, setTranscriptionFormVisible] = useState(false);
  const [transcriptionInput, setTranscriptionInput] = useState('');
  const [transcriptionUpdating, setTranscriptionUpdating] = useState(false);
  const [transcriptionFeedback, setTranscriptionFeedback] = useState<string | null>(null);
  const readingHeadingId = useId();
  const transcriptionHelpId = useId();
  const transcriptionStatusId = useId();

  useEffect(() => {
    if (!item) return;
    setLocalCounts({
      checked: item.checked_only_count ?? 0,
      learned: item.learned_count ?? 0,
      transcriptionTyping: item.transcription_typing_count ?? 0,
    });
    setFeedback(null);
    setTranscriptionFeedback(null);
    setTranscriptionFormVisible(false);
    setTranscriptionInput('');
    setTranscriptionUpdating(false);
  }, [item]);

  const recordProgress = async (kind: 'checked' | 'learned') => {
    if (!item) return;
    if (!settings.apiBase) {
      setFeedback('APIベースURLが未設定です');
      return;
    }
    setProgressUpdating(true);
    try {
      const res = await fetchJson<{ id: number; word_pack_id: string; checked_only_count: number; learned_count: number }>(
        `${settings.apiBase}/word/examples/${item.id}/study-progress`,
        {
          method: 'POST',
          body: { kind },
        },
      );
      // 学習記録更新後も最新の文字起こし回数を保持するため、既存値を引き継ぎつつ2項目のみ上書きする。
      setLocalCounts((prev) => ({
        checked: res.checked_only_count,
        learned: res.learned_count,
        transcriptionTyping: prev.transcriptionTyping,
      }));
      try {
        onStudyProgressRecorded?.({
          id: res.id,
          word_pack_id: res.word_pack_id,
          checked_only_count: res.checked_only_count,
          learned_count: res.learned_count,
        });
      } catch {}
      setFeedback(kind === 'learned' ? '学習済みとして記録しました' : '確認済みとして記録しました');
    } catch (e) {
      const m = e instanceof ApiError ? e.message : '学習状況の記録に失敗しました';
      setFeedback(m);
    } finally {
      setProgressUpdating(false);
    }
  };

  // 入力フォームの表示/非表示はトグルのみで制御し、直前の入力値を保持する
  const toggleTranscriptionForm = () => {
    setTranscriptionFormVisible((visible) => !visible);
  };

  // 文字起こしタイピングの送信処理。APIと連携しローカル状態および親へ反映させる。
  const recordTranscriptionTyping = async () => {
    if (!item) return;
    if (!settings.apiBase) {
      setTranscriptionFeedback('APIベースURLが未設定です');
      return;
    }
    setTranscriptionUpdating(true);
    setTranscriptionFeedback(null);
    try {
      // バックエンド契約に合わせて入力文字数だけを送信する（本文そのものは送らない）。
      const inputLength = transcriptionInput.length;
      const res = await fetchJson<{
        id: number;
        word_pack_id: string;
        transcription_typing_count: number;
      }>(`${settings.apiBase}/word/examples/${item.id}/transcription-typing`, {
        method: 'POST',
        body: { input_length: inputLength },
      });
      setLocalCounts((prev) => ({
        checked: prev.checked,
        learned: prev.learned,
        transcriptionTyping: res.transcription_typing_count,
      }));
      try {
        onTranscriptionTypingRecorded?.({
          id: res.id,
          word_pack_id: res.word_pack_id,
          transcription_typing_count: res.transcription_typing_count,
        });
      } catch {}
      setTranscriptionFeedback('タイピング記録を保存しました');
    } catch (e) {
      const m = e instanceof ApiError ? e.message : '文字起こしタイピングの記録に失敗しました';
      setTranscriptionFeedback(m);
    } finally {
      setTranscriptionUpdating(false);
    }
  };

  const transcriptionLengthDiff = transcriptionInput.length - (item?.en.length ?? 0);
  const isTranscriptionWithinRange = Math.abs(transcriptionLengthDiff) <= 10; // ±10文字差以内なら許容する
  const transcriptionDisabledReason = transcriptionInput.trim().length === 0
    ? '英文を入力すると記録できます。'
    : isTranscriptionWithinRange
      ? '文字数条件を満たしています。'
      : '入力文字数差が10文字以内になると記録できます。';
  const transcriptionRecordDisabled =
    transcriptionUpdating || !isTranscriptionWithinRange || transcriptionInput.trim().length === 0;
  const explanationSections = splitExampleExplanation(item?.grammar_ja);
  const translationPairs = item ? buildExampleTranslationPairs(item.en, item.ja) : [];
  const exampleHighlightKey = item ? `${item.id}:${item.en}:${item.ja}` : null;
  const exampleSentenceHighlight = useSentencePairHighlight(
    Boolean(item?.ja?.trim()) && translationPairs.length > 1,
    exampleHighlightKey,
  );
  const formattedPackUpdatedAt = item?.word_pack_updated_at ? formatDateJst(item.word_pack_updated_at) || item.word_pack_updated_at : null;
  const formattedCreatedAt = item ? formatDateJst(item.created_at) || item.created_at : null;

  if (!isOpen || !item) return null;
  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`例文 詳細（${item.lemma} / ${item.category}）`}>
      <section className="example-detail-modal" aria-label={`${item.lemma}の${item.category}例文詳細`}>
        <style>{`
          .example-detail-modal {
            display: grid;
            gap: 1rem;
            max-width: 58rem;
          }
          .example-detail-reading {
            display: grid;
            gap: 0.75rem;
          }
          .example-detail-reading__header {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 0.75rem;
            flex-wrap: wrap;
          }
          .example-detail-reading__header h3 {
            margin: 0;
          }
          .example-detail-tts-row {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            flex-wrap: wrap;
          }
          .example-detail-pairs {
            list-style: none;
            margin: 0;
            padding: 0;
            display: grid;
            gap: 0.65rem;
          }
          .example-detail-pair {
            display: grid;
            grid-template-columns: 2rem minmax(0, 1fr) minmax(0, 1fr);
            gap: 0.75rem;
            align-items: stretch;
            padding: 0.75rem;
            border: 1px solid var(--color-border);
            border-radius: 8px;
            background: var(--color-surface);
          }
          .example-detail-pair__index {
            align-self: start;
            justify-self: center;
            display: inline-grid;
            place-items: center;
            width: 1.75rem;
            height: 1.75rem;
            border-radius: 999px;
            background: var(--color-accent-bg);
            color: var(--color-accent);
            font-weight: 700;
            font-variant-numeric: tabular-nums;
          }
          .example-detail-pair__text {
            min-width: 0;
            display: grid;
            gap: 0.25rem;
            align-content: start;
          }
          .example-detail-label {
            color: var(--color-subtle);
            font-size: 0.85rem;
            font-weight: 700;
          }
          .example-detail-pair p,
          .example-detail-note p,
          .example-detail-grammar-details p {
            margin: 0;
            line-height: 1.65;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
          }
          .example-detail-sentence {
            display: inline;
          }
          .example-detail-explanation {
            display: grid;
            gap: 0.7rem;
            border: 1px solid var(--color-border);
            border-radius: 8px;
            padding: 0.8rem;
            background: var(--color-surface);
          }
          .example-detail-explanation h3,
          .example-detail-note h4 {
            margin: 0;
          }
          .example-detail-explanation__grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr));
            gap: 0.65rem;
          }
          .example-detail-note {
            display: grid;
            gap: 0.35rem;
            padding: 0.65rem 0.75rem;
            border-left: 3px solid var(--color-accent);
            border-radius: 6px;
            background: var(--color-accent-bg);
          }
          .example-detail-grammar-details {
            border: 1px dashed var(--color-border);
            border-radius: 6px;
            padding: 0.6rem 0.75rem;
          }
          .example-detail-grammar-details[open] summary {
            margin-bottom: 0.45rem;
          }
          .example-detail-grammar-details summary,
          .example-detail-meta summary {
            cursor: pointer;
            font-weight: 600;
          }
          .example-detail-meta {
            border-top: 1px solid var(--color-border);
            padding-top: 0.75rem;
          }
          .example-detail-meta dl {
            display: grid;
            grid-template-columns: minmax(7rem, 0.4fr) 1fr;
            column-gap: 0.75rem;
            row-gap: 0.35rem;
            color: var(--color-subtle);
            font-size: 0.85rem;
          }
          .example-detail-meta dd {
            margin: 0;
            word-break: break-word;
          }
          .example-detail-actions {
            display: grid;
            gap: 0.65rem;
            border-top: 1px solid var(--color-border);
            padding-top: 0.75rem;
          }
          .example-detail-action-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            align-items: center;
          }
          .example-detail-help {
            margin: 0;
            color: var(--color-subtle);
            line-height: 1.5;
          }
          @media (max-width: 640px) {
            .example-detail-pair {
              grid-template-columns: 2rem minmax(0, 1fr);
            }
            .example-detail-pair__text {
              grid-column: 2;
            }
            .example-detail-pair__index {
              grid-row: 1 / span 2;
            }
          }
        `}</style>
        <section className="example-detail-reading" aria-labelledby={readingHeadingId}>
          <div className="example-detail-reading__header">
            <h3 id={readingHeadingId}>原文と日本語訳</h3>
            <div className="example-detail-tts-row">
              <TTSButton text={item.en} label="原文の音声" ariaLabel="原文の音声" style={{ fontSize: '0.85em', padding: '0.15rem 0.5rem', borderRadius: 4 }} />
              <TTSButton text={item.ja} label="訳の音声" ariaLabel="日本語訳の音声" style={{ fontSize: '0.85em', padding: '0.15rem 0.5rem', borderRadius: 4 }} />
            </div>
          </div>
          <ol className="example-detail-pairs" aria-label="原文と日本語訳の対応">
            {translationPairs.map((pair) => {
              const pairKey = `sentence-${pair.index}`;
              const englishSentence = createManualSentenceSegment(`example-en-${pair.index}`, pairKey, pair.index, pair.en);
              const japaneseSentence = createManualSentenceSegment(`example-ja-${pair.index}`, pairKey, pair.index, pair.ja);
              return (
                <li key={`${pair.index}-${pair.en}`} className="example-detail-pair">
                  <span className="example-detail-pair__index" aria-hidden="true">{pair.index}</span>
                  <div className="example-detail-pair__text">
                    <span className="example-detail-label">原文</span>
                    <p>
                      <SentencePairSpan
                        sentence={englishSentence}
                        language="en"
                        highlight={exampleSentenceHighlight}
                        className="example-detail-sentence"
                      >
                        {pair.en}
                      </SentencePairSpan>
                    </p>
                  </div>
                  <div className="example-detail-pair__text">
                    <span className="example-detail-label">日本語訳</span>
                    <p>
                      <SentencePairSpan
                        sentence={japaneseSentence}
                        language="ja"
                        highlight={exampleSentenceHighlight}
                        className="example-detail-sentence"
                      >
                        {pair.ja}
                      </SentencePairSpan>
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        </section>
        {item.grammar_ja ? (
          <section className="example-detail-explanation" aria-label="例文の解説">
            <h3>解説</h3>
            <div className="example-detail-explanation__grid">
              {explanationSections.summary ? (
                <article className="example-detail-note">
                  <h4>要点</h4>
                  <p>{explanationSections.summary}</p>
                </article>
              ) : null}
              {explanationSections.structure ? (
                <article className="example-detail-note">
                  <h4>構文</h4>
                  <p>{explanationSections.structure}</p>
                </article>
              ) : null}
            </div>
            {explanationSections.details ? (
              <details className="example-detail-grammar-details">
                <summary>品詞分解を表示</summary>
                <p>{explanationSections.details}</p>
              </details>
            ) : null}
          </section>
        ) : null}
        <details className="example-detail-meta">
          <summary>例文の詳細情報</summary>
          <dl>
            <dt>ID</dt>
            <dd>{item.id}</dd>
            <dt>WordPack</dt>
            <dd>{item.word_pack_id}</dd>
            {formattedPackUpdatedAt ? (
              <>
                <dt>Pack更新</dt>
                <dd>{formattedPackUpdatedAt}</dd>
              </>
            ) : null}
            <dt>例文作成</dt>
            <dd>{formattedCreatedAt}</dd>
          </dl>
        </details>
        <section className="example-detail-actions" aria-label="例文の学習記録">
          <div className="example-detail-action-row">
            <h3 style={{ margin: 0, fontSize: '1rem' }}>学習記録</h3>
            <GuestLock isGuest={isGuest}>
              <button
                type="button"
                onClick={() => recordProgress('checked')}
                disabled={progressUpdating}
                style={{
                  padding: '0.3rem 0.6rem',
                  borderRadius: 6,
                  border: '1px solid #ffa726',
                  backgroundColor: '#fff3e0',
                  color: '#8a3a00',
                }}
              >
                確認済みにする ({localCounts.checked})
              </button>
            </GuestLock>
            <GuestLock isGuest={isGuest}>
              <button
                type="button"
                onClick={() => recordProgress('learned')}
                disabled={progressUpdating}
                style={{
                  padding: '0.3rem 0.6rem',
                  borderRadius: 6,
                  border: '1px solid #81c784',
                  backgroundColor: '#e8f5e9',
                  color: '#1b5e20',
                }}
              >
                学習済みにする ({localCounts.learned})
              </button>
            </GuestLock>
            {feedback ? (
              <span
                role="status"
                aria-live="polite"
                style={{
                  fontSize: '0.8em',
                  color: feedback.includes('失敗') || feedback.includes('未設定') ? '#c62828' : '#2e7d32',
                }}
              >
                {feedback}
              </span>
            ) : null}
          </div>
          <div style={{ display: 'grid', gap: '0.5rem' }}>
            <GuestLock isGuest={isGuest}>
              <button
                type="button"
                onClick={toggleTranscriptionForm}
                aria-expanded={transcriptionFormVisible}
                aria-controls={transcriptionFormVisible ? transcriptionHelpId : undefined}
                style={{
                  padding: '0.3rem 0.6rem',
                  borderRadius: 6,
                  border: '1px solid #64b5f6',
                  backgroundColor: transcriptionFormVisible ? '#e3f2fd' : '#f5faff',
                  color: '#0d47a1',
                  textAlign: 'left',
                }}
              >
                {transcriptionFormVisible ? '文字起こしタイピングを閉じる' : '文字起こしタイピングを開く'} ({localCounts.transcriptionTyping}文字)
              </button>
            </GuestLock>
            {transcriptionFormVisible ? (
              <div style={{ display: 'grid', gap: '0.5rem' }}>
                <p id={transcriptionHelpId} className="example-detail-help">
                  原文と同じ英文を入力してください。文字数差が10文字以内になると記録できます。
                </p>
                <label style={{ display: 'grid', gap: '0.25rem' }}>
                  <span style={{ fontWeight: 600 }}>英文入力</span>
                  <GuestLock isGuest={isGuest}>
                    <textarea
                      value={transcriptionInput}
                      onChange={(event) => setTranscriptionInput(event.target.value)}
                      rows={5}
                      style={{
                        borderRadius: 6,
                        border: '1px solid #90caf9',
                        padding: '0.5rem',
                        fontFamily: 'inherit',
                      }}
                      aria-label="文字起こしタイピング入力"
                      aria-describedby={`${transcriptionHelpId} ${transcriptionStatusId}`}
                    />
                  </GuestLock>
                </label>
                <div className="example-detail-action-row">
                  <GuestLock isGuest={isGuest}>
                    <button
                      type="button"
                      onClick={recordTranscriptionTyping}
                      disabled={transcriptionRecordDisabled}
                      aria-describedby={transcriptionStatusId}
                      style={{
                        padding: '0.3rem 0.6rem',
                        borderRadius: 6,
                        border: '1px solid #64b5f6',
                        backgroundColor: transcriptionRecordDisabled ? '#e3f2fd' : '#bbdefb',
                        color: '#0d47a1',
                      }}
                    >
                      文字起こしを記録
                    </button>
                  </GuestLock>
                  <span
                    id={transcriptionStatusId}
                    style={{ fontSize: '0.85em', color: isTranscriptionWithinRange ? '#2e7d32' : '#c62828' }}
                  >
                    入力文字数差: {transcriptionLengthDiff}。{transcriptionDisabledReason}
                  </span>
                  {transcriptionFeedback ? (
                    <span
                      role="status"
                      aria-live="polite"
                      style={{
                        fontSize: '0.8em',
                        color:
                          transcriptionFeedback.includes('失敗') || transcriptionFeedback.includes('未設定')
                            ? '#c62828'
                            : '#2e7d32',
                      }}
                    >
                      {transcriptionFeedback}
                    </span>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>
        </section>
      </section>
    </Modal>
  );
};
