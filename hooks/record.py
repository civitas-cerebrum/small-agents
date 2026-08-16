#!/usr/bin/env python3
"""PostToolUse recorder.

PostToolUse cannot block (Claude Code ignores exit 2 on this event), so this
hook only observes: it files each Bash command under an "approach" and counts
how many times that approach has failed. guard.py reads those counts.
"""

import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sa_state as S


def main():
    if S.disabled():
        return 0

    ev = S.read_event()
    if ev.get("tool_name") != "Bash":
        return 0

    command = (ev.get("tool_input") or {}).get("command", "")
    toks = S.tokenize(command)
    if len(toks) < S.MIN_TOKENS:
        return 0

    failed = S.looks_failed(ev.get("tool_response"))
    session = ev.get("session_id", "")
    st = S.load(session)

    idx, rec = S.match_approach(st, toks)
    if rec is None:
        rec = {"tokens": sorted(toks), "fails": 0, "runs": 0}
        st["approaches"].append(rec)
        idx = len(st["approaches"]) - 1

    rec["runs"] = rec.get("runs", 0) + 1
    if failed:
        rec["fails"] = rec.get("fails", 0) + 1
        st["failures"] = st.get("failures", 0) + 1
        # Keep the fingerprint current: a reformulated attempt drifts, and we
        # want the union so later variants still match this approach.
        rec["tokens"] = sorted(set(rec["tokens"]) | toks)
    else:
        # A working command clears the approach -- it is no longer a dead end.
        rec["fails"] = 0

    S.save(session, st)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # a recorder must never disrupt the session
