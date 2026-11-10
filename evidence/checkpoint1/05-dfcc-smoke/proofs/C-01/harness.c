#include "sqlite3.c"
int contract_putVarint64(unsigned char *p, u64 v)
  __CPROVER_ensures(1);

int contract_sqlite3PutVarint(unsigned char *p, u64 v)
  __CPROVER_ensures(1);

void harness_sqlite3PutVarint(void){
  unsigned char *p;
  u64 v;
  /* SETUP */
  p = malloc(9);
  /* END SETUP */
  sqlite3PutVarint(p, v);
}
void harness_putVarint64(void){
  unsigned char *p;
  u64 v;
  /* SETUP */
  p = malloc(9);
  /* END SETUP */
  putVarint64(p, v);
}
