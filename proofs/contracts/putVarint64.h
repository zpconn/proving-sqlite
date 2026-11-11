/* Value-dependent output size: seven bits per byte, capped at nine bytes.
** Keep this side-effect-free expression in requires and assigns: CBMC does
** not accept function calls in assigns target sizes. */
int contract_putVarint64(unsigned char *p, u64 v)
  __CPROVER_requires(__CPROVER_w_ok(p, (1 + (v >= ((u64)1 << 7)) + (v >= ((u64)1 << 14))
      + (v >= ((u64)1 << 21)) + (v >= ((u64)1 << 28))
      + (v >= ((u64)1 << 35)) + (v >= ((u64)1 << 42))
      + (v >= ((u64)1 << 49)) + (v >= ((u64)1 << 56)))))
  __CPROVER_assigns(__CPROVER_object_upto(p, (1 + (v >= ((u64)1 << 7)) + (v >= ((u64)1 << 14))
      + (v >= ((u64)1 << 21)) + (v >= ((u64)1 << 28))
      + (v >= ((u64)1 << 35)) + (v >= ((u64)1 << 42))
      + (v >= ((u64)1 << 49)) + (v >= ((u64)1 << 56)))))
  __CPROVER_ensures(1 <= __CPROVER_return_value && __CPROVER_return_value <= 9);
