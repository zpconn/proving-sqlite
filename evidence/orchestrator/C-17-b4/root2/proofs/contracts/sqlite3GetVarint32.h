#ifndef CONTRACT_SQLITE3GETVARINT32_H
#define CONTRACT_SQLITE3GETVARINT32_H
u8 contract_sqlite3GetVarint32(const unsigned char *p, u32 *v)
  __CPROVER_requires(__CPROVER_r_ok(p, 9))
  __CPROVER_requires(__CPROVER_w_ok(v, sizeof(*v)))
  __CPROVER_assigns(*v)
  __CPROVER_ensures(1 <= __CPROVER_return_value && __CPROVER_return_value <= 9);
#endif
