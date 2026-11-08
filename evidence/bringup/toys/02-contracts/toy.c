/* f has no clauses on its own definition. Clauses live on separate declarations. */
int f(int x) { return x + 1; }

/* c_true: true of f. */
int c_true(int x)
  __CPROVER_requires(x < 100)
  __CPROVER_ensures(__CPROVER_return_value == x + 1);

/* c_false: its ensures is false of f. */
int c_false(int x)
  __CPROVER_requires(x < 100)
  __CPROVER_ensures(__CPROVER_return_value == x + 2);

/* c_weak: true of f but weaker, so a caller relying on it can't prove r == x+1. */
int c_weak(int x)
  __CPROVER_requires(x < 100)
  __CPROVER_ensures(__CPROVER_return_value > x);

int caller(int x) {
  int r = f(x);
  __CPROVER_assert(r == x + 1, "caller: r == x+1");
  return r;
}

int main(void) {
  int x;
  __CPROVER_assume(x < 100);
#ifdef CALL_CALLER
  caller(x);
#else
  f(x);
#endif
  return 0;
}
