#include "sqlite3.c"
#include "contracts/sqlite3IsNaN.h"
#include "contracts/sqlite3IntFloatCompare.h"

void harness_sqlite3IsNaN(void){
  sqlite3_rtree_dbl x;
  int result;

  /* SETUP */
  /* END SETUP */

  result = sqlite3IsNaN(x);
}

void harness_sqlite3IntFloatCompare(void){
  i64 i;
  sqlite3_rtree_dbl r;
  int result;

  /* SETUP */
  /* END SETUP */

  result = sqlite3IntFloatCompare(i, r);
}
