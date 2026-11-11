/* Legacy-contracts validation toys (T-006, Zach's condition 3; tools/tests/test_tools.py -k legacy). They stand in for
 * upstream/sqlite3.c in a scratch repository. Each proof passes as written and fails, by the check the test names,
 * when VARIANT_<name> is defined (for forget, when contract_keep loses its ensures). */
#include <stdlib.h>
#include <string.h>
typedef struct Cell { unsigned flags; void *payload; } Cell;
typedef struct Flex { int n; void *a[]; } Flex;

/* callees replaced by their contracts in the toys that call them */
void keep(Cell *p) { (void)p; }                       /* its body changes nothing */
void reset(Cell *p) { p->flags = 0; }

/* 1. a replaced call must forget the old value of what its contract assigns */
unsigned t_forget(Cell *p) { p->flags = 5; keep(p); return p->flags; }

/* 2. a callee assigning outside the loop's frame */
void t_callee_frame(Cell *a, Cell *other, unsigned n) {
  unsigned i = 0;
  while (i < n)
    __CPROVER_assigns(i, __CPROVER_object_whole(a)
#ifndef VARIANT_callee_frame
                      , other->flags
#endif
                      )
    __CPROVER_loop_invariant(i <= n)
    __CPROVER_decreases(n - i)
  { reset(other); i++; }
}

/* 3. a write through an alias outside the loop's frame */
void t_alias_frame(Cell *a, Cell *b, unsigned n) {
  unsigned i = 0;
  Cell *q = b;
  while (i < n)
    __CPROVER_assigns(i, __CPROVER_object_whole(a)
#ifndef VARIANT_alias_frame
                      , b->flags
#endif
                      )
    __CPROVER_loop_invariant(i <= n)
    __CPROVER_decreases(n - i)
  { q->flags = 1; i++; }
}

/* 4. an invariant true at entry but false on a later pass */
void t_invariant(unsigned n) {
  unsigned i = 0;
  while (i < n)
    __CPROVER_assigns(i)
#ifdef VARIANT_invariant
    __CPROVER_loop_invariant(i <= 1)
#else
    __CPROVER_loop_invariant(i <= n)
#endif
    __CPROVER_decreases(n - i)
  { i++; }
}

/* 5. a wrong decreases */
void t_decreases(unsigned n) {
  unsigned i = 0;
  while (i < n)
    __CPROVER_assigns(i)
    __CPROVER_loop_invariant(i <= n)
#ifdef VARIANT_decreases
    __CPROVER_decreases(i)
#else
    __CPROVER_decreases(n - i)
#endif
  { i++; }
}

/* 6. a claim after the loop the invariant doesn't support */
unsigned t_after(unsigned n) {
  unsigned i = 0;
  while (i < n)
    __CPROVER_assigns(i)
#ifdef VARIANT_after
    __CPROVER_loop_invariant(i <= n + 1)
#else
    __CPROVER_loop_invariant(i <= n)
#endif
    __CPROVER_decreases(n - i)
  { i++; }
  return i;                                           /* the contract ensures i == n */
}

/* 7. an out-of-bounds write in the loop */
void t_oob(Cell *a, unsigned n) {
  unsigned i = 0;
#ifdef VARIANT_oob
  while (i <= n)
    __CPROVER_assigns(i, __CPROVER_object_whole(a))
    __CPROVER_loop_invariant(i <= n + 1)
    __CPROVER_decreases(n + 1 - i)
#else
  while (i < n)
    __CPROVER_assigns(i, __CPROVER_object_whole(a))
    __CPROVER_loop_invariant(i <= n)
    __CPROVER_decreases(n - i)
#endif
  { a[i].flags = 0; i++; }
}

/* 8. an out-of-bounds pointer passed to a replaced callee: its requires */
void t_callee_requires(Cell *a, unsigned n) {
#ifdef VARIANT_callee_requires
  reset(a + n);
#else
  reset(a + n - 1);
#endif
}

/* 9. T-003's flexible array: with an exact allocation, a read one element past the end is caught */
void * t_flex(Flex *s, int n) {
#ifdef VARIANT_flex
  return s->a[n];
#else
  return s->a[n - 1];
#endif
}

/* 10. is_fresh: separate objects under enforcement; aliased arguments refused at a replaced call */
void two(int *p, int *q) { *p = 1; }
int t_fresh(int *x, int *y) {
#ifdef VARIANT_fresh
  two(x, x);
#else
  two(x, y);
#endif
  return 0;
}

/* 11. T-006's pattern: a loop-carried pointer and four replaced calls per iteration (DFCC: no verdict; legacy: proves) */
void t_carried(Cell *a) {
  Cell *p = a;
  unsigned k = 0;
  while (k < 4)
    __CPROVER_assigns(k, p, __CPROVER_object_whole(a))
    __CPROVER_loop_invariant(k <= 4 && p == a + k)
    __CPROVER_decreases(4 - k)
  { reset(p); reset(p); reset(p); reset(p); ++p; ++k; }
}

/* 12. globals start unconstrained under legacy contracts too, as under DFCC (TRUSTED.md) */
int g_toy = 5;
int t_glob(void) { return g_toy; }

/* 13. T-012: a replaced callee with a static local, called in a loop, aborts the legacy enforce pass */
void stat(Cell *p) { static const unsigned tbl[] = { 1, 2 }; p->flags = tbl[p->flags & 1]; }
void t_static(Cell *a) {
  Cell *p = a;
  unsigned k = 0;
  while (k < 2)
    __CPROVER_assigns(k, p, __CPROVER_object_whole(a))
    __CPROVER_loop_invariant(k <= 2 && p == a + k)
    __CPROVER_decreases(2 - k)
  { stat(p); ++p; ++k; }
}
