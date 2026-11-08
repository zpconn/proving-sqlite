int g_entry(int x);
int c_g(int x) __CPROVER_requires(x > -1000 && x < 1000) __CPROVER_ensures(__CPROVER_return_value == 2 * x);
int main(void) { int x; __CPROVER_assume(x > -1000 && x < 1000); int r = g_entry(x); __CPROVER_assert(r == 2*x, "r==2x"); return 0; }
