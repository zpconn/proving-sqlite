#include <string.h>
#include <stdlib.h>
void h(void){ size_t n; char *a = malloc(n), *b = malloc(n); __CPROVER_assume(a&&b); int r = memcmp(a,b,n); }
