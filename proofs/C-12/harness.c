#include "sqlite3.c"
#include "contracts/isAllZero.h"
#include <stdlib.h>

void harness_isAllZero(void){
  size_t extent, offset;
  const char *input;
  int length;

  /* SETUP */
  __CPROVER_assume(extent <= 2147483647 && offset <= extent);
  input = malloc(extent);
  __CPROVER_assume(input != 0);
  /* END SETUP */

  isAllZero(input + offset, length);
}
