#ifndef C_two_H
#define C_two_H
void contract_two(int *p, int *q)
  __CPROVER_requires(__CPROVER_is_fresh(p, sizeof(int)) && __CPROVER_is_fresh(q, sizeof(int)))
  __CPROVER_assigns(*p)
  __CPROVER_ensures(*q == __CPROVER_old(*q));
#endif
