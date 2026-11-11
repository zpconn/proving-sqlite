/* B2 toy: memcmp replaced by its boundary contract. f compares two buffers and negates the result, as
 * sqlite3VdbeRecordCompareWithSkip does for a DESC key (92739-92740, 92793). BAD passes one byte more than b holds. */
#include <stdlib.h>
#include <string.h>
int contract_memcmp(const void *s1, const void *s2, size_t n)
  __CPROVER_requires(__CPROVER_r_ok(s1, n) && __CPROVER_r_ok(s2, n))
  __CPROVER_assigns()
  __CPROVER_ensures(-255 <= __CPROVER_return_value && __CPROVER_return_value <= 255);
int f(const unsigned char *a, const unsigned char *b, size_t n) {
#ifdef BAD
  int rc = memcmp(a, b, n + 1);
#else
  int rc = memcmp(a, b, n);
#endif
  return -rc;
}
int contract_f(const unsigned char *a, const unsigned char *b, size_t n)
  __CPROVER_requires(n <= 1000000 && __CPROVER_r_ok(a, n + 1) && __CPROVER_r_ok(b, n))
  __CPROVER_assigns()
  __CPROVER_ensures(-255 <= __CPROVER_return_value && __CPROVER_return_value <= 255);
void h(void) { size_t n; __CPROVER_assume(n <= 1000000);
  unsigned char *a = malloc(n + 1), *b = malloc(n); __CPROVER_assume(a && b); f(a, b, n); }
