#ifndef C_t_fresh_H
#define C_t_fresh_H
int contract_t_fresh(int *x, int *y)
  __CPROVER_requires(__CPROVER_w_ok(x, sizeof(int)) && __CPROVER_w_ok(y, sizeof(int)))
  __CPROVER_assigns(*x);
#endif
