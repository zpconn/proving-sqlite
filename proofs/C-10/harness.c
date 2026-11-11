#include "sqlite3.c"
#include "contracts/vdbeRecordDecodeInt.h"
#include <stdlib.h>

void harness_decode(void){
  size_t extent, offset;
  const u8 *input;
  u32 serial_type;

  /* SETUP */
  __CPROVER_assume(extent <= 16 && offset <= extent);
  input = malloc(extent);
  __CPROVER_assume(input != 0);
  /* END SETUP */

  vdbeRecordDecodeInt(serial_type, input + offset);
  free((void *)input);
}
