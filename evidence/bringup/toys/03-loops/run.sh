#!/bin/bash
# §1.3: inline loop contracts through PROOF(...), clauses in the order assigns, loop_invariant, decreases,
# applied by goto-instrument --dfcc main --apply-loop-contracts. Without unwinding: the loop must be abstracted.
cd "$(dirname "$0")"; T=$(mktemp -d); trap 'rm -rf $T' EXIT
run(){ n=$1 exp=$2; shift 2
  goto-cc "$@" loops.c -o $T/$n.0.goto || { echo "$n goto-cc failed"; return; }
  goto-instrument --dfcc main --apply-loop-contracts $T/$n.0.goto $T/$n.1.goto > $T/$n.i.log 2>&1 || { echo "$n instrument failed: $(tail -2 $T/$n.i.log)"; return; }
  cbmc $T/$n.1.goto > $T/$n.log 2>&1
  printf '%-14s [expect %-10s] %-26s %s\n' $n "$exp" "$(grep ^VERIF $T/$n.log)" "$(grep -E '^\[.*FAILURE' $T/$n.log | head -2 | tr '\n' ' ')"
  [ -n "$SHOW" ] && grep -E '^\[.*(loop_invariant|decreases|assigns)' $T/$n.log | head -6; }
SHOW=1 run while_good SUCCESSFUL -DWHILE -DWHILE_GOOD
run while_badinv FAILED     -DWHILE -DWHILE_BAD_INV
run while_baddec FAILED     -DWHILE -DWHILE_BAD_DEC
SHOW=1 run do_good    SUCCESSFUL -DDO_GOOD
run do_badinv    FAILED     -DDO_BAD_INV
run do_baddec    FAILED     -DDO_BAD_DEC
echo "== do-while with clauses after the condition, as GOAL.md says: does it parse?"
printf 'unsigned d(unsigned n){unsigned i=0; do { i++; } while (i < n) __CPROVER_assigns(i) __CPROVER_loop_invariant(i<=n) __CPROVER_decreases(n-i); return i;}\nint main(){unsigned n; d(n);}\n' > $T/after.c
goto-cc $T/after.c -o $T/after.goto 2>&1 | grep -E 'error' | sed 's|.*/after.c|after.c|'
echo "== unconstrained-assigns sanity: a loop writing a variable not in its assigns is caught"
printf 'unsigned w(unsigned n){unsigned i=0,s=0; while(i<n) __CPROVER_assigns(i) __CPROVER_loop_invariant(i<=n) __CPROVER_decreases(n-i) { s++; i++; } return s;}\nint main(){unsigned n; __CPROVER_assume(n<1000); w(n);}\n' > $T/asg.c
goto-cc $T/asg.c -o $T/asg.0.goto && goto-instrument --dfcc main --apply-loop-contracts $T/asg.0.goto $T/asg.1.goto >/dev/null 2>&1 && cbmc $T/asg.1.goto 2>&1 | grep -E '^VERIF|^\[.*FAILURE' | head -2
echo "== do-while invariant that holds only after the body (1 <= i): CBMC checks it before entry, so it fails"
sed 's/__CPROVER_loop_invariant(i < n) __CPROVER_decreases(n - i))/__CPROVER_loop_invariant(1 <= i \&\& i <= n) __CPROVER_decreases(n - i))/' loops.c > $T/late.c
cp $T/late.c ./.late.c && goto-cc -DDO_GOOD ./.late.c -o $T/late.0.goto && rm -f ./.late.c && goto-instrument --dfcc main --apply-loop-contracts $T/late.0.goto $T/late.1.goto >/dev/null 2>&1 && cbmc $T/late.1.goto 2>&1 | grep -E '^VERIF|loop_invariant_base.*FAILURE' | head -2
