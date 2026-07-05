import hashlib
from typing import Annotated

from pydantic import AliasChoices, Field, PrivateAttr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources.types import NoDecode

from ..llm_models import DEFAULT_LLM_MODEL


_MIN_SESSION_SECRET_KEY_LENGTH = 32
# ローカル開発環境で `uvicorn` を直接叩くときは 127.0.0.1 のみを信頼する。
_DEFAULT_LOCAL_TRUSTED_PROXY: tuple[str, ...] = ("127.0.0.1",)
_PLACEHOLDER_SESSION_SECRETS = frozenset({
    "change-me",
    "changeme",
    "change-me-to-random-value",
    "please-change-me",
})
_KNOWN_LEAKED_SESSION_SECRET_SHA256 = frozenset(
    {
        # ハッシュ値だけを保持し、過去に公開してしまった文字列の再利用を検知する。
        "8450352d877b76fb1f1ff9814c28408b254399e695f97bc3e446ee01dcd317d5",
    }
)

# Cloud Run/External HTTP(S) Load Balancer が付与する `X-Forwarded-For` から
# 実クライアント IP を復元するために信頼すべき既定 CIDR。
# なぜ: 本番環境でロードバランサ経由のアクセスを扱う際に、これらのレンジを
# 信頼しないと RateLimit やアクセスログが全件ロードバランサ IP と解釈される。
_DEFAULT_PRODUCTION_TRUSTED_PROXIES: tuple[str, ...] = (
    "35.191.0.0/16",
    "130.211.0.0/22",
)


