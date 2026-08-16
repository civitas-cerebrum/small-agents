# Diagnosing

Detail for the DIAGNOSE loop in `SKILL.md`. Read this when an investigation
is not converging.

---

## The core distinction: observe vs. interrogate

Almost every stalled investigation is a model interrogating a system when it
should be observing one.

| Interrogating (hard, often impossible) | Observing (easy, always available) |
|---|---|
| Calling a framework's internal functions by hand to see what they return | Running the app and looking at the output |
| Reading a shell's completion functions to predict completion | Pressing Tab in a real terminal |
| Reasoning about what a regex will match | Running it against the input |
| Inspecting a build tool's config resolution logic | Printing the resolved config |
| Tracing how a test runner sets up context | Adding one print statement and running the test |

Interrogation looks rigorous. It is usually a much harder problem than the
original one, because internals assume a runtime context you do not have.

**The tell:** you are getting errors *about your method* ("can only be called
from...", "no active context", "must be run inside...") rather than results
about the bug. Those errors are not obstacles on the path. They are the
system telling you there is no path this way.

### Reproducing what is hard to reproduce

"I can't observe it directly" is usually false. Common escapes:

| Barrier | Escape |
|---|---|
| Needs an interactive terminal (TTY/line editor) | Drive it through a pty (`script -q`, Python `pty.fork()`, `expect`) |
| Needs a browser | Drive a real browser, or check the console and network traffic |
| Needs a specific timing/race | Add logging at both sides of the boundary and run it repeatedly |
| Needs another machine's state | Reproduce the state locally, or gather evidence at each layer |
| Only fails in CI | Print the environment on both sides and diff it |

If reproduction is genuinely impossible, say so in step 5 and state what you
would need. Do not substitute speculation for observation and keep going.

---

## Step 2 in practice: the difference list

Pick the nearest working case. Then enumerate differences *mechanically*,
not by intuition:

```
broken:  lets-claude    installed today 14:27   symlink   ~/.local/bin
working: git            installed months ago    binary    /usr/bin
                        ^^^^^^^^^^^^^^^^^^^^^
```

Do not filter the list while building it. "That can't matter" is a
prediction, and predictions belong in step 4 where they get tested. In the
example above, the timing column is the one that looks irrelevant and is
in fact the entire answer.

Useful comparison axes: when it was created, who owns it, how it was
installed, what type it is, which layer it lives in, whether the process
started before or after it existed.

---

## Step 3 in practice: hypothesis quality

| Bad | Why | Better |
|---|---|---|
| "Something is wrong with the completion system" | Names a location, not a mechanism | "Completion reads a hash table that was built before the file existed" |
| "The config is broken" | Not falsifiable | "The config loads, but the value is overwritten later by the CLI default" |
| "It's a permissions issue" | No evidence cited | "The process runs as `nobody`, and the file is mode 600 owned by root" |
| "Maybe the cache is stale" | "Maybe" is not a commitment | "The cache is stale; it was written at 14:20 and the source changed at 14:27" |

A hypothesis you cannot be wrong about is not a hypothesis.

---

## Step 4 in practice: one variable

The experiment must distinguish your hypothesis from its alternatives.

```
Hypothesis: completion uses a stale hash built at shell start.
Prediction: a command created AFTER the shell started will fail to
            complete, but the same command WILL still run.
Experiment: start a shell, force it to hash, create a new command,
            then try both.
```

That experiment has a result that can contradict the hypothesis, which is
what makes it worth running. Compare with "let me add a flag and see" —
no prediction, so no possible refutation, so no information.

**One variable at a time.** If you change the command *and* the environment
*and* the input, a failure tells you nothing about which one mattered.

**When the prediction fails, the hypothesis dies.** Do not keep the
hypothesis and adjust the experiment. Go back to step 3.

---

## Step 5 in practice: the two shapes

**Solved:**
```
Root cause: <mechanism, one sentence>
Why it looked like <symptom>: <the misleading part>
Fix: <what changed>
Verified: <the check you ran, and what it printed>
```

Include the "why it looked like" line whenever the symptom was misleading.
It is what stops the user re-reporting the same bug.

**Stuck:**
```
I could not determine the cause.
Tried: <approaches, and how each failed>
Ruled out: <what the evidence eliminated, and which evidence>
Still unknown: <the specific open question>
Next: <the single most useful thing to try, and why>
```

A good stuck report is worth more than a bad fix. It is a handoff, not a
failure — the next person starts from your evidence instead of from zero.

---

## Worked contrast

A real investigation: a script runs when typed in full, but its name does
not tab-complete.

**What thrash looks like:**

```
1. check where the script lives                          -> fine
2. check whether the completion system is initialised     -> it isn't
3. call the completion function directly                  -> error
4. same, reformulated                                     -> "not found"
5. locate the function file
6. read the function file
7. same call, with an invented option                     -> "no such option"
8. same call, with more setup                             -> "can only be
                                                             called from a
                                                             completion
                                                             function"
9. grep the function file for that error text             -> nothing
   (the message comes from the binary, not the file)
   ...ends with no diagnosis
```

Six commands spent interrogating; the decisive error appeared four times and
was read as an obstacle each time. Step 2's evidence was correct and never
interpreted. No hypothesis was ever written.

**What the loop does instead:**

```
1. REPRODUCE  drive a real terminal through a pty, press Tab, watch it fail
2. COMPARE    a command that DOES complete differs in one way: it existed
              before the shell started
3. NAME       "completion reads a hash table built at startup; the script
              was added after, so completion cannot see it -- while
              execution still finds it via a live PATH search"
4. PREDICT    "a command created after startup will fail to complete but
              still run; rehash will fix completion"  -> all three confirmed
5. LAND       root cause, fix, and the verification output
```

Five commands, one of which was the answer.

The generalisable part: **when a thing works one way and fails another way,
the two ways use different mechanisms.** Find the mechanism that differs.
"Runs but doesn't complete", "works locally but not in CI", "passes alone but
fails in the suite", "renders but doesn't hydrate" are all the same shape.
