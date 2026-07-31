import { useRef, useState } from 'react';
import { render, screen, act, waitFor, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { axe } from 'vitest-axe';
import { AppProviders } from './main';
import { WordPackPanel } from './components/WordPackPanel';
import { GenerationQueuePanel } from './components/GenerationQueuePanel';
import { WordPackPreviewModal } from './components/WordPackPreviewModal';

describe('WordPackPanel E2E (mocked fetch)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
    (globalThis as any).fetch = vi.fn();
    try {
      localStorage.removeItem('wpfe.notifications.v1');
      localStorage.setItem(
        'wordpack.auth.v1',
        JSON.stringify({
          authMode: 'authenticated',
          user: { google_sub: 'tester', email: 'tester@example.com', display_name: 'Tester' },
        }),
      );
      (window as any).__lemmaCache = undefined;
    } catch {}
  });

  afterEach(() => {
    try {
      localStorage.removeItem('wordpack.auth.v1');
      localStorage.removeItem('wpfe.notifications.v1');
    } catch {}
  });

  const WordPackPanelHarness = () => {
    const [selectedWordPackId, setSelectedWordPackId] = useState<string | null>(null);
    const focusRef = useRef<HTMLElement>(null);
    return (
      <>
        <WordPackPanel
          focusRef={focusRef}
          selectedWordPackId={selectedWordPackId}
          onWordPackGenerated={setSelectedWordPackId}
          creationPanelPlacement="inline"
        />
        <GenerationQueuePanel />
      </>
    );
  };

  function renderWithAuth() {
    return render(
      <AppProviders googleClientId="test-client">
        <WordPackPanelHarness />
      </AppProviders>,
    );
  }

  function setupFetchMocks(
    seedLemmaById: Record<string, string> = {},
    options: { wordPackPostGate?: Promise<void> } = {},
  ) {
    const generated = new Set<string>();
    const lemmaById = new Map<string, string>();
    Object.entries(seedLemmaById).forEach(([id, lemma]) => lemmaById.set(id, lemma));
    let idSeq = 0;
    const nextWordPackId = () => `wp:${(idSeq++).toString(16).padStart(32, '0')}`;
    const mock = vi.spyOn(global, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : (input as URL).toString();
      if (url.includes('/api/word/lemma/Paths')) {
        lemmaById.set('wp:11111111111111111111111111111111', 'Paths');
        return new Response(
          JSON.stringify({ found: true, id: 'wp:11111111111111111111111111111111', lemma: 'Paths', sense_title: '語義タイトルなし' }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      if (url.endsWith('/api/word/packs') && init?.method === 'POST') {
        const body = init?.body ? JSON.parse(init.body as string) : {};
        const lemma = body.lemma || 'test';
        const id = nextWordPackId();
        lemmaById.set(id, lemma);
        return new Response(
          JSON.stringify({ id }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      if (url.startsWith('/api/word/packs/wp:') && (!init || (init && (!init.method || init.method === 'GET')))) {
        const idPart = url.split('/').pop() || '';
        const lemma = lemmaById.get(idPart) || 'test';
        return new Response(
          JSON.stringify({
            lemma,
            sense_title: `${lemma}概説`,
            pronunciation: { ipa_GA: null, ipa_RP: null, syllables: null, stress_index: null, linking_notes: [] },
            senses: [{ id: 's1', gloss_ja: '意味', definition_ja: '定義', nuances_ja: 'ニュアンス', patterns: ['p1'], synonyms: ['syn'], antonyms: ['ant'], register: 'formal', notes_ja: '注意' }],
            collocations: { general: { verb_object: [], adj_noun: [], prep_noun: [] }, academic: { verb_object: [], adj_noun: [], prep_noun: [] } },
            contrast: [],
            examples: {
              Dev: [
                { en: `${lemma} dev example one with around twenty five tokens total.`, ja: `${lemma} のDev例文1`, grammar_ja: '第3文型' },
                { en: `${lemma} dev example two includes subordinate clauses and clear structure.`, ja: `${lemma} のDev例文2`, grammar_ja: '関係節' }
              ],
              CS: [
                { en: `Paths ${lemma} at the main square downtown.`, ja: `${lemma} のCS例文1`, grammar_ja: '前置詞句' }
              ],
              LLM: [],
              Business: [],
              Common: [
                { en: `Paths ${lemma} at the main square downtown.`, ja: `${lemma} のCommon例文1`, grammar_ja: '前置詞句' },
                { en: `Schedules ${lemma} around the team’s availability.`, ja: `${lemma} のCommon例文2`, grammar_ja: '三単現' },
                { en: 'Ghosts linger without a defined sense in the archive.', ja: 'Ghosts のCommon例文 (senseなし)', grammar_ja: '動詞句' },
                {
                  en: 'SupercalifragilisticexpialidociousSupercalifragilisticexpialidocious appears as an invalid candidate.',
                  ja: '長すぎる候補のCommon例文',
                  grammar_ja: '名詞句',
                }
              ]
            },
            etymology: { note: '-', confidence: 'low' },
            study_card: `study of ${lemma}`,
            citations: [],
            confidence: 'medium',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      if (url.endsWith('/api/config') && (!init || (init && (!init.method || init.method === 'GET')))) {
        return new Response(
          JSON.stringify({ request_timeout_ms: 60000 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }

      if (url.endsWith('/api/word/pack/jobs') && init?.method === 'POST') {
        const body = init?.body ? JSON.parse(init.body as string) : {};
        const lemma = body.lemma || 'test';
        if (options.wordPackPostGate) {
          await options.wordPackPostGate;
        }
        const id = nextWordPackId();
        generated.add(lemma);
        lemmaById.set(id, lemma);
        const result = {
            id,
            lemma,
            sense_title: `${lemma}概説`,
            pronunciation: { ipa_GA: null, ipa_RP: null, syllables: null, stress_index: null, linking_notes: [] },
            senses: [{ id: 's1', gloss_ja: '意味', definition_ja: '定義', nuances_ja: 'ニュアンス', patterns: ['p1'], synonyms: ['syn'], antonyms: ['ant'], register: 'formal', notes_ja: '注意' }],
            collocations: { general: { verb_object: [], adj_noun: [], prep_noun: [] }, academic: { verb_object: [], adj_noun: [], prep_noun: [] } },
            contrast: [],
            examples: {
              Dev: [
                { en: `${lemma} dev example one with around twenty five tokens total.`, ja: `${lemma} のDev例文1`, grammar_ja: '第3文型' },
                { en: `${lemma} dev example two includes subordinate clauses and clear structure.`, ja: `${lemma} のDev例文2`, grammar_ja: '関係節' },
                { en: `${lemma} dev example three demonstrates prepositional phrases effectively.`, ja: `${lemma} のDev例文3`, grammar_ja: '前置詞句' },
                { en: `${lemma} dev example four focuses on application context and clarity.`, ja: `${lemma} のDev例文4`, grammar_ja: '不定詞' },
                { en: `${lemma} dev example five reflects code-review style feedback.`, ja: `${lemma} のDev例文5`, grammar_ja: '分詞構文' },
              ],
              CS: [
                { en: `In computer science, results ${lemma} toward a coherent theory under constraints.`, ja: `${lemma} のCS例文1`, grammar_ja: '倒置' },
                { en: `As complexity grows, algorithms ${lemma} on shared invariants.`, ja: `${lemma} のCS例文2`, grammar_ja: '従属節' },
                { en: `Formal proofs ${lemma} as lemmas link foundational claims.`, ja: `${lemma} のCS例文3`, grammar_ja: '仮定法' },
                { en: `Empirical results ${lemma} across benchmarks when variables are controlled.`, ja: `${lemma} のCS例文4`, grammar_ja: '受動態' },
                { en: `Theoretical bounds ${lemma} under relaxed assumptions.`, ja: `${lemma} のCS例文5`, grammar_ja: '関係代名詞' },
              ],
              LLM: [
                { en: `LLM outputs ${lemma} with more context provided via system prompts.`, ja: `LLM例文1`, grammar_ja: '時制一致' },
                { en: `Fine-tuned models ${lemma} on domain-specific jargon effectively.`, ja: `LLM例文2`, grammar_ja: '前置詞句' },
                { en: `Safety mitigations ${lemma} as alignment objectives are strengthened.`, ja: `LLM例文3`, grammar_ja: '分詞' },
                { en: `Evaluation metrics ${lemma} when test sets reflect real usage.`, ja: `LLM例文4`, grammar_ja: '従属節' },
                { en: `Chain-of-thought traces ${lemma} with improved reasoning over steps.`, ja: `LLM例文5`, grammar_ja: '不定詞' },
              ],
              Business: [
                { en: `Under mild assumptions, iterative updates ${lemma} to a local optimum.`, ja: `Business例1`, grammar_ja: '不定詞' },
                { en: `Multiple systems ${lemma} when signals stabilize over time.`, ja: `Business例2`, grammar_ja: '関係代名詞' },
                { en: `Gradients ${lemma} as learning rates decay across epochs.`, ja: `Business例3`, grammar_ja: '分詞' },
              ],
              Common: [
                { en: `Over months, ideas ${lemma} into a clear plan.`, ja: `Common例1`, grammar_ja: '副詞句' },
                { en: `Our opinions ${lemma} after discussing the options.`, ja: `Common例2`, grammar_ja: '現在完了' },
                { en: `Paths ${lemma} at the main square downtown.`, ja: `Common例3`, grammar_ja: '前置詞句' },
                { en: `Tastes ${lemma} as people grow older and gain experience.`, ja: `Common例4`, grammar_ja: '現在形' },
                { en: `Schedules ${lemma} around the team’s availability.`, ja: `Common例5`, grammar_ja: '三単現' },
                { en: `Trains ${lemma} at this station every hour.`, ja: `Common例6`, grammar_ja: '進行形' },
                { en: `Ghosts linger without a defined sense in the archive.`, ja: `Common例Ghost`, grammar_ja: '動詞句' },
              ],
            },
            etymology: { note: '-', confidence: 'low' },
            study_card: `study of ${lemma}`,
            citations: [{ text: 'citation' }],
            confidence: 'medium',
          };
        return new Response(
          JSON.stringify({
            job_id: `wordpack-generation-job:${id}`,
            job_type: 'wordpack-generation',
            status: 'succeeded',
            result,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      
      return new Response('not found', { status: 404 });
    });
    return mock;
  }

  it('shows loading placeholder with aria-readonly and no a11y violations', async () => {
    let resolveFetch: ((response: Response) => void) | null = null;
    const pending = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });

    vi.spyOn(global, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : (input as URL).toString();
      if (url.endsWith('/api/config')) {
        return Promise.resolve(
          new Response(JSON.stringify({ request_timeout_ms: 60000 }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      if (url.includes('/api/word/packs/wp:loading')) {
        return pending;
      }
      return Promise.resolve(new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }));
    });

    const { container } = render(
      <AppProviders googleClientId="test-client">
        <WordPackPanel focusRef={{ current: null }} selectedWordPackId="wp:loading" />
      </AppProviders>,
    );

    // 読み込み中フォームの aria-readonly が削除されていないことを最小ケースで検知する。
    const readonlyInput = await screen.findByLabelText('WordPack見出し語読み込み中');
    expect(readonlyInput).toHaveAttribute('aria-readonly');
    expect(await axe(container)).toHaveNoViolations();

    await act(async () => {
      resolveFetch?.(
        new Response(
          JSON.stringify({
            lemma: 'loading',
            sense_title: 'loading',
            pronunciation: { ipa_GA: null, ipa_RP: null, syllables: null, stress_index: null, linking_notes: [] },
            senses: [],
            collocations: { general: { verb_object: [], adj_noun: [], prep_noun: [] }, academic: { verb_object: [], adj_noun: [], prep_noun: [] } },
            contrast: [],
            examples: { Dev: [], CS: [], LLM: [], Business: [], Common: [] },
            etymology: { note: '-', confidence: 'low' },
            study_card: '',
            citations: [],
            confidence: 'low',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      );
    });
  });

  it('shows a recovery panel instead of the loading placeholder when loading a selected WordPack fails', async () => {
    vi.spyOn(global, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : (input as URL).toString();
      if (url.endsWith('/api/config')) {
        return new Response(JSON.stringify({ request_timeout_ms: 60000 }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/word/packs/wp:error')) {
        return new Response(JSON.stringify({ detail: 'WordPackデータを取得できませんでした' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } });
    });

    render(
      <AppProviders googleClientId="test-client">
        <WordPackPanel
          focusRef={{ current: null }}
          selectedWordPackId="wp:error"
          fallbackMeta={{ id: 'wp:error', lemma: 'failure', senseTitle: '失敗ケース' }}
        />
      </AppProviders>,
    );

    expect(await screen.findByRole('alert')).toHaveTextContent('WordPackを読み込めませんでした');
    expect(screen.getByRole('button', { name: '再試行' })).toBeInTheDocument();
    expect(screen.queryByText('WordPack を読み込み中です。プレビューが準備されるまでお待ちください。')).not.toBeInTheDocument();
  });

  it('links invalid lemma guidance to the input', async () => {
    setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();
    const input = await screen.findByLabelText('見出し語');

    await act(async () => {
      await user.clear(input);
      await user.type(input, '日本語');
    });

    const helper = document.getElementById('wordpack-lemma-help');
    expect(helper).toHaveTextContent('英数字と半角スペース、ハイフン、アポストロフィのみ利用できます');
    expect(helper).toHaveClass('is-invalid');
    expect(input).toHaveAttribute('aria-describedby', 'wordpack-lemma-help');
    expect(input).toHaveAttribute('aria-invalid', 'true');
  });

  it('lets keyboard users reveal the self-check card without waiting', async () => {
    setupFetchMocks();
    render(
      <AppProviders googleClientId="test-client">
        <WordPackPanel focusRef={{ current: null }} selectedWordPackId="wp:selfcheck" />
      </AppProviders>,
    );

    const user = userEvent.setup();
    const revealButton = await screen.findByRole('button', { name: /セルフチェックを表示する/ });
    revealButton.focus();
    expect(revealButton).toHaveFocus();

    await act(async () => {
      await user.keyboard('{Enter}');
    });

    await waitFor(() => expect(screen.queryByRole('button', { name: /セルフチェックを表示する/ })).not.toBeInTheDocument());
  });

  it('generates WordPack and shows examples', async () => {
    const fetchMock = setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();

    const input = await screen.findByPlaceholderText('見出し語を入力（英数字・ハイフン・アポストロフィ・半角スペースのみ）') as HTMLInputElement;
    expect(input).toBeInTheDocument();
    // モデルドロップダウンが表示されている
    expect(screen.getByLabelText('モデル')).toBeInTheDocument();
    const reasoningSelect = screen.getByLabelText('reasoning.effort') as HTMLSelectElement;
    const verbositySelect = screen.getByLabelText('text.verbosity') as HTMLSelectElement;
    expect(reasoningSelect).toHaveValue('high');
    expect(verbositySelect).toHaveValue('medium');
    expect(Array.from((screen.getByLabelText('モデル') as HTMLSelectElement).options).map((option) => option.value))
      .toEqual(['gpt-5.6-luna']);
    expect(Array.from(reasoningSelect.options).map((option) => option.value))
      .toEqual(['none', 'low', 'medium', 'high', 'xhigh', 'max']);
    await act(async () => {
      await user.selectOptions(screen.getByLabelText('モデル'), 'gpt-5.6-luna');
      await user.selectOptions(reasoningSelect, 'high');
      await user.selectOptions(verbositySelect, 'low');
    });
    await act(async () => {
      await user.type(input, 'delta');
      await user.click(screen.getByRole('button', { name: '作成を開始' }));
    });

    await screen.findByText('WordPack を生成しました');
    // 自動でプレビューモーダルは開かれない
    expect(screen.queryByRole('dialog', { name: 'WordPack プレビュー' })).not.toBeInTheDocument();

    const queue = await screen.findByRole('region', { name: '生成キュー' });
    const previewCallsStart = fetchMock.mock.calls.length;
    await act(async () => {
      await user.click(within(queue).getByRole('button', { name: 'delta の生成結果プレビューを開く' }));
    });
    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: /WordPack プレビュー: delta/ })).toBeVisible();
    });
    const previewUrls = fetchMock.mock.calls
      .slice(previewCallsStart)
      .map((c) => (typeof c[0] === 'string' ? c[0] : (c[0] as URL).toString()));
    expect(previewUrls.some((u) => u.endsWith('/api/word/packs/wp:00000000000000000000000000000000'))).toBe(true);
    expect(previewUrls.some((u) => u.endsWith('/api/word/lemma/delta'))).toBe(false);
    await act(async () => {
      await user.click(screen.getByRole('button', { name: 'WordPackプレビューを閉じる' }));
    });

    // fetch が正しいエンドポイントで呼ばれていること（採点APIは呼ばれない）
    const urls = fetchMock.mock.calls.map((c) => (typeof c[0] === 'string' ? c[0] : (c[0] as URL).toString()));
    expect(urls.some((u) => u.endsWith('/api/word/pack/jobs'))).toBe(true);
    expect(urls.some((u) => u.endsWith('/api/review/grade_by_lemma'))).toBe(false);

    // リクエストボディに model/reasoning/text が含まれていること
    const bodies = fetchMock.mock.calls
      .filter((c) => (typeof c[0] === 'string' ? (c[0] as string).endsWith('/api/word/pack/jobs') : ((c[0] as URL).toString().endsWith('/api/word/pack/jobs'))))
      .map((c) => (c[1]?.body ? JSON.parse(c[1]!.body as string) : {}));
    expect(bodies.some((b) => (
      b.model === 'gpt-5.6-luna'
      && b.reasoning?.effort === 'high'
      && b.text?.verbosity === 'low'
      && !('temperature' in b)
    ))).toBe(true);
  });

  it('creates empty WordPack via the new button and shows it', async () => {
    const fetchMock = setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();

    const input = await screen.findByPlaceholderText('見出し語を入力（英数字・ハイフン・アポストロフィ・半角スペースのみ）') as HTMLInputElement;
    await act(async () => {
      await user.clear(input);
      await user.type(input, 'epsilon');
      await user.click(screen.getByRole('button', { name: 'WordPackのみ作成' }));
    });

    // 概要セクションが表示され、学習カードは空文字
    await waitFor(() => expect(screen.getByRole('heading', { name: '概要' })).toBeInTheDocument());
    expect(screen.getByText('学習カード要点')).toBeInTheDocument();
    // 呼び出しURL検証
    const urls = fetchMock.mock.calls.map((c) => (typeof c[0] === 'string' ? c[0] : (c[0] as URL).toString()));
    expect(urls.some((u) => u.endsWith('/api/word/packs'))).toBe(true);
    // 直後に詳細取得が走る
    expect(urls.some((u) => /\/api\/word\/packs\/wp:[0-9a-f]{32}$/.test(u))).toBe(true);
  });

  it('warms lemma cache on hover and opens/minimizes/restores the lemma window', async () => {
    const fetchMock = setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();

    const input = await screen.findByPlaceholderText('見出し語を入力（英数字・ハイフン・アポストロフィ・半角スペースのみ）') as HTMLInputElement;
    await act(async () => {
      await user.clear(input);
      await user.type(input, 'theta');
      await user.click(screen.getByRole('button', { name: 'WordPackのみ作成' }));
    });

    const example = await screen.findByTestId('example-Common-0');
    const englishRow = within(example).getByRole('button', { name: /関連WordPackを開く/ });
    const token = within(englishRow).getByText('Paths', { selector: 'span.lemma-token' });

    await act(async () => {
      await user.hover(token);
    });
    await waitFor(() => expect(token).toHaveClass('lemma-known'));

    await act(async () => {
      await user.click(token);
    });

    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((call) => (typeof call[0] === 'string' ? call[0] : (call[0] as URL).toString()));
      expect(urls.some((u) => u.includes('/api/word/lemma/Paths'))).toBe(true);
    });
    const windowRegion = await screen.findByRole('complementary', { name: 'Paths のWordPack概要' });
    await waitFor(() => {
      const subtitle = windowRegion.querySelector('.lemma-window-subtitle');
      expect(subtitle).toBeTruthy();
      expect(subtitle).toHaveTextContent('Paths概説');
      expect(subtitle).not.toHaveTextContent('語義タイトルなし');
    });
    expect(within(windowRegion).getAllByText(/Paths概説/).length).toBeGreaterThan(0);

    const minimizeButton = within(windowRegion).getByRole('button', { name: '最小化' });
    await act(async () => {
      await user.click(minimizeButton);
    });
    await waitFor(() => expect(screen.queryByRole('complementary', { name: 'Paths のWordPack概要' })).not.toBeInTheDocument());

    const trayButton = await screen.findByRole('button', { name: /Paths.*概説/ });
    await act(async () => {
      await user.click(trayButton);
    });
    await waitFor(() => expect(screen.getByRole('complementary', { name: 'Paths のWordPack概要' })).toBeInTheDocument());
  });

  it('shows 未生成 tooltip for unknown lemma token and notifies when generating', async () => {
    const fetchMock = setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();

    const input = await screen.findByPlaceholderText('見出し語を入力（英数字・ハイフン・アポストロフィ・半角スペースのみ）') as HTMLInputElement;
    await act(async () => {
      await user.clear(input);
      await user.type(input, 'theta');
      await user.click(screen.getByRole('button', { name: 'WordPackのみ作成' }));
    });

    const ghostToken = await screen.findByText((content, element) => {
      if (!element) return false;
      if (!element.matches('span.lemma-token')) return false;
      return content.trim() === 'Ghosts';
    });

    await act(async () => {
      await user.hover(ghostToken);
    });

    await waitFor(() => {
      const tipEl = Array.from(document.querySelectorAll('.lemma-tooltip')).find((el) => el.textContent === '未生成');
      expect(tipEl).toBeTruthy();
    });
    const tooltip = Array.from(document.querySelectorAll('.lemma-tooltip')).find((el) => el.textContent === '未生成') as HTMLElement | undefined;
    expect(tooltip).toBeTruthy();
    expect(tooltip).toHaveAttribute('role', 'tooltip');
    expect(tooltip?.querySelector('button')).toBeNull();
    expect(screen.queryByRole('button', { name: /WordPackを生成/ })).not.toBeInTheDocument();

    await act(async () => {
      await user.click(ghostToken);
    });

    const queue = await screen.findByRole('region', { name: '生成キュー' });
    await waitFor(() => {
      expect(within(queue).getAllByText('Ghosts').length).toBeGreaterThan(0);
      expect(within(queue).getAllByText('完了').length).toBeGreaterThan(0);
    });

    const generatedBodies = fetchMock.mock.calls
      .filter((c) => (typeof c[0] === 'string' ? (c[0] as string).endsWith('/api/word/pack/jobs') : ((c[0] as URL).toString().endsWith('/api/word/pack/jobs'))))
      .map((c) => (c[1]?.body ? JSON.parse(c[1]!.body as string) : {}));
    expect(generatedBodies.some((body) => body.lemma === 'Ghosts')).toBe(true);
  });

  it('generates unknown lemma when token is clicked directly', async () => {
    const fetchMock = setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();

    const input = await screen.findByPlaceholderText('見出し語を入力（英数字・ハイフン・アポストロフィ・半角スペースのみ）') as HTMLInputElement;
    await act(async () => {
      await user.clear(input);
      await user.type(input, 'theta');
      await user.click(screen.getByRole('button', { name: 'WordPackのみ作成' }));
    });

    const ghostToken = await screen.findByText((content, element) => {
      if (!element) return false;
      if (!element.matches('span.lemma-token')) return false;
      return content.trim() === 'Ghosts';
    });

    await act(async () => {
      await user.hover(ghostToken);
    });

    await act(async () => {
      await user.click(ghostToken);
    });

    const queue = await screen.findByRole('region', { name: '生成キュー' });
    await waitFor(() => {
      expect(within(queue).getAllByText('Ghosts').length).toBeGreaterThan(0);
      expect(within(queue).getAllByText('完了').length).toBeGreaterThan(0);
    });
    expect(within(queue).getByRole('status')).toHaveTextContent('Ghosts の生成状態は完了です');
    const generatedBodies = fetchMock.mock.calls
      .filter((c) => (typeof c[0] === 'string' ? (c[0] as string).endsWith('/api/word/pack/jobs') : ((c[0] as URL).toString().endsWith('/api/word/pack/jobs'))))
      .map((c) => (c[1]?.body ? JSON.parse(c[1]!.body as string) : {}));
    expect(generatedBodies.some((body) => body.lemma === 'Ghosts')).toBe(true);
  });

  it('keeps the current preview modal content when generating an unknown lemma from an example', async () => {
    const sourceId = 'wp:22222222222222222222222222222222';
    const fetchMock = setupFetchMocks({ [sourceId]: 'theta' });
    render(
      <AppProviders googleClientId="test-client">
        <WordPackPreviewModal
          isOpen
          onClose={vi.fn()}
          wordPackId={sourceId}
          wordPacks={[{
            id: sourceId,
            lemma: 'theta',
            sense_title: 'theta概説',
            created_at: '2026-06-14T00:00:00Z',
            updated_at: '2026-06-14T00:00:00Z',
            checked_only_count: 0,
            learned_count: 0,
          }]}
        />
        <GenerationQueuePanel />
      </AppProviders>,
    );

    const user = userEvent.setup();
    const dialog = await screen.findByRole('dialog', { name: /WordPack プレビュー: theta/ });
    expect(await within(dialog).findByText('theta のCommon例文1')).toBeInTheDocument();

    const ghostToken = await within(dialog).findByText((content, element) => {
      if (!element) return false;
      if (!element.matches('span.lemma-token')) return false;
      return content.trim() === 'Ghosts';
    });

    await act(async () => {
      await user.hover(ghostToken);
    });
    await waitFor(() => {
      const tipEl = Array.from(document.querySelectorAll('.lemma-tooltip')).find((el) => el.textContent === '未生成');
      expect(tipEl).toBeTruthy();
    });

    const ghostLookupCountBeforeGenerate = fetchMock.mock.calls.filter((call) => {
      const url = typeof call[0] === 'string' ? call[0] : (call[0] as URL).toString();
      return url.includes('/api/word/lemma/Ghosts');
    }).length;

    await act(async () => {
      await user.click(ghostToken);
    });

    const queue = await screen.findByRole('region', { name: '生成キュー', hidden: true });
    await waitFor(() => {
      expect(within(queue).getAllByText('Ghosts').length).toBeGreaterThan(0);
      expect(within(queue).getAllByText('完了').length).toBeGreaterThan(0);
    });

    const dialogAfterGeneration = screen.getByRole('dialog', { name: /WordPack プレビュー: theta/ });
    expect(within(dialogAfterGeneration).getByText('theta のCommon例文1')).toBeInTheDocument();
    expect(within(dialogAfterGeneration).queryByText('Ghosts のDev例文1')).not.toBeInTheDocument();

    const generatedSummary = await screen.findByRole('complementary', { name: 'Ghosts のWordPack概要' });
    expect(within(generatedSummary).getAllByText(/Ghosts概説/).length).toBeGreaterThan(0);

    const urls = fetchMock.mock.calls.map((call) => (
      typeof call[0] === 'string' ? call[0] : (call[0] as URL).toString()
    ));
    expect(urls.some((url) => url.endsWith('/api/word/pack/jobs'))).toBe(true);
    expect(urls.filter((url) => url.includes('/api/word/lemma/Ghosts')).length).toBe(ghostLookupCountBeforeGenerate);
  });

  it('prevents duplicate detached generation requests while an unknown lemma is in flight', async () => {
    const sourceId = 'wp:33333333333333333333333333333333';
    let releaseGeneration: (() => void) | null = null;
    const wordPackPostGate = new Promise<void>((resolve) => {
      releaseGeneration = resolve;
    });
    const fetchMock = setupFetchMocks({ [sourceId]: 'theta' }, { wordPackPostGate });
    render(
      <AppProviders googleClientId="test-client">
        <WordPackPreviewModal
          isOpen
          onClose={vi.fn()}
          wordPackId={sourceId}
          wordPacks={[{
            id: sourceId,
            lemma: 'theta',
            sense_title: 'theta概説',
            created_at: '2026-06-14T00:00:00Z',
            updated_at: '2026-06-14T00:00:00Z',
            checked_only_count: 0,
            learned_count: 0,
          }]}
        />
        <GenerationQueuePanel />
      </AppProviders>,
    );

    const user = userEvent.setup();
    const dialog = await screen.findByRole('dialog', { name: /WordPack プレビュー: theta/ });
    const ghostToken = await within(dialog).findByText((content, element) => {
      if (!element) return false;
      if (!element.matches('span.lemma-token')) return false;
      return content.trim() === 'Ghosts';
    });

    await act(async () => {
      await user.hover(ghostToken);
    });
    await waitFor(() => {
      const tipEl = Array.from(document.querySelectorAll('.lemma-tooltip')).find((el) => el.textContent === '未生成');
      expect(tipEl).toBeTruthy();
    });

    const wordPackPostCount = () => fetchMock.mock.calls.filter((call) => {
      const url = typeof call[0] === 'string' ? call[0] : (call[0] as URL).toString();
      return url.endsWith('/api/word/pack/jobs') && call[1]?.method === 'POST';
    }).length;

    await act(async () => {
      await user.click(ghostToken);
    });
    await waitFor(() => expect(wordPackPostCount()).toBe(1));

    await act(async () => {
      await user.click(ghostToken);
    });
    expect(wordPackPostCount()).toBe(1);

    await act(async () => {
      releaseGeneration?.();
    });

    const queue = await screen.findByRole('region', { name: '生成キュー', hidden: true });
    await waitFor(() => {
      expect(within(queue).getAllByText('Ghosts').length).toBeGreaterThan(0);
      expect(within(queue).getAllByText('完了').length).toBeGreaterThan(0);
    });
    expect(wordPackPostCount()).toBe(1);
  });

  it('blocks guest unknown lemma generation from example tokens before write requests', async () => {
    try {
      localStorage.setItem('wordpack.auth.v1', JSON.stringify({ authMode: 'guest' }));
    } catch {}
    const fetchMock = setupFetchMocks();
    render(
      <AppProviders googleClientId="test-client">
        <WordPackPanel focusRef={{ current: null }} selectedWordPackId="wp:guest" />
      </AppProviders>,
    );

    const user = userEvent.setup();
    const ghostToken = await screen.findByText((content, element) => {
      if (!element) return false;
      if (!element.matches('span.lemma-token')) return false;
      return content.trim() === 'Ghosts';
    });

    await act(async () => {
      await user.hover(ghostToken);
    });

    await waitFor(() => {
      const tipEl = Array.from(document.querySelectorAll('.lemma-tooltip')).find(
        (el) => el.textContent === '未生成（ログインが必要）',
      );
      expect(tipEl).toBeTruthy();
    });

    await act(async () => {
      await user.click(ghostToken);
    });

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('ゲストモードでは例文中の未生成語をWordPack生成できません。ログインすると未生成語を追加できます。');
    const generatedBodies = fetchMock.mock.calls
      .filter((c) => (typeof c[0] === 'string' ? (c[0] as string).endsWith('/api/word/pack/jobs') : ((c[0] as URL).toString().endsWith('/api/word/pack/jobs'))))
      .map((c) => (c[1]?.body ? JSON.parse(c[1]!.body as string) : {}));
    expect(generatedBodies.some((body) => body.lemma === 'Ghosts')).toBe(false);
  });

  it('blocks invalid unknown lemma tokens before write requests', async () => {
    const fetchMock = setupFetchMocks();
    render(
      <AppProviders googleClientId="test-client">
        <WordPackPanel focusRef={{ current: null }} selectedWordPackId="wp:long-token" />
      </AppProviders>,
    );

    const user = userEvent.setup();
    const longTokenText = 'SupercalifragilisticexpialidociousSupercalifragilisticexpialidocious';
    const longToken = await screen.findByText((content, element) => {
      if (!element) return false;
      if (!element.matches('span.lemma-token')) return false;
      return content.trim() === longTokenText;
    });

    await act(async () => {
      await user.hover(longToken);
    });

    await waitFor(() => {
      const tipEl = Array.from(document.querySelectorAll('.lemma-tooltip')).find(
        (el) => el.textContent?.startsWith('作成不可:'),
      );
      expect(tipEl).toBeTruthy();
    });

    await act(async () => {
      await user.click(longToken);
    });

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(`「${longTokenText}」はWordPackとして生成できません。見出し語は最大64文字までです`);
    const generatedBodies = fetchMock.mock.calls
      .filter((c) => (typeof c[0] === 'string' ? (c[0] as string).endsWith('/api/word/pack/jobs') : ((c[0] as URL).toString().endsWith('/api/word/pack/jobs'))))
      .map((c) => (c[1]?.body ? JSON.parse(c[1]!.body as string) : {}));
    expect(generatedBodies.some((body) => body.lemma === longTokenText)).toBe(false);
  });

  // Note: 二重採点防止のテストは実装の複雑さのため、手動テストで確認
  // モーダルが開いている間は、WordPackPanelのキーハンドラーが無効化されることを確認済み
});
