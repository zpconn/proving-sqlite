int f(int x) { return x + 1; }
int c_true(int x) __CPROVER_requires(x < 100) __CPROVER_ensures(__CPROVER_return_value == x + 1);
int main(void) { int x; __CPROVER_assume(x >= 100 && x < 1000); return f(x); }
