#ifndef C_t_alias_frame_H
#define C_t_alias_frame_H
void contract_t_alias_frame(Cell *a, Cell *b, unsigned n)
  __CPROVER_requires(n <= 4 && __CPROVER_w_ok(a, 4 * sizeof(Cell)) && __CPROVER_w_ok(b, sizeof(Cell)))
  __CPROVER_assigns(__CPROVER_object_whole(a), b->flags);
#endif
