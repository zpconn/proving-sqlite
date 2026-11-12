/* Boundary contract for sqlite3DbMallocRaw (upstream/sqlite3.c:32113), replaced at its calls in C-14 (sqlite3VdbeAllocUnpackedRecord, call at 92103).
   Ledger: A-002. The clause below is LEDGER.md A-002's, word for word (scan.py checks it); written at
   checkpoint 1 and frozen in proof.lock. Builders do not change it. */
void *contract_sqlite3DbMallocRaw(sqlite3 *db, u64 n)
  __CPROVER_assigns()
  __CPROVER_ensures(__CPROVER_return_value == NULL || __CPROVER_is_fresh(__CPROVER_return_value, n));
