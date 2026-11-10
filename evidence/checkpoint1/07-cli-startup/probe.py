"""Q2/Q4 probe: run one CLI session exactly as tools/campaign.py starts it (sessions.toml's command, filled and
checked by campaign.py), under strace, and list every path outside the worktree it opens or looks for.
Usage: probe.py <codex|claude> <outdir> [--resume <session-id> --config <dir>]"""
import json, os, re, subprocess, sys
REPO = '/home/zpconn/code/proving-sqlite'
sys.path.insert(0, os.path.join(REPO, 'tools'))
import campaign as C  # noqa: E402
vendor, out = sys.argv[1], sys.argv[2]
resume = sys.argv[sys.argv.index('--resume') + 1] if '--resume' in sys.argv else None
os.makedirs(out, exist_ok=True)
p = C.P(REPO)
sess = C.load_sessions(REPO)
role = 'builder' if vendor == 'codex' else 'reviewer'
v, model, effort, vcfg = C.role_config(sess, role, 'standard')
assert v == vendor
effort = 'low'
wt = os.path.join(p.wt, 'q2-' + vendor)
if not os.path.isdir(wt):
    C.git(['worktree', 'add', '-q', '--detach', wt, 'HEAD'], cwd=REPO)
key = 'resume' if resume else 'start'
cfg = ''
if vendor == 'claude':
    cfg = sys.argv[sys.argv.index('--config') + 1] if '--config' in sys.argv else os.path.join(p.state, 'claude-config', 'q2-probe')
    C.seed_claude_config(cfg)
home = os.path.expanduser('~')
argv = C.prepare_mounts(C.fill(vcfg[key], dir=wt, model=model, effort=effort, home=home, wtroot=p.wt, repo=p.primary,
                               config=cfg, session=resume or ''), home)
probs = C.template_problems(vendor, key, vcfg[key]) + C.command_problems(vendor, argv, wt, p)
print('command problems:', probs)
assert not probs
env = C.session_env()
if vendor == 'codex':
    os.makedirs(os.path.join(wt, 'tmp'), exist_ok=True)
    env['TMPDIR'] = os.path.join(wt, 'tmp')
prompt = sys.argv[sys.argv.index('--prompt') + 1] if '--prompt' in sys.argv else \
    'Reply with the single word OK. Do not run any command or read any file.'
trace = os.path.join(out, 'strace-%s-%s.txt' % (vendor, key))
r = subprocess.run(['strace', '-f', '-qq', '-e', 'trace=%file', '-o', trace, 'nice', '-n', '10'] + argv, input=prompt,
                   capture_output=True, text=True, cwd=wt, env=env, timeout=900)
open(os.path.join(out, 'stdout-%s-%s.jsonl' % (vendor, key)), 'w').write(r.stdout)
open(os.path.join(out, 'stderr-%s-%s.txt' % (vendor, key)), 'w').write(r.stderr)
json.dump({'argv': argv, 'rc': r.returncode, 'config': cfg}, open(os.path.join(out, 'cmd-%s-%s.json' % (vendor, key)), 'w'), indent=1)
print('rc', r.returncode)
# every path argument in the trace, with whether the call succeeded
seen = {}
for line in open(trace, errors='replace'):
    m = re.search(r'^\d+\s+(\w+)\((?:AT_FDCWD|\d+)?,?\s*"([^"]+)"', line)
    if not m:
        continue
    path = m.group(2)
    okk = '= -1' not in line
    if not path.startswith('/'):
        continue
    seen.setdefault(path, set()).add('found' if okk else line.split('= -1')[1].split()[0])
skip = ('/usr/', '/lib', '/proc/', '/sys/', '/dev/', '/etc/ld.so', '/bin/', '/sbin/', wt + '/', wt)
rows = sorted((p_, ','.join(sorted(s))) for p_, s in seen.items() if not p_.startswith(skip) and p_ != wt)
with open(os.path.join(out, 'paths-%s-%s.txt' % (vendor, key)), 'w') as f:
    for p_, s in rows:
        f.write('%s\t%s\n' % (s, p_))
print(len(rows), 'paths outside the worktree and system dirs')
if vendor == 'claude' and not resume:
    for ln in r.stdout.split('\n'):
        if '"session_id"' in ln:
            print('session_id', json.loads(ln).get('session_id'))
            break
if vendor == 'codex':
    for ln in r.stdout.split('\n'):
        if 'thread_id' in ln or 'session_id' in ln:
            print(ln[:200]); break
