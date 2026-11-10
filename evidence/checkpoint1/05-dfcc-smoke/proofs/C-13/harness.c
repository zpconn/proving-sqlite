#include "sqlite3.c"
void contract_sqlite3VdbeMemSetNull(Mem *pMem)
  __CPROVER_ensures(1);

void harness_sqlite3VdbeMemSetNull(void){
  Mem *pMem;
  /* SETUP */
  pMem = malloc(sizeof(Mem));
  /* END SETUP */
  sqlite3VdbeMemSetNull(pMem);
}
