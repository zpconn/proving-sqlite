/* §1.8.1 native probe: varint round trips through SQLite's own functions, unmodified upstream.
** Build: see run.sh. One TU with upstream/sqlite3.c so the static functions are callable. */
#include "sqlite3.c"
#include <stdio.h>
#include <stdlib.h>

static u64 rng = 0x9E3779B97F4A7C15ull;
static u64 next(void){ rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17; return rng; }

static long fails = 0;
static long nlen[11];
static long varintlen_mismatch_lt63 = 0, varintlen_ge63 = 0, varintlen_ge63_is10 = 0;

static void one(u64 v, int verbose){
  unsigned char buf[16];
  int k, n, n2, n3;
  u64 got;
  u32 g32 = 0;
  memset(buf, 0xA5, sizeof buf);
  n = sqlite3PutVarint(buf, v);
  if( n<1 || n>9 ){ fails++; printf("FAIL put n=%d v=%llu\n", n, (unsigned long long)v); return; }
  for(k=n; k<16; k++) if( buf[k]!=0xA5 ){ fails++; printf("FAIL put wrote byte %d beyond n=%d v=%llu\n", k, n, (unsigned long long)v); }
  /* decode from an exact-size heap copy, so ASan flags any read past the encoding */
  {
    unsigned char *h = malloc(n);
    memcpy(h, buf, n);
    n2 = sqlite3GetVarint(h, &got);
    if( n2!=n || got!=v ){ fails++; printf("FAIL get v=%llu n=%d -> n2=%d got=%llu\n", (unsigned long long)v, n, n2, (unsigned long long)got); }
    n3 = getVarint32(h, g32);
    if( n3!=n || g32!=(v<=0xffffffffull ? (u32)v : 0xffffffffu) ){
      fails++; printf("FAIL getVarint32 v=%llu n=%d -> n3=%d g32=%u\n", (unsigned long long)v, n, n3, g32);
    }
    free(h);
  }
  nlen[n]++;
  {
    int L = sqlite3VarintLen(v);
    if( v < (1ull<<63) ){ if( L!=n ){ varintlen_mismatch_lt63++; printf("VarintLen mismatch v=%llu L=%d n=%d\n", (unsigned long long)v, L, n); } }
    else { varintlen_ge63++; if( L==10 ) varintlen_ge63_is10++; }
    if( verbose ) printf("v=%-20llu 0x%016llx put n=%d get ok  getVarint32 n=%d v32=0x%08x  VarintLen=%d\n",
                         (unsigned long long)v, (unsigned long long)v, n, n3, g32, L);
  }
}

int main(void){
  int k;
  long i;
  u64 b[] = {0, 1, 0x7f, 0x80, 0x3fff, 0x4000, 0x1fffff, 0x200000, 0xfffffff, 0x10000000,
             0x7ffffffffull, 0x800000000ull, 0x3ffffffffffull, 0x40000000000ull, 0x1ffffffffffffull,
             0x2000000000000ull, 0xffffffffffffffull, 0x100000000000000ull, 0xffffffffull, 0x100000000ull,
             0x7fffffffffffffffull, 0x8000000000000000ull, 0xffffffffffffffffull};
  printf("== boundary values\n");
  for(k=0; k<(int)(sizeof b/sizeof b[0]); k++) one(b[k], 1);
  printf("== VarintLen at the three values GOAL.md names\n");
  printf("sqlite3VarintLen(2^63-1) = %d\n", sqlite3VarintLen(0x7fffffffffffffffull));
  printf("sqlite3VarintLen(2^63)   = %d\n", sqlite3VarintLen(0x8000000000000000ull));
  printf("sqlite3VarintLen(2^64-1) = %d\n", sqlite3VarintLen(0xffffffffffffffffull));
  printf("== 1000000 random values, bit length uniform in 0..64\n");
  for(i=0; i<1000000; i++){
    int bits = (int)(next() % 65);
    u64 v = bits==0 ? 0 : (bits==64 ? next() : (next() & ((1ull<<bits)-1)) | (1ull<<(bits-1)));
    one(v, 0);
  }
  printf("encoded lengths:"); for(k=1;k<=9;k++) printf(" n=%d:%ld", k, nlen[k]); printf("\n");
  printf("VarintLen != encoded length for v < 2^63: %ld\n", varintlen_mismatch_lt63);
  printf("values >= 2^63: %ld, of which VarintLen returned 10: %ld\n", varintlen_ge63, varintlen_ge63_is10);
  printf("round-trip failures: %ld\n", fails);
  return fails!=0;
}
