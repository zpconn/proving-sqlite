/*
** validation/repro/preupdate_old_overread.c (finding draft, ledger agent
** 2026-11-10).  Built natively against unmodified upstream/sqlite3.c:
**
**   gcc -g -O1 -fsanitize=address -DSQLITE_ENABLE_PREUPDATE_HOOK \
**       -I../../upstream preupdate_old_overread.c ../../upstream/sqlite3.c -lm
**
** A table row whose record is 2000 bytes: header {04, 9f 22, 01} (a
** 1995-byte blob, then a 1-byte integer), body 1995 + 1 bytes.  The repro
** changes the last serial type from 1 to 6 (8-byte integer) in the database
** image, so the header now claims 8 bytes at offset 1999 of a 2000-byte
** record.  A DELETE with a pre-update hook that calls sqlite3_preupdate_old
** makes sqlite3_preupdate_old copy the payload into sqlite3DbMallocRaw(db,
** 2000) and pass it, with no padding, to sqlite3VdbeRecordUnpack, which
** reads 7 bytes past the allocation (serialGet via sqlite3VdbeSerialGet).
** Argument "clean" skips the corruption (control: no report).
*/
/* F-002 draft, as campaign.py's fixed repro command builds it (orchestrator, 2026-11-11): the one option the
** overread needs, then SQLite itself, unmodified and first (it defines _GNU_SOURCE before any system header); the
** ledger agent's version linked sqlite3.c separately. */
#define SQLITE_ENABLE_PREUPDATE_HOOK 1
#include "sqlite3.c"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int nHook = 0;
static void hook(void *pArg, sqlite3 *db, int op, const char *zDb,
                 const char *zTab, sqlite3_int64 k1, sqlite3_int64 k2){
  sqlite3_value *v = 0;
  int rc;
  (void)pArg; (void)zDb; (void)k1; (void)k2;
  if( op!=SQLITE_DELETE || strcmp(zTab, "t")!=0 ) return;
  rc = sqlite3_preupdate_old(db, 1, &v);     /* column b */
  nHook++;
  printf("preupdate_old(b): rc=%d type=%d\n", rc, v ? sqlite3_value_type(v) : -1);
}

static void check(int rc, sqlite3 *db, const char *z){
  if( rc!=SQLITE_OK ){ fprintf(stderr, "%s: %s\n", z, sqlite3_errmsg(db)); exit(1); }
}

int main(int argc, char **argv){
  int bClean = argc>1 && strcmp(argv[1], "clean")==0;
  sqlite3 *db;
  unsigned char *img, *copy;
  sqlite3_int64 n, i;
  int nFound = 0;
  static const unsigned char hdr[4] = {0x04, 0x9f, 0x22, 0x01};

  check(sqlite3_open(":memory:", &db), db, "open");
  check(sqlite3_exec(db,
    "PRAGMA page_size=4096;"
    "CREATE TABLE t(a BLOB, b INTEGER);"
    "INSERT INTO t VALUES(zeroblob(1995), 7);", 0, 0, 0), db, "setup");
  img = sqlite3_serialize(db, "main", &n, 0);
  for(i=0; i+4<=n; i++){
    if( memcmp(img+i, hdr, 4)==0 ){
      nFound++;
      if( !bClean ) img[i+3] = 0x06;      /* serial type 1 -> 6 */
    }
  }
  printf("record headers found: %d; corrupted: %s\n", nFound, bClean ? "no" : "yes");
  if( nFound!=1 ){ fprintf(stderr, "expected one record\n"); return 1; }
  copy = sqlite3_malloc64(n);
  memcpy(copy, img, n);
  sqlite3_free(img);
  check(sqlite3_deserialize(db, "main", copy, n, n,
        SQLITE_DESERIALIZE_FREEONCLOSE|SQLITE_DESERIALIZE_RESIZEABLE), db, "deserialize");
  sqlite3_preupdate_hook(db, hook, 0);
  {
    int rc = sqlite3_exec(db, "DELETE FROM t WHERE rowid=1;", 0, 0, 0);
    printf("DELETE rc=%d (%s); hook calls=%d\n", rc, sqlite3_errmsg(db), nHook);
  }
  sqlite3_close(db);
  return 0;
}
