#!/usr/bin/env python3
"""Compatibility entrypoint for governance frontmatter validation.

The parser and path-aware checks live in ``validate_governance.py`` so the
repository has one static governance validator.  This small entrypoint remains
for existing task-Skill callers and does not contain a second self-test suite.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.validate_governance import GovernanceError, ROOT, validate_frontmatter


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    try:
        root = ROOT.resolve()
        for path in args.paths:
            validate_frontmatter(path.resolve(), root)
    except (OSError, GovernanceError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
