/* C-17 round 4, scratch: a KeyInfo one byte short of SZ_KEYINFO(1) overflows natively at the aColl[0] read (92729).
   argv[1] = "0" allocates exactly SZ_KEYINFO(1) (control), anything else one byte less. */
#include "sqlite3.c"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char **argv){
  int shortby = (argc > 1 && strcmp(argv[1], "0") == 0) ? 0 : 1;
  unsigned char *rec = malloc(3 + 8);
  memset(rec, 0, 11); rec[0] = 2; rec[1] = 13 + 2*1; rec[2] = 'a';   /* header {2, text of length 1}, body "a" */
  KeyInfo *ki = malloc(SZ_KEYINFO(1) - shortby);
  memset(ki, 0, SZ_KEYINFO(1) - shortby);
  u8 *sf = calloc(1, 1);
  ki->nAllField = 1; ki->nKeyField = 1; ki->aSortFlags = sf; ki->enc = SQLITE_UTF8;
  Mem *m = calloc(1, sizeof(Mem));
  m->flags = MEM_Str; m->z = "b"; m->n = 1; m->enc = SQLITE_UTF8;
  UnpackedRecord *u = calloc(1, sizeof(UnpackedRecord));
  u->pKeyInfo = ki; u->aMem = m; u->nField = 1;
  int rc = sqlite3VdbeRecordCompareWithSkip(3, rec, u, 0);
  printf("shortby=%d rc=%d\n", shortby, rc);
  return 0;
}
