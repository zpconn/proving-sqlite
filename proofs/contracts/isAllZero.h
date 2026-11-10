#ifndef CONTRACT_ISALLZERO_H
#define CONTRACT_ISALLZERO_H
int contract_isAllZero(const char *z, int n)
  __CPROVER_requires(n <= 0 || __CPROVER_r_ok(z, n))
  __CPROVER_assigns()
  __CPROVER_ensures(__CPROVER_return_value == 0 || __CPROVER_return_value == 1);
#endif
