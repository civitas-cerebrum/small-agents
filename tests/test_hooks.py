#!/usr/bin/env python3
"""Harness tests.

The primary fixture is not synthetic: REAL_SESSION replays the nine Bash
commands a 32B local model actually issued while failing to diagnose a zsh
tab-completion bug. Commands 3, 4, 7 and 8 are the same dead-end approach
(hand-driving zsh's completion functions from a non-interactive shell,
which is impossible), reformulated four times. The harness must stop it at
the third, and must stay silent through the legitimate commands.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(os.path.dirname(HERE), "hooks")

PASS, FAIL = [], []


def run_hook(script, payload, env=None):
    e = dict(os.environ)
    e.update(env or {})
    p = subprocess.run(
        [sys.executable, os.path.join(HOOKS, script)],
        input=json.dumps(payload),
        capture_output=True, text=True, env=e,
    )
    return p.returncode, p.stderr


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (("  -- " + detail) if detail and not cond else ""))


def pre(cmd, sid, desc="", env=None):
    return run_hook("guard.py", {
        "session_id": sid, "hook_event_name": "PreToolUse",
        "tool_name": "Bash", "tool_input": {"command": cmd, "description": desc},
    }, env)


def post(cmd, sid, exit_code=0, stderr="", stdout="", env=None):
    return run_hook("record.py", {
        "session_id": sid, "hook_event_name": "PostToolUse",
        "tool_name": "Bash", "tool_input": {"command": cmd},
        "tool_response": {"exit_code": exit_code, "stderr": stderr,
                          "stdout": stdout, "interrupted": False},
    }, env)


# --- the real session -------------------------------------------------------
# (command, exit_code, stderr, is_the_dead_end_approach)
REAL_SESSION = [
    ("""echo "=== type/which ==="; type -a lets-claude 2>&1; echo "=== PATH ==="; echo $PATH; echo "=== interactive zsh view ==="; zsh -ic 'type -a lets-claude; alias | grep -i lets; echo PATH=$PATH' 2>&1""",
     0, "", False),
    ("""echo "=== file ==="; ls -l /Users/dev/.local/bin/lets-claude; echo "=== completion system loaded in interactive zsh? ==="; zsh -ic 'whence -w compinit _main_complete 2>&1'; echo "=== rc files mentioning compinit ==="; grep -nH compinit /Users/dev/.zshrc /Users/dev/.zprofile /etc/zshrc 2>/dev/null""",
     0, "", False),
    ("""zsh -c '
autoload -Uz compinit
compinit -u >/dev/null 2>&1
echo "_main_complete loaded: $(whence -w _main_complete)"
autoload -Uz compadd
PREFIX="lets-cl" SUFFIX="" CURRENT=1
typeset -ga _comps=()
_command_names >/dev/null 2>&1
echo "completions offered for lets-cl => ${_comps[@]}"
'""", 1, "", True),
    ("""zsh -c '
autoload -Uz compinit
compinit -u 2>&1 | head -3
autoload -Uz compadd
PREFIX="lets-cl" SUFFIX="" CURRENT=1
typeset -ga _comps=()
_command_names
print -l "exit=$?"
print -l -- "completions: ${_comps[@]}"
' 2>&1""", 0, "zsh:7: command not found: _command_names", True),
    ("""zsh -c 'print -l $fpath'; echo ---; find /usr/share/zsh -name "_command_names" 2>/dev/null""",
     0, "", False),
    ("""ls /usr/share/zsh/5.9/functions/ | head -40; echo ---; head -30 /usr/share/zsh/5.9/functions/_command_names""",
     0, "", False),
    ("""zsh -c '
autoload -Uz compinit
compinit -u >/dev/null 2>&1
setopt functions_autoload
context=command
PREFIX="lets-cl" SUFFIX="" CURRENT=1
typeset -ga _comps=()
_command_names 2>&1
print -l "completions offered for lets-cl => ${_comps[@]}"
'""", 1, "zsh:setopt:4: no such option: functions_autoload", True),
    ("""zsh -c '
autoload -Uz compinit
compinit -u >/dev/null 2>&1
typeset -A compstate
context=command
PREFIX="lets-cl" SUFFIX="" CURRENT=1
typeset -ga _comps=()
_command_names 2>&1
print -l "completions offered for lets-cl => ${_comps[@]}"
'""", 0, "_tags:comptags:36: can only be called from completion function", True),
]


def test_real_session():
    print("\n[1] replay of the real failed session")
    sid = "real-" + os.urandom(4).hex()
    blocked_at = None
    for i, (cmd, code, err, dead_end) in enumerate(REAL_SESSION, 1):
        rc, msg = pre(cmd, sid)
        if rc == 2 and blocked_at is None:
            blocked_at = i
        if rc != 2:
            post(cmd, sid, code, err)
        if not dead_end:
            check("cmd %d (legitimate) not blocked" % i, rc == 0,
                  "guard fired on a good command")

    check("dead-end approach was blocked", blocked_at is not None,
          "guard never fired -- thrash would have continued")
    check("blocked on the 3rd attempt (cmd 7), not earlier",
          blocked_at == 7, "blocked at %s, expected 7" % blocked_at)


def test_hypothesis_unblocks():
    print("\n[2] hypothesis escape hatch")
    sid = "hyp-" + os.urandom(4).hex()
    c = "zsh -c 'autoload compinit; _command_names; PREFIX=lets-cl'"
    for _ in range(2):
        post(c, sid, 1, "error: nope")
    rc, _ = pre(c, sid)
    check("blocked without hypothesis", rc == 2)

    rc, _ = pre(c, sid, desc="HYPOTHESIS: too short")
    check("rejects a stub hypothesis", rc == 2)

    rc, _ = pre(c, sid, desc="HYPOTHESIS: compadd only works inside a real ZLE "
                             "completion context, so this can never work here")
    check("real hypothesis unblocks", rc == 0)

    rc, _ = pre(c, sid)
    check("clock resets after hypothesis", rc == 0)


