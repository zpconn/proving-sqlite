#include "sqlite3.c"
i64 contract_vdbeRecordDecodeInt(u32 serial_type, const u8 *aKey)
  __CPROVER_ensures(1);

void harness_vdbeRecordDecodeInt(void){
  u32 serial_type;
  const u8 *aKey;
  /* SETUP */
  aKey = malloc(8);
  /* END SETUP */
  vdbeRecordDecodeInt(serial_type, aKey);
}
