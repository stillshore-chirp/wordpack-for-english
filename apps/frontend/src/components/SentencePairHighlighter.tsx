import React, { useEffect, useState } from 'react';
import type { SentenceLanguage, SentenceParagraph, SentenceSegment } from '../lib/sentenceAlignment';

export interface SentencePairHighlightState {
  enabled: boolean;
  activePairKey: string | null;
  pinnedPairKey: string | null;
  hoverPair: (key: string | null) => void;
  togglePinnedPair: (key: string) => void;
  clearPairs: () => void;
}

export const useSentencePairHighlight = (
  enabled = true,
  resetKey: string | number | null = null,
): SentencePairHighlightState => {
  const [hoveredPairKey, setHoveredPairKey] = useState<string | null>(null);
  const [pinnedPairKey, setPinnedPairKey] = useState<string | null>(null);
  const [currentResetKey, setCurrentResetKey] = useState<string | number | null>(resetKey);
  const isCurrentScope = currentResetKey === resetKey;

  useEffect(() => {
    setCurrentResetKey(resetKey);
    setHoveredPairKey(null);
    setPinnedPairKey(null);
  }, [enabled, resetKey]);

  return {
    enabled,
    activePairKey: enabled && isCurrentScope ? hoveredPairKey ?? pinnedPairKey : null,
    pinnedPairKey: enabled && isCurrentScope ? pinnedPairKey : null,
    hoverPair: (key) => {
      if (enabled && isCurrentScope) setHoveredPairKey(key);
    },
    togglePinnedPair: (key) => {
      if (!enabled || !isCurrentScope) return;
      setPinnedPairKey((current) => (current === key ? null : key));
    },
    clearPairs: () => {
      setHoveredPairKey(null);
      setPinnedPairKey(null);
    },
  };
};

export const sentencePairLabel = (language: SentenceLanguage, sentence: SentenceSegment) => (
  language === 'en'
    ? `英文 ${sentence.displayIndex}: 日本語訳と対応`
    : `日本語訳 ${sentence.displayIndex}: 英文と対応`
);

const shouldIgnoreSentenceClick = (target: EventTarget | null, currentTarget: HTMLElement): boolean => {
  if (!(target instanceof Element) || target === currentTarget) return false;
  return Boolean(target.closest('button, a, input, select, textarea, summary, [role="button"], [data-sentence-pair-ignore]'));
};

export const SentencePairSpan: React.FC<{
  sentence: SentenceSegment;
  language: SentenceLanguage;
  highlight: SentencePairHighlightState;
  className?: string;
  label?: string;
  interactive?: boolean;
  children: React.ReactNode;
}> = ({
  sentence,
  language,
  highlight,
  className,
  label,
  interactive = true,
  children,
}) => {
  const enabled = highlight.enabled && Boolean(sentence.pairKey);
  const pairKey = sentence.pairKey;
  const isActive = enabled && highlight.activePairKey === pairKey;
  const isPinned = enabled && highlight.pinnedPairKey === pairKey;
  const handleKeyDown = (event: React.KeyboardEvent<HTMLSpanElement>) => {
    if (!enabled || !interactive || !pairKey) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      highlight.togglePinnedPair(pairKey);
    }
  };

  const classes = [
    'sentence-pair-highlight',
    className,
    enabled ? 'is-paired' : '',
    isActive ? 'is-active' : '',
    isPinned ? 'is-pinned' : '',
  ].filter(Boolean).join(' ');

  return (
    <span
      className={classes}
      role={enabled && interactive ? 'group' : undefined}
      tabIndex={enabled && interactive ? 0 : undefined}
      aria-label={enabled && interactive ? label ?? sentencePairLabel(language, sentence) : undefined}
      onMouseEnter={() => {
        if (enabled && pairKey) highlight.hoverPair(pairKey);
      }}
      onMouseLeave={() => {
        if (enabled) highlight.hoverPair(null);
      }}
      onFocus={() => {
        if (enabled && pairKey) highlight.hoverPair(pairKey);
      }}
      onBlur={() => {
        if (enabled) highlight.hoverPair(null);
      }}
      onClick={(event) => {
        if (!enabled || !interactive || !pairKey || shouldIgnoreSentenceClick(event.target, event.currentTarget)) return;
        highlight.togglePinnedPair(pairKey);
      }}
      onKeyDown={handleKeyDown}
    >
      {children}
    </span>
  );
};

export const SentencePairParagraphs: React.FC<{
  paragraphs: SentenceParagraph[];
  language: SentenceLanguage;
  highlight: SentencePairHighlightState;
  paragraphClassName?: string;
  sentenceClassName?: string;
  sentenceInteractive?: boolean;
  preserveWhitespaceFrom?: string;
  renderSentence?: (sentence: SentenceSegment) => React.ReactNode;
}> = ({
  paragraphs,
  language,
  highlight,
  paragraphClassName,
  sentenceClassName,
  sentenceInteractive = true,
  preserveWhitespaceFrom,
  renderSentence,
}) => (
  <>
    {paragraphs.map((paragraph) => {
      let cursor = paragraph.sentences[0]?.start ?? 0;
      return (
        <p key={paragraph.key} className={paragraphClassName}>
          {paragraph.sentences.map((sentence, sentenceIndex) => {
            const preservedWhitespace = preserveWhitespaceFrom
              ? preserveWhitespaceFrom.slice(cursor, sentence.start)
              : null;
            cursor = sentence.end;
            return (
              <React.Fragment key={sentence.key}>
                {preservedWhitespace}
                <SentencePairSpan
                  sentence={sentence}
                  language={language}
                  highlight={highlight}
                  className={sentenceClassName}
                  interactive={sentenceInteractive}
                >
                  {renderSentence ? renderSentence(sentence) : sentence.text}
                </SentencePairSpan>
                {!preserveWhitespaceFrom && sentenceIndex < paragraph.sentences.length - 1 ? ' ' : null}
              </React.Fragment>
            );
          })}
        </p>
      );
    })}
  </>
);
