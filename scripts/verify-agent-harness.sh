#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() {
  echo "ERROR: $1" >&2
  exit 1
}

require_file() {
  [[ -f "$1" ]] || fail "required file missing: $1"
}

max_size() {
  local file="$1"
  local max_lines="$2"
  local max_bytes="$3"
  local lines bytes
  lines="$(wc -l < "$file" | tr -d ' ')"
  bytes="$(wc -c < "$file" | tr -d ' ')"
  (( lines <= max_lines )) || fail "$file exceeds ${max_lines} lines: $lines"
  (( bytes <= max_bytes )) || fail "$file exceeds ${max_bytes} bytes: $bytes"
}

require_text() {
  local file="$1"
  local pattern="$2"
  grep -Fq -- "$pattern" "$file" || fail "$file must contain: $pattern"
}

require_block_text() {
  local file="$1"
  local heading="$2"
  local block="$3"
  local pattern="$4"
  local start="<!-- agent-harness:${block}:start -->"
  local end="<!-- agent-harness:${block}:end -->"
  local content
  content="$(python3 - "$file" "$heading" "$start" "$end" <<'PY'
import sys

from markdown_it import MarkdownIt

path, heading, start, end = sys.argv[1:]
source = open(path, encoding="utf-8").read()
tokens = MarkdownIt("commonmark").parse(source)

headings = [
    index
    for index, token in enumerate(tokens[:-2])
    if token.type == "heading_open"
    and token.tag == "h2"
    and token.level == 0
    and tokens[index + 1].type == "inline"
    and tokens[index + 1].content == heading.removeprefix("## ")
    and tokens[index + 2].type == "heading_close"
]
starts = [
    index
    for index, token in enumerate(tokens)
    if token.type == "html_block" and token.level == 0 and token.content.strip() == start
]
ends = [
    index
    for index, token in enumerate(tokens)
    if token.type == "html_block" and token.level == 0 and token.content.strip() == end
]
if len(headings) != 1 or len(starts) != 1 or len(ends) != 1:
    raise SystemExit(2)
heading_index = headings[0]
start_index = starts[0]
end_index = ends[0]
heading_map = tokens[heading_index].map
start_map = tokens[start_index].map
if (
    heading_map is None
    or start_map is None
    or start_map[0] != heading_map[1]
    or start_index <= heading_index + 2
    or end_index <= start_index
):
    raise SystemExit(2)
if any(
    token.type == "heading_open" and token.level == 0 and token.tag in {"h1", "h2"}
    for token in tokens[start_index + 1 : end_index]
):
    raise SystemExit(2)
if end_index + 1 < len(tokens):
    next_token = tokens[end_index + 1]
    if not (
        next_token.type == "heading_open"
        and next_token.level == 0
        and next_token.tag in {"h1", "h2"}
    ):
        raise SystemExit(2)

visible_lines: list[str] = []
for token in tokens[start_index + 1 : end_index]:
    if token.type == "html_block":
        raise SystemExit(2)
    if token.type != "inline":
        continue
    inline_text: list[str] = []
    for child in token.children or []:
        if child.type in {"text", "code_inline"}:
            inline_text.append(child.content)
        elif child.type in {"softbreak", "hardbreak"}:
            inline_text.append("\n")
        elif child.type == "image":
            inline_text.append(f" {child.content} ")
        elif child.type == "html_inline":
            raise SystemExit(2)
        elif child.content:
            inline_text.append(f" {child.content} ")
    visible_lines.append("".join(inline_text))

print("\n".join(visible_lines))
PY
)" || fail "$file block $block must immediately follow heading: $heading"
  grep -Fq -- "$pattern" <<< "$content" || fail "$file block $block must contain: $pattern"
}

require_block_text \
  <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' '> ````md' '> <!-- literal in fenced code -->' '> # Replacement' '> ## Example' '> ````' 'required invariant' '<!-- agent-harness:self-test:end -->') \
  "## Checked" \
  "self-test" \
  "required invariant"
require_block_text \
  <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' 'required **invariant**' '<!-- agent-harness:self-test:end -->') \
  "## Checked" \
  "self-test" \
  "required invariant"
