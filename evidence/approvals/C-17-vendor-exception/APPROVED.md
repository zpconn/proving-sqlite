# Approval: C-17 builds on Claude and is reviewed on Codex (Zach, 2026-11-10)

Zach's answer, verbatim (PROGRESS.md Open questions, C-17, option (b)):

> C-17: option (b), for C-17 only. Claude builds and Codex reviews; record the ROLE_VENDOR change as a frozen-file approval with proof.lock. If the Codex reviewer is flagged too, park C-17 again. Don't rephrase anything to get past the filter. The INT_MIN negation at 92793 is a finding candidate: the builder settles it with a native repro on unmodified upstream, or a ledger statement with its justification.

## Why
The Codex service's content filter stopped C-17's builder in rounds 1 and 2: "flagged for possible cybersecurity risk" (evidence/orchestrator/tool-issues.md T-005).

## What changed
| File | Frozen | Change |
|---|---|---|
| tools/campaign.py | yes | See the list below. |
| cards/C-17.md | no | The decision; the INT_MIN finding candidate, to settle by repro or ledger statement; a pointer to T-006. |
| proof.lock | n/a | Rewritten for tools/campaign.py. |

The campaign.py changes:
- `CARD_ROLE_VENDOR = {'C-17': {'builder': 'claude', 'reviewer': 'codex'}}` beside ROLE_VENDOR, and `role_vendor(role, cid)`.
- `role_config(sess, role, tier, cid)` uses the card's vendor. It takes the model and effort that sessions.toml gives the vendor's own role at the card's tier (`VENDOR_ROLE`): Claude builds C-17 with roles.reviewer.high's model (claude-opus-5-5, high), and Codex reviews it with roles.builder.high's (gpt-6-astra, xhigh). Those are §0.10's models for each vendor at the high tier.
- **Why not new sessions.toml roles:** my first version added roles.builder-claude and roles.reviewer-codex, but `land` refused it. A land may not touch tools/sessions.toml, though proof.lock exempts it (T-007). So sessions.toml is unchanged.
- Vendor pauses are checked per card's vendor, also where a reviewer starts directly: after a builder's DONE or FINDING, and on a rerun after a discarded review. While reviewers were always on Claude those starts couldn't hit a Codex pause. The selftest's first run of this change caught one (C-06: a codex session started during the codex pause, the C-17 fixture's reviewer). Now the card waits in reviewing with no job, and the tick starts it after the pause.
- A builder on either vendor gets TMPDIR=tmp/ in its worktree.
- Builder and reviewer prompts fit the vendor: Claude may background long runs; Codex waits once and uses $TMPDIR. The exception is stated in the prompt.
- The selftest checks all of this:
  - C-17 only changes vendors;
  - its models are the vendor's own role's at the tier, and a sessions.toml that puts that role on the other vendor is refused;
  - the prompts fit their vendors;
  - the selftest's own C-17 fixture runs end to end with a claude builder and a codex reviewer.

The rule that a reviewer is never on its round's builder vendor is unchanged and still enforced: `_start_reviewer` and the merge check compare the job vendors.

## Tests
Tool tests and selftest (run under `env -u TMUX TMUX_TMPDIR=<scratch>`): `tool-tests.txt`, `selftest.txt`. They also cover T-004, which landed in the same land.
