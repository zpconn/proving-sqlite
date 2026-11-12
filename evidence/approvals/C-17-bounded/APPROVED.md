# Approved: C-17's bounded P1 and its tools (2026-11-11)

- **The auditor**, relayed by Zach: "C-17 package (wip/c17-pkg 644b754): OK to land after part 2. Verified: the patch applied to wip/part2 + orch dc02be4 gives the branch tree; lock PASS 60, scan PASS (all merged cards), -k c17 26/26, bounds 53/53, finding 1/1, legacy 21/21. The constant-input rule is a good addition."
- **The auditor's three fixes, made in the package** (README.md, "The auditor's OK"):
  - the aColl rule allows only malloc(sizeof(CollSeq)), and `c = 0` is refused;
  - C-17's card tells the reviewer to check that each symbolic allocation's size is the extent's local;
  - C-17's card tells the builder that the contract requires `bSkip == 0 || bSkip == 1`.
  patch.diff is wip/c17-pkg 5a5ee6a against wip/part2 1c0a4c9 merged with orch dc02be4, and patch-644b754.diff is the one approved.
- **Applied** on orch after part 2 landed (main fa63593, full gate PASS 3954 s). `git apply` was clean. The applied tools, TRUSTED.md, PROPERTIES.md, proofs/HOWTO.md and the C-17 to C-20 cards equal the branch's. Scan passes.
- **proof.lock** was rewritten after the commit: 60 files.
- **Next:** C-17's round 5 (legacy-unwind, K=8, 15 proofs), then Zach's item 7, a one-off measurement of C-15 on legacy-unwind.
