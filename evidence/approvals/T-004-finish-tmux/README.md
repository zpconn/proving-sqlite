# Approval request: tools/campaign.py, the selftest's finish kills the live campaign (2026-11-10)

**Status: approved in principle by Zach (2026-11-10); unapplied until he relays the auditor's OK on `patch.diff`** (GOAL.md §0.3, §3.2). Nothing waits on it.

**What happened** (evidence/orchestrator/tool-issues.md, T-004):
- At 16:35 I ran `tools/campaign.py selftest` to check the approved C-11 tool change, as a frozen tool change requires.
- The selftest's scratch campaign runs `finish` at its end. `cmd_finish` always runs `tmux kill-session -t campaign` (campaign.py:2306), which is the live campaign's session name, so it killed the live daemon.
- No session, merge or state was lost: the jobs are detached, and the journal reconciles. `tools/campaign.py start` restarted it at 16:37.
- The campaign itself was not stopped for this request, because the workaround below removes the risk.

**The patch** (`patch.diff`, tools/campaign.py only; proof.lock is rewritten when it is applied):
- `start` records in campaign state whether its daemon runs in tmux (`st.d['tmux'] = not a.no_tmux`).
- `finish` kills tmux session "campaign" only if its own campaign was started in tmux.
- The selftest gives its scratch campaign a tmux socket of its own (`TMUX_TMPDIR` under its base directory, `TMUX` unset). It starts a session named campaign there, runs finish, and checks the session survived.

**Tests:**
- With the patch: `RESULT selftest PASS 103/103` (`selftest-new.txt`), with the live campaign's tmux session still up afterwards.
- The control, the same selftest with finish's guard replaced by the old unconditional kill, fails the new check and only it: `RESULT selftest FAIL 102/103` (`selftest-control.txt`).
- Both runs were themselves started under `env -u TMUX TMUX_TMPDIR=<scratch>`, so they couldn't reach the live campaign either way.

**Workaround meanwhile:** I run the selftest only under `env -u TMUX TMUX_TMPDIR=<scratch dir>`.

**After the auditor's OK:** I apply `patch.diff` on orch with proof.lock, run the tool tests and the selftest (guarded), and land. The live state has no `tmux` flag until the next `start`. Until then `finish` leaves the session alone; it then shows "campaign.py daemon exited" and is harmless.
