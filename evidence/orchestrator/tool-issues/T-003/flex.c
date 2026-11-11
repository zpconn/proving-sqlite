/* Does CBMC 6.11 check the whole extent of an element access, or only its start? Each harness reads one 8-byte
 * (lp64) object whose last byte lies outside a heap object one byte too small. Every one is UB (out of bounds). */
#include <stdlib.h>
#include <string.h>
typedef struct S { int n; void *a[]; } S;          /* like KeyInfo's aColl[] */
typedef struct M { long long x; } M;

void flex_index(void){                             /* s->a[0] through a flexible array member */
  S *s = malloc(sizeof(S) + sizeof(void*) - 1);
  if( s ){ void *v = s->a[0]; (void)v; }
}
void flex_ptr(void){                               /* the same element through a pointer */
  S *s = malloc(sizeof(S) + sizeof(void*) - 1);
  if( s ){ void **pp = s->a; void *v = *pp; (void)v; }
}
void heap_array_index(void){                       /* p[1] of a heap array of 8-byte elements */
  long long *p = malloc(2*sizeof(long long) - 1);
  if( p ){ long long v = p[1]; (void)v; }
}
void heap_struct_member(void){                     /* a struct read through a pointer into a short object */
  M *m = malloc(sizeof(M) - 1);
  if( m ){ long long v = m->x; (void)v; }
}
void char_buf_cast(void){                          /* an 8-byte read at the end of a byte buffer */
  unsigned char *b = malloc(15);
  if( b ){ long long v = *(long long*)(b + 8); (void)v; }
}
void flex_nondet_index(void){                      /* a nondet index into a flexible array */
  unsigned k;
  S *s = malloc(sizeof(S) + 2*sizeof(void*) - 1);
  if( s && k < 2 ){ void *v = s->a[k]; (void)v; }
}
void flex_write(void){                             /* a write to the partial element */
  S *s = malloc(sizeof(S) + sizeof(void*) - 1);
  if( s ){ s->a[0] = 0; }
}
void flex_zero_entries(void){                      /* control: no element at all */
  S *s = malloc(sizeof(S));
  if( s ){ void *v = s->a[0]; (void)v; }
}
void flex_exact(void){                             /* control: exactly one element: defined */
  S *s = malloc(sizeof(S) + sizeof(void*));
  if( s ){ void *v = s->a[0]; (void)v; }
}
