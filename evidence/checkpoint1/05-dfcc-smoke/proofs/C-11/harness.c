#include "sqlite3.c"
int contract_sqlite3IntFloatCompare(i64 i, double r)
  __CPROVER_ensures(1);

int contract_sqlite3IsNaN(double x)
  __CPROVER_ensures(1);

void harness_sqlite3IsNaN(void){
  double x;
  /* SETUP */
  /* END SETUP */
  sqlite3IsNaN(x);
}
void harness_sqlite3IntFloatCompare(void){
  i64 i;
  double r;
  /* SETUP */
  /* END SETUP */
  sqlite3IntFloatCompare(i, r);
}
