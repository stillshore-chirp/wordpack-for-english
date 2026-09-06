import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { GoogleOAuthProvider } from '@react-oauth/google';
import { APP_EVENTS, dispatchAppEvent } from './shared/events/appEvents';

export interface AuthenticatedUser {
  google_sub: string;
  email: string;
  display_name: string;
  last_login_at?: string;
  [key: string]: unknown;
}

/**
 * Google Identity Services が返す CredentialResponse.credential（ID トークン）を示す型エイリアス。
 * 文字列そのものだが、呼び出し側が用途を見失わないよう意味付けを明示する。
 */
export type GoogleIdToken = string;

export type AuthMode = 'authenticated' | 'guest' | 'anonymous';
export type LogoutOutcome = 'confirmed' | 'failed' | 'unknown';

const isLogoutRecoveryOutcome = (outcome: LogoutOutcome | null): outcome is Exclude<LogoutOutcome, 'confirmed'> =>
  outcome === 'failed' || outcome === 'unknown';

export interface SignOutResult {
  outcome: LogoutOutcome;
  status?: number;
}

interface StoredAuthPayload {
  authMode: 'authenticated' | 'guest';
  user?: AuthenticatedUser;
  // UI 用に保持したい追加情報を将来拡張できるように予約枠を残す。
  [key: string]: unknown;
}

interface StoredLogoutRecovery {
  outcome: Exclude<LogoutOutcome, 'confirmed'>;
}

interface LogoutBroadcastMessage {
  type: 'logout-recovery';
  version: 1;
  outcome: LogoutOutcome;
}

type StorageKind = 'local' | 'session';

