/* T-006 probe: does a replaced contract that assigns a union-typed member abort the legacy enforce pass? */
#include <stdlib.h>
typedef struct M { union { long long i; double r; } u; unsigned flags; } M;
void get(M *p) { p->u.i = 1; p->flags = 4; }
void get(M *p) __CPROVER_requires(__CPROVER_w_ok(p, sizeof(M)))
#ifdef UNION
  __CPROVER_assigns(p->u, p->flags)
#else
  __CPROVER_assigns(p->u.i, p->flags)
#endif
  __CPROVER_ensures(p->flags == 4);
void f(M *p) { get(p); }
void f(M *p) __CPROVER_requires(__CPROVER_w_ok(p, sizeof(M))) __CPROVER_assigns(*p);
void h(void) { M *p = malloc(sizeof(M)); __CPROVER_assume(p); f(p); }
