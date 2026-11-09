# Does the measured waiting cost make any Appendix B cap too tight?

**No, so no new caps are proposed.** The reasoning, from measurements already in the repository:

1. **What waiting costs now.** Checkpoint 0's decision D measured one 15-minute wait under Codex (evidence/bringup/13-checkpoint0.md, D):
   - polled about once a minute (the pilot's way), it cost 748,078 tokens over 36 model calls;
   - waited once in a blocking `write_stdin` (the way builders now wait: builder §2.9, campaign.py's LONG_RUN_CODEX), it cost 36,925 tokens over 2 calls.

   So a run that outlasts the 1 s first yield now costs one extra model call, whatever its length. Every `make prove` does outlast it: C-01 takes 127 s on three configurations.
2. **What a model call costs.** The pilot's builder sessions (evidence/tokens.csv, with item counts from their stream logs):

   | Session | Card, round | Tokens | Model items | Tokens per item |
   |---|---|---|---|---|
   | J0001 | C-01, round 1 | 2,410,820 | 51 | 47,000 |
   | J0007 | C-01, round 2 | 1,313,598 | 38 | 35,000 |
   | J0003 | C-02, round 1 (resumed after J0002 was killed) | 761,490 | 21 | 36,000 |

   One wait is therefore about 35k–50k tokens early in a session. It grows with the context, to perhaps 150k late in a long high-tier session.
3. **What that adds per card.** Suppose a standard card makes about 20 long runs and a high card about 40:
   - a 5M standard card: 20 × 50k ≈ 1M, that is 20% of the cap;
   - a 10M–20M card: about 1M, 5–10%;
   - a 60M–80M high card: 40 × 150k ≈ 6M, 8–10%.

   Under the pilot's polling, the same high card would have paid about 750k per 15-minute run, roughly 30M for 40 such runs, which C-19 and C-20's 30M caps could not absorb. Decision D removed that.
4. **The pilot already paid more than this.** The pilot ran before decision D, so its builders polled. C-01 still used 3.72M builder tokens over two rounds against its 10M cap, and C-02 used 1.10M (J0002 and J0003). Waiting now costs less than it did in those numbers, which fit their caps with room (37% and 11%). Waiting adds nothing the pilot didn't already pay.

**One card to watch, for a reason other than waiting:** C-18 (sqlite3VdbeRecordCompare, 5M). It is a one-line wrapper, but its contract has to state sqlite3VdbeRecordCompareWithSkip's requires for bSkip = 0, and C-17's contract may be large. A builder reports STUCK at 80%, which is 4M, about one C-01 round plus a short second. If C-17's contract turns out large, raising C-18 to 10M before it starts would be reasonable. That is Zach's call under GOAL.md §0.3 (Appendix B is in GOAL.md), and nothing here changes it.
