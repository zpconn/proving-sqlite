#include "sqlite3.c"
#include "contracts/sqlite3VdbeMemSetNull.h"
#include <stdlib.h>

void harness_sqlite3VdbeMemSetNull(void){
  size_t extent, offset;
  Mem *cells;

  /* SETUP */
  __CPROVER_assume(extent <= 2 * sizeof(Mem));
  __CPROVER_assume(offset <= 1 && offset * sizeof(Mem) <= extent);
  cells = malloc(extent);
  __CPROVER_assume(cells != 0);
  /* END SETUP */

  sqlite3VdbeMemSetNull(cells + offset);
  free(cells);
}
