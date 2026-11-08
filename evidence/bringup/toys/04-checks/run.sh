#!/bin/bash
# §1.4: each option in proofs/CHECKS fires on a toy that commits its UB.
# For each toy: run with all of CHECKS ("all"), then with only that option removed ("minus"), where CBMC 6 turns a
# check on by default the minus run also passes its --no- form. Expect: all = FAILED by the named check; minus = no
# failure of that class. UNWINDING runs with --unwind 5. FLOAT_TO_INT uses tools/prove.py's second pass, reproduced here.
cd "$(dirname "$0")"; ROOT=../../../..
OPTS=$(grep -E '^--' $ROOT/proofs/CHECKS | tr '\n' ' ')
run(){ name=$1 opt=$2 neg=$3 extra=$4
  all=$(cbmc -D$name ub.c $OPTS $extra 2>&1 | grep -E '^\[.*FAILURE' | sed 's/^\[[^]]*\] line [0-9]* //' | head -1)
  minus=$(cbmc -D$name ub.c $(echo " $OPTS " | sed "s/ $opt / /") $neg $extra 2>&1 | grep -E '^\[.*FAILURE|^VERIF' | sed 's/^\[[^]]*\] line [0-9]* //' | head -1)
  printf '%-18s %-26s\n    all:   %s\n    minus: %s\n' $name "$opt" "${all:-NO FAILURE}" "$minus"; }
run POINTER           --pointer-check           --no-pointer-check
run BOUNDS            --bounds-check            --no-bounds-check
run POINTER_OVERFLOW  --pointer-overflow-check  ""
run POINTER_PRIMITIVE --pointer-primitive-check --no-pointer-primitive-check
run SIGNED_OVERFLOW   --signed-overflow-check   --no-signed-overflow-check
run UNDEFINED_SHIFT   --undefined-shift-check   --no-undefined-shift-check
run NEG_SHIFT         --undefined-shift-check   --no-undefined-shift-check
run SHL_OVERFLOW      --signed-overflow-check   --no-signed-overflow-check
run DIV_BY_ZERO       --div-by-zero-check       --no-div-by-zero-check
run FLOAT_DIV_BY_ZERO --float-div-by-zero-check ""
run MALLOC_MAY_FAIL   --malloc-may-fail         --no-malloc-may-fail
run UNWINDING         --unwinding-assertions    --no-unwinding-assertions  "--unwind 5"
echo "FLOAT_TO_INT       %float-to-int (second pass: --conversion-check, float properties only)"
ids=$(cbmc -DFLOAT_TO_INT ub.c $OPTS --conversion-check --show-properties 2>&1 | grep -B2 -E 'float to (signed|unsigned) integer type conversion' | grep -oE 'Property [^:]+' | awk '{print $2}')
echo "    float-to-int properties: $ids"
props=$(for i in $ids; do printf -- '--property %s ' $i; done)
echo "    pass 2: $(cbmc -DFLOAT_TO_INT ub.c $OPTS --conversion-check $props 2>&1 | grep -E '^\[.*FAILURE' | sed 's/^\[[^]]*\] line [0-9]* //' | head -1)"
echo "    pass 1 only (CHECKS options): $(cbmc -DFLOAT_TO_INT ub.c $OPTS 2>&1 | grep -E '^VERIF')"
