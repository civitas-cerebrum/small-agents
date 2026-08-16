# Migrating from small-model-agent-skill

`small-agents` replaces
[`small-model-agent-skill`](https://github.com/civitas-cerebrum/small-model-agent-skill).

## What carried over

Everything that was working, unchanged in substance:

| Was | Is now |
|---|---|
| `SKILL.md` — the PLAN → FOCUS → ACT → VERIFY protocol | `skills/small-agents/editing.md`, reached from the CHANGE loop |
| `failure-modes.md` — 10 editing failure modes | `skills/small-agents/failure-modes.md`, modes 1–10 |
| `language-tips.md` | `skills/small-agents/language-tips.md`, verbatim |

## What is new

- **A diagnostic loop.** The predecessor covered *editing* discipline only —
  context drift, phantom APIs, edit sizing. It had nothing for
  *investigation*, which is where small models lose whole sessions. See
  `skills/small-agents/diagnosing.md`.
- **Six investigation failure modes** (11–16): interrogation loop,
  investigation without a hypothesis, evidence blindness, phantom flags,
  approach thrash, silent abandonment.
- **The harness.** Hooks that block approach thrash and silent abandonment,
  rather than advising against them.
- **Plugin packaging.** Installable via the plugin marketplace instead of
  copy-pasting a skill file.

## Two problems this fixes

**The trigger never fired.** The predecessor's README stated that
`lets-claude` "injects `running claude code with a small model` as the first
message, which activates the skill." It does not — the script ends at
`exec claude --model "$MODEL"` with no message injection and no
`--append-system-prompt`. The skill's elaborate trigger phrase had no
mechanism behind it. Hooks load with the plugin and need no trigger phrase.

**Advice was the wrong instrument.** The skill's guidance was sound and was
still skipped by the model it was written for. The two rules that matter most
are now enforced, not suggested.

## What was dropped

`TESTING.md`, `evals.json`, and `run-tests.js` tested whether the skill's
*description* triggered on various phrasings. With hooks that load
unconditionally, trigger-phrase matching is no longer load-bearing, so those
were dropped in favour of `tests/test_hooks.py`, which tests the enforcement
itself against a real recorded failure.

## Migration steps

1. Install the plugin (see README).
2. Remove any copy of the old `SKILL.md` from your system prompt or
   `~/.claude/skills/`; keeping both means two competing protocols.
3. Nothing else — configuration is by environment variable, and the defaults
   are the intended settings.
