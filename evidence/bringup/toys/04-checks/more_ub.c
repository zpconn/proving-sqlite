/* More UB kinds for UB-CLASSES.md: which do proofs/CHECKS catch? */
#include <stdlib.h>
#include <string.h>
int nr(int x) { if (x > 0) return 1; }   /* falls off the end when x <= 0 */
int main(void) {
  int a[4], b[4]; int k = 0; unsigned n;
#ifdef PTR_RELATION        /* 6.5.8p5: relational comparison of pointers to different objects */
  k = (&a[0] < &b[0]);
#endif
#ifdef PTR_SUBTRACT        /* 6.5.6p9: subtraction of pointers to different objects */
  k = (int)(&a[0] - &b[0]);
#endif
#ifdef MEMCPY_OVERLAP      /* 7.24.2.1p2 */
  char c[8]; memcpy(c, c + 2, 4);
#endif
#ifdef FREE_INVALID        /* 7.22.3.3p2 */
  free(&a[1]);
#endif
#ifdef DOUBLE_FREE
  char *d = malloc(4); if (!d) return 0; free(d); free(d);
#endif
#ifdef NO_RETURN           /* 6.9.1p12: the value of a function that reached } is used */
  int x; k = nr(x);
#endif
#ifdef MEMCPY_OOB          /* 7.1.4: library function given an invalid array */
  char e[4]; char f[8]; memcpy(e, f, 8);
#endif
  return k;
}
