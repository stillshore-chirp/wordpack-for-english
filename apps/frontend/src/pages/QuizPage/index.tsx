import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../AuthContext';
import { useNotifications } from '../../NotificationsContext';
import { useSettings } from '../../SettingsContext';
import { GuestLock } from '../../components/GuestLock';
import {
  SentencePairParagraphs,
  useSentencePairHighlight,
  type SentencePairHighlightState,
} from '../../components/SentencePairHighlighter';
import { TTSButton } from '../../components/TTSButton';
import { WordPackPreviewModal } from '../../components/WordPackPreviewModal';
import {
  composeModelRequestFields,
  createEmptyWordPackRequest,
  fetchWordPackList,
  generateWordPackRequest,
} from '../../features/wordpack/api';
import type { WordPackListItem } from '../../features/wordpack/types';
import {
  createQuizGenerationJob,
  deleteQuiz,
  fetchQuiz,
  fetchQuizGenerationJob,
  fetchQuizList,
  submitQuizAttempt,
  updateQuizGuestPublic,
} from '../../features/quiz/api';
import {
  DIFFICULTY_LABELS,
  DOMAIN_INTENSITY_LABELS,
  FORMAT_PROFILE_LABELS,
  GENERATION_DOMAIN_LABELS,
  QUESTION_TYPE_LABELS,
} from '../../features/quiz/labels';
import type {
  Quiz,
  QuizAttemptResponse,
  QuizChoiceId,
  QuizDifficulty,
  QuizDomainIntensity,
  QuizFormatProfile,
  QuizGenerateRequest,
  QuizGenerationDomain,
  QuizListItem,
  QuizPassage,
  QuizQuestion,
  QuizQuestionResult,
  QuizSection,
  QuizWordPackLink,
} from '../../features/quiz/types';
import { ApiError } from '../../shared/api/ApiError';
import {
  buildSentenceAlignment,
  countSentencePairs,
  type SentenceParagraph,
  type SentenceSegment,
} from '../../lib/sentenceAlignment';
import { APP_EVENTS, dispatchAppEvent } from '../../shared/events/appEvents';
import './QuizPage.css';

type Answers = Record<string, QuizChoiceId | null>;

const FORMAT_PROFILE_OPTIONS = Object.keys(FORMAT_PROFILE_LABELS) as QuizFormatProfile[];
const GENERATION_DOMAIN_OPTIONS = Object.keys(GENERATION_DOMAIN_LABELS) as QuizGenerationDomain[];
const DOMAIN_INTENSITY_OPTIONS = Object.keys(DOMAIN_INTENSITY_LABELS) as QuizDomainIntensity[];
const DIFFICULTY_OPTIONS = Object.keys(DIFFICULTY_LABELS) as QuizDifficulty[];
const AUTO_LEMMA_COUNT = 3;
const WORD_PACK_PAGE_LIMIT = 100;

const normalizeApiBase = (base: string) => base.replace(/\/+$/, '');

const splitListInput = (value: string): string[] => (
  value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean)
);

const isGeneratedWordPack = (wordPack: WordPackListItem): boolean => !wordPack.is_empty;

