#ifndef CONTRACT_SQLITE3VDBESERIALGET_H
#define CONTRACT_SQLITE3VDBESERIALGET_H
void contract_sqlite3VdbeSerialGet(
  const unsigned char *buf, u32 serial_type, Mem *pMem)
  __CPROVER_requires(__CPROVER_w_ok(pMem, sizeof(Mem)))
  __CPROVER_requires(serial_type < 1 || serial_type > 7 ||
    __CPROVER_r_ok(buf, serial_type <= 4 ? serial_type :
      serial_type == 5 ? 6 : 8))
  __CPROVER_assigns(pMem->u, pMem->flags, pMem->n, pMem->z)
  __CPROVER_ensures(serial_type == 0 || serial_type == 11 ?
    pMem->flags == MEM_Null :
    serial_type == 10 ? pMem->flags == (MEM_Null|MEM_Zero) :
    serial_type == 7 ? (pMem->flags == MEM_Null || pMem->flags == MEM_Real) :
    serial_type < 12 ? pMem->flags == MEM_Int :
    pMem->flags == ((serial_type & 1) ? (MEM_Str|MEM_Ephem) : (MEM_Blob|MEM_Ephem)))
  __CPROVER_ensures(serial_type != 10 || (pMem->n == 0 && pMem->u.nZero == 0))
  __CPROVER_ensures(serial_type < 12 ||
    (pMem->z == (char *)buf && pMem->n == (serial_type-12)/2));
#endif
