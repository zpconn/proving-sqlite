#include "sqlite3.c"
u8 contract_sqlite3VdbeOneByteSerialTypeLen(u8 serial_type)
  __CPROVER_ensures(1);

u32 contract_sqlite3VdbeSerialTypeLen(u32 serial_type)
  __CPROVER_ensures(1);

void harness_sqlite3VdbeSerialTypeLen(void){
  u32 serial_type;
  /* SETUP */
  /* END SETUP */
  sqlite3VdbeSerialTypeLen(serial_type);
}
void harness_sqlite3VdbeOneByteSerialTypeLen(void){
  u8 serial_type;
  /* SETUP */
  /* END SETUP */
  sqlite3VdbeOneByteSerialTypeLen(serial_type);
}
