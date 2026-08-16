# Editing

Detail for the CHANGE loop in `SKILL.md`. Read this before any multi-step
edit. The governing rule: **never trust your memory of a file — trust only
what is on screen right now.**

## The Protocol: PLAN → FOCUS → ACT → VERIFY

Every task follows this loop. No exceptions.

### 1. PLAN — Decompose Before Touching Anything

Before editing a single file, produce a written plan. The plan is a numbered checklist of atomic steps. Each step must satisfy ALL of these constraints:

- Touches at most **2 files** (1 is better)
- Can be described in **1–2 sentences**
- Has a **concrete verification** (a test to run, an output to check, a grep to confirm)
- Does NOT depend on remembering content from a previous step — any needed context is re-read

**Planning template** (emit this at the start of every task):

```
## Task Plan
Goal: [one sentence]
Files involved: [list — if >5, split into sub-tasks first]

Steps:
1. [ ] Read [file] to understand [specific thing]
2. [ ] Edit [file]: [specific change, <20 lines]
   Verify: [how to confirm it worked]
3. [ ] Read [other file] to check [dependency]
4. [ ] Edit [other file]: [specific change]
   Verify: [how to confirm]
5. [ ] Run [test/build command]
   Expect: [specific passing output]
```

If the plan has more than **8 steps**, split it into **sub-tasks** and complete each sub-task fully (including verification) before starting the next.

### 2. FOCUS — Load Only What You Need Right Now

Context is precious. Treat it like a scarce resource.

**File reading rules:**
- Read only the section of a file you need, not the whole file. Use line ranges (e.g., `view file.py lines 40-80`) or grep first to find the right section.
- Never have more than **2 files' content** in your working context at once. If you need a third, summarize what you learned from one of the first two into a 2–3 line note, then drop it.
- Before editing, always re-read the target section. Don't rely on content you read more than ~1500 tokens ago.
- If a file is longer than **150 lines**, never read it all at once. Read the structure first (first 30 lines + grep for functions/classes), then zoom into the section you need.

**Context budget by model size:**

| Context window | Max lines per read | Max edit size | Max files in context | Compaction frequency |
|----------------|-------------------|---------------|---------------------|---------------------|
| 4K tokens      | 30 lines          | 10 lines      | 1                   | Every 2–3 turns     |
| 8K tokens      | 60 lines          | 20 lines      | 1–2                 | Every 4–5 turns     |
| 16K tokens     | 100 lines         | 30 lines      | 2                   | Every 6–8 turns     |
| 32K tokens     | 150 lines         | 50 lines      | 2–3                 | Every 10 turns      |

Within each step, budget roughly:
- ~30% for reading/understanding the current state
- ~50% for the edit or generation
- ~20% for verification output

### 3. ACT — Make Small, Surgical Edits

**Edit size rules:**
- Each edit should change **fewer than 30 lines**. If your change is bigger, split it into sequential edits with a verification between each.
- Prefer `str_replace` style edits (find exact text → replace) over rewriting entire files. This avoids the model needing to regenerate unchanged content (which is where hallucination happens).
- When creating a new file, write it in sections: skeleton first, then fill in one function at a time, verifying each.
- Never generate boilerplate from memory. If you need an import list, a config structure, or a template — read an existing example first, then adapt it.

**Anti-hallucination rules:**
- Never reference a function, class, variable, or API you haven't explicitly seen in the current context. If you think it exists, grep for it first.
- Never assume a file's structure. Read it.
- If you're unsure about syntax (e.g., a library API), say so and check the docs or an existing usage in the codebase rather than guessing.

### 4. VERIFY — Confirm Every Step Before Moving On

Every step in the plan must end with a verification. Acceptable verifications:

- **Run the test suite** (or a specific test) and confirm the expected result
- **Run the code** and confirm the output
- **Grep** for the expected change in the file
- **Read back** the edited section to confirm it looks right
- **Type-check or lint** the file

