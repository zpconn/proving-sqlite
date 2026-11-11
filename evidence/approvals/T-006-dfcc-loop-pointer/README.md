# Decision request: C-15 can't be proved under the frozen DFCC pipeline (T-006, 2026-11-10)

**Status: waiting for Zach. No patch yet:** the options change what *proved* rests on, so I'm asking for a direction before writing one. C-15 is parked. C-17 will likely need the same answer.

## The problem
- sqlite3VdbeRecordUnpack's loop advances `pMem` (92143 onwards) and calls four replaced contracts per iteration: sqlite3GetVarint32, sqlite3VdbeSerialGet, sqlite3VdbeSerialTypeLen and sqlite3VdbeMemSetNull.
- Under CBMC 6.11's DFCC loop contracts, a loop-carried pointer plus replaced calls makes the encoding explode. No run reaches a verdict: out of memory with SAT, a timeout with Z3.
- C-15's builder reduced this to a 27-line toy with no SQLite code, and I reproduced it.
- No harness, contract or allowed Makefile setting avoids it, because the pointer is carried in SQLite's own body. Evidence: evidence/orchestrator/tool-issues.md T-006 and evidence/orchestrator/tool-issues/T-006/.
- sqlite3VdbeRecordCompareWithSkip (C-17) carries `pRhs` the same way (92803).

## Options
1. **Recommended: CBMC's legacy (non-DFCC) contracts path, for the proofs that need it.**
   - **Evidence:** on the toy it verifies in under 1 s. It catches a planted false assertion, a wrong invariant and a missing assigns target. A contract can be attached to an already-defined static function by redeclaring it, and both replacement and enforcement work on that redeclaration.
   - **Changes needed:**
     - prove.py: a per-proof `<name>_CONTRACTS := legacy` that runs `--enforce-contract f` / `--replace-call-with-contract f` / `--apply-loop-contracts` without `--dfcc`. Each `contract_<fn>`'s clauses would be attached to a redeclaration of `<fn>`, generated mechanically from the frozen or approved header so the two can't diverge.
     - scan.py: rules for that mode.
     - TRUSTED.md: the legacy transformations.
     - Tool tests, plus §1.2/§1.3's toys rerun under legacy.
   - **What it costs:** a second contracts implementation in the trusted base. Bring-up chose DFCC (02-contracts.md); the legacy path is older, and its frame-condition checking differs, so the validation toys must cover assigns, loop invariants and decreases.
   - The patch is written only after a yes, then validated, then reviewed by you and the auditor before it lands.
2. **A bounded proof:** unwind the loop for records of at most K fields. This weakens P1 for C-15 and needs a PROPERTIES.md change. Not recommended.
3. **A newer CBMC:** if a release fixes DFCC's pointer havoc, every proof reruns under the new version. None is known, and there's no network to check.
4. **Leave C-15 unproved:** sqlite3VdbeRecordUnpack is then only *tested*, through the ledger agent, and C-15 stays parked.

C-17 can't start until you decide its separate question (Codex's content filter, T-005).
