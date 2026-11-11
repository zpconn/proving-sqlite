/* Independent diagnostic; no SQLite code. */
#include <stdlib.h>
struct Cell { unsigned flags; void *payload; };
void reset(struct Cell *p);
void reset_spec(struct Cell *p)
  __CPROVER_requires(__CPROVER_w_ok(p,sizeof(*p)))
  __CPROVER_assigns(p->flags)
  __CPROVER_ensures(p->flags==0);
void entry(void){
  struct Cell *a=malloc(4*sizeof(*a));
  __CPROVER_assume(a!=0);
  unsigned k=0;
  while(k<4)
    __CPROVER_assigns(k,__CPROVER_object_upto(a,4*sizeof(*a)))
    __CPROVER_loop_invariant(k<=4)
    __CPROVER_decreases(4-k)
  {
    struct Cell *p=a+k;
    reset(p);
    reset(p);
    reset(p);
    reset(p);
    __CPROVER_assert(p->flags==0,"callee postcondition visible");
    ++k;
  }
}
