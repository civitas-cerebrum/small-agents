#!/usr/bin/env python3
"""PreToolUse plan gate -- mission mode's mandatory brainstorm-then-plan.

Active only when SMALL_AGENTS_PLAN=1 (mission mode: long multi-deliverable
tasks). Motivating evidence: two 45-minute benchmark runs in which a 27B
was captured by the hardest sub-problem from minute one and delivered
nothing, ignoring an advisory mid-run nudge. Every effective mechanism in
this plugin is a gate, not a suggestion (the hypothesis gate measured
p=0.021); planning gets the same treatment.

Rule 1 (plan first): no Bash/Edit/Write until ./PLAN.md exists with the
required shape -- a brainstormed, ordered task list, easiest value first,
one deliverable + verification per task. Writing PLAN.md itself is always
allowed.

Rule 2 (bank or justify): with a plan in place, if 25+ minutes pass with
zero deliverables banked inside the workspace, further Bash is blocked
until either a deliverable lands or the call carries an explicit
`INVESTIGATION: <why this must continue, >=30 chars>` in its description
-- the same escape-hatch pattern as the hypothesis gate.

Rule 3 (strict dispatch, SMALL_AGENTS_PLAN=2): once the plan exists, the
MAIN session becomes a pure orchestrator -- every plan task must run in a
subagent (Agent/Task tool), keeping the orchestrator's context to plan +
verdicts. Empirically distinguished via the hook payload's agent_id
(measured: null in the main session, set in subagents), so subagents work
freely. The orchestrator keeps: PLAN.md edits, and Bash whose description
starts with `VERIFY:` (running a task's verification itself is the
orchestrator's job). Evidence: the one dispatched phase in re-match #3
was the phase that had consumed entire 45-minute budgets when inline, and
the orchestrator still hit the 129k context ceiling from the tasks it ran
inline.
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sa_state as S

ESCALATE_AFTER_MIN = 25
SUBAGENT_DEADLINE_MIN = 20   # hard; nudges at 10/15 proved advisory-only
                              # (90-min run: one dispatch consumed 73 min
                              # through two ignored wrap-up nudges)
INVESTIGATION_PREFIX = "INVESTIGATION:"
MIN_JUSTIFICATION = 30

PLAN_BLOCK = """\
BLOCKED by small-agents (mission mode): no PLAN.md yet.

Before any command or edit, brainstorm and write the plan. Think through:
what is actually being asked; which parts are easy wins and which are
genuinely hard; what order banks the most value earliest.

Then Write ./PLAN.md containing:

  ## Goal
  <one sentence>

  ## Tasks   (ordered easiest-value-first; the hard part goes LAST)
  - [ ] 1. <task> | deliverable: <file path> | verify: <command>
  - [ ] 2. <task> | deliverable: <file path> | verify: <command>
  ...

Each task must be small enough to hand to a fresh subagent (Task tool)
with a four-part brief: GOAL / CONTEXT (only what that task needs) /
COMMANDS / RETURN.

Specify BREADTH, not just areas -- "write field-level tests" is vague;
"one test per field + edge cases for complex interactions" is
actionable. A subagent delivers what the brief asks for, nothing more.

After PLAN.md exists, work resumes normally.
"""

BANK_BLOCK = """\
BLOCKED by small-agents (mission mode): {mins} minutes elapsed and no
deliverable from PLAN.md has been written inside the workspace yet.

Investigation is not the product. Complete the easiest unfinished task in
PLAN.md now -- write its deliverable and run its verify command -- then
continue. Probe scripts (in /tmp or dot-directories) do not count.

If continuing the current investigation truly is the right call, re-run
this command with a justification in the tool description:

    description: "INVESTIGATION: <what this will decide and why it cannot
    wait until after the next deliverable>"
"""


DEADLINE_BLOCK = """\
BLOCKED by small-agents (dispatch deadline): this dispatched task has run
{mins} minutes -- past its hard deadline. All further tool use in this
dispatch is blocked.

