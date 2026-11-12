#ifndef C_t_invariant_H
#define C_t_invariant_H
void contract_t_invariant(unsigned n)
  __CPROVER_requires(n <= 10)
  __CPROVER_assigns();
#endif
