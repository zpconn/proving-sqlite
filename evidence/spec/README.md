# evidence/spec: the file format document and checks of proofs/spec/record_format.h

- `fileformat2.html`: SQLite's file format document at the pin, extracted unchanged from
  `https://www.sqlite.org/2026/sqlite-doc-3530400.zip`, fetched 2026-11-09 and dated 2026-07-24 inside the zip, the 3.53.4
  release date.
  - zip sha256: `a1d0f5de57485d062796ed7e67daff0758b50d00001a0f233a2c15aaf40bbdc8`;
  - fileformat2.html sha256: `905067afacc30583c9ee86778b532094cc1830c7ec7b5f019bcfd2eb9ded97a2`.
  - The serial type table is in section 2.1, "Record Format". Its rows 10,11 give Content Size "variable".
- `spec_test.c`: a native test, *tested* evidence, not a proof. It compares `sqlite3VdbeSerialGet` in upstream/sqlite3.c with
  `ref_serial_get` in proofs/spec/record_format.h over 2,000,000 random and boundary inputs:
  - serial types 0–139, plus 11 large ones up to 2^32−1;
  - NaN, infinity, all-zero and all-ones bytes.
- Result (`spec_test.txt`): 2,000,000 checks, 0 mismatches, under ASan and UBSan.
  - The test can fail: with row 5's size changed from 6 to 5 in a copy of the spec, it gave 8,659 mismatches.
  - Build: `gcc -O1 -fsanitize=address,undefined -fno-sanitize-recover=undefined -I upstream -I proofs -o spec_test evidence/spec/spec_test.c -lm -lpthread -ldl`.
