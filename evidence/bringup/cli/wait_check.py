#!/usr/bin/env python3
"""Checkpoint 0, decision D: what a Codex builder session spends waiting on a 15-minute command.

Runs two builder sessions at once (gpt-6-astra, high effort: the standard builder tier), each in a scratch worktree
under ../proving-sqlite-wt/wait-*, through campaign.py's own runner and usage counting:
  before: the codex command line in sessions.toml at commit d26a1d4 (checkpoint 0) and the long-run advice the
          builder prompt then gave (foreground, poll until it ends);
  after:  the codex command line in the working tree's tools/sessions.toml and the advice in campaign.py's
          LONG_RUN_CODEX (one write_stdin call that blocks until the command exits).
Writes wait_results.json and prints each session's token total and the tool calls it made while waiting.
Usage: wait_check.py [--only before,after] [--seconds 900]
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import threading
import time

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(REPO, 'tools'))
import campaign as C  # noqa: E402

P = C.P(REPO)
BEFORE_COMMIT = 'd26a1d4'
BEFORE_ADVICE = ('CBMC runs can take 10 minutes per configuration. In this sandbox a command\'s background children are '
                 'killed when the command returns, so run long commands in the foreground with output in a file and let '
                 'them finish, or give them a timeout longer than the run. Trust only output that ends with its last line.')
results = {}
lock = threading.Lock()


class FakeState:
    def __init__(self):
        self.p = P
        self.d = {'job_seq': int(time.time()) % 100000, 'jobs': {}}
        self.p.jobs = os.path.join(HERE, 'jobs')
        os.makedirs(self.p.jobs, exist_ok=True)

    def journal(self, kind, **kw):
        pass


ST = FakeState()


def worktree(name):
    wt = os.path.join(P.wt, 'wait-' + name)
    if os.path.isdir(wt):
        C.git(['worktree', 'remove', '--force', wt], cwd=REPO, check=False)
    C.git(['worktree', 'add', '-q', '--detach', wt, 'HEAD'], cwd=REPO)
    return wt


def tool_calls(rollout):
    out = []
    for e in C.read_jsonl(rollout):
        p = e.get('payload') or {}
        if e.get('type') == 'response_item' and p.get('type') in ('function_call', 'custom_tool_call'):
            out.append([e.get('timestamp'), p.get('name'), str(p.get('arguments') or p.get('input'))[:160]])
    return out


def run(which, seconds):
    if which == 'before':
        sess = tomllib.loads(C.git(['show', '%s:tools/sessions.toml' % BEFORE_COMMIT], cwd=REPO))
        advice = BEFORE_ADVICE
    else:
        sess = C.load_sessions(REPO)
        advice = C.LONG_RUN_CODEX
    vendor, model, effort, vcfg = C.role_config(sess, 'builder', 'standard')
    wt = worktree(which)
    prompt = ('You are a builder session being measured on how it waits for a long command. Run this command, which '
              'takes %d seconds: `sleep %d; echo LONG-RUN-FINISHED`. %s When it has finished, write the line it printed '
              'into long.txt. Then reply done.\n' % (seconds, seconds, advice))
    with lock:
        job = C.new_job(ST, 'wait-%s' % which, role='builder', card=None, round=0)
    C.Campaign(P).start_session(ST, job, vendor, model, effort, vcfg, wt, prompt)
    t0 = time.time()
    while time.time() - t0 < seconds + 1800:
        if C.job_exit(job) is not None or not C.job_alive(job):
            break
        time.sleep(10)
    ex = C.job_exit(job)
    u, sid = C.usage_of(job)
    ro = job.get('rollout') or C.codex_rollout(sid)
    calls = tool_calls(ro) if ro else []
    lt = os.path.join(wt, 'long.txt')
    rec = {'exit': ex, 'usage': u, 'seconds': round((ex or {}).get('ended', time.time()) - job['started']),
           'long_txt': open(lt).read().strip() if os.path.exists(lt) else None, 'tool_calls': len(calls),
           'calls': calls, 'argv': vcfg['start'], 'model': model, 'effort': effort, 'advice': advice,
           'job': job['dir'], 'rollout': ro}
    with lock:
        results[which] = rec
        json.dump(results, open(os.path.join(HERE, 'wait_results.json'), 'w'), indent=1, sort_keys=True)
    print('[%s] total %d tokens, %d tool calls, %ds, long.txt=%r' % (which, u['total'], len(calls), rec['seconds'], rec['long_txt']))
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='before,after')
    ap.add_argument('--seconds', type=int, default=900)
    a = ap.parse_args()
    ths = [threading.Thread(target=run, args=(w, a.seconds)) for w in a.only.split(',')]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    for w in a.only.split(','):
        r = results.get(w) or {}
        print('RESULT wait %s %s tokens %s tool calls' % (w, (r.get('usage') or {}).get('total'), r.get('tool_calls')))


if __name__ == '__main__':
    main()
