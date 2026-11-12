#ifndef C_stat_H
#define C_stat_H
void contract_stat(Cell *p)
  __CPROVER_requires(__CPROVER_w_ok(p, sizeof(Cell)))
  __CPROVER_assigns(p->flags)
  __CPROVER_ensures(p->flags == 1 || p->flags == 2);
#endif
