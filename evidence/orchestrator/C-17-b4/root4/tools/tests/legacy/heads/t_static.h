#ifndef C_t_static_H
#define C_t_static_H
void contract_t_static(Cell *a)
  __CPROVER_requires(__CPROVER_w_ok(a, 2 * sizeof(Cell)))
  __CPROVER_assigns(__CPROVER_object_whole(a));
#endif
