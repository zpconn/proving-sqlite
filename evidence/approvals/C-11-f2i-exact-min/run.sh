#!/bin/sh
# Evidence for the C-11 approval request: native ASan/UBSan at r = -2^63, a positive control, and the CBMC toy.
D=$(dirname "$0")
U=/home/zpconn/code/proving-sqlite/upstream
cd "$D" || exit 1
cat > boundary.c <<'EOF'
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
EOF
cat > control.c <<'EOF'
/* Positive control: UBSan's float-cast-overflow flags the next double below -2^63. */
#include <stdio.h>
int main(void){ volatile double r = -0x1.0000000000001p63; long long y = (long long)r; printf("%lld\n", y); return 0; }
EOF
nice -n 10 cc -std=gnu11 -g -O1 -fsanitize=address,undefined,float-cast-overflow -fno-sanitize-recover=all \
  -I "$U" boundary.c -o boundary -lm -lpthread -ldl
nice -n 10 cc -std=gnu11 -g -O1 -fsanitize=undefined,float-cast-overflow -fno-sanitize-recover=all control.c -o control
{
  echo '$ ./boundary   (cc -fsanitize=address,undefined,float-cast-overflow, against upstream/sqlite3.c)'
  ASAN_OPTIONS=detect_leaks=0 ./boundary; echo "exit $?"
  echo '$ ./control'
  ./control; echo "exit $?"
} > native.txt 2>&1
: > toy.txt
for e in exact_min below_min top at_top f_exact_min i32_exact_min; do
  printf '%-14s ' "$e" >> toy.txt
  timeout 60 nice -n 10 cbmc t.c --function "$e" --conversion-check > "toy-$e.out" 2>&1
  grep -E 'VERIFICATION' "toy-$e.out" >> toy.txt
done
