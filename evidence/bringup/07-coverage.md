# §1.7 Coverage (2026-11-08)

- **Command:** `cbmc <program> <CHECKS minus --unwinding-assertions> --cover location`, which reports each basic block with its source lines as SATISFIED or FAILED. (CBMC refuses `--cover` together with unwinding assertions.)
- tools/prove.py counts a line of the function under proof as uncovered if any block containing it is FAILED. A line whose `if` is reached but whose body is not therefore still counts as uncovered.
- Under DFCC enforcement the function's body is renamed `<fn>_wrapped_for_contract_checking`, and coverage is read from that body.
- **The deliberately unreachable line:** `tools/tests/test_tools.py -k coverage` puts `if( x>20 && x<15 ){ r = 2; }` in a toy and flags line 33 as `sqlite3.c:33`. Unexplained, the coverage RESULT fails; explained in NOTES.md, it passes. An enforced toy function shows no false gaps.
