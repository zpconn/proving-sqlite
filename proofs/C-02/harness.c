#include "sqlite3.c"

/* P2 is relational: all five functions execute their real bodies. */
void harness_roundtrip(void){
  u64 value;
  unsigned char buffer[9];
  unsigned char before[9];
  unsigned char *encoded;
  unsigned int extent;
  int n, i;
  u64 decoded64;
  u32 decoded32;
  u8 read64, read32;

  /* SETUP */
  __CPROVER_assume(extent >= 1 && extent <= 9);
  encoded = malloc(extent);
  __CPROVER_assume(encoded != 0);
  /* END SETUP */

  for(i=0; i<9; ++i) before[i] = buffer[i];
  n = sqlite3PutVarint(buffer, value);
  __CPROVER_assert(n >= 1 && n <= 9, "P2 encoded length is 1 through 9");
  for(i=0; i<9; ++i){
    if(i >= n){
      __CPROVER_assert(buffer[i] == before[i], "P2 suffix is unchanged");
    }
  }
  __CPROVER_assert(sqlite3VarintLen(value) ==
      (value < (((u64)1)<<63) ? n : 10), "P2 VarintLen including high-bit case");

  /* extent is independent of value: for every value there is a matching
  ** allocation. The branch selects it without assuming anything about bytes.
  ** Only the n encoder-produced bytes are available to either decoder. */
  if(extent == n){
    for(i=0; i<n; ++i) encoded[i] = buffer[i];
    read64 = sqlite3GetVarint(encoded, &decoded64);
    __CPROVER_assert(read64 == n, "P2 GetVarint length");
    __CPROVER_assert(decoded64 == value, "P2 GetVarint value");
    read32 = getVarint32(encoded, decoded32);
    __CPROVER_assert(read32 == n, "P2 getVarint32 length");
    __CPROVER_assert(decoded32 ==
        (value <= (u64)0xffffffff ? (u32)value : (u32)0xffffffff),
        "P2 getVarint32 value or saturation");
  }
  free(encoded);
}
