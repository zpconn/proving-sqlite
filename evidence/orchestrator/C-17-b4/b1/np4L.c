#include <stdlib.h>
typedef struct { char *z; int n; } M;
typedef struct { int k; M *a; } U;
/* np4: a quantifier with no pointer primitive: does assuming it constrain a[j].n at all? */
int f(U *u, int j)
  __CPROVER_requires(__CPROVER_r_ok(u, sizeof(U)) && u->k > 0 && __CPROVER_r_ok(u->a, sizeof(M)*u->k))
  __CPROVER_requires(0 <= j && j < u->k)
  __CPROVER_requires(__CPROVER_forall { int q; (0 <= q && q < u->k) ==> (u->a[q].n >= 0 && u->a[q].n < 100) })
  __CPROVER_assigns();
int f(U *u, int j)
{
  M *m = u->a + j;
  __CPROVER_assert(m->n >= 0 && m->n < 100, "quantified requires holds at j");
  return m->n;
}
void h(void){
  U *u; size_t k; int j;
  u = malloc(sizeof(U)); __CPROVER_assume(u != 0);
  __CPROVER_assume(k < 1000);
  u->a = malloc(k * sizeof(M)); __CPROVER_assume(u->a != 0);
  f(u, j);
}
