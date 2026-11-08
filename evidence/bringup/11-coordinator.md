# §1.11 Coordinator (2026-11-08)

`tools/campaign.py` (GOAL.md §3.1) and `tools/campaign.py selftest`, whose latest output is `11-selftest.txt` (31/31). The selftest builds a scratch repository of its own under /tmp: a copy of tools/ and agents/, fixture cards and a fake gate. It puts `tools/fakecli/` (fake `codex` and `claude` that emit each CLI's real event formats) first on PATH, and drives the real daemon with no tmux. It never touches a live campaign. What it shows:

- Approved and merged (C-01). A rejection whose second round answers the review, with the round-2 prompt naming `reviews/C-02-r1.md` (C-02). Three rejections go to triage (C-03).
- A crash resumed with the CLI's own resume command, in the same session (C-04). Three crashes in one round go to triage (C-05).
- A usage limit: the vendor is paused until the reset time it printed, no session starts on it meanwhile, the card's interruption count stays 0, and the card then merges (C-06).
- A builder that changes or commits a file outside May change goes to triage, and nothing is committed (C-07, C-08); so does a builder that writes its own review file (C-14). A reviewer that changes a tracked file is discarded and rerun once; the second time, the card goes to triage (C-09, C-10).
- A gate failure after APPROVE goes to triage, with main unchanged (C-11). A session at its cap is stopped, its allowed changes committed, and the card triaged (C-12).
- A card whose dependency isn't merged never starts (C-13). A reviewer on the builder's vendor is refused (C-15). A card branch that gains a commit after its review is never merged (C-16). An approved FINDING goes to triage, not merge (C-17).
- A land that touches proofs/ is refused. A land of PROGRESS.md lands on main with a trailer.
- kill -9 of the daemon mid-session: one start per session, nothing lost (C-21). kill -9 of the session itself: resumed in the same worktree (C-22). kill -9 of the daemon and the merge job mid-merge: the merge is redone exactly once (C-23). kill -9 of the daemon alone mid-merge: the surviving job's result is taken once (C-24).
- Every commit on main's first-parent history since start carries a `Campaign:` trailer. No reviewer ran on its round's builder vendor. No session saw the API-key or `CLAUDE_CODE_*` variables planted in campaign.py's environment. `finish` returns the primary checkout to main with orch merged.

Design notes for the auditor:
- **The merge path** (`do_merge`). In a scratch worktree at main's head, campaign.py checks that card/C-NN's head is exactly the review commit, whose parent is the approved commit, and that the review commit adds only `reviews/C-NN-rK.md`. It then runs `git merge --no-ff --no-commit`, checks every path against the card's May change line plus its reviews, commits with `Campaign:` and `Campaign-Merge:` trailers, and runs `make gate CARD=C-NN BASE=<main>`. On PASS it commits the results with a `Campaign-Step:` trailer and fast-forwards main only if main hasn't moved.
- **Idempotence.** A merge or land job's step id goes on main as `Campaign-Step: <id>`. After a crash, campaign.py looks for that trailer before redoing the job.
- **Detached jobs.** Sessions and merges run as `campaign.py _job <dir>` runners in their own sessions. Each writes `pid`, `child.pid`, `out.jsonl`, `err.log` and `exit.json` under `../proving-sqlite-wt/state/jobs/`, so a session outlives a restart of the daemon.
- **"Every commit on main carries a trailer"** holds for main's first-parent history. The commits a merge or land brings in as second parents are the builder's and review commits (made by campaign.py, with trailers) or orch commits (made by the orchestrator).
