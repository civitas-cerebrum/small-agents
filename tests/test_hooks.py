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
    return run_hook("coach.py", {
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


def test_short_real_commands_are_fingerprinted():
    """Regression: found by live testing against a 27B model.

    The tokenizer kept "/" and "." inside tokens, so a whole path collapsed
    into one atom and ordinary commands fell under MIN_TOKENS -- the harness
    silently ignored every command in a real session."""
    print("\n[7] short real-world commands are fingerprinted")
    sys.path.insert(0, HOOKS)
    import sa_state as S
    for cmd, least in [("python3 host.py", 2),
                       ("python3 -m app.main", 3),
                       ("ls -R /private/tmp/scratch/runD", 4),
                       ("cat app/cache.py", 3)]:
        n = len(S.tokenize(cmd))
        check("tokenizes %r into >=%d tokens (got %d)" % (cmd, least, n),
              n >= least)

    sid = "short-" + os.urandom(4).hex()
    for _ in range(2):
        post("python3 host.py", sid, 1, "ModuleNotFoundError: no module named app")
    rc, _ = pre("python3 host.py", sid)
    check("a repeated short failing command is now caught", rc == 2)


def test_edit_resets_clock():
    """Regression: re-running a command after fixing the code is
    verification, not thrash, and must never be blocked."""
    print("\n[8] an edit resets the approach clock")
    sid = "edit-" + os.urandom(4).hex()
    c = "python3 -m pytest tests/test_report.py"
    for _ in range(2):
        post(c, sid, 1, "AssertionError: expected 3 got 0")
    rc, _ = pre(c, sid)
    check("blocked while nothing has changed", rc == 2)

    run_hook("coach.py", {
        "session_id": sid, "hook_event_name": "PostToolUse",
        "tool_name": "Edit", "tool_input": {"file_path": "app/report.py"},
        "tool_response": {"type": "text"}})
    rc, _ = pre(c, sid)
    check("re-running the same command after an edit is allowed", rc == 0)


def test_block_message_is_truthful():
    """Regression: found live -- the model was told an approach "has already
    failed 0 times", spotted the contradiction, and dismissed the harness as
    misconfigured. A block message must never claim failures that did not
    happen."""
    print("\n[9] block message never claims phantom failures")
    sid = "msg-" + os.urandom(4).hex()
    c = "python3 host.py"
    post(c, sid, 0, "")                      # a SUCCESS, no failures at all
    rc, msg = pre(c, sid, env={"SMALL_AGENTS_FAIL_LIMIT": "0"})
    check("blocks under FAIL_LIMIT=0", rc == 2)
    check("does not claim 'failed 0 times'", "failed 0 times" not in msg,
          repr(msg[:80]))
    check("states the true history instead",
          "already been run in this session" in msg, repr(msg[:120]))
    check("body does not contradict it either",
          "already failed" not in msg, repr(msg[:250]))

    sid2 = "msg2-" + os.urandom(4).hex()
    for _ in range(2):
        post(c, sid2, 1, "ModuleNotFoundError: no module named app")
    rc, msg = pre(c, sid2)
    check("real failures are still reported as failures",
          "already failed 2 times" in msg, repr(msg[:100]))


def coach(cmd, sid, exit_code=0, stderr="", stdout=""):
    e=dict(os.environ)
    p=subprocess.run([sys.executable, os.path.join(HOOKS,"coach.py")],
        input=json.dumps({"session_id":sid,"hook_event_name":"PostToolUse",
            "tool_name":"Bash","tool_input":{"command":cmd},
            "tool_response":{"exit_code":exit_code,"stderr":stderr,"stdout":stdout,"interrupted":False}}),
        capture_output=True,text=True,env=e)
    try: return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
    except Exception: return None


def test_coach():
    """v1.2: live coaching via PostToolUse additionalContext. Found needed by
    A/B testing -- interrogation probes exit 0 with useless output, so the
    blocking guard (failure-gated) never fires on real thrash."""
    print("\n[10] coach -- live nudges without blocking")
    sid = "coach-" + os.urandom(4).hex()
    c = "zsh -c 'compinit probe number one lets-cl'"
    n1 = coach(c, sid); n2 = coach(c, sid)
    check("no nudge on 1st or 2nd run", n1 is None and n2 is None)
    n3 = coach(c, sid)
    check("nudges on 3rd similar command even with exit 0",
          n3 is not None and "NAME step" in n3)
    n4 = coach(c, sid)
    check("nudges again on 4th", n4 is not None)
    n5 = coach(c, sid)
    check("stops after two nudges per approach (anti-noise cap)", n5 is None)

    sid2 = "coach2-" + os.urandom(4).hex()
    n = coach("zsh -c 'some totally new approach here'", sid2, 0,
              "_tags: can only be called from completion function")
    check("method-error nudge fires immediately",
          n is not None and "runtime context" in n)

    sid3 = "coach3-" + os.urandom(4).hex()
    n = coach("ls -la /tmp/workspace/project", sid3)
    check("ordinary first-time command gets no nudge", n is None)


def test_deliverable_checkpoints():
    """Motivated by the achilles benchmark: 84 succeeding probes, zero
    deliverables, 45 minutes gone. Succeeding commands must still trigger
    a bank-value nudge when nothing has been delivered."""
    print("\n[11] deliverable-banking checkpoints")
    import time as _t
    sid = "ckpt-" + os.urandom(4).hex()
    # simulate an old session start by pre-writing state with t0 in the past
    sys.path.insert(0, HOOKS)
    import sa_state as S
    st = S.load(sid); st["t0"] = _t.time() - 16 * 60; S.save(sid, st)
    n = coach("curl fetching remote endpoint alpha", sid, 0, "", "ok")
    check("fires bank-value nudge at 15m with zero deliverables",
          n is not None and "Bank" in n)
    n2 = coach("grep searching source tree beta", sid, 0, "", "ok")
    check("does not re-fire before the next checkpoint", n2 is None)

    st = S.load(sid); st["t0"] = _t.time() - 26 * 60; S.save(sid, st)
    n3 = coach("node evaluate widget internals gamma", sid, 0, "", "ok")
    check("fires second checkpoint at 25m", n3 is not None and "Bank" in n3)
    n4 = coach("python compute statistics delta", sid, 0, "", "ok")
    check("capped at two checkpoint nudges", n4 is None)

    sid2 = "ckpt2-" + os.urandom(4).hex()
    st = S.load(sid2); st["t0"] = _t.time() - 16 * 60; S.save(sid2, st)
    run_hook("coach.py", {"session_id": sid2, "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "tests/e2e/forms.spec.ts"},
        "tool_response": {"type": "text"}})
    n5 = coach("ls listing directory epsilon", sid2, 0, "", "ok")
    check("a real deliverable suppresses the nudge", n5 is None)

    sid3 = "ckpt3-" + os.urandom(4).hex()
    st = S.load(sid3); st["t0"] = _t.time() - 16 * 60; S.save(sid3, st)
    run_hook("coach.py", {"session_id": sid3, "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": ".playwright-cli/dp-experiment.js"},
        "tool_response": {"type": "text"}})
    n6 = coach("cat reading config zeta", sid3, 0, "", "ok")
    check("hidden-dir probe scripts do NOT count as deliverables",
          n6 is not None and "Bank" in n6)


def test_plan_gate():
    """v1.4 mission mode: brainstorm-then-plan as a mechanical gate, plus
    the 25-minute bank-or-justify escalation. Motivated by two 45-min runs
    captured by the hardest sub-problem with nothing delivered."""
    print("\n[12] mission-mode plan gate")
    import tempfile, time as _t
    ws = tempfile.mkdtemp(prefix="plangate-")
    env = {"SMALL_AGENTS_PLAN": "1"}
    def gate(tool, tin, sid="pg1", cwd=ws):
        return run_hook("plan_gate.py", {"session_id": sid,
            "hook_event_name": "PreToolUse", "cwd": cwd,
            "tool_name": tool, "tool_input": tin}, env)

    rc, msg = gate("Bash", {"command": "ls -la"})
    check("blocks Bash before PLAN.md exists", rc == 2 and "PLAN.md" in msg)
    rc, _ = gate("Edit", {"file_path": ws + "/foo.py"})
    check("blocks edits before PLAN.md", rc == 2)
    rc, _ = gate("Write", {"file_path": ws + "/PLAN.md"})
    check("writing PLAN.md itself is allowed", rc == 0)

    open(ws + "/PLAN.md", "w").write("## Goal\nx\n## Tasks\n- [ ] 1. a | deliverable: a.ts | verify: t\n- [ ] 2. b | deliverable: b.ts | verify: t\n")
    rc, _ = gate("Bash", {"command": "ls -la"})
    check("valid plan unlocks work", rc == 0)

    open(ws + "/PLAN.md", "w").write("just some prose")
    rc, _ = gate("Bash", {"command": "ls -la"})
    check("a structureless PLAN.md does not satisfy the gate", rc == 2)
    open(ws + "/PLAN.md", "w").write("## Goal\nx\n## Tasks\n- [ ] 1. a | deliverable: a.ts | verify: t\n- [ ] 2. b | deliverable: b.ts | verify: t\n")

    print("    25-minute bank-or-justify escalation")
    sys.path.insert(0, HOOKS)
    import sa_state as S
    sid = "pg-esc-" + os.urandom(4).hex()
    st = S.load(sid); st["t0"] = _t.time() - 26 * 60; S.save(sid, st)
    rc, msg = gate("Bash", {"command": "node probe.js"}, sid=sid)
    check("blocks Bash at 25m with zero deliverables", rc == 2 and "Bank" not in msg and "deliverable" in msg)
    rc, _ = gate("Bash", {"command": "node probe.js",
        "description": "INVESTIGATION: this decides which selector strategy the whole suite uses"}, sid=sid)
    check("INVESTIGATION justification passes", rc == 0)
    rc, _ = gate("Write", {"file_path": ws + "/spec.ts"}, sid=sid)
    check("edits (banking) are never escalation-blocked", rc == 0)
    st = S.load(sid); st["deliverables"] = 1; S.save(sid, st)
    rc, _ = gate("Bash", {"command": "node probe.js"}, sid=sid)
    check("a banked deliverable lifts the escalation", rc == 0)

    print("    off outside mission mode")
    rc, _ = run_hook("plan_gate.py", {"session_id": "pg2",
        "hook_event_name": "PreToolUse", "cwd": ws,
        "tool_name": "Bash", "tool_input": {"command": "ls"}}, {})
    check("inactive without SMALL_AGENTS_PLAN", rc == 0)


def test_strict_dispatch():
    """v1.5 rule 3: under SMALL_AGENTS_PLAN=2, after the plan exists the
    main session (agent_id null -- empirically measured) may only dispatch,
    edit PLAN.md, or run VERIFY: Bash; subagents (agent_id set) work
    freely."""
    print("\n[14] strict dispatch (PLAN=2)")
    import tempfile
    ws = tempfile.mkdtemp(prefix="strict-")
    open(ws + "/PLAN.md", "w").write("## Goal\nx\n## Tasks\n- [ ] 1. a | deliverable: a.ts | verify: t\n- [ ] 2. b | deliverable: b.ts | verify: t\n")
    env = {"SMALL_AGENTS_PLAN": "2"}
    def gate(tool, tin, agent_id=None):
        payload = {"session_id": "sd1", "hook_event_name": "PreToolUse",
                   "cwd": ws, "tool_name": tool, "tool_input": tin}
        if agent_id:
            payload["agent_id"] = agent_id
        return run_hook("plan_gate.py", payload, env)

    rc, msg = gate("Bash", {"command": "npx playwright test"})
    check("main-session Bash blocked", rc == 2 and "subagent" in msg)
    rc, _ = gate("Write", {"file_path": ws + "/tests/x.spec.ts"})
    check("main-session Write blocked", rc == 2)
    rc, _ = gate("Edit", {"file_path": ws + "/PLAN.md"})
    check("PLAN.md bookkeeping allowed", rc == 0)
    rc, _ = gate("Bash", {"command": "npx playwright test",
                          "description": "VERIFY: task 4 verification"})
    check("VERIFY: Bash allowed for the orchestrator", rc == 0)
    rc, _ = gate("Bash", {"command": "npx playwright test"}, agent_id="a812")
    check("subagent Bash works freely", rc == 0)
    rc, _ = gate("Write", {"file_path": ws + "/tests/x.spec.ts"}, agent_id="a812")
    check("subagent Write works freely", rc == 0)

    print("    PLAN=2 still enforces rule 1 (plan-first)")
    ws2 = tempfile.mkdtemp(prefix="strict2-")
    payload = {"session_id": "sd2", "hook_event_name": "PreToolUse",
               "cwd": ws2, "tool_name": "Bash", "tool_input": {"command": "ls"}}
    rc, msg = run_hook("plan_gate.py", payload, env)
    check("no plan -> plan block, not dispatch block", rc == 2 and "PLAN.md" in msg)


def test_dispatch_deadline():
    """90-min run regression: an inspection dispatch ran 73 minutes through
    two ignored advisory nudges. Past the hard deadline, every tool call in
    a subagent blocks -- the only possible act left is emitting the verdict."""
    print("\n[17] hard dispatch deadline")
    import tempfile, time as _t
    ws = tempfile.mkdtemp(prefix="ddl-")
    open(ws + "/PLAN.md", "w").write("## Tasks\n- [ ] 1. a | verify: t\n- [ ] 2. b | verify: t\n")
    env = {"SMALL_AGENTS_PLAN": "2"}
    sys.path.insert(0, HOOKS)
    import sa_state as S
    sid = "ddl-" + os.urandom(4).hex(); aid = "agent-77"
    def gate(tool, tin):
        return run_hook("plan_gate.py", {"session_id": sid, "agent_id": aid,
            "hook_event_name": "PreToolUse", "cwd": ws,
            "tool_name": tool, "tool_input": tin}, env)
    rc, _ = gate("Bash", {"command": "npx something"})
    check("fresh subagent works freely", rc == 0)
    st = S.load(sid); st["agents"][aid]["t0"] = _t.time() - 21 * 60; S.save(sid, st)
    rc, msg = gate("Bash", {"command": "npx something"})
    check("Bash blocked past deadline", rc == 2 and "deadline" in msg)
    rc, _ = gate("Write", {"file_path": ws + "/notes.md"})
    check("Write blocked past deadline too", rc == 2)
    rc, _ = gate("Edit", {"file_path": ws + "/PLAN.md"})
    check("even PLAN.md edits blocked in an overdue subagent", rc == 2)
    # main session unaffected by any of this
    rc, _ = run_hook("plan_gate.py", {"session_id": sid,
        "hook_event_name": "PreToolUse", "cwd": ws,
        "tool_name": "Bash", "tool_input": {"command": "ls",
        "description": "VERIFY: check"}}, env)
    check("orchestrator unaffected", rc == 0)


def test_deliverable_workspace_scoping():
    """Re-match #2 regression: /tmp probe scripts must not count."""
    print("\n[13] deliverables are workspace-scoped")
    import tempfile
    ws = tempfile.mkdtemp(prefix="scope-")
    sid = "scope-" + os.urandom(4).hex()
    def write(path):
        run_hook("coach.py", {"session_id": sid, "hook_event_name": "PostToolUse",
            "cwd": ws, "tool_name": "Write", "tool_input": {"file_path": path},
            "tool_response": {"type": "text"}})
    sys.path.insert(0, HOOKS)
    import sa_state as S
    write("/tmp/dp-probe-1.js")
    check("a /tmp write does not count",
          S.load(sid).get("deliverables", 0) == 0)
    write(ws + "/tests/forms.spec.ts")
    check("a workspace write counts",
          S.load(sid).get("deliverables", 0) == 1)


def test_plan_completion_stop_gate():
    """Re-match #4 regression: orchestrator ended at minute 36 with 5
    unchecked plan tasks, reporting a subagent as still running."""
    print("\n[15] mission-mode stop gate on unchecked plan tasks")
    import tempfile
    ws = tempfile.mkdtemp(prefix="landplan-")
    open(ws + "/PLAN.md", "w").write("## Tasks\n- [x] 1. done | verify: t\n- [ ] 2. pending | verify: t\n")
    env = {"SMALL_AGENTS_PLAN": "2"}
    sid = "lp-" + os.urandom(4).hex()
    def stop(msg, active=False):
        return run_hook("land.py", {"session_id": sid, "cwd": ws,
            "hook_event_name": "Stop", "stop_hook_active": active,
            "last_assistant_message": msg}, env)
    rc, msg = stop("Stage 2 inspection is actively running; ending here.")
    check("blocks ending with unchecked tasks", rc == 2 and "unchecked" in msg)
    rc, _ = stop("still going to stop", active=True)
    check("never fights an active stop hook", rc == 0)
    rc, _ = stop("attempt again")
    check("second block allowed", rc == 2)
    rc, _ = stop("third attempt")
    check("capped at two blocks (no infinite loop)", rc == 0)

    ws2 = tempfile.mkdtemp(prefix="landplan2-")
    open(ws2 + "/PLAN.md", "w").write("## Tasks\n- [x] 1. a | verify: t\n- [x] 2. b | verify: t\n")
    rc, _ = run_hook("land.py", {"session_id": "lp2", "cwd": ws2,
        "hook_event_name": "Stop", "stop_hook_active": False,
        "last_assistant_message": "all done"}, env)
    check("fully-checked plan ends freely", rc == 0)

    rc, _ = run_hook("land.py", {"session_id": "lp3", "cwd": ws,
        "hook_event_name": "Stop", "stop_hook_active": False,
        "last_assistant_message": "done"}, {})
    check("inactive outside mission mode", rc == 0)


def test_subagent_wrapup():
    """Re-match #5 regression: a dispatched subagent ran 30+ min of a 45-min
    budget. Subagent sessions (agent_id set) get wrap-up nudges at 10/15m."""
    print("\n[16] subagent wrap-up nudges")
    import time as _t
    sys.path.insert(0, HOOKS)
    import sa_state as S
    sid = "wrap-" + os.urandom(4).hex(); aid = "agent-123"
    st = S.load(sid)
    st["agents"] = {aid: {"t0": _t.time() - 11 * 60, "wrapups": 0}}
    S.save(sid, st)
    def sub_post(cmd):
        p = subprocess.run([sys.executable, os.path.join(HOOKS, "coach.py")],
            input=json.dumps({"session_id": sid, "agent_id": aid,
                "hook_event_name": "PostToolUse", "tool_name": "Bash",
                "tool_input": {"command": cmd},
                "tool_response": {"exit_code": 0, "stdout": "ok", "stderr": ""}}),
            capture_output=True, text=True)
        try: return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
        except Exception: return None
    n = sub_post("curl inspect live page alpha")
    check("nudges a subagent at 10 minutes", n is not None and "Wrap up" in n)
    n2 = sub_post("grep search results beta")
    check("no re-nudge before 15m", n2 is None)
    st = S.load(sid); st["agents"][aid]["t0"] = _t.time() - 16 * 60; S.save(sid, st)
    n3 = sub_post("node run analysis gamma")
    check("second nudge at 15m", n3 is not None)
    n4 = sub_post("python compute delta")
    check("capped at two", n4 is None)
    n5_p = subprocess.run([sys.executable, os.path.join(HOOKS, "coach.py")],
        input=json.dumps({"session_id": "wrap-main", "hook_event_name": "PostToolUse",
            "tool_name": "Bash", "tool_input": {"command": "ls listing files"},
            "tool_response": {"exit_code": 0, "stdout": "ok", "stderr": ""}}),
        capture_output=True, text=True)
    check("main session (no agent_id) unaffected", "Wrap up" not in n5_p.stdout)


def test_safety():
    print("\n[6] safety -- the harness must never wedge a session")
    sid = "safe-" + os.urandom(4).hex()
    c = "zsh -c 'dead end approach _command_names compinit'"
    for _ in range(3):
        post(c, sid, 1, "error: bad")

    rc, _ = pre(c, sid, env={"SMALL_AGENTS_DISABLE": "1"})
    check("SMALL_AGENTS_DISABLE=1 disables the guard", rc == 0)

    rc, _ = pre("ls", sid)
    check("single-token commands are never fingerprinted", rc == 0)

    for script in ("guard.py", "coach.py", "record.py", "land.py"):
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
        test_short_real_commands_are_fingerprinted()
        test_edit_resets_clock()
        test_block_message_is_truthful()
        test_coach()
        test_deliverable_checkpoints()
        test_plan_gate()
        test_strict_dispatch()
        test_plan_completion_stop_gate()
        test_subagent_wrapup()
        test_dispatch_deadline()
        test_deliverable_workspace_scoping()
        test_safety()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        print("failed: " + ", ".join(FAIL))
    sys.exit(1 if FAIL else 0)
