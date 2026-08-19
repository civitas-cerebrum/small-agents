# Failure Modes of Small Model Agents

A detailed catalogue of how models ≤30B parameters fail during agentic coding, with specific countermeasures.

Modes 1–10 are **editing** failures (see `editing.md`). Modes 11–16 are
**investigation** failures (see `diagnosing.md`) — these are the ones that
burn a whole session without producing anything.

---

## 1. Context Drift

**What happens:** The model reads file A, then reads file B, then tries to edit file A based on stale or partially-remembered content. The edit is wrong because the model is working from a hallucinated version of file A.

**Frequency:** Very high. This is the #1 failure mode.

**Countermeasures:**
- Always re-read the exact lines being edited immediately before the edit. Not 3 tool calls ago — immediately before.
- Use `str_replace` with the exact existing text, never "rewrite the function that does X" from memory.
- If you need information from two files simultaneously (e.g., a function signature from one file to use in another), extract the key fact into a short note in the working memory notebook, then work from that note.

**Example of failure:**
```
1. Read src/api.ts (200 lines) 
2. Read src/types.ts (100 lines)
3. Edit src/api.ts — WRONG: model remembers api.ts incorrectly
```

**Correct approach:**
```
1. Read src/types.ts:15-25 (just the type definition needed)
2. Note: "UserInput type has fields: name (string), email (string), age (number?)"
3. Read src/api.ts:40-60 (just the function to edit)
4. Edit src/api.ts:45-50 using the noted type info
5. Re-read src/api.ts:40-60 to verify
```

---

## 2. Phantom APIs (Hallucinated Interfaces)

**What happens:** The model generates code that calls functions, methods, or uses APIs that don't exist. It is confidently wrong — the function name sounds plausible but isn't real.

**Frequency:** High, especially with less popular libraries or project-specific utilities.

**Countermeasures:**
- Before writing a function call, `grep -r "function_name"` in the codebase.
- Before writing an import, check that the module exports what you think it does.
- For external library APIs, find an existing usage in the codebase and copy its pattern rather than generating from memory.
- If no existing usage exists, read the library's actual type definitions or docs.

**Example of failure:**
```python
# Model generates:
from utils import validate_email  # This function doesn't exist in utils.py
```

**Correct approach:**
```
1. grep -r "validate" src/utils.py
2. Discover the actual function is called "check_email_format"
3. Use the real function name
```

---

## 3. Scope Creep / Cascade Edits

**What happens:** The model starts a small edit, notices something related, and starts "fixing" that too, then notices another thing, and spirals into a multi-file refactor that breaks coherence.

**Frequency:** Medium-high. Triggered especially by tasks like "fix this bug" where the model finds adjacent issues.

**Countermeasures:**
- The plan is sacred. If a step says "edit line 45 of api.ts," only edit line 45 of api.ts.
- If you notice something else that needs fixing, add it to the plan as a new step — don't do it now.
- After completing the planned edit, run the verification before doing anything else.
- If the model starts a response with "while I'm here, I'll also..." — that's the danger signal.

---

## 4. Partial Generation / Truncated Output

**What happens:** The model runs out of output tokens partway through generating a file or function. The result is syntactically broken (unclosed braces, missing return statements, incomplete logic).

**Frequency:** Medium. More likely with larger files and smaller `max_tokens` settings.

**Countermeasures:**
- Never generate a new file longer than ~80 lines in one shot. Build incrementally:
  1. Write the skeleton (imports, class/function signatures, empty bodies)
  2. Fill in one function body at a time
  3. Verify after each addition
- For edits, use `str_replace` to change only the affected lines rather than regenerating the entire function.
- Set `max_tokens` / `num_predict` appropriately: 1024 for edits, 2048 for new file sections.

---

## 5. Echo Errors (Error Propagation)

**What happens:** The model makes a mistake in step 2. In step 4, it reads back its own mistake, accepts it as correct, and builds on it. The error compounds.

**Frequency:** Medium. Insidious because it looks like the model is working correctly.

**Countermeasures:**
- Verify after every step, not just at the end. Catch mistakes before they become the model's "ground truth."
- When verification fails, re-read the file from disk (the actual file), not from the conversation context.
- Consider running a linter or type-checker as an automated verification — it doesn't suffer from echo errors.

