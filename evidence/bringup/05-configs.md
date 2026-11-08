# §1.5 Configurations (2026-11-08)

`proofs/CONFIGS`: `lp64-le -m64`; `ilp32-le -m32`; `lp64-be --big-endian -DSQLITE_BYTEORDER=4321`. Rerun: `toys/05-configs/run.sh` (output `result.txt`) and `make probe` (output `05-probe.txt`).

- **Probe harness** (`tools/probe/config_probe.c`, built with the overlay as every proof is). All 7 assertions pass on each configuration: pointer and long width, SQLITE_PTRSIZE, the byte order of memory, SQLITE_BYTEORDER, SQLITE_BIGENDIAN, and that sqlite3Get4byte decodes big-endian. The gate runs the probe.
- **Preprocessing the overlay:** lp64-le and ilp32-le give SQLITE_BYTEORDER=1234 and a sqlite3Get4byte body of `memcpy` + `__builtin_bswap32`. lp64-be gives 4321 and `memcpy` with no swap. Pointer sizes are 8, 4 and 8.
- **Wrong configurations fail the probe:** `-m64 --big-endian`, because goto-cc's `-m64` silently resets the architecture to x86_64 little-endian; `--big-endian` without `-DSQLITE_BYTEORDER=4321`, because SQLite then takes its little-endian bswap branch on big-endian memory and sqlite3Get4byte decodes wrong; `-m64` named ilp32; `-m32` named lp64.
- cbmc takes word size and byte order from the goto binary. Its own `--big-endian` flag does not override a binary built little-endian, so CONFIGS flags go to goto-cc only.
- ilp32-le needs the 32-bit libc headers (`gcc-multilib`, installed by Zach on 2026-11-08).
