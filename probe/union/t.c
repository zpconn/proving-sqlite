/* T-006 probe: does a ?: inside a replaced contract's requires abort the legacy enforce pass? */
#include <stdlib.h>
typedef struct M { union { long long i; double r; } u; unsigned flags; } M;
void get(const unsigned char *buf, unsigned t, M *p) { p->flags = 4; }
void get(const unsigned char *buf, unsigned t, M *p)
  __CPROVER_requires(__CPROVER_w_ok(p, sizeof(M)))
#ifdef TERNARY
  __CPROVER_requires(t < 1 || t > 7 || __CPROVER_r_ok(buf, t <= 4 ? t : t == 5 ? 6 : 8))
#else
  __CPROVER_requires(t < 1 || t > 7 || __CPROVER_r_ok(buf, 8))
#endif
  __CPROVER_assigns(p->u, p->flags)
  __CPROVER_ensures(p->flags == 4);
void f(const unsigned char *buf, M *p) { get(buf, 3, p); }
void f(const unsigned char *buf, M *p) __CPROVER_requires(__CPROVER_r_ok(buf, 8) && __CPROVER_w_ok(p, sizeof(M))) __CPROVER_assigns(*p);
void h(void) { M *p = malloc(sizeof(M)); unsigned char *b = malloc(8); __CPROVER_assume(p && b); f(b, p); }