def _is_known_leaked_session_secret(secret: str) -> bool:
    """Return True when the given secret matches a previously published value.

    なぜ: ドキュメントで一度でも掲載したシークレットは攻撃者に周知されているため、
    起動時に検知して強制停止し、安全な乱数へ差し替える運用を徹底させる。
    """

    hashed = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    return hashed in _KNOWN_LEAKED_SESSION_SECRET_SHA256


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    環境変数から読み込まれるアプリ設定クラス。
    - environment: 実行環境（development/staging/production など）
    - llm_provider: 利用する LLM プロバイダ
    - embedding_provider: 利用するベクトル埋め込みプロバイダ
    """

    environment: str = Field(
        default="development",
        description="Runtime environment / 実行環境",
    )
    gcp_project_id: str | None = Field(
        default=None,
        description=(
            "Google Cloud project ID used for trace correlation / "
            "Cloud Logging のトレース関連付けに利用する GCP プロジェクト ID"
        ),
        validation_alias=AliasChoices(
            "gcp_project_id",
            "GCP_PROJECT_ID",
            "GOOGLE_CLOUD_PROJECT",
            "PROJECT_ID",
        ),
    )
    firestore_project_id: str | None = Field(
        default=None,
        description="Firestore project ID / Firestore 接続に利用するプロジェクト ID",
        validation_alias=AliasChoices(
            "firestore_project_id",
            "FIRESTORE_PROJECT_ID",
        ),
    )
    firestore_emulator_host: str | None = Field(
        default=None,
        description="Firestore emulator host (hostname:port) / Firestore エミュレータのホスト:ポート",
        validation_alias=AliasChoices(
            "firestore_emulator_host",
            "FIRESTORE_EMULATOR_HOST",
        ),
    )
    google_client_id: str = Field(
        default="",
        description="Google OAuth client ID / Googleサインイン用クライアントID",
    )
    google_allowed_hd: str | None = Field(
        default=None,
        description="Optional allowed Google Workspace domain / 許可するGoogle Workspaceドメイン",
    )
    google_clock_skew_seconds: int = Field(
        default=60,
        description=(
            "Allowed clock skew when verifying Google ID tokens (seconds) / "
            "Google ID トークン検証時に許容する時計ずれ（秒）"
        ),
    )
    # NoDecode を付与し、カンマ区切りの文字列を JSON と誤解釈しないようにする。
    # なぜ: Cloud Run などの環境変数では配列を JSON 形式で渡しづらく、
    #       README でもカンマ区切りで指定する手順を案内しているため。
    admin_email_allowlist: Annotated[tuple[str, ...], NoDecode] = Field(
        default=(),
        description=(
            "Email addresses allowed to sign in when restrict mode is enabled / "
            "ログインを許可するメールアドレス一覧（制限有効時に使用）"
        ),
    )
    session_secret_key: str = Field(
        default="",
        description="Secret key for signing session cookies / セッションクッキー署名用シークレット",
    )
    session_cookie_name: str = Field(
        default="wp_session",
        description="Session cookie name / セッションクッキー名",
    )
    session_cookie_secure: bool = Field(
        default=False,
        description="Whether to mark session cookie as Secure / セッションクッキーにSecure属性を付与するか",
    )
    session_max_age_seconds: int = Field(
        default=60 * 60 * 24 * 14,
        description="Session lifetime in seconds / セッションの寿命（秒）",
    )
    session_idle_timeout_seconds: int = Field(
        default=60 * 60 * 24 * 7,
        description=(
            "Idle timeout for authenticated server-side sessions / "
            "認証済みサーバー側セッションのアイドルタイムアウト（秒）"
        ),
    )
    session_last_seen_update_interval_seconds: int = Field(
        default=300,
        description=(
            "Minimum interval for updating session last_seen_at / "
            "セッション last_seen_at 更新の最小間隔（秒）"
        ),
    )
    guest_session_cookie_name: str = Field(
        default="wp_guest",
        description="Guest session cookie name / ゲストセッションCookie名",
    )
    guest_session_max_age_seconds: int = Field(
        default=60 * 60 * 24,
        description="Guest session lifetime in seconds / ゲストセッションの寿命（秒）",
    )
    guest_session_idle_timeout_seconds: int = Field(
        default=60 * 60 * 24,
        description=(
            "Idle timeout for guest server-side sessions / "
            "ゲストサーバー側セッションのアイドルタイムアウト（秒）"
        ),
    )
    csrf_protection_enabled: bool = Field(
        default=True,
        description="Enable Fetch Metadata / Origin CSRF guard / CSRF ガードを有効化",
    )
    csrf_trusted_origins: Annotated[tuple[str, ...], NoDecode] = Field(
        default=(),
        description=(
            "Comma separated origins allowed for unsafe cookie requests / "
            "Cookie を伴う unsafe request を許可する Origin 一覧"
        ),
    )
    enforce_owner_scoping: bool = Field(
        default=False,
        description=(
            "Enforce owner_user_id checks for legacy-owned content / "
            "owner_user_id による所有者スコープを強制する"
        ),
    )
    llm_provider: str = Field(
        default="openai",
        description="LLM service provider / 利用するLLMプロバイダ",
    )
    embedding_provider: str = Field(
        default="openai",
        description="Embedding service provider / 利用する埋め込みプロバイダ",
    )
    llm_model: str = Field(
        default=DEFAULT_LLM_MODEL,
        description="LLM model name / 利用するLLMモデル名",
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Embedding model name / 埋め込みモデル名",
    )

    # --- LLM 呼出しのタイムアウト/リトライ ---
    llm_timeout_ms: int = Field(
        default=60000,
        description="Per-attempt timeout for LLM calls (ms) / LLM呼出しの試行毎タイムアウト(ms)",
    )
    llm_max_retries: int = Field(
        default=1,
        description="Max retries for LLM calls / LLM呼出しの最大リトライ回数",
    )
    llm_max_tokens: int = Field(
        default=900,
        description="Max tokens for LLM completion output / LLM出力の最大トークン数",
    )

    # （削除済み）

    # --- Auto seed on startup (optional) ---
    auto_seed_on_startup: bool = Field(
        default=False,
        description="Automatically seed Chroma collections on API startup / 起動時に自動シード",
    )
    auto_seed_word_jsonl: str | None = Field(
        default=None,
        description="Optional JSONL path for word_snippets to seed on startup / 起動時シード用のword_snippets JSONL",
    )
    auto_seed_terms_jsonl: str | None = Field(
        default=None,
        description="Optional JSONL path for domain_terms to seed on startup / 起動時シード用のdomain_terms JSONL",
    )

    # （Chroma 設定は削除）

    # --- API Keys ---
    openai_api_key: str | None = Field(default=None, description="OpenAI API Key")
    voyage_api_key: str | None = Field(default=None, description="Voyage API Key")

    # --- Operations/Observability (PR4) ---
    rate_limit_per_min_ip: int = Field(
        default=240,
        description="Per-IP API requests per minute / IP単位の毎分上限",
    )
    rate_limit_per_min_user: int = Field(
        default=240,
        description="Per-user API requests per minute / 認証セッション単位の毎分上限",
    )
    # --- Security headers ---
    security_hsts_max_age_seconds: int = Field(
        default=63072000,
        description=(
            "Strict-Transport-Security max-age directive in seconds / "
            "Strict-Transport-Security の max-age（秒）"
        ),
    )
    security_hsts_include_subdomains: bool = Field(
        default=True,
        description=(
            "Whether to append includeSubDomains to Strict-Transport-Security / "
            "Strict-Transport-Security に includeSubDomains を付与するか"
        ),
    )
    security_hsts_preload: bool = Field(
        default=False,
        description=(
            "Whether to append preload to Strict-Transport-Security / "
            "Strict-Transport-Security に preload を付与するか"
        ),
    )
    security_csp_default_src: Annotated[tuple[str, ...], NoDecode] = Field(
        default=("'self'",),
        description=(
            "Content-Security-Policy default-src sources (comma separated) / "
            "Content-Security-Policy の default-src で許可するソース"
        ),
        validation_alias=AliasChoices(
            "security_csp_default_src",
            "security_csp_origins",
        ),
    )
    security_csp_connect_src: Annotated[tuple[str, ...], NoDecode] = Field(
        default=(),
        description=(
            "Content-Security-Policy connect-src sources (comma separated). "
            "Empty tuple falls back to default-src / "
            "Content-Security-Policy の connect-src で許可するソース（空の場合は default-src を利用）"
        ),
        validation_alias=AliasChoices(
            "security_csp_connect_src",
            "security_csp_connect_origins",
        ),
    )
    sentry_dsn: str | None = Field(
        default=None, description="Sentry DSN (enable if set)"
    )
    # なぜ: CORS の許可オリジンを設定ファイルから明示することで、誤ったドメインを
    # 許可しないまま本番リリースしてしまうリスクを避ける。未設定の場合は既存の
    # ワイルドカード挙動（認証クッキー非許可）にフォールバックする。
    allowed_cors_origins: Annotated[tuple[str, ...], NoDecode] = Field(
        default=(),
        description=(
            "Comma separated CORS origins / CORS で許可するオリジンのカンマ区切り一覧"
        ),
        validation_alias=AliasChoices("allowed_cors_origins", "cors_allowed_origins"),
    )
    # Langfuse 観測基盤
    langfuse_enabled: bool = Field(
        default=False,
        description="Enable Langfuse tracing/observability / Langfuse の有効化",
    )
    langfuse_public_key: str | None = Field(
        default=None, description="Langfuse public key"
    )
    langfuse_secret_key: str | None = Field(
        default=None, description="Langfuse secret key"
    )
    langfuse_host: str | None = Field(
        default=None, description="Langfuse host (e.g. https://cloud.langfuse.com)"
    )
    langfuse_release: str | None = Field(
        default=None, description="Release/version tag for tracing"
    )
    # Langfuse 除外パス（完全一致 or 接頭一致のワイルドカード*対応）
    langfuse_exclude_paths: list[str] = Field(
        default=["/healthz", "/health", "/metrics*"],
        description="Exclude paths from Langfuse tracing (exact or prefix*)",
    )
    # Langfuse 入力ログの詳細度（LLM プロンプトの全文送信を制御）
    langfuse_log_full_prompt: bool = Field(
        default=False,
        description="Send full LLM prompt to Langfuse in span input (disabled by default)",
    )
    langfuse_prompt_max_chars: int = Field(
        default=40000,
        description="Max characters to record for prompt/input to Langfuse",
    )

    trusted_proxy_ips: Annotated[tuple[str, ...], NoDecode] = Field(
        default=_DEFAULT_LOCAL_TRUSTED_PROXY,
        description=(
            "Trusted proxy IPs/CIDR ranges for ProxyHeadersMiddleware / "
            "ProxyHeadersMiddleware に渡す信頼済みプロキシの IP または CIDR"
        ),
        validation_alias=AliasChoices(
            "trusted_proxy_ips",
            "forwarded_allow_ips",
        ),
    )
    allowed_hosts_raw: str = Field(
        default="*",
        description=(
            "Comma separated allowed hosts for TrustedHostMiddleware / "
            "TrustedHostMiddleware で許可するホスト名（カンマ区切り）"
        ),
        validation_alias=AliasChoices(
            "allowed_hosts",
            "trusted_hosts",
        ),
    )

    _allowed_hosts_values: tuple[str, ...] = PrivateAttr(default_factory=tuple)

    # --- Strict mode ---
    strict_mode: bool = Field(
        default=True,
        description="Fail fast on missing/invalid configuration (disable only for tests)",
    )

    disable_session_auth: bool = Field(
        default=False,
        description=(
            "Disable session cookie authentication (development/testing only) / "
            "セッションクッキー認証を無効化する（開発・テスト用途のみ）"
        ),
    )

    # Pydantic v2 settings config
    # - env_file: .env を読み込む
    # - extra: .env に存在する未使用キー（例: api_key/allowed_origins など）を無視
    # - case_sensitive: 環境変数キーの大小文字を区別しない
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )


    @field_validator("session_secret_key", mode="after")
    @classmethod
    def _validate_session_secret(
        cls, value: str
    ) -> str:
        """Ensure session secret keys are safely randomised before accepting them.

        なぜ: セッション署名鍵が既知のプレースホルダーや短い文字列のまま起動すると
        総当たり攻撃で利用者のセッションが奪取される恐れがあるため、環境変数の
        読み込み段階で検証し、危険な値は即座に拒否する。
        """

        secret = (value or "").strip()
        if not secret:
            raise ValueError(
                "SESSION_SECRET_KEY must be a non-empty random string",
            )

        if secret.casefold() in _PLACEHOLDER_SESSION_SECRETS:
            raise ValueError(
                "SESSION_SECRET_KEY must not use placeholder values like 'change-me'",
            )

        if _is_known_leaked_session_secret(secret):
            raise ValueError(
                "SESSION_SECRET_KEY must not reuse published sample values",
            )

        if len(secret) < _MIN_SESSION_SECRET_KEY_LENGTH:
            raise ValueError(
                "SESSION_SECRET_KEY must be at least 32 characters long",
            )

        return secret

    @field_validator("firestore_emulator_host", mode="after")
    @classmethod
    def _normalize_firestore_emulator_host(cls, host: str | None) -> str | None:
        """Trim emulator host values and treat blanks as unset."""

        cleaned = (host or "").strip()
        return cleaned or None

    @field_validator("admin_email_allowlist", mode="before")
    @classmethod
    def _normalise_admin_allowlist(
        cls, raw_allowlist: object
    ) -> tuple[str, ...] | object:  # pragma: no cover - pydantic handles typing
        """Normalise allowlist values before model parsing.

        文字列/シーケンスのいずれでも受け取り、重複排除・小文字化したタプルへ変換する。
        """

        if raw_allowlist is None:
            candidates: list[str] = []
        elif isinstance(raw_allowlist, str):
            candidates = raw_allowlist.split(",")
        else:
            try:
                candidates = list(raw_allowlist)
            except TypeError:
                return raw_allowlist

        normalised: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            trimmed = candidate.strip().lower()
            if not trimmed or trimmed in seen:
                continue
            seen.add(trimmed)
            normalised.append(trimmed)

        return tuple(normalised)

    @field_validator("allowed_cors_origins", "csrf_trusted_origins", mode="before")
    @classmethod
    def _normalise_allowed_cors_origins(
        cls, raw_origins: object
    ) -> tuple[str, ...] | object:  # pragma: no cover - pydantic handles typing
        """Convert environment input into a deduplicated tuple of origins.

        なぜ: CORS 設定を `.env` で管理するときに空白や重複が混ざりやすいため、
        FastAPI へ渡す前にトリムと重複排除を行って安全な配列へ正規化する。
        """

        if raw_origins is None:
            candidates: list[str] = []
        elif isinstance(raw_origins, str):
            candidates = raw_origins.split(",")
        else:
            try:
                candidates = list(raw_origins)
            except TypeError:
                return raw_origins

        normalised: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            trimmed = candidate.strip()
            if not trimmed or trimmed in seen:
                continue
            seen.add(trimmed)
            normalised.append(trimmed)

        return tuple(normalised)

    @field_validator("trusted_proxy_ips", mode="before")
    @classmethod
    def _normalise_trusted_proxy_ips(
        cls, raw_ips: object
    ) -> tuple[str, ...] | object:  # pragma: no cover - pydantic handles typing
        """Normalise trusted proxy definitions into a trimmed, deduplicated tuple.

        なぜ: Cloud Run やロードバランサの IP 範囲を `.env` で管理するとき、
        空白や重複・誤入力が混ざると本来信頼すべきヘッダが拒否され、
        アクセス元 IP の解析やレート制限の判定が正しく行われなくなる。
        入力段階で正規化し、ProxyHeadersMiddleware へ安全に渡す。
        """

        if raw_ips is None:
            candidates: list[str] = []
        elif isinstance(raw_ips, str):
            candidates = raw_ips.split(",")
        else:
            try:
                candidates = list(raw_ips)
            except TypeError:
                return raw_ips

        normalised: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            trimmed = candidate.strip()
            if not trimmed or trimmed in seen:
                continue
            seen.add(trimmed)
            normalised.append(trimmed)

        return tuple(normalised)

    @property
    def allowed_hosts(self) -> list[str]:
        """Return a parsed list of allowed hosts for middleware consumption.

        なぜ: 設定入力は文字列として受け取りつつ、ミドルウェアではリストを
        要求するため、初期化時に正規化したリストを公開し、外部からの利用者に
        型の差異を意識させない。
        """

        return list(self._allowed_hosts_values)

    @field_validator("allowed_hosts_raw", mode="before")
    @classmethod
    def _coerce_allowed_hosts_raw(cls, raw_hosts: object) -> str | object:
        """Accept sequences for allowed hosts and normalise to comma strings.

        なぜ: 既存設定との互換性を維持しつつ、環境変数や .env にリスト形式で
        記述された値も受け付けるため。ミドルウェアでの利用前に文字列へ統一し、
        予期しない型をそのまま返すことで Pydantic による型検証へ委ねる。
        """

        if raw_hosts is None:
            return ""
        if isinstance(raw_hosts, str):
            return raw_hosts
        try:
            candidates = list(raw_hosts)
        except TypeError:
            return raw_hosts
        return ",".join(candidates)

    @field_validator(
        "security_csp_default_src",
        "security_csp_connect_src",
        mode="before",
    )
    @classmethod
    def _normalise_csp_sources(
        cls, raw_sources: object
    ) -> tuple[str, ...] | object:  # pragma: no cover - pydantic handles typing
        """Normalise CSP directive source values to trimmed, deduplicated tuples.

        なぜ: CSP の許可リストは空白や重複が混ざりやすく、誤ったスペースや
        末尾のスラッシュ差異があるとセキュリティヘッダが意図通りに作用しない。
        事前にトリムと重複排除を行い、設定ミスに起因する許可漏れ/過剰許可を
        防止する。
        """

        if raw_sources is None:
            candidates: list[str] = []
        elif isinstance(raw_sources, str):
            candidates = raw_sources.split(",")
        else:
            try:
                candidates = list(raw_sources)
            except TypeError:
                return raw_sources

        normalised: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            trimmed = candidate.strip()
            if not trimmed or trimmed in seen:
                continue
            seen.add(trimmed)
            normalised.append(trimmed)

        return tuple(normalised)

    @staticmethod
    def _parse_allowed_hosts(raw_hosts: str) -> tuple[str, ...]:
        """Parse and deduplicate allowed hosts from comma separated input.

        なぜ: Host ヘッダの許可リストに重複や空要素が混入すると、意図しない
        ホスト偽装を許してしまう可能性がある。起動時にトリムと重複排除を行い、
        ミドルウェアへ安全な値を渡す。"""

        if not raw_hosts:
            return tuple()

        normalised: list[str] = []
        seen: set[str] = set()
        for candidate in raw_hosts.split(","):
            trimmed = candidate.strip()
            if not trimmed or trimmed in seen:
                continue
            seen.add(trimmed)
            normalised.append(trimmed)

        return tuple(normalised)

    @model_validator(mode="after")
    def _apply_environment_sensitive_defaults(self) -> "Settings":
        """Harmonise environment defaults without overriding explicit choices.

        なぜ: ローカル開発環境（HTTPアクセスが多い）で Secure 属性が有効だと
        document.cookie からセッション Cookie を参照できずログイン検証が失敗する。
        ENVIRONMENT=production のときだけ Secure を既定で有効化し、環境変数や
        テストから明示的に設定された値は上書きしない。また Cloud Run などの
        プロキシを経由する本番環境では、`X-Forwarded-For` を信頼する IP レンジを
        必ず指定しないと実クライアント単位の監査やレート制御が破綻する。加えて、
        本番運用では管理者許可リストが空だと全ユーザーが通過してしまうため、
        ADMIN_EMAIL_ALLOWLIST を必須化して意図しない公開を防ぐ。
        """

        environment_name = (self.environment or "").lower()
        project_id = self.firestore_project_id or self.gcp_project_id
        if not project_id and self.firestore_emulator_host:
            project_id = "local-emulator"
        if not project_id and environment_name != "production":
            project_id = "wordpack-local"
        if project_id:
            self.firestore_project_id = project_id
            if self.gcp_project_id is None:
                self.gcp_project_id = project_id
        elif self.strict_mode:
            raise ValueError(
                "FIRESTORE_PROJECT_ID (or GCP_PROJECT_ID) must be configured for Firestore access"
            )
        parsed_allowed_hosts = self._parse_allowed_hosts(self.allowed_hosts_raw)
        self._allowed_hosts_values = parsed_allowed_hosts
        is_secure_explicitly_configured = "session_cookie_secure" in self.model_fields_set
        if environment_name == "production" and not is_secure_explicitly_configured:
            self.session_cookie_secure = True

        if environment_name == "production" and not self.admin_email_allowlist:
            raise ValueError(
                "ADMIN_EMAIL_ALLOWLIST must specify allowed admin emails in production"
            )

        if environment_name == "production" and self.disable_session_auth:
            raise ValueError(
                "DISABLE_SESSION_AUTH must not be enabled in production"
            )

        if environment_name == "production" and not self.csrf_protection_enabled:
            raise ValueError(
                "CSRF_PROTECTION_ENABLED must not be disabled in production"
            )

        is_trusted_proxy_explicit = "trusted_proxy_ips" in self.model_fields_set
        if environment_name == "production":
            configured_proxies = tuple(self.trusted_proxy_ips or ())
            should_apply_production_defaults = (
                not is_trusted_proxy_explicit
                and configured_proxies == _DEFAULT_LOCAL_TRUSTED_PROXY
            )
            if should_apply_production_defaults:
                self.trusted_proxy_ips = _DEFAULT_PRODUCTION_TRUSTED_PROXIES
                configured_proxies = self.trusted_proxy_ips
            if not configured_proxies:
                raise ValueError(
                    "TRUSTED_PROXY_IPS must be configured in production (e.g. 35.191.0.0/16,130.211.0.0/22)"
                )

        allowed_hosts = parsed_allowed_hosts
        # なぜ: Cloud Run 等の本番環境でワイルドカード Host を許可すると、
        #      Host ヘッダ偽装や別ドメインからの CSRF が成立する恐れがある。
        #      既定の `*` から切り替えられていない場合は早期に失敗させ、
        #      Cloud Run のデフォルト URL やカスタムドメインの明示を強制する。
        if environment_name == "production":
            has_wildcard_host = any(host == "*" for host in allowed_hosts)
            if has_wildcard_host or not allowed_hosts:
                raise ValueError(
                    "ALLOWED_HOSTS must list the Cloud Run default URL or custom domains in production"
                )

        return self


settings = Settings()


__all__ = ["Settings", "settings"]
