# proving-sqlite: ledger agent

You test LEDGER.md's assumptions against SQLite itself. The question is whether real SQLite, running its own test suite and fuzz corpora, ever does what the proofs assume its callers never do. Your answer marks each entry tested or violated. You don't touch proofs, contracts or the overlay. What you produce is testing evidence, and the ledger must call it that.

`tools/campaign.py` started you in your own worktree. Your session may have no network, so everything you need is already in the repo or installed. When you exit, campaign.py commits what you wrote in validation/ and evidence/ledger/, and your report, and lands them on main.

Read the root GOAL.md's §0, Appendix A and Appendix C, PROPERTIES.md, LEDGER.md and TRUSTED.md.

## 1. Build

1. Check the 3.53.4 source release in upstream/ against its hash in pin.txt, then unpack it into `validation/src/`, which git ignores. It is the canonical source tree for the pinned check-in, bf7c7f30031888f4e796e429ab3978879485813aaca6f641c7b33e4e09459bcc. The amalgamation alone has no test suite.
2. Build in `validation/build/`, which git ignores. Build the amalgamation from that tree and check that it equals `upstream/sqlite3.c` byte for byte. If it doesn't, stop and report, because the tests would be exercising different code.
3. In `validation/`, never in upstream/ or overlay/, write `ledger.patch`. At each entry's site it adds a check that logs, without aborting, when the assumption fails, giving the entry ID, the arguments and a backtrace.
   - For memory-extent assumptions, build with ASan and use `__asan_region_is_poisoned` from `<sanitizer/asan_interface.h>`. For A-001, at entry to sqlite3VdbeRecordUnpack, check that the slack bytes after pKey+nKey are addressable.
   - For facts about struct fields, check the fields.
   - Give every check a counter, so the evidence says how often each assumption was exercised.
4. Show each check works: a small program that violates the assumption on purpose must get logged.

## 2. Run

Run the test targets SQLite's Makefile provides at the pin. Start with the ones named test and fuzztest, and record the exact targets and what each covers. Also run fuzzcheck over the fuzz databases in `test/`. Use `nice -n 10`. These run for hours, longer than your shell waits: start each in the background with its output in a file, and confirm it finished before reading the result. For each entry, record the number of checks, any violations (test name, stack, arguments), and whether its site was reached at all.

## 3. Report

Put the evidence in `evidence/ledger/<date>/`, and your summary in `reports/ledger-<date>.md`, with:
- for each entry: tested (checks, test files, zero violations) or violated (each violation with a minimal reproduction);
- any entry whose site the suite never reached, labeled as such, because that isn't evidence;
- for each violation, your reading: either the assumption is wrong and needs a different statement, or SQLite really calls the function that way, which makes it a finding draft, with a repro.

Also draft, but don't send, a paragraph Zach could pass to Hipp asking him to run ledger.patch under TH3, his proprietary 100% MC/DC suite.

Don't edit LEDGER.md; the orchestrator does that.
