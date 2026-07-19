import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { ExamplesSection } from './ExamplesSection';
import * as AuthContext from '../../AuthContext';
import type { WordPack } from '../../hooks/useWordPack';

describe('ExamplesSection', () => {
  const data: WordPack = {
    lemma: 'alpha',
    sense_title: '初期検証版',
    pronunciation: { linking_notes: [] },
    senses: [],
    collocations: { general: { verb_object: [], adj_noun: [], prep_noun: [] }, academic: { verb_object: [], adj_noun: [], prep_noun: [] } },
    contrast: [],
    examples: {
      Dev: [
        {
          en: 'The alpha build exposed navigation issues before the public beta started.',
          ja: 'アルファ版は公開ベータが始まる前にナビゲーション上の問題を明らかにした。',
          grammar_ja: '解説：exposed は問題発見の文脈に合います。',
        },
      ],
      CS: [],
      LLM: [],
      Business: [],
      Common: [],
    },
    etymology: { note: '', confidence: 'medium' },
    study_card: 'alpha release は初期検証版。',
    citations: [],
    confidence: 'medium',
  };
  const multiSentenceData: WordPack = {
    ...data,
    examples: {
      ...data.examples,
      Dev: [
        {
          ...data.examples.Dev[0]!,
          en: 'The alpha build exposed navigation issues. The beta team fixed them quickly.',
          ja: 'アルファ版はナビゲーション上の問題を明らかにした。ベータチームはそれらをすぐに修正した。',
        },
      ],
    },
  };

  beforeEach(() => {
    vi.spyOn(AuthContext, 'useAuth').mockReturnValue({ isGuest: false } as any);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('keeps copy available for unsaved generated WordPacks', async () => {
    const onCopyExampleText = vi.fn().mockResolvedValue(undefined);

    render(
      <ExamplesSection
        data={data}
        currentWordPackId={null}
        isActionLoading={false}
        onGenerateExamples={vi.fn()}
        onDeleteExample={vi.fn()}
        onImportArticleFromExample={vi.fn()}
        onCopyExampleText={onCopyExampleText}
        onLemmaOpen={vi.fn()}
        lookupLemmaMetadata={vi.fn()}
        triggerUnknownLemmaGeneration={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: 'alphaのDev例文1を削除' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'alphaのDev例文1から記事を作成' })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'alphaのDev例文1をコピー' }));

    expect(onCopyExampleText).toHaveBeenCalledWith('Dev', 0);
  });

  it('highlights paired sentences in WordPack examples without taking over the English word action', async () => {
    const onLemmaOpen = vi.fn();
    const user = userEvent.setup();
    const { container } = render(
      <ExamplesSection
        data={multiSentenceData}
        currentWordPackId="wp:alpha"
        isActionLoading={false}
        onGenerateExamples={vi.fn()}
        onDeleteExample={vi.fn()}
        onImportArticleFromExample={vi.fn()}
        onCopyExampleText={vi.fn()}
        onLemmaOpen={onLemmaOpen}
        lookupLemmaMetadata={vi.fn()}
        triggerUnknownLemmaGeneration={vi.fn()}
      />,
    );

    const englishSentence = container.querySelectorAll('.ex-en .sentence-pair-highlight')[1] as HTMLElement;
    const japaneseSentence = screen.getByRole('group', { name: '日本語訳 2: 英文と対応' });
    expect(englishSentence).toBeInTheDocument();

    await user.hover(englishSentence);

    await waitFor(() => {
      expect(englishSentence).toHaveClass('is-active');
      expect(japaneseSentence).toHaveClass('is-active');
    });

    await user.unhover(englishSentence);
    await user.click(japaneseSentence);

    await waitFor(() => {
      expect(englishSentence).toHaveClass('is-pinned');
      expect(japaneseSentence).toHaveClass('is-pinned');
    });

    await user.click(screen.getByRole('button', { name: 'Devカテゴリの例文1の語句から関連WordPackを開く' }));

    expect(onLemmaOpen).toHaveBeenCalledWith('alpha');
  });

  it('does not highlight a single-sentence WordPack example', () => {
    const { container } = render(
      <ExamplesSection
        data={data}
        currentWordPackId="wp:alpha"
        isActionLoading={false}
        onGenerateExamples={vi.fn()}
        onDeleteExample={vi.fn()}
        onImportArticleFromExample={vi.fn()}
        onCopyExampleText={vi.fn()}
        onLemmaOpen={vi.fn()}
        lookupLemmaMetadata={vi.fn()}
        triggerUnknownLemmaGeneration={vi.fn()}
      />,
    );

    expect(screen.queryByRole('group', { name: '日本語訳 1: 英文と対応' })).not.toBeInTheDocument();
    const englishSentence = container.querySelector('.ex-en .sentence-pair-highlight');
    const japaneseSentence = container.querySelector('.ex-ja .sentence-pair-highlight');
    expect(englishSentence).toBeInTheDocument();
    expect(japaneseSentence).toBeInTheDocument();
    expect(englishSentence).not.toHaveClass('is-paired');
    expect(japaneseSentence).not.toHaveClass('is-paired');
  });
});
