import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';
import { NotificationsProvider } from '../../NotificationsContext';
import { ExplorePage } from './index';
import type { WordPack } from '../../features/wordpack/types';

const authState = vi.hoisted(() => ({ isGuest: false }));

vi.mock('../../AuthContext', () => ({
  useAuth: () => ({
    isGuest: authState.isGuest,
  }),
}));

vi.mock('../../SettingsContext', () => ({
  DEFAULT_GENERATION_REQUEST_TIMEOUT_MS: 1_500_000,
  useSettings: () => ({
    settings: {
      apiBase: '/api',
      requestTimeoutMs: 60000,
      generationRequestTimeoutMs: 1_500_000,
    },
  }),
  useOptionalSettings: () => ({
    settings: {
      apiBase: '/api',
      requestTimeoutMs: 60000,
      generationRequestTimeoutMs: 1_500_000,
    },
  }),
}));

vi.mock('../../components/WordPackPreviewModal', () => ({
  WordPackPreviewModal: ({ isOpen, wordPackId }: { isOpen: boolean; wordPackId: string | null }) => (
    isOpen ? <div role="dialog" aria-label="WordPack プレビュー">Preview {wordPackId}</div> : null
  ),
}));

const wordPackDetail: WordPack = {
  lemma: 'robust',
  sense_title: '壊れにくい',
  pronunciation: { linking_notes: [] },
  senses: [
    {
      id: 's1',
      gloss_ja: '壊れにくい',
      patterns: ['robust against N'],
      synonyms: ['resilient'],
      antonyms: ['fragile'],
    },
  ],
  collocations: {
    general: {
      verb_object: [],
      adj_noun: ['robust fallback', 'robust evidence'],
      prep_noun: [],
    },
    academic: {
      verb_object: [],
      adj_noun: [],
      prep_noun: [],
    },
  },
  contrast: [{ with: 'brittle', diff_ja: 'brittle は壊れやすさを示す。' }],
  examples: {
    Dev: [{ en: 'This sentence, with punctuation, should not become a WordPack.', ja: '句読点を含む文全体は見出し語ではない。' }],
    CS: [],
    LLM: [],
    Business: [],
    Common: [],
  },
  etymology: { note: 'test', confidence: 'low' },
  study_card: 'test',
  citations: [],
  confidence: 'low',
};

