#include "sqlite3.c"
#include "contracts/serialGet.h"
#include "contracts/serialGet7.h"
#include <stdlib.h>

void harness_serialGet(void){
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

  serialGet(buf + offset, serial_type, mem);
  free(mem);
  free((void *)buf);
}

void harness_serialGet7(void){
  size_t extent, offset;
  const unsigned char *buf;
  Mem *mem;

  /* SETUP */
  __CPROVER_assume(extent <= 16 && offset <= extent);
  buf = malloc(extent);
  __CPROVER_assume(buf != 0);
  mem = malloc(sizeof(Mem));
  /* END SETUP */

  serialGet7(buf + offset, mem);
  free(mem);
  free((void *)buf);
}
