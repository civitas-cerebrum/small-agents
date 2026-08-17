# Dispatching

Detail for the DISPATCH pattern in `SKILL.md`. Read this when an
investigation or edit sequence is longer than a few steps.

## Why dispatch

A small model's context is its scarcest resource, and an investigation is
context-hostile: every dead end, every 200-line tool output, every wrong
turn stays in the window and degrades every later decision. By command 30
the model is reasoning through a fog of its own history.

Subagents invert this. Each step runs in a **fresh context** containing
only what that step needs. The orchestrator never sees raw output — only
verdicts — and a subagent never sees the orchestrator's accumulated noise.

## The orchestrator contract

The main session becomes an orchestrator. It holds exactly three things:

1. **The task** — one sentence.
2. **The notebook** — hypotheses tested, verdicts returned, facts learned.
   Keep it under ~15 lines; prune superseded entries.
3. **The next dispatch** — the single step currently out.

Everything else belongs inside a subagent.

## Crafting a dispatch brief

A dispatch is one DIAGNOSE step, never the whole problem. The brief has
four parts, all mandatory:

```
GOAL:     one sentence, one step (reproduce X / compare X to Y /
          test hypothesis Z)
CONTEXT:  only the facts this step needs, from the notebook --
          never "see above", never the full history
COMMANDS: the exact command(s) to run, or the exact experiment shape
RETURN:   the shape of the answer you want back -- a verdict, a diff,
          a yes/no plus evidence. Cap it: "return at most 10 lines".
```

Rules:

- **One step per dispatch.** "Reproduce the failure" is a dispatch.
  "Reproduce and diagnose and fix" is three.
- **The subagent inherits nothing.** If the brief doesn't contain a fact,
  the subagent doesn't know it. This is a feature: write the brief from
  the notebook, and gaps in the brief expose gaps in your understanding.
- **Demand verdicts, not transcripts.** The RETURN cap is what keeps the
  orchestrator's context clean. A subagent that would return 200 lines of
  raw output has been given a bad RETURN spec.
- **Prediction goes in the brief.** "If the hypothesis is right you will
  see X; report whether you saw X" — this keeps step 4 of DIAGNOSE intact
  across the context boundary.

## Example

Notebook says: works-when-run / fails-to-complete; suspect stale hash.

```
Dispatch 1
GOAL:    reproduce the completion failure in a real terminal
CONTEXT: command `zzz-deploy` is at tools/zzz-deploy; shell starts with
         ZDOTDIR=$PWD/zdot zsh -i
COMMANDS: drive an interactive zsh through a pty (python pty), type
         "zzz-dep", press TAB, capture the buffer
RETURN:  "completed" or "not completed", plus the raw buffer line only

Dispatch 2 (after verdict "not completed")
GOAL:    test hypothesis: completion reads a hash table built at startup
CONTEXT: reproduction works as in dispatch 1
COMMANDS: same pty; run `rehash` inside the shell, then retry TAB
RETURN:  "completes after rehash" yes/no
```

Each dispatch is ~8 lines. The orchestrator's whole visible history for a
5-step investigation stays under a page.

## When NOT to dispatch

- The task is under ~5 commands total — dispatch overhead exceeds the win.
- The step needs the full interactive state of the session (rare; most
  state can be re-established from the brief).
- No subagent mechanism is available — then fall back to the working-memory
  notebook discipline in `editing.md`, which is this pattern without the
  hard context boundary.
