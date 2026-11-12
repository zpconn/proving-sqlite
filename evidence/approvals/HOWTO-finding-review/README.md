# Approval request: part 2 after the T-015 follow-up: HOWTO's "Bounded proofs", TRUSTED.md's wording, and a finding-review role (2026-11-11)

**Status:** waiting for the auditor's OK on `patch.diff`, which Zach relays. Nothing is applied. The patch is the local branch `wip/part2` against `wip/t015-followup` de5bbda, the approved part 1. It lands after part 1 has landed and the daemon has restarted, once proofs/HOWTO.md is frozen (T-017; T-013).

| Change | Asked by | Frozen |
|---|---|---|
| **proofs/HOWTO.md gains "Bounded proofs".** It no longer copies evidence/approvals/C-15-bounded/HOWTO-bounded-proofs.md word for word: that text still said a bounded proof "allocates no fixed size except one object", like the docstring part 1 fixed. It now gives the two shapes, the size rule (each buffer as large as the largest extent) and the named tail terms. | Zach (T-017) | yes, after part 1 |
| **TRUSTED.md, T-015:** the check's conditions and reassignment rule. Its textual limit: a write through a member or an address the target depends on (`p->a = x` before a loop whose target is `p->a[0].x`, or `g(&p)`) is the legacy proof's reviewer's to find, and the auditor's note that it doesn't arise in C-17. | the auditor | yes |
| **campaign.py and sessions.toml: a `finding-review` one-off role** on Codex (gpt-6-astra, xhigh), writing only `reviews/finding-<n>.md`. Its fixed prompt judges F-002 from campaign.py's sandboxed run and control, and reproduces F-001-b as FINDINGS.md says, at -O2 and -O0 with controls, in $TMPDIR. | Zach: "one-off Codex session for F-002 and F-001-b now" | campaign.py yes; sessions.toml lands without approval, but its role has to match campaign.py's ROLE_VENDOR |
| tools/tests/test_tools.py `-k finding` | | yes |

The session itself is started with `tools/campaign.py session finding-review`, by the orchestrator, once this lands. It runs from a worktree of main, which by then holds evidence/orchestrator/F-002/, evidence/orchestrator/F-001-b/ and tests/repro/F-001-b.c.

## Results (wip/part2 783b050; proof.lock at 6248d88, 60 files)
- **Tool tests:** `RESULT tool-tests PASS 321/321`, including `-k finding`.
- **Selftest:** `RESULT selftest PASS 110/110`, run as `env -u TMUX TMUX_TMPDIR=<scratch>`; the live tmux sessions were intact.
- **lock check** on the branch: PASS, 60 files.
