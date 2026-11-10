#include "sqlite3.c"
#include "contracts/sqlite3VdbeSerialTypeLen.h"
#include "contracts/sqlite3VdbeOneByteSerialTypeLen.h"

void harness_serial_type_len(void){
  u32 serial_type;
  /* SETUP */
  /* END SETUP */
  sqlite3VdbeSerialTypeLen(serial_type);
}

void harness_one_byte_serial_type_len(void){
  u8 serial_type;
  /* SETUP */
  /* END SETUP */
  sqlite3VdbeOneByteSerialTypeLen(serial_type);
}
