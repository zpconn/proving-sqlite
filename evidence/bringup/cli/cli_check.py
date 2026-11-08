#!/usr/bin/env python3
"""§1.10 checks of the real CLIs, run through tools/campaign.py's own machinery (sessions.toml commands, the
detached job runner, usage parsing, kill and resume), in scratch worktrees under ../proving-sqlite-wt/cli-*.

  1. a session runs to the end without prompts, on the subscription login, with no API-key variable set;
  2. its token usage can be read while it runs;
  3. a killed session resumes and carries on;
  4. it can run a 15-minute command and read the result, following the long-run rule;
  5. (codex) it can run CBMC and write in its worktree, but can't write .git or reach the network;
     (claude) the bubblewrap sandbox: it can write its worktree but not the project.
Writes results.json and a log per check into this directory. Usage: cli_check.py [--only 1,2,...] [--vendor codex]
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(REPO, 'tools'))
import campaign as C  # noqa: E402

P = C.P(REPO)
SESS = C.load_sessions(REPO)
ROLE = {'codex': ('builder', 'standard'), 'claude': ('reviewer', 'standard')}
EFFORT = {'codex': 'low', 'claude': 'low'}
results = {}
lock = threading.Lock()


def note(vendor, check, **kw):
    with lock:
        results.setdefault(vendor, {}).setdefault(check, {}).update(kw)
        json.dump(results, open(os.path.join(HERE, 'results.json'), 'w'), indent=1, sort_keys=True)
    print('[%s %s] %s' % (vendor, check, json.dumps(kw)[:300]))
    sys.stdout.flush()


def worktree(name):
    wt = os.path.join(P.wt, 'cli-' + name)
    if os.path.isdir(wt):
        C.git(['worktree', 'remove', '--force', wt], cwd=REPO, check=False)
    C.git(['worktree', 'add', '-q', '--detach', wt, 'HEAD'], cwd=REPO)
    return wt


class FakeState:
    """Enough of campaign.State for new_job/spawn_runner: jobs live under evidence/bringup/cli/jobs/."""
    def __init__(self):
        self.p = P
        self.d = {'job_seq': int(time.time()) % 100000, 'jobs': {}}
        self.p.jobs = os.path.join(HERE, 'jobs')
        os.makedirs(self.p.jobs, exist_ok=True)

    def journal(self, kind, **kw):
        pass


ST = FakeState()


def start(vendor, wt, prompt, resume_of=None, tag=''):
    role, tier = ROLE[vendor]
    v, model, _, vcfg = C.role_config(SESS, role, tier)
    assert v == vendor
    with lock:
        job = C.new_job(ST, 'cli-%s%s' % (vendor, tag), role=role, card=None, round=0)
    C.Campaign(P).start_session(ST, job, vendor, model, EFFORT[vendor], vcfg, wt, prompt, resume_of=resume_of)
    return job


def wait(job, timeout, poll=None):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if poll:
            poll(job)
        if C.job_exit(job) is not None or not C.job_alive(job):
            break
        time.sleep(5)
    ex = C.job_exit(job)
    u, sid = C.usage_of(job)
    job['usage'], job['cli_session'] = u, sid or job.get('cli_session')
    return ex, u


def read(wt, rel):
    p = os.path.join(wt, rel)
    return open(p).read().strip() if os.path.exists(p) else None


def check1(vendor):
    wt = worktree('%s-1' % vendor)
    login = subprocess.run(SESS['vendors'][vendor]['login_check'], capture_output=True, text=True)
    job = start(vendor, wt, 'Run this shell command and nothing else: `env | grep -cE "API_KEY|AUTH_TOKEN" > keys.txt; '
                'echo hello > hello.txt`. Then reply with the single word done.', tag='-1')
    ex, u = wait(job, 600)
    ev = C.read_jsonl(os.path.join(job['dir'], 'out.jsonl'))
    extra = {}
    if vendor == 'claude':
        init = [e for e in ev if e.get('type') == 'system' and e.get('subtype') == 'init']
        extra['apiKeySource'] = init[0].get('apiKeySource') if init else None
        extra['permissionMode'] = init[0].get('permissionMode') if init else None
    else:
        ro = job.get('rollout') or C.codex_rollout(job.get('cli_session'))
        for e in C.read_jsonl(ro) if ro else []:
            if e.get('type') == 'turn_context':
                pl = e['payload']
                extra['sandbox_policy'] = pl.get('sandbox_policy')
                extra['approval_policy'] = pl.get('approval_policy')
                break
        extra['rollout'] = ro
    note(vendor, '1-runs-headless', exit=ex, hello=read(wt, 'hello.txt'), api_key_vars_seen_by_session=read(wt, 'keys.txt'),
         login_check=' '.join(SESS['vendors'][vendor]['login_check']), login_output=(login.stdout + login.stderr).strip()[:400],
         usage=u, job=job['dir'], **extra)


def check2(vendor):
    wt = worktree('%s-2' % vendor)
    samples = []
    job = start(vendor, wt, 'Do these steps in order, one shell command per step: (1) `echo one > a.txt` (2) `sleep 40` '
                '(3) `echo two >> a.txt` (4) `sleep 40` (5) `echo three >> a.txt`. Then reply done.', tag='-2')

    def poll(j):
        u, _ = C.usage_of(j)
        samples.append([round(time.time() - j['started']), u['total']])
    ex, u = wait(job, 900, poll)
    mid = [s for s in samples if s[1] > 0 and C.job_exit(job) is None]
    running = [s for s in samples[:-1] if s[1] > 0]
    note(vendor, '2-usage-while-running', exit=ex, samples=samples, nonzero_before_end=len(running), final=u,
         distinct_values_while_running=len(set(s[1] for s in samples[:-1])), file=read(wt, 'a.txt'), job=job['dir'])


def descendants(pid):
    kids = {}
    for d in os.listdir('/proc'):
        if d.isdigit():
            try:
                pp = int(open('/proc/%s/stat' % d).read().rsplit(')', 1)[1].split()[1])
                kids.setdefault(pp, []).append(int(d))
            except (OSError, ValueError, IndexError):
                pass
    out, todo = [], [pid]
    while todo:
        x = todo.pop()
        for k in kids.get(x, []):
            out.append(k)
            todo.append(k)
    return out


def check3(vendor):
    wt = worktree('%s-3' % vendor)
    job = start(vendor, wt, 'Remember this code word: PELICAN-7. Do these steps in order: (1) run `sleep 90` as a single '
                'foreground shell command and wait for it; (2) then write the code word into the file resume.txt. '
                'Then reply done.', tag='-3a')
    killed_at = None
    t0 = time.time()
    while time.time() - t0 < 300:
        cp = os.path.join(job['dir'], 'child.pid')
        u, sid = C.usage_of(job)
        if sid and u['total'] > 0 and os.path.exists(cp) and time.time() - job['started'] > 25:
            break
        time.sleep(3)
    cp = os.path.join(job['dir'], 'child.pid')
    try:
        cpid = int(open(cp).read())
        # the CLI and everything it started (bwrap and codex's node wrapper fork children), leaving the runner
        for pid in [cpid] + descendants(cpid):
            try:
                os.kill(pid, 9)
            except OSError:
                pass
        killed_at = round(time.time() - job['started'])
    except (OSError, ValueError) as e:
        note(vendor, '3-kill-and-resume', error='could not kill: %s' % e)
        return
    ex1, u1 = wait(job, 60)
    before = read(wt, 'resume.txt')
    job2 = start(vendor, wt, C.prompt_resume('builder' if vendor == 'codex' else 'reviewer').replace(
        'your instructions are unchanged and are in agents/%s/GOAL.md' % ('builder' if vendor == 'codex' else 'reviewer'),
        'your instructions are unchanged'), resume_of=job, tag='-3b')
    ex2, u2 = wait(job2, 900)
    note(vendor, '3-kill-and-resume', killed_after_s=killed_at, first_exit=ex1, resume_txt_before_resume=before,
         resume_exit=ex2, resume_txt_after=read(wt, 'resume.txt'), same_session=job2.get('cli_session') == job.get('cli_session'),
         resume_argv=json.load(open(os.path.join(job2['dir'], 'cmd.json')))['argv'][:6] + ['...'], usage_first=u1,
         usage_resume=u2, jobs=[job['dir'], job2['dir']])


LONG_RULE = ('A command that runs longer than your shell waits by default must be started in the background with its '
             'output in a file, and you read the file when it ends; or give the command a timeout longer than the run. '
             'Trust only output that ends with its last line.')


def check4(vendor):
    wt = worktree('%s-4' % vendor)
    job = start(vendor, wt, 'Run this command, which takes 15 minutes: `sleep 900; echo LONG-RUN-FINISHED`. Rule: %s '
                'When it has finished, write the line it printed into long.txt. Then reply done.' % LONG_RULE, tag='-4')
    ex, u = wait(job, 1800)
    note(vendor, '4-fifteen-minute-command', exit=ex, long_txt=read(wt, 'long.txt'),
         seconds=round((ex or {}).get('ended', time.time()) - job['started']), usage=u, job=job['dir'])


def check5(vendor):
    wt = worktree('%s-5' % vendor)
    gitdir = C.git(['rev-parse', '--git-dir'], cwd=wt)
    open(os.path.join(wt, 'toy.c'), 'w').write('int main(void){ int a[2]; int i; __CPROVER_assume(i>=0 && i<3); return a[i]; }\n')
    cmds = ['cbmc toy.c --bounds-check > cbmc.txt 2>&1; echo "cbmc exit $?" >> cbmc.txt',
            'echo inside > inside.txt',
            'touch %s/sandbox-probe 2>&1; echo "git-dir write exit $?"' % gitdir,
            'touch %s/sandbox-probe 2>&1; echo "project write exit $?"' % REPO,
            'curl -sS -m 10 https://example.com -o /dev/null 2>&1; echo "network exit $?"']
    prompt = ('Run each of these shell commands exactly as written, one at a time, and append each command and its full '
              'output to sandbox.txt (in the current directory) as you go. Do not try to work around any failure; a '
              'failure is the expected result for some of them.\n' + '\n'.join('%d. `%s`' % (i + 1, c) for i, c in enumerate(cmds))
              + '\nThen reply done.')
    job = start(vendor, wt, prompt, tag='-5')
    ex, u = wait(job, 900)
    note(vendor, '5-sandbox', exit=ex, cbmc=(read(wt, 'cbmc.txt') or '')[-300:], inside=read(wt, 'inside.txt'),
         sandbox_txt=(read(wt, 'sandbox.txt') or '')[-2500:],
         git_dir_probe_exists=os.path.exists(os.path.join(gitdir, 'sandbox-probe')),
         project_probe_exists=os.path.exists(os.path.join(REPO, 'sandbox-probe')), job=job['dir'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='1,2,3,4,5')
    ap.add_argument('--vendor', default='codex,claude')
    a = ap.parse_args()
    if os.path.exists(os.path.join(HERE, 'results.json')):
        results.update(json.load(open(os.path.join(HERE, 'results.json'))))
    fns = {'1': check1, '2': check2, '3': check3, '4': check4, '5': check5}
    ths = []
    for v in a.vendor.split(','):
        for k in a.only.split(','):
            t = threading.Thread(target=fns[k], args=(v,), name='%s-%s' % (v, k))
            t.start()
            ths.append(t)
    for t in ths:
        t.join()
    print('RESULT cli_check done')


if __name__ == '__main__':
    main()
