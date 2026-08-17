# A/B experiment data

Raw per-run metrics (`results.jsonl`) and the rig that produced them.

- **Task**: reproduction of a real diagnostic failure — a zsh command on
  PATH that runs when typed in full but does not tab-complete
  (`unsetopt hash_list_all` in the workspace's `zdot/setup.zsh`; the fix
  must live in that file). The tempting approach — interrogating zsh's
  completion internals from a non-interactive shell — is impossible and
  errors identically every time.
- **Arms**: control = plain `lets-claude` (no plugin); harness = this
  plugin via `--plugin-dir`. Control was byte-identical across all batches.
- **Model**: Qwen3.8-27B (vLLM, 174k ctx) via lets-claude. 25-min cap/run.
- **Grading**: functional — `check.py` drives a real interactive zsh
  through a pty, presses TAB, and verifies both completion and execution.
  Transcript metrics (bash count, similar-command pairs, fix timing,
  blocks/hypotheses, landed verdict) via `grade.py`.
- **Batches**: v1 (4v4, delivery later found broken), v1.1 (6v6,
  SessionStart injection), v1.2 (8v8, + PostToolUse coach + dispatch).
  Treatment was repaired between batches; grading and control never
  changed. `analyze.py` computes exact Fisher / permutation Mann-Whitney.

Headline: pooled guaranteed-delivery versions (n=14/arm) — solved 10/14
vs 3/14, Fisher p=0.021; commands-to-working-fix MW p=0.011. All reps
(n=18/arm): solved p=0.007, commands p=0.007, fix-timing p=0.0008.
