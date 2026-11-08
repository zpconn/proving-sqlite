/* §1.8.2 native probe: sqlite3VdbeRecordUnpack on the two-byte record {0x02, 0x81} held in an exact-size
** malloc, unmodified upstream. The header says 2 bytes; byte 1 (0x81) starts a multi-byte serial type
** varint, so decoding it reads aKey[2], past the record. ASan should report a heap-buffer-overflow read. */
#include "sqlite3.c"
#include <stdio.h>
#include <stdlib.h>

int main(void){
  KeyInfo ki;
  UnpackedRecord ur;
  Mem mem[2];
  unsigned char *rec = malloc(2);
  rec[0] = 0x02; rec[1] = 0x81;
  memset(&ki, 0, sizeof ki); memset(&ur, 0, sizeof ur); memset(mem, 0, sizeof mem);
  ki.enc = SQLITE_UTF8; ki.db = 0; ki.nKeyField = 1;
  ur.pKeyInfo = &ki; ur.aMem = mem; ur.nField = 2;
  printf("calling sqlite3VdbeRecordUnpack(2, {0x02,0x81}, ...)\n"); fflush(stdout);
  sqlite3VdbeRecordUnpack(2, rec, &ur);
  printf("returned: nField=%d\n", ur.nField);
  free(rec);
  return 0;
}
