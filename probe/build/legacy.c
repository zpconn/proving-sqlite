/* T-006 probe: generated legacy unit for C-15 proof unpack */
#include "/home/zpconn/code/proving-sqlite-wt/wip-t006-c15/proofs/C-15/harness.c"
/* from proofs/contracts/sqlite3VdbeRecordUnpack.h */
void sqlite3VdbeRecordUnpack(int nKey, const void *pKey, UnpackedRecord *p)
  __CPROVER_requires(__CPROVER_w_ok(p, sizeof(UnpackedRecord)))
  __CPROVER_requires(__CPROVER_r_ok(p->pKeyInfo,
    offsetof(KeyInfo, db) + sizeof(sqlite3 *)))
  __CPROVER_requires(__CPROVER_w_ok(p->aMem, sizeof(Mem) * p->nField))
  __CPROVER_requires(nKey >= 0 && __CPROVER_r_ok(pKey, (size_t)(nKey > 0 ? nKey : 1)))
  __CPROVER_assigns(p->default_rc, p->nField,
    __CPROVER_object_upto(p->aMem, sizeof(Mem) * p->nField))
  __CPROVER_ensures(p->default_rc == 0)
  __CPROVER_ensures(p->nField <= __CPROVER_old(p->nField));
/* from proofs/contracts/sqlite3GetVarint32.h */
u8 sqlite3GetVarint32(const unsigned char *p, u32 *v)
  __CPROVER_requires(__CPROVER_r_ok(p, 9))
  __CPROVER_requires(__CPROVER_w_ok(v, sizeof(*v)))
  __CPROVER_assigns(*v)
  __CPROVER_ensures(1 <= __CPROVER_return_value && __CPROVER_return_value <= 9);
/* from proofs/contracts/sqlite3VdbeSerialGet.h */
void sqlite3VdbeSerialGet(
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
/* from proofs/contracts/sqlite3VdbeSerialTypeLen.h */
u32 sqlite3VdbeSerialTypeLen(u32 serial_type)
  __CPROVER_assigns()
  __CPROVER_ensures(__CPROVER_return_value <= 2147483641U);
/* from proofs/contracts/sqlite3VdbeMemSetNull.h */
void sqlite3VdbeMemSetNull(Mem *pMem)
  __CPROVER_requires(__CPROVER_w_ok(pMem, offsetof(Mem, flags) + sizeof(pMem->flags)))
  __CPROVER_requires(!VdbeMemDynamic(pMem))
  __CPROVER_assigns(pMem->flags)
  __CPROVER_ensures(pMem->flags == MEM_Null);
