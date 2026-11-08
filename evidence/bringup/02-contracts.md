# §1.2 Contracts on separate declarations (2026-11-08)

Rerun: `toys/02-contracts/run.sh`; output `toys/02-contracts/result.txt`.

- `--enforce-contract f/c` checks f against the clauses on a separate declaration c: with c true of f, VERIFICATION SUCCESSFUL (A); with c's ensures false of f, FAILED on `c_false.postcondition` (B).
- `--replace-call-with-contract f/c` replaces calls to f with c: a caller that needs more than a weak c fails (C), and passes without replacement (D). c's requires is checked at the call site (F).
- The same holds for a static function in another translation unit, through its `--export-file-local-symbols` name (H, I, J, K).
- Two `--enforce-contract` options in one DFCC run abort goto-instrument with an invariant violation, so a proof enforces one contract.
- **Choice:** contracts live in `proofs/contracts/<fn>.h` as `contract_<fn>` declarations, and SQLite's text gets only loop annotations. Proofs include the overlay as one translation unit (§1.6), so static functions keep their own names.
