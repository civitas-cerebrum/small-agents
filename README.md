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

**The harness** (`hooks/`) — delivery, coaching, and two blocks:

| Trigger | Hook | Effect |
|---|---|---|
| Session starts | `SessionStart` | The protocol core is injected as context — delivery does not depend on the model choosing to load a skill. |
| Output shows a method-error ("can only be called from…"), or a 3rd similar command regardless of exit status | `PostToolUse` | A short coaching note is injected (`additionalContext`) — non-blocking, no failure classification needed. |
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
44 passed, 0 failed
```

## A/B tested against a live local model

The plugin was validated with a controlled A/B experiment: a self-hosted
**Qwen3.8-27B** (vLLM, via `lets-claude`) given a hard diagnostic task — a
faithful reproduction of the real failure this repo was built from (a zsh
command that runs but won't tab-complete; the tempting interrogation
approach is impossible and errors identically every time). Control arm: no
plugin. Treatment arm: this plugin. Every run graded functionally by a pty
replay (does TAB now complete?), plus transcript metrics. 25-minute cap
per run.

**Primary result** (versions with guaranteed protocol delivery, n=14/arm):

| Metric | Control | Harness | p (exact) |
|---|---|---|---|
| Solved (fix works in pty replay) | 3/14 | **10/14** | **0.021** (Fisher) |
| Commands until working fix (median) | never | 22 | **0.011** (Mann-Whitney) |
| Bash commands per run (median) | 24 | 18 | 0.097 |

Sensitivity analysis over every rep ever run (n=18/arm): solved p=0.007,
commands p=0.007, time-to-fix p=0.0008 — same direction, stronger.

Caveats, stated plainly: one task family, one model, sequential batches in
which the treatment was repaired between rounds (the control arm was
byte-identical throughout; grading was automated and identical for both
arms). In one treatment run the full loop fired end-to-end organically:
thrash → **blocked** → model wrote a genuine `HYPOTHESIS:` → recovered →
solved the task.

## What live testing changed

The harness has been run end-to-end against a self-hosted
**Qwen3.8-27B** via `lets-claude`, not just against fixtures. Live testing
confirmed the full loop — a blocked command, the block message delivered to
the model, and the model unblocking itself by writing a real `HYPOTHESIS:`
into the tool description — and it found three defects that the fixture
suite had missed:

| Defect | Why fixtures missed it |
|---|---|
| The tokenizer kept `/` and `.` inside tokens, so a whole path collapsed into one atom and ordinary commands (`python3 host.py`) fell under the minimum token count. **The harness was inert for exactly the commands agents run most.** | Every fixture was a long compound command with many tokens. |
| Re-running a command after *fixing* the code counted as thrash. | No fixture edited a file mid-session. An `Edit`/`Write` now resets the approach clock. |
| The block message could claim an approach "has already failed 0 times". The model spotted the contradiction and dismissed the harness as misconfigured. | Fixtures only exercised the path where failures had actually occurred. |

Each is covered by a regression test. The third is the instructive one: a
self-contradictory enforcement message does not merely fail to help — it
teaches the model to ignore the harness.

Worth noting honestly: on two ordinary seeded diagnostic bugs the 27B model
solved both cleanly, in 3 and 5 commands, with correct root causes — and the
harness stayed silent, as it should. **Thrash is a failure mode of hard
problems, not of every problem**, and the guard produced no false positives
on competent work.

## Repo layout

| Path | What |
|---|---|
| `skills/small-agents/SKILL.md` | The protocol — both loops, red flags, rationalization table |
| `skills/small-agents/diagnosing.md` | DIAGNOSE in depth: observe vs. interrogate, hypothesis quality, worked contrast |
| `skills/small-agents/editing.md` | CHANGE in depth: context budgets, edit sizing, working-memory notebook |
| `skills/small-agents/dispatching.md` | DISPATCH: run long investigations as an orchestrator — one subagent per step, crafted four-part briefs, fresh context each step |
| `skills/small-agents/failure-modes.md` | 16 failure modes with countermeasures (1–10 editing, 11–16 investigation) |
| `skills/small-agents/language-tips.md` | Per-language guidance |
| `hooks/` | The harness: `inject.py`, `coach.py`, `guard.py`, `land.py`, shared `sa_state.py` (`record.py` kept for reference) |
| `tests/test_hooks.py` | Replay suite |

## License

MIT
