#!/usr/bin/env python3
"""PreToolUse guard -- blocks a third run of an approach that has already
failed twice.

The escape hatch is deliberate and is the whole point of the harness: the
agent may retry a blocked approach, but only by writing a hypothesis into
the Bash tool's `description` field. That forces the one step small models
skip -- saying out loud what they think is wrong and why -- and it is
checkable from inside a hook, unlike prose in a chat message.
"""

import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sa_state as S

HYPOTHESIS_PREFIX = "HYPOTHESIS:"
MIN_HYPOTHESIS_CHARS = 30

BLOCK_MESSAGE = """\
BLOCKED by small-agents: {history}

Do ONE of these instead:

1. Re-read the last error literally. If it says something is impossible
   (wrong context, unsupported operation, missing capability), it will not
   become possible with different flags. Choose a different mechanism.

2. Observe the system instead of interrogating it. If you want to know what
   something does, run it and watch the result. Do not ask its internals to
   describe themselves.

3. Compare a working case against the broken one. Find something similar
   that DOES work, and list every difference.

If you still believe this exact approach is right, re-run it with a
hypothesis in the tool's `description` field, in this form:

    description: "HYPOTHESIS: <what you think is wrong and why you think so>"

It must be at least {minchars} characters and name a cause, not a next step.
"""


def main():
    if S.disabled():
        return 0

    ev = S.read_event()
    if ev.get("tool_name") != "Bash":
        return 0

    tool_input = ev.get("tool_input") or {}
    command = tool_input.get("command", "")
    toks = S.tokenize(command)
    if len(toks) < S.MIN_TOKENS:
        return 0

    session = ev.get("session_id", "")
    st = S.load(session)
    idx, rec = S.match_approach(st, toks)

    if rec is None or rec.get("fails", 0) < S.fail_limit():
        return 0

    # Escape hatch: an articulated hypothesis buys another attempt.
    desc = (tool_input.get("description") or "").strip()
    if desc.upper().startswith(HYPOTHESIS_PREFIX):
        body = desc[len(HYPOTHESIS_PREFIX):].strip()
        if len(body) >= MIN_HYPOTHESIS_CHARS:
            rec["fails"] = 0          # hypothesis granted; clock resets
            rec["hypotheses"] = rec.get("hypotheses", 0) + 1
            S.save(session, st)
            return 0

    st["blocks"] = st.get("blocks", 0) + 1
    S.save(session, st)

    fails = rec.get("fails", 0)
    # Never claim failures that did not happen -- a self-contradictory block
    # message ("has already failed 0 times") destroys the message's authority
    # and invites the agent to dismiss the whole harness.
    if fails > 0:
        history = (
            "this approach has already failed %d times.\n\n"
            "This would be attempt %d. The command is a reformulation of one\n"
            "that already failed -- so the parameters are not the problem,\n"
            "the approach is." % (fails, fails + 1)
        )
    else:
        history = (
            "this approach has already been run in this session.\n\n"
            "Re-running it unchanged cannot produce new information."
        )

    sys.stderr.write(
        BLOCK_MESSAGE.format(history=history, minchars=MIN_HYPOTHESIS_CHARS)
    )
    return 2  # exit 2 on PreToolUse blocks the call; stderr is the reason


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # fail open -- never wedge a session on a harness bug
