#include "sqlite3.c"
RecordCompare contract_sqlite3VdbeFindCompare(UnpackedRecord *p)
  __CPROVER_ensures(1);

void harness_sqlite3VdbeFindCompare(void){
  UnpackedRecord *p;
  /* SETUP */
  p = malloc(sizeof(UnpackedRecord));
  /* END SETUP */
  sqlite3VdbeFindCompare(p);
}
