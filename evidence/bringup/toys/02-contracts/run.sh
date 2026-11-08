#!/bin/bash
# §1.2: do --enforce-contract f/c and --replace-call-with-contract f/c take clauses from a separate declaration c?
# Run from this directory. Prints one line per experiment; expected verdict in brackets.
cd "$(dirname "$0")"; T=$(mktemp -d); trap 'rm -rf $T' EXIT
run(){ n=$1 exp=$2 src=$3; shift 3; def=""; [ "$src" = toy.c+caller ] && { src=toy.c; def=-DCALL_CALLER; }
  goto-cc $def $src -o $T/$n.0.goto || return 1
  [ -n "$LIB" ] && { goto-cc $T/$n.0.goto $T/libx.goto -o $T/$n.l.goto; mv $T/$n.l.goto $T/$n.0.goto; }
  goto-instrument --dfcc main "$@" $T/$n.0.goto $T/$n.1.goto > $T/$n.instr.log 2>&1
  cbmc $T/$n.1.goto > $T/$n.log 2>&1
  printf '%-30s [expect %-10s] %-26s %s\n' "$n" "$exp" "$(grep ^VERIF $T/$n.log)" "$(grep -E '^\[.*FAILURE' $T/$n.log | head -1)"; }
echo "== non-static f, clauses on separate declarations c_true / c_false / c_weak (toy.c)"
run A_enforce_true   SUCCESSFUL toy.c        --enforce-contract f/c_true
run B_enforce_false  FAILED     toy.c        --enforce-contract f/c_false
run C_replace_weak   FAILED     toy.c+caller --replace-call-with-contract f/c_weak
run D_no_replace     SUCCESSFUL toy.c+caller
run E_replace_true   SUCCESSFUL toy.c+caller --replace-call-with-contract f/c_true
run F_callsite_req   FAILED     bad_call.c   --replace-call-with-contract f/c_true
echo "== static g in another TU (lib.c), built with --export-file-local-symbols, as overlay/sqlite3.c will be"
goto-cc --export-file-local-symbols lib.c -o $T/libx.goto; LIB=1
run H_static_true    SUCCESSFUL harness2.c   --enforce-contract __CPROVER_file_local_lib_c_g/c_g
run I_static_false   FAILED     harness2.c   --enforce-contract __CPROVER_file_local_lib_c_g/c_g_false
run J_static_replace SUCCESSFUL caller2.c    --replace-call-with-contract __CPROVER_file_local_lib_c_g/c_g
run K_static_weak    FAILED     caller2_weak.c --replace-call-with-contract __CPROVER_file_local_lib_c_g/c_g
