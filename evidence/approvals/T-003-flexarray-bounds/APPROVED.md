# Approval: TRUSTED.md entry for CBMC's flexible-array bounds gap, with one addition (Zach, 2026-11-10)

Zach's answer, verbatim:

> T-003: the TRUSTED.md entry is approved, with one addition, in it and in C-16's and C-17's cards: whole-entry footprints are sound only if the harness allocates the KeyInfo at exactly SZ_KEYINFO(n) bytes (is_fresh or malloc of that size, never larger), so a read of aColl[n] starts out of bounds and CBMC catches it. The reviewer checks both, the whole-entry footprint and the exact allocation, and NOTES.md shows a read one entry past the end fails. Land it with its approval record and proof.lock, then retry C-16.

## What was applied
- **TRUSTED.md (frozen):** README.md's `patch.diff` entry, now with two conditions that the reviewer checks both of:
  1. footprints stated in whole elements;
  2. the KeyInfo allocated at exactly SZ_KEYINFO(n) bytes, never larger.

  It adds NOTES.md's read one element past the end, which must fail.
- **cards/C-16.md and cards/C-17.md:** the same addition.
- **proof.lock:** rewritten for TRUSTED.md.
