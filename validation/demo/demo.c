/*
** validation/demo/demo.c: show that each ledger.patch check logs a
** violation it is given on purpose, and stays quiet on a control.
** Built against the patched amalgamation (validation/build/lamal/sqlite3.c)
** by run_demos.sh, with and without ASan.  Usage: demo <case>.
** Each case prints what it did; run_demos.sh then checks the log.
*/
#include "sqlite3.c"
#include <stdlib.h>

static sqlite3 *openDb(void){
  sqlite3 *db = 0;
  if( sqlite3_open(":memory:", &db) ){ fprintf(stderr, "open failed\n"); exit(1); }
  return db;
}
static UnpackedRecord *newRecord(sqlite3 *db, int nField){
  KeyInfo *pKI = sqlite3KeyInfoAlloc(db, nField, 0);
  UnpackedRecord *p = sqlite3VdbeAllocUnpackedRecord(pKI);
  if( p==0 ){ fprintf(stderr, "alloc failed\n"); exit(1); }
  return p;
}

/* A-001 --------------------------------------------------------------- */
static void a001_control(void){
  sqlite3 *db = openDb();
  UnpackedRecord *p = newRecord(db, 2);
  unsigned char *buf = malloc(3+8);           /* 8 bytes of slack */
  memcpy(buf, "\x02\x01\x05", 3);
  sqlite3VdbeRecordUnpack(3, buf, p);
  unsigned char *buf0 = malloc(9);             /* nKey==0 needs 9 */
  memset(buf0, 0, 9);
  sqlite3VdbeRecordUnpack(0, buf0, p);
  printf("a001_control: nField=%u\n", p->nField);
}
static void a001_slack(void){
  /* Well-formed 3-byte record {hdr 2, type 1, value 5}, exact allocation:
  ** no slack.  The function reads nothing past it, but A-001 asks for 8. */
  sqlite3 *db = openDb();
  UnpackedRecord *p = newRecord(db, 2);
  unsigned char *buf = malloc(3);
  memcpy(buf, "\x02\x01\x05", 3);
  sqlite3VdbeRecordUnpack(3, buf, p);
  unsigned char *buf0 = malloc(4);             /* nKey==0, 4 < 9 */
  memset(buf0, 0, 4);
  sqlite3VdbeRecordUnpack(0, buf0, p);
  printf("a001_slack: nField=%u value=%lld\n", p->nField, (long long)p->aMem[0].u.i);
}
static void a001_overread(void){
  /* Bring-up's probe (evidence/bringup/08-probes.md): {0x02, 0x81} with no
  ** slack.  The check logs first; then ASan reports the real overread at
  ** the varint (built with -fsanitize-recover=address, halt_on_error=0). */
  sqlite3 *db = openDb();
  UnpackedRecord *p = newRecord(db, 2);
  unsigned char *buf = malloc(2);
  memcpy(buf, "\x02\x81", 2);
  sqlite3VdbeRecordUnpack(2, buf, p);
  printf("a001_overread: returned\n");
}
static void a001_negative(void){
  sqlite3 *db = openDb();
  UnpackedRecord *p = newRecord(db, 2);
  unsigned char *buf = malloc(64);
  memset(buf, 0, 64);
  buf[0] = 0x01;
  sqlite3VdbeRecordUnpack(-1, buf, p);
  printf("a001_negative: nField=%u\n", p->nField);
}

