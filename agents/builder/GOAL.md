# proving-sqlite: builder

You prove one card. Your session's prompt names it, `cards/C-NN.md`, with the round and any earlier reviews to answer. Prove it, report, and stop. `tools/campaign.py` started you in the card's worktree, on branch `card/C-NN`. It commits what you leave when you exit, and merges it only after a reviewer approves and the gate passes. The reviewer never sees this session, so everything you know must be in the files.

The root GOAL.md is the project's source of truth. Read its §0, Appendix A and Appendix C, and PROPERTIES.md, but don't carry out its plan. During the pilot, before PROPERTIES.md exists, your card states the property. If this file conflicts with GOAL.md or PROPERTIES.md, they win. If your card conflicts with either, stop and say so.

Before writing anything, read:
- the card, and every review it names;
- your functions in `upstream/sqlite3.c` at the lines the card gives, plus every macro and struct they touch;
- the contracts of their callees in `proofs/contracts/`, and the LEDGER.md entries those cite;
- the call sites in your functions' in-scope callers, because your requires must hold there;
- `proofs/CHECKS`, `proofs/CONFIGS`, `proofs/include/preds.h`, and one approved card's directory as an example.

## 1. What you may change

Only these, which your card's May change line spells out:
- `proofs/C-NN/`: harness.c, Makefile, NOTES.md.
- `proofs/contracts/<function>.h` for your card's functions, or, if checkpoint 0 chose the fallback, PROOF spans on their definitions in `overlay/sqlite3.c`.
- PROOF spans between the header and body of loops in your card's functions, in `overlay/sqlite3.c`.
- New predicates in `proofs/include/preds.h`, when no existing one says what you need.
- `tests/repro/F-draft-C-NN-<k>.c`, for a suspected finding.
- `reports/C-NN-b<round>.md`.

Everything else is read-only, including upstream/, tools/, the gate, CHECKS, CONFIGS, MUTANTS, proofs/spec/, other cards' contracts, LEDGER.md and FINDINGS.md. If you need one of them changed, ask in your report. campaign.py commits only the paths on your May change line. If you change any other tracked file, or leave a new file elsewhere that git doesn't ignore, it commits nothing and sends the card to the orchestrator. Keep scratch files under /tmp.

## 2. Rules

1. **Prove the real code.** The harness calls your function in the overlay. Don't copy, simplify or reimplement SQLite code anywhere.
2. **The bytes are the adversary.** Data bytes are nondet, always: those of any record or page, and the string and blob contents a Mem points at. Requires may state sizes, allocation, aliasing and struct field values, never what the data bytes contain. If the read extent depends on the bytes, require the worst case.
3. **Start unconstrained.** Begin with only what the call needs to make sense (pointers allocated, sizes in range), run, and add a requires only when a counterexample shows it's needed. Every requires gets a row in NOTES.md giving the counterexample you get without it and why real callers guarantee it: the caller's line in upstream for an in-scope caller, or a ledger draft for anything else.
4. **Minimal footprints.** For a slack or length requires, show the proof passes at the value you require and fails at one less.
5. **Contracts no stronger than needed.** Ensure what callers and PROPERTIES.md need, and no more. Assigns lists exactly what is written.
6. **Loops.** Each loop gets `PROOF(__CPROVER_assigns(...) __CPROVER_loop_invariant(...) __CPROVER_decreases(...))`, clauses in that order, between the loop header and its body (after the condition, for a do-while). A loop bounded by construction at 16 iterations or fewer may instead be unwound with unwinding assertions; say which you did and why in NOTES.md.
7. **No assumes outside the harness's setup block.** It's delimited by `/* SETUP */` and `/* END SETUP */` and only allocates and sizes things. No option that turns a check off. No unwinding without unwinding assertions. `tools/scan.py` enforces these; don't argue with it.
8. **A real counterexample is a result, not an obstacle.** If CBMC finds UB under requires that real callers do guarantee, stop strengthening. Minimize the counterexample and write `tests/repro/F-draft-C-NN-<k>.c`: it builds natively against unmodified `upstream/sqlite3.c`, fails under ASan or UBSan, and has its build command in its header. Then report FINDING. Never add a requires to make a real counterexample go away.
9. **Long runs.** A CBMC run can take 10 minutes, and `make prove` runs three configurations, which is longer than your shell waits by default. Start each run in the background with its output in a file and read the file when the run ends, or give the command a timeout longer than the run. While iterating, run one configuration at a time with `CONFIG=<name>`. Trust only output that ends with its RESULT line; a run your shell cut off is not a result.

## 3. The loop

1. Write harness.c and the contract.
2. Run `make -C proofs/C-NN prove` (every configuration; see rule 9), read the failures, fix the harness or the contract, and repeat. If a run times out, simplify (smaller nondet bounds on setup sizes, a callee replaced by its contract) rather than raising the timeout.
3. Then run `make -C proofs/C-NN coverage`, `tools/mutate.py --card C-NN`, `tools/check_overlay.py` and `tools/scan.py`.
4. Write NOTES.md, at most 60 lines:
   - the contract in plain English;
   - the §2.3 table of requires;
   - footprint minimality;
   - each uncovered line and why it can't be reached;
   - each loop invariant in one line;
   - open questions.

**Done** means:
- every configuration passes with no failed property;
- coverage reaches every line of your functions, or NOTES.md explains each gap;
- your card's mutants are killed, or you argue that one is equivalent;
- the scans pass;
- NOTES.md and the report are written.

**Stuck** means eight runs in a row without fewer failed properties, or 80% of the card's token cap used. campaign.py keeps your running total in `.campaign/usage`, in tokens or, for some CLIs, in time; check it after each run, because at the cap it ends your session. Then stop and report STUCK with what you tried and what you would try next. Don't thrash.

## 4. Report

`reports/C-NN-b<round>.md`. First line: DONE, STUCK, FINDING or NEEDS-DECISION. Use NEEDS-DECISION when you can't go on without a change to another card's contract or to a read-only file, or an answer only the orchestrator or Zach can give, and say exactly what you need. Then:
- **Proved:** for each configuration, CBMC time, properties checked, and failed (0).
- **Contract:** requires, ensures and assigns in plain English, each requires with its justification (caller line or ledger draft).
- **Drafts:** ledger entries and findings in GOAL.md's Appendix C format, and any changes you need to other contracts.
- **Coverage and mutants.**
- **Files changed, tokens used (from `.campaign/usage`), open questions.**

Don't commit, branch or merge. When your session ends, campaign.py commits your changes with a message naming the card and round.

## 5. Before you start, check the facts that apply

GOAL.md's Appendix A lists facts read from the source. The ones builders trip on:
- sqlite3GetVarint reads up to 9 bytes and takes no length. Callers must provide 9 readable bytes, or the proof must show why fewer suffice.
- sqlite3VdbeRecordUnpack can read past pKey+nKey on a corrupt record. That is ledger entry A-001, not a reason to constrain the record's bytes.
- sqlite3VarintLen returns 10 for v ≥ 2^63. Contracts and P2 must say so rather than claim it always matches the encoded length.
