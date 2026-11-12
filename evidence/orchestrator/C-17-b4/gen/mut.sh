#!/bin/bash
cd /home/zpconn/code/proving-sqlite-wt/C-17
for m in base M-054 M-055 M-056; do
  ov=overlay; [ $m != base ] && ov=tmp/mut/$m
  nice -n 10 python3 tools/prove.py prove --card-dir tmp/mutcard/C-17 --config lp64-le --overlay $ov --build-dir tmp/mutbuild/$m > tmp/mut/$m.log 2>&1
  echo "== $m"; grep RESULT tmp/mut/$m.log
  grep -h FAILURE tmp/mutbuild/$m/lp64-le/*.cbmc | sed -E 's/^\[([^]]*)\] (line [0-9]+) ([^:]*).*/\1 \2 \3/' | cut -c1-150 | sort | uniq -c
done
