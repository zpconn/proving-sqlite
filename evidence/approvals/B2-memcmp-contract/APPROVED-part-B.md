# B2 part B: the rest of the approved patch (2026-11-11)

The auditor's OK (APPROVED.md) covers `patch.diff` at wip/b2-memcmp ab697bd. Part A (lock.py, campaign.py's land rules) landed first, because the land job judges a land by main's rules (T-013; LANDING.md).

Part B makes these files equal to ab697bd's:
- LEDGER.md, TRUSTED.md and proofs/contracts/memcmp.h;
- tools/sessions.toml, tools/scan.py, tools/prove.py, tools/tests/test_tools.py, tools/campaign.py and tools/lock.py;
- proof.lock (58 files).

They were checked as `git diff wip/b2-memcmp -- <those paths>` = empty, with proof.lock byte for byte the approved one. The end state on main is `patch.diff` exactly.
