/* C-17 round 4, scratch: native random test past the CBMC bound. Unmodified upstream, ASan+UBSan.
   Each trial: nField in [1+bSkip, NMAX], random Mems (Int, IntReal, Real, Str, Blob, Blob|Zero, Null, random flags),
   random sort flags, KeyInfo at exactly SZ_KEYINFO(min(nField, nAllField)), record of random bytes at exactly
   max(nKey1, 10 + (bSkip != 0)) + 8 bytes (A-001 slack), string/blob buffers at exactly n bytes.
   Collations return values in [-1000, 1000] (F-001's INT_MIN is a known finding; excluded here). */
#include "sqlite3.c"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned long long rs = 88172645463325252ULL;
static unsigned rnd(void){ rs ^= rs << 13; rs ^= rs >> 7; rs ^= rs << 17; return (unsigned)rs; }
static int coll(void *p, int n1, const void *a, int n2, const void *b){
  int n = n1 < n2 ? n1 : n2, c = memcmp(a, b, n); (void)p;
  return c ? (c < 0 ? -1 - (int)(rnd() % 1000) : 1 + (int)(rnd() % 1000)) : n1 - n2; }
static const u16 kinds[] = { MEM_Int, MEM_IntReal, MEM_Real, MEM_Str, MEM_Blob, MEM_Blob|MEM_Zero, MEM_Null };
int main(int argc, char **argv){
  int trials = argc > 1 ? atoi(argv[1]) : 100000, NMAX = argc > 2 ? atoi(argv[2]) : 200, t, nonzero = 0, maxi = 0;
  CollSeq cs; memset(&cs, 0, sizeof cs); cs.enc = SQLITE_UTF8; cs.xCmp = coll;
  for(t = 0; t < trials; t++){
    int bSkip = rnd() & 1, nField = 1 + bSkip + (int)(rnd() % (NMAX - bSkip)), nAll = 1 + (int)(rnd() % (NMAX + 2));
    int nA = nField < nAll ? nField : nAll, i, j, nKey1;
    /* records: mostly well-formed-looking headers of small serial types, sometimes pure random bytes */
    nKey1 = (int)(rnd() % (4 * nField + 40));
    size_t ext = (size_t)(nKey1 > 10 + bSkip ? nKey1 : 10 + bSkip) + 8;
    unsigned char *rec = malloc(ext);
    for(j = 0; j < (int)ext; j++) rec[j] = (unsigned char)rnd();
    int deep = rnd() & 1, tail = (int)(rnd() % 4);
    if( deep ){ nKey1 = 1 + nField + 16; ext = (size_t)(nKey1 > 10 + bSkip ? nKey1 : 10 + bSkip) + 8;
      rec = realloc(rec, ext); for(j = 0; j < (int)ext; j++) rec[j] = (unsigned char)rnd(); }
    if( deep || rnd() % 4 ){ int h = 1 + nField; if( h < nKey1 && h < 128 ){ rec[0] = (unsigned char)h;
      for(j = 1; j < h; j++) rec[j] = deep && j <= nField - tail ? 0 : (unsigned char)(rnd() % 20); } }
    KeyInfo *ki = malloc(SZ_KEYINFO(nA));
    memset(ki, 0, SZ_KEYINFO(nA));
    ki->nAllField = (u16)nAll; ki->nKeyField = (u16)nAll; ki->enc = SQLITE_UTF8;
    ki->aSortFlags = malloc(nField);
    for(j = 0; j < nField; j++) ki->aSortFlags[j] = (u8)(rnd() % 4 == 0 ? rnd() & 3 : 0);
    for(j = 0; j < nA; j++) ki->aColl[j] = (rnd() & 1) ? &cs : 0;
    Mem *m = calloc(nField, sizeof(Mem));
    char **bufs = calloc(nField, sizeof(char*));
    for(j = 0; j < nField; j++){
      m[j].flags = (deep && j < nField - tail) ? MEM_Null : (rnd() % 16 == 0) ? (u16)rnd() : kinds[rnd() % 7];
      m[j].enc = SQLITE_UTF8;
      m[j].u.i = (i64)(((u64)rnd() << 32) | rnd()) >> (rnd() % 64);
      if( m[j].flags & MEM_Real ) m[j].u.r = (double)(int)rnd() / 7.0;
      m[j].n = (int)(rnd() % 12);
      bufs[j] = malloc(m[j].n ? m[j].n : 1);
      for(i = 0; i < m[j].n; i++) bufs[j][i] = (char)(rnd() % 3 ? 'a' + rnd() % 3 : rnd());
      m[j].z = bufs[j];
      if( (m[j].flags & (MEM_Str|MEM_Zero)) == MEM_Zero ) m[j].u.nZero = (int)(rnd() % 16);
    }
    UnpackedRecord *u = calloc(1, sizeof(UnpackedRecord));
    u->pKeyInfo = ki; u->aMem = m; u->nField = (u16)nField; u->default_rc = (i8)((int)(rnd() % 3) - 1);
    int rc = sqlite3VdbeRecordCompareWithSkip(nKey1, rec, u, bSkip);
    if( rc ) nonzero++;
    if( u->eqSeen && nField > maxi ) maxi = nField;
    for(j = 0; j < nField; j++) free(bufs[j]);
    free(bufs); free(m); free(ki->aSortFlags); free(ki); free(rec); free(u);
  }
  printf("trials=%d NMAX=%d nonzero=%d largest nField reaching the end=%d\n", trials, NMAX, nonzero, maxi);
  return 0;
}
