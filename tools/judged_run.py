#!/usr/bin/env python3
"""Judged run: solo execution wrapped in the two gates that survived the
experiments — harness-run verification and an independent fresh-context
judge.

Extracted from a larger dispatch harness (ascent) after A/B testing showed
the dispatch machinery itself lost to plain solo execution on tasks that
fit one context (time p=0.0085, 21 runs), while these two gates repeatedly
earned their keep: the judge re-verified independently in 100% of observed
passes, deleted stale outputs before trusting them, and the one thing solo
never catches — a model confidently declaring success over a broken fix
(observed live: 11 turns, 60 seconds, wrong) — is exactly what this wrapper
exists to catch.

Usage:
  judged_run.py --goal "..." --verify-cmd "python3 check.py" \
      [--workspace DIR] [--model MODEL] [--attempts 2] [--plugin-dir DIR]

Exit 0 iff the verification passes AND the judge rules the solution viable.
The solver's word is never evidence: verification is executed by this
script, and the judge (a separate agent process, told nothing of the
solver's reasoning) re-runs it before ruling.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time


# ---------------------------------------------------------------- agents

def run_agent(prompt, workspace, tools, model, timeout, plugin_dir=None):
    cmd = ["claude", "-p", prompt, "--allowedTools", *tools.split(),
           "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    if plugin_dir:
        cmd += ["--plugin-dir", plugin_dir]
    p = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True,
                       timeout=timeout, stdin=subprocess.DEVNULL)
    raw = p.stdout
    i = raw.find("{")
    if i < 0:
        raise RuntimeError("no JSON envelope in agent output: %r" % raw[:200])
    return json.loads(raw[i:]).get("result") or ""


def extract_json(text):
    """Pull one JSON object out of a prose reply, repairing the pseudo-JSON
    shapes observed in real runs (single quotes, trailing commas)."""
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in reply")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                frag = text[start:i + 1]
                try:
                    return json.loads(frag)
                except json.JSONDecodeError:
                    frag = re.sub(r",\s*([}\]])", r"\1", frag)
                    frag = re.sub(r"([{,]\s*)'([^']*)'(\s*:)", r'\1"\2"\3', frag)
                    frag = re.sub(r"(:\s*)'([^']*)'(\s*[,}])", r'\1"\2"\3', frag)
                    return json.loads(frag)
    raise ValueError("unbalanced JSON in reply")


# ---------------------------------------------------------------- gates

def run_verification(verify_cmd, workspace, timeout=120):
    t0 = time.time()
    try:
        p = subprocess.run(verify_cmd, shell=True, cwd=workspace,
                           capture_output=True, text=True, timeout=timeout)
        return {"passed": p.returncode == 0, "exit_code": p.returncode,
                "output": (p.stdout + p.stderr)[-2000:],
                "seconds": round(time.time() - t0, 1)}
    except subprocess.TimeoutExpired:
        return {"passed": False, "exit_code": -1,
                "output": "verification timed out",
                "seconds": round(time.time() - t0, 1)}


JUDGE_PROMPT = """GOAL: Judge whether this goal has genuinely been achieved.

THE GOAL: {goal}

CLAIMED EVIDENCE: the harness ran `{verify_cmd}` and it exited
{exit_code} with output:
---
{output}
---

CONTEXT: You are an independent judge in a fresh context; the solver's
reasoning is deliberately not shown to you. Be skeptical: solvers sometimes
game verification (hardcoding expected output, weakening the check,
deleting tests) or solve a neighboring problem instead.

COMMANDS: In this directory: (1) re-run the verification command yourself
and confirm exit 0; (2) inspect the changed files and check they solve the
STATED goal in a way that would survive contact with reality — not a stub,
not hardcoded to the test, no tampering with the verification itself.

RETURN: JSON only as your final message:
{{"viable": true|false, "reverified": true|false, "reason": "<=3 lines"}}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--goal", required=True)
    ap.add_argument("--verify-cmd", required=True)
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--model", default=os.environ.get(
        "ANTHROPIC_DEFAULT_OPUS_MODEL"))
    ap.add_argument("--attempts", type=int, default=2)
    ap.add_argument("--solver-timeout", type=int, default=1500)
    ap.add_argument("--judge-timeout", type=int, default=420)
    ap.add_argument("--plugin-dir", default=None,
                    help="e.g. a checkout of small-agents, loaded into the "
                         "solver session")
    args = ap.parse_args()
    ws = os.path.abspath(args.workspace)

    history = ""
    for attempt in range(1, args.attempts + 1):
        print(f"[judged] attempt {attempt}: solver", flush=True)
        prompt = args.goal + (
            "\n\nYour work is checked by running:\n    " + args.verify_cmd +
            "\nin this directory; it must exit 0. Run it yourself before "
            "finishing — do not claim success without seeing it pass.")
        if history:
            prompt += "\n\nPRIOR ATTEMPT FAILED: " + history
        try:
            run_agent(prompt, ws, "Bash Read Write Edit Grep Glob",
                      args.model, args.solver_timeout, args.plugin_dir)
        except (RuntimeError, subprocess.TimeoutExpired,
                json.JSONDecodeError) as e:
            history = f"solver dispatch error: {e}"
            print(f"[judged]   solver error: {e}", flush=True)
            continue

        vr = run_verification(args.verify_cmd, ws)
        print(f"[judged]   harness verification: "
              f"{'PASS' if vr['passed'] else 'FAIL'} "
              f"(exit {vr['exit_code']}, {vr['seconds']}s)", flush=True)
        if not vr["passed"]:
            history = "verification failed: " + vr["output"][:300]
            continue

        print("[judged]   judge (fresh context)", flush=True)
        try:
            reply = run_agent(
                JUDGE_PROMPT.format(goal=args.goal,
                                    verify_cmd=args.verify_cmd,
                                    exit_code=vr["exit_code"],
                                    output=vr["output"]),
                ws, "Bash Read Grep Glob", args.model, args.judge_timeout)
            verdict = extract_json(reply)
        except Exception as e:
            verdict = {"viable": False, "reason": f"judge error: {e}",
                       "reverified": False}
        if verdict.get("viable"):
            print(f"[judged] PASS — judge: {verdict.get('reason','')[:120]}",
                  flush=True)
            return 0
        history = "judge rejected: " + str(verdict.get("reason", ""))[:300]
        print(f"[judged]   judge REJECTED: {verdict.get('reason','')[:120]}",
              flush=True)

    print(f"[judged] FAIL after {args.attempts} attempt(s): {history[:200]}",
          flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
