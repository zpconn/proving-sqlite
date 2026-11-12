/* tools/probe/config_probe.c: the configuration probe (GOAL.md §1.5), run by `make probe` and the gate.
** One TU with the overlay, as every proof is built. tools/prove.py derives EXPECT_* from the configuration name. */
#include "sqlite3.c"
#ifdef __CHAR_UNSIGNED__
#define PROBE_PP_CHAR_UNSIGNED 1
#else
#define PROBE_PP_CHAR_UNSIGNED 0
#endif
void probe(void) {
  unsigned x = 0x01020304u;
  const unsigned char b[4] = {1, 2, 3, 4};
  char c = (char)-1;
  __CPROVER_assert(sizeof(void*) == EXPECT_PTR, "pointer width");
  __CPROVER_assert(sizeof(long) == EXPECT_LONG, "long width");
  __CPROVER_assert(SQLITE_PTRSIZE == EXPECT_PTR, "SQLITE_PTRSIZE");
  __CPROVER_assert(*(unsigned char*)&x == EXPECT_LOW_BYTE, "byte order of memory (low byte of 0x01020304)");
  __CPROVER_assert(SQLITE_BYTEORDER == EXPECT_BYTEORDER, "SQLITE_BYTEORDER");
  __CPROVER_assert(SQLITE_BIGENDIAN == (EXPECT_BYTEORDER == 4321), "SQLITE_BIGENDIAN");
  __CPROVER_assert((c < 0) == !EXPECT_CHAR_UNSIGNED, "plain char signedness (CBMC)");
  __CPROVER_assert(PROBE_PP_CHAR_UNSIGNED == EXPECT_CHAR_UNSIGNED, "plain char signedness (preprocessor, __CHAR_UNSIGNED__)");
  /* sqlite3Get4byte's branch depends on SQLITE_BYTEORDER; every branch must decode big-endian 0x01020304. */
  __CPROVER_assert(sqlite3Get4byte(b) == 0x01020304u, "sqlite3Get4byte decodes big-endian on this config");
}
