# Tool issues

Defects or surprising behaviour in a tool or library, hit by the orchestrator, a builder or a reviewer (Zach, 2026-11-10). Each entry gives the tool and version, what happened, a minimal repro or its path, the effect on the campaign, and the workaround. Nothing here is reported upstream.

## T-001 CBMC 6.11.0: `--conversion-check` fails the exact minimum of a float-to-signed conversion

- **Tool:** CBMC 6.11.0 (cbmc-6.11.0), `--conversion-check`, as run by the `%float-to-int` pass (proofs/CHECKS, tools/prove.py).
- **What happened:** C-11's builder (round 1, 2026-11-10) found the float-to-int property for `y = (i64)r` at sqlite3IntFloatCompare 92434 failing on all three configurations, with r = −2^63 (0xc3e0000000000000). C11 6.3.1.4p1 defines that conversion: the result is INT64_MIN. CBMC's check reads `r > -9.223372e+18 && r < 9.223372e+18`. That fits a lower bound of −2^(w−1)−1 that rounds to −2^(w−1) in the floating type, compared strictly. This was measured, not read in CBMC's source.
- **Repro:** evidence/approvals/C-11-f2i-exact-min/toy.c, with `cbmc toy.c --function exact_min --conversion-check` (results in toy.txt).
  - False failures: (i64)(−2^63) and (int)(float)(−2^31).
  - Correct: double to 32-bit, the next double below −2^63, and 2^63.
  - So it rejects one defined input per conversion type and misses no UB.