Your only remaining move is the right one: END NOW with your verdict --
what you established, what you produced, what remains. A partial verdict
your parent can act on is the deliverable; more tool calls are not.
"""


DISPATCH_BLOCK = """\
BLOCKED by small-agents (strict dispatch): the plan exists, so the main
session is now an orchestrator. This work belongs in a subagent.

Dispatch the current PLAN.md task with the Agent/Task tool, briefing it
with: GOAL (that one task) / CONTEXT (only what it needs -- paths, the
element inventory, the verify command) / COMMANDS / RETURN (a capped
verdict, never a transcript). The subagent works freely; your context
stays clean for the remaining tasks.

The orchestrator itself may still: edit PLAN.md (tracking progress), and
run a task's verification directly with a Bash call whose description
starts with "VERIFY:".
"""


def plan_ok(cwd):
    p = os.path.join(cwd, "PLAN.md")
    try:
        s = open(p).read()
    except OSError:
        return False
    return ("## Tasks" in s and len(re.findall(r"- \[.\]", s)) >= 2
            and "verify" in s.lower())


def main():
    if S.disabled():
        return 0
    if os.environ.get("SMALL_AGENTS_PLAN", "") not in ("1", "2", "true"):
        return 0

    ev = S.read_event()
    tool = ev.get("tool_name")
    if tool not in ("Bash", "Write", "Edit", "NotebookEdit", "MultiEdit"):
        return 0
    cwd = ev.get("cwd") or os.getcwd()
    tool_input = ev.get("tool_input") or {}

    # Hard dispatch deadline: inside a subagent past the window, every tool
    # is blocked -- the only possible next act is emitting the verdict.
    agent_id = ev.get("agent_id")
    if agent_id:
        session = ev.get("session_id", "")
        st = S.load(session)
        ag = st.setdefault("agents", {}).setdefault(
            agent_id, {"t0": time.time(), "wrapups": 0})
        S.save(session, st)
        a_min = (time.time() - ag["t0"]) / 60.0
        if a_min >= SUBAGENT_DEADLINE_MIN:
            sys.stderr.write(DEADLINE_BLOCK.format(mins=int(a_min)))
            return 2
        return 0   # within deadline: subagents work freely

    # Writing the plan itself is always allowed.
    fp = str(tool_input.get("file_path", ""))
    if tool == "Write" and fp.endswith("PLAN.md"):
        return 0

    if not plan_ok(cwd):
        sys.stderr.write(PLAN_BLOCK)
        return 2

    # Rule 3: strict dispatch -- main session orchestrates, subagents work.
    if os.environ.get("SMALL_AGENTS_PLAN") == "2" and not ev.get("agent_id"):
        desc = str(tool_input.get("description", "")).strip()
        if tool == "Bash" and desc.upper().startswith("VERIFY:"):
            pass  # orchestrator running a task's verification
        elif tool in ("Edit", "Write") and fp.endswith("PLAN.md"):
            pass  # plan bookkeeping
        else:
            sys.stderr.write(DISPATCH_BLOCK)
            return 2

    # Rule 2: bank-or-justify escalation (Bash only -- edits ARE banking).
    if tool != "Bash":
        return 0
    session = ev.get("session_id", "")
    st = S.load(session)
    t0 = st.get("t0")
    if not t0:
        return 0
    mins = (time.time() - t0) / 60.0
    if mins < ESCALATE_AFTER_MIN or st.get("deliverables", 0) > 0:
        return 0

    desc = str(tool_input.get("description", "")).strip()
    if desc.upper().startswith(INVESTIGATION_PREFIX):
        if len(desc[len(INVESTIGATION_PREFIX):].strip()) >= MIN_JUSTIFICATION:
            return 0

    st["plan_blocks"] = st.get("plan_blocks", 0) + 1
    S.save(session, st)
    sys.stderr.write(BANK_BLOCK.format(mins=int(mins)))
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # fail open -- never wedge a session on a harness bug
