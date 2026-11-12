#ifndef CONTRACT_SQLITE3ISNAN_H
#define CONTRACT_SQLITE3ISNAN_H

int contract_sqlite3IsNaN(double x)
  __CPROVER_assigns()
  __CPROVER_ensures((__CPROVER_return_value != 0) == (x != x));

#endif
