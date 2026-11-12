#ifndef C_t_callee_requires_H
#define C_t_callee_requires_H
void contract_t_callee_requires(Cell *a, unsigned n)
  __CPROVER_requires(n >= 1 && n <= 4 && __CPROVER_w_ok(a, n * sizeof(Cell)))
  __CPROVER_assigns(__CPROVER_object_whole(a));
#endif