interface AuthContextValue {
  user: AuthenticatedUser | null;
  authMode: AuthMode;
  isGuest: boolean;
  isAuthenticating: boolean;
  error: string | null;
  logoutOutcome: LogoutOutcome | null;
  signIn: (idToken: GoogleIdToken) => Promise<void>;
  signOut: () => Promise<SignOutResult>;
  enterGuestMode: () => Promise<void>;
  clearError: () => void;
  authBypassActive: boolean;
  missingClientId: boolean;
  googleClientId: string;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const STORAGE_KEY = 'wordpack.auth.v1';
const LOGOUT_RECOVERY_STORAGE_KEY = 'wordpack.logout.v1';
const LOGOUT_BROADCAST_CHANNEL_NAME = 'wordpack.logout.v1';
const LOGOUT_BROADCAST_MESSAGE_TYPE = 'logout-recovery';
const LOGOUT_BROADCAST_VERSION = 1 as const;
// 回復マーカー以上の容量を使い、near-quotaでprobeだけ成功する判定を避ける。
const LOGOUT_STORAGE_PROBE_KEY = 'wordpack.logout.storage-probe.v1';
const NOTIFICATIONS_STORAGE_KEY = 'wpfe.notifications.v1';
const SESSION_UI_STORAGE_KEYS = ['wp.list.ui_state.v1', 'examples.list.ui_state.v1'];
export const LOGOUT_REQUEST_TIMEOUT_MS = 15_000;

function getStorage(kind: StorageKind): Storage | null {
  if (typeof window === 'undefined') return null;
  try {
    return kind === 'local' ? window.localStorage : window.sessionStorage;
  } catch {
    return null;
  }
}

function readStorageItem(storage: Storage | null, key: string): { available: boolean; value: string | null } {
  if (!storage) return { available: false, value: null };
  try {
    return { available: true, value: storage.getItem(key) };
  } catch {
    return { available: false, value: null };
  }
}

function removeStorageItem(storage: Storage | null, key: string): void {
  if (!storage) return;
  try {
    storage.removeItem(key);
  } catch {
    // 1項目の削除失敗で他の個人情報の掃除を止めない。
  }
}

function writeStorageItem(storage: Storage | null, key: string, value: string): boolean {
  if (!storage) return false;
  try {
    storage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

function isStorageWritable(storage: Storage | null): boolean {
  const previous = readStorageItem(storage, LOGOUT_STORAGE_PROBE_KEY);
  if (!previous.available) return false;
  const probeValue = JSON.stringify({ outcome: 'unknown' } satisfies StoredLogoutRecovery);
  try {
    storage?.setItem(LOGOUT_STORAGE_PROBE_KEY, probeValue);
    const roundTrip = storage?.getItem(LOGOUT_STORAGE_PROBE_KEY) === probeValue;
    if (previous.value === null) {
      storage?.removeItem(LOGOUT_STORAGE_PROBE_KEY);
    } else {
      storage?.setItem(LOGOUT_STORAGE_PROBE_KEY, previous.value);
    }
    return roundTrip;
  } catch {
    // probeの掃除もbest-effortに留め、保存領域の例外を認証処理へ伝播させない。
    try {
      if (previous.value === null) {
        storage?.removeItem(LOGOUT_STORAGE_PROBE_KEY);
      } else {
        storage?.setItem(LOGOUT_STORAGE_PROBE_KEY, previous.value);
      }
    } catch {
      // 書込み不能なstorageは回復マーカーの保存先として使わない。
    }
    return false;
  }
}

function isLogoutRecoveryStorageUsable(storage: Storage | null): boolean {
  return readStorageItem(storage, LOGOUT_RECOVERY_STORAGE_KEY).available && isStorageWritable(storage);
}

function createLogoutBroadcastChannel(): BroadcastChannel | null {
  if (typeof window === 'undefined') return null;
  const BroadcastChannelConstructor = (window as Window & {
    BroadcastChannel?: typeof BroadcastChannel;
  }).BroadcastChannel;
  if (typeof BroadcastChannelConstructor !== 'function') return null;
  try {
    return new BroadcastChannelConstructor(LOGOUT_BROADCAST_CHANNEL_NAME);
  } catch {
    return null;
  }
}

function canUseLogoutBroadcastChannel(): boolean {
  const channel = createLogoutBroadcastChannel();
  if (!channel) return false;
  try {
    channel.close();
  } catch {
    // capability probeのclose失敗は、送信経路を利用不能として扱う。
    return false;
  }
  return true;
}

function trackPendingRequest<T>(pending: Set<Promise<unknown>>, request: Promise<T>): Promise<T> {
  const tracked = Promise.resolve(request);
  pending.add(tracked);
  // finally()の戻り値がrejectした場合も、元の認証処理へ追加のunhandled rejectionを作らない。
  void tracked.finally(() => pending.delete(tracked)).catch(() => undefined);
  return tracked;
}

export const LOGOUT_RECOVERY_MESSAGES: Record<Exclude<LogoutOutcome, 'confirmed'>, string> = {
  failed:
    'ログアウトに失敗しました。画面上の個人情報は削除しましたが、サーバー側のセッションは終了していない可能性があります。再試行してください。',
  unknown:
    'ログアウトの結果を確認できませんでした。画面上の個人情報は削除しましたが、サーバー側のセッション状態は未確認です。再試行してください。',
};

const AUTH_BYPASS_USER: AuthenticatedUser = {
  google_sub: 'dev-bypass',
  email: 'dev@wordpack.local',
  display_name: 'WordPack Dev User',
};

function readRuntimeGoogleClientId(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') return null;
  const value = (payload as { google_client_id?: unknown }).google_client_id;
  if (typeof value !== 'string') return null;
  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}

/**
 * ローカルストレージから最後に成功した認証情報を読み取る。
 * 副作用: window が存在しない環境では何もしない。
 */
function readStoredAuth(): StoredAuthPayload | null {
  const { available, value: raw } = readStorageItem(getStorage('local'), STORAGE_KEY);
  if (!available) return null;
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<StoredAuthPayload> & { token?: unknown };
    if (!parsed || typeof parsed !== 'object') return null;
    if (parsed.authMode === 'guest') {
      return { authMode: 'guest' };
    }
    if (parsed.user && typeof parsed.user === 'object') {
      // 互換性確保のため、旧バージョンが保存した token フィールドは読み飛ばし
      // （破棄）し、UI 用のユーザー情報だけを復元する。
      return { authMode: 'authenticated', user: parsed.user as AuthenticatedUser };
    }
  } catch (error) {
    console.warn('Failed to parse stored auth payload', error);
  }
  return null;
}

function parseStoredLogoutRecovery(raw: string | null): StoredLogoutRecovery | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<StoredLogoutRecovery>;
    if (parsed.outcome === 'failed' || parsed.outcome === 'unknown') {
      return { outcome: parsed.outcome };
    }
  } catch {
    console.warn('Stored logout recovery state is invalid; keeping logout unresolved');
  }
  // 不明な形式も安全側へ倒し、保存済みの認証表示を復元しない。
  return { outcome: 'unknown' };
}

function parseLogoutBroadcastMessage(value: unknown): LogoutBroadcastMessage | null {
  if (!value || typeof value !== 'object') return null;
  const message = value as Partial<LogoutBroadcastMessage>;
  if (message.type !== LOGOUT_BROADCAST_MESSAGE_TYPE || message.version !== LOGOUT_BROADCAST_VERSION) {
    return null;
  }
  if (message.outcome !== 'confirmed' && message.outcome !== 'failed' && message.outcome !== 'unknown') {
    return null;
  }
  return {
    type: LOGOUT_BROADCAST_MESSAGE_TYPE,
    version: LOGOUT_BROADCAST_VERSION,
    outcome: message.outcome,
  };
}

