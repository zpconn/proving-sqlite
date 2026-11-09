/* proofs/spec/record_format.h: what a serial value decodes to (PROPERTIES.md P3). Written from SQLite's file
** format document, section 2.1 "Record Format", table "Serial Type Codes Of The Record Format": a copy is
** evidence/spec/fileformat2.html (sqlite-doc-3530400.zip). Each case cites its row of that table.
** Departures, where SQLite 3.53.4's code and not the table decides (PROPERTIES.md P3):
**   D1. A row 7 value whose bits are a NaN decodes as NULL.
**   D2. Rows 10,11 give "variable" Content Size; the code reads 0 bytes. 10 is NULL with MEM_Zero, n = 0 and
**       u.nZero = 0; 11 is NULL.
**   D3. For N >= 12 nothing is read: z points at the bytes (MEM_Ephem, not copied) and n is the length. */
#ifndef RECORD_FORMAT_H
#define RECORD_FORMAT_H

/* The bytes a decoder may read for type t: the Content Size column for rows 0-9, 0 for rows 10,11 (D2), and 0
** for N >= 12 (D3). */
static u32 ref_serial_bytes(u32 t){
  if( t>=1 && t<=4 ) return t;        /* rows 1-4: sizes 1, 2, 3, 4 */
  if( t==5 ) return 6;                /* row 5: size 6 */
  if( t==6 || t==7 ) return 8;        /* rows 6, 7: size 8 */
  return 0;                           /* rows 0, 8, 9: size 0; rows 10,11: D2; N >= 12: D3 */
}

/* The first n bytes of b as a big-endian unsigned number (rows 1-7 are all big-endian). */
static u64 ref_be(const unsigned char *b, u32 n){
  u64 u = 0;
  u32 k;
  for(k = 0; k < n; k++) u = (u << 8) | b[k];
  return u;
}

/* Rows 1-6: "a big-endian 8n-bit twos-complement integer", n = 1, 2, 3, 4, 6 or 8 bytes. */
static i64 ref_be_int(const unsigned char *b, u32 n){
  u64 u = ref_be(b, n), top = (u64)1 << (8*n - 1);
  if( (u & top)==0 ) return (i64)u;
  return -(i64)((top << 1) - 1 - u) - 1;  /* u - 2^(8n), without overflow; top << 1 wraps to 0 for n = 8 */
}

/* 1 if m holds what serial type t with bytes b decodes to, else 0. */
static int ref_serial_get(const unsigned char *b, u32 t, const Mem *m){
  u64 bits, got;
  if( t==0 ) return m->flags==MEM_Null;                                  /* row 0: NULL */
  if( t>=1 && t<=6 )                                                     /* rows 1-6: integers */
    return m->flags==MEM_Int && m->u.i==ref_be_int(b, ref_serial_bytes(t));
  if( t==7 ){                                                            /* row 7: IEEE 754 64-bit float */
    bits = ref_be(b, 8);
    if( ((bits >> 52) & 0x7ff)==0x7ff && (bits & 0xfffffffffffffULL)!=0 ) return m->flags==MEM_Null;  /* D1 */
    memcpy(&got, &m->u.r, sizeof(got));
    return m->flags==MEM_Real && got==bits;
  }
  if( t==8 || t==9 ) return m->flags==MEM_Int && m->u.i==(i64)(t - 8);  /* rows 8, 9: the integers 0, 1 */
  if( t==10 ) return m->flags==(MEM_Null|MEM_Zero) && m->n==0 && m->u.nZero==0;  /* rows 10,11: D2 */
  if( t==11 ) return m->flags==MEM_Null;                                 /* rows 10,11: D2 */
  if( t%2==0 )                                    /* row N >= 12 and even: a BLOB of (N-12)/2 bytes (D3) */
    return m->flags==(MEM_Blob|MEM_Ephem) && (const unsigned char *)m->z==b && m->n==(int)((t - 12)/2);
  /* row N >= 13 and odd: a string of (N-13)/2 bytes, its nul terminator not stored (D3) */
  return m->flags==(MEM_Str|MEM_Ephem) && (const unsigned char *)m->z==b && m->n==(int)((t - 13)/2);
}

#endif
