# Approval request: TRUSTED.md, CBMC's flexible-array bounds gap (2026-11-10)

**Status: unapplied, waiting for Zach** (GOAL.md §0.3). Nothing waits on it: C-16 was sent back with the workaround below.

**The gap** (evidence/orchestrator/tool-issues.md, T-003; toys and native run in evidence/orchestrator/tool-issues/T-003/):
- CBMC 6.11.0, with every option in proofs/CHECKS, checks an element of a flexible array member (`s->a[k]`) only where it starts.
- C-16's builder found that sqlite3VdbeFindCompare passes with a KeyInfo one byte short of SZ_KEYINFO(1). Natively, ASan reports a heap-buffer-overflow, READ of size 8 at 93045.
- `__CPROVER_r_ok` checks the whole range, so requires in whole entries are sound.

**What's wrong today:** TRUSTED.md says CBMC's model covers "the meaning of every check in proofs/CHECKS". That is untrue for this access form, and a proof could pass with a footprint short by part of an element.

**The patch** (`patch.diff`, TRUSTED.md only; it applies after the C-11 change, which adds the bullet it follows):
- It records the gap and the rule that makes proofs sound despite it: footprints over such arrays are stated in whole elements, and reviewers check that.
- It names the "minus one fails" evidence for those footprints: minus one element in CBMC (proved), minus one byte natively under ASan (tested).
- On a yes, I land it with proof.lock.

**Already done without approval** (non-frozen):
- cards/C-16.md and C-17.md state the rule and the evidence; the reviewer checks whole-entry footprints.
- C-16 went back for round 2.

**Recommendation:** approve. The alternatives are worse:
- a tool check (scan.py or prove.py) for whole-element footprints, which is hard to state generally;
- a CBMC with the gap fixed, which changes the trusted base, and none is known.
