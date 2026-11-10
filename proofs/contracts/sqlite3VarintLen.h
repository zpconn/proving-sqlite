#ifndef CONTRACT_SQLITE3VARINTLEN_H
#define CONTRACT_SQLITE3VARINTLEN_H

int contract_sqlite3VarintLen(u64 v)
  __CPROVER_assigns()
  __CPROVER_ensures(1 <= __CPROVER_return_value && __CPROVER_return_value <= 10);

#endif
