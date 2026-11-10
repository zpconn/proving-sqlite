/* Tested, not proved: sqlite3IntFloatCompare at r = -2^63, the one input CBMC 6.11's float-to-int check rejects. */
#include "sqlite3.c"
#include <stdio.h>
int main(void){
  volatile double r = -0x1p63;
  static const i64 is[] = { 0, -1, 1, (-9223372036854775807LL - 1), -9223372036854775807LL, 9223372036854775807LL };
  int bad = 0;
  for(unsigned k = 0; k < sizeof(is)/sizeof(is[0]); k++){
    int c = sqlite3IntFloatCompare(is[k], r);
    int want = is[k] > (-9223372036854775807LL - 1) ? 1 : 0;
    printf("i=%lld r=%a compare=%d want=%d\n", (long long)is[k], r, c, want);
    bad |= c != want;
  }
  return bad;
}
