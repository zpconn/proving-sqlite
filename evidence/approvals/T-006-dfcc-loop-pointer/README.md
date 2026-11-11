# Decision request: C-15 can't be proved under the frozen DFCC pipeline (T-006, 2026-11-10)

**Status (22:55):** option 1 was approved in principle with five conditions, and the auditor reproduced min4.c. The patch is written on the local branch `wip/t006-legacy`, unapplied and unlanded. It waits for the auditor's OK on `patch.diff` (condition 5). See "The patch" at the end.

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

C-17's separate question (Codex's content filter, T-005) was decided on 2026-11-10: Claude builds it, Codex reviews it.

## The patch (wip/t006-legacy, 2026-11-10 22:55)

Written to Zach's five conditions:
1. **Opt-in per proof.** `<name>_CONTRACTS := legacy` in a card's Makefile, accepted only for the cards in prove.py's `LEGACY_CARDS` (C-15, C-17). Every other proof stays on DFCC, and an unknown value is refused.
2. **Generated, can't diverge.** At every build, prove.py writes a translation unit: harness.c, then each ENFORCE and REPLACE function redeclared with its `contract_<fn>` header's declaration, with only the name changed. A check confirms the copy matches the header token for token, and that the header has exactly one declaration. The build key includes the generated text, so a header edit always rebuilds, and a test shows one doing so. A legacy harness may carry no contract clauses of its own. The legacy engine can't read `contract_<fn>` itself ("Function 'two/contract_two' was not found"), which is why the clauses are copied.
3. **Validation toys** (tools/tests/legacy/, tool tests `-k legacy`, 20/20). Each named bad variant fails by its expected check and its good variant proves:
   - a replaced call forgets what it assigns ("Check ensures clause");
   - a callee assigning outside the loop's frame ("other->flags (assigned by the contract of reset) is assignable");
   - a write through an alias outside it ("Check that q->flags is assignable");
   - an invariant not preserved;
   - a wrong decreases;
   - a claim after the loop the invariant doesn't support;
   - an out-of-bounds write in the loop;
   - an out-of-bounds pointer to a replaced callee ("Check requires clause of reset");
   - T-003's flexible array with an exact allocation ("dynamic object upper bound");
   - aliased arguments to an `is_fresh` contract ("Check requires clause of two"), while separate ones prove.

   Also tested:
   - T-006's pattern (a loop-carried pointer, four replaced calls) proves;
   - globals start unconstrained;
   - T-012's static-local abort is reported by name, and its workaround proves.

   **The pass order is a soundness requirement:** replace, then loops, then enforce. With loops first, a replaced callee whose body is removed can write outside the loop's frame unchecked; the callee-frame toy passed that way in the prototype.
4. **TRUSTED.md** records the legacy engine as a second contracts implementation: for which proofs, what it is trusted to check, the pass order, the static-local rule, the validated cases, and that globals and T-003's gap behave as under DFCC (`flexgap.c` here).
5. **Landing:** only after Zach relays the auditor's OK on `patch.diff`, with proof.lock rewritten and this record.

**C-15's real function** (T-012; evidence/orchestrator/tool-issues/T-012/c15-results/, all runs capped):
- Replacing sqlite3VdbeSerialGet aborts the legacy enforce pass. That function has a static local, `aFlag` (92080).
- With its body kept, the patched prove.py takes C-15's real function through every step: 2,019 properties, 138 s of CBMC, inside prove.py's 12 GB cap. (Correction, 2026-11-11: the harness was round 1's, bounded to 64 record bytes and at most 4 fields, with separate allocations that weren't exact. The full domain gives no verdict; see T-014.) The verdict fails on the builder's unfinished round-2 contract, whose pKey footprint lacks A-001's +8.
- C-15's card now says to keep SerialGet's body.

**One part of condition 3 can't be met before landing: a planted bug in C-15's real proof.** That proof doesn't exist yet. Its builder can only write it once this patch is on main, and the current harness already fails, so a planted bug there would show nothing. Proposed instead: land the patch after the auditor's OK, then C-15's round 3. Before C-15 merges, its gate runs its own mutants M-050 and M-051 against that proof, and I also plant a bug by hand (`tools/mutate.py --adhoc` on the overlay) and show it caught. C-15 stays unmerged until both are shown.

