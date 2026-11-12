#ifndef C_t_carried_H
#define C_t_carried_H
void contract_t_carried(Cell *a)
  __CPROVER_requires(__CPROVER_w_ok(a, 4 * sizeof(Cell)))
  __CPROVER_assigns(__CPROVER_object_whole(a));
#endif
