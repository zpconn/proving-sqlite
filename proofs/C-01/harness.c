#include "sqlite3.c"
#include "contracts/putVarint64.h"
#include "contracts/sqlite3PutVarint.h"

void harness_putVarint64(void){
  unsigned char output[9];
  u64 value;
  putVarint64(output, value);
}

void harness_sqlite3PutVarint(void){
  unsigned char output[9];
  u64 value;
  sqlite3PutVarint(output, value);
}
