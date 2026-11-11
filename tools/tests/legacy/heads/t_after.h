#ifndef C_t_after_H
#define C_t_after_H
unsigned contract_t_after(unsigned n)
  __CPROVER_requires(n <= 10)
  __CPROVER_assigns()
  __CPROVER_ensures(__CPROVER_return_value == n);
#endif