- **Effect:** C-11 went to triage and was parked for Zach. C-17 to C-20 waited behind it.
- **Workaround** (Zach's decision, evidence/approvals/C-11-f2i-exact-min/APPROVED.md):
  - the harness assumes `r != -0x1p63`;
  - that input is argued in UB-CLASSES.md and tested natively;
  - TRUSTED.md records the imprecision;
  - RESULTS.md marks the function's rows "proved for every other (i, r); argued and tested at r = −2^63".

## T-002 LeakSanitizer (gcc 13.3.0): fails under ptrace in the Codex sandbox

- **Tool:** gcc 13.3.0's `-fsanitize=address` LeakSanitizer, inside codex-cli 0.166.0's workspace-write sandbox.
- **What happened:** C-11's builder (round 1) ran a native ASan/UBSan test in its sandbox. LeakSanitizer stopped the run because the sandbox runs commands under ptrace. With `ASAN_OPTIONS=detect_leaks=0` the same test ran clean (reports/C-11-b1.md, "Tested").
- **Repro:** any `-fsanitize=address` binary run by a Codex builder command; see C-11-b1.md.
- **Effect:** none on proofs. A builder's own native tests need `detect_leaks=0`. campaign.py's repro runner, which runs outside Codex, is not affected; a leak is not UB anyway (UB-CLASSES.md).
- **Workaround:** `ASAN_OPTIONS=detect_leaks=0` for native tests inside builder sessions.

## T-003 CBMC 6.11.0: a flexible array member's element is bounds-checked only where it starts

- **Tool:** CBMC 6.11.0, `--bounds-check` and `--pointer-check`, every option in proofs/CHECKS.
- **What happened:** C-16's builder (round 1, 2026-11-10, reports/C-16-b1.md) found that sqlite3VdbeFindCompare passes all 543 properties with a KeyInfo one byte short of SZ_KEYINFO(1). ASan, natively, reports the 8-byte read of `aColl[0]` at 93045 overflowing it. CBMC's property for `p->pKeyInfo->aColl[0]` tests the element's start offset against the object's size, not start + sizeof(CollSeq*). Its dereference check covers only the struct's fixed part.
- **Repro:** evidence/orchestrator/tool-issues/T-003/ (flex.c, rok.c, native.c; results.txt, native.txt).
  - **Missed:** `s->a[0]` and `s->a[k]` reads, and an `s->a[0]` write, of a flexible array element whose last byte is out of bounds.
  - **Caught:** the same element through a pointer (`void **pp = s->a; *pp`), a heap array `p[1]`, a struct member, a cast read at a byte buffer's end, and a flexible array with no element at all.
  - **Sound:** `__CPROVER_r_ok(s, n)` checks the whole range.
- **Effect:**
  - A proof whose requires states KeyInfo's footprint in whole entries, `r_ok(pKeyInfo, SZ_KEYINFO(n))`, is sound, and CBMC passes it.
  - CBMC can't show that one byte less fails (builder GOAL §2.4, reviewer checklist 3).
  - It would also pass a footprint short by part of an entry.
  - In scope only KeyInfo's aColl is indexed this way: sqlite3VdbeFindCompare 93045 (C-16), sqlite3VdbeRecordCompareWithSkip 92730 and 92736 (C-17). No merged card's proof indexes it.
- **Workaround** (orchestrator, cards C-16 and C-17):
  - KeyInfo footprints stay in whole entries;
  - minus one entry fails in CBMC (proved), and minus one byte overflows natively under ASan (tested);
  - the reviewer checks that every such footprint is whole entries.
  - the harness allocates the KeyInfo at exactly SZ_KEYINFO(n) bytes, never larger, so a read of aColl[n] starts out of bounds and CBMC catches it; NOTES.md shows that read fails (Zach's addition);
  - TRUSTED.md records the gap and both conditions (evidence/approvals/T-003-flexarray-bounds/APPROVED.md).

## T-004 tools/campaign.py (frozen at checkpoint 1): the selftest's `finish` kills the live campaign's daemon

- **Tool:** tools/campaign.py at proof.lock 4b851e7, with tmux 3.4 (Ubuntu 24.04).
- **What happened:** at 16:35 on 2026-11-10 I ran `tools/campaign.py selftest` to check an approved tool change (C-11). The selftest drives a scratch campaign started with `--no-tmux`, then runs its `finish`. `cmd_finish` always runs `tmux kill-session -t campaign` (campaign.py:2306), and that is also the live campaign's session name. It killed the live daemon. The detached jobs (J0039, J0040, J0041) carried on, and nothing was lost. `tools/campaign.py start` restarted the daemon at 16:37. The selftest's docstring says it "never touches a live campaign".
- **Repro:** start a campaign in tmux, then run `tools/campaign.py selftest`; `tmux ls` afterwards shows no session.
- **Effect:** the daemon was down for about 4 minutes and `wait` returned "campaign.py is not running". No session, merge or state was lost.
- **Workaround, until the fix is approved:**
  - run the selftest only as `env -u TMUX TMUX_TMPDIR=<scratch dir> tools/campaign.py selftest`, so its tmux calls reach another server;
  - or don't run it while a campaign runs.
- **Fix requested:** evidence/approvals/T-004-finish-tmux/. finish kills the session only if its own campaign was started in tmux, and the selftest uses its own tmux socket and checks that a session it didn't make survives.

## T-005 Codex service (codex-cli 0.166.0, gpt-6-astra): content filter stops a builder; campaign.py's resumes replay the flagged thread

- **Tool:** the Codex service behind codex-cli 0.166.0 (gpt-6-astra, xhigh), and tools/campaign.py's interruption handling.
- **What happened:** C-17's round 1 builder (J0058, 2026-11-10 18:43) read sqlite3VdbeRecordCompareWithSkip and the boundary contracts. Its last message: "The frozen collation contract permits any `int` result. SQLite negates that result for descending order, so `INT_MIN` may cause signed overflow. I'll check this path with CBMC and, if confirmed, test it against unmodified…". The next turn failed with `{"type":"error","message":"This content was flagged for possible cybersecurity risk. If this seems wrong, try rephrasing your request. If you're doing authorized security work that requires more cyber permissive safeguards, apply for Daybreak access via https://platform.openai.com/settings/organization/status-and-access before retrying."}` and exit 1.
  - campaign.py counted it as an interruption and resumed the same thread twice (J0059, J0060). Each was flagged at its first turn, so the card went to triage after "three interruptions".
- **Repro:** ../proving-sqlite-wt/state/jobs/J0058-builder/out.jsonl, J0059-builder, J0060-builder.
- **Effect:** C-17 lost round 1 (0.19M tokens). A resume of a flagged thread can never succeed, so the three-interruption rule spends the round on replays. The filter's message matches neither the usage-limit nor the auth-failure patterns.
- **Workaround:** `tools/campaign.py retry C-17`, which starts a fresh session in a new round, with no change to the prompt. I'm not rephrasing anything to get past the filter. If it is flagged again, the card is parked for Zach, since the message's remedy (Daybreak access) is an account decision.
- **Outcome:** round 2's fresh session (J0061, 18:49) was flagged after about 4 minutes, and its resumes (J0063, J0064) at once. C-17 was parked for Zach at 18:55 (PROGRESS.md, Open questions 1).
- **Possible fix (not requested yet):** campaign.py could treat this message as its own outcome, sending the card straight to triage instead of resuming. That is a frozen-file change.
- **Resolution** (Zach, 2026-11-10): for C-17 only, Claude builds and Codex reviews (evidence/approvals/C-17-vendor-exception/). If the Codex reviewer is flagged too, C-17 is parked again.

## T-006 CBMC 6.11.0 (DFCC loop contracts): a loop-carried pointer plus replaced calls blows up the encoding (confirmed)

- **Tool:** CBMC 6.11.0, `goto-instrument --dfcc` with `--apply-loop-contracts` and `--replace-call-with-contract`; MiniSat 2 and Z3 4.8.12.
- **What happened:** C-15's builder couldn't get a verdict on sqlite3VdbeRecordUnpack. In round 1, eight prove runs ran out of memory or timed out. In round 2 it reduced the problem to a 27-line toy with no SQLite code (reports C-15-b1.md, C-15-b2.md):
  - a loop that carries a pointer (`p == a+k` invariant, `++p`), with the pointer in the loop's assigns;
  - four calls to a replaced contract inside the loop;
  - this times out with 17.6 GiB RSS.
  - **Mechanism:** DFCC havocs the pointer through a write-set target into an unconstrained typed pointer. The invariant is assumed only afterwards, so every dereference and every replaced callee's havoc expands over all address-taken objects, DFCC's own write-set bookkeeping included.
  - **Controls:** the same toy with the pointer derived inside the iteration (`p = a+k`) verifies in about 1 s. With one call it verifies in 8 s.
  - **A rejected workaround:** framing the pointer as a byte slice shrinks the formula but falsely fails the callee's ensures right after the call.
- **Orchestrator's confirmation** (evidence/orchestrator/tool-issues/T-006/results.txt):
  - The DFCC results reproduce: control 1 s, one call 8 s, four calls no verdict in 300 s.
  - CBMC's legacy (non-DFCC) contracts path verifies the four-call toy in under 1 s and catches a planted false assertion, a wrong invariant and a missing assigns target.
  - A legacy contract can be attached by redeclaring an already-defined static function, and both replacement and enforcement work on that redeclaration.
- **Repro:** evidence/orchestrator/tool-issues/T-006/ (min4.c, min4-ctl.c, min1.c, run.sh; the legacy variants; redecl.c; both builder reports).
- **Effect:**
  - C-15 can't be proved under the frozen pipeline: SQLite's loop carries pMem, and the body can't change. C-15 is parked for Zach.
  - C-17's loop carries pRhs (`pRhs++`, 92803), so it will likely hit the same problem.
- **Workaround:** none within the frozen tools. Options are in evidence/approvals/T-006-dfcc-loop-pointer/README.md.

## T-007 tools/campaign.py (frozen at checkpoint 1): `land` can't carry tools/sessions.toml

- **Tool:** tools/campaign.py's `land_paths_problems`.
- **What happened:** on 2026-11-10 I tried to land C-17's vendor exception with two new model entries in tools/sessions.toml. The land was refused: "a land may touch only cards/, tests/repro/, evidence/approvals/, evidence/orchestrator/, PROGRESS.md, LEDGER.md, FINDINGS.md; this one touches tools/sessions.toml".
  - GOAL.md §0.3 exempts sessions.toml from proof.lock "because CLI flags change", so lock.py's EXEMPT keeps it out of the frozen list.
  - LAND_ALLOWED doesn't list it either. So no land can change it, with or without an approval record.
  - The daemon reads sessions.toml from main's checkout.
- **Repro:** change tools/sessions.toml on orch, commit, and run `tools/campaign.py land`.
- **Effect:** none on the campaign so far. The exception's models now come from the vendor's existing roles (VENDOR_ROLE in campaign.py), so sessions.toml stays unchanged. A real CLI flag change mid-campaign would need `stop`, a change to campaign.py, or `finish`.
- **Workaround:** keep sessions.toml unchanged during the campaign. If a CLI flag must change, ask Zach; the fix (sessions.toml in LAND_ALLOWED, or treated as frozen) is a frozen-file change.
