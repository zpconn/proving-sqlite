/* Boundary contract for sqlite3CorruptError (upstream/sqlite3.c:191373), replaced at its calls in C-17 (sqlite3VdbeRecordCompareWithSkip) and C-19 (vdbeRecordCompareString).
   Ledger: A-004. The clause below is LEDGER.md A-004's, word for word (scan.py checks it); written at
   checkpoint 1 and frozen in proof.lock. Builders do not change it. */
int contract_sqlite3CorruptError(int lineno)
  __CPROVER_assigns()
  __CPROVER_ensures(__CPROVER_return_value == SQLITE_CORRUPT);
