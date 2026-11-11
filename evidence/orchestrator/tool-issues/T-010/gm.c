#include <string.h>
#include <stdio.h>
#include <stdlib.h>
int main(int argc, char **argv){ (void)argv;
  size_t n = 64 + (size_t)argc; char *a = malloc(n), *b = malloc(n);
  memset(a, 0, n); memset(b, 0, n); a[40] = 0; b[40] = (char)0xff;
  int (*volatile f)(const void*, const void*, size_t) = memcmp;
  printf("%d %d\n", f(a, b, n), f(b, a, n)); return 0; }
