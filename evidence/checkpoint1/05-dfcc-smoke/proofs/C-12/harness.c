#include "sqlite3.c"
int contract_isAllZero(const char *z, int n)
  __CPROVER_ensures(1);

void harness_isAllZero(void){
  const char *z;
  int n;
  /* SETUP */
  z = malloc(4);
  /* END SETUP */
  isAllZero(z, n);
}