const setupFetch = () => {
  let createdPack: { id: string; lemma: string } | null = null;
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString();
    if (url === '/api/word/packs' && init?.method === 'POST') {
      const body = JSON.parse(String(init.body ?? '{}')) as { lemma?: string };
      createdPack = { id: 'wp:created', lemma: body.lemma ?? 'created' };
      return Promise.resolve(
        new Response(JSON.stringify({ id: createdPack.id }), { status: 200, headers: { 'Content-Type': 'application/json' } }),
      );
    }
    if (url.startsWith('/api/word/packs?')) {
      const items = [
        {
          id: 'wp:robust',
          lemma: 'robust',
          sense_title: '壊れにくい',
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-02T00:00:00Z',
          is_empty: false,
          guest_public: true,
          examples_count: { Dev: 1, CS: 0, LLM: 0, Business: 0, Common: 0 },
          checked_only_count: 1,
          learned_count: 0,
        },
        {
          id: 'wp:fallback',
          lemma: 'fallback',
          sense_title: '代替手段',
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
          is_empty: false,
          guest_public: true,
          examples_count: { Dev: 0, CS: 0, LLM: 0, Business: 0, Common: 0 },
          checked_only_count: 0,
          learned_count: 0,
        },
      ];
      if (createdPack) {
        items.push({
          id: createdPack.id,
          lemma: createdPack.lemma,
          sense_title: createdPack.lemma,
          created_at: '2024-01-03T00:00:00Z',
          updated_at: '2024-01-03T00:00:00Z',
          is_empty: true,
          guest_public: false,
          examples_count: { Dev: 0, CS: 0, LLM: 0, Business: 0, Common: 0 },
          checked_only_count: 0,
          learned_count: 0,
        });
      }
      return Promise.resolve(
        new Response(JSON.stringify({
          items,
          total: items.length,
          limit: 200,
          offset: 0,
        }), { status: 200, headers: { 'Content-Type': 'application/json' } }),
      );
    }
    if (url.endsWith('/api/word/packs/wp:robust')) {
      return Promise.resolve(
        new Response(JSON.stringify(wordPackDetail), { status: 200, headers: { 'Content-Type': 'application/json' } }),
      );
    }
    if (createdPack && url.endsWith(`/api/word/packs/${createdPack.id}`)) {
      return Promise.resolve(
        new Response(JSON.stringify({
          ...wordPackDetail,
          lemma: createdPack.lemma,
          sense_title: createdPack.lemma,
          senses: [],
          collocations: { general: { verb_object: [], adj_noun: [], prep_noun: [] }, academic: { verb_object: [], adj_noun: [], prep_noun: [] } },
          contrast: [],
          examples: { Dev: [], CS: [], LLM: [], Business: [], Common: [] },
        }), { status: 200, headers: { 'Content-Type': 'application/json' } }),
      );
    }
    return Promise.resolve(
      new Response(JSON.stringify({ ...wordPackDetail, lemma: 'fallback', sense_title: '代替手段' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
  });
  (globalThis as any).fetch = fetchMock;
  return fetchMock;
};

const renderExplorePage = () => render(
  <NotificationsProvider persist={false}>
    <ExplorePage />
  </NotificationsProvider>,
);

describe('ExplorePage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    authState.isGuest = false;
    setupFetch();
  });

  it('loads existing WordPacks and shows relation cards from selected detail', async () => {
    renderExplorePage();

    expect(screen.getByRole('heading', { name: 'Explore' })).toBeInTheDocument();
    expect(screen.getByText('保存済みWordPackのつながりを見つけ、未登録の語を追加できます。')).toBeInTheDocument();
    expect(screen.getByLabelText('探索するWordPackを検索')).toBeInTheDocument();
    expect(screen.getByText('ステータスの意味')).toBeInTheDocument();
    expect(screen.getAllByText('未登録').length).toBeGreaterThan(0);
    expect(await screen.findByRole('button', { name: 'robust を接続元に選ぶ' })).toBeInTheDocument();

    const user = userEvent.setup();
    await act(async () => {
      await user.click(screen.getByRole('button', { name: '共起' }));
    });

    expect(screen.getByRole('button', { name: '共起' })).toHaveAttribute('aria-pressed', 'true');
    expect(await screen.findByText('robust fallback')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /robust fallback.*開く|robust fallback/ })).toBeEnabled();
    expect(screen.getAllByRole('button', { name: /WordPackを作成/ })[0]).toBeEnabled();

    await act(async () => {
      await user.type(screen.getByLabelText('探索するWordPackを検索'), 'fall');
    });

    const candidateList = screen.getByLabelText('探索候補');
    await waitFor(() => expect(within(candidateList).queryByRole('button', { name: /robust/ })).not.toBeInTheDocument());
    expect(within(candidateList).getByRole('button', { name: /fallback/ })).toBeInTheDocument();
  });

  it('creates an empty WordPack from an unregistered relation and opens its preview', async () => {
    const fetchMock = setupFetch();
    renderExplorePage();

    expect(await screen.findByRole('button', { name: 'robust を接続元に選ぶ' })).toBeInTheDocument();
    const user = userEvent.setup();

    const createAction = await screen.findByRole('button', { name: '「resilient」のWordPackを作成' });

    await act(async () => {
      await user.click(createAction);
    });

    expect(await screen.findByText(/空WordPackを作成しました/)).toBeInTheDocument();
    expect(await screen.findByRole('dialog', { name: 'WordPack プレビュー' })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/word/packs',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ lemma: 'resilient' }),
      }),
    );
  });

  it('does not offer creation for example sentences that are not valid lemma candidates', async () => {
    const fetchMock = setupFetch();
    renderExplorePage();

    expect(await screen.findByRole('button', { name: 'robust を接続元に選ぶ' })).toBeInTheDocument();
    const user = userEvent.setup();

    await act(async () => {
      await user.click(screen.getByRole('button', { name: '例文' }));
    });

    const blockedAction = await screen.findByRole('button', {
      name: /This sentence, with punctuation, should not become a WordPack.*作成できません/,
    });
    expect(blockedAction).toBeDisabled();
    expect(screen.getByText(/例文全体は見出し語ではないため/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      '/api/word/packs',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('locks unregistered relation creation for guest users before sending a write request', async () => {
    authState.isGuest = true;
    const fetchMock = setupFetch();
    renderExplorePage();

    expect(await screen.findByRole('button', { name: 'robust を接続元に選ぶ' })).toBeInTheDocument();
    const guestCreateAction = await screen.findByRole('button', {
      name: '「resilient」はログインするとWordPackを作成できます',
    });

    expect(guestCreateAction).toBeDisabled();
    expect(screen.getAllByText('ゲストモードではWordPackを作成できません。ログインすると未登録語を追加できます。').length).toBeGreaterThan(0);
    expect(fetchMock).not.toHaveBeenCalledWith(
      '/api/word/packs',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('has no automated accessibility violations in the loaded Explore state', async () => {
    const { container } = renderExplorePage();

    expect(await screen.findByRole('button', { name: 'robust を接続元に選ぶ' })).toBeInTheDocument();
    expect(await screen.findByText('resilient')).toBeInTheDocument();

    expect(await axe(container, { rules: { 'color-contrast': { enabled: false } } })).toHaveNoViolations();
  });
});
