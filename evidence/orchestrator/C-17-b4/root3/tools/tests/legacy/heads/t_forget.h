#ifndef C_t_forget_H
#define C_t_forget_H
unsigned contract_t_forget(Cell *p)
  __CPROVER_requires(__CPROVER_w_ok(p, sizeof(Cell)))
  __CPROVER_assigns(p->flags)
  __CPROVER_ensures(__CPROVER_return_value == 5);
#endif
