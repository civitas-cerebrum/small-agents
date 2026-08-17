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

REPEAT_AT = 3  # coach on the 3rd similar command


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
    if METHOD_ERROR.search(blob[:4000]):
        note = NUDGE_METHOD_ERROR
    elif rec["runs"] >= REPEAT_AT and rec.get("coached", 0) < 2:
        # coach at most twice per approach -- a third identical nudge is noise
        note = NUDGE_REPEAT % rec["runs"]
        rec["coached"] = rec.get("coached", 0) + 1

    S.save(session, st)
    if note:
        emit(note)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # a coach must never disrupt the session
