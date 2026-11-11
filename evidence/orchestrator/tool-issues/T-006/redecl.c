/* Can a later declaration attach a legacy contract to an already-defined static function, as a harness would
 * have to for SQLite's? reset's body writes flags = 7; the contract says it ensures flags == 0. If the call is
 * replaced by the contract the assertion holds; if the body runs it fails. */
#include <stdlib.h>
struct Cell { unsigned flags; void *payload; };
static void reset(struct Cell *p){ p->flags = 7; }
static void reset(struct Cell *p)
  __CPROVER_requires(__CPROVER_w_ok(p,sizeof(*p)))
  __CPROVER_assigns(p->flags)
  __CPROVER_ensures(p->flags==0);
void entry(void){
  struct Cell *a = malloc(sizeof(*a));
  __CPROVER_assume(a != 0);
  reset(a);
  __CPROVER_assert(a->flags == 0, "replaced by the contract");
}
