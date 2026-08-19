#!/usr/bin/env python3
"""SessionStart hook -- delivers the protocol core as session context.

Live A/B testing showed the passive route fails: the skill listing may carry
only the bare skill name, and a small model mid-task does not stop to invoke
a Skill tool it has never heard of. In 3 of 4 instrumented runs the skill
body never entered context at all. SessionStart stdout is injected as
context unconditionally, so the protocol is present from turn 1.

Kept deliberately compact: the operative core only, so it does not crowd a
small context window. The full protocol stays in the skill files.
"""

import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sa_state as S

PROTOCOL = """\
[small-agents] This session runs on a small/local model. Follow this
protocol; two of its rules are enforced by hooks.

When DIAGNOSING (finding out why something is broken):
1. REPRODUCE - run the failing thing and watch it fail. Observe the system;
   do not interrogate its internals (calling internal functions by hand
   almost always needs a runtime context you do not have). If behaviour
   needs a real terminal, drive one through a pty (python pty, script -q).
2. COMPARE - find the nearest case that works and list every difference.
3. NAME - before the next command, write one sentence: "I think <cause>
   because <evidence already seen>". No sentence = no hypothesis = stop.
4. PREDICT - say what you expect, then run ONE command. Wrong prediction
   kills the hypothesis; write a new one, do not re-run variations.
5. LAND - end with a verdict: either the root cause + fix + verification,
   or "I am stuck" + what you tried + what you ruled out + best next step.

Enforced: a 3rd run of an approach that failed twice is blocked (write
HYPOTHESIS: <cause and evidence> in the tool description to proceed);
ending after failures with no verdict is blocked.

When EDITING: re-read before every edit, keep edits under ~30 lines, never
reference an API you have not seen in this session, verify after each step.
Error messages are literal - "no such option" means it does not exist;
"can only be called from X" means there is no path from outside X.
If a subagent/Task tool is available, run long investigations as an
orchestrator: keep a <=15-line notebook, dispatch each step as a subagent
with GOAL / CONTEXT (only what that step needs) / COMMANDS / RETURN
(capped verdict, never a transcript). Fresh context per step beats one
long window accumulating dead ends."""


MISSION = """
MISSION MODE is active (SMALL_AGENTS_PLAN={mode}): this is a long,
multi-deliverable task. The harness enforces:
1. Brainstorm FIRST, then Write ./PLAN.md (ordered easiest-value-first,
   one deliverable + verify command per task; the hard part goes LAST).
   All other tools are blocked until PLAN.md exists.
2. Tackle each task with a fresh subagent via the Agent/Task tool --
   brief it with GOAL / CONTEXT (only what that task needs) / COMMANDS /
   RETURN (capped verdict). Keep this context to the plan plus verdicts.
   (Under SMALL_AGENTS_PLAN=2 this is ENFORCED: after the plan exists,
   the main session may only dispatch, edit PLAN.md, and run
   verifications via Bash described as "VERIFY: ...".)
3. Bank deliverables early and often; after 25 minutes with nothing
   banked, non-deliverable commands are blocked.
4. Give every dispatch brief a time budget ("aim for <=10 minutes;
   return a partial verdict rather than overrunning") -- dispatched
   subagents get harness wrap-up nudges at 10 and 15 minutes.
   ATOMICITY: a task whose brief needs more than a few lines is a
   composite -- split it into separate PLAN.md tasks BEFORE dispatching
   (re-match #5: one "inspect everything" dispatch ran 30+ minutes;
   five 5-minute errands would have banked partial value throughout).
   BREADTH: specify per-behavior coverage in the brief, not per-area.
   "Write tests for the form" produces minimal coverage; "write one
   test per field, plus edge cases for each complex interaction
   (select, datepicker, validation)" produces thorough coverage.
   The brief caps what the subagent delivers -- list every test or
   behavior you expect, because the subagent will not add its own.
   If you are the DISPATCHED agent: your brief is your plan -- open by
   listing the 3-5 checks you will perform, then execute them in order;
   do not create plans of your own or dispatch further agents.
5. A dispatched subagent DIES IF THIS SESSION ENDS. After dispatching,
   WAIT for its verdict (blocking TaskOutput) and only then update
   PLAN.md and move on. Ending with unchecked plan tasks is blocked;
   a task you cannot finish must be marked blocked in PLAN.md with a
   one-line reason."""


def main():
    if S.disabled():
        return 0
    print(PROTOCOL)
    mode = os.environ.get("SMALL_AGENTS_PLAN", "")
    if mode in ("1", "2", "true"):
        print(MISSION.format(mode=mode))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