if (
  require_block_text \
    <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' '> ```md' '> required invariant' '> ```' '<!-- agent-harness:self-test:end -->') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification accepted required text inside fenced code"
fi
if (
  require_block_text \
    <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' '<!-- required invariant -->' '<!-- agent-harness:self-test:end -->') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification accepted required text inside an HTML comment"
fi
if (
  require_block_text \
    <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' '<div hidden>' '' 'required invariant' '' '</div>' '' '<!-- agent-harness:self-test:end -->') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification accepted required text inside a hidden HTML container"
fi
if (
  require_block_text \
    <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' '<span hidden>required invariant</span>' '<!-- agent-harness:self-test:end -->') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification accepted required text inside inline HTML"
fi
if (
  require_block_text \
    <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' 'required' 'invariant' '<!-- agent-harness:self-test:end -->') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification joined required text across a soft break"
fi
if (
  require_block_text \
    <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' 'required![other content](missing.png)invariant' '<!-- agent-harness:self-test:end -->') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification dropped image content inside required text"
fi
if (
  require_block_text \
    <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' '<!-- agent-harness:self-test:end -->' 'required invariant') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification accepted required text outside its canonical block"
fi
if (
  require_block_text \
    <(printf '%s\n' '<!--' '## Checked' '<!-- agent-harness:self-test:start -->' 'required invariant' '<!-- agent-harness:self-test:end -->' '-->') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification accepted a canonical block inside an HTML comment"
fi
if (
  require_block_text \
    <(printf '%s\n' '````md' '## Checked' '<!-- agent-harness:self-test:start -->' 'required invariant' '<!-- agent-harness:self-test:end -->' '````') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification accepted a canonical block inside fenced code"
fi
if (
  require_block_text \
    <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' '# Replacement' 'required invariant' '<!-- agent-harness:self-test:end -->') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification accepted a canonical block spanning a peer heading"
fi

reject_text() {
  local file="$1"
  local pattern="$2"
  if grep -Fq -- "$pattern" "$file"; then
    fail "$file contains retired instruction: $pattern"
  fi
}

reject_regex() {
  local file="$1"
  local pattern="$2"
  if grep -Eiq -- "$pattern" "$file"; then
    fail "$file contains environment-specific instruction: $pattern"
  fi
}

REGEX_END_OF_LINE=$'\x24'
REGEX_BACKTICK=$'\x60'
MODEL_ID_CORE='(gpt-[0-9]+[a-z]?([.][0-9]+)*([_-][[:alnum:]]+)*|o[0-9]+([.][0-9]+)*([_-][[:alnum:]]+)*|claude-(opus|sonnet|haiku|[0-9]+)([.][0-9]+)*([_-][[:alnum:]]+)*|gemini-(pro|flash|ultra|[0-9]+)([.][0-9]+)*([_-][[:alnum:]]+)*|llama-[0-9]+([.][0-9]+)*([_-][[:alnum:]]+)*)'
MODEL_ID_TOKEN_PATTERN="(^|[[:space:]\"'${REGEX_BACKTICK}:(){}<*_]|\\[)${MODEL_ID_CORE}([[:space:]\"'${REGEX_BACKTICK}.,;:!?(){}<>*_]|\\]|${REGEX_END_OF_LINE})"
MODEL_ID_SAFE_CONTEXT_PATTERN='(do[[:space:]]+not|does[[:space:]]+not|must[[:space:]]+not|not[[:space:]]+(use|select|require|fixed|specified|mandatory|required|permitted|allowed)|never|without|avoid|forbid|forbidden|prohibit|prohibited|disallowed|optional|example|explanation|mentioned|mention|documentation|禁止|説明|例|しない|ではない|不要|任意|固定しない|指定しない|必須ではない|使わない|利用しない)'

VENDOR_CORE='(OpenAI|Anthropic|Google|AWS|Azure)'
VENDOR_LEAD="(^|[[:space:]${REGEX_BACKTICK}(){}<])"
VENDOR_TRAIL="([[:space:]${REGEX_BACKTICK}.,;:!?(){}<>]|${REGEX_END_OF_LINE})"
VENDOR_AFTER_PATTERN="${VENDOR_LEAD}${VENDOR_CORE}([[:space:]]+(API|SDK|service))?[[:space:]]+(must[[:space:]]+(be[[:space:]]+)?(used|use|selected|select|chosen|choose|required)|is[[:space:]]+(required|mandatory|fixed|specified)|are[[:space:]]+(required|mandatory|fixed|specified)|required|mandatory|fixed|specified)${VENDOR_TRAIL}|${VENDOR_LEAD}${VENDOR_CORE}(は|が|を)[[:space:]]*(必須|固定|指定)([[:space:]]*(とする|にする|です)?[[:space:]。,.!?(){}<>]|${REGEX_END_OF_LINE})"
VENDOR_BEFORE_EN="${VENDOR_LEAD}(must|required|mandatory|fixed|specified)[[:space:]:-]+(use|choose|select|require|provider|vendor)?[[:space:]:-]+${VENDOR_CORE}${VENDOR_TRAIL}|${VENDOR_LEAD}(must|required|mandatory|fixed|specified)[[:space:]:-]+${VENDOR_CORE}${VENDOR_TRAIL}"
VENDOR_BEFORE_JA="${VENDOR_LEAD}(必須|固定|指定)[[:space:]:：_-]+(vendor|provider|の|として)?[[:space:]:：_-]*${VENDOR_CORE}${VENDOR_TRAIL}"
VENDOR_USE_PATTERN="${VENDOR_LEAD}(use|choose|select)[[:space:]]+(the[[:space:]]+)?${VENDOR_CORE}([[:space:]]+(API|SDK|service))?${VENDOR_TRAIL}"
VENDOR_MANDATE_PATTERN="${VENDOR_AFTER_PATTERN}|${VENDOR_BEFORE_EN}|${VENDOR_BEFORE_JA}|${VENDOR_USE_PATTERN}"
VENDOR_SAFE_CONTEXT_PATTERN='(do[[:space:]]+not|does[[:space:]]+not|must[[:space:]]+not|not[[:space:]]+(use|select|require|mandatory|required)|never|without|avoid|optional|example|explanation|mentioned|mention|official|documentation|禁止|説明|例|しない|ではない|不要|任意|固定しない|指定しない|必須ではない|使わない|利用しない)'

TOOL_NAME_CORE='(gh|codex|claude|cursor)'
TOOL_ARGUMENT="(\"[^\"\\\\]*(\\\\.[^\"\\\\]*)*\"|'[^'\\\\]*(\\\\.[^'\\\\]*)*'|[^[:space:]${REGEX_BACKTICK}]+)"
TOOL_COMMAND_PATTERN="${REGEX_BACKTICK}${TOOL_NAME_CORE}([[:space:]]+${TOOL_ARGUMENT})+${REGEX_BACKTICK}|(^|[[:space:](){}<])@${TOOL_NAME_CORE}([[:space:]]+${TOOL_ARGUMENT})+"
# An option keeps a sentence such as "Codex is supported" out of bare-command matches.
TOOL_BARE_COMMAND_PATTERN="^[[:space:]]*([>${REGEX_END_OF_LINE}][[:space:]]*)?${TOOL_NAME_CORE}[[:space:]]+${TOOL_ARGUMENT}([[:space:]]+${TOOL_ARGUMENT})*[[:space:]]+--${TOOL_ARGUMENT}"
MCP_TOOL_PATTERN="(^|[[:space:]${REGEX_BACKTICK}(){}<])mcp__[[:alnum:]_-]+([[:space:]${REGEX_BACKTICK}.,;:!?(){}<>]|${REGEX_END_OF_LINE})"
TOOL_SYNTAX_PATTERN="${TOOL_COMMAND_PATTERN}|${TOOL_BARE_COMMAND_PATTERN}|${MCP_TOOL_PATTERN}"
TOOL_SAFE_CONTEXT_PATTERN='(do[[:space:]]+not|does[[:space:]]+not|must[[:space:]]+not|not|never|without|avoid|optional|example|explanation|mentioned|mention|official|documentation|禁止|説明|例|しない|ではない|不要|任意|固定しない|指定しない|使わない|利用しない)'
ACTION_PREFIX_PATTERN='(^|[[:space:][:punct:]])(use|select|require|choose|run|execute|call|set|inspect|verify|ensure)[[:space:]]+'

RUNTIME_KEY_CORE='(default_subagent_model|default_subagent_reasoning_effort|max_concurrent_threads_per_session|OPENAI_API_KEY)'
RUNTIME_KEY_ASSIGNMENT_PATTERN="(^|[[:space:]\"'${REGEX_BACKTICK}{])${RUNTIME_KEY_CORE}[\"']?[[:space:]]*[:=]"
SAFE_SCOPE_MARKER='__agent_harness_safe_scope__'

expect_regex_match() {
  local label="$1"
  local pattern="$2"
  local text="$3"
  grep -Eiq -- "$pattern" <<< "$text" || fail "regex self-test expected match: $label"
}

expect_regex_no_match() {
  local label="$1"
  local pattern="$2"
  local text="$3"
  if grep -Eiq -- "$pattern" <<< "$text"; then
    fail "regex self-test expected no match: $label"
  fi
}

# Split before a clause boundary or a new command/required marker. The scanner
# ignores punctuation inside quoted/backticked arguments. Safe enumerations
# keep their context across commas and connectors; decimal model versions stay
# intact.
split_segments() {
  printf '%s\n' "$1" | awk -v safe_scope_marker="$SAFE_SCOPE_MARKER" '
    BEGIN {
      if ((getline remaining) <= 0) exit
      remaining = tolower(remaining)
      action = "((do|does|must)[[:space:]]+not[[:space:]]+)?(must[[:space:]]+)?(use|select|require|choose|run|execute|call|set|inspect|verify|ensure|is[[:space:]]+(required|mandatory|fixed|specified)|are[[:space:]]+(required|mandatory|fixed|specified)|required|mandatory|fixed|specified|必須|固定|指定|使う|使用|利用|選択|実行|呼び出す)"
      punctuation = "[;,!?。！？、|:.][[:space:]]*" action "[[:space:]]+"
      connector = "[[:space:]]+(and|but|or|then|also|as[[:space:]]+well[[:space:]]+as|かつ|または|ただし|そして)[[:space:]]+" action "[[:space:]]+"
      boundary = "[;,、|:()][[:space:]]*|[.!?][[:space:]]+|[。！？][[:space:]]*"
      safe_intro = "(for[[:space:]]+example|e[.]g[.]|as[[:space:]]+an[[:space:]]+example|例として|たとえば|例えば)"
      safe_scope = 0
      while (find_boundary(remaining)) {
        separator = substr(remaining, boundary_start, boundary_length)
        prefix = substr(remaining, 1, boundary_start - 1)
        if (prefix ~ safe_intro) safe_scope = 1
        print prefix
        sentence_end = separator ~ /^[.!?。！？;]/
        if (separator ~ /^[[:space:]]+(and|but|or|then|also|as[[:space:]]+well[[:space:]]+as|かつ|または|ただし|そして)[[:space:]]+/) {
          sub(/^[[:space:]]+(and|but|or|then|also|as[[:space:]]+well[[:space:]]+as|かつ|または|ただし|そして)[[:space:]]+/, "", separator)
        } else {
          sub(/^[;,!?。！？、|:.()][[:space:]]*/, "", separator)
        }
        if (safe_scope && !sentence_end) separator = safe_scope_marker " " separator
        remaining = separator substr(remaining, boundary_start + boundary_length)
        if (sentence_end) safe_scope = 0
      }
      print remaining
      exit
    }

    function find_boundary(text,    i, ch, candidate, in_backtick, quote, escaped) {
      in_backtick = 0
      quote = ""
      escaped = 0
      for (i = 1; i <= length(text); i++) {
        ch = substr(text, i, 1)
        if (escaped) {
          escaped = 0
          continue
        }
        if (quote != "") {
          if (ch == "\\") {
            escaped = 1
          } else if (ch == quote) {
            quote = ""
          }
          continue
        }
        if (ch == "\\") {
          escaped = 1
          continue
        }
        if (ch == "`") {
          in_backtick = !in_backtick
          continue
        }
        if (in_backtick && (ch == "\"" || ch == sprintf("%c", 39))) {
          quote = ch
          continue
        }
        if (in_backtick) {
          continue
        }
        if (ch == ":" && substr(text, i, 3) == "://") {
          continue
        }
        candidate = substr(text, i)
        if (match(candidate, punctuation) && RSTART == 1) {
          boundary_start = i
          boundary_length = RLENGTH
          return 1
        }
        if (match(candidate, connector) && RSTART == 1) {
          boundary_start = i
          boundary_length = RLENGTH
          return 1
        }
        if (match(candidate, boundary) && RSTART == 1) {
          boundary_start = i
          boundary_length = RLENGTH
          return 1
        }
      }
      return 0
    }
  '
}

segment_is_actionable() {
  local text="$1"
  local token_pattern="$2"
  local safe_pattern="$3"
  local segment
  while IFS= read -r segment; do
    if grep -Eiq -- "$token_pattern" <<< "$segment" \
      && ! grep -Fq -- "$SAFE_SCOPE_MARKER" <<< "$segment"; then
      local context token_offset action_offset safe_before_action
      # URLs are not prose context. A safe word before the instruction keeps
      # the token explanatory; an unrelated safe word after it does not.
      context="$(printf '%s\n' "$segment" | sed -E 's#https?://[^[:space:]]*##g')"
      if ! grep -Eiq -- "$safe_pattern" <<< "$context"; then
        return 0
      fi
      token_offset="$(grep -Eibo -- "$token_pattern" <<< "$context" | head -n1 | cut -d: -f1 || true)"
      action_offset="$(grep -Eibo -- "$ACTION_PREFIX_PATTERN" <<< "$context" \
        | awk -F: -v token_offset="$token_offset" '$1 <= token_offset { print $1; exit }' || true)"
      if [[ -n "$action_offset" ]]; then
        safe_before_action="$(grep -Eibo -- "$safe_pattern" <<< "$context" \
          | awk -F: -v action_offset="$action_offset" '$1 < action_offset { print $1; exit }' || true)"
        if [[ -z "$safe_before_action" ]]; then
          return 0
        fi
        continue
      fi
      # Without an instruction prefix, a safe word remains explanatory
      # context for the matched token.
      continue
    fi
  done < <(split_segments "$text")
  return 1
}

model_id_is_actionable() {
  segment_is_actionable "$1" "$MODEL_ID_TOKEN_PATTERN" "$MODEL_ID_SAFE_CONTEXT_PATTERN"
}

reject_model_ids() {
  local file="$1"
  local line
  while IFS= read -r line || [[ -n "$line" ]]; do
    if model_id_is_actionable "$line"; then
      fail "$file contains an actionable model ID instruction"
    fi
  done < "$file"
}

vendor_mandate_is_actionable() {
  segment_is_actionable "$1" "$VENDOR_MANDATE_PATTERN" "$VENDOR_SAFE_CONTEXT_PATTERN"
}

reject_vendor_mandates() {
  local file="$1"
  local line
  while IFS= read -r line || [[ -n "$line" ]]; do
    if vendor_mandate_is_actionable "$line"; then
      fail "$file contains a mandatory vendor instruction"
    fi
  done < "$file"
}

tool_syntax_is_actionable() {
  segment_is_actionable "$1" "$TOOL_SYNTAX_PATTERN" "$TOOL_SAFE_CONTEXT_PATTERN"
}

reject_tool_syntax() {
  local file="$1"
  local line
  while IFS= read -r line || [[ -n "$line" ]]; do
    if tool_syntax_is_actionable "$line"; then
      fail "$file contains a tool-specific command"
    fi
  done < "$file"
}

expect_regex_match \
  "model version boundary" \
  "$MODEL_ID_TOKEN_PATTERN" \
  "Use ${REGEX_BACKTICK}gpt-5.6${REGEX_BACKTICK}."
expect_regex_match \
  "model variant boundary" \
  "$MODEL_ID_TOKEN_PATTERN" \
  "Use claude-3.7-sonnet."
expect_regex_match \
  "general model token" \
  "$MODEL_ID_TOKEN_PATTERN" \
  "Use o3-mini."
expect_regex_match \
  "family model token" \
  "$MODEL_ID_TOKEN_PATTERN" \
  "Use claude-opus-4-1."
for text in \
  "Use **gpt-5.6**." \
  "Use _gpt-5.6_." \
  "Use [gpt-5.6](https://example.test/models)."; do
  if ! model_id_is_actionable "$text"; then
    fail "regex self-test missed a Markdown-delimited model ID: $text"
  fi
done
expect_regex_no_match \
  "embedded model-like word" \
  "$MODEL_ID_TOKEN_PATTERN" \
  "agpt-5.6 is not a model ID."
expect_regex_match \
  "quoted model token" \
  "$MODEL_ID_TOKEN_PATTERN" \
  "model: \"o3-mini\""
expect_regex_no_match \
  "model ID in official URL" \
  "$MODEL_ID_TOKEN_PATTERN" \
  "See https://example.test/models/gpt-5.6 for documentation."
expect_regex_no_match \
  "model ID in URL query" \
  "$MODEL_ID_TOKEN_PATTERN" \
  "See https://example.test/models?model=gpt-5.6 for documentation."
if ! model_id_is_actionable "Use gpt-5.6."; then
  fail "regex self-test expected an actionable model instruction"
fi
if model_id_is_actionable "For example, use gpt-5.6."; then
  fail "regex self-test lost the safe scope of a model introduction"
fi
for text in \
  "The policy forbids gpt-5.6." \
  "For example, gpt-5.6 is mentioned." \
  "Do not use gpt-5.6."; do
  if model_id_is_actionable "$text"; then
    fail "regex self-test accepted a model explanation or negation: $text"
  fi
done
if ! model_id_is_actionable "The policy forbids gpt-5.6; use claude-opus-4-1."; then
  fail "regex self-test lost an actionable model in a mixed clause"
fi
if ! model_id_is_actionable "Do not use gpt-5.6. Use claude-opus-4-1."; then
  fail "regex self-test lost an actionable model after a sentence boundary"
fi
if ! model_id_is_actionable "Do not use gpt-5.6 and use claude-opus-4-1."; then
  fail "regex self-test lost an actionable model after a connector"
fi
if ! model_id_is_actionable "Use gpt-5.6; consult documentation afterward."; then
  fail "regex self-test suppressed an actionable model before unrelated safe text"
fi
if ! model_id_is_actionable "Use gpt-5.6: consult documentation afterward."; then
  fail "regex self-test suppressed an actionable model before a colon"
fi
if ! model_id_is_actionable "Use gpt-5.6 (see documentation)."; then
  fail "regex self-test suppressed an actionable model before parentheses"
fi
if ! model_id_is_actionable "Use gpt-5.6 documentation."; then
  fail "regex self-test suppressed an actionable model before unrelated documentation"
fi
if model_id_is_actionable "Do not use gpt-5.6 and do not use claude-opus-4-1."; then
  fail "regex self-test accepted a fully negated model sentence"
fi
for text in \
  "Do not use gpt-5.6 or claude-opus-4-1." \
  "For example, gpt-5.6 and claude-opus-4-1."; do
  if model_id_is_actionable "$text"; then
    fail "regex self-test broke safe model enumeration: $text"
  fi
done

expect_regex_match \
  "vendor command after" \
  "$VENDOR_MANDATE_PATTERN" \
  "OpenAI is required."
expect_regex_match \
  "vendor command before" \
  "$VENDOR_MANDATE_PATTERN" \
  "must use OpenAI."
expect_regex_match \
  "vendor use command" \
  "$VENDOR_MANDATE_PATTERN" \
  "Use OpenAI."
expect_regex_match \
  "vendor API use command" \
  "$VENDOR_MANDATE_PATTERN" \
  "Use the OpenAI API."
expect_regex_match \
  "vendor API command after" \
  "$VENDOR_MANDATE_PATTERN" \
  "OpenAI API is required."
expect_regex_match \
  "Japanese vendor command" \
  "$VENDOR_MANDATE_PATTERN" \
  "OpenAIを必須とする。"
expect_regex_no_match \
  "vendor negation" \
  "$VENDOR_MANDATE_PATTERN" \
  "OpenAI is not required."
expect_regex_no_match \
  "vendor explanation" \
  "$VENDOR_MANDATE_PATTERN" \
  "OpenAI is an example provider."
expect_regex_no_match \
  "vendor in official URL" \
  "$VENDOR_MANDATE_PATTERN" \
  "Official URL: https://openai.com/required"
expect_regex_no_match \
  "Japanese vendor negation" \
  "$VENDOR_MANDATE_PATTERN" \
  "ベンダーを固定しない。OpenAIを例に挙げる。"
if vendor_mandate_is_actionable "Do not use OpenAI."; then
  fail "regex self-test accepted a vendor negation"
fi
if ! vendor_mandate_is_actionable "Do not use OpenAI; Use Anthropic."; then
  fail "regex self-test lost an actionable vendor in a mixed clause"
fi
if ! vendor_mandate_is_actionable "Use OpenAI."; then
  fail "regex self-test expected an actionable vendor instruction"
fi
if vendor_mandate_is_actionable "For example, use OpenAI."; then
  fail "regex self-test lost the safe scope of a vendor introduction"
fi
if ! vendor_mandate_is_actionable "Do not use OpenAI. Use Anthropic."; then
  fail "regex self-test lost an actionable vendor after a sentence boundary"
fi
if ! vendor_mandate_is_actionable "Do not use OpenAI and use Anthropic."; then
  fail "regex self-test lost an actionable vendor after a connector"
fi
if ! vendor_mandate_is_actionable "Use OpenAI; consult documentation afterward."; then
  fail "regex self-test suppressed an actionable vendor before unrelated safe text"
fi
if ! vendor_mandate_is_actionable "Use OpenAI: consult documentation afterward."; then
  fail "regex self-test suppressed an actionable vendor before a colon"
fi
if ! vendor_mandate_is_actionable "Use OpenAI (see documentation)."; then
  fail "regex self-test suppressed an actionable vendor before parentheses"
fi
if ! vendor_mandate_is_actionable "Use OpenAI documentation."; then
  fail "regex self-test suppressed an actionable vendor before unrelated documentation"
fi
if vendor_mandate_is_actionable "Do not use OpenAI and do not use Anthropic."; then
  fail "regex self-test accepted a fully negated vendor sentence"
fi
for text in \
  "Do not use OpenAI or Anthropic." \
  "For example, OpenAI and Anthropic."; do
  if vendor_mandate_is_actionable "$text"; then
    fail "regex self-test broke safe vendor enumeration: $text"
  fi
done

expect_regex_match \
  "at-command syntax" \
  "$TOOL_SYNTAX_PATTERN" \
  "@codex review --focus"
expect_regex_match \
  "backticked command syntax" \
  "$TOOL_SYNTAX_PATTERN" \
  "Use ${REGEX_BACKTICK}gh pr create --draft${REGEX_BACKTICK}."
expect_regex_match \
  "backticked quoted argument" \
  "$TOOL_SYNTAX_PATTERN" \
  "Use ${REGEX_BACKTICK}gh pr comment --body \"approved\"${REGEX_BACKTICK}."
expect_regex_match \
  "backticked escaped quoted argument" \
  "$TOOL_SYNTAX_PATTERN" \
  "Use ${REGEX_BACKTICK}gh pr comment --body \"say \\\"approved\\\"\"${REGEX_BACKTICK}."
expect_regex_match \
  "backticked quoted argument with punctuation" \
  "$TOOL_SYNTAX_PATTERN" \
  "Use ${REGEX_BACKTICK}gh pr comment --body \"approved, thanks\"${REGEX_BACKTICK}."
expect_regex_match \
  "bare command syntax" \
  "$TOOL_SYNTAX_PATTERN" \
  "gh pr create --draft"
expect_regex_match \
  "MCP tool syntax" \
  "$TOOL_SYNTAX_PATTERN" \
  "Call mcp__server__tool."
expect_regex_no_match \
  "generic product description" \
  "$TOOL_SYNTAX_PATTERN" \
  "Codex is one of the supported products."
expect_regex_no_match \
  "backticked product name" \
  "$TOOL_SYNTAX_PATTERN" \
  "The product is ${REGEX_BACKTICK}Codex${REGEX_BACKTICK}."
expect_regex_no_match \
  "at-command in official URL" \
  "$TOOL_SYNTAX_PATTERN" \
  "See https://example.test/@codex/review."
expect_regex_no_match \
  "MCP tool in official URL" \
  "$TOOL_SYNTAX_PATTERN" \
  "See https://example.test/mcp__server__tool."
if tool_syntax_is_actionable "Do not use ${REGEX_BACKTICK}gh pr create${REGEX_BACKTICK}."; then
  fail "regex self-test accepted a tool negation"
fi
if ! tool_syntax_is_actionable "Use ${REGEX_BACKTICK}codex review${REGEX_BACKTICK}."; then
  fail "regex self-test expected an actionable tool instruction"
fi
if ! tool_syntax_is_actionable "Use ${REGEX_BACKTICK}codex review${REGEX_BACKTICK}; consult documentation afterward."; then
  fail "regex self-test suppressed an actionable tool before unrelated safe text"
fi
if ! tool_syntax_is_actionable "Use ${REGEX_BACKTICK}codex review${REGEX_BACKTICK}: consult documentation afterward."; then
  fail "regex self-test suppressed an actionable tool before a colon"
fi
if ! tool_syntax_is_actionable "Use ${REGEX_BACKTICK}codex review${REGEX_BACKTICK} (see documentation)."; then
  fail "regex self-test suppressed an actionable tool before parentheses"
fi
if ! tool_syntax_is_actionable "Use ${REGEX_BACKTICK}codex review${REGEX_BACKTICK} documentation."; then
  fail "regex self-test suppressed an actionable tool before unrelated documentation"
fi
if tool_syntax_is_actionable "For example, run ${REGEX_BACKTICK}codex review${REGEX_BACKTICK}."; then
  fail "regex self-test lost the safe scope of a tool introduction"
fi
if ! tool_syntax_is_actionable "Do not use ${REGEX_BACKTICK}gh pr create${REGEX_BACKTICK}. Use ${REGEX_BACKTICK}codex review${REGEX_BACKTICK}."; then
  fail "regex self-test lost an actionable tool after a sentence boundary"
fi
if ! tool_syntax_is_actionable "The example is ${REGEX_BACKTICK}gh pr${REGEX_BACKTICK}; run ${REGEX_BACKTICK}codex review${REGEX_BACKTICK}."; then
  fail "regex self-test lost an actionable tool in a mixed clause"
fi
if ! tool_syntax_is_actionable "Do not use ${REGEX_BACKTICK}gh pr create${REGEX_BACKTICK} and use ${REGEX_BACKTICK}codex review --focus${REGEX_BACKTICK}."; then
  fail "regex self-test lost an actionable tool after a connector"
fi
if tool_syntax_is_actionable "Do not use ${REGEX_BACKTICK}gh pr create${REGEX_BACKTICK} and do not use ${REGEX_BACKTICK}codex review --focus${REGEX_BACKTICK}."; then
  fail "regex self-test accepted a fully negated tool sentence"
fi
for text in \
  "Do not use ${REGEX_BACKTICK}gh pr create${REGEX_BACKTICK} or ${REGEX_BACKTICK}codex review --focus${REGEX_BACKTICK}." \
  "For example, ${REGEX_BACKTICK}gh pr create${REGEX_BACKTICK} and ${REGEX_BACKTICK}codex review --focus${REGEX_BACKTICK}."; do
  if tool_syntax_is_actionable "$text"; then
    fail "regex self-test broke safe tool enumeration: $text"
  fi
done

expect_regex_match \
  "YAML runtime key assignment" \
  "$RUNTIME_KEY_ASSIGNMENT_PATTERN" \
  "default_subagent_model: value"
expect_regex_match \
  "JSON runtime key assignment" \
  "$RUNTIME_KEY_ASSIGNMENT_PATTERN" \
  "{\"default_subagent_model\": \"value\"}"
expect_regex_match \
  "quoted runtime key assignment" \
  "$RUNTIME_KEY_ASSIGNMENT_PATTERN" \
  "'OPENAI_API_KEY' = \"placeholder\""
expect_regex_no_match \
  "runtime key explanation" \
  "$RUNTIME_KEY_ASSIGNMENT_PATTERN" \
  "The default_subagent_model key is documented."
expect_regex_no_match \
  "runtime key in official URL" \
  "$RUNTIME_KEY_ASSIGNMENT_PATTERN" \
  "See https://example.test/default_subagent_model."

CANONICAL_HARNESS_PATHS=(
  "AGENTS.md"
  "CLAUDE.md"
  "apps/frontend/AGENTS.md"
  "apps/backend/AGENTS.md"
  "docs/operations/AGENTS.md"
  "docs/agent-harness.md"
  "docs/agent-principles.md"
  "docs/ai-governance/13-maintenance-policy.md"
  "docs/ai-governance/15-agent-harness-compatibility.md"
  "requirements-agent-harness.txt"
  "scripts/validate_agent_frontmatter.py"
  "scripts/verify-agent-harness.sh"
  "scripts/verify-ai-governance.sh"
  ".agents/skills/ui-ux-review/SKILL.md"
  ".agents/skills/github-delivery/SKILL.md"
  ".agents/skills/production-investigation/SKILL.md"
  ".agents/skills/security-publication/SKILL.md"
  ".claude/rules/agent-governance.md"
  ".claude/rules/agent-harness.md"
  ".claude/rules/frontend.md"
  ".claude/rules/backend.md"
  ".claude/rules/operations.md"
  ".claude/skills/ui-ux-review/SKILL.md"
  ".claude/skills/github-delivery/SKILL.md"
  ".claude/skills/production-investigation/SKILL.md"
  ".claude/skills/security-publication/SKILL.md"
  ".cursor/rules/agent-governance.mdc"
  ".cursor/rules/agent-harness.mdc"
  ".cursor/rules/frontend.mdc"
  ".cursor/rules/backend.mdc"
  ".cursor/rules/operations.mdc"
)

FRONTMATTER_PATHS=()
CLAUDE_RULE_PATHS=()
CLAUDE_SKILL_PATHS=()
CURSOR_RULE_PATHS=()
MODEL_NEUTRAL_PATHS=()

for file in "${CANONICAL_HARNESS_PATHS[@]}"; do
  require_file "$file"
  case "$file" in
    .agents/skills/*/SKILL.md)
      FRONTMATTER_PATHS+=("$file")
      MODEL_NEUTRAL_PATHS+=("$file")
      ;;
    .claude/rules/*)
      FRONTMATTER_PATHS+=("$file")
      CLAUDE_RULE_PATHS+=("$file")
      MODEL_NEUTRAL_PATHS+=("$file")
      ;;
    .claude/skills/*/SKILL.md)
      FRONTMATTER_PATHS+=("$file")
      CLAUDE_SKILL_PATHS+=("$file")
      MODEL_NEUTRAL_PATHS+=("$file")
      ;;
    .cursor/rules/*)
      FRONTMATTER_PATHS+=("$file")
      CURSOR_RULE_PATHS+=("$file")
      MODEL_NEUTRAL_PATHS+=("$file")
      ;;
    AGENTS.md|CLAUDE.md|apps/frontend/AGENTS.md|apps/backend/AGENTS.md|docs/operations/AGENTS.md|docs/agent-harness.md|docs/agent-principles.md|docs/ai-governance/13-maintenance-policy.md|docs/ai-governance/15-agent-harness-compatibility.md|scripts/verify-ai-governance.sh)
      MODEL_NEUTRAL_PATHS+=("$file")
      ;;
  esac
done

for file in "${CANONICAL_HARNESS_PATHS[@]}"; do
  case "$file" in
    AGENTS.md)
      max_size "$file" 180 16384
      ;;
    apps/frontend/AGENTS.md|apps/backend/AGENTS.md|docs/operations/AGENTS.md)
      max_size "$file" 100 8192
      combined_bytes="$(( $(wc -c < AGENTS.md) + $(wc -c < "$file") ))"
      (( combined_bytes <= 24576 )) || fail "AGENTS.md + $file exceeds 24576 bytes: $combined_bytes"
      ;;
    .agents/skills/*/SKILL.md)
      max_size "$file" 180 16384
      ;;
    .claude/rules/*|.claude/skills/*/SKILL.md|.cursor/rules/*)
      max_size "$file" 30 4096
      ;;
  esac
done

python3 scripts/validate_agent_frontmatter.py --self-test
python3 scripts/validate_agent_frontmatter.py "${FRONTMATTER_PATHS[@]}"

CLAUDE_CONTENT="$(tr -d '\r' < CLAUDE.md | sed '/^[[:space:]]*$/d')"
[[ "$CLAUDE_CONTENT" == "@AGENTS.md" ]] || fail "CLAUDE.md must contain only @AGENTS.md"

for file in "${CLAUDE_RULE_PATHS[@]}"; do
  require_text "$file" "AGENTS.md"
done
for file in "${CURSOR_RULE_PATHS[@]}"; do
  require_text "$file" "AGENTS.md"
done
for file in "${CLAUDE_SKILL_PATHS[@]}"; do
  require_text "$file" ".agents/skills/"
  require_text "$file" "唯一の手順正本"
done

for file in "${CLAUDE_RULE_PATHS[@]}" "${CURSOR_RULE_PATHS[@]}"; do
  case "$file" in
    *agent-governance*)
      require_text "$file" "13-maintenance-policy.md"
      require_text "$file" "15-agent-harness-compatibility.md"
      ;;
    *agent-harness*)
      require_text "$file" "agent-harness.md"
      require_text "$file" "13-maintenance-policy.md"
      ;;
  esac
done

for product in "Codex" "Claude Code" "Cursor"; do
  require_text "AGENTS.md" "$product"
  require_text "docs/agent-harness.md" "$product"
  require_text "docs/ai-governance/13-maintenance-policy.md" "$product"
done

for anchor in \
  "## 1. 目的" \
  "## 2. 用語" \
  "## 3. 3エージェントの適用構造" \
  "## 4. 配置判断" \
  "## 5. instruction budget" \
  "## 6. tool中立性" \
  "## 7. hard gateとheuristic" \
  "## 8. ハーネス変更時の互換性レビュー" \
  "## 9. 検証" \
  "## 10. 保守時の停止条件"; do
  require_text "docs/ai-governance/15-agent-harness-compatibility.md" "$anchor"
done
require_text "docs/ai-governance/15-agent-harness-compatibility.md" "scripts/verify-ai-governance.sh"

for path in \
  ".agents/skills/ui-ux-review/SKILL.md" \
  ".agents/skills/github-delivery/SKILL.md" \
  ".agents/skills/production-investigation/SKILL.md" \
  ".agents/skills/security-publication/SKILL.md" \
  "docs/agent-harness.md" \
  "tests/e2e/**" \
  "tests/**/*.py" \
  "docs/api-reference.md" \
  "docs/authentication.md" \
  "docs/firestore.md" \
  ".github/workflows/**"; do
  require_text "AGENTS.md" "$path"
done

reject_text "AGENTS.md" "コードレビュー往復は最大 10 回"
reject_text "AGENTS.md" "P0 または P1 を含まないレビュー結果が 3 回連続"
reject_text "AGENTS.md" "codex/<目的>"
reject_text "AGENTS.md" "Codex 自動コードレビュー"
reject_text "AGENTS.md" "リポジトリ変更の公開まで依頼されている場合"
reject_text ".agents/skills/github-delivery/SKILL.md" "ユーザーが完成した変更のPRを求めている場合"
reject_text ".agents/skills/github-delivery/SKILL.md" "typoや同一PR内の局所修正"
reject_text "scripts/verify-ai-governance.sh" ".cursor directory must not be created"
reject_text "scripts/verify-ai-governance.sh" "コードレビュー往復は最大 10 回"
reject_text "scripts/verify-ai-governance.sh" "P0 または P1 を含まないレビュー結果が 3 回連続"

require_text "docs/agent-harness.md" "Hard gateとheuristic"
require_text "docs/agent-harness.md" "Instruction budget"
require_text "docs/agent-harness.md" "clean review"
require_block_text "AGENTS.md" "## 作業の進め方" "workflow" "サブエージェントは独立して並行実行でき、handoffの固定費に見合うbounded work laneへ使います"
require_block_text "AGENTS.md" "## 作業の進め方" "workflow" "primary agentは要件・計画・割当・進捗・競合・ガバナンス・受入・配送判断を担います"
require_block_text "AGENTS.md" "## 作業の進め方" "workflow" "委任、短い作業のprimary担当、lane owner、長い検証前のprocess状態、HEAD/baseに束縛したevidenceの詳細は"
require_block_text "AGENTS.md" "## 作業の進め方" "workflow" "docs/agent-harness.md"
require_block_text "AGENTS.md" "## 作業の進め方" "workflow" "配送対象の最終HEADではfull gateを原則1回実行します"
require_block_text "AGENTS.md" "## 作業の進め方" "workflow" "包括レビューは同一PR・同一HEAD系列で原則2周まで"
require_block_text "AGENTS.md" "## 作業の進め方" "workflow" "P2以下だけなら影響とnon-blocking判断を記録して収束"
reject_text "AGENTS.md" "同じworktreeとHEADで長い検証を始める前に"
reject_text "AGENTS.md" "各evidenceは対象HEADとbase HEAD、確認済みpath、diff identifierに束縛します"
require_block_text ".agents/skills/github-delivery/SKILL.md" "## 3. Branch、実装、commit" "delivery-stack" "stacked PRでは、親PR・子PRのbaseと依存順を記録"
require_block_text ".agents/skills/github-delivery/SKILL.md" "## 5. CIとreview" "delivery-review" "同一HEADのfull gateは原則1回"
require_block_text ".agents/skills/github-delivery/SKILL.md" "## 5. CIとreview" "delivery-review" "親merge後のbase統合・full gate・latest HEAD reviewをそれぞれ原則1回"
require_block_text ".agents/skills/github-delivery/SKILL.md" "## 5. CIとreview" "delivery-review" "push: 同じHEADを送っただけならlocal test、full gate、review証拠は失効せず"
require_block_text ".agents/skills/github-delivery/SKILL.md" "## 5. CIとreview" "delivery-review" "base変更・base統合: HEAD/base snapshotとbase依存のCI・review・mergeabilityを失効させる"
require_block_text ".agents/skills/github-delivery/SKILL.md" "## 5. CIとreview" "delivery-review" "review thread解決: thread状態だけを更新し"
require_block_text ".agents/skills/github-delivery/SKILL.md" "## 5. CIとreview" "delivery-review" "scripts/verify-ai-governance.sh"
require_block_text ".agents/skills/github-delivery/SKILL.md" "## 5. CIとreview" "delivery-review" "scripts/verify-agent-harness.sh"
require_block_text ".agents/skills/github-delivery/SKILL.md" "## 6. 権限境界と終了" "delivery-exit" "merge直前には、必要な再確認を終えた同一時点の単一snapshotへ"
[[ "$(grep -Fxc -- 'bash scripts/verify-agent-harness.sh' scripts/verify-ai-governance.sh)" -eq 1 ]] || fail "scripts/verify-ai-governance.sh must invoke verify-agent-harness.sh exactly once"
require_block_text ".agents/skills/ui-ux-review/SKILL.md" "## 2. レビュー経路を選ぶ" "uiux-review-routing" "UI変更レビュー: 変更した画面、component、状態、文言、操作を確認する。単一画面の局所変更だけならフロー監査を追加しない。"
require_block_text ".agents/skills/ui-ux-review/SKILL.md" "## 2. レビュー経路を選ぶ" "uiux-review-routing" "フロー監査: 既存画面または複数ステップの体験を監査する依頼、または画面遷移を追わなければタスク達成を評価できない場合に使う。"
require_block_text ".agents/skills/ui-ux-review/SKILL.md" "## 2. レビュー経路を選ぶ" "uiux-review-routing" "併用: UI変更が複数ステップの主要タスクへ影響する場合、取得可能な変更前フローを基準にし、変更レビュー後に同じタスクの変更後フローを監査する。片方の証跡で他方を代用しない。"
require_block_text ".agents/skills/ui-ux-review/SKILL.md" "## 2. レビュー経路を選ぶ" "uiux-review-routing" "GitHubが所有する未変更の操作フローを監査対象へ広げず"
require_block_text ".agents/skills/ui-ux-review/SKILL.md" "## 4. 実行" "uiux-change-scope" "review target、base ref / SHA、head ref / SHA"
require_block_text ".agents/skills/ui-ux-review/SKILL.md" "## 4. 実行" "uiux-change-scope" "diffの追加側と削除側"
require_block_text ".agents/skills/ui-ux-review/SKILL.md" "## 4. 実行" "uiux-change-scope" "shared primitive、global token、common component"
require_block_text ".agents/skills/ui-ux-review/SKILL.md" "## 4. 実行" "uiux-change-scope" "Introduced / Regression / Pre-existing"
require_block_text "docs/ai-governance/03-evidence-and-completion-gates.md" "## 2. 変更scopeの証跡" "uiux-change-scope-evidence" "Target snapshot / ref"
require_block_text "docs/ai-governance/03-evidence-and-completion-gates.md" "## 2. 変更scopeの証跡" "uiux-change-scope-evidence" "Base ref / SHA、Head ref / SHA"
require_block_text "docs/ai-governance/03-evidence-and-completion-gates.md" "## 2. 変更scopeの証跡" "uiux-change-scope-evidence" "Expanded surfaces"
require_block_text "docs/ai-governance/03-evidence-and-completion-gates.md" "## 2. 変更scopeの証跡" "uiux-change-scope-evidence" "Coverage / unknowns"
require_block_text "docs/ai-governance/03-evidence-and-completion-gates.md" "## 5. 変更由来findingの証跡" "uiux-finding-provenance" "分類はbase / head、diff"
require_block_text "docs/ai-governance/03-evidence-and-completion-gates.md" "## 5. 変更由来findingの証跡" "uiux-finding-provenance" "同じroot causeは一件へ統合"
require_block_text "docs/ai-governance/03-evidence-and-completion-gates.md" "## 5. 変更由来findingの証跡" "uiux-finding-provenance" "IntroducedとRegressionは今回の変更のfindingとして"
require_block_text "docs/ai-governance/05-accessibility-and-inclusive-design.md" "## 17. 検証証跡" "uiux-a11y-quality" "複合widgetのentry / 内部移動 / exit、focus表示・移動・復帰"
require_block_text "docs/ai-governance/05-accessibility-and-inclusive-design.md" "## 17. 検証証跡" "uiux-a11y-quality" "foreground / background pairのcontrast測定、dark mode、forced colors"
require_block_text "docs/ai-governance/05-accessibility-and-inclusive-design.md" "## 17. 検証証跡" "uiux-a11y-quality" "200% zoom、320 CSS pxまたは256 CSS px相当"
require_block_text "docs/ai-governance/05-accessibility-and-inclusive-design.md" "## 17. 検証証跡" "uiux-a11y-quality" "reduced motion、notificationの保持時間"
require_block_text "docs/ai-governance/06-visual-hierarchy-and-information-architecture.md" "## 14. 検証証跡" "uiux-visual-quality" "主要componentのcontainer幅、zoom、文字拡大"
require_block_text "docs/ai-governance/06-visual-hierarchy-and-information-architecture.md" "## 14. 検証証跡" "uiux-visual-quality" "font request、読み込み済みfamily / weight、fallback、wrap、truncation"
require_block_text "docs/ai-governance/06-visual-hierarchy-and-information-architecture.md" "## 14. 検証証跡" "uiux-visual-quality" "foreground / background pairのcontrast、dark / light / forced colors"
require_block_text "docs/ai-governance/06-visual-hierarchy-and-information-architecture.md" "## 14. 検証証跡" "uiux-visual-quality" "主要stateとvisual finishのrender"
require_block_text "docs/ai-governance/06-visual-hierarchy-and-information-architecture.md" "## 14. 検証証跡" "uiux-visual-quality" "reduced motion、初回表示"
require_block_text "docs/ai-governance/templates/uiux-review-report.md" "## 1. 概要" "uiux-report-scope" "review route"
require_block_text "docs/ai-governance/templates/uiux-review-report.md" "## 1. 概要" "uiux-report-scope" "Target snapshot / ref"
require_block_text "docs/ai-governance/templates/uiux-review-report.md" "## 11. 指摘一覧" "uiux-report-provenance" "Introduced / Regression"
require_block_text "docs/ai-governance/templates/uiux-review-report.md" "## 11. 指摘一覧" "uiux-report-provenance" "Pre-existingは今回の変更findingと完了判定へ混ぜず"
require_block_text "docs/ai-governance/templates/completion-gate-report.md" "## 変更scope（UI変更レビューで差分がある場合）" "uiux-completion-scope" "Target snapshot / ref"
require_block_text "docs/ai-governance/templates/completion-gate-report.md" "## 変更scope（UI変更レビューで差分がある場合）" "uiux-completion-scope" "Coverage / 未確認consumer / 除外理由"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "同一PR・同一HEAD系列の包括レビューは、配送対象の最終HEADに対する初回レビュー1回と、指摘修正後の再レビュー1回までを原則とする"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "同じ配送系列への包括レビュー実行回数で数え、review comment、thread、指摘の件数では数えない"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "3回目以降の包括レビューは実行しません。次のいずれかで前回証拠が失効した場合だけ、対象risk laneと変更pathを明示した限定再確認を行う"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "未解決のP0またはP1"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "セキュリティ、秘密情報、データ整合性に関わる未解決事項"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "前回レビュー後に新しい変更範囲またはrisk laneが追加された"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "前回のレビュー証拠に具体的な不足または矛盾が見つかった"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "P2以下の指摘だけが残る場合は、影響とnon-blocking判断をPRへ記録し、必要なら別Issueへ分離して同じPRの包括レビュー周回を終了する"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "修正commit、変更path、元の指摘、focused test結果だけを文脈として使う"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "成功済みレビューまたはfull gateを再実行する場合は、対象変更、新規risk lane、実行条件変更、証拠期限切れなど、証拠が失効した具体的な理由を記録する"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "対象HEAD、対象path、確認する具体的な問い"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "既存報告やメインエージェント自身の一次証拠確認では不足する理由"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "委任対象は、他の作業から独立して並列化できるbounded laneだけです"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "CIの待機・監視だけを行う作業"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "同一PRの各laneは、一人のownerが開始からcompletionまで継続して担当します"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "同じworktreeとHEADで長い検証を始める前に、利用可能なprocess stateをoperatorが確認し"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "環境が自動的なlockを保証する仕組みではありません"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "各evidenceは対象HEADとbase HEAD、確認済みpath、diff identifierに束縛します"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "同一HEAD・同一risk laneの独立監査は原則1回"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "包括監査を複数agentへ同時委任せず"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "再監査を認めるのは、対象コードが変わった、新しい実行証拠が得られた、前回監査に明確な不足がある、または未解決の証拠矛盾がある場合"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "修正後に変更pathを対象再検証すること"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "監査結果が矛盾した場合は追加agentの多数決を取りません"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "full-history forkを既定にしません"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "必要なHEAD、path、acceptance、既知の指摘だけを短く渡します"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "primary agentは、要件・適用ルール、完了条件・非対象、lane設計、担当割当、依存関係、進捗、lane間の競合、ガバナンス、成果受入、Issue・commit・PR・CI・review・mergeabilityの確認、配送判断を担います"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "subagentは、コードベース・履歴・仕様の探索、実装、focused verification、コード・セキュリティ・公開安全性review、review fix、docs、配送など、分離できる実務を担当できます"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "subagentを監査専用には限定しません"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "実行環境のモデル、ベンダー、製品固有tool、固有command、config keyを指定せず"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "owner、write ownership、completion、verification、invalidation condition"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "開発中は変更によって影響を受けるfocused test"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "配送対象の最終HEADが確定した時点でfrontend / backend / operationsなど必要なfull gateを原則1回実行する"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "成功済み検証を再実行する時は、対象変更、生成物変更、実行条件変更、証拠期限切れなど、証拠が失効した理由を記録する"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "HEADだけを監査済みsnapshotとして扱いません"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "target HEAD"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "target path"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "completion"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "verification"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "evidence package"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "changed paths"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "| verified snapshot |"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "| invalidation condition |"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "primary agentの受入はevidence packageからscope、acceptance、evidence、unrelated diff、commit responsibility、lane conflict、completion gatesを確認し"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "| evidence package | scope、acceptance、changed paths、conclusion、verification results、unperformed checks、remaining risks、unrelated diff、commit responsibility、lane conflict、completion gates、snapshotまたはdiff identifier |"
require_block_text "docs/ai-governance/13-maintenance-policy.md" "## サブエージェント運用" "subagent-maintenance" "docs/agent-harness.md"
require_block_text "docs/ai-governance/13-maintenance-policy.md" "## サブエージェント運用" "subagent-maintenance" "同一HEADの重複監査"
require_block_text "docs/ai-governance/13-maintenance-policy.md" "## Review収束" "review-maintenance" "docs/agent-harness.md"
require_block_text "docs/ai-governance/13-maintenance-policy.md" "## Review収束" "review-maintenance" "P2以下だけを理由とする包括レビュー反復"
require_text ".agents/skills/github-delivery/SKILL.md" "docs/agent-harness.md"
require_text "docs/agent-principles.md" "重複回数だけで抽象化を強制しない"
require_text "AGENTS.md" "大小を問わずすべてソースコード変更"
require_text "AGENTS.md" "GitHub配送Skillが定義する通常配送"
require_text "AGENTS.md" "GitHub上でCIとコードレビュー対応が完了し、マージ可能な状態"
require_text "AGENTS.md" "観測可能な完了条件"
require_text "AGENTS.md" "独立した責務を未commitのまま蓄積せず"
require_text "AGENTS.md" "GitHub配送Skillを正本"
require_text ".agents/skills/github-delivery/SKILL.md" "大小を問わず必ず発動"
require_text ".agents/skills/github-delivery/SKILL.md" "ソースコード変更は規模や種類にかかわらず主Issueを必須"
require_text ".agents/skills/github-delivery/SKILL.md" "非ドラフトPRを作成または更新"
require_text ".agents/skills/github-delivery/SKILL.md" "GitHubのmergeabilityがclean"
require_text ".agents/skills/github-delivery/SKILL.md" "予定commitの責務"
require_text ".agents/skills/github-delivery/SKILL.md" "次の独立責務を編集する前"
require_text ".agents/skills/github-delivery/SKILL.md" "サブエージェントの完了報告を受けたら"
require_text ".agents/skills/github-delivery/SKILL.md" "作業時間、行数、担当者だけを理由"
require_text ".agents/skills/github-delivery/SKILL.md" "git diff --cached --check"
require_text "docs/agent-harness.md" "ソースコード変更のGitHub配送権限"
require_text "docs/ai-governance/03-evidence-and-completion-gates.md" "自己レビューは補助証跡に限り"
require_text ".github/pull_request_template.md" "push CI"
require_text ".github/pull_request_template.md" "pull_request CI"
require_text ".github/pull_request_template.md" "GitHub mergeability"

# Keep the shared contract and task/adapters model-neutral without rejecting
# legitimate environment names, official URLs, or product-specific docs. The
# verifier itself is excluded because its fixtures and patterns intentionally
# contain the examples being checked.
for file in "${MODEL_NEUTRAL_PATHS[@]}"; do
  reject_model_ids "$file"
  reject_regex "$file" "$RUNTIME_KEY_ASSIGNMENT_PATTERN"
  reject_tool_syntax "$file"
  reject_vendor_mandates "$file"
done

echo "Agent harness verification: PASS"
