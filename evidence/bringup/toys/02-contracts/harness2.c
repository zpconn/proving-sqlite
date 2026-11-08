/* SQLite's static g, as goto-cc --export-file-local-symbols names it */
int __CPROVER_file_local_lib_c_g(int x);
int c_g(int x) __CPROVER_requires(x > -1000 && x < 1000) __CPROVER_ensures(__CPROVER_return_value == 2 * x);
int c_g_false(int x) __CPROVER_requires(x > -1000 && x < 1000) __CPROVER_ensures(__CPROVER_return_value == 3 * x);
int main(void) { int x; return __CPROVER_file_local_lib_c_g(x); }