def test_success_clears():
    print("\n[3] a working command clears the approach")
    sid = "clr-" + os.urandom(4).hex()
    c = "grep -rn compinit /Users/dev/.zshrc /etc/zshrc"
    post(c, sid, 1, "error: no such file")
    post(c, sid, 1, "error: no such file")
    rc, _ = pre(c, sid)
    check("blocked after two failures", rc == 2)
    post(c, sid, 0, "")          # it worked this time
    rc, _ = pre(c, sid)
    check("unblocked after success", rc == 0)


def test_compound_masked_failure():
    print("\n[4] failure hidden behind exit 0 in a compound command")
    sid = "cmp-" + os.urandom(4).hex()
    c = "zsh -c 'setopt functions_autoload; _command_names; print done'"
    for _ in range(2):
        post(c, sid, 0, "", "zsh: no such option: functions_autoload\ndone")
    rc, _ = pre(c, sid)
    check("detects failure via output, not just exit code", rc == 2)


def test_stop_hook():
    print("\n[5] Stop hook -- landing the plane")
    sid = "stop-" + os.urandom(4).hex()
    for _ in range(3):
        post("zsh -c 'broken thing here _command_names'", sid, 1, "error: bad")

    rc, _ = run_hook("land.py", {
        "session_id": sid, "hook_event_name": "Stop",
        "stop_hook_active": False,
        "last_assistant_message": "No response requested."})
    check("blocks silent abandonment", rc == 2)

    sid2 = "stop2-" + os.urandom(4).hex()
    for _ in range(3):
        post("zsh -c 'broken thing here _command_names'", sid2, 1, "error: bad")
    rc, _ = run_hook("land.py", {
        "session_id": sid2, "hook_event_name": "Stop",
        "stop_hook_active": False,
        "last_assistant_message":
            "The root cause is a stale command hash. zsh populates its hash "
            "table once at startup; lets-claude was symlinked in afterwards, "
            "so completion cannot see it while execution still finds it via a "
            "live PATH search. Fixed by adding compinit plus "
            "zstyle ':completion:*' rehash true to ~/.zshrc, verified with a "
            "pty replay that now completes on the first attempt."})
    check("allows a real root-cause report", rc == 0)

    sid3 = "stop3-" + os.urandom(4).hex()
    for _ in range(3):
        post("zsh -c 'broken thing here _command_names'", sid3, 1, "error: bad")
    rc, _ = run_hook("land.py", {
        "session_id": sid3, "hook_event_name": "Stop",
        "stop_hook_active": False,
        "last_assistant_message":
            "I am stuck. I confirmed the script is on PATH and executable, and "
            "I ruled out a PATH ordering problem and a permissions problem. "
            "What I could not determine is why ZLE refuses the completion, "
            "because I could not observe a real TAB keypress from a "
            "non-interactive shell. The next thing to try is driving zsh "
            "through a pty so the widget actually runs."})
    check("accepts an honest stuck report", rc == 0)

    sid4 = "stop4-" + os.urandom(4).hex()
    rc, _ = run_hook("land.py", {
        "session_id": sid4, "hook_event_name": "Stop",
        "stop_hook_active": False, "last_assistant_message": "Done."})
    check("stays quiet when no investigation happened", rc == 0)

    rc, _ = run_hook("land.py", {
        "session_id": sid, "hook_event_name": "Stop",
        "stop_hook_active": True, "last_assistant_message": "No."})
    check("never loops (stop_hook_active honoured)", rc == 0)

    rc, _ = run_hook("land.py", {
        "session_id": sid, "hook_event_name": "Stop",
        "stop_hook_active": False, "last_assistant_message": "No."})
    check("blocks at most once per session", rc == 0)


def test_safety():
    print("\n[6] safety -- the harness must never wedge a session")
    sid = "safe-" + os.urandom(4).hex()
    c = "zsh -c 'dead end approach _command_names compinit'"
    for _ in range(3):
        post(c, sid, 1, "error: bad")

    rc, _ = pre(c, sid, env={"SMALL_AGENTS_DISABLE": "1"})
    check("SMALL_AGENTS_DISABLE=1 disables the guard", rc == 0)

    rc, _ = pre("ls", sid)
    check("short commands are never fingerprinted", rc == 0)

    for script in ("guard.py", "record.py", "land.py"):
        p = subprocess.run([sys.executable, os.path.join(HOOKS, script)],
                           input="not json at all", capture_output=True, text=True)
        check("%s fails open on malformed payload" % script, p.returncode == 0)

    p = subprocess.run([sys.executable, os.path.join(HOOKS, "guard.py")],
                       input=json.dumps({"tool_name": "Read",
                                         "tool_input": {"file_path": "/x"}}),
                       capture_output=True, text=True)
    check("ignores non-Bash tools", p.returncode == 0)


if __name__ == "__main__":
    tmp = tempfile.mkdtemp(prefix="sa-test-")
    os.environ["CLAUDE_PLUGIN_DATA"] = tmp
    try:
        test_real_session()
        test_hypothesis_unblocks()
        test_success_clears()
        test_compound_masked_failure()
        test_stop_hook()
        test_safety()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        print("failed: " + ", ".join(FAIL))
    sys.exit(1 if FAIL else 0)
