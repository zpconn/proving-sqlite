#ifndef C_t_flex_H
#define C_t_flex_H
void *contract_t_flex(Flex *s, int n)
  __CPROVER_requires(n >= 1 && n <= 4 && __CPROVER_r_ok(s, sizeof(Flex) + (size_t)n * sizeof(void *)))
  __CPROVER_assigns();
#endif
