#ifndef CONTRACT_VDBERECORDDECODEINT_H
#define CONTRACT_VDBERECORDDECODEINT_H
i64 contract_vdbeRecordDecodeInt(u32 serial_type, const u8 *aKey)
  __CPROVER_requires(serial_type > 6 || __CPROVER_r_ok(aKey,
    serial_type <= 1 ? 1 : serial_type <= 4 ? serial_type :
    serial_type == 5 ? 6 : 8))
  __CPROVER_assigns();
#endif
