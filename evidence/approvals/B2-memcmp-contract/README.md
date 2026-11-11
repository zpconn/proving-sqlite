# Approval request: memcmp's boundary contract (B2) and the changes bundled with it (2026-11-10)

**Status: waiting for the auditor's OK on `patch.diff`**, which Zach relays. Nothing is applied: the patch is on the local branch `wip/b2-memcmp`. Zach approved B2 itself (memcmp's contract) and asked for the smallest frozen change that lets its header land. The other items below are his, to go in the same change.

## What the patch does (`patch.diff`, 10 files, against orch after T-006)
| File | Frozen | Change |
|---|---|---|
| LEDGER.md | no | **A-006**, memcmp's boundary contract, in the Appendix C format. Its clause: `int contract_memcmp(const void *s1, const void *s2, size_t n) __CPROVER_requires(__CPROVER_r_ok(s1, n) && __CPROVER_r_ok(s2, n)) __CPROVER_assigns() __CPROVER_ensures(-255 <= __CPROVER_return_value && __CPROVER_return_value <= 255);`. The result's range is *assumed* from glibc and CBMC's model; C11 fixes only its sign. |
| proofs/contracts/memcmp.h | yes, newly | The clause word for word, with its `Ledger: A-006` line; scan.py's D2 check enforces the match. |
| tools/lock.py | yes | **The smallest change that lets the header land:** `proofs/contracts/memcmp.h` is added to FROZEN. That puts it in proof.lock, and makes `land` accept it, as a frozen file, only with an approval record and proof.lock in the same land. No other land rule changes for it. |
| tools/scan.py | yes | Rejects function contract clauses in proofs/include/ headers (preds.h). |
| tools/prove.py | yes | Every build fails if proofs/include/ carries a contract clause, or if a contracts header puts clauses on anything but a `contract_<name>` declaration (`header_clause_problems`). Under the legacy engine such a clause would attach to a SQLite function. All current headers pass. |
| tools/campaign.py | yes | **The Claude command lines** get `--disallowedTools WebFetch,WebSearch,RemoteTrigger,PushNotification,CronCreate,CronDelete,Workflow` (Zach, after T-011). command_problems refuses a Claude command without exactly that list, and the selftest gains two guard cases. **The T-007 fix:** `tools/sessions.toml` joins LAND_ALLOWED. Its command lines must equal campaign.py's anyway, so a land can change only its models and patterns. |
| tools/sessions.toml | no | The same `--disallowedTools` in the Claude start and resume lines. It lands now because of the T-007 fix. |
| TRUSTED.md | yes | The legacy entry: loop frames are checked against kept callee bodies too, and where clauses may sit. memcmp's library-model line: where C-17 and C-19 replace it with A-006, the model isn't used and the contract is *assumed*. |
| tools/tests/test_tools.py | yes | `-k b2`, 12 tests, below. |
| proof.lock | n/a | Rewritten: 58 files. |

## Evidence
- **Toys first, as Zach asked** (`toys.txt`, with `mc.c`, `mcl.c`, `kept.c`; all capped at 24 GB):
  - replacing memcmp with the contract proves for lengths up to 10^6 under both engines;
  - a call one byte past an argument fails by the contract's requires: "Check requires clause of contract contract::contract_memcmp for function memcmp" under DFCC, "Check requires clause of memcmp in f" under legacy;
  - without the replacement, CBMC's per-byte memcmp loop gives no verdict within 300 s;
  - a kept callee body writing outside a legacy loop's assigns fails by "Check that p->flags is assignable", inside the callee.
- **Tool tests `-k b2`, 12/12:**
  - memcmp's contract proves, and the r_ok violation fails, through prove.py under DFCC and legacy;
  - a clause smuggled into preds.h onto the ENFORCE function fails the build, and scan rejects it, under both engines;
  - a clause smuggled into a contracts header onto the REPLACE function (memcmp) fails the build, under both engines;
  - a kept callee body writing outside a legacy loop's assigns fails;
  - memcmp.h is frozen and lands only with an approval record and proof.lock;
  - tools/sessions.toml may land.
- **A real session with the new Claude command line** (Claude Code 2.1.322, through checkpoint 1's probe, with this branch's campaign.py): it started with 17 tools, the seven above gone, and replied normally.
- **Full tool tests:** 264/264 (`tool-tests.txt`). **Selftest:** 109/109 (`selftest.txt`), run as `env -u TMUX TMUX_TMPDIR=<scratch>`, with the live campaign's tmux session intact afterwards.

## After the auditor's OK
- Apply `patch.diff` on orch, rewrite proof.lock, add APPROVED.md, and land; the full gate runs.
- Then restart the daemon onto the new campaign.py (T-008).
- From then on, every Claude session runs without those seven tools, and C-17 and C-19 may REPLACE memcmp with `memcmp/contract_memcmp`.
- A-006 joins the ledger agent's second run, with every other entry that changed (Zach's §4 instruction).
