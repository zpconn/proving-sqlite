/* Does __CPROVER_r_ok check the whole range? A requires r_ok(s, sizeof(S)+8) must exclude a one-byte-short object. */
#include <stdlib.h>
typedef struct S { int n; void *a[]; } S;
void rok_short(void){ S *s = malloc(sizeof(S) + sizeof(void*) - 1); if( s ) __CPROVER_assert(!__CPROVER_r_ok(s, sizeof(S) + sizeof(void*)), "r_ok false on a 1-byte-short object"); }
void rok_exact(void){ S *s = malloc(sizeof(S) + sizeof(void*)); if( s ) __CPROVER_assert(__CPROVER_r_ok(s, sizeof(S) + sizeof(void*)), "r_ok true on the exact object"); }
