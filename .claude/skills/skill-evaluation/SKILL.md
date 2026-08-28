---
name: skill-evaluation
description: "独自Skillの静的品質、instruction budget、代表scenario、benchmark比較の共有SkillをClaude Codeから呼び出す。"
---

# skill-evaluation adapter

このファイルはClaude Code向けの薄いadapterです。独自Skillの追加・変更、品質監査、token budget、benchmark、before/after比較を扱う前に、[`.agents/skills/skill-evaluation/SKILL.md`](../../../.agents/skills/skill-evaluation/SKILL.md) を読み、その内容を唯一の手順正本として適用します。

Claude Code固有のtool名や操作は、正本のpreflight、artifact境界、live実行条件、配送権限を変更しません。
