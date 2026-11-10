/* Tested: sqlite3VdbeFindCompare on a KeyInfo one byte short of SZ_KEYINFO(1), against unmodified upstream. */
#include "sqlite3.c"
#include <stdio.h>
int main(void){
  UnpackedRecord *p = calloc(1, sizeof(*p)); KeyInfo *k = malloc(SZ_KEYINFO(1) - 1);
  Mem *m = calloc(1, sizeof(*m)); u8 *sort = calloc(1, 1);
  if( !p || !k || !m || !sort ) return 2;
  memset(k, 0, SZ_KEYINFO(1) - 1); k->nAllField = 1; k->aSortFlags = sort; m->flags = MEM_Str;
  p->pKeyInfo = k; p->aMem = m;
  printf("string comparator: %d\n", sqlite3VdbeFindCompare(p) == vdbeRecordCompareString);
  return 0;
}