const escapeRegExp = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const isWordBoundary = (value: string | undefined): boolean => !value || !/[A-Za-z0-9'-]/.test(value);

const findFallbackOccurrences = (body: string, link: QuizWordPackLink, passageId: string) => {
  const hasExplicitOccurrence = (link.occurrences ?? []).some((occurrence) => (
    (occurrence.passage_id ?? passageId) === passageId
  ));
  if (hasExplicitOccurrence || !link.lemma.trim()) return [];
  const pattern = new RegExp(escapeRegExp(link.lemma), 'gi');
  const occurrences: Array<{ start: number; end: number; passage_id?: string | null; link: QuizWordPackLink }> = [];
  let match = pattern.exec(body);
  while (match) {
    const start = match.index;
    const end = start + match[0].length;
    if (isWordBoundary(body[start - 1]) && isWordBoundary(body[end])) {
      occurrences.push({ start, end, passage_id: passageId, link });
    }
    match = pattern.exec(body);
  }
  return occurrences;
};

const clampInteger = (raw: string, min: number, max: number): number => {
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return min;
  return Math.min(max, Math.max(min, Math.trunc(parsed)));
};

const getAllQuestions = (quiz: Quiz | null): QuizQuestion[] => (
  quiz ? quiz.sections.flatMap((section) => section.questions) : []
);

const getAttemptResultMap = (attempt: QuizAttemptResponse | null): Record<string, QuizQuestionResult> => (
  Object.fromEntries((attempt?.results ?? []).map((result) => [result.question_id, result]))
);

const formatDate = (value: string | null | undefined) => {
  if (!value) return '日時なし';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('ja-JP', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
};

const buildLocalAttempt = (quiz: Quiz, answers: Answers): QuizAttemptResponse => {
  const results = getAllQuestions(quiz).map((question) => {
    const selected = answers[question.id] ?? null;
    return {
      question_id: question.id,
      selected_choice_id: selected,
      correct_choice_id: question.correct_choice_id,
      is_correct: selected === question.correct_choice_id,
    };
  });
  const score = results.filter((result) => result.is_correct).length;
  const total = results.length;
  return {
    id: 'local-preview',
    quiz_id: quiz.id,
    score,
    total,
    percentage: total ? (score / total) * 100 : 0,
    results,
    submitted_at: new Date().toISOString(),
  };
};

type PassageWordOccurrence = {
  start: number;
  end: number;
  link: QuizWordPackLink;
};

const buildPassageWordOccurrences = (
  body: string,
  links: QuizWordPackLink[],
  passageId: string,
): PassageWordOccurrence[] => {
  const explicitOccurrences = links.flatMap((link) =>
    (link.occurrences ?? [])
      .filter((occurrence) => (occurrence.passage_id ?? passageId) === passageId)
      .map((occurrence) => ({ start: occurrence.start, end: occurrence.end, link })),
  );
  const fallbackOccurrences = links.flatMap((link) => findFallbackOccurrences(body, link, passageId));
  return [...explicitOccurrences, ...fallbackOccurrences]
    .filter((occurrence) => (
      occurrence.start >= 0
      && occurrence.end > occurrence.start
      && occurrence.end <= body.length
    ))
    .sort((a, b) => a.start - b.start);
};

const buildSentenceSegments = (
  body: string,
  sentence: SentenceSegment,
  occurrences: PassageWordOccurrence[],
): Array<{ key: string; text: string; link?: QuizWordPackLink }> => {
  const out: Array<{ key: string; text: string; link?: QuizWordPackLink }> = [];
  let cursor = sentence.start;
  occurrences.forEach((occurrence, index) => {
    if (occurrence.start < cursor || occurrence.start < sentence.start || occurrence.end > sentence.end) {
      return;
    }
    if (occurrence.start > cursor) {
      out.push({ key: `text-${sentence.key}-${index}-${cursor}`, text: body.slice(cursor, occurrence.start) });
    }
    out.push({
      key: `word-${sentence.key}-${index}-${occurrence.start}`,
      text: body.slice(occurrence.start, occurrence.end),
      link: occurrence.link,
    });
    cursor = occurrence.end;
  });
  if (cursor < sentence.end) {
    out.push({ key: `text-${sentence.key}-end-${cursor}`, text: body.slice(cursor, sentence.end) });
  }
  return out.length ? out : [{ key: `text-${sentence.key}`, text: sentence.text }];
};

const InlineWordPackAnchor: React.FC<{
  link: QuizWordPackLink;
  text: string;
  isGuest: boolean;
  onOpenWordPack: (wordPackId: string) => void;
  onCreateEmpty: (lemma: string) => void;
  onGenerate: (lemma: string) => void;
}> = ({ link, text, isGuest, onOpenWordPack, onCreateEmpty, onGenerate }) => {
  const [open, setOpen] = useState(false);
  const canOpen = Boolean(link.word_pack_id) && (link.status === 'existing' || link.status === 'created');
  const label = link.status === 'missing'
    ? '未登録'
    : link.status === 'generated_requested'
      ? '生成中'
      : link.is_empty
        ? '未生成'
        : 'WordPack';

  const handleClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (canOpen && link.word_pack_id) {
      onOpenWordPack(link.word_pack_id);
      return;
    }
    setOpen((prev) => !prev);
  };

  return (
    <span className="quiz-inline-word">
      <button
        type="button"
        className={`quiz-inline-word__button is-${link.status}`}
        onClick={handleClick}
        aria-expanded={open}
        aria-label={`${link.lemma} のWordPack操作を開く`}
      >
        <span>{text}</span>
        <small>{label}</small>
      </button>
      {open && !canOpen ? (
        <span
          className="quiz-inline-word__popover"
          role="dialog"
          aria-label={`${link.lemma} のWordPack操作`}
          onClick={(event) => event.stopPropagation()}
        >
          <strong>{link.lemma}</strong>
          <span>
            {isGuest
              ? 'ゲスト閲覧では作成・生成できません。'
              : '未登録の語をWordPackへ接続できます。'}
          </span>
          <span className="quiz-inline-word__actions">
            <GuestLock isGuest={isGuest}>
              <button type="button" onClick={() => onCreateEmpty(link.lemma)}>
                空で作成
              </button>
            </GuestLock>
            <GuestLock isGuest={isGuest}>
              <button type="button" onClick={() => onGenerate(link.lemma)}>
                生成開始
              </button>
            </GuestLock>
          </span>
        </span>
      ) : null}
    </span>
  );
};


const QuizPassageText: React.FC<{
  passageId: string;
  body: string;
  paragraphs: SentenceParagraph[];
  links: QuizWordPackLink[];
  isGuest: boolean;
  highlight: SentencePairHighlightState;
  onOpenWordPack: (wordPackId: string) => void;
  onCreateEmpty: (lemma: string) => void;
  onGenerate: (lemma: string) => void;
}> = ({
  passageId,
  body,
  paragraphs,
  links,
  isGuest,
  highlight,
  onOpenWordPack,
  onCreateEmpty,
  onGenerate,
}) => {
  const occurrences = useMemo(() => buildPassageWordOccurrences(body, links, passageId), [body, links, passageId]);

  return (
    <div className="quiz-passage-body" aria-label="英文本文">
      <SentencePairParagraphs
        paragraphs={paragraphs}
        language="en"
        highlight={highlight}
        paragraphClassName="quiz-passage-paragraph"
        sentenceClassName="quiz-sentence"
        renderSentence={(sentence) => {
          const segments = buildSentenceSegments(body, sentence, occurrences);
          return segments.map((segment) => (
            segment.link ? (
              <InlineWordPackAnchor
                key={segment.key}
                link={segment.link}
                text={segment.text}
                isGuest={isGuest}
                onOpenWordPack={onOpenWordPack}
                onCreateEmpty={onCreateEmpty}
                onGenerate={onGenerate}
              />
            ) : (
              <React.Fragment key={segment.key}>{segment.text}</React.Fragment>
            )
          ));
        }}
      />
    </div>
  );
};

const QuizTranslationText: React.FC<{
  paragraphs: SentenceParagraph[];
  highlight: SentencePairHighlightState;
}> = ({
  paragraphs,
  highlight,
}) => (
  <div className="quiz-translation__body" aria-label="日本語訳本文">
    <SentencePairParagraphs
      paragraphs={paragraphs}
      language="ja"
      highlight={highlight}
      paragraphClassName="quiz-translation__paragraph"
      sentenceClassName="quiz-sentence"
    />
  </div>
);

const QuizPassageArticle: React.FC<{
  passage: QuizPassage;
  links: QuizWordPackLink[];
  isGuest: boolean;
  onOpenWordPack: (wordPackId: string) => void;
  onCreateEmpty: (lemma: string) => void;
  onGenerate: (lemma: string) => void;
}> = ({ passage, links, isGuest, onOpenWordPack, onCreateEmpty, onGenerate }) => {
  const [translationOpen, setTranslationOpen] = useState(false);
  const alignment = useMemo(
    () => buildSentenceAlignment(passage.body_en, passage.body_ja),
    [passage.body_en, passage.body_ja],
  );
  const sentenceHighlight = useSentencePairHighlight(
    translationOpen && countSentencePairs(alignment) > 1,
    `${passage.id}:${passage.body_en}:${passage.body_ja ?? ''}`,
  );
  return (
    <article className={`quiz-passage ${translationOpen ? 'is-translation-open' : ''}`}>
      <div className="quiz-passage__header">
        <div>
          <p className="quiz-question__meta">{passage.kind}</p>
          <h4>{passage.title || `本文 ${passage.order}`}</h4>
        </div>
        <TTSButton text={passage.body_en} label="本文を聞く" ariaLabel={`${passage.title || `本文 ${passage.order}`}を聞く`} />
      </div>
      <QuizPassageText
        passageId={passage.id}
        body={passage.body_en}
        paragraphs={alignment.englishParagraphs}
        links={links}
        isGuest={isGuest}
        highlight={sentenceHighlight}
        onOpenWordPack={onOpenWordPack}
        onCreateEmpty={onCreateEmpty}
        onGenerate={onGenerate}
      />
      {passage.body_ja ? (
        <details
          className="quiz-translation"
          open={translationOpen}
          onToggle={(event) => {
            const nextOpen = event.currentTarget.open;
            setTranslationOpen(nextOpen);
            if (!nextOpen) {
              sentenceHighlight.clearPairs();
            }
          }}
        >
          <summary>日本語訳</summary>
          <QuizTranslationText
            paragraphs={alignment.japaneseParagraphs}
            highlight={sentenceHighlight}
          />
        </details>
      ) : null}
    </article>
  );
};

const QuizQuestionCard: React.FC<{
  section: QuizSection;
  question: QuizQuestion;
  answer: QuizChoiceId | null;
  reviewResult?: QuizQuestionResult;
  onAnswer: (questionId: string, choiceId: QuizChoiceId) => void;
  onRelatedLemma: (lemma: string) => void;
}> = ({ section, question, answer, reviewResult, onAnswer, onRelatedLemma }) => {
  const reviewed = Boolean(reviewResult);
  const resultLabel = reviewed
    ? reviewResult?.is_correct
      ? '正解'
      : answer
        ? '不正解'
        : '未回答'
    : null;
  return (
    <article className={`quiz-question ${reviewed ? 'is-reviewed' : ''}`} aria-labelledby={`${question.id}-title`}>
      <div className="quiz-question__header">
        <div>
          <p className="quiz-question__meta">
            {section.title} / {QUESTION_TYPE_LABELS[question.type]}
          </p>
          <h4 id={`${question.id}-title`}>{question.prompt}</h4>
        </div>
        {resultLabel ? <span className={`quiz-result-pill ${reviewResult?.is_correct ? 'is-correct' : 'is-wrong'}`}>{resultLabel}</span> : null}
      </div>
      <fieldset className="quiz-choice-group">
        <legend className="visually-hidden">{question.prompt}</legend>
        {question.choices.map((choice) => {
          const isSelected = answer === choice.id;
          const isCorrect = reviewed && choice.id === question.correct_choice_id;
          const isWrongSelected = reviewed && isSelected && !isCorrect;
          return (
            <label
              key={choice.id}
              className={`quiz-choice ${isSelected ? 'is-selected' : ''} ${isCorrect ? 'is-correct' : ''} ${isWrongSelected ? 'is-wrong' : ''}`}
            >
              <input
                type="radio"
                name={question.id}
                value={choice.id}
                checked={isSelected}
                disabled={reviewed}
                onChange={() => onAnswer(question.id, choice.id)}
              />
              <span className="quiz-choice__id">{choice.id}</span>
              <span>{choice.text}</span>
              {isCorrect ? <strong>正答</strong> : null}
              {isWrongSelected ? <strong>選択</strong> : null}
            </label>
          );
        })}
      </fieldset>
      {reviewed ? (
        <div className="quiz-explanation" id={`${question.id}-explanation`}>
          <div>
            <strong>根拠</strong>
            <p>{question.explanation.evidence_text || '本文中の根拠は生成結果に含まれていません。本文と解説を照合してください。'}</p>
          </div>
          <div>
            <strong>日本語解説</strong>
            <p>{question.explanation.explanation_ja}</p>
          </div>
          {Object.keys(question.explanation.wrong_choice_explanations_ja ?? {}).length ? (
            <details>
              <summary>誤答理由</summary>
              <ul>
                {Object.entries(question.explanation.wrong_choice_explanations_ja).map(([choiceId, reason]) => (
                  <li key={choiceId}><strong>{choiceId}</strong>: {reason}</li>
                ))}
              </ul>
            </details>
          ) : null}
          {question.explanation.related_lemmas.length ? (
            <div className="quiz-lemma-row" aria-label="関連lemma">
              {question.explanation.related_lemmas.map((lemma) => (
                <button key={lemma} type="button" onClick={() => onRelatedLemma(lemma)}>
                  {lemma}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </article>
  );
};

export const QuizPage: React.FC = () => {
  const { isGuest } = useAuth();
  const { settings } = useSettings();
  const notifications = useNotifications();
  const apiBase = normalizeApiBase(settings.apiBase);
  const [items, setItems] = useState<QuizListItem[]>([]);
  const [selectedQuizId, setSelectedQuizId] = useState<string | null>(null);
  const [selectedQuiz, setSelectedQuiz] = useState<Quiz | null>(null);
  const [wordPacks, setWordPacks] = useState<WordPackListItem[]>([]);
  const [answers, setAnswers] = useState<Answers>({});
  const [attempt, setAttempt] = useState<QuizAttemptResponse | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [message, setMessage] = useState<{ kind: 'status' | 'alert'; text: string } | null>(null);
  const [generating, setGenerating] = useState(false);
  const [previewWordPackId, setPreviewWordPackId] = useState<string | null>(null);
  const [relatedLinks, setRelatedLinks] = useState<QuizWordPackLink[]>([]);
  const [detailFocusMode, setDetailFocusMode] = useState(false);

  const [formatProfile, setFormatProfile] = useState<QuizFormatProfile>('single_passage');
  const [generationDomain, setGenerationDomain] = useState<QuizGenerationDomain>('technical');
  const [domainIntensity, setDomainIntensity] = useState<QuizDomainIntensity>('standard');
  const [difficulty, setDifficulty] = useState<QuizDifficulty>('medium');
  const [sectionCount, setSectionCount] = useState(2);
  const [questionsPerSection, setQuestionsPerSection] = useState(3);
  const [selectedWordPackIds, setSelectedWordPackIds] = useState<string[]>([]);
  const [lemmaInput, setLemmaInput] = useState('mitigate, latency, trade-off');
  const [topicSeed, setTopicSeed] = useState('');
  const [avoidTopics, setAvoidTopics] = useState('malware, credential theft');

  const resultMap = useMemo(() => getAttemptResultMap(attempt), [attempt]);
  const questions = useMemo(() => getAllQuestions(selectedQuiz), [selectedQuiz]);
  const linkWarnings = useMemo(() => relatedLinks.filter((link) => Boolean(link.warning)), [relatedLinks]);
  const generatedWordPacks = useMemo(() => wordPacks.filter(isGeneratedWordPack), [wordPacks]);
  const generatedWordPackIds = useMemo(() => new Set(generatedWordPacks.map((wordPack) => wordPack.id)), [generatedWordPacks]);
  const autoLemmaCandidates = useMemo(() => (
    generatedWordPacks
      .map((wordPack) => wordPack.lemma.trim())
      .filter(Boolean)
      .slice(0, AUTO_LEMMA_COUNT)
  ), [generatedWordPacks]);
  const unansweredCount = questions.filter((question) => !answers[question.id]).length;
  const generationDisabled = selectedWordPackIds.length === 0 && splitListInput(lemmaInput).length === 0;
  const hiddenWordPackCount = wordPacks.length - generatedWordPacks.length;
  const wordPackHelperText = hiddenWordPackCount > 0
    ? `生成済みWordPackだけを表示します。未生成WordPack${hiddenWordPackCount}件は候補から除外しています。`
    : '生成済みWordPackだけを表示します。未生成WordPackは候補に含めません。';
  const autoLemmaHelpText = autoLemmaCandidates.length
    ? `生成済みWordPackから${autoLemmaCandidates.length}件を任意lemmaにセットします。`
    : '生成済みWordPackが読み込まれると、最大3件を任意lemmaにセットできます。';

  useEffect(() => {
    setSelectedWordPackIds((prev) => {
      const next = prev.filter((id) => generatedWordPackIds.has(id));
      return next.length === prev.length ? prev : next;
    });
  }, [generatedWordPackIds]);

  const loadWordPacks = useCallback(async () => {
    try {
      const items: WordPackListItem[] = [];
      let offset = 0;
      let total = Number.POSITIVE_INFINITY;
      while (offset < total) {
        const response = await fetchWordPackList(apiBase, {
          limit: WORD_PACK_PAGE_LIMIT,
          offset,
          timeoutMs: settings.requestTimeoutMs,
        });
        items.push(...response.items);
        total = response.total;
        if (!response.items.length) break;
        offset += response.items.length;
      }
      setWordPacks(items);
    } catch (error) {
      console.warn('[QuizPage] failed to load word packs', error);
    }
  }, [apiBase, settings.requestTimeoutMs]);

  const loadList = useCallback(async () => {
    setLoadingList(true);
    try {
      const response = await fetchQuizList(apiBase, {
        limit: 50,
        offset: 0,
        timeoutMs: settings.requestTimeoutMs,
      });
      setItems(response.items);
      setMessage(null);
      if (!selectedQuizId && response.items.length) {
        setSelectedQuizId(response.items[0].id);
      }
    } catch (error) {
      const text = error instanceof ApiError ? error.message : 'Quiz一覧を読み込めませんでした。';
      setMessage({ kind: 'alert', text });
    } finally {
      setLoadingList(false);
    }
  }, [apiBase, selectedQuizId, settings.requestTimeoutMs]);

  useEffect(() => {
    void loadList();
    void loadWordPacks();
  }, [loadList, loadWordPacks]);

  useEffect(() => {
    if (!selectedQuizId) {
      setSelectedQuiz(null);
      setDetailFocusMode(false);
      return;
    }
    const ctrl = new AbortController();
    setLoadingDetail(true);
    fetchQuiz(apiBase, selectedQuizId, {
      signal: ctrl.signal,
      timeoutMs: settings.requestTimeoutMs,
    })
      .then((quiz) => {
        setSelectedQuiz(quiz);
        setRelatedLinks(quiz.related_word_packs ?? []);
        setAnswers({});
        setAttempt(null);
      })
      .catch((error) => {
        if (ctrl.signal.aborted) return;
        const text = error instanceof ApiError ? error.message : 'Quiz詳細を読み込めませんでした。';
        setMessage({ kind: 'alert', text });
        setSelectedQuiz(null);
      })
      .finally(() => setLoadingDetail(false));
    return () => ctrl.abort();
  }, [apiBase, selectedQuizId, settings.requestTimeoutMs]);

  const updateRelatedLink = useCallback((lemma: string, patch: Partial<QuizWordPackLink>) => {
    setRelatedLinks((prev) => prev.map((link) => (
      link.lemma.toLowerCase() === lemma.toLowerCase() ? { ...link, ...patch } : link
    )));
  }, []);

  const handleAutoSetLemmas = useCallback(() => {
    if (!autoLemmaCandidates.length) return;
    setLemmaInput(autoLemmaCandidates.join(', '));
    setMessage({
      kind: 'status',
      text: `生成済みWordPackから${autoLemmaCandidates.length}件のlemmaを任意lemmaにセットしました。`,
    });
  }, [autoLemmaCandidates]);

  const handleCreateQuiz = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (generationDisabled) {
      setMessage({ kind: 'alert', text: '含めるWordPackまたはlemmaを1件以上指定してください。' });
      return;
    }
    setGenerating(true);
    setMessage({ kind: 'status', text: 'Quiz生成ジョブを開始しています。' });
    const notifId = notifications.add({
      title: 'Quiz生成中',
      message: '長文と設問を生成しています。',
      status: 'progress',
      category: GENERATION_DOMAIN_LABELS[generationDomain],
    });
    try {
      const modelFields = composeModelRequestFields({
        model: settings.model ?? 'gpt-5.4-mini',
        reasoningEffort: settings.reasoningEffort,
        textVerbosity: settings.textVerbosity,
      }) as Pick<QuizGenerateRequest, 'model' | 'reasoning' | 'text'>;
      const requestBody: QuizGenerateRequest = {
        format_profile: formatProfile,
        generation_domain: generationDomain,
        domain_intensity: domainIntensity,
        difficulty,
        word_pack_ids: selectedWordPackIds,
        lemmas: splitListInput(lemmaInput),
        section_count: sectionCount,
        questions_per_section: questionsPerSection,
        include_translation: true,
        topic_seed: topicSeed.trim() || null,
        avoid_topics: splitListInput(avoidTopics),
        ...modelFields,
      };
      const job = await createQuizGenerationJob(apiBase, requestBody, {
        timeoutMs: settings.requestTimeoutMs,
      });
      let current = job;
      for (let attemptIndex = 0; attemptIndex < 180; attemptIndex += 1) {
        if (current.status === 'succeeded' || current.status === 'failed') break;
        await new Promise((resolve) => window.setTimeout(resolve, 1800));
        current = await fetchQuizGenerationJob(apiBase, current.job_id, {
          timeoutMs: settings.requestTimeoutMs,
        });
      }
      if (current.status !== 'succeeded' || !current.quiz_id) {
        throw new Error(current.error || 'Quiz生成が完了しませんでした。時間をおいて再試行してください。');
      }
      notifications.update(notifId, {
        title: 'Quiz生成完了',
        status: 'success',
        message: '一覧を更新しました。',
      });
      setMessage({ kind: 'status', text: 'Quizを生成しました。生成結果を開いています。' });
      await loadList();
      setSelectedQuizId(current.quiz_id);
    } catch (error) {
      const text = error instanceof Error ? error.message : 'Quiz生成に失敗しました。';
      notifications.update(notifId, {
        title: 'Quiz生成失敗',
        status: 'error',
        message: text,
      });
      setMessage({ kind: 'alert', text });
    } finally {
      setGenerating(false);
    }
  };

  const handleDeleteQuiz = async (quiz: QuizListItem) => {
    const ok = window.confirm(`「${quiz.title_en}」を削除します。関連するAttempt履歴も削除され、元に戻せません。`);
    if (!ok) return;
    try {
      await deleteQuiz(apiBase, quiz.id, { timeoutMs: settings.requestTimeoutMs });
      setMessage({ kind: 'status', text: 'Quizを削除しました。' });
      if (selectedQuizId === quiz.id) {
        setSelectedQuizId(null);
        setSelectedQuiz(null);
      }
      await loadList();
    } catch (error) {
      const text = error instanceof ApiError ? error.message : 'Quizを削除できませんでした。';
      setMessage({ kind: 'alert', text });
    }
  };

  const handleToggleQuizPublic = async (quiz: QuizListItem) => {
    if (isGuest) return;
    const nextValue = !Boolean(quiz.guest_public);
    setItems((prev) => prev.map((item) => (
      item.id === quiz.id ? { ...item, guest_public: nextValue } : item
    )));
    setSelectedQuiz((prev) => (
      prev?.id === quiz.id ? { ...prev, guest_public: nextValue } : prev
    ));
    try {
      const response = await updateQuizGuestPublic(apiBase, quiz.id, nextValue, {
        timeoutMs: settings.requestTimeoutMs,
      });
      setItems((prev) => prev.map((item) => (
        item.id === quiz.id ? { ...item, guest_public: response.guest_public } : item
      )));
      setSelectedQuiz((prev) => (
        prev?.id === quiz.id ? { ...prev, guest_public: response.guest_public } : prev
      ));
      setMessage({
        kind: 'status',
        text: response.guest_public ? 'Quizをゲスト公開しました。' : 'Quizを非公開にしました。',
      });
    } catch (error) {
      setItems((prev) => prev.map((item) => (
        item.id === quiz.id ? { ...item, guest_public: Boolean(quiz.guest_public) } : item
      )));
      setSelectedQuiz((prev) => (
        prev?.id === quiz.id ? { ...prev, guest_public: Boolean(quiz.guest_public) } : prev
      ));
      const text = error instanceof ApiError ? error.message : 'Quizの公開設定を更新できませんでした。';
      setMessage({ kind: 'alert', text });
    }
  };

  const handleGrade = async () => {
    if (!selectedQuiz) return;
    if (isGuest) {
      setAttempt(buildLocalAttempt(selectedQuiz, answers));
      setMessage({ kind: 'status', text: 'ゲスト閲覧のため採点結果は保存していません。' });
      return;
    }
    const payload = {
      answers: questions.map((question) => ({
        question_id: question.id,
        selected_choice_id: answers[question.id] ?? null,
      })),
      started_at: null,
      elapsed_ms: null,
    };
    try {
      const response = await submitQuizAttempt(apiBase, selectedQuiz.id, payload, {
        timeoutMs: settings.requestTimeoutMs,
      });
      setAttempt(response);
      setMessage({ kind: 'status', text: `採点しました。${response.score}/${response.total} 問正解です。` });
    } catch (error) {
      const text = error instanceof ApiError ? error.message : '採点結果を保存できませんでした。';
      setMessage({ kind: 'alert', text });
    }
  };

  const openLemma = (lemma: string) => {
    const link = relatedLinks.find((item) => item.lemma.toLowerCase() === lemma.toLowerCase());
    if (link?.word_pack_id) {
      setPreviewWordPackId(link.word_pack_id);
      return;
    }
    setMessage({ kind: 'alert', text: `${lemma} はまだWordPackに接続されていません。本文中の語から作成または生成してください。` });
  };

  const createEmpty = async (lemma: string) => {
    if (isGuest) return;
    try {
      const response = await createEmptyWordPackRequest(apiBase, lemma, {
        timeoutMs: settings.requestTimeoutMs,
      });
      updateRelatedLink(lemma, { status: 'created', word_pack_id: response.id, is_empty: true });
      dispatchAppEvent(APP_EVENTS.wordPackUpdated);
      await loadWordPacks();
      setPreviewWordPackId(response.id);
      setMessage({ kind: 'status', text: `${lemma} の空WordPackを作成しました。` });
    } catch (error) {
      const text = error instanceof ApiError ? error.message : '空のWordPackを作成できませんでした。';
      setMessage({ kind: 'alert', text });
    }
  };

  const generateWordPack = async (lemma: string) => {
    if (isGuest) return;
    updateRelatedLink(lemma, { status: 'generated_requested' });
    const notifId = notifications.add({
      title: `【${lemma}】の生成処理中...`,
      message: 'Quiz本文からWordPack生成を開始しました。',
      status: 'progress',
      lemma,
    });
    try {
      const response = await generateWordPackRequest(apiBase, {
        lemma,
        pronunciation_enabled: settings.pronunciationEnabled,
        regenerate_scope: settings.regenerateScope,
        ...composeModelRequestFields({
          model: settings.model ?? 'gpt-5.4-mini',
          reasoningEffort: settings.reasoningEffort,
          textVerbosity: settings.textVerbosity,
        }),
      }, { timeoutMs: settings.requestTimeoutMs });
      updateRelatedLink(lemma, { status: 'existing', word_pack_id: response.id, is_empty: false });
      notifications.update(notifId, {
        title: `【${response.lemma}】の生成完了`,
        message: 'WordPackを開けます。',
        status: 'success',
        wordPackId: response.id ?? null,
        lemma: response.lemma,
      });
      dispatchAppEvent(APP_EVENTS.wordPackUpdated);
      await loadWordPacks();
      if (response.id) setPreviewWordPackId(response.id);
    } catch (error) {
      const text = error instanceof ApiError ? error.message : 'WordPack生成に失敗しました。';
      updateRelatedLink(lemma, { status: 'missing' });
      notifications.update(notifId, {
        title: `【${lemma}】の生成失敗`,
        message: text,
        status: 'error',
        lemma,
      });
      setMessage({ kind: 'alert', text });
    }
  };

  return (
    <div className="quiz-page dictionary-main">
      <div className="quiz-page__heading dictionary-page-heading">
        <div className="dictionary-page-title">
          <h2>Quiz</h2>
          <p>保存済みWordPackを、長文読解・解答・根拠確認につなげます。</p>
        </div>
        <div className="quiz-page__summary" aria-live="polite">
          <strong>{items.length}</strong>
          <span>保存済みQuiz</span>
        </div>
      </div>

      {message ? (
        <div className={`quiz-message is-${message.kind}`} role={message.kind === 'alert' ? 'alert' : 'status'}>
          {message.text}
        </div>
      ) : null}

      <div className={`quiz-workspace ${detailFocusMode ? 'is-detail-focus' : ''}`}>
        <form className="quiz-generator" onSubmit={handleCreateQuiz} aria-label="Quiz生成フォーム" hidden={detailFocusMode}>
          <div className="quiz-panel-heading">
            <div>
              <h3>長文読解クイズを生成</h3>
              <p>出題形式と題材を選び、含めたい語を指定します。</p>
            </div>
          </div>
          <label>
            出題フォーマット
            <select value={formatProfile} onChange={(event) => setFormatProfile(event.target.value as QuizFormatProfile)}>
              {FORMAT_PROFILE_OPTIONS.map((value) => <option key={value} value={value}>{FORMAT_PROFILE_LABELS[value]}</option>)}
            </select>
          </label>
          <label>
            生成傾向
            <select value={generationDomain} onChange={(event) => setGenerationDomain(event.target.value as QuizGenerationDomain)}>
              {GENERATION_DOMAIN_OPTIONS.map((value) => <option key={value} value={value}>{GENERATION_DOMAIN_LABELS[value]}</option>)}
            </select>
          </label>
          <div className="quiz-form-row">
            <label>
              専門性の強さ
              <select value={domainIntensity} onChange={(event) => setDomainIntensity(event.target.value as QuizDomainIntensity)}>
                {DOMAIN_INTENSITY_OPTIONS.map((value) => <option key={value} value={value}>{DOMAIN_INTENSITY_LABELS[value]}</option>)}
              </select>
            </label>
            <label>
              難易度
              <select value={difficulty} onChange={(event) => setDifficulty(event.target.value as QuizDifficulty)}>
                {DIFFICULTY_OPTIONS.map((value) => <option key={value} value={value}>{DIFFICULTY_LABELS[value]}</option>)}
              </select>
            </label>
          </div>
          <div className="quiz-form-row">
            <label>
              大問数
              <input type="number" min={1} max={4} value={sectionCount} onChange={(event) => setSectionCount(clampInteger(event.target.value, 1, 4))} />
            </label>
            <label>
              小問数/大問
              <input type="number" min={1} max={5} value={questionsPerSection} onChange={(event) => setQuestionsPerSection(clampInteger(event.target.value, 1, 5))} />
            </label>
          </div>
          <label>
            含めるWordPack
            <select
              multiple
              value={selectedWordPackIds}
              onChange={(event) => setSelectedWordPackIds(Array.from(event.currentTarget.selectedOptions).map((option) => option.value))}
              aria-describedby="quiz-wordpack-helper"
            >
              {generatedWordPacks.map((wordPack) => (
                <option key={wordPack.id} value={wordPack.id}>
                  {wordPack.lemma}{wordPack.sense_title ? ` / ${wordPack.sense_title}` : ''}
                </option>
              ))}
            </select>
          </label>
          <p id="quiz-wordpack-helper" className="quiz-helper">{wordPackHelperText}</p>
          <div className="quiz-field">
            <div className="quiz-field-heading">
              <label htmlFor="quiz-lemma-input">任意 lemma</label>
              <button
                type="button"
                className="quiz-secondary-button"
                onClick={handleAutoSetLemmas}
                disabled={autoLemmaCandidates.length === 0}
                aria-describedby="quiz-auto-lemma-helper"
              >
                お任せで3件セット
              </button>
            </div>
            <textarea
              id="quiz-lemma-input"
              value={lemmaInput}
              onChange={(event) => setLemmaInput(event.target.value)}
              rows={3}
              placeholder="mitigate, latency, trade-off"
              aria-describedby="quiz-auto-lemma-helper"
            />
            <p id="quiz-auto-lemma-helper" className="quiz-helper">{autoLemmaHelpText}</p>
          </div>
          <label>
            topic_seed
            <input value={topicSeed} onChange={(event) => setTopicSeed(event.target.value)} placeholder="API rate limiting" />
          </label>
          <label>
            avoid_topics
            <input value={avoidTopics} onChange={(event) => setAvoidTopics(event.target.value)} placeholder="malware, credential theft" />
          </label>
          {generationDisabled ? (
            <p className="quiz-input-error">含めるWordPackまたはlemmaを1件以上指定してください。</p>
          ) : null}
          <GuestLock isGuest={isGuest}>
            <button className="quiz-primary-button" type="submit" disabled={generating || generationDisabled}>
              {generating ? '生成中...' : '生成開始'}
            </button>
          </GuestLock>
        </form>

        <section className="quiz-list-panel" aria-label="保存済みQuiz" hidden={detailFocusMode}>
          <div className="quiz-panel-heading">
            <div>
              <h3>保存済みQuiz</h3>
              <p>{loadingList ? '読み込み中です。' : `${items.length}件を表示しています。`}</p>
            </div>
            <button type="button" onClick={() => void loadList()}>更新</button>
          </div>
          {items.length === 0 ? (
            <div className="quiz-empty-state">
              <strong>{isGuest ? 'ゲスト公開中のQuizはまだありません。' : '保存済みQuizはまだありません。'}</strong>
              <span>
                {isGuest
                  ? 'ログイン済みユーザーが公開したQuizだけがここに表示されます。'
                  : '左のフォームで対象語を指定し、長文読解クイズを生成してください。'}
              </span>
            </div>
          ) : (
            <div className="quiz-list">
              {items.map((item) => (
                <article key={item.id} className={`quiz-list-item ${selectedQuizId === item.id ? 'is-selected' : ''}`}>
                  <button type="button" onClick={() => setSelectedQuizId(item.id)}>
                    <strong>{item.title_en}</strong>
                    <span>{FORMAT_PROFILE_LABELS[item.format_profile]} / {GENERATION_DOMAIN_LABELS[item.generation_domain]} / {DOMAIN_INTENSITY_LABELS[item.domain_intensity]}</span>
                    <small>{item.question_count}問・{item.passage_count}本文・{formatDate(item.updated_at)}</small>
                  </button>
                  <div className="quiz-public-row">
                    <span className={`quiz-public-pill ${item.guest_public ? 'is-public' : 'is-private'}`}>
                      {item.guest_public ? '公開中' : '非公開'}
                    </span>
                    {!isGuest ? (
                      <button
                        type="button"
                        className="quiz-secondary-button"
                        onClick={() => void handleToggleQuizPublic(item)}
                      >
                        {item.guest_public ? '非公開にする' : '公開にする'}
                      </button>
                    ) : null}
                  </div>
                  <div className="quiz-list-item__lemmas">
                    {item.source_lemmas.slice(0, 5).map((lemma) => <span key={lemma}>{lemma}</span>)}
                  </div>
                  <GuestLock isGuest={isGuest}>
                    <button type="button" className="quiz-danger-button" onClick={() => void handleDeleteQuiz(item)}>
                      削除
                    </button>
                  </GuestLock>
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="quiz-detail-panel" aria-label="選択中Quiz詳細">
          {loadingDetail ? (
            <div className="quiz-empty-state"><strong>Quiz詳細を読み込み中です。</strong></div>
          ) : selectedQuiz ? (
            <>
              <div className="quiz-detail-header">
                <div>
                  <p className="quiz-question__meta">
                    {FORMAT_PROFILE_LABELS[selectedQuiz.format_profile]} / {GENERATION_DOMAIN_LABELS[selectedQuiz.generation_domain]} / {DIFFICULTY_LABELS[selectedQuiz.difficulty]}
                  </p>
                  <h3>{selectedQuiz.title_en}</h3>
                  <p>{selectedQuiz.notes_ja || '本文を読み、設問に答えてから根拠を確認します。'}</p>
                </div>
                <div className="quiz-detail-actions">
                  <button
                    type="button"
                    className="quiz-focus-toggle"
                    aria-pressed={detailFocusMode}
                    onClick={() => setDetailFocusMode((prev) => !prev)}
                  >
                    {detailFocusMode ? '3カラムに戻す' : '本文/問題を広げる'}
                  </button>
                  <div className="quiz-attempt-summary" aria-live="polite">
                    <strong>{attempt ? `${attempt.score}/${attempt.total}` : `未回答 ${unansweredCount}`}</strong>
                    <span>{attempt ? `${Math.round(attempt.percentage)}%` : '採点前'}</span>
                    <GuestLock isGuest={false}>
                      <button type="button" className="quiz-primary-button" onClick={() => void handleGrade()} disabled={Boolean(attempt)}>
                        採点する
                      </button>
                    </GuestLock>
                  </div>
                </div>
              </div>
              {isGuest ? (
                <div className="quiz-guest-note" role="note">
                  <strong>ゲスト閲覧では保存できません</strong>
                  <span>読むだけなら利用できます。採点結果やWordPack作成を保存するにはログインしてください。</span>
                </div>
              ) : null}
              {linkWarnings.length ? (
                <div className="quiz-warning-list" role="status" aria-label="Quiz生成時の注意">
                  <strong>生成時の注意</strong>
                  {linkWarnings.map((link) => (
                    <span key={`${link.lemma}-${link.status}`}>{link.warning}</span>
                  ))}
                </div>
              ) : null}
              <div className="quiz-passages">
                {selectedQuiz.passages
                  .slice()
                  .sort((a, b) => a.order - b.order)
                  .map((passage) => (
                    <QuizPassageArticle
                      key={`${selectedQuiz.id}:${passage.id}`}
                      passage={passage}
                      links={relatedLinks}
                      isGuest={isGuest}
                      onOpenWordPack={setPreviewWordPackId}
                      onCreateEmpty={createEmpty}
                      onGenerate={generateWordPack}
                    />
                  ))}
              </div>
              <div className="quiz-sections">
                {selectedQuiz.sections
                  .slice()
                  .sort((a, b) => a.order - b.order)
                  .map((section) => (
                    <section key={section.id} className="quiz-section">
                      <div className="quiz-section__heading">
                        <h4>{section.title}</h4>
                        {section.description_ja ? <p>{section.description_ja}</p> : null}
                      </div>
                      {section.questions
                        .slice()
                        .sort((a, b) => a.order - b.order)
                        .map((question) => (
                          <QuizQuestionCard
                            key={question.id}
                            section={section}
                            question={question}
                            answer={answers[question.id] ?? null}
                            reviewResult={resultMap[question.id]}
                            onAnswer={(questionId, choiceId) => setAnswers((prev) => ({ ...prev, [questionId]: choiceId }))}
                            onRelatedLemma={openLemma}
                          />
                        ))}
                    </section>
                  ))}
              </div>
            </>
          ) : (
            <div className="quiz-empty-state">
              <strong>Quizを選択してください。</strong>
              <span>生成済みQuizを選ぶと、本文・設問・復習情報を表示します。</span>
            </div>
          )}
        </section>
      </div>

      <WordPackPreviewModal
        isOpen={Boolean(previewWordPackId)}
        onClose={() => setPreviewWordPackId(null)}
        wordPackId={previewWordPackId}
        wordPacks={wordPacks}
        onWordPackUpdated={() => {
          dispatchAppEvent(APP_EVENTS.wordPackUpdated);
          void loadWordPacks();
        }}
        contextLabel="Quiz"
        contextDescription="Quiz本文または解説から開いたWordPackです。"
      />
    </div>
  );
};
