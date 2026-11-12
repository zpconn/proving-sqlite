#ifndef C_t_glob_H
#define C_t_glob_H
int contract_t_glob(void)
  __CPROVER_requires(1)
  __CPROVER_assigns()
  __CPROVER_ensures(__CPROVER_return_value == 5);
#endif
