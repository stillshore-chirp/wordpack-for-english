import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import ArticleDetailModal, { ArticleDetailData } from './ArticleDetailModal';
import * as AuthContext from '../AuthContext';

describe('ArticleDetailModal', () => {
  beforeEach(() => {
    vi.spyOn(AuthContext, 'useAuth').mockReturnValue({ isGuest: false } as any);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('displays article metadata below related word packs', () => {
    const article: ArticleDetailData = {
      id: 'art:test',
      title_en: 'Sample Title',
      body_en: 'English body',
      body_ja: '日本語本文',
      notes_ja: '補足',
      llm_model: 'gpt-5.4-mini',
      llm_params: 'reasoning.effort=minimal;text.verbosity=medium',
      generation_category: 'Dev',
      created_at: '2024-05-01T10:00:00+09:00',
      updated_at: '2024-05-01T10:01:05+09:00',
      generation_started_at: '2024-05-01T10:00:00+09:00',
      generation_completed_at: '2024-05-01T10:01:05+09:00',
      generation_duration_ms: 65_000,
      warnings: ['Resilient: Firestore 検索が不安定だったためプレースホルダーを生成しました。'],
      related_word_packs: [
        { word_pack_id: 'wp:1', lemma: 'alpha', status: 'existing' },
      ],
    };

    render(
      <ArticleDetailModal
        isOpen
        onClose={() => {}}
        title="文章プレビュー"
        article={article}
        onSelectWordPackPreview={() => {}}
      />,
    );

    expect(screen.getByRole('button', { name: '記事本文の音声' })).toBeInTheDocument();
    const meta = screen.getByTestId('article-meta');
    expect(meta.tagName.toLowerCase()).toBe('dl');
    expect(screen.getByText('生成・管理情報')).toBeInTheDocument();
    expect(meta).toHaveTextContent('作成');
    expect(meta).toHaveTextContent('更新');
    expect(meta).toHaveTextContent('生成所要時間');
    expect(meta).toHaveTextContent('生成カテゴリ');
    expect(meta).toHaveTextContent('AIモデル');
    expect(meta).toHaveTextContent('AIパラメータ');
    expect(meta).toHaveTextContent('gpt-5.4-mini');
    expect(meta).toHaveTextContent('reasoning.effort=minimal;text.verbosity=medium');
    expect(meta).toHaveTextContent('2024/05/01 10:00');
    expect(meta).toHaveTextContent('1分5秒');
    expect(meta).toHaveTextContent('Dev（開発）');
    expect(screen.getByLabelText('インポート警告')).toHaveTextContent('Resilient');
    const heading = screen.getByRole('heading', { level: 4, name: '関連WordPack' });
    expect(heading).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'WordPack「alpha」をプレビュー' })).toBeInTheDocument();
    // メタ情報が「関連WordPack」見出しより後に来ることを確認
    expect(heading.compareDocumentPosition(meta) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('highlights paired English and Japanese article sentences', async () => {
    const article: ArticleDetailData = {
      id: 'art:highlight',
      title_en: 'Sentence Pairing',
      body_en: 'The cache serves fresh data. The platform keeps latency low.',
      body_ja: 'キャッシュは新しいデータを提供します。プラットフォームは低遅延を保ちます。',
      related_word_packs: [],
    };
    const user = userEvent.setup();

    render(
      <ArticleDetailModal
        isOpen
        onClose={() => {}}
        article={article}
      />,
    );

    const englishSecondSentence = screen.getByRole('group', { name: '英文 2: 日本語訳と対応' });
    const japaneseSecondSentence = screen.getByRole('group', { name: '日本語訳 2: 英文と対応' });

    await user.hover(englishSecondSentence);

    await waitFor(() => {
      expect(englishSecondSentence).toHaveClass('is-active');
      expect(japaneseSecondSentence).toHaveClass('is-active');
    });

    await user.unhover(englishSecondSentence);
    await user.click(japaneseSecondSentence);

    await waitFor(() => {
      expect(englishSecondSentence).toHaveClass('is-pinned');
      expect(japaneseSecondSentence).toHaveClass('is-pinned');
    });
  });

  it('does not enable sentence highlighting for a single-sentence article', () => {
    const article: ArticleDetailData = {
      id: 'art:single-sentence',
      title_en: 'Single Sentence',
      body_en: 'Only one sentence is available.',
      body_ja: '利用できる文は1つだけです。',
      related_word_packs: [],
    };

    render(
      <ArticleDetailModal
        isOpen
        onClose={() => {}}
        article={article}
      />,
    );

    expect(screen.queryByRole('group', { name: '英文 1: 日本語訳と対応' })).not.toBeInTheDocument();
    expect(screen.queryByRole('group', { name: '日本語訳 1: 英文と対応' })).not.toBeInTheDocument();
    const sentence = screen.getByLabelText('英文本文').querySelector('.sentence-pair-highlight');
    expect(sentence).toBeInTheDocument();
    expect(sentence).not.toHaveClass('is-paired');
  });

  it('preserves imported article line breaks while highlighting sentences', () => {
    const article: ArticleDetailData = {
      id: 'art:line-breaks',
      title_en: 'Line Breaks',
      body_en: 'First line stays.\nSecond line stays.',
      body_ja: '1行目を保持します。\n2行目を保持します。',
      related_word_packs: [],
    };

    render(
      <ArticleDetailModal
        isOpen
        onClose={() => {}}
        article={article}
      />,
    );

    expect(screen.getByLabelText('英文本文').textContent).toBe(article.body_en);
    expect(screen.getByLabelText('日本語訳本文').textContent).toBe(article.body_ja);
    expect(screen.getByRole('group', { name: '英文 2: 日本語訳と対応' })).toHaveTextContent('Second line stays.');
  });

  it('clears pinned article sentence when the article changes', async () => {
    const firstArticle: ArticleDetailData = {
      id: 'art:first',
      title_en: 'First Article',
      body_en: 'First article opens. First article pins.',
      body_ja: '最初の記事を開きます。最初の記事を固定します。',
      related_word_packs: [],
    };
    const secondArticle: ArticleDetailData = {
      id: 'art:second',
      title_en: 'Second Article',
      body_en: 'Second article opens. Second article stays clear.',
      body_ja: '2つ目の記事を開きます。2つ目の記事は固定されません。',
      related_word_packs: [],
    };
    const user = userEvent.setup();

    const { rerender } = render(
      <ArticleDetailModal
        isOpen
        onClose={() => {}}
        article={firstArticle}
      />,
    );

    const pinnedSentence = screen.getByRole('group', { name: '日本語訳 2: 英文と対応' });
    await user.click(pinnedSentence);

    await waitFor(() => {
      expect(screen.getByRole('group', { name: '英文 2: 日本語訳と対応' })).toHaveClass('is-pinned');
    });

    rerender(
      <ArticleDetailModal
        isOpen
        onClose={() => {}}
        article={secondArticle}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole('group', { name: '英文 2: 日本語訳と対応' })).not.toHaveClass('is-pinned');
      expect(screen.getByRole('group', { name: '日本語訳 2: 英文と対応' })).not.toHaveClass('is-pinned');
    });
  });

  it('selects a related WordPack preview inside the article dialog', async () => {
    const article: ArticleDetailData = {
      id: 'art:preview',
      title_en: 'Preview Source',
      body_en: 'English body',
      body_ja: '日本語本文',
      related_word_packs: [{ word_pack_id: 'wp:1', lemma: 'alpha', status: 'existing' }],
    };
    const onSelectWordPackPreview = vi.fn();
    const user = userEvent.setup();

    render(
      <ArticleDetailModal
        isOpen
        onClose={() => {}}
        article={article}
        onSelectWordPackPreview={onSelectWordPackPreview}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'WordPack「alpha」をプレビュー' }));

    expect(onSelectWordPackPreview).toHaveBeenCalledWith('wp:1');
  });

  it('falls back to 0秒 when created_at and updated_at are identical', () => {
    const article: ArticleDetailData = {
      id: 'art:zero',
      title_en: 'Zero Duration',
      body_en: 'English body',
      body_ja: '日本語本文',
      related_word_packs: [],
      created_at: '2024-05-01T10:00:00+09:00',
      updated_at: '2024-05-01T10:00:00+09:00',
      generation_duration_ms: 0,
    };

    render(
      <ArticleDetailModal
        isOpen
        onClose={() => {}}
        article={article}
      />,
    );

    const meta = screen.getByTestId('article-meta');
    expect(meta).toHaveTextContent('0秒');
    expect(meta).toHaveTextContent('未指定');
    expect(meta).toHaveTextContent('未記録');
  });

  it('keeps the "生成" button right-aligned when wrapped by GuestLock', () => {
    const article: ArticleDetailData = {
      id: 'art:wp-actions',
      title_en: 'Title',
      body_en: 'English body',
      body_ja: '日本語本文',
      related_word_packs: [{ word_pack_id: 'wp:1', lemma: 'alpha', status: 'existing' }],
    };

    render(
      <ArticleDetailModal
        isOpen
        onClose={() => {}}
        article={article}
        onRegenerateWordPack={() => {}}
      />,
    );

    const button = screen.getByRole('button', { name: '例文を生成' });
    const wrapper = button.parentElement as HTMLElement;
    // GuestLock wrapper が flex item になるため、autoマージンは wrapper 側に必要
    expect(wrapper).toHaveStyle({ marginLeft: 'auto' });
  });

  it('shows an explicit empty state when no related WordPack exists', () => {
    const article: ArticleDetailData = {
      id: 'art:no-related',
      title_en: 'No Related',
      body_en: 'English body',
      body_ja: '日本語本文',
      related_word_packs: [],
    };

    render(
      <ArticleDetailModal
        isOpen
        onClose={() => {}}
        article={article}
      />,
    );

    expect(screen.getByText('関連WordPack')).toBeInTheDocument();
    expect(screen.getByText(/この記事に紐づくWordPackはまだありません/)).toBeInTheDocument();
  });
});
