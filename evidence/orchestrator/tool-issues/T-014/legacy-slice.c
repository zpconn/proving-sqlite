/* From C-15 round 3 (reports/C-15-b3.md). FRAME is a placeholder: see T-014 in tool-issues.md. */
#include <stdlib.h>
typedef struct { unsigned flags; void *payload; } Cell;
typedef struct { Cell *a; unsigned n; } Box;
void traverse(Box *b)
__CPROVER_requires(__CPROVER_w_ok(b, sizeof(*b)))
__CPROVER_requires(b->n > 0 && b->n <= 4)
__CPROVER_requires(__CPROVER_w_ok(b->a, sizeof(Cell)*b->n))
__CPROVER_assigns(__CPROVER_object_upto(b->a,sizeof(Cell)*b->n))
{
  unsigned i=0;
  Cell *p=b->a;
  while(i < b->n)
  __CPROVER_assigns(i,p,FRAME)
  __CPROVER_loop_invariant(i <= b->n && p == b->a+i)
  __CPROVER_decreases(b->n-i)
  { p->flags=0; ++p; ++i; }
}
void entry(void){
  unsigned n;
  __CPROVER_assume(n>0 && n<=4);
  void *v=malloc(sizeof(Box)+sizeof(Cell)*n);
  __CPROVER_assume(v);
  Box *b=v;
  b->a=v+sizeof(Box); b->n=n;
  traverse(b);
}
