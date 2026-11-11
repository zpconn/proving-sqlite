/* T-011 reduction: a synthetic loop (not SQLite's algorithm) carrying a Mem pointer and calling sqlite3VdbeSerialGet,
 * replaced by its approved contract, under the legacy engine. SQLite's types come from the overlay; no SQLite code is changed. */
#include "sqlite3.c"
void sqlite3VdbeSerialGet(
  const unsigned char *buf, u32 serial_type, Mem *pMem)
  __CPROVER_requires(__CPROVER_w_ok(pMem, sizeof(Mem)))
  __CPROVER_requires(serial_type < 1 || serial_type > 7 ||
    __CPROVER_r_ok(buf, serial_type <= 4 ? serial_type :
      serial_type == 5 ? 6 : 8))
  __CPROVER_assigns(pMem->u, pMem->flags, pMem->n, pMem->z)
  __CPROVER_ensures(serial_type == 0 || serial_type == 11 ?
    pMem->flags == MEM_Null :
    serial_type == 10 ? pMem->flags == (MEM_Null|MEM_Zero) :
    serial_type == 7 ? (pMem->flags == MEM_Null || pMem->flags == MEM_Real) :
    serial_type < 12 ? pMem->flags == MEM_Int :
    pMem->flags == ((serial_type & 1) ? (MEM_Str|MEM_Ephem) : (MEM_Blob|MEM_Ephem)))
  __CPROVER_ensures(serial_type != 10 || (pMem->n == 0 && pMem->u.nZero == 0))
  __CPROVER_ensures(serial_type < 12 ||
    (pMem->z == (char *)buf && pMem->n == (serial_type-12)/2));
void walk(const unsigned char *buf, u32 t, Mem *a, unsigned n){
  Mem *pMem = a;
  unsigned k = 0;
  while( k < n )
    __CPROVER_assigns(k, pMem, __CPROVER_object_whole(a))
    __CPROVER_loop_invariant(k <= n && pMem == a + k)
    __CPROVER_decreases(n - k)
  {
    sqlite3VdbeSerialGet(buf, t, pMem);
    pMem++; k++;
  }
}
void walk(const unsigned char *buf, u32 t, Mem *a, unsigned n)
  __CPROVER_requires(n <= 4 && __CPROVER_r_ok(buf, 8) && __CPROVER_w_ok(a, 4 * sizeof(Mem)))
  __CPROVER_assigns(__CPROVER_object_whole(a));
void h(void){ unsigned n; u32 t; unsigned char *b = malloc(8); Mem *a = malloc(4 * sizeof(Mem));
  __CPROVER_assume(b && a); walk(b, t, a, n); }
