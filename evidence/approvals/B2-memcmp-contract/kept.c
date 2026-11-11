/* Under legacy contracts, is a kept (not replaced) callee body's write checked against the loop's assigns?
 * bump(other) writes other->flags; the loop's assigns lists it only in the GOOD variant. The callee keeps its body. */
#include <stdlib.h>
typedef struct Cell { unsigned flags; void *payload; } Cell;
void bump(Cell *p) { p->flags++; }
void walk(Cell *a, Cell *other, unsigned n) {
  unsigned i = 0;
  while (i < n)
    __CPROVER_assigns(i, __CPROVER_object_whole(a)
#ifndef BAD
                      , other->flags
#endif
                      )
    __CPROVER_loop_invariant(i <= n)
    __CPROVER_decreases(n - i)
  { bump(other); i++; }
}
void walk(Cell *a, Cell *other, unsigned n)
  __CPROVER_requires(n <= 4 && __CPROVER_w_ok(a, 4 * sizeof(Cell)) && __CPROVER_w_ok(other, sizeof(Cell)))
  __CPROVER_assigns(__CPROVER_object_whole(a), other->flags);
void h(void) { unsigned n; Cell *a = malloc(4 * sizeof(Cell)), *o = malloc(sizeof(Cell)); __CPROVER_assume(a && o); walk(a, o, n); }
