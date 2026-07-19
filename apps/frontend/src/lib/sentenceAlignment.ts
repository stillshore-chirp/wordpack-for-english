export type SentenceLanguage = 'en' | 'ja';

export interface SentenceSegment {
  key: string;
  pairKey: string | null;
  displayIndex: number;
  text: string;
  start: number;
  end: number;
}

export interface SentenceParagraph {
  key: string;
  sentences: SentenceSegment[];
}

export interface SentenceAlignment {
  englishParagraphs: SentenceParagraph[];
  japaneseParagraphs: SentenceParagraph[];
}

const paragraphBreakPattern = /((?:\r?\n)[\t ]*(?:\r?\n)+)/g;
const englishSentencePattern = /[^.!?]+[.!?]+["')\]]*|[^.!?]+$/g;
const japaneseSentencePattern = /[^。！？!?]+[。！？!?]+["'）】」』]*|[^。！？!?]+$/gu;

type SentenceSegmenter = {
  segment: (input: string) => Iterable<{ segment: string; index: number }>;
};

const getEnglishSentenceSegmenter = (): SentenceSegmenter | null => {
  const SegmenterCtor = (Intl as unknown as {
    Segmenter?: new (locale: string, options: { granularity: 'sentence' }) => SentenceSegmenter;
  }).Segmenter;
  return typeof SegmenterCtor === 'function' ? new SegmenterCtor('en', { granularity: 'sentence' }) : null;
};

const trimSentenceSegment = (
  raw: string,
  absoluteStart: number,
): { text: string; start: number; end: number } | null => {
  const leading = raw.match(/^\s*/)?.[0].length ?? 0;
  const trailing = raw.match(/\s*$/)?.[0].length ?? 0;
  const start = absoluteStart + leading;
  const end = absoluteStart + raw.length - trailing;
  if (end <= start) return null;
  return { text: raw.slice(leading, raw.length - trailing), start, end };
};

export const splitTextSentences = (
  text: string,
  paragraphStart: number,
  language: SentenceLanguage,
): Array<{ text: string; start: number; end: number }> => {
  if (language === 'en') {
    const segmenter = getEnglishSentenceSegmenter();
    if (segmenter) {
      const segmented = Array.from(segmenter.segment(text))
        .map((segment) => trimSentenceSegment(segment.segment, paragraphStart + segment.index))
        .filter((sentence): sentence is { text: string; start: number; end: number } => Boolean(sentence));
      if (segmented.length) return segmented;
    }
  }

  const pattern = language === 'ja'
    ? new RegExp(japaneseSentencePattern.source, japaneseSentencePattern.flags)
    : new RegExp(englishSentencePattern.source, englishSentencePattern.flags);
  const sentences: Array<{ text: string; start: number; end: number }> = [];
  let match = pattern.exec(text);
  while (match) {
    const sentence = trimSentenceSegment(match[0], paragraphStart + match.index);
    if (sentence) sentences.push(sentence);
    match = pattern.exec(text);
  }
  if (sentences.length) return sentences;

  const fallback = text.trim();
  if (!fallback) return [];
  const start = paragraphStart + (text.match(/^\s*/)?.[0].length ?? 0);
  return [{ text: fallback, start, end: start + fallback.length }];
};

export const buildLanguageParagraphs = (value: string, language: SentenceLanguage): SentenceParagraph[] => {
  const chunks = value.split(paragraphBreakPattern);
  const paragraphs: SentenceParagraph[] = [];
  let cursor = 0;
  let sentenceCounter = 0;

  chunks.forEach((chunk) => {
    if (!chunk) return;
    if (new RegExp(paragraphBreakPattern.source).test(chunk)) {
      cursor += chunk.length;
      return;
    }

    const leading = chunk.match(/^\s*/)?.[0].length ?? 0;
    const trailing = chunk.match(/\s*$/)?.[0].length ?? 0;
    const start = cursor + leading;
    const end = cursor + chunk.length - trailing;
    if (end > start) {
      const paragraphIndex = paragraphs.length;
      const paragraphText = value.slice(start, end);
      const sentences = splitTextSentences(paragraphText, start, language).map((sentence, sentenceIndex) => {
        sentenceCounter += 1;
        return {
          key: `${language}-p${paragraphIndex}-s${sentenceIndex}`,
          pairKey: null,
          displayIndex: sentenceCounter,
          ...sentence,
        };
      });
      if (sentences.length) {
        paragraphs.push({
          key: `${language}-p${paragraphIndex}`,
          sentences,
        });
      }
    }
    cursor += chunk.length;
  });

  return paragraphs;
};

export const flattenSentenceParagraphs = (paragraphs: SentenceParagraph[]) => (
  paragraphs.flatMap((paragraph) => paragraph.sentences)
);

export const countSentencePairs = (alignment: SentenceAlignment): number => {
  const englishPairedCount = flattenSentenceParagraphs(alignment.englishParagraphs)
    .filter((sentence) => Boolean(sentence.pairKey)).length;
  const japanesePairedCount = flattenSentenceParagraphs(alignment.japaneseParagraphs)
    .filter((sentence) => Boolean(sentence.pairKey)).length;
  return Math.min(englishPairedCount, japanesePairedCount);
};

const regroupJapaneseParagraphs = (
  englishParagraphs: SentenceParagraph[],
  japaneseParagraphs: SentenceParagraph[],
): SentenceParagraph[] => {
  if (englishParagraphs.length <= 1 || japaneseParagraphs.length === englishParagraphs.length) {
    return japaneseParagraphs;
  }
  const englishCounts = englishParagraphs.map((paragraph) => paragraph.sentences.length);
  const englishSentenceTotal = englishCounts.reduce((sum, count) => sum + count, 0);
  const japaneseSentences = flattenSentenceParagraphs(japaneseParagraphs);
  if (japaneseSentences.length !== englishSentenceTotal) {
    return japaneseParagraphs;
  }

  let cursor = 0;
  return englishCounts.map((count, paragraphIndex) => {
    const sentences = japaneseSentences.slice(cursor, cursor + count).map((sentence, sentenceIndex) => ({
      ...sentence,
      key: `ja-p${paragraphIndex}-s${sentenceIndex}`,
    }));
    cursor += count;
    return {
      key: `ja-p${paragraphIndex}`,
      sentences,
    };
  });
};

const assignPairKeys = (
  englishParagraphs: SentenceParagraph[],
  japaneseParagraphs: SentenceParagraph[],
): SentenceAlignment => {
  const englishSentences = flattenSentenceParagraphs(englishParagraphs);
  const japaneseSentences = flattenSentenceParagraphs(japaneseParagraphs);
  const pairableCount = Math.min(englishSentences.length, japaneseSentences.length);
  const applyPairKeys = (paragraphs: SentenceParagraph[]) => paragraphs.map((paragraph) => ({
    ...paragraph,
    sentences: paragraph.sentences.map((sentence) => {
      const pairIndex = sentence.displayIndex - 1;
      return {
        ...sentence,
        pairKey: pairIndex < pairableCount ? `sentence-${pairIndex + 1}` : null,
      };
    }),
  }));

  return {
    englishParagraphs: applyPairKeys(englishParagraphs),
    japaneseParagraphs: applyPairKeys(japaneseParagraphs),
  };
};

export const buildSentenceAlignment = (bodyEn: string, bodyJa?: string | null): SentenceAlignment => {
  const englishParagraphs = buildLanguageParagraphs(bodyEn, 'en');
  const japaneseBaseParagraphs = bodyJa ? buildLanguageParagraphs(bodyJa, 'ja') : [];
  const japaneseParagraphs = regroupJapaneseParagraphs(englishParagraphs, japaneseBaseParagraphs);
  return assignPairKeys(englishParagraphs, japaneseParagraphs);
};

export const createManualSentenceSegment = (
  key: string,
  pairKey: string | null,
  displayIndex: number,
  text: string,
): SentenceSegment => ({
  key,
  pairKey,
  displayIndex,
  text,
  start: 0,
  end: text.length,
});
