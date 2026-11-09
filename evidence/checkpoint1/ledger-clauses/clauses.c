#include <stdlib.h>
typedef unsigned long long u64; typedef unsigned char u8;
typedef struct sqlite3 sqlite3; struct sqlite3 { int x; };
typedef struct Mem { char *z; int n; int enc; } Mem;
typedef struct CollSeq { int enc; void *pUser; } CollSeq;
#define SQLITE_CORRUPT 11
void *sqlite3DbMallocRaw(sqlite3 *db, u64 n);
int vdbeCompareMemString(const Mem *pMem1, const Mem *pMem2, const CollSeq *pColl, u8 *prcErr);
int sqlite3CorruptError(int lineno);
void *contract_sqlite3DbMallocRaw(sqlite3 *db, u64 n)
  __CPROVER_assigns()
  __CPROVER_ensures(__CPROVER_return_value == NULL || __CPROVER_is_fresh(__CPROVER_return_value, n));
int contract_vdbeCompareMemString(const Mem *pMem1, const Mem *pMem2, const CollSeq *pColl, u8 *prcErr)
  __CPROVER_requires(__CPROVER_r_ok(pMem1, sizeof(Mem)) && __CPROVER_r_ok(pMem2, sizeof(Mem))
                     && __CPROVER_r_ok(pColl, sizeof(CollSeq)))
  __CPROVER_requires(pMem1->n >= 0 && __CPROVER_r_ok(pMem1->z, pMem1->n)
                     && pMem2->n >= 0 && __CPROVER_r_ok(pMem2->z, pMem2->n))
  __CPROVER_requires(prcErr == NULL || __CPROVER_w_ok(prcErr, 1))
  __CPROVER_assigns(prcErr != NULL: *prcErr);
int contract_sqlite3CorruptError(int lineno)
  __CPROVER_assigns()
  __CPROVER_ensures(__CPROVER_return_value == SQLITE_CORRUPT);
int harness(void){
  sqlite3 db; Mem a, b; CollSeq c; u8 err = 0; char s[4];
  a.z = s; a.n = 4; b.z = s; b.n = 2;
  unsigned char *p = sqlite3DbMallocRaw(&db, 16);
  if( p ){ p[15] = 1; }
  int r = vdbeCompareMemString(&a, &b, &c, &err);
  int e = sqlite3CorruptError(1);
  __CPROVER_assert(e == SQLITE_CORRUPT, "corrupt");
  return r;
}
