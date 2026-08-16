# small-agents

Keeps small and local models on target.

A Claude Code plugin: a protocol the model reads, plus **hooks that enforce
the two rules it will otherwise skip**. Supersedes
[`small-model-agent-skill`](https://github.com/civitas-cerebrum/small-model-agent-skill).

## Why hooks

The predecessor to this repo was a skill — good advice, correctly written,
and inert. Advice only works on a model that follows advice.

The case this plugin was built from: a 32B local model was asked why a
script ran but would not tab-complete. It loaded a debugging skill. It then
spent six commands trying to call a shell's completion internals by hand —
an approach the shell rejected with *"can only be called from completion
function"* **four separate times** — invented a shell option that does not
exist, never wrote down a hypothesis, and ended its turn with no diagnosis
at all. The decisive evidence was on screen at its second command and was
never read.

None of that was a knowledge problem. The model had the right skill loaded
and did not follow it. So this repo enforces the two rules mechanically.

## What it does

**The protocol** (`skills/small-agents/`) — two loops:

- **DIAGNOSE** — REPRODUCE → COMPARE → NAME → PREDICT → LAND, for finding
  out why something is broken.
- **CHANGE** — PLAN → FOCUS → ACT → VERIFY, for making an edit that works
  (carried forward from the predecessor skill).

**The harness** (`hooks/`) — two blocks:

| Trigger | Hook | Effect |
|---|---|---|
| A third run of an approach that already failed twice | `PreToolUse` | Blocked. To proceed, the model must write `HYPOTHESIS: <cause and evidence>` in the tool call's `description`. |
| Ending a turn with no verdict after a failed investigation | `Stop` | Blocked. The model must state a root cause or say plainly that it is stuck. |

The hypothesis gate is the design centre: it forces the one step small
models skip — committing to a cause in writing — and unlike prose in a chat
message, a hook can actually check it.

Commands are matched by token-set similarity, not string equality, so
reformulations (different quoting, an added flag, a reordered pipeline) still
count as the same approach.

## Install

```bash
/plugin marketplace add civitas-cerebrum/small-agents
/plugin install small-agents@civitas-cerebrum
```

Requires `python3` (stdlib only — no dependencies).

With [`lets-claude`](https://github.com/Umutayb/lets-claude), install once and
it applies to every local-model session.

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `SMALL_AGENTS_DISABLE` | unset | `1` turns the harness off entirely |
| `SMALL_AGENTS_FAIL_LIMIT` | `2` | Failures of one approach before the next is blocked |
| `SMALL_AGENTS_THRESHOLD` | `0.55` | Token-overlap ratio at which two commands count as the same approach |

Every hook fails open: a malformed payload, a missing state file, or a bug in
the harness exits 0 and lets the session proceed. The harness can annoy you;
it cannot wedge you.

## Tests

```bash
python3 tests/test_hooks.py
```

The main fixture is not synthetic — it replays the nine Bash commands from the
real failed session described above. The suite asserts the guard fires on the
third attempt at the impossible approach and stays silent through all four
legitimate commands.

```
25 passed, 0 failed
```

## Repo layout

| Path | What |
|---|---|
| `skills/small-agents/SKILL.md` | The protocol — both loops, red flags, rationalization table |
| `skills/small-agents/diagnosing.md` | DIAGNOSE in depth: observe vs. interrogate, hypothesis quality, worked contrast |
| `skills/small-agents/editing.md` | CHANGE in depth: context budgets, edit sizing, working-memory notebook |
| `skills/small-agents/failure-modes.md` | 16 failure modes with countermeasures (1–10 editing, 11–16 investigation) |
| `skills/small-agents/language-tips.md` | Per-language guidance |
| `hooks/` | The harness: `guard.py`, `record.py`, `land.py`, shared `sa_state.py` |
| `tests/test_hooks.py` | Replay suite |

## License

MIT
