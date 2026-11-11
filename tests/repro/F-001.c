/* F-draft-C-17-1: signed overflow negating a collation's INT_MIN result for a DESC key
** (sqlite3VdbeRecordCompareWithSkip, upstream/sqlite3.c:92793, `rc = -rc;`).
**
** A collation's xCmp may return any negative int for "less" (sqlite3_create_collation
** documents only the sign). vdbeCompareMemString returns that value unchanged (92359), and
** for a DESC index column sqlite3VdbeRecordCompareWithSkip negates it. With INT_MIN the
** negation overflows (C11 6.5p5). Reached here from SQL: a table with a DESC index on a
** column that uses the collation holds 'a'; inserting 'b' makes the index b-tree seek
** compare the stored key 'a' (pKey1) with the new key 'b' (pPKey2): sqlite3BtreeIndexMoveto
** -> sqlite3VdbeRecordCompare -> sqlite3VdbeRecordCompareWithSkip, bSkip 0. The collation
** gives INT_MIN for 'a' < 'b', and aSortFlags[0] is KEYINFO_ORDER_DESC, so 92793 runs.
**
** Build (campaign.py's fixed command): cc -std=gnu11 -g -O1 -fsanitize=address,undefined
**   -I upstream tests/repro/F-draft-C-17-1.c, then run the binary. UBSan reports
**   "negation of -2147483648 cannot be represented in type 'int'" at sqlite3.c:92793.
** __ubsan_default_options makes UBSan stop at the first report, so the run exits nonzero. */
#include "sqlite3.c"
#include <limits.h>
#include <stdio.h>

const char *__ubsan_default_options(void){ return "halt_on_error=1:print_stacktrace=1"; }

/* Byte order, as BINARY does, but "less" is reported as INT_MIN. */
static int cmpIntMin(void *pUser, int n1, const void *z1, int n2, const void *z2){
  int n = n1<n2 ? n1 : n2;
  int r = memcmp(z1, z2, (size_t)n);
  (void)pUser;
  if( r==0 ) r = n1 - n2;
  return r<0 ? INT_MIN : (r>0 ? 1 : 0);
}

int main(void){
  sqlite3 *db = 0;
  char *zErr = 0;
  int rc = sqlite3_open(":memory:", &db);
  if( rc!=SQLITE_OK ){ fprintf(stderr, "open: %d\n", rc); return 2; }
  rc = sqlite3_create_collation(db, "intmin", SQLITE_UTF8, 0, cmpIntMin);
  if( rc!=SQLITE_OK ){ fprintf(stderr, "collation: %d\n", rc); return 2; }
  rc = sqlite3_exec(db,
      "CREATE TABLE t(x TEXT COLLATE intmin);"
      "CREATE INDEX t_x ON t(x DESC);"
      "INSERT INTO t VALUES('a');"
      "INSERT INTO t VALUES('b');",
      0, 0, &zErr);
  printf("exec rc=%d %s\n", rc, zErr ? zErr : "");
  sqlite3_free(zErr);
  sqlite3_close(db);
  return 0;
}
