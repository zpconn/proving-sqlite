#include "sqlite3.c"
#include "contracts/serialGet.h"
#include "contracts/sqlite3VdbeSerialGet.h"
#include <stdlib.h>

void harness_serial_get(void){
  size_t extent, offset;
  const unsigned char *buf;
  Mem *mem;
  u32 serial_type;

  /* SETUP */
  __CPROVER_assume(extent <= 16 && offset <= extent);
  buf = malloc(extent);
  __CPROVER_assume(buf != 0);
  mem = malloc(sizeof(Mem));
  /* END SETUP */

  sqlite3VdbeSerialGet(buf + offset, serial_type, mem);
  free(mem);
  free((void *)buf);
}