/* A-002 --------------------------------------------------------------- */
/* An allocator that breaks A-002's promise on purpose, only while a002Mode
** is set; otherwise it is the C library's. */
#include <malloc.h>
static int a002Mode = 0;   /* 1: misaligned by 4; 2: 16 bytes short */
static void *a002Bad = 0;  /* the one block handed out in a bad mode */
static void *a002Malloc(int n){
  if( a002Mode==1 ){
    char *p = malloc(n+16);
    a002Bad = p+4;
    return a002Bad;
  }
  if( a002Mode==2 ){
    a002Bad = malloc(n-16);
    return a002Bad;
  }
  return malloc(n);
}
static void a002Free(void *p){ if( p!=a002Bad ) free(p); }
static void *a002Realloc(void *p, int n){ return realloc(p, n); }
static int a002Size(void *p){
  if( p==a002Bad ) return a002Mode==2 ? 72 : 1000000;
  return (int)malloc_usable_size(p);
}
static int a002Roundup(int n){ return (n+7)&~7; }
static int a002Init(void *x){ (void)x; return 0; }
static void a002Shutdown(void *x){ (void)x; }
static void a002_run(int mode){
  sqlite3_mem_methods m = { a002Malloc, a002Free, a002Realloc, a002Size,
                            a002Roundup, a002Init, a002Shutdown, 0 };
  KeyInfo ki;
  UnpackedRecord *p;
  sqlite3_config(SQLITE_CONFIG_MALLOC, &m);
  sqlite3_initialize();
  memset(&ki, 0, sizeof(ki));
  ki.db = 0;               /* db==0: sqlite3DbMallocRaw goes to sqlite3Malloc */
  ki.nKeyField = 3;
  ki.nAllField = 3;
  a002Mode = mode;
  p = sqlite3VdbeAllocUnpackedRecord(&ki);   /* nByte = 40 + 4*sizeof(Mem) */
  a002Mode = 0;
  printf("a002 mode=%d: p=%p\n", mode, (void*)p);
}

/* A-003 --------------------------------------------------------------- */
/* A collation that writes into the strings it is given: it breaks A-003's
** "assigns at most *prcErr", from SQL alone. */
static int evilCmp(void *pUser, int n1, const void *z1, int n2, const void *z2){
  int n = n1<n2 ? n1 : n2;
  int rc = memcmp(z1, z2, n);
  (void)pUser;
  if( n1>0 ) ((char*)z1)[0] ^= 0;           /* write the same byte: no change */
  if( pUser && n2>0 ) ((char*)z2)[n2-1] = 'Z'; /* a real change */
  return rc ? rc : n1-n2;
}
static int honestCmp(void *pUser, int n1, const void *z1, int n2, const void *z2){
  int n = n1<n2 ? n1 : n2;
  int rc;
  if( n<0 ) n = 0;           /* the requires demo passes n = -1 */
  rc = memcmp(z1, z2, n);
  (void)pUser;
  return rc ? rc : n1-n2;
}
static void a003_sql(int bEvil){
  sqlite3 *db = openDb();
  char *zErr = 0;
  sqlite3_create_collation(db, "c", SQLITE_UTF8, bEvil ? (void*)db : 0,
                           bEvil ? evilCmp : honestCmp);
  sqlite3_exec(db,
    "CREATE TABLE t(x TEXT COLLATE c, y);"
    "CREATE INDEX ti ON t(x, y);"
    "INSERT INTO t VALUES('alpha',1),('bravo',2),('charlie',3),('delta',4);"
    "SELECT count(*) FROM t WHERE x>'b';", 0, 0, &zErr);
  printf("a003_sql evil=%d: %s\n", bEvil, zErr ? zErr : "ok");
}
static void a003_requires(void){
  /* Direct call to the C-17 call-site wrapper with pMem2->n = -1. */
  sqlite3 *db = openDb();
  UnpackedRecord *p = newRecord(db, 1);
  Mem m1, m2;
  CollSeq coll;
  u8 err = 0;
  unsigned char key[16] = {0x02, 0x13, 'a', 'b', 'c'};
  memset(&m1, 0, sizeof(m1)); memset(&m2, 0, sizeof(m2));
  memset(&coll, 0, sizeof(coll));
  coll.enc = SQLITE_UTF8; coll.xCmp = honestCmp; coll.zName = "honest";
  m1.enc = SQLITE_UTF8; m1.z = "abc"; m1.n = 3; m1.flags = MEM_Str;
  m2.enc = SQLITE_UTF8; m2.z = "abd"; m2.n = -1; m2.flags = MEM_Str;
  ledgerCompareMemStringA003(&m1, &m2, &coll, &err, 5, key, p);
  m2.n = 3;
  ledgerCompareMemStringA003(&m1, &m2, &coll, &err, 5, key, p);  /* control */
  printf("a003_requires: done\n");
}

