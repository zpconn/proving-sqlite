/* §1.5 probe: one TU with the overlay, as every proof is built. Each assertion states what the configuration's
** name says; run under each configuration, the probe passes only when all hold. EXPECT_* come from run.sh. */
#include "sqlite3.c"
void probe(void) {
  unsigned x = 0x01020304u;
  const unsigned char b[4] = {1, 2, 3, 4};
  __CPROVER_assert(sizeof(void*) == EXPECT_PTR, "pointer width");
  __CPROVER_assert(sizeof(long) == EXPECT_LONG, "long width");
  __CPROVER_assert(SQLITE_PTRSIZE == EXPECT_PTR, "SQLITE_PTRSIZE");
  __CPROVER_assert(*(unsigned char*)&x == EXPECT_LOW_BYTE, "byte order of memory (low byte of 0x01020304)");
  __CPROVER_assert(SQLITE_BYTEORDER == EXPECT_BYTEORDER, "SQLITE_BYTEORDER");
  __CPROVER_assert(SQLITE_BIGENDIAN == (EXPECT_BYTEORDER == 4321), "SQLITE_BIGENDIAN");
  /* sqlite3Get4byte's branch depends on SQLITE_BYTEORDER; every branch must decode big-endian 0x01020304. */
  __CPROVER_assert(sqlite3Get4byte(b) == 0x01020304u, "sqlite3Get4byte decodes big-endian on this config");
}
