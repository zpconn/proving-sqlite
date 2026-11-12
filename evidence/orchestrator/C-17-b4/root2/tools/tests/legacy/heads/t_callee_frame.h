#ifndef C_t_callee_frame_H
#define C_t_callee_frame_H
void contract_t_callee_frame(Cell *a, Cell *other, unsigned n)
  __CPROVER_requires(n <= 4 && __CPROVER_w_ok(a, 4 * sizeof(Cell)) && __CPROVER_w_ok(other, sizeof(Cell)))
  __CPROVER_assigns(__CPROVER_object_whole(a), other->flags);
#endif
