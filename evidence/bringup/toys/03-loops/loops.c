#include "../../../../proofs/include/proof.h"
/* sum of 0..n-1 style while loop, and a do-while like RecordCompareWithSkip's */
unsigned w(unsigned n) {
  unsigned i = 0, s = 0;
  __CPROVER_assume(n <= 1000);
  while (i < n)
#ifdef WHILE_GOOD
    PROOF(__CPROVER_assigns(i, s) __CPROVER_loop_invariant(i <= n && s == i) __CPROVER_decreases(n - i))
#elif defined(WHILE_BAD_INV)
    PROOF(__CPROVER_assigns(i, s) __CPROVER_loop_invariant(i <= n && s == 2 * i) __CPROVER_decreases(n - i))
#elif defined(WHILE_BAD_DEC)
    PROOF(__CPROVER_assigns(i, s) __CPROVER_loop_invariant(i <= n && s == i) __CPROVER_decreases(i))
#endif
  {
    s++; i++;
  }
  return s;
}
unsigned d(unsigned n) {
  unsigned i = 0;
  __CPROVER_assume(n >= 1 && n <= 1000);
  /* CBMC 6.11 accepts do-while clauses only between `do` and the body (see result.txt).
  ** The invariant is checked before the first iteration and after each step that loops back,
  ** so it must hold at the top of every iteration: here i < n, not 1 <= i. */
  do
#ifdef DO_GOOD
    PROOF(__CPROVER_assigns(i) __CPROVER_loop_invariant(i < n) __CPROVER_decreases(n - i))
#elif defined(DO_BAD_INV)
    PROOF(__CPROVER_assigns(i) __CPROVER_loop_invariant(i == 0) __CPROVER_decreases(n - i))
#elif defined(DO_BAD_DEC)
    PROOF(__CPROVER_assigns(i) __CPROVER_loop_invariant(i < n) __CPROVER_decreases(n + i))
#endif
  {
    i++;
  } while (i < n);
  return i;
}
int main(void) {
  unsigned n;
#ifdef WHILE
  unsigned r = w(n);
  __CPROVER_assert(r == n, "w returns n");
#else
  unsigned r = d(n);
  __CPROVER_assert(r == n, "d returns n");
#endif
  return 0;
}
