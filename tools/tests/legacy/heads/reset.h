#ifndef C_reset_H
#define C_reset_H
void contract_reset(Cell *p)
  __CPROVER_requires(__CPROVER_w_ok(p, sizeof(Cell)))
  __CPROVER_assigns(p->flags)
  __CPROVER_ensures(p->flags == 0);
#endif
