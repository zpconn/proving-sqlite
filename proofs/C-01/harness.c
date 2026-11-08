#include "sqlite3.c"
#include "contracts/putVarint64.h"
#include "contracts/sqlite3PutVarint.h"
#include <stdlib.h>

void harness_putVarint64(void){
  size_t extent, offset;
  unsigned char *output;
  u64 value;

  /* SETUP */
  __CPROVER_assume(extent <= 16 && offset <= extent);
  output = malloc(extent);
  __CPROVER_assume(output != 0);
  /* END SETUP */

  putVarint64(output + offset, value);
  free(output);
}

void harness_sqlite3PutVarint(void){
  size_t extent, offset;
  unsigned char *output;
  u64 value;

  /* SETUP */
  __CPROVER_assume(extent <= 16 && offset <= extent);
  output = malloc(extent);
  __CPROVER_assume(output != 0);
  /* END SETUP */

  sqlite3PutVarint(output + offset, value);
  free(output);
}