/* A-004 --------------------------------------------------------------- */
static UnpackedRecord *a004Target = 0;
static void scribbleLog(void *pArg, int iErr, const char *zMsg){
  (void)pArg; (void)iErr; (void)zMsg;
  if( a004Target ) a004Target->r1 = 99;     /* changes caller-visible state */
}
static int wrongCorrupt(int lineno){ (void)lineno; return SQLITE_OK; }
static void a004_run(int mode){
  /* mode 0: control; 1: log callback writes pPKey2; 2: callee returns OK */
  sqlite3 *db;
  UnpackedRecord *p;
  unsigned char key1[8] = {0x05, 0x01, 0x01};   /* szHdr 5 > nKey1 1: corrupt */
  int rc;
  if( mode==1 ) sqlite3_config(SQLITE_CONFIG_LOG, scribbleLog, 0);
  db = openDb();
  p = newRecord(db, 1);
  p->aMem[0].flags = MEM_Int; p->aMem[0].u.i = 1; p->nField = 1;
  p->r1 = -1; p->r2 = 1;
  if( mode==1 ) a004Target = p;
  if( mode==2 ) ledgerCorruptErrorFn = wrongCorrupt;
  rc = sqlite3VdbeRecordCompareWithSkip(1, key1, p, 0);
  ledgerCorruptErrorFn = sqlite3CorruptError;
  printf("a004 mode=%d: rc=%d errCode=%d\n", mode, rc, p->errCode);
}

/* A-005 --------------------------------------------------------------- */
static void a005_run(int mode){
  /* mode 0: control, 9 bytes; 1: 1-byte heap buffer, v=5 (writes 1 byte);
  ** 2: 3-byte heap buffer, v=0x4000 (writes 3 bytes, goes to putVarint64);
  ** 3: stack array of 4, v=0x10000 at offset 1 */
  unsigned char stackBuf[4];
  unsigned char *b;
  int n = 0;
  switch( mode ){
    case 0: b = malloc(9); n = sqlite3PutVarint(b, 0xffffffffffffffffULL); break;
    case 1: b = malloc(1); n = sqlite3PutVarint(b, 5); break;
    case 2: b = malloc(3); n = sqlite3PutVarint(b, 0x4000); break;
    case 3: n = sqlite3PutVarint(stackBuf+1, 0x10000); break;
  }
  printf("a005 mode=%d: wrote %d\n", mode, n);
}

int main(int argc, char **argv){
  const char *z = argc>1 ? argv[1] : "";
  setvbuf(stdout, 0, _IONBF, 0);
  if( !strcmp(z,"a001_control") ) a001_control();
  else if( !strcmp(z,"a001_slack") ) a001_slack();
  else if( !strcmp(z,"a001_overread") ) a001_overread();
  else if( !strcmp(z,"a001_negative") ) a001_negative();
  else if( !strcmp(z,"a002_control") ) a002_run(0);
  else if( !strcmp(z,"a002_misaligned") ) a002_run(1);
  else if( !strcmp(z,"a002_short") ) a002_run(2);
  else if( !strcmp(z,"a003_control") ) a003_sql(0);
  else if( !strcmp(z,"a003_assigns") ) a003_sql(1);
  else if( !strcmp(z,"a003_requires") ) a003_requires();
  else if( !strcmp(z,"a004_control") ) a004_run(0);
  else if( !strcmp(z,"a004_assigns") ) a004_run(1);
  else if( !strcmp(z,"a004_rc") ) a004_run(2);
  else if( !strcmp(z,"a005_control") ) a005_run(0);
  else if( !strcmp(z,"a005_heap1") ) a005_run(1);
  else if( !strcmp(z,"a005_heap3") ) a005_run(2);
  else if( !strcmp(z,"a005_stack") ) a005_run(3);
  else { fprintf(stderr, "unknown case\n"); return 2; }
  return 0;
}
