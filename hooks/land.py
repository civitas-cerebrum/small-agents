#!/usr/bin/env python3
"""Stop hook -- refuses a silent exit from a failed investigation.

The failure this exists for: an agent burns a dozen commands on a problem,
fails, and then ends its turn with nothing -- no cause, no fix, no admission
of being stuck. The user is left worse off than if it had never started,
because the transcript looks like work.

Rule: if the session accumulated real failures, the closing message must
either name a cause or say plainly that it is stuck. Both are acceptable.
Silence is not.
"""

import re
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sa_state as S

MIN_FAILURES = 2      # below this, no real investigation happened
MIN_CHARS = 180       # a closing message shorter than this cannot have landed

# Either of these counts as landing the plane.
LANDED = re.compile(
    r"""(
        root\s+cause
      | the\s+cause\s+(is|was)
      | caused\s+by
      | because\b
      | turns?\s+out
      | the\s+(bug|problem|issue|failure)\s+(is|was)
      | i'?m\s+stuck | i\s+am\s+stuck
      | could\s+not\s+(determine|find|reproduce|identify)
      | couldn'?t\s+(determine|find|reproduce|identify)
      | unable\s+to\s+(determine|find|reproduce|identify)
      | ruled\s+out
      | still\s+(failing|unresolved|unknown)
      | needs?\s+(your|user|human)\s+input
      | i\s+don'?t\s+(know|understand)
    )""",
    re.IGNORECASE | re.VERBOSE,
)

BLOCK_MESSAGE = """\
BLOCKED by small-agents: do not end here.

This session recorded {failures} failed commands, and the closing message
does not report an outcome. An investigation that stops without a verdict
leaves the user worse off than one that never started.

Before ending, say one of these plainly:

  * The root cause: "X happens because Y" -- plus the fix and how you
    verified it.
  * Or that you are stuck: what you tried, what you ruled out, what the
    evidence actually showed, and the single most useful thing to try next.

"I am stuck" is a complete and acceptable answer. Silence is not.
"""


def main():
    if S.disabled():
        return 0

    ev = S.read_event()

    # Never fight a stop twice -- that is an infinite loop.
    if ev.get("stop_hook_active"):
        return 0

    session = ev.get("session_id", "")
    st = S.load(session)

    if st.get("landed_block"):
        return 0
    if st.get("failures", 0) < MIN_FAILURES:
        return 0

    msg = (ev.get("last_assistant_message") or "").strip()
    if len(msg) >= MIN_CHARS and LANDED.search(msg):
        return 0
    if len(msg) >= MIN_CHARS * 4:
        return 0  # a substantial writeup; don't nitpick its phrasing

    st["landed_block"] = True
    S.save(session, st)

    sys.stderr.write(BLOCK_MESSAGE.format(failures=st.get("failures", 0)))
    return 2  # exit 2 on Stop prevents the stop and continues the turn


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
