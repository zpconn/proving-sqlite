#include <stdlib.h>
typedef struct { char *z; int n; } M;
typedef struct { int k; M *a; } U;
int f(U *u, int j)
  __CPROVER_requires(__CPROVER_r_ok(u, sizeof(U)) && u->k > 0 && __CPROVER_r_ok(u->a, sizeof(M)*u->k))
  __CPROVER_requires(0 <= j && j < u->k)
  __CPROVER_requires(u->a[j].n >= 0 && __CPROVER_r_ok(u->a[j].z, u->a[j].n))
  __CPROVER_assigns();
int f(U *u, int j)
{
  M *m = u->a + j;
  char c = m->n > 0 ? m->z[m->n - 1] : 0;
  __CPROVER_assert(c != 42 || m->n != 3, "reachable: last byte 42 at n 3");
  return c;
}
void h(void){
  U *u; size_t k; int j;
  u = malloc(sizeof(U)); __CPROVER_assume(u != 0);
  __CPROVER_assume(k < 1000);
  u->a = malloc(k * sizeof(M)); __CPROVER_assume(u->a != 0);
  f(u, j);
}
