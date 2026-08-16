---
name: small-agents
description: Use when the active model is a small or local one (ollama, vLLM, llama.cpp, LM Studio, lets-claude, or a named open-weights model such as Qwen, Llama, Mistral, Phi, Gemma, DeepSeek, GLM, CodeLlama), or when an agent is thrashing - repeating a command that already failed, investigating without a hypothesis, inventing flags or APIs that do not exist, or ending a turn with no verdict.
---

# Small Agents

Small models do not fail randomly. They fail in two specific ways, and each
has its own loop.

**Investigating** — you are trying to find out why something is wrong.
The failure is thrash: many commands, no hypothesis, no conclusion.
→ Use **DIAGNOSE** below. Detail in `diagnosing.md`.

**Changing** — you are trying to make an edit that works.
The failure is drift: stale context, invented APIs, oversized edits.
→ Use **CHANGE** below. Detail in `editing.md`.

If you are running commands to *learn* something, you are investigating.
If you are running commands to *verify* something you wrote, you are changing.

**The one rule under both:** loading a skill is not following it. A model
that reads a protocol and then improvises has not used it. Before each
command, name the step you are on.

---

## DIAGNOSE

Five steps. Do not skip one because the answer feels obvious — the answer
feeling obvious is the most common reason it is wrong.

### 1. REPRODUCE — see it fail with your own eyes

Run the failing thing and watch the actual result. Not a proxy for it, not
its configuration, not its source code.

**Observe the system; do not interrogate it.** To learn what something does,
run it and look. Asking its internals to describe themselves is a much
harder problem than the one you started with, and it is usually impossible.

If the behaviour needs a real terminal, a real browser, or a real user
action, then reproduce it there. A test that cannot reproduce the symptom
proves nothing about the symptom.

### 2. COMPARE — find something that works

Find the nearest case that behaves correctly and list every difference
against the broken one. Not the plausible differences — every one.

This is the highest-yield step and the one most often skipped. "Why does
`foo` complete but `bar` doesn't?" collapses a search space that
open-ended investigation does not.

### 3. NAME — commit to a cause, in writing

Before your next command, write exactly one sentence:

> I think **&lt;cause&gt;** because **&lt;evidence I have already seen&gt;**.

Rules for that sentence:
- The cause is a mechanism, not a location. "The hash table is stale" is a
  cause. "Something is wrong with completion" is not.
- The evidence is something already on your screen. If you cannot point at
  it, you do not have a hypothesis — you have a guess, and you need step 1.
- One sentence. If it needs three, you have three hypotheses; test the
  cheapest one first.

### 4. PREDICT — say what you expect before you look

State what you will see if the hypothesis is true, **then** run one command.

A command with no prediction attached cannot fail, which means it cannot
teach you anything. This is what separates an experiment from a poke.

If the prediction was wrong, the hypothesis was wrong. Return to step 3 and
write a new one. Do not adjust the command and re-run it.

### 5. LAND — never end without a verdict

Every investigation ends in one of exactly two shapes:

**Solved.** The cause is X. The fix is Y. I verified it by Z, and the
symptom is gone.

**Stuck.** I could not determine the cause. I tried A, B, C. I ruled out
D and E, and here is the evidence. The single most useful next step is F.

"I am stuck" is a complete, professional, acceptable answer. Trailing off
is not an answer at all — it costs the user everything you learned.

---

## CHANGE

For edits, the loop is **PLAN → FOCUS → ACT → VERIFY**, and the governing
rule is: never trust your memory of a file, only what is on screen now.

Full protocol, context budgets by model size, and edit-size limits are in
`editing.md`. Read it before a multi-step edit.

---

## Red Flags — stop and restart the loop

| You are about to... | What it actually means |
|---|---|
| Re-run a command with a tweaked flag after it failed | The approach failed, not the flag. Step 2 or a new step 3. |
| Say "let me just try..." | You have no hypothesis. Step 3. |
| Use a flag, option, or API you have not verified exists | Check it first. Inventing one costs more than looking. |
| Read source code to predict runtime behaviour | Run it instead. Step 1. |
| Explain why the error message does not apply to you | It applies. Read it literally. |
| End the turn with no cause and no fix | Step 5. Say you are stuck. |

## Rationalizations

| Excuse | Reality |
|---|---|
| "The error is generic, it doesn't mean anything" | Errors are literal. "Can only be called from X" means exactly that. |
| "One more variation and it'll work" | Two failures of one approach = the approach is wrong. Change it. |
| "I already know what's wrong" | Then write the sentence in step 3. If you cannot, you do not know. |
| "Reproducing it properly is too slow" | Slower than the twelve commands you are about to run? |
| "I'll investigate more and report at the end" | There is no end. Land it now with what you have. |
| "The skill is loaded, I'm following it" | Name the step you are on. If you cannot, you are not. |

---

## The harness

This plugin also enforces two of these rules mechanically, because a model
that will skip a written rule will also skip a written rule about not
skipping rules:

- Running a third variation of an approach that already failed twice is
  **blocked**. To proceed you must put `HYPOTHESIS: <cause and evidence>`
  in the tool call's `description` field — that is step 3, made checkable.
- Ending a turn with no verdict after a failed investigation is
  **blocked**. That is step 5.

Set `SMALL_AGENTS_DISABLE=1` to turn the harness off.

## Companion skills

- `superpowers:systematic-debugging` — the full four-phase method. DIAGNOSE
  is its shape, compressed to survive a small context window.
- `superpowers:verification-before-completion` — before claiming step 5.
- `superpowers:test-driven-development` — when the fix needs a test.
- `superpowers:brainstorming` — when the task is to build, not to diagnose.

`failure-modes.md` catalogues how small models fail, with countermeasures.
`language-tips.md` covers per-language specifics.
