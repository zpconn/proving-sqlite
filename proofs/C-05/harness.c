#include "sqlite3.c"
#include "contracts/sqlite3VarintLen.h"

void harness_sqlite3VarintLen(void){
  u64 value;

  /* SETUP */
  /* END SETUP */

  sqlite3VarintLen(value);
}
