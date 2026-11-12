/* F-001, second repro: what the overflow at 92793 does in compiled code (the auditor's test, 2026-11-11; copied
** unchanged below this comment from the auditor's ref/f001/misorder.c).
**
** Build against unmodified upstream, with no sanitizers, at -O2 or -O0:
**   cc -std=gnu11 -O2 -I upstream -o misorder tests/repro/F-001-b.c upstream/sqlite3.c -lm -lpthread -ldl
** Run `./misorder` (INT_MIN for "less", DESC index), `./misorder control` (-1, DESC) and `./misorder intmin asc`.
** With INT_MIN and DESC: PRAGMA integrity_check gives 2,000 errors ("row N missing from index i"), and 2,000 of 2,001
** equality lookups through the index disagree with a table scan. Both controls are clean. The orchestrator's run, in
** campaign.py's repro sandbox: evidence/orchestrator/F-001-b/run.txt.
*/
/* Auditor's test (2026-11-11): does F-001 (rc = -rc at 92793 with rc == INT_MIN) give wrong
** results in compiled code?  A collation returning INT_MIN for "less" is legal (only the sign
** matters).  Under a DESC index the negation wraps back to INT_MIN, so "less" stays "less". */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include "sqlite3.h"
static int lessval;
static int cmp(void *u, int n1, const void *a, int n2, const void *b){
  int n = n1<n2 ? n1 : n2, r = memcmp(a, b, n);
  if( r==0 ) r = n1 - n2;
  (void)u;
  return r<0 ? lessval : (r>0 ? 1 : 0);
}
static int cb(void *p, int n, char **v, char **c){ (void)n; (void)c; printf("  %s: %s\n", (char*)p, v[0]); return 0; }
int main(int argc, char **argv){
  sqlite3 *db; int i; char sql[200];
  lessval = (argc>1 && strcmp(argv[1],"control")==0) ? -1 : INT_MIN;
  printf("collation returns %d for less\n", lessval);
  sqlite3_open(":memory:", &db);
  sqlite3_create_collation(db, "c", SQLITE_UTF8, 0, cmp);
  { char ddl[200]; const char *dir = (argc>2 && strcmp(argv[2],"asc")==0) ? "ASC" : "DESC"; printf("index direction %s\n", dir);
    sqlite3_snprintf(sizeof(ddl), ddl, "CREATE TABLE t(x TEXT); CREATE INDEX i ON t(x COLLATE c %s);", dir); sqlite3_exec(db, ddl, 0, 0, 0); }
  srand(1);
  for(i=0; i<2000; i++){
    sqlite3_snprintf(sizeof(sql), sql, "INSERT INTO t VALUES('k%06d')", rand()%100000);
    sqlite3_exec(db, sql, 0, 0, 0);
  }
  sqlite3_exec(db, "INSERT INTO t VALUES('probe-value')", 0, 0, 0);
  { sqlite3_stmt *s; int bad=0, n=0;
    sqlite3_prepare_v2(db, "PRAGMA integrity_check(100000)", -1, &s, 0);
    while( sqlite3_step(s)==SQLITE_ROW ){ n++; if( strcmp((const char*)sqlite3_column_text(s,0),"ok") ) bad++; }
    sqlite3_finalize(s); printf("  integrity_check: %d lines, %d errors\n", n, bad); }
  { sqlite3_stmt *a, *b, *q; int rows=0, wrong=0;
    sqlite3_prepare_v2(db, "SELECT x FROM t NOT INDEXED", -1, &q, 0);
    sqlite3_prepare_v2(db, "SELECT count(*) FROM t INDEXED BY i WHERE x=?1 COLLATE c", -1, &a, 0);
    sqlite3_prepare_v2(db, "SELECT count(*) FROM t NOT INDEXED WHERE x=?1 COLLATE c", -1, &b, 0);
    while( sqlite3_step(q)==SQLITE_ROW ){
      const unsigned char *v = sqlite3_column_text(q,0); int ca, cb2;
      sqlite3_bind_text(a,1,(const char*)v,-1,SQLITE_TRANSIENT); sqlite3_bind_text(b,1,(const char*)v,-1,SQLITE_TRANSIENT);
      sqlite3_step(a); sqlite3_step(b); ca=sqlite3_column_int(a,0); cb2=sqlite3_column_int(b,0);
      sqlite3_reset(a); sqlite3_reset(b); rows++; if( ca!=cb2 ) wrong++;
    }
    sqlite3_finalize(q); sqlite3_finalize(a); sqlite3_finalize(b);
    printf("  equality lookups: %d rows, %d where the index count differs from a table scan\n", rows, wrong); }
  sqlite3_exec(db, "SELECT count(*) FROM t WHERE x='probe-value' COLLATE c", cb, "indexed lookup of probe-value (expect 1)", 0);
  sqlite3_exec(db, "SELECT count(*) FROM t NOT INDEXED WHERE x='probe-value' COLLATE c", cb, "table scan of probe-value (expect 1)", 0);
  sqlite3_close(db);
  return 0;
}
