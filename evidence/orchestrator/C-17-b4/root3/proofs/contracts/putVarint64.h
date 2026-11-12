int contract_putVarint64(unsigned char *p, u64 v)
  __CPROVER_requires(__CPROVER_w_ok(p, 9))
  __CPROVER_assigns(__CPROVER_object_upto(p, 9))
  __CPROVER_ensures(1 <= __CPROVER_return_value && __CPROVER_return_value <= 9);