function readStoredLogoutRecovery(): StoredLogoutRecovery | null {
  if (typeof window === 'undefined') return null;
  const localStorage = getStorage('local');
  const sessionStorage = getStorage('session');
  const local = readStorageItem(localStorage, LOGOUT_RECOVERY_STORAGE_KEY);
  const session = readStorageItem(sessionStorage, LOGOUT_RECOVERY_STORAGE_KEY);
  const stored = parseStoredLogoutRecovery(local.value) ?? parseStoredLogoutRecovery(session.value);
  if (stored) return stored;
  // 片方だけが利用不能でも、もう片方で回復マーカーの保存可否を確認できるなら
  // 初期認証を不必要にunknownへ倒さない。両方ともusableでない場合だけfail-closedにする。
  const localUsable = isLogoutRecoveryStorageUsable(localStorage);
  const sessionUsable = isLogoutRecoveryStorageUsable(sessionStorage);
  if (!localUsable && !sessionUsable) {
    return { outcome: 'unknown' };
  }
  // localStorageが使えない場合、sessionStorageだけでは兄弟tabへ状態を伝えられない。
  // BroadcastChannelも初期化できない環境では、再読込後の認証入口をfail-closedにする。
  if (!localUsable && !canUseLogoutBroadcastChannel()) {
    return { outcome: 'unknown' };
  }
  return null;
}

function persistLogoutRecovery(outcome: Exclude<LogoutOutcome, 'confirmed'> | null): void {
  const local = getStorage('local');
  const session = getStorage('session');
  if (outcome === null) {
    removeStorageItem(local, LOGOUT_RECOVERY_STORAGE_KEY);
    removeStorageItem(session, LOGOUT_RECOVERY_STORAGE_KEY);
    return;
  }
  const serialized = JSON.stringify({ outcome } satisfies StoredLogoutRecovery);
  // localStorageを主経路にしつつ、private mode等での書き込み拒否に備えてsessionStorageにも保存する。
  writeStorageItem(local, LOGOUT_RECOVERY_STORAGE_KEY, serialized);
  writeStorageItem(session, LOGOUT_RECOVERY_STORAGE_KEY, serialized);
}

/**
 * ログアウト時にローカルへ残るユーザー由来の表示情報を消去する。
 * HttpOnly CookieはJavaScriptから操作せず、サーバーのlogout応答だけに任せる。
 */
function clearLocalPersonalData(): void {
  const local = getStorage('local');
  const session = getStorage('session');
  removeStorageItem(local, STORAGE_KEY);
  removeStorageItem(local, NOTIFICATIONS_STORAGE_KEY);
  SESSION_UI_STORAGE_KEYS.forEach((key) => removeStorageItem(session, key));
  // Storage実装に依存しないReact stateの掃除通知は常に発火する。
  dispatchAppEvent(APP_EVENTS.localAuthDataCleared);
}

/**
 * 現在の認証状態をローカルストレージへ保存する。
 * 副作用: 認証解除時は保存内容を破棄する。
 * 備考: ID トークンは XSS 時の二次被害を避けるため保存しない。HttpOnly Cookie を前提に
 *       セッションを維持し、ストレージには UI 表示に必要なユーザー情報のみを残す。
 */
function persistAuth(payload: StoredAuthPayload | null): void {
  const local = getStorage('local');
  if (payload === null) {
    removeStorageItem(local, STORAGE_KEY);
    return;
  }
  // ゲスト閲覧モードはログイン不要の入口として用いるため、再読み込み後も状態を維持する。
  writeStorageItem(local, STORAGE_KEY, JSON.stringify(payload));
}

