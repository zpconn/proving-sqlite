/* T-015: a legacy loop frame wider than the function's assigns. f may assign only cells[i].a; the loop's frame,
 * object_from(p), also covers b; the body writes b. A sound frame check rejects this. (C-15 round 4, reports/C-15-b4.md) */
#include <stdlib.h>
typedef struct { unsigned a, b; } Cell;
void f(Cell *cells, unsigned n)
__CPROVER_requires(n>0 && n<=2 && __CPROVER_w_ok(cells, sizeof(Cell)*n))
__CPROVER_assigns(1: cells[0].a; n>1: cells[1].a)
{
  unsigned i=0;
  Cell *p=cells;
  while(i<n)
  __CPROVER_assigns(i,p,__CPROVER_object_from(p))
  __CPROVER_loop_invariant(i<=n && p==cells+i)
  __CPROVER_decreases(n-i)
  {
#ifdef GOOD
    p->a=0;
#else
    p->b=0;
#endif
    i++; p++; }
}
void entry(void){
  unsigned n;
  __CPROVER_assume(n>0 && n<=2);
  Cell *p=malloc(sizeof(Cell)*n);
  __CPROVER_assume(p);
  f(p,n);
}
