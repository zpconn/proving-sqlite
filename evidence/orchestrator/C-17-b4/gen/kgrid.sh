#!/bin/bash
# kgrid.sh <K> <root>: every proof of bound K (b0n1..b0nK, b1n2..b1nK) with the K-field contract, on $CFG
K=$1; export R2=$2; cd /home/zpconn/code/proving-sqlite-wt/C-17
for b in 0 1; do for n in $(seq $((1+b)) $K); do bash tmp/gen/lpipe.sh K$K-${CFG:-lp64-le}-b${b}n$n $b $n tmp/grid2/c$K.h; done; done
