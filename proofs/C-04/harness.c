#include "sqlite3.c"
#include "contracts/sqlite3GetVarint32.h"
#include "contracts/sqlite3GetVarint.h"

void harness_separate(void){
  size_t input_extent, input_offset, output_extent, output_offset;
  const unsigned char *input;
  u32 *output;

  /* SETUP */
  __CPROVER_assume(input_extent <= 24 && input_offset <= input_extent);
  __CPROVER_assume(output_extent <= 24);
  __CPROVER_assume(output_offset <= output_extent / sizeof(u32));
  input = malloc(input_extent);
  output = malloc(output_extent);
  __CPROVER_assume(input != 0 && output != 0);
  /* END SETUP */

  sqlite3GetVarint32(input + input_offset, output + output_offset);
}

void harness_shared(void){
  size_t extent, input_offset, output_offset;
  void *storage;
  const unsigned char *input;
  u32 *output;

  /* SETUP */
  __CPROVER_assume(extent <= 24 && input_offset <= extent);
  __CPROVER_assume(output_offset <= extent / sizeof(u32));
  storage = malloc(extent);
  __CPROVER_assume(storage != 0);
  input = storage;
  output = storage;
  /* END SETUP */

  sqlite3GetVarint32(input + input_offset, output + output_offset);
  free(storage);
}
