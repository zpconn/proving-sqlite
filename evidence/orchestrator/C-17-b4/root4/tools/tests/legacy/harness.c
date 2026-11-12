/* harnesses for the legacy validation toys: every pointer malloc'd at the size the requires names, never larger */
void h_forget(void) { Cell *p = malloc(sizeof(Cell)); __CPROVER_assume(p); t_forget(p); }
void h_callee_frame(void) { unsigned n; Cell *a = malloc(4 * sizeof(Cell)), *o = malloc(sizeof(Cell));
  __CPROVER_assume(a && o); t_callee_frame(a, o, n); }
void h_alias_frame(void) { unsigned n; Cell *a = malloc(4 * sizeof(Cell)), *b = malloc(sizeof(Cell));
  __CPROVER_assume(a && b); t_alias_frame(a, b, n); }
void h_invariant(void) { unsigned n; t_invariant(n); }
void h_decreases(void) { unsigned n; t_decreases(n); }
void h_after(void) { unsigned n; t_after(n); }
void h_oob(void) { unsigned n; __CPROVER_assume(n >= 1 && n <= 4); Cell *a = malloc(n * sizeof(Cell));
  __CPROVER_assume(a); t_oob(a, n); }
void h_callee_requires(void) { unsigned n; __CPROVER_assume(n >= 1 && n <= 4); Cell *a = malloc(n * sizeof(Cell));
  __CPROVER_assume(a); t_callee_requires(a, n); }
void h_flex(void) { int n; __CPROVER_assume(n >= 1 && n <= 4); Flex *s = malloc(sizeof(Flex) + (size_t)n * sizeof(void *));
  __CPROVER_assume(s); t_flex(s, n); }
void h_fresh(void) { int *x = malloc(sizeof(int)), *y = malloc(sizeof(int)); __CPROVER_assume(x && y); t_fresh(x, y); }
void h_two(void) { int *p = malloc(sizeof(int)), *q = malloc(sizeof(int)); __CPROVER_assume(p && q); two(p, q); }
void h_carried(void) { Cell *a = malloc(4 * sizeof(Cell)); __CPROVER_assume(a); t_carried(a); }
void h_glob(void) { t_glob(); }
void h_static(void) { Cell *a = malloc(2 * sizeof(Cell)); __CPROVER_assume(a); t_static(a); }
