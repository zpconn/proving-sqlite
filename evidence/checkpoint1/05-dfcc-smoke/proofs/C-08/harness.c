#include "sqlite3.c"
void contract_serialGet(const unsigned char *buf, u32 serial_type, Mem *pMem)
  __CPROVER_ensures(1);

void contract_sqlite3VdbeSerialGet(const unsigned char *buf, u32 serial_type, Mem *pMem)
  __CPROVER_ensures(1);

void harness_sqlite3VdbeSerialGet(void){
  const unsigned char *buf;
  u32 serial_type;
  Mem *pMem;
  /* SETUP */
  buf = malloc(8);
  pMem = malloc(sizeof(Mem));
  /* END SETUP */
  sqlite3VdbeSerialGet(buf, serial_type, pMem);
}