If a verification fails:
1. Re-read the relevant file section (don't trust your memory of what you wrote)
2. Identify the specific error
3. Fix it with a single targeted edit
4. Re-verify

If verification fails **3 times on the same step**, the step is too big. Break it down:
1. Split the failing step into 2–3 smaller sub-steps, each with its own verification
2. Re-read all relevant files fresh (discard your mental model — it's probably wrong)
3. Attempt the first sub-step
4. If the sub-steps also fail, ask the user for help. Don't spiral.

---

## Working Memory Notebook

Since small models forget, maintain an explicit scratchpad. At the start of the task and after each major step, update a brief state note:

```
## Current State
- Working on: Step 3 of 6 — adding validation to UserForm
- Last verified: Step 2 passed (unit test for parseInput runs green)
- Key facts: 
  - UserForm is in src/components/UserForm.tsx (lines 45-120)
  - Validation schema uses zod, defined in src/schemas.ts
  - The existing pattern for validation is in LoginForm.tsx:30-55
```

This note is for the model itself — it replaces the memory that a larger model would have naturally.

---

## Task Size Boundaries

Use these heuristics to decide if a task is appropriate for a single pass:

| Task size | Files | Lines changed | Approach |
|-----------|-------|---------------|----------|
| Tiny | 1 | <15 | Direct edit + verify |
| Small | 1–2 | 15–50 | Plan → 2–4 steps |
| Medium | 2–4 | 50–200 | Plan → sub-tasks of 3–5 steps each |
| Large | 5–6 | 200–400 | Decompose into multiple independent medium tasks |
| Too large | 7+ | 400+ | Refuse or ask user to scope down |

For **large** tasks, complete and verify each sub-task fully before starting the next. The sub-tasks should be designed so that each one leaves the codebase in a working state.

---

## Language and Framework-Specific Guidance

Read `language-tips.md` for tips on handling specific languages and frameworks with small models. Key principles:

- For **typed languages** (TypeScript, Rust, Go), lean hard on the compiler. Run type-checking after every edit — it catches errors the model can't reason about.
- For **Python**, run the specific test or a quick smoke test after every edit. Without a type-checker, runtime is your safety net.
- For **React/frontend**, make one component change at a time. Never edit both a component and its parent's usage in the same step.
- For **SQL/database**, always test queries against the actual DB or a test fixture — never trust a model-generated query without running it.

---

## Prompt Patterns for Small Models

When the user is constructing prompts for a small model agent, recommend these patterns:

**Structured output forcing**: Ask for output in a specific format (JSON, XML, numbered steps) to reduce rambling and keep the model on track.

**One-shot examples**: Include one example of the expected input→output transformation. Small models benefit enormously from a concrete example, much more than from abstract instructions.

**Negative examples**: Explicitly state what NOT to do. "Do NOT edit any file other than utils.py" is more effective with small models than "Focus on utils.py."

**Checkpoint prompts**: After each step, re-inject the current state as a new prompt rather than relying on conversation history. This is the single most impactful pattern for small models.

---

## Usage Modes

This skill operates in two distinct modes depending on who is running it:

**Mode 1 — Large model orchestrating a small model** (e.g., Claude Code reading this skill to generate prompts or instructions that a small model will execute): Focus on the Prompt Patterns section. Your job is to structure tasks so the small model receives one clear, bounded instruction at a time, with an example and explicit constraints. Re-inject the current state as a fresh prompt between steps rather than relying on the small model's conversation history.

**Mode 2 — Small model running this skill itself** (e.g., Qwen or Mistral is the active agent in Claude Code): The model reading these instructions IS the model with limited context. In this case: keep the working memory notebook brief (3–5 lines max), skip re-reading sections of this skill after the initial load (those tokens are gone), and be aggressive about context compaction. Prioritize the PLAN → FOCUS → ACT → VERIFY loop over everything else — that loop is the minimum viable protocol for staying coherent.

When in doubt about which mode applies: if the model can hold this entire skill in context alongside the codebase, it's Mode 1. If the skill itself is crowding out the code, it's Mode 2.

---

## Integration Notes

This protocol works with any agentic coding framework: Claude Code, aider, continue.dev, open-interpreter, cursor agent, etc. The key integration points:

- If the framework supports **tool result truncation**, enable it — small models shouldn't see 500-line file reads.
- If the framework supports **system prompt injection**, include the Planning Template and Working Memory Notebook format in the system prompt.
- If using **ollama** or **llama.cpp**, set `num_ctx` to the model's full capacity and set `num_predict` based on the operation: ~1024 for edits and targeted changes, ~2048 for generating new file sections. Higher values risk runaway generation; lower values risk truncation mid-function.
- If the framework supports **conversation compaction**, enable it aggressively — every ~5 turns is a good cadence for 8K context models.
