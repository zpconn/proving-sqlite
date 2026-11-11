# Approval: T-004, campaign.py's finish and tmux (Zach, relaying the auditor, 2026-11-10)

Zach's answer, verbatim:

> T-004: the auditor OKs patch.diff as written. Apply it with proof.lock, run the tool tests and the selftest (still under env -u TMUX TMUX_TMPDIR=<scratch>), and land with the approval record.

Applied: `patch.diff` exactly as written (tools/campaign.py), and proof.lock rewritten. It landed together with the C-17 vendor exception (evidence/approvals/C-17-vendor-exception/), so the tool tests and selftest named there cover both.