---

## 6. Import/Dependency Confusion

**What happens:** The model writes imports that are wrong — importing from the wrong path, using named imports that don't exist, or mixing up similar packages (e.g., `lodash` vs `lodash/fp`, `path` vs `node:path`).

**Frequency:** Medium. Higher in JavaScript/TypeScript where import styles vary.

**Countermeasures:**
- Before writing imports, check how the target module is imported elsewhere in the project: `grep -r "from.*module_name" src/`
- For project-internal imports, verify the export exists: `grep "export" src/target-file.ts | head -20`
- Copy the exact import style used in neighboring files.

---

## 7. Stale Test Expectations

**What happens:** The model edits code but forgets to update the corresponding test expectations, or updates tests based on what it thinks the code does rather than what it actually does.

**Frequency:** Medium.

**Countermeasures:**
- If the plan involves editing code, include a step to check and update tests.
- After editing code, run the tests before modifying them — the test failure message tells you exactly what changed.
- Never update a test expectation without first running the test to see the actual output.

---

## 8. Multi-Step Logic Errors

**What happens:** The model can implement each step of an algorithm individually, but when the steps need to interact (shared state, sequencing, error handling), the composition is wrong.

**Frequency:** Medium. Higher for async code, state machines, and complex control flow.

**Countermeasures:**
- Break complex logic into named, testable functions rather than inline code.
- Write the simplest possible version first (even if it's inefficient), verify it works, then optimize.
- For async code: get the synchronous version working first, then add async.
- Write a simple test case before writing the implementation. Seeing the test helps the model stay focused on the contract.

---

## 9. Off-by-One / Boundary Errors

**What happens:** Small models are weak at reasoning about boundaries — array indices, string slicing, range endpoints, pagination offsets.

**Frequency:** Medium.

**Countermeasures:**
- When writing boundary logic, add a concrete example as a comment: `// For input [a, b, c], start=1, end=2 → should return [b]`
- Immediately test with edge cases: empty input, single element, full range.
- Prefer high-level operations (`.slice()`, `.filter()`, list comprehensions) over manual index arithmetic.

---

## 10. Inconsistent Naming

**What happens:** The model uses `userId` in one place and `user_id` in another, or `getData` in the interface and `fetchData` in the implementation.

**Frequency:** Low-medium. Higher across file boundaries.

**Countermeasures:**
- Before introducing a new name, grep for existing conventions: `grep -r "user.*[Ii]d" src/`
- When editing a file, check its naming style in the first 20 lines and match it.
- In the working memory notebook, note the naming convention: "This project uses camelCase for variables, PascalCase for types."

---

# Investigation Failure Modes

## 11. Interrogation Loop

**What happens:** The model tries to learn what a system does by calling its
internals directly, instead of running the system and watching. The internals
require a runtime context the model does not have, so every attempt returns an
error *about the method* rather than a result about the bug. The model reads
each error as an obstacle to route around and tries again.

**Frequency:** Very high during debugging. This is the #1 investigation failure.

**The tell:** errors of the form "can only be called from...", "no active
context", "must be run inside...", "not available outside of...".

**Countermeasures:**
- Treat that class of error as a stop sign, not a speed bump. It means there is
  no path this way, not that you need one more setup line.
- Ask: "what would I look at if I could not inspect the internals at all?"
  That is almost always the right experiment.
- If the behaviour needs a real terminal or browser, drive a real one
  (pty, `script -q`, a browser session) rather than simulating it.

---

## 12. Investigation Without a Hypothesis

**What happens:** The model runs command after command, each individually
reasonable, with no statement of what it thinks is wrong. Evidence accumulates
and is never interpreted. Frequently the answer is already on screen.

**Frequency:** Very high. Often co-occurs with #11.

**The tell:** you cannot answer "what do you currently think is wrong?" in one
sentence.

**Countermeasures:**
- After the third command, stop and write: "I think X because Y."
- If you cannot name a mechanism, re-read the output you already have before
  gathering more. Small models under-read evidence and over-collect it.
- Attach a prediction to every command. A command with no prediction cannot
  fail, so it cannot inform.

---

## 13. Evidence Blindness

**What happens:** The model runs the command that reveals the root cause,
prints it, and moves on without registering it. The decisive line scrolls past
inside a larger output block.

**Frequency:** High, especially with multi-part `echo === X ===` commands whose
output is long.

**Countermeasures:**
- After each command, state in one line what its output *established* — not
  what it printed.
- Prefer several small commands over one compound command with many sections;
  compound output is where findings go to die.
- When a command answers a yes/no question, say the answer out loud.

---

## 14. Phantom Flags and Options

**What happens:** The model invents a command-line flag, shell option, or
config key that sounds right but does not exist (`setopt functions_autoload`,
`--recursive` on a command that has no such flag).

**Frequency:** High. The editing equivalent is #2 (Phantom APIs).

**Countermeasures:**
- Before using a flag you have not seen in this session, check `--help`,
  `man`, or the docs. One lookup is cheaper than one failed command.
- Error text like "no such option" / "unrecognized argument" means the thing
  does not exist. Do not retry it with different spelling.

---

## 15. Approach Thrash

**What happens:** An approach fails, and the model retries it with cosmetic
changes — different quoting, an extra setup line, a reordered pipeline —
believing the parameters are wrong when the approach is wrong. Three or four
near-identical attempts in a row.

**Frequency:** Very high. This is the mode the harness blocks mechanically.

**Countermeasures:**
- Two failures of one approach means: change the approach, not the command.
- Ask what *class* of thing failed. If the class is "this cannot work from
  here", no variation inside the class will work.
- The harness blocks the third attempt and requires a written hypothesis.
  Treat that block as information, not as an obstacle.

---

## 16. Silent Abandonment

**What happens:** After a long unsuccessful investigation the model ends its
turn with nothing — no cause, no fix, no admission of being stuck. Sometimes a
single content-free line. The user is left worse off than before, because the
transcript looks like work was done.

**Frequency:** Medium, but the most costly single mode — it discards
everything the session learned.

**Countermeasures:**
- Every investigation ends in one of two shapes: solved, or stuck. Both are
  acceptable outputs. Silence is not.
- A stuck report is a handoff: what you tried, what you ruled out and on what
  evidence, and the best next step.
- The harness blocks a turn that ends this way.

---

# Dispatch Failure Modes

## 17. Brief Scope Capping

**What happens:** The orchestrator writes a dispatch brief that consolidates
multiple plan tasks into one, with a narrow scope. "Write tests for the form"
or "Keep it to these ~6 tests." The subagent implements exactly what the brief
says — no more, no less — producing minimal output. On the same task, an
unrestricted session (or one that writes tests in-context) produces 2–3×
more tests because it expands the scope spontaneously.

**Frequency:** High in strict-dispatch mode. Confirmed by forensic comparison:
an orchestrator's brief saying "Keep it to these ~6 tests" produced 6 tests;
the same model writing tests in-context produced 11.

**Countermeasures:**
- Specify **per-behavior** coverage in the brief, not per-area. "One test per
  field, plus edge cases for each complex interaction" is actionable; "write
  tests for the form" is not.
- List every test or behavior you expect in the brief. The subagent will not
  add its own.
- In the plan itself, specify granularity: "field-level tests — one per field"
  rather than "field-level tests."

---

## 18. Unbounded Dispatch

**What happens:** A dispatched subagent runs indefinitely because nothing in
the brief says when to stop. Advisory wrap-up nudges are ignored (proven by a
73-minute dispatch that ran through two nudges). The orchestrator waits
correctly, and the external cap kills everything.

**Frequency:** High without deadlines. The overnight 90-minute run produced
fewer tasks than shorter runs because one dispatch consumed the entire budget.

**Countermeasures:**
- Include a time budget in every brief: "Aim for ≤10 minutes."
- The harness enforces this in PLAN=2 (dispatches without a time budget
  reference are blocked).
- Hard dispatch deadlines (20 min) block all tool use past the window.
  Advisory nudges at 10/15 minutes prompt wrapping up.
- The mere existence of a deadline changes behavior: the same inspection
  that ran 73 minutes unbounded returned in 17 with a deadline.
