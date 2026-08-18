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
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sa_state as S

ESCALATE_AFTER_MIN = 25
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
COMMANDS / RETURN. After PLAN.md exists, work resumes normally.
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
    if os.environ.get("SMALL_AGENTS_PLAN", "") not in ("1", "true"):
        return 0

    ev = S.read_event()
    tool = ev.get("tool_name")
    if tool not in ("Bash", "Write", "Edit", "NotebookEdit", "MultiEdit"):
        return 0
    cwd = ev.get("cwd") or os.getcwd()
    tool_input = ev.get("tool_input") or {}

    # Writing the plan itself is always allowed.
    fp = str(tool_input.get("file_path", ""))
    if tool == "Write" and fp.endswith("PLAN.md"):
        return 0

    if not plan_ok(cwd):
        sys.stderr.write(PLAN_BLOCK)
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
