/* T-011 reduction: a synthetic loop (not SQLite's algorithm) carrying a Mem pointer and calling sqlite3VdbeSerialGet,
 * replaced by its approved contract, under the legacy engine. SQLite's types come from the overlay; no SQLite code is changed. */
#include "sqlite3.c"
void myget(const unsigned char *buf, u32 serial_type, Mem *pMem) { static const u16 tbl[] = { MEM_Blob, MEM_Str }; pMem->flags = tbl[serial_type & 1]; }
void myget(const unsigned char *buf, u32 serial_type, Mem *pMem) __CPROVER_requires(1) __CPROVER_ensures(1) __CPROVER_assigns();
void walk(const unsigned char *buf, u32 t, Mem *a, unsigned n){
  Mem *pMem = a;
  unsigned k = 0;
  while( k < n )
    __CPROVER_assigns(k, pMem, __CPROVER_object_whole(a))
    __CPROVER_loop_invariant(k <= n && pMem == a + k)
    __CPROVER_decreases(n - k)
  {
    myget(buf, t, pMem);
    pMem++; k++;
  }
}
void walk(const unsigned char *buf, u32 t, Mem *a, unsigned n)
  __CPROVER_requires(n <= 4 && __CPROVER_r_ok(buf, 8) && __CPROVER_w_ok(a, 4 * sizeof(Mem)))
  __CPROVER_assigns(__CPROVER_object_whole(a));
void h(void){ unsigned n; u32 t; unsigned char *b = malloc(8); Mem *a = malloc(4 * sizeof(Mem));
  __CPROVER_assume(b && a); walk(b, t, a, n); }
