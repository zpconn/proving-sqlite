#include "sqlite3.c"
void contract_serialGet(const unsigned char *buf, u32 serial_type, Mem *pMem)
  __CPROVER_ensures(1);

int contract_serialGet7(const unsigned char *buf, Mem *pMem)
  __CPROVER_ensures(1);

void harness_serialGet(void){
  const unsigned char *buf;
  u32 serial_type;
  Mem *pMem;
  /* SETUP */
  buf = malloc(8);
  pMem = malloc(sizeof(Mem));
  /* END SETUP */
  serialGet(buf, serial_type, pMem);
}
void harness_serialGet7(void){
  const unsigned char *buf;
  Mem *pMem;
  /* SETUP */
  buf = malloc(8);
  pMem = malloc(sizeof(Mem));
  /* END SETUP */
  serialGet7(buf, pMem);
}
