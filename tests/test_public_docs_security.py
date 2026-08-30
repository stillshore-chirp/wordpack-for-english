from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DOC_GLOBS = (
    "*.md",
    "*.txt",
    "docs/**/*.md",
    "docs/**/*.json",
    "plans/**/*.md",
    "plans/**/*.json",
    ".agents/**/*.md",
    ".agents/**/*.json",
    ".claude/**/*.md",
    ".cursor/**/*.mdc",
    ".github/**/*.md",
    ".github/**/*.json",
    ".github/**/*.yml",
    ".github/**/*.yaml",
)

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private key block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    ),
    (
        "GitHub classic token",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b"),
    ),
    (
        "GitHub fine-grained token",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    ),
    (
        "OpenAI-style API key",
        re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "Google API key",
        re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    ),
    (
        "JWT-like token",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b"
        ),
    ),
    (
        "Authorization header value",
        re.compile(
            r"(?i)\bAuthorization\s*:\s*"
            r"(?!<redacted>|Bearer\s+<redacted>|Bearer\s+\$?\{?[A-Z_]+\}?)[^\s`]{10,}"
        ),
    ),
    (
        "client secret assignment",
        re.compile(
            r"(?i)\bclient_secret\b\s*[:=]\s*"
            r"(?!<redacted>|placeholder|example|dummy|null|環境変数)[\"']?[A-Za-z0-9_\-./+=]{10,}"
        ),
    ),
    (
        "Cloud Run revision exact identifier",
        re.compile(r"\b[a-z][a-z0-9-]{0,40}-\d{5}-[a-z0-9]{3}\b"),
    ),
    (
        "Cloud Run revision suffix",
        re.compile(r"\b\d{5}-[a-z0-9]{3}\b"),
    ),
)


def _iter_doc_files() -> list[Path]:
    files: set[Path] = set()
    for pattern in DOC_GLOBS:
        files.update(path for path in ROOT.glob(pattern) if path.is_file())
    return sorted(files)


def test_public_documents_do_not_contain_high_risk_secret_material() -> None:
    findings: list[str] = []
    for path in _iter_doc_files():
        relative_path = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for label, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(f"{relative_path}:{line_number}: {label}")

    assert not findings, "公開ドキュメントに秘匿値または不要に具体的な運用識別子の疑いがあります:\n" + "\n".join(
        findings
    )


def test_public_text_scan_covers_governance_surfaces_without_binary_evidence() -> None:
    relative_paths = {path.relative_to(ROOT).as_posix() for path in _iter_doc_files()}

    assert "docs/ai-governance/templates/task-state.json" in relative_paths
    assert ".agents/skills/skill-evaluation/references/application-security-benchmark.json" in relative_paths
    assert any(path.startswith(".claude/") and path.endswith(".md") for path in relative_paths)
    assert any(path.startswith(".cursor/") and path.endswith(".mdc") for path in relative_paths)
    assert any(
        path.startswith(".github/") and path.endswith((".md", ".yml", ".yaml"))
        for path in relative_paths
    )
    assert not any(
        Path(path).suffix.lower() in {".gif", ".ico", ".jpeg", ".jpg", ".png", ".webp"}
        for path in relative_paths
    )
