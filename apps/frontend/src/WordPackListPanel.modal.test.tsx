import { render, screen, act, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { App } from './App';
import { AppProviders } from './main';

describe('WordPackListPanel modal preview', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    (globalThis as any).fetch = vi.fn();
    try {
      sessionStorage.clear();
    } catch {}
    try {
      localStorage.setItem(
        'wordpack.auth.v1',
        JSON.stringify({
          authMode: 'authenticated',
          user: { google_sub: 'tester', email: 'tester@example.com', display_name: 'Tester' },
        }),
      );
    } catch {}
  });

  afterEach(() => {
    try {
      localStorage.removeItem('wordpack.auth.v1');
    } catch {}
  });

  function renderWithAuth() {
    return render(
      <AppProviders googleClientId="test-client">
        <App />
      </AppProviders>,
    );
  }

  function setupFetchMocks() {
    const mock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: any, init?: any) => {
      const url = typeof input === 'string' ? input : (input as URL).toString();
      if (url.endsWith('/api/config') && (!init || (init && (!init.method || init.method === 'GET')))) {
        return new Response(
          JSON.stringify({ request_timeout_ms: 60000 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      if (url.startsWith('/api/word/packs?')) {
        const now = new Date();
        const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
        const twoDaysAgo = new Date(now.getTime() - 2 * 24 * 60 * 60 * 1000);

        return new Response(
          JSON.stringify({
            items: [
              {
                id: 'wp:test:1',
                lemma: 'delta',
                sense_title: 'デルタ概説',
                created_at: twoDaysAgo.toISOString(),
                updated_at: yesterday.toISOString(),
                is_empty: true,
                checked_only_count: 5,
                learned_count: 3
              },
              {
                id: 'wp:test:2',
                lemma: 'alpha',
                sense_title: 'アルファ概説',
                created_at: yesterday.toISOString(),
                updated_at: now.toISOString(),
                is_empty: false,
                examples_count: { Dev: 2, CS: 1, LLM: 0, Business: 3, Common: 4 },
                checked_only_count: 8,
                learned_count: 6
              },
              {
                id: 'wp:test:3',
                lemma: 'beta',
                sense_title: 'ベータ概説',
                created_at: now.toISOString(),
                updated_at: twoDaysAgo.toISOString(),
                is_empty: false,
                examples_count: { Dev: 1, CS: 2, LLM: 1, Business: 1, Common: 2 },
                checked_only_count: 2,
                learned_count: 1
              },
            ],
            total: 3,
            limit: 20,
            offset: 0,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      if (url.endsWith('/api/word/packs/wp:test:1/regenerate/async')) {
        return new Response(
          JSON.stringify({ job_id: 'job:test:1', status: 'succeeded' }),
          { status: 202, headers: { 'Content-Type': 'application/json' } },
        );
      }
      if (url.endsWith('/api/word/packs/wp:test:1/regenerate/jobs/job:test:1')) {
        return new Response(
          JSON.stringify({ job_id: 'job:test:1', status: 'succeeded' }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      if (url.endsWith('/api/word/packs/wp:test:1')) {
        return new Response(
          JSON.stringify({
            lemma: 'delta',
            sense_title: 'デルタ概説',
            pronunciation: { ipa_GA: null, ipa_RP: null, syllables: null, stress_index: null, linking_notes: [] },
            senses: [{ id: 's1', gloss_ja: '意味', definition_ja: '定義', nuances_ja: 'ニュアンス', patterns: ['p1'], synonyms: ['syn'], antonyms: ['ant'], register: 'formal', notes_ja: '注意' }],
            collocations: { general: { verb_object: [], adj_noun: [], prep_noun: [] }, academic: { verb_object: [], adj_noun: [], prep_noun: [] } },
            contrast: [],
            examples: {
              Dev: [
                { en: `delta dev one about twenty five words overall in context.`, ja: `delta Dev例1`, grammar_ja: '第3文型' },
                { en: `delta dev two showcasing config and deployment narrative.`, ja: `delta Dev例2`, grammar_ja: '関係節' },
                { en: `delta dev three clarifying API stability and versioning.`, ja: `delta Dev例3`, grammar_ja: '前置詞句' },
                { en: `delta dev four reflecting review feedback and fixes.`, ja: `delta Dev例4`, grammar_ja: '不定詞' },
                { en: `delta dev five discussing refactor and readability.`, ja: `delta Dev例5`, grammar_ja: '分詞構文' },
              ],
              CS: [],
              LLM: [],
              Business: [
                { en: `In practice, estimates delta as constraints relax and noise diminishes.`, ja: `Business例1`, grammar_ja: '受動態' },
                { en: `Optimization routines delta when gradients vanish near stationary points.`, ja: `Business例2`, grammar_ja: '分詞' },
                { en: `Signals delta across nodes under synchronized sampling schedules.`, ja: `Business例3`, grammar_ja: '関係代名詞' },
              ],
              Common: [
                { en: `Paths delta near the central plaza after sunset.`, ja: `Common例1`, grammar_ja: '副詞句' },
                { en: `Their plans delta as deadlines approach.`, ja: `Common例2`, grammar_ja: '現在形' },
                { en: `Our views delta with more data and reflection.`, ja: `Common例3`, grammar_ja: '進行形' },
                { en: `Schedules delta around meetings and travel.`, ja: `Common例4`, grammar_ja: '前置詞句' },
                { en: `Tastes delta as we try new cuisines.`, ja: `Common例5`, grammar_ja: '三単現' },
                { en: `The lines delta at the corner of the page.`, ja: `Common例6`, grammar_ja: '受動態' },
              ],
            },
            etymology: { note: '-', confidence: 'low' },
            study_card: `study of delta`,
            citations: [{ text: 'citation' }],
            confidence: 'medium',
            // For UI rendering of AI info under 更新 row (from list meta)
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      if (url.endsWith('/api/word/packs/wp:test:2')) {
        return new Response(
          JSON.stringify({
            lemma: 'alpha',
            sense_title: 'アルファ概説',
            pronunciation: { ipa_GA: null, ipa_RP: null, syllables: null, stress_index: null, linking_notes: [] },
            senses: [{ id: 's1', gloss_ja: '意味', definition_ja: '定義', nuances_ja: 'ニュアンス', patterns: ['p1'], synonyms: ['syn'], antonyms: ['ant'], register: 'formal', notes_ja: '注意' }],
            collocations: { general: { verb_object: [], adj_noun: [], prep_noun: [] }, academic: { verb_object: [], adj_noun: [], prep_noun: [] } },
            contrast: [],
            examples: {
              Dev: [
                { en: `alpha dev one about twenty five words overall in context.`, ja: `alpha Dev例1`, grammar_ja: '第3文型' },
                { en: `alpha dev two showcasing config and deployment narrative.`, ja: `alpha Dev例2`, grammar_ja: '関係節' },
              ],
              CS: [
                { en: `alpha cs one about computer science concepts.`, ja: `alpha CS例1`, grammar_ja: '第3文型' },
              ],
              LLM: [],
              Business: [
                { en: `In practice, estimates alpha as constraints relax and noise diminishes.`, ja: `Business例1`, grammar_ja: '受動態' },
                { en: `Optimization routines alpha when gradients vanish near stationary points.`, ja: `Business例2`, grammar_ja: '分詞' },
                { en: `Signals alpha across nodes under synchronized sampling schedules.`, ja: `Business例3`, grammar_ja: '関係代名詞' },
              ],
              Common: [
                { en: `Paths alpha near the central plaza after sunset.`, ja: `Common例1`, grammar_ja: '副詞句' },
                { en: `Their plans alpha as deadlines approach.`, ja: `Common例2`, grammar_ja: '現在形' },
                { en: `Our views alpha with more data and reflection.`, ja: `Common例3`, grammar_ja: '進行形' },
                { en: `Schedules alpha around meetings and travel.`, ja: `Common例4`, grammar_ja: '前置詞句' },
              ],
            },
            etymology: { note: '-', confidence: 'low' },
            study_card: `study of alpha`,
            citations: [{ text: 'citation' }],
            confidence: 'medium',
            // For UI rendering of AI info under 更新 row (from list meta)
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      
      return new Response('not found', { status: 404 });
    });
    return mock;
  }

  it('カードをクリックするとモーダルでWordPack内容を表示する（WordPackタブ統合後）', async () => {
    setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();

    // WordPack タブへ（デフォルトがWordPackのため念のためAlt+4で明示）
    await act(async () => {
      await user.keyboard('{Alt>}{4}{/Alt}');
    });

    // 統合された一覧のヘッダーが表示される
    await waitFor(() => expect(screen.getByRole('heading', { name: /保存済みWordPack/ })).toBeInTheDocument());

    const senseButtons = await screen.findAllByRole('button', { name: '語義' });
    expect(senseButtons).toHaveLength(3);

    const ttsButtons = await screen.findAllByRole('button', { name: /の音声$/ });
    expect(ttsButtons).toHaveLength(3);

    // 例文未生成バッジ表示
    await waitFor(() => expect(screen.getByText('例文未生成')).toBeInTheDocument());

    // カードをクリック
    const cards = screen.getAllByTestId('wp-card');
    expect(cards).toHaveLength(3);
    
    // カードがクリック可能になるまで少し待機
    await waitFor(() => expect(cards[0]).toBeInTheDocument());
    
    await act(async () => {
      await user.click(cards[0]);
    });

    // モーダルが開くまで待機
    await waitFor(() => expect(screen.getByRole('dialog', { name: /WordPack プレビュー:/ })).toBeInTheDocument(), { timeout: 5000 });
    
    // WordPackの詳細が読み込まれるまで待機（モーダル内の内容を一意に特定）
    const modalContent = await waitFor(() => screen.getByTestId('modal-wordpack-content'), { timeout: 10000 });
    expect(modalContent).toHaveTextContent('学習カード要点');
    const lemmaLabel = within(modalContent).getByText('見出し語');
    const lemmaValue = lemmaLabel.nextElementSibling as HTMLElement | null;
    expect(lemmaValue).not.toBeNull();
    const lemmaTtsButtons = lemmaValue ? within(lemmaValue).getAllByRole('button', { name: '見出し語の音声' }) : [];
    expect(lemmaTtsButtons).toHaveLength(1);

    // 閉じる
    await act(async () => {
      await user.click(screen.getByRole('button', { name: 'WordPackプレビューを閉じる' }));
    });
    await waitFor(() => expect(screen.queryByRole('dialog', { name: /WordPack プレビュー/ })).not.toBeInTheDocument(), { timeout: 3000 });
  }, 15000);

  it('カードに学習記録バッジを表示し、イベントでリアルタイム更新される', async () => {
    setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();

    await act(async () => {
      await user.keyboard('{Alt>}{4}{/Alt}');
    });

    const cards = await screen.findAllByTestId('wp-card');
    expect(cards).toHaveLength(3);

    const deltaCard = cards.find((card) => card.textContent?.includes('delta'));
    expect(deltaCard).toBeDefined();
    const targetCard = deltaCard!;
    expect(within(targetCard).getByText('使える 3')).toBeInTheDocument();
    expect(within(targetCard).getByText('確認済み 5')).toBeInTheDocument();

    await act(async () => {
      window.dispatchEvent(
        new CustomEvent('wordpack:study-progress', {
          detail: { wordPackId: 'wp:test:1', learned_count: 9, checked_only_count: 12 },
        }),
      );
    });

    await waitFor(() => {
      expect(within(targetCard).getByText('使える 9')).toBeInTheDocument();
      expect(within(targetCard).getByText('確認済み 12')).toBeInTheDocument();
    });
  });

  it('カード表示では読み上げを直接、リスト表示では項目メニューから利用できる', async () => {
    setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();

    await act(async () => {
      await user.keyboard('{Alt>}{4}{/Alt}');
    });

    const buttonsInCardView = await screen.findAllByRole('button', { name: /の音声$/ });
    expect(buttonsInCardView).toHaveLength(3);

    const senseButtonsInCardView = await screen.findAllByRole('button', { name: '語義' });
    expect(senseButtonsInCardView).toHaveLength(3);

    await act(async () => {
      await user.click(screen.getByRole('button', { name: 'リスト' }));
    });

    const listItems = await screen.findAllByTestId('wp-index-item');
    const firstListItem = listItems.find((item) => item.textContent?.includes('alpha'));
    expect(firstListItem).toBeDefined();
    const firstListOpenButton = within(firstListItem!).getByRole('button', { name: '開く' });
    firstListOpenButton.focus();
    expect(firstListOpenButton).toHaveFocus();

    expect(within(firstListItem!).queryByRole('menuitem', { name: 'alphaの音声を再生' })).toBeNull();
    await act(async () => {
      await user.click(within(firstListItem!).getByRole('button', { name: 'alpha のその他の操作' }));
    });
    const actionMenu = within(firstListItem!).getByRole('menu', { name: 'alpha の操作メニュー' });
    expect(within(actionMenu).getByRole('menuitem', { name: 'alphaの音声を再生' })).toBeInTheDocument();

    await act(async () => {
      await user.keyboard('{Escape}');
    });
    expect(within(firstListItem!).queryByRole('menu', { name: 'alpha の操作メニュー' })).toBeNull();
    await waitFor(() => {
      expect(within(firstListItem!).getByRole('button', { name: 'alpha のその他の操作' })).toHaveFocus();
    });
    firstListOpenButton.focus();

    await act(async () => {
      await user.keyboard('{Enter}');
    });

    await waitFor(() => expect(screen.getByRole('dialog', { name: /WordPack プレビュー:/ })).toBeInTheDocument());

    await act(async () => {
      await user.click(screen.getByRole('button', { name: 'WordPackプレビューを閉じる' }));
    });

    await act(async () => {
      await user.click(screen.getByRole('button', { name: 'カード' }));
    });
  });

  it('語義ボタンで語義タイトルを確認できる（カード/リスト）', async () => {
    setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();

    await act(async () => {
      await user.keyboard('{Alt>}{4}{/Alt}');
    });

    const cards = await screen.findAllByTestId('wp-card');
    expect(cards).toHaveLength(3);

    const firstCardSenseButton = within(cards[0]).getByRole('button', { name: '語義' });

    await act(async () => {
      await user.click(firstCardSenseButton);
    });

    const senseTitleInCard = within(cards[0]).getByTestId('wp-card-sense-title');
    expect(senseTitleInCard).toHaveTextContent('アルファ概説');

    await act(async () => {
      await user.click(firstCardSenseButton);
    });

    expect(within(cards[0]).queryByTestId('wp-card-sense-title')).toBeNull();

    await act(async () => {
      await user.click(screen.getByRole('button', { name: 'リスト' }));
    });

    const listItems = await screen.findAllByTestId('wp-index-item');
    expect(listItems).toHaveLength(3);

    const firstListItem = listItems[0];
    await act(async () => {
      await user.click(within(firstListItem).getByRole('button', { name: 'alpha のその他の操作' }));
    });
    const listSenseButton = within(firstListItem).getByRole('menuitemcheckbox', { name: '語義を表示' });

    await act(async () => {
      await user.click(listSenseButton);
    });

    expect(within(firstListItem).getByTestId('wp-index-title-row')).toHaveTextContent('alpha');
    expect(firstListItem).toHaveTextContent('アルファ概説');

    await act(async () => {
      await user.click(screen.getByRole('button', { name: 'カード' }));
    });
  });

  it('語義一括表示トグルで全語義タイトルを同時表示・非表示できる', async () => {
    setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();

    await act(async () => {
      await user.keyboard('{Alt>}{4}{/Alt}');
    });

    const cards = await screen.findAllByTestId('wp-card');
    expect(cards).toHaveLength(3);

    // 初期状態では語義タイトルは表示されていない
    expect(screen.queryByTestId('wp-card-sense-title')).toBeNull();

    const toggle = screen.getByLabelText('語義一括表示') as HTMLInputElement;
    expect(toggle).not.toBeChecked();

    await act(async () => {
      await user.click(toggle);
    });

    await waitFor(() => {
      const displayed = screen.getAllByTestId('wp-card-sense-title');
      expect(displayed).toHaveLength(3);
      expect(displayed[0]).toHaveTextContent(/概説/);
    });

    // 個別ボタンは一括表示中は操作不可
    const senseButton = within(cards[0]).getByRole('button', { name: '語義' }) as HTMLButtonElement;
    expect(senseButton).toBeDisabled();

    await act(async () => {
      await user.click(toggle);
    });

    await waitFor(() => {
      expect(screen.queryByTestId('wp-card-sense-title')).toBeNull();
    });

    expect(senseButton).not.toBeDisabled();
  });

  it('ソート機能が正しく動作する', async () => {
    setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();

    // WordPack タブへ
    await act(async () => {
      await user.keyboard('{Alt>}{4}{/Alt}');
    });

    // 一覧が表示されるまで待機
    await waitFor(() => expect(screen.getByRole('heading', { name: /保存済みWordPack/ })).toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByTestId('wp-card')).toHaveLength(3));

    // デフォルトは更新日時降順（alpha, delta, beta）
    const cards = screen.getAllByTestId('wp-card');
    expect(cards[0]).toHaveTextContent(/alpha/);
    expect(cards[1]).toHaveTextContent(/delta/);
    expect(cards[2]).toHaveTextContent(/beta/);

    // 単語名でソート（昇順）
    await act(async () => {
      await user.selectOptions(screen.getByLabelText('並び順:'), 'lemma');
    });
    await act(async () => {
      await user.click(screen.getByTitle('昇順'));
    });

    // alpha, beta, delta の順になる
    const sortedCards = screen.getAllByTestId('wp-card');
    expect(sortedCards[0]).toHaveTextContent(/alpha/);
    expect(sortedCards[1]).toHaveTextContent(/beta/);
    expect(sortedCards[2]).toHaveTextContent(/delta/);

    // 例文数でソート（降順）
    await act(async () => {
      await user.selectOptions(screen.getByLabelText('並び順:'), 'total_examples');
    });
    await act(async () => {
      await user.click(screen.getByTitle('降順'));
    });

    // alpha(10), beta(7), delta(0) の順になる
    const exampleSortedCards = screen.getAllByTestId('wp-card');
    expect(exampleSortedCards[0]).toHaveTextContent(/alpha/);
    expect(exampleSortedCards[1]).toHaveTextContent(/beta/);
    expect(exampleSortedCards[2]).toHaveTextContent(/delta/);
  }, 10000);

  it('表示絞り込みチップ（生成済/未生成/すべて）が正しく動作する', async () => {
    setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();

    await act(async () => {
      await user.keyboard('{Alt>}{4}{/Alt}');
    });

    await waitFor(() => expect(screen.getByRole('heading', { name: /保存済みWordPack/ })).toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByTestId('wp-card')).toHaveLength(3));

    // 生成済のみ
    await act(async () => {
      await user.click(screen.getByRole('button', { name: '生成済み 2' }));
    });
    await waitFor(() => expect(screen.getAllByTestId('wp-card')).toHaveLength(2));
    const genCards = screen.getAllByTestId('wp-card');
    expect(genCards[0]).not.toHaveTextContent(/delta/);
    expect(genCards[1]).not.toHaveTextContent(/delta/);

    // 未生成のみ
    await act(async () => {
      await user.click(screen.getByRole('button', { name: '未生成 1' }));
    });
    const notGenCards = await waitFor(() => screen.getAllByTestId('wp-card'));
    expect(notGenCards).toHaveLength(1);
    expect(notGenCards[0]).toHaveTextContent(/delta/);

    // すべて
    await act(async () => {
      await user.click(screen.getByRole('button', { name: 'すべて' }));
    });
    await waitFor(() => expect(screen.getAllByTestId('wp-card')).toHaveLength(3));
  }, 10000);

  it('例文未生成のWordPackに生成ボタンが表示され、押下で生成APIを呼び出す', async () => {
    const fetchMock = setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();

    await act(async () => {
      await user.keyboard('{Alt>}{4}{/Alt}');
    });

    const cards = await screen.findAllByTestId('wp-card');
    const targetCard = cards.find((card) => /delta/i.test(card.textContent || ''));
    expect(targetCard).toBeDefined();
    const generateButton = within(targetCard as HTMLElement).getByRole('button', { name: '生成' });
    expect(generateButton).toBeEnabled();

    await act(async () => {
      await user.click(generateButton);
    });

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/word/packs/wp:test:1/regenerate/async',
        expect.objectContaining({ method: 'POST' }),
      ),
    );

    await waitFor(() =>
      expect(screen.getByText('【delta】の例文生成が完了しました')).toBeInTheDocument(),
    );
  });

  it('上部検索バーの部分一致検索が正しく動作する', async () => {
    setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();

    await act(async () => {
      await user.keyboard('{Alt>}{4}{/Alt}');
    });

    await waitFor(() => expect(screen.getByRole('heading', { name: /保存済みWordPack/ })).toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByTestId('wp-card')).toHaveLength(3));

    const searchInput = screen.getByRole('searchbox', { name: '保存済みWordPackを検索' });

    // "al" -> alpha のみ
    await act(async () => {
      await user.clear(searchInput);
      await user.type(searchInput, 'al{Enter}');
    });
    const prefixCards = await waitFor(() => screen.getAllByTestId('wp-card'));
    expect(prefixCards).toHaveLength(1);
    expect(prefixCards[0]).toHaveTextContent(/alpha/);

    // "ta" -> beta, delta
    await act(async () => {
      await user.clear(searchInput);
      await user.type(searchInput, 'ta{Enter}');
    });
    const suffixCards = await waitFor(() => screen.getAllByTestId('wp-card'));
    expect(suffixCards).toHaveLength(2);
    expect(suffixCards.some(c => /beta/i.test(c.textContent || ''))).toBe(true);
    expect(suffixCards.some(c => /delta/i.test(c.textContent || ''))).toBe(true);

    // "et" -> beta のみ
    await act(async () => {
      await user.clear(searchInput);
      await user.type(searchInput, 'et{Enter}');
    });
    const containsCards = await waitFor(() => screen.getAllByTestId('wp-card'));
    expect(containsCards).toHaveLength(1);
    expect(containsCards[0]).toHaveTextContent(/beta/);

    // 空文字で検索を再適用すると、全件（3件）に戻る
    await act(async () => {
      await user.clear(searchInput);
      await user.keyboard('{Enter}');
    });
    await waitFor(() => expect(screen.getAllByTestId('wp-card')).toHaveLength(3));
  }, 12000);
});
