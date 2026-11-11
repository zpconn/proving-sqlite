# Landing B2 in two parts (2026-11-11)

The auditor OK'd `patch.diff` at wip/b2-memcmp ab697bd. Landed whole, it was refused by the land job (J0088): "a land may touch only cards/, … this one touches proofs/contracts/memcmp.h, tools/sessions.toml". The land job runs main's campaign.py and lock.py, so it judges a change to the land rules by the old rules (T-013). So the approved patch lands in two parts. **The end state is `patch.diff` exactly, and each part is a subset of it:**

- **Part A:** tools/lock.py (memcmp.h added to FROZEN), and campaign.py's land rules: tools/sessions.toml in LAND_ALLOWED, `sessions_toml_changes` naming the keys a land changes in its trailer, and the comment. With proof.lock for that tree (57 files), which repairs main's (T-006's 19 fixtures). Allowed by today's rules: frozen files, with this approval record and proof.lock.
- **Part B:** the rest of `patch.diff`:
  - proofs/contracts/memcmp.h and LEDGER.md A-006;
  - scan.py's and prove.py's clause guards;
  - campaign.py's `--tools` allowlist and its checks, with tools/sessions.toml's matching command lines;
  - TRUSTED.md and the tests;
  - proof.lock (58 files).

  Allowed by part A's rules.

**The daemon:**
- **After part A,** it restarts onto the new land rules (T-008). sessions.toml still matches campaign.py's command lines, so it starts.
- **For part B,** it is stopped while the land job runs. The job fast-forwards main itself (`ff_main`). That way no session starts between part B reaching main and the daemon loading part B's command lines. Then it restarts, and C-15's reviewer, and every later Claude session, starts with `--tools`.
