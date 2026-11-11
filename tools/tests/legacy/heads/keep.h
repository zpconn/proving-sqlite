#ifndef C_keep_H
#define C_keep_H
void contract_keep(Cell *p)
  __CPROVER_requires(__CPROVER_w_ok(p, sizeof(Cell)))
  __CPROVER_assigns(p->flags)
  __CPROVER_ensures(p->flags == __CPROVER_old(p->flags));
#endif
