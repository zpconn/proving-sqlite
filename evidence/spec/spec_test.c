/* Native sanity test (not a proof): sqlite3VdbeSerialGet against ref_serial_get on random and boundary bytes. */
#include "sqlite3.c"
#include "spec/record_format.h"
#include <stdio.h>
#include <stdlib.h>
static u64 rs = 88172645463325252ULL;
static u64 rnd(void){ rs ^= rs << 13; rs ^= rs >> 7; rs ^= rs << 17; return rs; }
int main(void){
  unsigned char b[16]; Mem m; long checks = 0, bad = 0; u32 t; int k, it;
  u32 big[] = {12, 13, 126, 127, 128, 129, 1000001, 0x7ffffffe, 0x7fffffff, 0xfffffffe, 0xffffffff};
  for(it = 0; it < 2000000; it++){
    for(k = 0; k < 16; k++) b[k] = (unsigned char)rnd();
    if( it % 7 == 0 ){ b[0] = (it & 8) ? 0x7f : 0xff; b[1] = 0xf0 | (unsigned char)(it & 0xf); } /* NaN/inf region */
    if( it % 11 == 0 ) memset(b, (it & 16) ? 0xff : 0x00, 16);
    t = (it % 3 == 0) ? big[it % 11] : (u32)(it % 140);
    memset(&m, 0xa5, sizeof(m));
    sqlite3VdbeSerialGet(b, t, &m);
    checks++;
    if( !ref_serial_get(b, t, &m) ){ if( bad++ < 10 ) printf("mismatch t=%u flags=%x\n", t, m.flags); }
  }
  printf("%ld checks, %ld mismatches\n", checks, bad);
  return bad != 0;
}
