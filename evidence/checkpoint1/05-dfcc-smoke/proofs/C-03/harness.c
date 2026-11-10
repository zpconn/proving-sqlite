#include "sqlite3.c"
u8 contract_sqlite3GetVarint(const unsigned char *p, u64 *v)
  __CPROVER_ensures(1);

void harness_sqlite3GetVarint(void){
  const unsigned char *p;
  u64 *v;
  /* SETUP */
  p = malloc(9);
  v = malloc(sizeof(u64));
  /* END SETUP */
  sqlite3GetVarint(p, v);
}
