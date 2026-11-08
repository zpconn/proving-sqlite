/* One toy per check in proofs/CHECKS. Build with -D<NAME>. Each commits exactly one kind of UB. */
#include <stdlib.h>
int main(void) {
  int k; unsigned n; int a[4];
#ifdef POINTER          /* deref of a pointer to a dead object */
  int *p; { int x = 1; p = &x; } k = *p;
#endif
#ifdef BOUNDS           /* array index out of bounds */
  __CPROVER_assume(n < 8); k = a[n];
#endif
#ifdef POINTER_OVERFLOW /* pointer arithmetic beyond one past the end */
  int *q = a; __CPROVER_assume(n < 8); q = q + n; (void)q;
#endif
#ifdef POINTER_PRIMITIVE /* __CPROVER_r_ok on a dangling pointer */
  char *d = malloc(4); if (!d) return 0; free(d); k = __CPROVER_r_ok(d, 1);
#endif
#ifdef SIGNED_OVERFLOW
  int s; s = s + 1; k = s;
#endif
#ifdef UNDEFINED_SHIFT  /* shift by >= width */
  __CPROVER_assume(n < 40); k = 1u << n;
#endif
#ifdef NEG_SHIFT        /* left shift of a negative value, C11 6.5.7p4 */
  int ns; __CPROVER_assume(ns < 0); k = ns << 1;
#endif
#ifdef SHL_OVERFLOW     /* 1 << 31 in int: result not representable, C11 6.5.7p4 */
  __CPROVER_assume(n < 32); k = 1 << n;
#endif
#ifdef DIV_BY_ZERO
  int z; k = 10 / z;
#endif
#ifdef FLOAT_DIV_BY_ZERO
  double fz; double fr = 1.0 / fz; (void)fr;
#endif
#ifdef MALLOC_MAY_FAIL  /* uses malloc's result without a NULL check */
  int *m = malloc(sizeof(int)); *m = 1; free(m);
#endif
#ifdef UNWINDING        /* loop bound larger than --unwind */
  __CPROVER_assume(n < 20); for (unsigned i = 0; i < n; i++) k += i;
#endif
#ifdef FLOAT_TO_INT     /* (long long) of an out-of-range double */
  double r; long long li = (long long)r; (void)li;
#endif
  return k;
}
