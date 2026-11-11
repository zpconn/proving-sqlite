/* T-003 under legacy contracts: a read of an element whose last byte is out of bounds, in a legacy-enforced function.
 * goto-cc --function h flexgap.c -o 0.goto; goto-instrument --enforce-contract rd 0.goto 1.goto;
 * cbmc 1.goto <every option in proofs/CHECKS>   (each under ulimit -v 25165824). Result: VERIFICATION SUCCESSFUL (the gap). */
#include <stdlib.h>
typedef struct Flex { int n; void *a[]; } Flex;
void *rd(Flex *s) { return s->a[0]; }
void *rd(Flex *s) __CPROVER_requires(__CPROVER_r_ok(s, sizeof(Flex))) __CPROVER_assigns();
void h(void) { Flex *s = malloc(sizeof(Flex) + sizeof(void *) - 1); __CPROVER_assume(s); rd(s); }
