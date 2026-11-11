#ifndef C_t_decreases_H
#define C_t_decreases_H
void contract_t_decreases(unsigned n)
  __CPROVER_requires(n <= 10)
  __CPROVER_assigns();
#endif
