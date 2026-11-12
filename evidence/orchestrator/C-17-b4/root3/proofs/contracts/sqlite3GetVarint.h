#ifndef CONTRACT_SQLITE3GETVARINT_H
#define CONTRACT_SQLITE3GETVARINT_H
u8 contract_sqlite3GetVarint(const unsigned char *p, u64 *v)
  __CPROVER_requires(__CPROVER_r_ok(p, 9))
  __CPROVER_requires(__CPROVER_w_ok(v, sizeof(*v)))
  __CPROVER_assigns(*v)
  __CPROVER_ensures(1 <= __CPROVER_return_value && __CPROVER_return_value <= 9)
  __CPROVER_ensures((__CPROVER_old(p[0]) & __CPROVER_old(p[1])
                     & __CPROVER_old(p[2]) & 0x80) == 0
                    || __CPROVER_return_value > 3);
#endif
