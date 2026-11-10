#include "sqlite3.c"
u8 contract_sqlite3GetVarint(const unsigned char *p, u64 *v)
  __CPROVER_ensures(1);

u8 contract_sqlite3GetVarint32(const unsigned char *p, u32 *v)
  __CPROVER_ensures(1);

void harness_sqlite3GetVarint32(void){
  const unsigned char *p;
  u32 *v;
  /* SETUP */
  p = malloc(9);
  v = malloc(sizeof(u32));
  /* END SETUP */
  sqlite3GetVarint32(p, v);
}
