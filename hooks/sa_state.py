"""Shared state and command-similarity logic for the small-agents harness.

The harness answers one question: "has the agent already tried this and
watched it fail?" Small models re-run near-identical commands because they
treat a failure as a parameter problem when it is an approach problem.

Commands are reduced to a token set, and two commands are "the same approach"
when their token sets overlap past a threshold. This catches reformulations
(different quoting, extra echo, an added flag) that an exact-match check
would miss entirely.
"""

import json
import os
import re
import sys

# Tokens that appear in almost every shell command and therefore carry no
# information about *which approach* is being attempted.
STOPWORDS = frozenset("""
echo then else elif done fi do if for while
true false null and not the with
""".split())

DEFAULT_THRESHOLD = 0.55
DEFAULT_FAIL_LIMIT = 2  # block the attempt that would be the 3rd
MIN_TOKENS = 2  # below this a command is too short to fingerprint reliably

# Error markers that indicate failure even when the shell reports exit 0
# (very common in compound `a; b; c` commands where only the last exit
# code survives -- precisely the shape small models emit).
ERROR_PATTERNS = re.compile(
    r"""(
        command\s+not\s+found
      | no\s+such\s+(file|option|directory)
      | not\s+found
      | can\s+only\s+be\s+called
      | permission\s+denied
      | unrecognized\s+(option|argument)
      | invalid\s+(option|argument|syntax)
      | undefined\s+(reference|variable|method)
      | unbound\s+variable
      | parse\s+error
      | syntax\s+error
      | Traceback\s+\(most\s+recent
      | \bfatal:
      | \berror:
      | \bERROR\b
      | AssertionError
      | ModuleNotFoundError
      | NameError|TypeError|ValueError|AttributeError|KeyError
    )""",
    re.IGNORECASE | re.VERBOSE,
)


# --------------------------------------------------------------------------
# event / state plumbing
# --------------------------------------------------------------------------

def read_event():
    """Read the hook payload from stdin. Never raises -- a broken payload
    must not take the user's session down with it."""
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def disabled():
    return os.environ.get("SMALL_AGENTS_DISABLE", "") not in ("", "0", "false")


def _env_int(name, default):
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def fail_limit():
    return _env_int("SMALL_AGENTS_FAIL_LIMIT", DEFAULT_FAIL_LIMIT)


def threshold():
    try:
        return float(os.environ["SMALL_AGENTS_THRESHOLD"])
    except (KeyError, ValueError):
        return DEFAULT_THRESHOLD


def state_dir():
    base = os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.expanduser(
        "~/.claude/small-agents"
    )
    path = os.path.join(base, "state")
    os.makedirs(path, exist_ok=True)
    return path


def _state_path(session_id):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "nosession")[:120]
    return os.path.join(state_dir(), safe + ".json")


def load(session_id):
    try:
        with open(_state_path(session_id)) as fh:
            st = json.load(fh)
    except Exception:
        st = {}
    st.setdefault("approaches", [])
    st.setdefault("failures", 0)
    st.setdefault("blocks", 0)
    st.setdefault("landed_block", False)
    return st


def save(session_id, st):
    try:
        tmp = _state_path(session_id) + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(st, fh)
        os.replace(tmp, _state_path(session_id))
    except Exception:
        pass  # state is an optimisation, never a hard dependency


# --------------------------------------------------------------------------
# similarity
# --------------------------------------------------------------------------

def tokenize(command):
    """Reduce a shell command to the token set that identifies its approach."""
    if not command:
        return set()
    lowered = command.lower()
    # Split on path and extension separators too. Keeping "/" and "." inside
    # tokens collapses an entire path into a single atom, which silently
    # pushes ordinary commands ("python3 host.py") under MIN_TOKENS and makes
    # the harness inert for exactly the commands agents run most.
    raw = re.split(r"[^a-z0-9_-]+", lowered)
    toks = set()
    for t in raw:
        t = t.strip("-_")
        if len(t) < 3:
            continue
        if t in STOPWORDS:
            continue
        if t.isdigit():
            continue
        toks.add(t)
    return toks


def similarity(a, b):
    """Jaccard overlap of two token sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def looks_failed(tool_response):
    """Did this command fail? Trust exit_code, but also scan the output --
    compound commands mask failures behind a successful final segment."""
    if not isinstance(tool_response, dict):
        return False
    code = tool_response.get("exit_code")
    if isinstance(code, int) and code != 0:
        return True
    if tool_response.get("interrupted"):
        return False  # user interruption is not the agent's failure
    blob = "\n".join(
        str(tool_response.get(k, ""))
        for k in ("stderr", "stdout", "text")
    )
    return bool(ERROR_PATTERNS.search(blob))


def match_approach(state, toks, thresh=None):
    """Return (index, record) of the closest recorded approach, or (None, None)."""
    if len(toks) < MIN_TOKENS:
        return None, None
    thresh = threshold() if thresh is None else thresh
    best_i, best_rec, best_score = None, None, 0.0
    for i, rec in enumerate(state.get("approaches", [])):
        score = similarity(toks, set(rec.get("tokens", [])))
        if score >= thresh and score > best_score:
            best_i, best_rec, best_score = i, rec, score
    return best_i, best_rec
