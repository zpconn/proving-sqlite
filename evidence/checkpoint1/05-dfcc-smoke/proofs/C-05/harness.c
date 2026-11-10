#include "sqlite3.c"
int contract_sqlite3VarintLen(u64 v)
  __CPROVER_ensures(1);

void harness_sqlite3VarintLen(void){
  u64 v;
  /* SETUP */
  /* END SETUP */
  sqlite3VarintLen(v);
}
