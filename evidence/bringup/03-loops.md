# §1.3 Loop contracts (2026-11-08)

Rerun: `toys/03-loops/run.sh`; output `toys/03-loops/result.txt`. `proofs/include/proof.h` defines `PROOF(...)` as `__VA_ARGS__`.

- **while loop**, clauses `__CPROVER_assigns`, `__CPROVER_loop_invariant`, `__CPROVER_decreases` in that order, between header and body, applied by `goto-instrument --dfcc main --apply-loop-contracts`: the good contract passes, the false invariant fails `loop_invariant_step`, the non-decreasing measure fails `loop_decreases`. A write outside the loop's assigns fails `assigns`.
- **do-while loop:** clauses after the condition, as GOAL.md and builder §2.6 say, **do not parse** in CBMC 6.11 ("syntax error before '__CPROVER_assigns'"). Between `do` and the body they parse and are applied: the good contract passes, the false invariant and the non-decreasing measure each fail.
- A do-while invariant is checked before the first iteration (`loop_invariant_base`), so it must hold at the top of every iteration. An invariant that holds only after the body (`1 <= i`) fails.
- goto-synthesizer: not used. Contracts are inline, as the GOAL says.
- **GOAL.md correction:** builder §2.6's "after the condition, for a do-while" should read "between `do` and the body". scan.py enforces the working placement and names the reason.
