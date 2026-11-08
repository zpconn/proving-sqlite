#!/usr/bin/env python3
"""Checkpoint 0, decision C6: what a reviewer session sees inside the new bubblewrap sandbox. Starts one real
claude reviewer session (sessions.toml's command line, through campaign.py's runner) in a scratch detached worktree
under ../proving-sqlite-wt/, after planting a marker in the host /tmp, and asks it to run fixed probes.
Writes sandbox_results.json. Usage: sandbox_check.py"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(REPO, 'tools'))
import campaign as C  # noqa: E402
from wait_check import FakeState  # noqa: E402

P = C.P(REPO)
ST = FakeState()
home = os.path.expanduser('~')
wt = os.path.join(P.wt, 'sandbox-r1')
if os.path.isdir(wt):
    C.git(['worktree', 'remove', '--force', wt], cwd=REPO, check=False)
C.git(['worktree', 'add', '-q', '--detach', wt, 'HEAD'], cwd=REPO)
marker = '/tmp/c6-host-marker-%d' % os.getpid()
open(marker, 'w').write('host /tmp\n')
probes = [
    ('host /tmp marker visible', 'test -e %s && echo VISIBLE || echo HIDDEN' % marker),
    ('~/.codex/sessions visible', 'ls %s/.codex/sessions 2>/dev/null | head -1 | grep -q . && echo VISIBLE || echo HIDDEN' % home),
    ('state/ visible', 'test -e %s/state/state.json && echo VISIBLE || echo HIDDEN' % P.wt),
    ('other worktree C-01 visible', 'test -e %s/C-01/proofs && echo VISIBLE || echo HIDDEN' % P.wt),
    ('primary checkout files visible', 'test -e %s/GOAL.md && echo VISIBLE || echo HIDDEN' % REPO),
    ('git diff main...HEAD works', 'git diff --stat main...HEAD >/dev/null 2>&1 && echo WORKS || echo FAILS'),
    ('own worktree writable', 'touch own-write.txt 2>/dev/null && echo WRITABLE || echo READONLY'),
    ('git dir writable', 'touch %s/.git/sandbox-probe 2>/dev/null && echo WRITABLE || echo READONLY' % REPO),
    ('~/.claude writable', 'touch %s/.claude/sandbox-probe 2>/dev/null && echo WRITABLE && rm -f %s/.claude/sandbox-probe || echo READONLY' % (home, home)),
]
prompt = ('Run each of these shell commands exactly as written, one at a time, and append "<number>: <its output>" to '
          'probes.txt in the current directory. Do not try to work around any result.\n' +
          '\n'.join('%d. `%s`' % (i + 1, c) for i, (_, c) in enumerate(probes)) + '\nThen reply done.\n')
sess = C.load_sessions(REPO)
v, m, e, vcfg = C.role_config(sess, 'reviewer', 'standard')
job = C.new_job(ST, 'sandbox-c6', role='reviewer', card=None, round=0)
C.Campaign(P).start_session(ST, job, v, m, 'low', vcfg, wt, prompt)
t0 = time.time()
while time.time() - t0 < 900 and C.job_exit(job) is None and C.job_alive(job):
    time.sleep(5)
os.remove(marker)
out = open(os.path.join(wt, 'probes.txt')).read() if os.path.exists(os.path.join(wt, 'probes.txt')) else ''
res = {'argv': json.load(open(os.path.join(job['dir'], 'cmd.json')))['argv'], 'exit': C.job_exit(job), 'probes.txt': out,
       'probes': [name for name, _ in probes], 'job': job['dir'], 'usage': C.usage_of(job)[0]}
json.dump(res, open(os.path.join(HERE, 'sandbox_results.json'), 'w'), indent=1)
print(out)
print('RESULT sandbox-check %s' % ('done' if out else 'no probes.txt'))
