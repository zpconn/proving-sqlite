/* Boundary contract for memcmp (the C library; called at upstream/sqlite3.c:92739, 92767 and 92975), replaced at its
   calls in C-17 (sqlite3VdbeRecordCompareWithSkip) and C-19 (vdbeRecordCompareString).
   Ledger: A-006. The clause below is LEDGER.md A-006's, word for word (scan.py checks it); frozen in proof.lock
   (Zach, 2026-11-10, evidence/approvals/B2-memcmp-contract/). Builders do not change it. */
int contract_memcmp(const void *s1, const void *s2, size_t n)
  __CPROVER_requires(__CPROVER_r_ok(s1, n) && __CPROVER_r_ok(s2, n))
  __CPROVER_assigns()
  __CPROVER_ensures(-255 <= __CPROVER_return_value && __CPROVER_return_value <= 255);
