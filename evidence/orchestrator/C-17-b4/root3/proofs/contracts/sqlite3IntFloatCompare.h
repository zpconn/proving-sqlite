#ifndef CONTRACT_SQLITE3INTFLOATCOMPARE_H
#define CONTRACT_SQLITE3INTFLOATCOMPARE_H

int contract_sqlite3IntFloatCompare(i64 i, double r)
  __CPROVER_assigns()
  __CPROVER_ensures(-1 <= __CPROVER_return_value && __CPROVER_return_value <= 1);

#endif