export const AuthProvider: React.FC<{ clientId: string; children: React.ReactNode }> = ({ clientId, children }) => {
  const [initialAuthState] = useState(() => {
    const storedLogoutRecovery = readStoredLogoutRecovery();
    if (storedLogoutRecovery) {
      // 前回のログアウト結果が未確認のままなら、Cookie再送で認証UIを復元しない。
      return {
        authMode: 'anonymous' as const,
        user: null as AuthenticatedUser | null,
        logoutOutcome: storedLogoutRecovery.outcome as LogoutOutcome,
      };
    }
    const stored = readStoredAuth();
    if (stored?.authMode === 'guest') {
      return {
        authMode: 'guest' as const,
        user: null as AuthenticatedUser | null,
        logoutOutcome: null,
      };
    }
    if (stored?.authMode === 'authenticated' && stored.user) {
      return {
        authMode: 'authenticated' as const,
        user: stored.user,
        logoutOutcome: null,
      };
    }
    return {
      authMode: 'anonymous' as const,
      user: null as AuthenticatedUser | null,
      logoutOutcome: null,
    };
  });
  const [user, setUser] = useState<AuthenticatedUser | null>(initialAuthState.user);
  const [authMode, setAuthMode] = useState<AuthMode>(initialAuthState.authMode);
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [logoutOutcome, setLogoutOutcomeState] = useState<LogoutOutcome | null>(initialAuthState.logoutOutcome);
  const [authBypassActive, setAuthBypassActive] = useState(false);
  const [runtimeGoogleClientId, setRuntimeGoogleClientId] = useState<string | null>(null);
  /**
   * /api/config の初期ロードが完了したかを記録する。
   * 新参メンバー向けに補足すると、このフラグが true になるまでは
   * Google クライアント ID の警告ログを抑制し、誤検知による混乱を避ける。
   */
  const [authConfigResolved, setAuthConfigResolved] = useState(false);
  const buildTimeClientId = useMemo(() => clientId.trim(), [clientId]);
  const normalizedClientId = runtimeGoogleClientId ?? buildTimeClientId;
  const clientIdRef = useRef(normalizedClientId);
  const authModeRef = useRef<AuthMode>(authMode);
  const logoutOutcomeRef = useRef<LogoutOutcome | null>(initialAuthState.logoutOutcome);
  const authOperationSequenceRef = useRef(0);
  const activeAuthOperationRef = useRef<{ id: number; kind: 'sign-in' | 'logout' | 'guest' } | null>(null);
  const logoutRequestRef = useRef<Promise<SignOutResult> | null>(null);
  const logoutBroadcastChannelRef = useRef<BroadcastChannel | null>(null);
  const pendingSessionRequestsRef = useRef<Set<Promise<unknown>>>(new Set());
  // 外部logoutと重なった発行を、storage eventの配送順に依存せず再確認するための世代。
  const sessionIssueGenerationRef = useRef(0);
  const sessionIssueDirtyRef = useRef(false);
  /**
   * ゲストセッション再発行の並行実行を防ぐフラグ。
   * 新参メンバー向けに補足すると、複数の 401 が同時発生しても最初のリクエストのみが
   * 実行され、後続の重複呼び出しは無視される。これにより遅延した失敗リクエストが
   * 成功済みセッションを誤って anonymous に戻す競合を防止する。
   */
  const isReissuingGuestRef = useRef<boolean>(false);
  const shouldWaitForRuntimeClientId = buildTimeClientId.length === 0 && !authConfigResolved;
  const missingClientId = normalizedClientId.length === 0;

  useEffect(() => {
    clientIdRef.current = normalizedClientId;
    if (!authConfigResolved || normalizedClientId) {
      return;
    }
    const message = 'VITE_GOOGLE_CLIENT_ID is not set; Google login will not work.';
    if (authBypassActive) {
      console.warn(
        `${message} Authentication bypass is active; continuing with development fallback.`,
      );
      return;
    }
    console.error(message);
  }, [normalizedClientId, authConfigResolved, authBypassActive]);

  const updateAuthMode = useCallback((next: AuthMode) => {
    // 重要: authModeRef は「最新のモードを即座に参照する」ための退避先。
    // /api/config のような初期ロードが非常に高速に完了すると、setState の再レンダー前に
    // 非同期処理側が参照する可能性があるため、ref と state を同時に更新して競合を避ける。
    authModeRef.current = next;
    setAuthMode(next);
  }, []);

  const updateLogoutOutcome = useCallback((next: LogoutOutcome | null) => {
    logoutOutcomeRef.current = next;
    setLogoutOutcomeState(next);
  }, []);

  const notifyLogoutRecovery = useCallback((outcome: LogoutOutcome): boolean => {
    const channel = logoutBroadcastChannelRef.current;
    if (!channel) return false;
    try {
      channel.postMessage({
        type: LOGOUT_BROADCAST_MESSAGE_TYPE,
        version: LOGOUT_BROADCAST_VERSION,
        outcome,
      } satisfies LogoutBroadcastMessage);
      return true;
    } catch {
      // BroadcastChannelの送信失敗は、localStorageも使えない場合にだけ
      // server logoutのconfirmed表示を抑止する。エラー内容は公開しない。
      logoutBroadcastChannelRef.current = null;
      try {
        channel.close();
      } catch {
        // close失敗は回復状態の保存を妨げない。
      }
      console.warn('Could not broadcast logout recovery state');
      return false;
    }
  }, []);

  const isCurrentAuthOperation = useCallback(
    (id: number) => authOperationSequenceRef.current === id,
    [],
  );

  const finishAuthOperation = useCallback((id: number) => {
    if (activeAuthOperationRef.current?.id !== id) return;
    activeAuthOperationRef.current = null;
    setIsAuthenticating(false);
  }, []);

  const beginAuthOperation = useCallback((kind: 'sign-in' | 'guest'): number | null => {
    if (activeAuthOperationRef.current) return null;
    const id = authOperationSequenceRef.current + 1;
    authOperationSequenceRef.current = id;
    activeAuthOperationRef.current = { id, kind };
    setIsAuthenticating(true);
    return id;
  }, []);

  const trackSessionRequest = useCallback(<T,>(request: Promise<T>): Promise<T> => {
    sessionIssueGenerationRef.current += 1;
    sessionIssueDirtyRef.current = true;
    return trackPendingRequest(pendingSessionRequestsRef.current, request);
  }, []);

  const waitForSessionRequests = useCallback(async (): Promise<boolean> => {
    const pending = Array.from(pendingSessionRequestsRef.current);
    if (pending.length === 0) return true;

    let timeoutId: number | undefined;
    const drained = Promise.allSettled(pending).then(() => true);
    const timeout = new Promise<boolean>((resolve) => {
      timeoutId = window.setTimeout(() => resolve(false), LOGOUT_REQUEST_TIMEOUT_MS);
    });
    try {
      return await Promise.race([drained, timeout]);
    } finally {
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    }
  }, []);

  useEffect(() => {
    if (authMode === 'guest') {
      persistAuth({ authMode: 'guest' });
      return;
    }
    if (authMode === 'authenticated' && user) {
      persistAuth({ authMode: 'authenticated', user });
      return;
    }
    persistAuth(null);
  }, [authMode, user]);

  useEffect(() => {
    let aborted = false;
    const configOperationId = authOperationSequenceRef.current;
    (async () => {
      try {
        const res = await fetch('/api/config', { method: 'GET' });
        if (!res.ok) return;
        const json = (await res
          .json()
          .catch(() => null)) as { session_auth_disabled?: boolean; google_client_id?: string } | null;
        const runtimeClientId = readRuntimeGoogleClientId(json);
        // runtime client IDは認証状態とは独立した設定なので、logout等で認証世代が
        // 更新されても、mount中に届いた有効な設定を破棄しない。
        if (!aborted && runtimeClientId) {
          setRuntimeGoogleClientId(runtimeClientId);
        }
        // session_auth_disabledは認証状態へ影響するため、開始時の世代を厳密に確認する。
        if (aborted || !isCurrentAuthOperation(configOperationId)) return;
        if (json?.session_auth_disabled && !isLogoutRecoveryOutcome(logoutOutcomeRef.current) && !activeAuthOperationRef.current) {
          setAuthBypassActive(true);
          setUser((prev) => (authModeRef.current === 'guest' ? prev : prev ?? AUTH_BYPASS_USER));
        }
      } catch (err) {
        console.warn('Failed to detect authentication bypass flag from /api/config', err);
      } finally {
        if (!aborted) {
          setAuthConfigResolved(true);
        }
      }
    })();
    return () => {
      aborted = true;
    };
  }, [isCurrentAuthOperation]);

  useEffect(() => {
    if (!authBypassActive || user || authMode !== 'anonymous' || isLogoutRecoveryOutcome(logoutOutcomeRef.current)) {
      return;
    }
    /**
     * バイパスフラグ有効時にユーザー情報を初期化する。
     * 新規参画者向け補足: 認証をスキップする開発専用ルートを確実に起動するため、
     * ここでモックユーザーを注入する。ID トークンは保持せず、Cookie によるセッションだけを信頼する。
     */
    setUser(AUTH_BYPASS_USER);
    updateAuthMode('authenticated');
  }, [authBypassActive, user, authMode, updateAuthMode]);

  /**
   * Google から取得した ID トークンをバックエンドへ送信し、セッションを確立する。
   * 副作用: セッション Cookie 設定、ユーザー状態の更新、エラー時は状態クリア。
   * 注意: XSS 耐性を高めるため、ID トークンはローカル状態へ保持せずスコープ終了とともに破棄する。
   */
  const signIn = useCallback(async (idToken: GoogleIdToken) => {
    if (isLogoutRecoveryOutcome(logoutOutcomeRef.current)) {
      const message = LOGOUT_RECOVERY_MESSAGES[logoutOutcomeRef.current];
      setError(message);
      throw new Error(message);
    }
    const operationId = beginAuthOperation('sign-in');
    if (operationId === null) {
      throw new Error('認証処理が進行中です。完了してから再試行してください。');
    }
    updateLogoutOutcome(null);
    setError(null);
    try {
      const response = await trackSessionRequest(fetch('/api/auth/google', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ id_token: idToken }),
      }));
      const payload = (await response.json().catch(() => null)) as
        | { user?: AuthenticatedUser; detail?: string }
        | null;
      if (!response.ok || !payload || !payload.user) {
        const detail = payload?.detail || 'Unknown error';
        throw new Error(detail);
      }
      if (!isCurrentAuthOperation(operationId) || isLogoutRecoveryOutcome(logoutOutcomeRef.current)) return;
      setUser(payload.user);
      updateAuthMode('authenticated');
    } catch (err) {
      if (!isCurrentAuthOperation(operationId)) return;
      console.error('Google sign-in failed', err);
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Google sign-in failed');
      }
      throw err;
    } finally {
      finishAuthOperation(operationId);
    }
  }, [beginAuthOperation, finishAuthOperation, isCurrentAuthOperation, trackSessionRequest, updateAuthMode, updateLogoutOutcome]);

  /**
   * バックエンドへログアウトを通知し、サーバー応答の確度を状態へ反映する。
   * 200/204だけをserver-side invalidation確認済みとし、HTTP失敗と通信結果不明を分ける。
   */
  const requestLogout = useCallback(async (): Promise<SignOutResult> => {
    const existingRequest = logoutRequestRef.current;
    if (existingRequest) return existingRequest;

    const operationId = authOperationSequenceRef.current + 1;
    authOperationSequenceRef.current = operationId;
    const sessionIssueGenerationAtStart = sessionIssueGenerationRef.current;
    // ログアウトは進行中のログイン・ゲスト処理を無効化し、遅れて返る結果で認証状態を戻させない。
    activeAuthOperationRef.current = { id: operationId, kind: 'logout' };
    setIsAuthenticating(true);
    // ローカル情報と永続化した認証状態は通信の結果を待たずに消去する。
    // 先に unknown を保存しておくことで、リクエストがハングしたまま再読込されても
    // Cookie由来の認証UIを復元せず、結果確認が必要な状態を維持できる。
    clearLocalPersonalData();
    setUser(null);
    updateAuthMode('anonymous');
    // 開発用バイパスが有効でも、明示的なログアウト直後に認証UIを再注入しない。
    setAuthBypassActive(false);
    persistLogoutRecovery('unknown');
    notifyLogoutRecovery('unknown');
    updateLogoutOutcome('unknown');
    setError(LOGOUT_RECOVERY_MESSAGES.unknown);

    const request = (async (): Promise<SignOutResult> => {
      let result: SignOutResult;
      const drained = await waitForSessionRequests();
      if (!drained) {
        // セッション発行応答の到着順を確定できない間はlogoutを送らず、後続のretryへ委ねる。
        result = { outcome: 'unknown' };
        console.warn('Could not drain pending session requests before logout');
      } else {
        const controller = new AbortController();
        let timeoutId: number | undefined;
        try {
          const response = await Promise.race([
            fetch('/api/auth/logout', {
              method: 'POST',
              credentials: 'include',
              signal: controller.signal,
            }),
            new Promise<never>((_, reject) => {
              timeoutId = window.setTimeout(() => {
                controller.abort();
                reject(new Error('Logout request timed out'));
              }, LOGOUT_REQUEST_TIMEOUT_MS);
            }),
          ]);
          if (response.status === 204 || response.status === 200) {
            result = { outcome: 'confirmed', status: response.status };
          } else {
            result = {
              outcome: 'failed',
              status: response.status,
            };
            console.warn('Unexpected response when logging out', response.status);
          }
        } catch {
          // 応答を受け取れない場合、server-sideで処理済みかどうかは判定できない。
          result = { outcome: 'unknown' };
          console.warn('Could not confirm backend logout result');
        } finally {
          if (timeoutId !== undefined) window.clearTimeout(timeoutId);
        }
      }

      // より新しい認証操作が開始済みなら、その操作の状態を上書きしない。
      if (!isCurrentAuthOperation(operationId)) return result;

      const notified = notifyLogoutRecovery(result.outcome);
      if (!notified && !isLogoutRecoveryStorageUsable(getStorage('local'))) {
        // localStorageとBroadcastChannelの両方が使えない場合、別タブへ結果を
        // 伝えられず、confirmed/failedを全体状態として断定できない。
        if (result.outcome !== 'unknown') {
          console.warn('Could not synchronize logout recovery state across tabs');
        }
        result = { outcome: 'unknown' };
      }

      if (result.outcome === 'confirmed') {
        if (sessionIssueGenerationRef.current === sessionIssueGenerationAtStart) {
          sessionIssueDirtyRef.current = false;
        }
        persistLogoutRecovery(null);
        updateLogoutOutcome('confirmed');
        setError(null);
      } else {
        persistLogoutRecovery(result.outcome);
        updateLogoutOutcome(result.outcome);
        setError(LOGOUT_RECOVERY_MESSAGES[result.outcome]);
      }
      finishAuthOperation(operationId);
      return result;
    })();

    let trackedRequest: Promise<SignOutResult>;
    trackedRequest = request.finally(() => {
      if (logoutRequestRef.current === trackedRequest) {
        logoutRequestRef.current = null;
      }
    });
    logoutRequestRef.current = trackedRequest;
    return trackedRequest;
  }, [finishAuthOperation, isCurrentAuthOperation, notifyLogoutRecovery, updateAuthMode, updateLogoutOutcome, waitForSessionRequests]);

  const signOut = useCallback(() => requestLogout(), [requestLogout]);

  const clearError = useCallback(() => setError(null), []);

  /**
   * ログイン不要で画面を閲覧するためのゲストモードへ切り替える。
   * なぜ: まず UI を体験したい利用者の入口を確保し、学習開始までのハードルを下げるため。
   * 補足: バックエンドの /api/auth/guest は { mode: "guest" } と HttpOnly Cookie を返す。
   */
  const enterGuestMode = useCallback(async () => {
    if (isLogoutRecoveryOutcome(logoutOutcomeRef.current)) {
      setError(LOGOUT_RECOVERY_MESSAGES[logoutOutcomeRef.current]);
      return;
    }
    if (activeAuthOperationRef.current) {
      return;
    }

    setError(null);
    const logoutResult = await requestLogout();
    if (logoutResult.outcome !== 'confirmed') {
      return;
    }

    const operationId = beginAuthOperation('guest');
    if (operationId === null) return;
    updateLogoutOutcome(null);
    try {
      const response = await trackSessionRequest(fetch('/api/auth/guest', {
        method: 'POST',
        credentials: 'include',
      }));
      const payload = (await response.json().catch(() => null)) as { mode?: string; detail?: string } | null;
      if (!response.ok || payload?.mode !== 'guest') {
        throw new Error(payload?.detail || 'Guest session request failed');
      }
      if (!isCurrentAuthOperation(operationId) || isLogoutRecoveryOutcome(logoutOutcomeRef.current)) return;
      setUser(null);
      updateAuthMode('guest');
    } catch (err) {
      if (!isCurrentAuthOperation(operationId)) return;
      console.warn('Failed to enter guest mode', err);
      // ゲスト Cookie が確立できない場合は匿名状態を維持し、誤って guest 表示に遷移しない。
      setError('ゲストモードの開始に失敗しました。しばらくしてから再試行してください。');
    } finally {
      finishAuthOperation(operationId);
    }
  }, [beginAuthOperation, finishAuthOperation, isCurrentAuthOperation, requestLogout, trackSessionRequest, updateAuthMode, updateLogoutOutcome]);

  /**
   * ゲストセッションの再発行を試みる。
   * なぜ: ゲスト利用中の 401 は Cookie の期限切れが主因のため、無駄なログアウト通知を避けて
   *      体験を中断しないようにバックエンドへ再発行のみを依頼する。
   * 並行制御: 複数の 401 が同時発生しても最初のリクエストのみが実行され、後続は無視される。
   *          これにより遅延した失敗リクエストが成功済みセッションを anonymous に戻す競合を防ぐ。
   */
  const reissueGuestSession = useCallback(async () => {
    // 単一実行ガード: 既に再発行中なら重複呼び出しを無視する
    if (isReissuingGuestRef.current) {
      return;
    }
    isReissuingGuestRef.current = true;
    const operationId = authOperationSequenceRef.current + 1;
    authOperationSequenceRef.current = operationId;
    try {
      const response = await trackSessionRequest(fetch('/api/auth/guest', {
        method: 'POST',
        credentials: 'include',
      }));
      const payload = (await response.json().catch(() => null)) as { mode?: string; detail?: string } | null;
      if (!response.ok || payload?.mode !== 'guest') {
        throw new Error(payload?.detail || 'Guest session request failed');
      }
      // 再発行リクエスト中にユーザーが別の操作でモードを変更した可能性を考慮
      if (!isCurrentAuthOperation(operationId) || authModeRef.current !== 'guest' || isLogoutRecoveryOutcome(logoutOutcomeRef.current)) {
        return;
      }
      setError(null);
      updateAuthMode('guest');
    } catch {
      console.warn('Failed to reissue guest session');
      // 再発行リクエスト中にユーザーが別の操作でモードを変更した可能性を考慮
      if (!isCurrentAuthOperation(operationId) || authModeRef.current !== 'guest' || isLogoutRecoveryOutcome(logoutOutcomeRef.current)) {
        return;
      }
      clearLocalPersonalData();
      setUser(null);
      updateAuthMode('anonymous');
      setError('ゲストセッションの再発行に失敗しました。しばらくしてから再試行してください。');
    } finally {
      // 成功・失敗に関わらず、次の再発行を許可するためフラグをリセット
      isReissuingGuestRef.current = false;
    }
  }, [isCurrentAuthOperation, trackSessionRequest, updateAuthMode]);

  /**
   * どのエンドポイントでも 401 が返った場合に、セッション切れとして扱う。
   * fetchJson は `auth:unauthorized` カスタムイベントを発火するため、ここで
   * それを監視してクライアント側状態を初期化する。
   */
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ status?: number }>).detail;
      if (detail && detail.status === 401) {
        if (activeAuthOperationRef.current?.kind === 'logout' || isLogoutRecoveryOutcome(logoutOutcomeRef.current)) {
          return;
        }
        if (authModeRef.current === 'guest') {
          void reissueGuestSession();
          return;
        }
        // 401 は進行中のログイン・guest開始も無効化する。古い応答の finally が
        // isAuthenticating を解除できるよう、active ref はここで明示的に解放する。
        activeAuthOperationRef.current = null;
        setIsAuthenticating(false);
        authOperationSequenceRef.current += 1;
        clearLocalPersonalData();
        setUser(null);
        updateAuthMode('anonymous');
        setAuthBypassActive(false);
        setError('セッションの有効期限が切れました。もう一度ログインしてください。');
      }
    };
    window.addEventListener(APP_EVENTS.authUnauthorized, handler as EventListener);
    return () => {
      window.removeEventListener(APP_EVENTS.authUnauthorized, handler as EventListener);
    };
  }, [reissueGuestSession, updateAuthMode]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const channel = createLogoutBroadcastChannel();
    if (!channel) return;

    channel.onmessage = (event: MessageEvent<unknown>) => {
      const message = parseLogoutBroadcastMessage(event.data);
      if (!message) return;
      // 受信したメッセージを再broadcastせず、既存のstorage handlerへ一方向に
      // 渡すことで、storage eventとの重複があってもping-pongを起こさない。
      window.dispatchEvent(new StorageEvent('storage', {
        key: LOGOUT_RECOVERY_STORAGE_KEY,
        newValue: message.outcome === 'confirmed'
          ? null
          : JSON.stringify({ outcome: message.outcome } satisfies StoredLogoutRecovery),
      }));
    };
    logoutBroadcastChannelRef.current = channel;

    return () => {
      channel.onmessage = null;
      if (logoutBroadcastChannelRef.current === channel) {
        logoutBroadcastChannelRef.current = null;
      }
      try {
        channel.close();
      } catch {
        // close失敗はアンマウント時の認証状態へ伝播させない。
      }
    };
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== LOGOUT_RECOVERY_STORAGE_KEY) return;

      // 別タブのconfirmed通知は、このタブの発行リクエストが残っているときだけでは
      // server-side logoutの完了を保証しない。発行応答が後着してCookieを再発行する
      // 可能性があるため、ローカル状態を先に消去してから、このタブ自身のlogoutで
      // 発行リクエストのsettle後にもう一度失効を確認する。
      const hasPendingSessionRequest =
        event.newValue === null && pendingSessionRequestsRef.current.size > 0;
      const hasSessionIssueOverlap =
        event.newValue === null && (hasPendingSessionRequest || sessionIssueDirtyRef.current);
      const hasLogoutInFlight = logoutRequestRef.current !== null;

      // 既にこのタブのlogoutがdrainまたはserver応答待ちなら、storage通知の種類を問わず
      // その世代を無効化しない。進行中のlogoutをstale扱いにすると、自処理の結果を受けても
      // confirmed/failed/unknownを反映できず、かえって回復操作を隠すことになる。
      if (hasLogoutInFlight) return;

      const stored = parseStoredLogoutRecovery(event.newValue);
      const nextOutcome: LogoutOutcome = event.newValue === null
        ? 'confirmed'
        : stored?.outcome ?? 'unknown';
      authOperationSequenceRef.current += 1;
      activeAuthOperationRef.current = null;
      setIsAuthenticating(false);
      clearLocalPersonalData();
      setUser(null);
      updateAuthMode('anonymous');
      setAuthBypassActive(false);
      if (hasSessionIssueOverlap) {
        // 別タブのconfirmedはこのタブの発行履歴を処理しないため、再確認が終わるまで
        // unknownをdurableに残す。requestLogoutはpending requestをdrainしてから送信する。
        persistLogoutRecovery('unknown');
        updateLogoutOutcome('unknown');
        setError(LOGOUT_RECOVERY_MESSAGES.unknown);
        void requestLogout();
        return;
      }
      if (nextOutcome === 'confirmed') {
        // 別タブの成功通知で、このタブのsessionStorage fallbackも掃除する。
        persistLogoutRecovery(null);
        updateLogoutOutcome('confirmed');
        setError(null);
      } else {
        // localStorageイベントを受けたタブでもfallback markerを保持する。
        persistLogoutRecovery(nextOutcome);
        updateLogoutOutcome(nextOutcome);
        setError(LOGOUT_RECOVERY_MESSAGES[nextOutcome]);
      }
    };
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, [requestLogout, updateAuthMode, updateLogoutOutcome]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      authMode,
      isGuest: authMode === 'guest',
      isAuthenticating,
      error,
      logoutOutcome,
      signIn,
      signOut,
      enterGuestMode,
      clearError,
      authBypassActive,
      missingClientId,
      googleClientId: normalizedClientId,
    }),
    [
      user,
      authMode,
      isAuthenticating,
      error,
      logoutOutcome,
      signIn,
      signOut,
      enterGuestMode,
      clearError,
      authBypassActive,
      missingClientId,
      normalizedClientId,
    ],
  );

  if (shouldWaitForRuntimeClientId) {
    return null;
  }

  const contextNode = <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;

  if (missingClientId) {
    /**
     * Google OAuth プロバイダーはクライアント ID が空のままでは初期化に失敗する。
     * 新規メンバーが遭遇しても認証 UI 自体は動作させたいので、ここでラップを省略する。
     */
    return contextNode;
  }

  return (
    <GoogleOAuthProvider clientId={normalizedClientId} locale="ja">
      {contextNode}
    </GoogleOAuthProvider>
  );
};

export const useAuth = (): AuthContextValue => {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
};
