#!/usr/bin/env python3
"""PostToolUse coach -- live, non-blocking course correction.

A/B testing (12 instrumented runs, 27B model) showed the guard's blind
spot: interrogation probes usually exit 0 while printing nothing useful, so
they never register as failures and the blocking guard never fires. The
model thrashes through "successful" commands.

This hook coaches instead of blocking. It watches for two signals that need
no failure classification, and injects a short note the model sees as
context (PostToolUse additionalContext -- confirmed delivered verbatim):

1. A method-error in the output ("can only be called from...") -- the
   signature of interrogating internals that need a context you don't have.
2. The Nth similar command, regardless of exit status -- repetition itself
   is the signal.

Runs in the same process as record.py's logic: this hook both records and
coaches, replacing record.py in hooks.json (one process per event, not two).
"""

import json
import re
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sa_state as S

METHOD_ERROR = re.compile(
    r"""(can\s+only\s+be\s+called\s+from
      | no\s+active\s+(context|session|loop)
      | must\s+be\s+(run|called)\s+(inside|from|within)
      | not\s+available\s+outside
      | outside\s+of\s+a\s+\w+\s+context)""",
    re.IGNORECASE | re.VERBOSE,
)

NUDGE_REPEAT = (
    "[small-agents] That was %d similar commands on one approach. Before the "
    "next command, apply the NAME step: state in one sentence what you think "
    "the cause is and which evidence supports it. If you cannot, stop "
    "gathering and re-read the output you already have. Consider the COMPARE "
    "step: find the nearest case that works and list every difference."
)

NUDGE_METHOD_ERROR = (
    "[small-agents] That error says the call needs a runtime context you do "
    "not have. This approach class cannot work from here -- no variation of "
    "it will. Observe the system instead of interrogating it: run the real "
    "thing and watch (for terminal behaviour, drive a pty: python pty or "
    "script -q). Then apply NAME: one sentence, cause plus evidence."
)

# Deliverable-banking checkpoints. Motivating failure (achilles benchmark,
# 2026-08-18): a 27B spent its whole 45-min budget reverse-engineering a
# datepicker's internals -- 84 succeeding probes, so neither the
# failure-gated guard nor the repeat-capped coach ever fired -- and
# delivered zero runnable output, while the easy 80% of the task needed
# none of that investigation. Succeeding commands can still be a spiral.
CHECKPOINT_MINUTES = (15, 25)
NUDGE_BANK_VALUE = (
    "[small-agents] %d minutes elapsed and no deliverable has been written "
    "yet (only probes/experiments). Investigation is not the product. Bank "
    "value NOW: build and verify the simplest deliverable the task asks for "
    "(the easy cases first), then return to the hard part with the easy "
    "wins already secured. If one sub-problem is consuming everything, "
    "finish everything else first and time-box the hard one explicitly."
)

# A deliverable must live INSIDE the session's workspace (re-match #2
# lesson: the model wrote 7 probe scripts to /tmp and they were miscounted,
# muting the second checkpoint) and not in a hidden directory.
def _is_deliverable(path, cwd):
    path = str(path)
    if cwd and not os.path.abspath(path).startswith(os.path.abspath(cwd) + os.sep):
        return False
    parts = [p for p in path.split("/") if p]
    return bool(parts) and not any(p.startswith(".") for p in parts[-2:])

REPEAT_AT = 3  # coach on the 3rd similar command

# Subagent wrap-up nudges. Re-match #5: an inspection subagent consumed 30+
# of the mission's 45 minutes without returning; the orchestrator (correctly)
# waited, and the external cap killed everything. A dispatched task is a
# bounded errand, not a residency.
SUBAGENT_WRAPUP_MIN = (10, 15)
NUDGE_WRAPUP = (
    "[small-agents] This dispatched task has been running %d minutes. A "
    "subagent is a bounded errand: your parent is blocked waiting for your "
    "verdict. Wrap up NOW -- return what you have (partial inventory, "
    "partial results, plus what remains) rather than overrunning. A partial "
    "verdict the orchestrator can act on beats a complete one that arrives "
    "after the budget is gone."
)


def emit(note):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": note,
        }
    }))


def main():
    if S.disabled():
        return 0

    ev = S.read_event()
    tool = ev.get("tool_name")

    if tool in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        session = ev.get("session_id", "")
        st = S.load(session)
        for rec in st.get("approaches", []):
            rec["fails"] = 0
        if _is_deliverable((ev.get("tool_input") or {}).get("file_path", ""),
                           ev.get("cwd")):
            st["deliverables"] = st.get("deliverables", 0) + 1
        S.save(session, st)
        return 0

    if tool != "Bash":
        return 0

    command = (ev.get("tool_input") or {}).get("command", "")
    toks = S.tokenize(command)
    if len(toks) < S.MIN_TOKENS:
        return 0

    resp = ev.get("tool_response") or {}
    failed = S.looks_failed(resp)
    blob = "\n".join(str(resp.get(k, "")) for k in ("stderr", "stdout", "text"))

    session = ev.get("session_id", "")
    st = S.load(session)
    import time as _time
    st.setdefault("t0", _time.time())

    idx, rec = S.match_approach(st, toks)
    if rec is None:
        rec = {"tokens": sorted(toks), "fails": 0, "runs": 0, "coached": 0}
        st["approaches"].append(rec)

    rec["runs"] = rec.get("runs", 0) + 1
    if failed:
        rec["fails"] = rec.get("fails", 0) + 1
        st["failures"] = st.get("failures", 0) + 1
        rec["tokens"] = sorted(set(rec["tokens"]) | toks)
    else:
        rec["fails"] = 0

    note = None
    agent_id = ev.get("agent_id")
    if agent_id:
        import time as _t2
        ag = st.setdefault("agents", {}).setdefault(
            agent_id, {"t0": _t2.time(), "wrapups": 0})
        a_min = (_t2.time() - ag["t0"]) / 60.0
        if (ag["wrapups"] < len(SUBAGENT_WRAPUP_MIN)
                and a_min >= SUBAGENT_WRAPUP_MIN[ag["wrapups"]]):
            note = NUDGE_WRAPUP % int(a_min)
            ag["wrapups"] += 1
            S.save(session, st)
            emit(note)
            return 0
    if METHOD_ERROR.search(blob[:4000]):
        note = NUDGE_METHOD_ERROR
    elif rec["runs"] >= REPEAT_AT and rec.get("coached", 0) < 2:
        # coach at most twice per approach -- a third identical nudge is noise
        note = NUDGE_REPEAT % rec["runs"]
        rec["coached"] = rec.get("coached", 0) + 1
    else:
        elapsed_min = (_time.time() - st["t0"]) / 60.0
        fired = st.get("checkpoints_fired", 0)
        if (st.get("deliverables", 0) == 0 and fired < len(CHECKPOINT_MINUTES)
                and elapsed_min >= CHECKPOINT_MINUTES[fired]):
            note = NUDGE_BANK_VALUE % int(elapsed_min)
            st["checkpoints_fired"] = fired + 1

    S.save(session, st)
    if note:
        emit(note)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # a coach must never disrupt the session
