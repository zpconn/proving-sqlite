#include "sqlite3.c"
#include "spec/record_format.h"

/* P3 executes both SQLite bodies; no callee is replaced by a contract. */
void harness_serial_decode(void){
  u32 serial_type;
  size_t extent;
  const unsigned char *bytes;
  Mem decoded;

  /* SETUP */
  /* Size only: SETUP cannot call the reference, so check this expression
  ** against ref_serial_bytes after the call. No data byte is constrained. */
  extent = serial_type >= 1 && serial_type <= 4 ? serial_type :
           serial_type == 5 ? 6 :
           serial_type == 6 || serial_type == 7 ? 8 : 0;
  bytes = malloc(extent);
  __CPROVER_assume(bytes != 0 || extent == 0);
  /* END SETUP */

  sqlite3VdbeSerialGet(bytes, serial_type, &decoded);
  __CPROVER_assert(extent == ref_serial_bytes(serial_type),
                   "P3 allocation has exactly the reference read extent");
  __CPROVER_assert(ref_serial_get(bytes, serial_type, &decoded),
                   "P3 serial value agrees with the file-format reference");
}
