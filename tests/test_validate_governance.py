from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validate_governance import (
    GovernanceError,
    markdown_targets,
    validate_links,
    validate_skills,
)


def _write_skill(
    root: Path,
    tree: str,
    directory: str,
    *,
    name: str | None = None,
    body: str = "",
) -> Path:
    path = root / tree / directory / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"name: {name or directory}\n"
        "description: synthetic governance fixture\n"
        "---\n"
        f"{body}",
        encoding="utf-8",
    )
    return path


def _skill_tree(
    root: Path,
    *,
    canonical: dict[str, str] | None = None,
    adapters: dict[str, str] | None = None,
    router_content: str | None = None,
    adapter_bodies: dict[str, str] | None = None,
) -> tuple[Path, Path]:
    canonical = canonical or {"sample": "sample"}
    adapters = adapters or {directory: directory for directory in canonical}
    for directory, name in canonical.items():
        _write_skill(root, ".agents/skills", directory, name=name)
    for directory, name in adapters.items():
        body = (adapter_bodies or {}).get(
            directory,
            f"[canonical](../../../.agents/skills/{directory}/SKILL.md)\n",
        )
        _write_skill(root, ".claude/skills", directory, name=name, body=body)

    router = root / "AGENTS.md"
    if router_content is None:
        router_content = "\n".join(
            f"[{directory}](.agents/skills/{directory}/SKILL.md)"
            for directory in canonical
        ) + "\n"
    router.write_text(router_content, encoding="utf-8")
    return root, router


def test_validate_skills_accepts_matching_identity_and_rendered_links(tmp_path: Path) -> None:
    root, router = _skill_tree(tmp_path)

    assert validate_skills(root, [router]) == (1, 1, 1)


@pytest.mark.parametrize("side", ["canonical", "adapter"])
def test_validate_skills_rejects_name_that_differs_from_directory(
    tmp_path: Path, side: str
) -> None:
    kwargs: dict[str, object] = {}
    if side == "canonical":
        kwargs["canonical"] = {"sample": "other"}
    else:
        kwargs["adapters"] = {"sample": "other"}
    root, router = _skill_tree(tmp_path, **kwargs)

    with pytest.raises(GovernanceError, match="must match its directory"):
        validate_skills(root, [router])


@pytest.mark.parametrize("side", ["canonical", "adapter"])
def test_validate_skills_rejects_duplicate_frontmatter_names(
    tmp_path: Path, side: str
) -> None:
    kwargs: dict[str, object] = {}
    if side == "canonical":
        kwargs["canonical"] = {"alpha": "same", "beta": "same"}
    else:
        kwargs["canonical"] = {"alpha": "alpha", "beta": "beta"}
        kwargs["adapters"] = {"alpha": "same", "beta": "same"}
    root, router = _skill_tree(tmp_path, **kwargs)

    with pytest.raises(GovernanceError, match="duplicate .*frontmatter name"):
        validate_skills(root, [router])


@pytest.mark.parametrize(
    "canonical,adapters,message",
    [
        (
            {"sample": "sample", "other": "other"},
            {"sample": "sample"},
            "missing adapters: other",
        ),
        (
            {"sample": "sample"},
            {"sample": "sample", "orphan": "orphan"},
            "orphan adapters: orphan",
        ),
    ],
)
def test_validate_skills_requires_matching_canonical_and_adapter_names(
    tmp_path: Path,
    canonical: dict[str, str],
    adapters: dict[str, str],
    message: str,
) -> None:
    root, router = _skill_tree(
        tmp_path,
        canonical=canonical,
        adapters=adapters,
    )

    with pytest.raises(GovernanceError, match=message):
        validate_skills(root, [router])


@pytest.mark.parametrize(
    "surface,content",
    [
        ("inline", "`[sample]({target})`\n"),
        ("indented", "    [sample]({target})\n"),
        ("fence", "````md\n[sample]({target})\n````\n"),
        ("comment", "<!-- [sample]({target}) -->\n"),
        ("router_image", "![sample]({target})\n"),
        ("adapter", "![sample]({target})\n"),
    ],
)
def test_validate_skills_requires_rendered_markdown_link(
    tmp_path: Path, surface: str, content: str
) -> None:
    target = ".agents/skills/sample/SKILL.md"
    router_content = content.format(target=target)
    adapter_bodies = None
    if surface == "adapter":
        router_content = f"[sample]({target})\n"
        adapter_bodies = {
            "sample": content.format(
                target="../../../.agents/skills/sample/SKILL.md"
            )
        }
    root, router = _skill_tree(
        tmp_path,
        router_content=router_content,
        adapter_bodies=adapter_bodies,
    )

    with pytest.raises(GovernanceError, match="must link"):
        validate_skills(root, [router])


@pytest.mark.parametrize(
    "content",
    [
        f"{chr(96)}[sample]({{target}}){chr(96)}\n",
        "    [sample]({target})\n",
        f"{chr(96) * 4}md\n[sample]({{target}})\n{chr(96) * 4}\n",
        "<!-- [sample]({target}) -->\n",
    ],
)
def test_validate_skills_requires_rendered_link_in_adapter(
    tmp_path: Path, content: str
) -> None:
    target = "../../../.agents/skills/sample/SKILL.md"
    root, router = _skill_tree(
        tmp_path,
        router_content="[sample](.agents/skills/sample/SKILL.md)\n",
        adapter_bodies={"sample": content.format(target=target)},
    )

    with pytest.raises(GovernanceError, match="must link"):
        validate_skills(root, [router])


def test_markdown_targets_can_exclude_images_for_reachability(tmp_path: Path) -> None:
    source = tmp_path / "AGENTS.md"
    source.write_text("[doc](linked.md)\n![asset](asset.png)\n", encoding="utf-8")

    link_only = set(markdown_targets(source, tmp_path, include_images=False))
    all_targets = set(markdown_targets(source, tmp_path))

    assert link_only == {(tmp_path / "linked.md").resolve()}
    assert all_targets == {
        (tmp_path / "linked.md").resolve(),
        (tmp_path / "asset.png").resolve(),
    }


@pytest.mark.parametrize("href", ["./references/missing.md", "../missing.md"])
def test_validate_links_rejects_broken_relative_local_targets(
    tmp_path: Path, href: str
) -> None:
    skill = _write_skill(
        tmp_path,
        ".agents/skills",
        "sample",
        body=f"[missing]({href})\n",
    )

    with pytest.raises(GovernanceError, match="broken local link"):
        validate_links([skill], tmp_path)


def test_validate_links_accepts_existing_peer_skill_with_parent_reference(
    tmp_path: Path,
) -> None:
    _write_skill(tmp_path, ".agents/skills", "peer")
    sample = _write_skill(
        tmp_path,
        ".agents/skills",
        "sample",
        body="[peer](../peer/SKILL.md)\n",
    )

    validate_links([sample], tmp_path)


def test_validate_links_still_checks_broken_image_targets(tmp_path: Path) -> None:
    source = tmp_path / "AGENTS.md"
    source.write_text("![missing](missing.png)\n", encoding="utf-8")

    with pytest.raises(GovernanceError, match="broken local link"):
        validate_links([source], tmp_path)
