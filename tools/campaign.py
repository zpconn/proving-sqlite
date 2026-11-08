#!/usr/bin/env python3
"""campaign.py: the card loop (GOAL.md §3.1). A plain program with no model in its loop.

Commands
  start [--cards C-01,C-02] [--no-tmux]   move the primary checkout to branch orch, give main its own checkout at
                                          ../<repo>-wt/main, and run the daemon in tmux session "campaign"
  stop                                    stop starting anything new; running sessions carry on
  finish                                  stop, remove main's checkout, return the primary checkout to main with orch merged
  status                                  each card's state, round, vendor, tokens against cap, what it waits on;
                                          triage queue, merge queue, vendor pauses, last full gate
  wait                                    return when the triage queue changes, the campaign finishes, campaign.py
                                          stops, or four hours pass
  retry C-NN | park C-NN | reopen C-NN --for C-MM
  resume-vendor <codex|claude>            after Zach signs in again: lift the pause a failed login caused
  land                                    merge main into orch, check the paths, queue orch for main
  session <spec-review|ledger>            a one-off session, started the same way
  selftest                                rerun the coordinator tests in a scratch directory of its own
Internal: daemon, _job <dir>, _merge <dir>

Layout (GOAL.md Appendix D): PRIMARY is the orchestrator's checkout; WT = PRIMARY + "-wt" holds main/ (main's
checkout during the campaign), C-NN/ (builder worktrees on card/C-NN), C-NN-r<k>[-a<n>]/ (reviewer worktrees,
detached), merge/ (scratch for merge gates) and state/ (journal, state.json, job dirs with session logs).

Every commit this program makes carries a "Campaign:" trailer saying what it is and what checked it.
"""
import argparse
import csv
import datetime as dt
import fcntl
import glob
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import cards as cardlib  # noqa: E402

MAX_SESSIONS = 4                 # GOAL.md §0.9: builders and reviewers together
MAX_ROUNDS = 3                   # REJECTs before triage
MAX_INTERRUPTIONS = 3            # per round
SESSION_WALL_LIMIT = 12 * 3600   # a session running longer than this is killed and counts as an interruption
PAUSE_DEFAULT = 30 * 60          # usage limit with no reset time: 30 min, doubling to 4 h
PAUSE_MAX = 4 * 3600
WAIT_MAX = 4 * 3600
STRIP_ENV = ['ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'OPENAI_API_KEY', 'CODEX_API_KEY', 'AZURE_OPENAI_API_KEY',
             'ANTHROPIC_BASE_URL', 'OPENAI_BASE_URL', 'CLAUDECODE', 'CLAUDE_PID', 'CLAUDE_EFFORT']
STRIP_ENV_PREFIX = ['CLAUDE_CODE_']   # the orchestrator's own session linkage; each session must stand alone
VERDICTS_BUILDER = ('DONE', 'STUCK', 'FINDING', 'NEEDS-DECISION')
VERDICTS_REVIEWER = ('APPROVE', 'REJECT', 'NEEDS-ZACH')
LAND_ALLOWED = ['cards/', 'tests/repro/', 'evidence/approvals/', 'evidence/orchestrator/', 'PROGRESS.md', 'LEDGER.md',
                'FINDINGS.md']
ROLE_PATHS = {'spec-review': ['reviews/spec-'], 'ledger': ['validation/', 'evidence/ledger/', 'reports/ledger-']}
# GOAL.md §0.10, hard-coded (checkpoint 0, decision C5): sessions.toml supplies models and command lines, never vendors.
# The spec was written by Claude, so its reviewer runs on Codex.
ROLE_VENDOR = {'builder': 'codex', 'reviewer': 'claude', 'ledger': 'claude', 'spec-review': 'codex'}
AUTH_RECHECK = 15 * 60          # an auth pause is lifted only by `resume-vendor`; status reminds every 15 min
TICK = float(os.environ.get('CAMPAIGN_TICK', '10'))


# =============================================================== paths and git

def git(args, cwd, check=True, capture=True):
    p = subprocess.run(['git'] + args, cwd=cwd, capture_output=capture, text=True)
    if check and p.returncode != 0:
        raise GitError('git %s (in %s): %s' % (' '.join(args), cwd, (p.stderr or p.stdout).strip()[:800]))
    return p.stdout.strip() if capture else ''


class GitError(Exception):
    pass


class CampaignError(Exception):
    pass


def primary_repo():
    common = git(['rev-parse', '--path-format=absolute', '--git-common-dir'], cwd=TOOLS)
    return os.path.dirname(common)


class P:
    """All paths, derived from the primary checkout."""

    def __init__(self, primary=None):
        self.primary = primary or primary_repo()
        self.wt = self.primary.rstrip('/') + '-wt'
        self.state = os.path.join(self.wt, 'state')
        self.mainwt = os.path.join(self.wt, 'main')
        self.merge = os.path.join(self.wt, 'merge')
        self.jobs = os.path.join(self.state, 'jobs')

    def main_dir(self):
        """Where branch main is checked out: main/ during the campaign, else the primary checkout."""
        if os.path.isdir(self.mainwt) and current_branch(self.mainwt) == 'main':
            return self.mainwt
        return self.primary

    def card_wt(self, cid):
        return os.path.join(self.wt, cid)


def current_branch(d):
    try:
        return git(['rev-parse', '--abbrev-ref', 'HEAD'], cwd=d)
    except GitError:
        return None


def changed_paths(wt, base):
    """Every path changed since base: committed, staged, unstaged, and untracked files git doesn't ignore."""
    paths = set()
    out = git(['diff', '--name-only', base, 'HEAD'], cwd=wt)
    paths.update(x for x in out.split('\n') if x)
    pr = subprocess.run(['git', 'status', '--porcelain=v1', '-z', '--untracked-files=all'], cwd=wt,
                        capture_output=True, text=True, check=True)
    entries = pr.stdout.split('\0')   # not stripped: the first entry may start with a space
    i = 0
    while i < len(entries):
        e = entries[i]
        if not e:
            i += 1
            continue
        code, path = e[:2], e[3:]
        paths.add(path)
        if code[0] in 'RC':
            i += 1
            if i < len(entries) and entries[i]:
                paths.add(entries[i])
        i += 1
    return sorted(paths)


def now():
    return time.time()


def iso(t=None):
    return dt.datetime.fromtimestamp(t if t is not None else now()).astimezone().isoformat(timespec='seconds')


# =============================================================== state

class State:
    """state.json under an exclusive flock on state.lock; written atomically. journal.jsonl is append-only."""

    def __init__(self, p):
        self.p = p
        os.makedirs(p.state, exist_ok=True)
        os.makedirs(p.jobs, exist_ok=True)
        self.lockf = None
        self.d = None

    def __enter__(self):
        self.lockf = open(os.path.join(self.p.state, 'state.lock'), 'w')
        fcntl.flock(self.lockf, fcntl.LOCK_EX)
        path = os.path.join(self.p.state, 'state.json')
        if os.path.exists(path):
            with open(path) as f:
                self.d = json.load(f)
        else:
            self.d = {'cards': {}, 'jobs': {}, 'vendors': {}, 'merge_queue': [], 'scope': None, 'started': False,
                      'stopping': False, 'last_full_gate': None, 'triage_seq': 0, 'job_seq': 0, 'lands': []}
        return self

    def __exit__(self, *exc):
        if exc[0] is None:
            self.save()
        fcntl.flock(self.lockf, fcntl.LOCK_UN)
        self.lockf.close()

    def save(self):
        path = os.path.join(self.p.state, 'state.json')
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(self.d, f, indent=1, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def journal(self, kind, **kw):
        rec = dict(ts=iso(), kind=kind, **kw)
        with open(os.path.join(self.p.state, 'journal.jsonl'), 'a') as f:
            f.write(json.dumps(rec, sort_keys=True) + '\n')
            f.flush()
            os.fsync(f.fileno())
        log('%s %s' % (kind, ' '.join('%s=%s' % (k, v) for k, v in sorted(kw.items()) if k not in ('detail',))))

    def read_only(p):
        path = os.path.join(p.state, 'state.json')
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)


LOGF = None


def log(msg):
    line = '%s %s' % (dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), msg)
    print(line)
    sys.stdout.flush()
    if LOGF:
        LOGF.write(line + '\n')
        LOGF.flush()


# =============================================================== sessions.toml

def load_sessions(main_dir):
    path = os.path.join(main_dir, 'tools', 'sessions.toml')
    with open(path, 'rb') as f:
        return tomllib.load(f)


class SessionRefused(CampaignError):
    pass


def role_config(sess, role, tier):
    """(vendor, model, effort, vendor config). The vendor is ROLE_VENDOR's; a sessions.toml that names another for
    the role is refused rather than followed."""
    try:
        rc = sess['roles'][role][tier]
    except KeyError:
        raise CampaignError('sessions.toml has no roles.%s.%s' % (role, tier))
    vendor = ROLE_VENDOR.get(role)
    if vendor is None:
        raise SessionRefused('no vendor is fixed for role %s' % role)
    if rc.get('vendor', vendor) != vendor:
        raise SessionRefused('sessions.toml puts roles.%s.%s on %s, but campaign.py runs %s sessions on %s only '
                             '(GOAL.md §0.10)' % (role, tier, rc.get('vendor'), role, vendor))
    return vendor, rc['model'], rc['effort'], sess['vendors'][vendor]


CODEX_FORBIDDEN = {'--dangerously-bypass-approvals-and-sandbox', '--yolo', '--full-auto', '--approve-for-me', '-s',
                   '--sandbox', '-a', '--ask-for-approval', '--add-dir', '--oss', '-p', '--profile'}
CLAUDE_FORBIDDEN = {'--dangerously-skip-permissions', '--allow-dangerously-skip-permissions', '--bare',
                    '--add-dir', '--permission-prompt-tool', '--settings', '--mcp-config', '--plugin-dir'}


def command_problems(vendor, argv, wt, p):
    """Why a session's command line is refused (checkpoint 0, decisions C5 and C6), or [].
    codex: `codex exec` with sandbox_mode="workspace-write" and approval_policy="never", each set once, and none of the
    flags that loosen either. claude: bubblewrap first, with / read-only, a private /tmp, ~/.codex, the worktree root
    (../<repo>-wt: state/ and every other worktree) and the primary checkout hidden (its .git read-only), and only
    the session's own worktree, ~/.claude and ~/.claude.json writable, then `claude -p` in auto permission mode."""
    home = os.path.expanduser('~')
    probs = []
    if vendor == 'codex':
        if os.path.basename(argv[0]) != 'codex' or len(argv) < 2 or argv[1] != 'exec':
            probs.append('a codex session must start with `codex exec`')
        sets = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a in ('-c', '--config')]
        sb = [x for x in sets if x.split('=', 1)[0].strip() in ('sandbox_mode',)]
        ap = [x for x in sets if x.split('=', 1)[0].strip() in ('approval_policy', 'ask_for_approval')]
        if sb != ['sandbox_mode="workspace-write"']:
            probs.append('codex must set sandbox_mode="workspace-write" exactly once (found %s)' % sb)
        if ap != ['approval_policy="never"']:
            probs.append('codex must set approval_policy="never" exactly once (found %s)' % ap)
        loose = [x for x in sets if x.split('=', 1)[0].strip().startswith(('sandbox_workspace_write', 'sandbox_permissions',
                                                                          'permissions', 'default_permissions', 'shell_environment_policy'))]
        if loose:
            probs.append('codex settings that loosen the sandbox: %s' % loose)
        bad = [a for a in argv if a in CODEX_FORBIDDEN or a.startswith('--sandbox=') or a.startswith('--profile=')]
        if bad:
            probs.append('codex flags not allowed: %s' % bad)
        return probs
    if vendor != 'claude':
        return ['unknown vendor %s' % vendor]
    if not argv or os.path.basename(argv[0]) != 'bwrap':
        return ['a claude session must start with bwrap']
    try:
        ci = [os.path.basename(a) for a in argv].index('claude')
    except ValueError:
        return ['no claude command after bwrap']
    bw, cl = argv[1:ci], argv[ci:]
    mounts, i = [], 0
    while i < len(bw):
        a = bw[i]
        if a in ('--ro-bind', '--bind', '--dev-bind', '--ro-bind-try', '--bind-try', '--dev-bind-try', '--symlink'):
            mounts.append((a, bw[i + 1], bw[i + 2]))
            i += 3
        elif a in ('--tmpfs', '--dev', '--proc', '--chdir', '--dir', '--remount-ro', '--perms', '--size'):
            mounts.append((a, bw[i + 1], bw[i + 1]))
            i += 2
        else:
            mounts.append((a, None, None))
            i += 1
    real = lambda x: os.path.realpath(x)  # noqa: E731
    if not mounts or mounts[0] != ('--ro-bind', '/', '/'):
        probs.append('bwrap must begin with --ro-bind / /')
    allowed_rw = {real(wt), real(os.path.join(home, '.claude')), real(os.path.join(home, '.claude.json'))}
    for kind, src, dst in mounts:
        if kind in ('--bind', '--dev-bind', '--bind-try', '--dev-bind-try') and real(dst) not in allowed_rw:
            probs.append('bwrap binds %s writable; only the worktree, ~/.claude and ~/.claude.json may be' % dst)
        if kind in ('--ro-bind', '--ro-bind-try') and (src, dst) != ('/', '/') and \
                (real(src), real(dst)) != (real(os.path.join(p.primary, '.git')),) * 2:
            probs.append('bwrap read-only binds %s; only / and the primary checkout\'s .git are' % dst)
        if kind in ('--symlink', '--remount-ro', '--perms', '--size', '--dir') or kind not in (
                '--ro-bind', '--bind', '--dev-bind', '--ro-bind-try', '--bind-try', '--dev-bind-try', '--tmpfs', '--dev',
                '--proc', '--chdir', '--die-with-parent', '--new-session', '--unshare-pid', '--unshare-ipc'):
            probs.append('bwrap option %s not allowed' % kind)
    order = [(k, real(d) if d else d) for k, s_, d in mounts]

    def last_mount_at(path):
        """The last mount whose destination is path or one of its parents, as bwrap applies them in order."""
        rp = real(path)
        hit = None
        for k, d in order:
            if d and k != '--chdir' and (rp == d or rp.startswith(d.rstrip('/') + '/')):
                hit = (k, d)
        return hit
    for hidden in ('/tmp', os.path.join(home, '.codex'), p.wt, p.primary, os.path.join(p.wt, 'state'),
                   os.path.join(p.wt, 'main'), os.path.join(p.wt, 'merge')):
        if real(hidden) in (real(wt),):
            continue
        hit = last_mount_at(hidden)
        if not hit or hit[0] != '--tmpfs':
            probs.append('bwrap must hide %s behind a --tmpfs (last mount there: %s)' % (hidden, hit))
    hit = last_mount_at(wt)
    if not hit or hit != ('--bind', real(wt)):
        probs.append('the worktree %s must be the last mount at its path, writable (found %s)' % (wt, hit))
    if len(cl) < 2 or cl[1] != '-p':
        probs.append('claude must run as `claude -p`')
    if 'bypassPermissions' in cl or any(a in CLAUDE_FORBIDDEN for a in cl):
        probs.append('claude flags not allowed: %s' % [a for a in cl if a in CLAUDE_FORBIDDEN or a == 'bypassPermissions'])
    if 'auto' not in [cl[i + 1] for i, a in enumerate(cl[:-1]) if a == '--permission-mode']:
        probs.append('claude must run with --permission-mode auto')
    return probs


def fill(argv, **kw):
    out = []
    for a in argv:
        for k, v in kw.items():
            a = a.replace('{%s}' % k, str(v))
        out.append(a)
    return out


def session_env():
    env = {k: v for k, v in os.environ.items()
           if k not in STRIP_ENV and not any(k.startswith(pfx) for pfx in STRIP_ENV_PREFIX)}
    env['GNUMAKEFLAGS'] = '--no-print-directory'
    return env


# =============================================================== jobs: detached processes that outlive the daemon

def new_job(st, kind, **meta):
    st.d['job_seq'] += 1
    jid = 'J%04d-%s' % (st.d['job_seq'], kind)
    jdir = os.path.join(st.p.jobs, jid)
    os.makedirs(jdir)
    job = dict(id=jid, kind=kind, dir=jdir, state='new', created=now(), **meta)
    st.d['jobs'][jid] = job
    return job


def spawn_runner(p, job, argv, cwd, stdin_text):
    """Write the job's command and start `campaign.py _job <dir>` detached in its own session."""
    with open(os.path.join(job['dir'], 'prompt.txt'), 'w') as f:
        f.write(stdin_text)
    with open(os.path.join(job['dir'], 'cmd.json'), 'w') as f:
        json.dump({'argv': argv, 'cwd': cwd}, f, indent=1)
    devnull = open(os.devnull, 'r+')
    subprocess.Popen([sys.executable, os.path.join(TOOLS, 'campaign.py'), '_job', job['dir']],
                     stdin=devnull, stdout=devnull, stderr=devnull, start_new_session=True, env=session_env(),
                     cwd=cwd)
    job['state'] = 'running'
    job['started'] = now()


def cmd_job(jdir):
    """The runner: owns one CLI process; records pid and exit status beside the output."""
    with open(os.path.join(jdir, 'cmd.json')) as f:
        c = json.load(f)
    with open(os.path.join(jdir, 'pid'), 'w') as f:
        f.write('%d\n' % os.getpid())
    out = open(os.path.join(jdir, 'out.jsonl'), 'ab')
    err = open(os.path.join(jdir, 'err.log'), 'ab')
    inp = open(os.path.join(jdir, 'prompt.txt'), 'rb')
    try:
        proc = subprocess.Popen(['nice', '-n', '10'] + c['argv'], cwd=c['cwd'], stdin=inp, stdout=out, stderr=err)
        with open(os.path.join(jdir, 'child.pid'), 'w') as f:
            f.write('%d\n' % proc.pid)
        rc = proc.wait()
    except OSError as e:
        err.write(('runner: cannot start %s: %s\n' % (c['argv'][:1], e)).encode())
        rc = 127
    tmp = os.path.join(jdir, 'exit.json.tmp')
    with open(tmp, 'w') as f:
        json.dump({'rc': rc, 'ended': now()}, f)
    os.replace(tmp, os.path.join(jdir, 'exit.json'))
    return 0


def job_alive(job):
    pf = os.path.join(job['dir'], 'pid')
    if not os.path.exists(pf):
        return (now() - job.get('started', 0)) < 60   # runner not up yet
    try:
        pid = int(open(pf).read().strip())
        with open('/proc/%d/cmdline' % pid, 'rb') as f:
            return job['dir'].encode() in f.read()
    except (OSError, ValueError):
        return False


def job_exit(job):
    ef = os.path.join(job['dir'], 'exit.json')
    if os.path.exists(ef):
        with open(ef) as f:
            return json.load(f)
    return None


def kill_job(job):
    pf = os.path.join(job['dir'], 'pid')
    try:
        pid = int(open(pf).read().strip())
        os.killpg(pid, signal.SIGTERM)
        time.sleep(1)
        os.killpg(pid, signal.SIGKILL)
    except (OSError, ValueError):
        pass


# =============================================================== reading session output

def read_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, 'rb') as f:
        for raw in f:
            try:
                out.append(json.loads(raw.decode('utf-8', 'replace')))
            except ValueError:
                out.append({'_raw': raw.decode('utf-8', 'replace').rstrip('\n')})
    return out


def codex_rollout(thread_id):
    if not thread_id:
        return None
    hits = glob.glob(os.path.expanduser('~/.codex/sessions/*/*/*/rollout-*-%s.jsonl' % thread_id))
    return sorted(hits)[-1] if hits else None


def usage_of(job):
    """Token usage of one job: {'input','cache_read','cache_write','output','total'}, and the CLI session id.
    claude: sum of message_delta usages (final per message), or the sum over result events if larger.
    codex: the rollout log's cumulative total_token_usage for the thread, minus its value when the job began
    (a resume appends to the same thread). OpenAI's input_tokens already includes cached_input_tokens."""
    ev = read_jsonl(os.path.join(job['dir'], 'out.jsonl'))
    u = {'input': 0, 'cache_read': 0, 'cache_write': 0, 'output': 0}
    sid = job.get('cli_session')
    if job['vendor'] == 'claude':
        # Each result event covers one turn (a session that backgrounds a command runs several turns), so the
        # total is the sum over messages, checked against the sum over results.
        res = {'input': 0, 'cache_read': 0, 'cache_write': 0, 'output': 0}
        for e in ev:
            if e.get('type') == 'system' and e.get('subtype') == 'init':
                sid = e.get('session_id') or sid
            if e.get('type') == 'stream_event' and e.get('event', {}).get('type') == 'message_delta':
                x = e['event'].get('usage') or {}
                u['input'] += x.get('input_tokens', 0) or 0
                u['cache_read'] += x.get('cache_read_input_tokens', 0) or 0
                u['cache_write'] += x.get('cache_creation_input_tokens', 0) or 0
                u['output'] += x.get('output_tokens', 0) or 0
            if e.get('type') == 'result':
                x = e.get('usage') or {}
                res['input'] += x.get('input_tokens', 0) or 0
                res['cache_read'] += x.get('cache_read_input_tokens', 0) or 0
                res['cache_write'] += x.get('cache_creation_input_tokens', 0) or 0
                res['output'] += x.get('output_tokens', 0) or 0
        if sum(res.values()) > sum(u.values()):
            u = res
        u['total'] = u['input'] + u['cache_read'] + u['cache_write'] + u['output']
    else:
        for e in ev:
            if e.get('type') == 'thread.started':
                sid = e.get('thread_id') or sid
        tot = None
        ro = job.get('rollout') or codex_rollout(sid)
        if ro and os.path.exists(ro):
            job['rollout'] = ro
            for e in read_jsonl(ro):
                p = e.get('payload') or {}
                if e.get('type') == 'event_msg' and p.get('type') == 'token_count' and p.get('info'):
                    tot = p['info'].get('total_token_usage')
        if tot is None:
            # fall back to turn.completed usage in the --json stream (end of run only)
            for e in ev:
                if e.get('type') == 'turn.completed' and e.get('usage'):
                    x = e['usage']
                    tot = {'input_tokens': (tot or {}).get('input_tokens', 0) + x.get('input_tokens', 0),
                           'cached_input_tokens': (tot or {}).get('cached_input_tokens', 0) + x.get('cached_input_tokens', 0),
                           'cache_write_input_tokens': (tot or {}).get('cache_write_input_tokens', 0) + x.get('cache_write_input_tokens', 0),
                           'output_tokens': (tot or {}).get('output_tokens', 0) + x.get('output_tokens', 0)}
        tot = tot or {}
        base = job.get('codex_base') or {}
        g = lambda k: max(0, (tot.get(k, 0) or 0) - (base.get(k, 0) or 0))  # noqa: E731
        u = {'input': g('input_tokens'), 'cache_read': g('cached_input_tokens'), 'cache_write': g('cache_write_input_tokens'),
             'output': g('output_tokens')}
        u['total'] = u['input'] + u['cache_write'] + u['output']
        job['codex_last_total'] = tot
    return u, sid


def control_text(job):
    """Text a usage-limit pattern may match: stderr, non-JSON stdout lines, and the CLI's own error, failure,
    error-result and rate-limit events. Never agent messages or tool output, which a model could write."""
    parts = []
    try:
        parts.append(open(os.path.join(job['dir'], 'err.log'), errors='replace').read())
    except OSError:
        pass
    for e in read_jsonl(os.path.join(job['dir'], 'out.jsonl')):
        t = e.get('type')
        if '_raw' in e:
            parts.append(e['_raw'])
        elif t in ('error', 'turn.failed', 'rate_limit_event') or (t == 'result' and e.get('is_error')):
            parts.append(json.dumps(e, ensure_ascii=False))
    return '\n'.join(parts)


MONTHS = {m: i for i, m in enumerate(['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], 1)}


def reset_time(text):
    """Best-effort reset time (epoch) from usage-limit output; None if none found."""
    cands = []
    for m in re.finditer(r'"(?:resets_?[aA]t|resetsAt)"\s*:\s*([0-9]{9,11})', text):
        cands.append(int(m.group(1)))
    for m in re.finditer(r'\|([0-9]{9,11})\b', text):
        cands.append(int(m.group(1)))
    m = re.search(r'(?i)try again at\s+([A-Za-z]{3})[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\s+(\d{1,2}):(\d{2})\s*([AP]M)', text)
    if m:
        mon = MONTHS.get(m.group(1).lower()[:3])
        if mon:
            h = int(m.group(4)) % 12 + (12 if m.group(6).upper() == 'PM' else 0)
            t = dt.datetime(int(m.group(3)), mon, int(m.group(2)), h, int(m.group(5))).astimezone()
            cands.append(int(t.timestamp()) + 60)
    future = [c for c in cands if c > now() - 60]
    return max(future) if future else None


def hit_usage_limit(job, sess):
    pats = sess['vendors'][job['vendor']].get('usage_limit_patterns', [])
    text = control_text(job)
    for pat in pats:
        if re.search(pat, text):
            return True, reset_time(text)
    return False, None


def hit_auth_failure(job, sess):
    """The CLI's own output says its login is gone or expired (checkpoint 0, decision E). Returns the matching line
    or None. Like usage limits, matched against control_text only, never agent messages."""
    pats = sess['vendors'][job['vendor']].get('auth_failure_patterns', [])
    text = control_text(job)
    for pat in pats:
        m = re.search(pat, text)
        if m:
            a = text.rfind('\n', 0, m.start()) + 1
            b = text.find('\n', m.end())
            return text[a:b if b >= 0 else len(text)].strip()[:300]
    return None


def login_ok(sess, vendor):
    """(ok, output) from the vendor's login_check command."""
    cmd = sess['vendors'][vendor].get('login_check')
    if not cmd:
        return False, 'sessions.toml has no login_check for %s' % vendor
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60, env=session_env())
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    out = (p.stdout + p.stderr).strip()
    if p.returncode != 0 or re.search(r'(?i)not logged in|"loggedIn"\s*:\s*false', out):
        return False, out[:400]
    m = re.search(r'"loginExpiresAt"\s*:\s*"([^"]+)"', out)
    if m:
        try:
            if dt.datetime.fromisoformat(m.group(1).replace('Z', '+00:00')).timestamp() < now():
                return False, 'login expired at %s' % m.group(1)
        except ValueError:
            pass
    return True, out[:400]


def mode_problems(wt, base, paths):
    """Symlinks, submodules and file-mode changes the builder's commit would carry (checkpoint 0, decision C2):
    everything since base, committed or not, staged into a scratch index."""
    if not paths:
        return []
    idx = os.path.join(wt, '.campaign', 'mode-check.index')
    os.makedirs(os.path.dirname(idx), exist_ok=True)
    env = dict(os.environ, GIT_INDEX_FILE=idx)
    try:
        subprocess.run(['git', 'read-tree', 'HEAD'], cwd=wt, env=env, check=True, capture_output=True)
        subprocess.run(['git', 'add', '-A', '--'] + paths, cwd=wt, env=env, check=True, capture_output=True)
        raw = subprocess.run(['git', 'diff', '--cached', '--raw', '--no-renames', base], cwd=wt, env=env, check=True,
                             capture_output=True, text=True).stdout
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode('utf-8', 'replace') if isinstance(e.stderr, bytes) else (e.stderr or '')
        return ['cannot check file modes: %s' % err.strip()[:200]]
    finally:
        if os.path.exists(idx):
            os.remove(idx)
    probs = []
    for line in raw.split('\n'):
        m = re.match(r'^:(\d{6}) (\d{6}) \S+ \S+ (\S+)\t(.*)$', line)
        if not m:
            continue
        old, new, path = m.group(1), m.group(2), m.group(4)
        if new in ('120000', '160000'):
            probs.append('%s would be a %s' % (path, 'symlink' if new == '120000' else 'submodule'))
        elif old == '000000' and new not in ('000000', '100644'):
            probs.append('new file %s has mode %s, not 100644' % (path, new))
        elif old != '000000' and new != '000000' and old != new:
            probs.append('%s changes mode %s -> %s' % (path, old, new))
    return probs


def first_line(path):
    if not os.path.exists(path):
        return None
    with open(path, errors='replace') as f:
        for line in f:
            s = line.strip()
            if s:
                return re.sub(r'[*#`_]', '', s).strip().split()[0].rstrip(':.') if s else None
    return None


# =============================================================== prompts (fixed here, frozen with tools/)

# How a Codex builder waits for a long command (checkpoint 0, decision D; evidence/bringup/13-waiting.md). Codex runs
# tools inside a JavaScript exec cell; sessions.toml lets one write_stdin call and the cell around it block for up to
# an hour, so a 15-minute run costs one model call instead of one per minute. agents/builder/GOAL.md §2.9 says the same.
LONG_RUN_CODEX = (
    'Long commands (a CBMC run can take 10 minutes per configuration): wait once, never poll. In one exec cell, start '
    'the command with tools.exec_command, its output in a file (yield_time_ms 1000); if it is still running, call '
    'tools.write_stdin with its session_id, chars "" and yield_time_ms 3600000. That call returns when the command '
    'exits (this session allows waits of up to an hour), so the cell and your turn wait with it. Do not use sleep, '
    'short yields or repeated wait calls to check on a run. Background jobs do not survive here: a command\'s '
    'background children are killed when it returns. Trust only output that ends with its RESULT line.')


def prompt_builder(cid, rnd, reviews, notes, wt):
    lines = [
        'You are a builder session in the proving-sqlite project. Your instructions are agents/builder/GOAL.md; '
        'read it first and follow it. The rules every role obeys are in AGENTS.md.',
        'Your card is cards/%s.md. This is round %d.' % (cid, rnd),
    ]
    if reviews:
        lines.append('Answer these reviews of earlier rounds; each issue must be fixed or argued in your report: '
                     + ', '.join(reviews) + '.')
    for n in notes:
        lines.append('Orchestrator note: ' + n)
    lines += [
        'Write your report to reports/%s-b%d.md; its first line is DONE, STUCK, FINDING or NEEDS-DECISION.' % (cid, rnd),
        'Your token usage so far, against the card\'s cap, is in .campaign/usage; check it after each run.',
        'Work only in this directory (%s) and /tmp. Do not commit, branch or merge: campaign.py commits what you '
        'leave when you exit, and only the paths on your card\'s May change line.' % wt,
        LONG_RUN_CODEX + ' proofs/HOWTO.md records how proofs are built here.',
    ]
    return '\n\n'.join(lines) + '\n'


def prompt_reviewer(cid, rnd, commit, builder_report, rereview=None):
    lines = [
        'You are a reviewer session in the proving-sqlite project. Your instructions are agents/reviewer/GOAL.md; '
        'read it first and follow it. The rules every role obeys are in AGENTS.md.',
    ]
    if rereview:
        lines.append('This is a re-review after a contract change (%s). Your worktree is at main\'s head, commit %s. '
                     'Judge card cards/%s.md against the changed contract.' % (rereview, commit, cid))
    else:
        lines.append('Judge card cards/%s.md, builder round %d, commit %s. Your worktree is detached at that commit. '
                     'The builder\'s report is %s.' % (cid, rnd, commit, builder_report))
    lines += [
        'Write your verdict to reviews/%s-r%d.md; its first line is APPROVE, REJECT or NEEDS-ZACH.' % (cid, rnd),
        'Do not modify any tracked file and do not run git commands that write; make scratch copies under /tmp. '
        'If you change a tracked file your review is discarded.',
        'CBMC runs can take 10 minutes per configuration: run them in the background with output in a file, or '
        'with a timeout longer than the run, and trust only output that ends with its RESULT line.',
    ]
    return '\n\n'.join(lines) + '\n'


def prompt_resume(kind):
    return ('Your session was interrupted. Continue the task you were given, from where you left off; your '
            'instructions are unchanged and are in agents/%s/GOAL.md. Do not repeat work already complete.\n' % kind)


def prompt_oneoff(role, n):
    if role == 'spec-review':
        return ('You are a reviewer session in the proving-sqlite project, on the vendor that did not write the file '
                'you review. Read GOAL.md §2 (P3), AGENTS.md, and proofs/spec/record_format.h. Check ref_serial_get '
                'against the serial type table in SQLite\'s file format document (sqlite.org/fileformat2.html, '
                '"Record Format"; a copy may be under evidence/ or ref/), row by row, and check that each departure '
                'GOAL.md P3 lists is written out and that nothing else departs from the table. It must be at most '
                '60 lines with each case citing its row. Do not modify any tracked file. Write your verdict to '
                'reviews/spec-r%d.md: first line APPROVE or REJECT, then numbered issues with severity, evidence and '
                'the fix.\n' % n)
    if role == 'ledger':
        return ('You are the ledger agent in the proving-sqlite project. Your instructions are agents/ledger/GOAL.md; '
                'read it first and follow it. The rules every role obeys are in AGENTS.md. Write only under '
                'validation/, evidence/ledger/ and reports/ledger-<date>.md. Do not commit.\n')
    raise CampaignError('unknown one-off role %s' % role)


# =============================================================== the coordinator

class Campaign:
    def __init__(self, p):
        self.p = p

    # ---------------------------------------------------------- helpers
    def cards(self):
        return cardlib.load_all(self.p.main_dir())

    def sess(self):
        return load_sessions(self.p.main_dir())

    def card(self, st, cid):
        c = st.d['cards'].get(cid)
        if c is None:
            c = {'id': cid, 'state': 'waiting', 'round': 0, 'epoch_rounds': 0, 'interruptions': 0, 'tokens_builder': 0,
                 'tokens_reviewer': 0, 'reason': None, 'notes': [], 'history': [], 'job': None, 'review_attempt': 0}
            st.d['cards'][cid] = c
        return c

    def set_state(self, st, c, state, reason=None, **kw):
        old = c['state']
        c['state'] = state
        c['reason'] = reason
        c['since'] = now()
        c.update(kw)
        if state == 'triage':
            st.d['triage_seq'] += 1
            c['triage_seq'] = st.d['triage_seq']
        c['history'].append([iso(), old, state, reason])
        st.journal('card', card=c['id'], frm=old, to=state, reason=reason)

    def running_sessions(self, st):
        return [j for j in st.d['jobs'].values() if j['kind'] in ('builder', 'reviewer', 'oneoff') and j['state'] in ('running', 'limit', 'auth')]

    def vendor_paused(self, st, vendor):
        v = st.d['vendors'].get(vendor) or {}
        return v.get('paused_until', 0) > now() or bool(v.get('auth_failed'))

    def auth_pause(self, st, vendor, job, line):
        """A login that failed works like a usage limit (checkpoint 0, decision E): no session starts on the vendor,
        the interrupted session waits to resume, nothing counts against its card, and a triage item asks Zach to
        sign in again. `campaign.py resume-vendor <vendor>` lifts it once the CLI's login check passes."""
        v = st.d['vendors'].setdefault(vendor, {})
        if not v.get('auth_failed'):
            v['auth_failed'] = {'at': iso(), 'job': job['id'], 'line': line}
            st.d['triage_seq'] += 1
            st.d.setdefault('vendor_triage', {})[vendor] = {
                'seq': st.d['triage_seq'], 'since': iso(),
                'reason': '%s login failed (%s): ask Zach to sign in again (`%s`), then run `tools/campaign.py '
                          'resume-vendor %s`' % (vendor, line[:160], 'codex login' if vendor == 'codex' else 'claude auth login', vendor)}
            st.journal('vendor-auth-pause', vendor=vendor, job=job['id'], line=line)
        job['state'] = 'auth'
        job['outcome'] = 'auth failure'

    def scoped(self, st, cards):
        sc = st.d.get('scope')
        return [k for k in sorted(cards) if sc is None or k in sc]

    def write_usage_file(self, wt, used, cap):
        d = os.path.join(wt, '.campaign')
        os.makedirs(d, exist_ok=True)
        pct = 100.0 * used / cap if cap else 0
        with open(os.path.join(d, 'usage'), 'w') as f:
            f.write('tokens_used %d\ncap %d\npercent %.1f\n' % (used, cap, pct))
            f.write('# %d of %d tokens (%.1f%%) used by this card\'s %s sessions so far; at 80%% report STUCK.\n' % (
                used, cap, pct, 'builder' if '-r' not in os.path.basename(wt) else 'reviewer'))

    def record_tokens(self, job):
        path = os.path.join(self.p.state, 'tokens.csv')
        new = not os.path.exists(path)
        with open(path, 'a', newline='') as f:
            w = csv.writer(f)
            if new:
                w.writerow(['job', 'card', 'role', 'round', 'vendor', 'model', 'effort', 'cli_session', 'started', 'ended',
                            'seconds', 'input', 'cache_read', 'cache_write', 'output', 'total', 'exit', 'outcome'])
            u = job.get('usage') or {}
            w.writerow([job['id'], job.get('card', ''), job.get('role', ''), job.get('round', ''), job.get('vendor', ''),
                        job.get('model', ''), job.get('effort', ''), job.get('cli_session', ''), iso(job.get('started')),
                        iso(job.get('ended')), round((job.get('ended') or now()) - (job.get('started') or now())),
                        u.get('input', 0), u.get('cache_read', 0), u.get('cache_write', 0), u.get('output', 0),
                        u.get('total', 0), job.get('rc', ''), job.get('outcome', '')])

    # ---------------------------------------------------------- starting sessions
    def start_session(self, st, job, vendor, model, effort, vcfg, wt, prompt, resume_of=None):
        """Start a session, or raise SessionRefused if its command line fails command_problems."""
        job.update(vendor=vendor, model=model, effort=effort, wt=wt)
        places = dict(dir=wt, model=model, effort=effort, home=os.path.expanduser('~'), wtroot=self.p.wt,
                      repo=self.p.primary)
        if resume_of and resume_of.get('cli_session'):
            argv = fill(vcfg['resume'], session=resume_of['cli_session'], **places)
        else:
            argv = fill(vcfg['start'], session='', **places)
        probs = command_problems(vendor, argv, wt, self.p)
        if probs:
            job['state'] = 'refused'
            job['outcome'] = 'refused: ' + '; '.join(probs)
            st.journal('session-refused', job=job['id'], card=job.get('card'), vendor=vendor, why='; '.join(probs))
            raise SessionRefused('refused to start a %s session: %s' % (vendor, '; '.join(probs)))
        for i, a in enumerate(argv[:-1]):
            if a == '--tmpfs' and not os.path.exists(argv[i + 1]):
                os.makedirs(argv[i + 1], exist_ok=True)   # bwrap cannot create a mount point under a read-only /
        if resume_of and resume_of.get('cli_session'):
            job['resumed_from'] = resume_of['id']
            job['cli_session'] = resume_of['cli_session']
            if vendor == 'codex':
                job['codex_base'] = resume_of.get('codex_last_total') or {}
                job['rollout'] = resume_of.get('rollout')
        st.journal('session-start', job=job['id'], card=job.get('card'), role=job.get('role'), vendor=vendor,
                   model=model, round=job.get('round'), resume=bool(resume_of))
        spawn_runner(self.p, job, argv, wt, prompt)

    def ensure_card_wt(self, cid):
        wt = self.p.card_wt(cid)
        main = self.p.main_dir()
        if not os.path.isdir(wt):
            br = 'card/%s' % cid
            exists = git(['branch', '--list', br], cwd=main)
            if exists:
                git(['worktree', 'add', wt, br], cwd=main)
            else:
                git(['worktree', 'add', '-b', br, wt, 'main'], cwd=main)
        return wt

    def start_builder_round(self, st, c, card, sess, resume_job=None):
        try:
            self._start_builder_round(st, c, card, sess, resume_job)
        except SessionRefused as e:
            c['job'] = None
            self.set_state(st, c, 'triage', str(e))

    def _start_builder_round(self, st, c, card, sess, resume_job=None):
        cid = c['id']
        vendor, model, effort, vcfg = role_config(sess, 'builder', card.tier)
        wt = self.ensure_card_wt(cid)
        if resume_job is None:
            # a new round: merge main into the card branch
            if changed_paths(wt, 'HEAD'):
                git(['reset', '--hard', '-q'], cwd=wt)
                git(['clean', '-fdq'], cwd=wt)
            msg = ('Merge main into card/%s for round %d\n\nCampaign: merge of main %s into card/%s before builder round %d; '
                   'no conflicts' % (cid, c['round'] + 1, git(['rev-parse', '--short', 'main'], cwd=wt), cid, c['round'] + 1))
            p = subprocess.run(['git', 'merge', '--no-edit', '-q', '-m', msg, 'main'], cwd=wt, capture_output=True, text=True)
            if p.returncode != 0:
                subprocess.run(['git', 'merge', '--abort'], cwd=wt, capture_output=True)
                self.set_state(st, c, 'triage', 'merging main into card/%s conflicts: %s' % (cid, (p.stdout + p.stderr).strip()[:300]))
                return
            c['round'] += 1
            c['epoch_rounds'] += 1
            c['interruptions'] = 0
            c['review_attempt'] = 0
            c['round_base'] = git(['rev-parse', 'HEAD'], cwd=wt)
        self.write_usage_file(wt, c['tokens_builder'], card.cap_builder)
        reviews = sorted(os.path.relpath(x, wt) for x in glob.glob(os.path.join(wt, 'reviews', '%s-r*.md' % cid)))
        job = new_job(st, 'builder', card=cid, role='builder', round=c['round'], tier=card.tier)
        if resume_job and resume_job.get('cli_session'):
            prompt = prompt_resume('builder')
        else:
            prompt = prompt_builder(cid, c['round'], reviews, c.get('notes', []), wt)
        self.start_session(st, job, vendor, model, effort, vcfg, wt, prompt, resume_of=resume_job)
        c['job'] = job['id']
        if c['state'] != 'building':
            self.set_state(st, c, 'building')

    def start_reviewer(self, st, c, card, sess, resume_job=None, rereview=None):
        try:
            self._start_reviewer(st, c, card, sess, resume_job, rereview)
        except SessionRefused as e:
            c['job'] = None
            self.set_state(st, c, 'triage', 'refused to start a reviewer: %s' % e)

    def _start_reviewer(self, st, c, card, sess, resume_job=None, rereview=None):
        cid = c['id']
        vendor, model, effort, vcfg = role_config(sess, 'reviewer', card.tier)
        bvendor = c.get('builder_vendor')
        # re-reviews too (checkpoint 0, decision C5): the reviewer is never on the vendor that built the card's last round
        if not bvendor or bvendor == vendor:
            raise SessionRefused('the reviewer would run on %s, the vendor that built round %d (%s)%s' % (
                vendor, c['round'], bvendor, ' (re-review)' if rereview else ''))
        if resume_job is not None:
            wt = resume_job['wt']
            commit = resume_job['commit']
        else:
            commit = c['judge_commit'] if rereview is None else git(['rev-parse', 'main'], cwd=self.p.main_dir())
            c['review_attempt'] += 1
            wt = os.path.join(self.p.wt, '%s-r%d%s' % (cid, c['round'], '' if c['review_attempt'] == 1 else '-a%d' % c['review_attempt']))
            if os.path.isdir(wt):
                git(['worktree', 'remove', '--force', wt], cwd=self.p.main_dir(), check=False)
                shutil.rmtree(wt, ignore_errors=True)
            git(['worktree', 'add', '--detach', wt, commit], cwd=self.p.main_dir())
        self.write_usage_file(wt, c['tokens_reviewer'], card.cap_reviewer)
        job = new_job(st, 'reviewer', card=cid, role='reviewer', round=c['round'], tier=card.tier, commit=commit,
                      rereview=rereview)
        if resume_job and resume_job.get('cli_session'):
            prompt = prompt_resume('reviewer')
        else:
            prompt = prompt_reviewer(cid, c['round'], commit, 'reports/%s-b%d.md' % (cid, c['round']), rereview)
        self.start_session(st, job, vendor, model, effort, vcfg, wt, prompt, resume_of=resume_job)
        c['job'] = job['id']
        if c['state'] != 'reviewing':
            self.set_state(st, c, 'reviewing')

    # ---------------------------------------------------------- the tick
    def tick(self, st):
        cards = self.cards()
        sess = self.sess()
        scope = self.scoped(st, cards)
        for cid in scope:
            c = self.card(st, cid)
            if c['state'] == 'waiting' and all(self.card(st, d)['state'] == 'merged' for d in cards[cid].depends):
                self.set_state(st, c, 'ready')
        # monitor running sessions
        for job in list(st.d['jobs'].values()):
            if job['kind'] not in ('builder', 'reviewer') or job['state'] != 'running':
                continue
            self.monitor(st, job, cards, sess)
        # resume sessions paused by a usage limit
        for job in list(st.d['jobs'].values()):
            if job['state'] in ('limit', 'auth') and not self.vendor_paused(st, job['vendor']) and not st.d.get('stopping'):
                if len(self.running_sessions(st)) - 1 < MAX_SESSIONS:   # it counts itself
                    c = self.card(st, job['card'])
                    job['state'] = 'resumed'
                    if job['kind'] == 'builder':
                        self.start_builder_round(st, c, cards[job['card']], sess, resume_job=job)
                    else:
                        self.start_reviewer(st, c, cards[job['card']], sess, resume_job=job)
        # merge jobs
        for job in list(st.d['jobs'].values()):
            if job['kind'] in ('merge', 'land') and job['state'] == 'running':
                self.monitor_merge(st, job)
        if st.d.get('stopping'):
            return
        # pending reviewer starts and builder rounds
        for cid in scope:
            c = self.card(st, cid)
            if c['state'] == 'reviewing' and c.get('job') is None:
                if len(self.running_sessions(st)) < MAX_SESSIONS and not self.vendor_paused(st, ROLE_VENDOR['reviewer']):
                    self.start_reviewer(st, c, cards[cid], sess, rereview=c.get('rereview'))
        for cid in scope:
            c = self.card(st, cid)
            if c['state'] == 'ready':
                if len(self.running_sessions(st)) < MAX_SESSIONS and not self.vendor_paused(st, ROLE_VENDOR['builder']):
                    self.start_builder_round(st, c, cards[cid], sess)
        # one merge at a time
        if not any(j['kind'] in ('merge', 'land') and j['state'] == 'running' for j in st.d['jobs'].values()):
            if st.d['merge_queue']:
                item = st.d['merge_queue'][0]
                self.start_merge(st, item)

    def monitor(self, st, job, cards, sess):
        c = self.card(st, job['card'])
        card = cards[job['card']]
        u, sid = usage_of(job)
        job['usage'] = u
        if sid:
            job['cli_session'] = sid
        prior = sum((st.d['jobs'][j].get('usage') or {}).get('total', 0) for j in st.d['jobs']
                    if st.d['jobs'][j].get('card') == job['card'] and st.d['jobs'][j].get('role') == job['role']
                    and j != job['id'] and st.d['jobs'][j]['state'] not in ('new',))
        used = prior + u['total']
        cap = card.cap_builder if job['role'] == 'builder' else card.cap_reviewer
        if job['role'] == 'builder':
            c['tokens_builder'] = used
        else:
            c['tokens_reviewer'] = used
        self.write_usage_file(job['wt'], used, cap)
        ex = job_exit(job)
        alive = job_alive(job)
        if ex is None and alive:
            if used >= cap:
                st.journal('cap', job=job['id'], card=job['card'], used=used, cap=cap)
                kill_job(job)
                job['cap_reached'] = True
            elif now() - job['started'] > SESSION_WALL_LIMIT:
                st.journal('wall-limit', job=job['id'])
                kill_job(job)
                job['wall_limit'] = True
            return
        if ex is None and not alive:
            ex = {'rc': 'lost', 'ended': now()}    # runner died (machine restart): an interruption
        job['state'] = 'ended'
        job['rc'] = ex['rc']
        job['ended'] = ex['ended']
        u, sid = usage_of(job)
        job['usage'] = u
        if sid:
            job['cli_session'] = sid
        if job['role'] == 'builder':
            self.builder_ended(st, c, card, job, sess)
        else:
            self.reviewer_ended(st, c, card, job, sess)
        self.record_tokens(job)

    def interrupted(self, st, c, card, job, sess, why):
        c['interruptions'] += 1
        job['outcome'] = 'interrupted: ' + why
        st.journal('interrupted', job=job['id'], card=c['id'], n=c['interruptions'], why=why)
        if c['interruptions'] >= MAX_INTERRUPTIONS:
            c['job'] = None
            self.set_state(st, c, 'triage', 'three interruptions in round %d (last: %s); logs %s' % (c['round'], why, job['dir']))
            return
        if job['role'] == 'builder':
            self.start_builder_round(st, c, card, sess, resume_job=job)
        else:
            self.start_reviewer(st, c, card, sess, resume_job=job)

    def builder_ended(self, st, c, card, job, sess):
        cid = c['id']
        wt = job['wt']
        c['job'] = None
        limit, reset = hit_usage_limit(job, sess) if not job.get('cap_reached') else (False, None)
        if limit:
            self.pause_vendor(st, job['vendor'], reset)
            job['state'] = 'limit'
            job['outcome'] = 'usage limit'
            c['job'] = job['id']
            return
        auth = hit_auth_failure(job, sess) if not job.get('cap_reached') else None
        if auth:
            self.auth_pause(st, job['vendor'], job, auth)
            c['job'] = job['id']
            return
        paths = changed_paths(wt, c['round_base'])
        bad = [x for x in paths if not card.allows(x)]
        if not bad:
            modes = mode_problems(wt, c['round_base'], paths)
            if modes:
                job['outcome'] = 'symlink or mode change'
                self.set_state(st, c, 'triage', 'builder left a symlink or a file-mode change (nothing committed): %s' % '; '.join(modes[:5]))
                return
        report = os.path.join(wt, 'reports', '%s-b%d.md' % (cid, c['round']))
        verdict = first_line(report)
        if job.get('cap_reached'):
            if bad:
                job['outcome'] = 'cap; changes outside May change'
                self.set_state(st, c, 'triage', 'builder reached its cap (%d tokens); nothing committed because it changed paths outside May change: %s' % (c['tokens_builder'], ', '.join(bad[:10])))
                return
            self.commit_builder(st, c, wt, paths, job, note='builder reached cap')
            job['outcome'] = 'cap'
            self.set_state(st, c, 'triage', 'builder reached its cap (%d of %d tokens); allowed changes committed' % (c['tokens_builder'], card.cap_builder))
            return
        if verdict is None:
            if bad:
                job['outcome'] = 'changes outside May change'
                self.set_state(st, c, 'triage', 'builder changed paths outside its May change line (nothing committed): %s' % ', '.join(bad[:10]))
                return
            self.interrupted(st, c, card, job, sess, 'ended without its report (exit %s)' % job['rc'])
            return
        if bad:
            job['outcome'] = 'changes outside May change'
            self.set_state(st, c, 'triage', 'builder changed paths outside its May change line (nothing committed): %s' % ', '.join(bad[:10]))
            return
        commit = self.commit_builder(st, c, wt, paths, job)
        job['outcome'] = verdict
        c['builder_verdict'] = verdict
        c['builder_vendor'] = job['vendor']
        c['judge_commit'] = commit
        if verdict in ('DONE', 'FINDING'):
            c['review_attempt'] = 0
            c['rereview'] = None
            self.set_state(st, c, 'reviewing', 'builder %s; reviewer to judge %s' % (verdict, commit[:12]))
            if len(self.running_sessions(st)) < MAX_SESSIONS:
                self.start_reviewer(st, c, card, sess)
        else:
            self.set_state(st, c, 'triage', 'builder reported %s (reports/%s-b%d.md)' % (verdict, cid, c['round']))

    def commit_builder(self, st, c, wt, paths, job, note=''):
        cid = c['id']
        if paths:
            git(['add', '-A', '--'] + paths, cwd=wt)
        staged = git(['diff', '--cached', '--name-only'], cwd=wt)
        if staged or git(['rev-parse', 'HEAD'], cwd=wt) == c['round_base']:
            msg = ('%s: builder round %d%s\n\nCampaign: builder round %s r%d, session %s (%s/%s); every path checked '
                   'against the card\'s May change line: %s' % (cid, c['round'], (' (' + note + ')') if note else '', cid,
                                                              c['round'], job['id'], job['vendor'], job['model'],
                                                              ', '.join(paths) or 'no changes'))
            git(['commit', '-q', '--allow-empty', '-m', msg], cwd=wt)
        sha = git(['rev-parse', 'HEAD'], cwd=wt)
        st.journal('commit-builder', card=cid, round=c['round'], sha=sha)
        return sha

    def reviewer_ended(self, st, c, card, job, sess):
        cid = c['id']
        wt = job['wt']
        c['job'] = None
        limit, reset = hit_usage_limit(job, sess) if not job.get('cap_reached') else (False, None)
        if limit:
            self.pause_vendor(st, job['vendor'], reset)
            job['state'] = 'limit'
            job['outcome'] = 'usage limit'
            c['job'] = job['id']
            return
        auth = hit_auth_failure(job, sess) if not job.get('cap_reached') else None
        if auth:
            self.auth_pause(st, job['vendor'], job, auth)
            c['job'] = job['id']
            return
        if job.get('cap_reached'):
            job['outcome'] = 'cap'
            self.remove_wt(wt)
            self.set_state(st, c, 'triage', 'reviewer reached its cap (%d of %d tokens)' % (c['tokens_reviewer'], card.cap_reviewer))
            return
        rname = 'reviews/%s-r%d.md' % (cid, c['round'])
        head = git(['rev-parse', 'HEAD'], cwd=wt, check=False)
        status = subprocess.run(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=wt, capture_output=True,
                                text=True).stdout
        tracked_changed = [ln[3:] for ln in status.split('\n') if ln and not ln.startswith('??')]
        if head != job['commit'] or tracked_changed:
            job['outcome'] = 'changed tracked files: %s' % (', '.join(tracked_changed[:5]) or 'HEAD moved')
            st.journal('review-discarded', job=job['id'], card=cid, why=job['outcome'])
            self.remove_wt(wt)
            if c['review_attempt'] >= 2:
                self.set_state(st, c, 'triage', 'reviewer changed a tracked file twice (%s); reviews discarded' % job['outcome'])
            else:
                self.start_reviewer(st, c, card, sess, rereview=job.get('rereview'))
            return
        rpath = os.path.join(wt, rname)
        verdict = first_line(rpath)
        if verdict is None:
            self.interrupted(st, c, card, job, sess, 'ended without its verdict (exit %s)' % job['rc'])
            return
        job['outcome'] = verdict
        text = open(rpath, 'rb').read()
        if job.get('rereview'):
            sha = self.commit_review_on_main(st, c, rname, text, job, verdict)
            self.remove_wt(wt)
            if verdict == 'APPROVE':
                self.set_state(st, c, 'merged', 're-review approved (%s)' % sha[:12], rereview=None)
            elif verdict == 'REJECT':
                c['epoch_rounds'] = 0
                self.set_state(st, c, 'ready', 're-review rejected', rereview=None)
            else:
                self.set_state(st, c, 'triage', 're-review verdict %s' % verdict, rereview=None)
            return
        bwt = self.p.card_wt(cid)
        bhead = git(['rev-parse', 'HEAD'], cwd=bwt)
        if bhead != job['commit'] or changed_paths(bwt, 'HEAD'):
            self.remove_wt(wt)
            self.set_state(st, c, 'triage', 'card/%s moved or changed after the reviewed commit %s (now %s); review not committed' % (
                cid, job['commit'][:12], bhead[:12]))
            return
        os.makedirs(os.path.join(bwt, 'reviews'), exist_ok=True)
        with open(os.path.join(bwt, rname), 'wb') as f:
            f.write(text)
        git(['add', '--', rname], cwd=bwt)
        git(['commit', '-q', '-m', '%s: review of round %d: %s\n\nCampaign: review %s r%d by session %s (%s/%s) of commit %s; '
             'reviewer worktree had no tracked changes' % (cid, c['round'], verdict, cid, c['round'], job['id'], job['vendor'],
                                                           job['model'], job['commit'])], cwd=bwt)
        review_commit = git(['rev-parse', 'HEAD'], cwd=bwt)
        self.remove_wt(wt)
        c['review_commit'] = review_commit
        c['reviewer_job'] = job['id']
        c['reviewer_vendor'] = job['vendor']
        if verdict == 'APPROVE':
            if c.get('builder_verdict') == 'FINDING':
                self.set_state(st, c, 'triage', 'FINDING approved: the reviewer reproduced the repro (reviews/%s-r%d.md)' % (cid, c['round']))
                return
            self.set_state(st, c, 'merging', 'approved %s' % job['commit'][:12])
            st.d['merge_queue'].append({'kind': 'merge', 'card': cid, 'round': c['round'], 'approved': job['commit'],
                                        'review_commit': review_commit, 'reviewer_job': job['id'],
                                        'reviewer_vendor': job['vendor'], 'reviewer_model': job['model'],
                                        'builder_vendor': c.get('builder_vendor')})
        elif verdict == 'REJECT':
            if c['epoch_rounds'] >= MAX_ROUNDS:
                self.set_state(st, c, 'triage', 'third REJECT (reviews/%s-r%d.md)' % (cid, c['round']))
            else:
                self.set_state(st, c, 'ready', 'REJECT; next round answers reviews/%s-r%d.md' % (cid, c['round']))
        else:
            self.set_state(st, c, 'triage', 'reviewer verdict %s (reviews/%s-r%d.md)' % (verdict, cid, c['round']))

    def commit_review_on_main(self, st, c, rname, text, job, verdict):
        main = self.p.main_dir()
        with open(os.path.join(main, rname), 'wb') as f:
            f.write(text)
        git(['add', '--', rname], cwd=main)
        git(['commit', '-q', '-m', '%s: re-review: %s\n\nCampaign: re-review of %s after a contract change, session %s (%s/%s), '
             'at main %s' % (c['id'], verdict, c['id'], job['id'], job['vendor'], job['model'], job['commit'])], cwd=main)
        return git(['rev-parse', 'HEAD'], cwd=main)

    def remove_wt(self, wt):
        git(['worktree', 'remove', '--force', wt], cwd=self.p.main_dir(), check=False)
        shutil.rmtree(wt, ignore_errors=True)
        git(['worktree', 'prune'], cwd=self.p.main_dir(), check=False)

    def pause_vendor(self, st, vendor, reset):
        v = st.d['vendors'].setdefault(vendor, {})
        if reset:
            until = reset
            v['backoff'] = 0
        else:
            v['backoff'] = min(PAUSE_MAX, (v.get('backoff') or PAUSE_DEFAULT // 2) * 2)
            until = now() + v['backoff']
        v['paused_until'] = until
        st.journal('vendor-pause', vendor=vendor, until=iso(until), parsed=bool(reset))

    # ---------------------------------------------------------- merges and lands (jobs)
    def start_merge(self, st, item):
        job = new_job(st, item['kind'], **{k: v for k, v in item.items() if k != 'kind'})
        job['step'] = hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()[:16]
        job['main_before'] = git(['rev-parse', 'main'], cwd=self.p.main_dir())
        with open(os.path.join(job['dir'], 'merge.json'), 'w') as f:
            json.dump(job, f, indent=1)
        st.journal('%s-start' % item['kind'], job=job['id'], card=item.get('card'), step=job['step'])
        argv = [sys.executable, os.path.join(TOOLS, 'campaign.py'), '_merge', job['dir']]
        with open(os.path.join(job['dir'], 'cmd.json'), 'w') as f:
            json.dump({'argv': argv, 'cwd': self.p.wt}, f)
        with open(os.path.join(job['dir'], 'prompt.txt'), 'w') as f:
            f.write('')
        devnull = open(os.devnull, 'r+')
        subprocess.Popen([sys.executable, os.path.join(TOOLS, 'campaign.py'), '_job', job['dir']], stdin=devnull,
                         stdout=devnull, stderr=devnull, start_new_session=True, cwd=self.p.wt)
        job['state'] = 'running'
        job['started'] = now()
        job['vendor'] = None

    def monitor_merge(self, st, job):
        ex = job_exit(job)
        if ex is None and job_alive(job):
            return
        res_path = os.path.join(job['dir'], 'result.json')
        res = json.load(open(res_path)) if os.path.exists(res_path) else None
        if res is None:
            # killed mid-merge: did it reach main?
            if self.step_on_main(job['step']):
                res = {'ok': True, 'recovered': True, 'detail': 'found step %s on main after restart' % job['step']}
            else:
                st.journal('%s-lost' % job['kind'], job=job['id'], card=job.get('card'))
                job['state'] = 'ended'
                job['outcome'] = 'lost; requeued'
                st.d['merge_queue'][0]['attempts'] = st.d['merge_queue'][0].get('attempts', 0) + 1
                if st.d['merge_queue'][0]['attempts'] >= 3:
                    item = st.d['merge_queue'].pop(0)
                    if item['kind'] == 'merge':
                        self.set_state(st, self.card(st, item['card']), 'triage', 'merge job died three times')
                return
        job['state'] = 'ended'
        job['outcome'] = 'ok' if res.get('ok') else 'fail'
        item = st.d['merge_queue'].pop(0)
        st.journal('%s-end' % job['kind'], job=job['id'], card=job.get('card'), ok=res.get('ok'), detail=res.get('detail'))
        if job['kind'] == 'merge':
            c = self.card(st, item['card'])
            if res.get('ok'):
                self.set_state(st, c, 'merged', 'merged %s' % (res.get('merge') or '')[:12])
                self.after_merge(st, c)
            else:
                self.set_state(st, c, 'triage', 'merge failed: %s' % res.get('detail'))
        else:
            if res.get('ok'):
                for cid in res.get('failing_cards', []):
                    self.set_state(st, self.card(st, cid), 'triage', 'proof fails after land %s' % job.get('sha', '')[:12])
            st.d['lands'].append({'sha': item.get('sha'), 'ok': res.get('ok'), 'detail': res.get('detail'), 'at': iso()})
        if res.get('full_gate'):
            st.d['last_full_gate'] = res['full_gate']

    def step_on_main(self, step):
        out = git(['log', '--first-parent', '--format=%B', '-n', '200', 'main'], cwd=self.p.main_dir(), check=False)
        return ('Campaign-Step: %s' % step) in out

    def after_merge(self, st, c):
        """Re-review merged cards whose proofs use this card's contracts, if this merge answered a reopen."""
        for other, req in list((c.get('reopened_for') or {}).items()):
            oc = self.card(st, other)
            if oc['state'] == 'waiting':
                self.set_state(st, oc, 'ready', '%s merged again' % c['id'])
        cards = self.cards()
        if c.get('reopened_for') is not None:
            for k in cardlib.callers_of(cards, c['id']):
                oc = self.card(st, k)
                if oc['state'] == 'merged':
                    oc['rereview'] = 'contract change in %s' % c['id']
                    oc['round'] += 1
                    oc['review_attempt'] = 0
                    oc['job'] = None
                    self.set_state(st, oc, 'reviewing', 're-review after %s changed its contract' % c['id'])
            c['reopened_for'] = None
        # campaign finished?
        scope = self.scoped(st, cards)
        if scope and all(self.card(st, k)['state'] == 'merged' for k in scope) and not st.d.get('full_gate_queued'):
            st.d['full_gate_queued'] = True
            st.d['merge_queue'].append({'kind': 'land', 'sha': None, 'full_gate': True})


# =============================================================== merge and land jobs (run as `_merge <dir>`)

def ensure_merge_wt(p):
    main = p.main_dir()
    if not os.path.isdir(p.merge):
        git(['worktree', 'prune'], cwd=main, check=False)
        git(['worktree', 'add', '--detach', p.merge, 'main'], cwd=main)
    subprocess.run(['git', 'merge', '--abort'], cwd=p.merge, capture_output=True)
    git(['reset', '-q', '--hard'], cwd=p.merge)
    git(['clean', '-fdxq'], cwd=p.merge)
    git(['checkout', '-q', '--detach', 'main'], cwd=p.merge)


def run_gate(p, cwd, args, logpath):
    env = session_env()
    with open(logpath, 'w') as lf:
        rc = subprocess.run(['nice', '-n', '10', 'make', 'gate'] + args, cwd=cwd, stdout=lf, stderr=subprocess.STDOUT,
                            env=env).returncode
    text = open(logpath, errors='replace').read()
    res = [ln for ln in text.split('\n') if ln.startswith('RESULT gate ')]
    last = res[-1] if res else ''
    ok = rc == 0 and ' PASS ' in last + ' '
    failing = sorted(set(re.findall(r'^\s+prove (C-[0-9]{2})\s+FAIL', text, re.M)))
    return ok, last or '(no RESULT gate line; rc %s)' % rc, failing


def ff_main(p, sha, expect):
    main = p.main_dir()
    head = git(['rev-parse', 'main'], cwd=main)
    if head != expect:
        raise CampaignError('main moved during the merge (%s, expected %s)' % (head[:12], expect[:12]))
    if main == p.primary and current_branch(main) != 'main':
        git(['branch', '-f', 'main', sha], cwd=main)
    else:
        git(['merge', '-q', '--ff-only', sha], cwd=main)


def collect_results(p, mw, cids, round_, reviewer, commit=None, gate_log=None, merged=None):
    """Copy the gate's per-card evidence into evidence/results/C-XX.json (the input RESULTS.md and results.csv
    are generated from), and regenerate RESULTS.md, results.csv, CAMPAIGN.md and evidence/tokens.csv.
    A field the gate didn't rerun is kept as it was (a caller's gate reruns its proofs and coverage, not its mutants),
    and rec['provenance'][field] says which commit's gate produced each field and where its log is (decision C9)."""
    os.makedirs(os.path.join(mw, 'evidence', 'results'), exist_ok=True)
    for cid in cids:
        b = os.path.join(mw, 'proofs', cid, 'build')
        out = os.path.join(mw, 'evidence', 'results', cid + '.json')
        rec = json.load(open(out)) if os.path.exists(out) else {}
        rec['card'] = cid
        prov = rec.setdefault('provenance', {})
        for name in ('prove-summary', 'coverage-summary', 'mutants'):
            f = os.path.join(b, name + '.json')
            if os.path.exists(f):
                key = name.replace('-', '_')
                rec[key] = json.load(open(f))
                prov[key] = {'commit': commit, 'gate_log': gate_log, 'gate': merged}
        with open(out, 'w') as f:
            json.dump(rec, f, indent=1, sort_keys=True)
    src = os.path.join(p.state, 'tokens.csv')
    if os.path.exists(src):
        shutil.copy(src, os.path.join(mw, 'evidence', 'tokens.csv'))
    subprocess.run([sys.executable, os.path.join(mw, 'tools', 'results.py'), '--root', mw,
                    '--state', os.path.join(p.state, 'state.json')], check=True, cwd=mw)


def do_merge(p, job, logf):
    cid, rnd = job['card'], job['round']
    main_before = job['main_before']
    if git(['rev-parse', 'main'], cwd=p.main_dir()) != main_before:
        return {'ok': False, 'detail': 'main moved before the merge started'}
    cards = cardlib.load_all(p.main_dir())
    card = cards[cid]
    ensure_merge_wt(p)
    mw = p.merge
    head = git(['rev-parse', 'card/%s' % cid], cwd=mw)
    if head != job['review_commit']:
        return {'ok': False, 'detail': 'card/%s is at %s, not the review commit %s: the branch gained a commit after its review' % (
            cid, head[:12], job['review_commit'][:12])}
    parent = git(['rev-parse', job['review_commit'] + '^'], cwd=mw)
    if parent != job['approved']:
        return {'ok': False, 'detail': 'the review commit\'s parent %s is not the approved commit %s' % (parent[:12], job['approved'][:12])}
    rfiles = git(['diff', '--name-only', job['approved'], job['review_commit']], cwd=mw).split('\n')
    if rfiles != ['reviews/%s-r%d.md' % (cid, rnd)]:
        return {'ok': False, 'detail': 'the review commit changes %s, not just reviews/%s-r%d.md' % (rfiles, cid, rnd)}
    if job['reviewer_vendor'] == job.get('builder_vendor'):
        return {'ok': False, 'detail': 'reviewer and builder on the same vendor (%s)' % job['reviewer_vendor']}
    pm = subprocess.run(['git', 'merge', '--no-ff', '--no-commit', job['review_commit']], cwd=mw, capture_output=True, text=True)
    if pm.returncode != 0:
        return {'ok': False, 'detail': 'merge conflict: %s' % (pm.stdout + pm.stderr).strip()[:300]}
    paths = [x for x in git(['diff', '--cached', '--name-only', 'HEAD'], cwd=mw).split('\n') if x]
    bad = [x for x in paths if not (card.allows(x) or re.match(r'^reviews/%s-r[0-9]+\.md$' % cid, x))]
    if bad:
        return {'ok': False, 'detail': 'the merge touches paths outside %s\'s May change line and reviews: %s' % (cid, ', '.join(bad[:10]))}
    git(['commit', '-q', '-m', 'Merge %s round %d\n\nCampaign: merge %s r%d, approved commit %s (reviewer %s on %s/%s; builder on %s); '
         'paths checked against May change; gate below\nCampaign-Merge: %s' % (
             cid, rnd, cid, rnd, job['approved'], job['reviewer_job'], job['reviewer_vendor'], job['reviewer_model'],
             job.get('builder_vendor'), cid)], cwd=mw)
    merge_sha = git(['rev-parse', 'HEAD'], cwd=mw)
    glog = os.path.join(job['dir'], 'gate.log')
    log('merge %s: running make gate CARD=%s (log %s)' % (cid, cid, glog))
    ok, last, failing = run_gate(p, mw, ['CARD=%s' % cid, 'BASE=%s' % main_before], glog)
    if not ok:
        return {'ok': False, 'detail': 'gate failed: %s (log %s)' % (last, glog)}
    run_cards = sorted(set([cid] + [k for k in cardlib.callers_of(cards, cid)
                                    if os.path.exists(os.path.join(mw, 'proofs', k, 'Makefile'))]))
    os.makedirs(os.path.join(mw, 'evidence', 'gate'), exist_ok=True)
    shutil.copy(glog, os.path.join(mw, 'evidence', 'gate', '%s-r%d.log' % (cid, rnd)))
    # results are generated with this card already counted as merged
    collect_results(p, mw, [k for k in run_cards if os.path.exists(os.path.join(mw, 'proofs', k, 'Makefile'))], rnd, job,
                    commit=merge_sha, gate_log='evidence/gate/%s-r%d.log' % (cid, rnd), merged='make gate CARD=%s (merge of %s r%d)' % (cid, cid, rnd))
    git(['add', '-A', '--', 'evidence', 'RESULTS.md', 'results.csv', 'CAMPAIGN.md'], cwd=mw)
    git(['commit', '-q', '-m', '%s: results after merge\n\nCampaign: results and gate log for %s r%d; %s\nCampaign-Step: %s' % (
        cid, cid, rnd, last, job['step'])], cwd=mw)
    final = git(['rev-parse', 'HEAD'], cwd=mw)
    ff_main(p, final, main_before)
    return {'ok': True, 'merge': merge_sha, 'final': final, 'detail': last}


def land_paths_problems(paths, added):
    import lock as locklib
    frozen = [x for x in paths if any(x == f or (f.endswith('/') and x.startswith(f)) for f in locklib.FROZEN)
              and x not in locklib.EXEMPT]
    other = [x for x in paths if x not in frozen and not any(x == a or (a.endswith('/') and x.startswith(a)) for a in LAND_ALLOWED)
             and x != 'proof.lock']
    probs = []
    if other:
        probs.append('a land may touch only %s; this one touches %s' % (', '.join(LAND_ALLOWED), ', '.join(other[:10])))
    if frozen:
        if not any(a.startswith('evidence/approvals/') for a in added):
            probs.append('frozen files changed (%s) without a new approval record under evidence/approvals/' % ', '.join(frozen[:5]))
        if 'proof.lock' not in paths:
            probs.append('frozen files changed (%s) without an updated proof.lock in the same land' % ', '.join(frozen[:5]))
    if 'proof.lock' in paths and not frozen:
        probs.append('proof.lock changed without a frozen-file change')
    return probs, bool(frozen)


def do_land(p, job, logf):
    main_before = job['main_before']
    ensure_merge_wt(p)
    mw = p.merge
    if job.get('sha') is None:
        glog = os.path.join(job['dir'], 'gate.log')
        log('full gate at main (log %s)' % glog)
        ok, last, failing = run_gate(p, mw, [], glog)
        fg = {'ok': ok, 'result': last, 'at': iso(), 'main': main_before}
        os.makedirs(os.path.join(mw, 'evidence', 'gate'), exist_ok=True)
        name = 'full-%s.log' % dt.datetime.now().strftime('%Y%m%d-%H%M%S')
        shutil.copy(glog, os.path.join(mw, 'evidence', 'gate', name))
        git(['add', '--', 'evidence/gate/' + name], cwd=mw)
        git(['commit', '-q', '-m', 'Full gate: %s\n\nCampaign: full make gate at main %s after the last card merged; %s\nCampaign-Step: %s' % (
            'PASS' if ok else 'FAIL', main_before[:12], last, job['step'])], cwd=mw)
        ff_main(p, git(['rev-parse', 'HEAD'], cwd=mw), main_before)
        return {'ok': True, 'full_gate': fg, 'failing_cards': failing, 'detail': last}
    sha = job['sha']
    role_paths = job.get('role_paths')
    pm = subprocess.run(['git', 'merge', '--no-ff', '--no-commit', sha], cwd=mw, capture_output=True, text=True)
    if pm.returncode != 0:
        return {'ok': False, 'detail': 'land conflicts with main: %s' % (pm.stdout + pm.stderr).strip()[:300]}
    paths = [x for x in git(['diff', '--cached', '--name-only', 'HEAD'], cwd=mw).split('\n') if x]
    added = [x for x in git(['diff', '--cached', '--name-only', '--diff-filter=A', 'HEAD'], cwd=mw).split('\n') if x]
    if role_paths is not None:
        bad = [x for x in paths if not any(x.startswith(r) for r in role_paths)]
        probs, frozen = (['the session wrote outside %s: %s' % (role_paths, bad[:10])] if bad else []), False
    else:
        probs, frozen = land_paths_problems(paths, added)
    if probs:
        return {'ok': False, 'detail': '; '.join(probs)}
    what = job.get('what') or 'orch %s' % sha[:12]
    git(['commit', '-q', '-m', 'Land %s\n\nCampaign: land %s; paths checked: %s%s\nCampaign-Step: %s' % (
        what, what, ', '.join(paths[:20]) + (' ...' if len(paths) > 20 else ''),
        '; frozen files changed with approval record and proof.lock, full gate below' if frozen else '', job['step'])], cwd=mw)
    res = {'ok': True, 'detail': 'landed %s (%d paths)' % (what, len(paths))}
    if frozen:
        glog = os.path.join(job['dir'], 'gate.log')
        ok, last, failing = run_gate(p, mw, [], glog)
        res['full_gate'] = {'ok': ok, 'result': last, 'at': iso(), 'main': main_before}
        res['failing_cards'] = failing
        res['detail'] += '; full gate %s' % last
    ff_main(p, git(['rev-parse', 'HEAD'], cwd=mw), main_before)
    return res


def cmd_merge(jdir):
    global LOGF
    job = json.load(open(os.path.join(jdir, 'merge.json')))
    p = P()
    LOGF = open(os.path.join(jdir, 'merge.log'), 'a')
    try:
        if Campaign(p).step_on_main(job['step']):
            res = {'ok': True, 'detail': 'already on main (step %s)' % job['step']}
        elif job['kind'] == 'merge':
            res = do_merge(p, job, LOGF)
        else:
            res = do_land(p, job, LOGF)
    except (GitError, CampaignError, subprocess.CalledProcessError, OSError) as e:
        res = {'ok': False, 'detail': '%s: %s' % (type(e).__name__, e)}
    tmp = os.path.join(jdir, 'result.json.tmp')
    with open(tmp, 'w') as f:
        json.dump(res, f, indent=1)
    os.replace(tmp, os.path.join(jdir, 'result.json'))
    return 0


# =============================================================== commands

def daemon_alive(p):
    lf = os.path.join(p.state, 'daemon.lock')
    if not os.path.exists(lf):
        return False
    with open(lf, 'a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f, fcntl.LOCK_UN)
            return False
        except OSError:
            return True


def reconcile_merged(p, st, camp, scope):
    """Cards merged on main (a Campaign-Merge trailer on main's first-parent history) are merged."""
    out = git(['log', '--first-parent', '--format=%B', 'main'], cwd=p.main_dir(), check=False)
    merged = set(re.findall(r'^Campaign-Merge: (C-[0-9]{2})$', out, re.M))
    for cid in scope:
        c = camp.card(st, cid)
        if cid in merged and c['state'] in ('waiting', 'ready'):
            camp.set_state(st, c, 'merged', 'found merged on main')


def cmd_start(a):
    p = P()
    camp = Campaign(p)
    with State(p) as st:
        if not st.d['started']:
            if current_branch(p.primary) != 'main':
                raise CampaignError('the primary checkout must be on main to start (it is on %s)' % current_branch(p.primary))
            dirty = changed_paths(p.primary, 'HEAD')
            if dirty:
                raise CampaignError('the primary checkout has uncommitted changes: %s' % ', '.join(dirty[:10]))
            git(['checkout', '-q', '-B', 'orch', 'main'], cwd=p.primary)
            if os.path.isdir(p.mainwt):
                raise CampaignError('%s exists already' % p.mainwt)
            git(['worktree', 'add', '-q', p.mainwt, 'main'], cwd=p.primary)
            st.d['started'] = True
            st.d['started_at'] = iso()
            st.journal('start', primary=p.primary, main=p.mainwt)
        if a.cards:
            st.d['scope'] = sorted(x.strip() for x in a.cards.split(',') if x.strip())
        st.d['stopping'] = False
        st.d['full_gate_queued'] = st.d.get('full_gate_queued') and False
        cards = camp.cards()
        scope = camp.scoped(st, cards)
        missing = [x for x in (st.d.get('scope') or []) if x not in cards]
        if missing:
            raise CampaignError('no card files for %s' % ', '.join(missing))
        for cid in scope:
            camp.card(st, cid)
        reconcile_merged(p, st, camp, scope)
    if daemon_alive(p):
        print('campaign.py daemon already running')
    else:
        exe = os.path.join(p.mainwt, 'tools', 'campaign.py')
        if a.no_tmux:
            out = open(os.path.join(p.state, 'daemon.out'), 'a')
            subprocess.Popen([sys.executable, exe, 'daemon'], stdout=out, stderr=out, stdin=subprocess.DEVNULL,
                             start_new_session=True, cwd=p.mainwt, env=dict(os.environ))
        else:
            subprocess.run(['tmux', 'kill-session', '-t', 'campaign'], capture_output=True)
            # the tmux server's environment may predate this shell's PATH (codex lives under nvm), so pass it
            import shlex
            subprocess.run(['tmux', 'new-session', '-d', '-s', 'campaign', '-c', p.mainwt,
                            'env PATH=%s %s %s daemon; echo "campaign.py daemon exited"; sleep 86400' % (
                                shlex.quote(os.environ.get('PATH', '')), sys.executable, exe)], check=True)
        for _ in range(50):
            if daemon_alive(p):
                break
            time.sleep(0.2)
        print('campaign.py daemon %s' % ('started' if daemon_alive(p) else 'NOT RUNNING (see %s)' % os.path.join(p.state, 'daemon.log')))
    print_status(p)
    return 0


def cmd_daemon(a):
    global LOGF
    p = P()
    os.makedirs(p.state, exist_ok=True)
    lockf = open(os.path.join(p.state, 'daemon.lock'), 'a')
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print('daemon already running')
        return 1
    LOGF = open(os.path.join(p.state, 'daemon.log'), 'a')
    with open(os.path.join(p.state, 'daemon.pid'), 'w') as f:
        f.write('%d\n' % os.getpid())
    camp = Campaign(p)
    log('daemon started (pid %d, tools %s)' % (os.getpid(), TOOLS))
    while True:
        try:
            with State(p) as st:
                if st.d.get('stopping'):
                    st.journal('daemon-stop')
                    break
                camp.tick(st)
        except (GitError, CampaignError, cardlib.CardFormatError, OSError, ValueError, KeyError) as e:
            log('tick error: %s: %s' % (type(e).__name__, e))
        time.sleep(TICK)
    log('daemon exiting; running sessions carry on')
    return 0


def cmd_stop(a):
    p = P()
    with State(p) as st:
        st.d['stopping'] = True
        st.journal('stop-requested')
    for _ in range(int(max(30, TICK * 6))):
        if not daemon_alive(p):
            break
        time.sleep(1)
    print('campaign.py %s' % ('stopped' if not daemon_alive(p) else 'still stopping'))
    return 0


def cmd_finish(a):
    p = P()
    cmd_stop(a)
    if daemon_alive(p):
        raise CampaignError('the daemon has not stopped')
    with State(p) as st:
        running = [j for j in st.d['jobs'].values() if j['state'] == 'running' and job_alive(j)]
        if running:
            raise CampaignError('jobs still running: %s; wait for them or kill them first' % ', '.join(j['id'] for j in running))
        if not st.d['started']:
            print('campaign not started; nothing to finish')
            return 0
        if current_branch(p.primary) != 'orch':
            raise CampaignError('the primary checkout should be on orch (it is on %s)' % current_branch(p.primary))
        dirty = changed_paths(p.primary, 'HEAD')
        if dirty:
            raise CampaignError('commit your changes on orch first: %s' % ', '.join(dirty[:10]))
        pm = subprocess.run(['git', 'merge', '--no-edit', '-q', '-m', orch_merge_msg(p, 'finish'), 'main'], cwd=p.primary,
                            capture_output=True, text=True)
        if pm.returncode != 0:
            subprocess.run(['git', 'merge', '--abort'], cwd=p.primary, capture_output=True)
            raise CampaignError('merging main into orch conflicts: %s' % pm.stdout.strip()[:300])
        paths = [x for x in git(['diff', '--name-only', 'main', 'orch'], cwd=p.primary).split('\n') if x]
        added = [x for x in git(['diff', '--name-only', '--diff-filter=A', 'main', 'orch'], cwd=p.primary).split('\n') if x]
        probs, _ = land_paths_problems(paths, added)
        if probs:
            raise CampaignError('orch cannot be merged into main: ' + '; '.join(probs))
        if os.path.isdir(p.mainwt):
            if changed_paths(p.mainwt, 'HEAD'):
                raise CampaignError('%s has uncommitted changes' % p.mainwt)
            git(['worktree', 'remove', p.mainwt], cwd=p.primary)
        if os.path.isdir(p.merge):
            git(['worktree', 'remove', '--force', p.merge], cwd=p.primary, check=False)
        git(['checkout', '-q', 'main'], cwd=p.primary)
        if paths:
            git(['merge', '-q', '--no-ff', 'orch', '-m', 'Finish: merge orch\n\nCampaign: finish; orch merged into main, '
                 'paths checked against the land rules: %s' % ', '.join(paths[:20])], cwd=p.primary)
        git(['branch', '-D', 'orch'], cwd=p.primary, check=False)
        git(['worktree', 'prune'], cwd=p.primary, check=False)
        st.d['started'] = False
        st.d['stopping'] = False
        st.journal('finish', merged_orch_paths=len(paths))
    subprocess.run(['tmux', 'kill-session', '-t', 'campaign'], capture_output=True)
    print('finished: the primary checkout is on main%s' % (' with orch merged' if paths else ''))
    print_status(p)
    return 0


def card_line(cid, c, card, jobs):
    j = jobs.get(c.get('job') or '') or {}
    vendor = j.get('vendor') or c.get('builder_vendor') or '-'
    waiting = ''
    if c['state'] == 'waiting':
        waiting = 'deps ' + ','.join(card.depends) if card else ''
    elif c['state'] in ('triage', 'parked'):
        waiting = c.get('reason') or ''
    elif c['state'] == 'building' and j.get('state') == 'limit':
        waiting = 'usage limit on %s' % vendor
    elif c['state'] in ('building', 'reviewing') and j:
        waiting = '%s %s' % (j.get('id'), j.get('state'))
    elif c['state'] == 'merging':
        waiting = 'merge queue'
    capb = card.cap_builder if card else 0
    capr = card.cap_reviewer if card else 0
    return '%-5s %-9s r%-2d %-6s %13s %13s %s' % (
        cid, c['state'], c['round'], vendor, '%.2fM/%.0fM' % (c['tokens_builder'] / 1e6, capb / 1e6),
        '%.2fM/%.0fM' % (c['tokens_reviewer'] / 1e6, capr / 1e6), waiting[:110])


def print_status(p):
    d = State.read_only(p)
    if d is None:
        print('no campaign state yet (%s)' % p.state)
        print('RESULT status none')
        return
    try:
        cards = cardlib.load_all(p.main_dir())
    except cardlib.CardFormatError:
        cards = {}
    print('campaign: %s; daemon %s; primary on %s; main at %s' % (
        'started ' + d.get('started_at', '') if d.get('started') else 'not started',
        'running' if daemon_alive(p) else 'not running', current_branch(p.primary),
        git(['rev-parse', '--short', 'main'], cwd=p.main_dir(), check=False)))
    if d.get('scope'):
        print('scope: %s' % ', '.join(d['scope']))
    print('%-5s %-9s %-3s %-6s %13s %13s %s' % ('card', 'state', 'rnd', 'vendor', 'builder tok', 'reviewer tok', 'waiting on / reason'))
    for cid in sorted(d['cards']):
        print(card_line(cid, d['cards'][cid], cards.get(cid), d['jobs']))
    tri = sorted([(c.get('triage_seq', 0), c['id'], c.get('reason')) for c in d['cards'].values() if c['state'] == 'triage'] +
                 [(x.get('seq', 0), 'vendor ' + v, x.get('reason')) for v, x in sorted((d.get('vendor_triage') or {}).items())])
    print('triage queue: %s' % ('; '.join('%s (%s)' % (k, r) for _, k, r in tri) or 'empty'))
    print('merge queue: %s' % (', '.join(x.get('card') or ('land ' + (x.get('sha') or 'full gate')[:12]) for x in d['merge_queue']) or 'empty'))
    pauses = ['%s until %s' % (v, iso(x['paused_until'])) for v, x in sorted(d['vendors'].items()) if x.get('paused_until', 0) > now()]
    pauses += ['%s until its login is fixed (since %s)' % (v, x['auth_failed'].get('at')) for v, x in sorted(d['vendors'].items())
               if x.get('auth_failed')]
    print('vendor pauses: %s' % (', '.join(pauses) or 'none'))
    run = [j for j in d['jobs'].values() if j['state'] in ('running', 'limit', 'auth')]
    print('running jobs: %s' % (', '.join('%s(%s %s)' % (j['id'], j.get('card') or j.get('role') or '', j['state']) for j in run) or 'none'))
    fg = d.get('last_full_gate')
    print('last full gate: %s' % ('%s at %s' % (fg.get('result'), fg.get('at')) if fg else 'none'))
    n = {}
    for c in d['cards'].values():
        n[c['state']] = n.get(c['state'], 0) + 1
    print('RESULT status %s' % ' '.join('%s=%d' % kv for kv in sorted(n.items())))


def cmd_status(a):
    print_status(P())
    return 0


def triage_signature(d):
    return sorted([(c['id'], c.get('triage_seq')) for c in d.get('cards', {}).values() if c['state'] == 'triage'] +
                  [('vendor ' + v, x.get('seq')) for v, x in (d.get('vendor_triage') or {}).items()])


def cmd_resume_vendor(a):
    """Lift an auth pause once the vendor's login check passes; its paused sessions resume on the next tick."""
    p = P()
    camp = Campaign(p)
    sess = camp.sess()
    if a.vendor not in sess.get('vendors', {}):
        raise CampaignError('no vendor %s in sessions.toml' % a.vendor)
    ok, out = login_ok(sess, a.vendor)
    if not ok:
        print('resume-vendor: %s login check still fails: %s' % (a.vendor, out))
        return 1
    with State(p) as st:
        v = st.d['vendors'].setdefault(a.vendor, {})
        was = v.pop('auth_failed', None)
        (st.d.get('vendor_triage') or {}).pop(a.vendor, None)
        st.journal('vendor-auth-resume', vendor=a.vendor, was=bool(was), login=out[:120])
    print('resume-vendor: %s login check passes; %s' % (a.vendor, 'paused sessions resume on the next tick' if was else 'it was not paused'))
    print_status(p)
    return 0


def cmd_wait(a):
    p = P()
    t0 = now()
    d0 = State.read_only(p) or {'cards': {}}
    tri0 = triage_signature(d0)
    reason = None
    while reason is None:
        time.sleep(min(20, max(1, TICK)))
        d = State.read_only(p) or {'cards': {}, 'merge_queue': []}
        tri = triage_signature(d)
        scope = d.get('scope') or sorted(d['cards'])
        if tri != tri0:
            reason = 'triage queue changed'
        elif scope and all(d['cards'].get(k, {}).get('state') in ('merged', 'parked') for k in scope) and not d.get('merge_queue'):
            reason = 'campaign finished (every card merged or parked)'
        elif not daemon_alive(p):
            reason = 'campaign.py is not running'
        elif now() - t0 > float(a.max or WAIT_MAX):
            reason = 'four hours passed'
    print('wait: %s' % reason)
    print_status(p)
    return 0


def cmd_retry(a):
    p = P()
    camp = Campaign(p)
    with State(p) as st:
        c = st.d['cards'].get(a.card)
        if not c or c['state'] not in ('triage', 'parked'):
            raise CampaignError('%s is not in triage or parked' % a.card)
        if a.note:
            c['notes'].append(a.note)
        c['epoch_rounds'] = 0
        c['interruptions'] = 0
        camp.set_state(st, c, 'ready', 'retry' + (': ' + a.note if a.note else ''))
    print_status(p)
    return 0


def cmd_park(a):
    p = P()
    camp = Campaign(p)
    with State(p) as st:
        c = st.d['cards'].get(a.card)
        if not c or c['state'] != 'triage':
            raise CampaignError('%s is not in triage' % a.card)
        camp.set_state(st, c, 'parked', a.note or c.get('reason'))
    print_status(p)
    return 0


def cmd_reopen(a):
    p = P()
    camp = Campaign(p)
    with State(p) as st:
        c = st.d['cards'].get(a.card)
        o = st.d['cards'].get(a.for_)
        if not c or c['state'] != 'merged':
            raise CampaignError('%s is not merged' % a.card)
        if not o:
            raise CampaignError('no card %s in the campaign' % a.for_)
        note = 'Reopened for %s: %s' % (a.for_, a.note or 'see its NEEDS-DECISION report')
        c['notes'].append(note)
        c['reopened_for'] = dict(c.get('reopened_for') or {}, **{a.for_: note})
        c['epoch_rounds'] = 0
        camp.set_state(st, c, 'ready', note)
        if o['state'] in ('triage', 'parked', 'ready'):
            camp.set_state(st, o, 'waiting', 'waits for %s to merge again' % a.card)
    print_status(p)
    return 0


def orch_merge_msg(p, why):
    return ('Merge main into orch\n\nCampaign: %s; main %s merged into orch, the orchestrator\'s checkout, so it lands '
            'on current main; no conflicts' % (why, git(['rev-parse', '--short', 'main'], cwd=p.primary)))


def cmd_land(a):
    p = P()
    if current_branch(p.primary) != 'orch':
        raise CampaignError('land runs on branch orch in %s (it is on %s)' % (p.primary, current_branch(p.primary)))
    dirty = changed_paths(p.primary, 'HEAD')
    if dirty:
        raise CampaignError('commit your changes on orch first: %s' % ', '.join(dirty[:10]))
    pm = subprocess.run(['git', 'merge', '--no-edit', '-q', '-m', orch_merge_msg(p, 'land'), 'main'], cwd=p.primary,
                        capture_output=True, text=True)
    if pm.returncode != 0:
        subprocess.run(['git', 'merge', '--abort'], cwd=p.primary, capture_output=True)
        raise CampaignError('merging main into orch conflicts: %s' % (pm.stdout + pm.stderr).strip()[:300])
    paths = [x for x in git(['diff', '--name-only', 'main', 'orch'], cwd=p.primary).split('\n') if x]
    added = [x for x in git(['diff', '--name-only', '--diff-filter=A', 'main', 'orch'], cwd=p.primary).split('\n') if x]
    if not paths:
        print('land: orch has nothing main lacks')
        return 0
    probs, frozen = land_paths_problems(paths, added)
    if probs:
        print('land refused: ' + '; '.join(probs))
        return 1
    sha = git(['rev-parse', 'orch'], cwd=p.primary)
    with State(p) as st:
        st.d['merge_queue'].append({'kind': 'land', 'sha': sha, 'frozen': frozen, 'what': 'orch %s' % sha[:12]})
        st.journal('land-queued', sha=sha, paths=len(paths), frozen=frozen)
    print('land queued: orch %s, %d paths%s; the daemon lands it' % (sha[:12], len(paths), ', frozen files changed: full gate' if frozen else ''))
    return 0


def cmd_session(a):
    p = P()
    camp = Campaign(p)
    role = a.role
    if role not in ROLE_PATHS:
        raise CampaignError('one-off roles: %s' % ', '.join(ROLE_PATHS))
    tier = 'standard' if role == 'spec-review' else 'high'
    sess = camp.sess()
    vendor, model, effort, vcfg = role_config(sess, role, tier)
    if role == 'spec-review' and vendor == 'claude':
        raise CampaignError('the spec was written by Claude; its reviewer must run on the other vendor')
    with State(p) as st:
        n = 1 + sum(1 for j in st.d['jobs'].values() if j['kind'] == 'oneoff' and j.get('role') == role)
        branch = 'session/%s-%d' % (role, n)
        wt = os.path.join(p.wt, 'session-%s-%d' % (role, n))
        git(['worktree', 'add', '-q', '-b', branch, wt, 'main'], cwd=p.main_dir())
        base = git(['rev-parse', 'HEAD'], cwd=wt)
        job = new_job(st, 'oneoff', role=role, card=None, round=n, tier=tier)
        camp.start_session(st, job, vendor, model, effort, vcfg, wt, prompt_oneoff(role, n))
        jid = job['id']
    print('session %s started: %s on %s/%s in %s' % (jid, role, vendor, model, wt))
    while True:
        time.sleep(min(30, max(1, TICK)))
        with State(p) as st:
            job = st.d['jobs'][jid]
            u, sid = usage_of(job)
            job['usage'] = u
            job['cli_session'] = sid or job.get('cli_session')
            ex = job_exit(job)
            if ex is None and job_alive(job):
                continue
            job['rc'] = (ex or {}).get('rc', 'lost')
            job['ended'] = (ex or {}).get('ended', now())
            auth = hit_auth_failure(job, sess)
            if auth:
                camp.auth_pause(st, vendor, job, auth)
                camp.record_tokens(job)
                print('%s login failed (%s); sign in again, run `tools/campaign.py resume-vendor %s`, then rerun this '
                      'session' % (vendor, auth, vendor))
                return 1
            limit, reset = hit_usage_limit(job, sess)
            if limit:
                camp.pause_vendor(st, vendor, reset)
                until = st.d['vendors'][vendor]['paused_until']
                job['state'] = 'resumed'
                camp.record_tokens(job)
                print('usage limit on %s; waiting until %s' % (vendor, iso(until)))
                st.save()
                time.sleep(max(0, until - now()))
                nj = new_job(st, 'oneoff', role=role, card=None, round=n, tier=tier)
                camp.start_session(st, nj, vendor, model, effort, vcfg, wt,
                                   prompt_resume('ledger' if role == 'ledger' else 'reviewer') if job.get('cli_session') else prompt_oneoff(role, n),
                                   resume_of=job)
                jid = nj['id']
                continue
            job['state'] = 'ended'
            camp.record_tokens(job)
            break
    paths = changed_paths(wt, base)
    bad = [x for x in paths if not any(x.startswith(r) for r in ROLE_PATHS[role])]
    if bad:
        print('session wrote outside %s: %s; nothing committed (worktree %s kept)' % (ROLE_PATHS[role], ', '.join(bad[:10]), wt))
        return 1
    if not paths:
        print('session ended (exit %s) without writing anything; worktree %s' % (job['rc'], wt))
        return 1
    git(['add', '-A', '--'] + paths, cwd=wt)
    git(['commit', '-q', '-m', 'Session %s %d\n\nCampaign: one-off %s session %s (%s/%s); paths checked against %s: %s' % (
        role, n, role, jid, vendor, model, ROLE_PATHS[role], ', '.join(paths[:20]))], cwd=wt)
    sha = git(['rev-parse', 'HEAD'], cwd=wt)
    with State(p) as st:
        if st.d['started']:
            st.d['merge_queue'].append({'kind': 'land', 'sha': sha, 'role_paths': ROLE_PATHS[role],
                                        'what': '%s session %d (%s)' % (role, n, branch)})
            print('committed %s on %s; queued to land on main' % (sha[:12], branch))
        else:
            print('committed %s on %s (campaign not started: merge it into main yourself)' % (sha[:12], branch))
    first = None
    for x in paths:
        if x.endswith('.md') and (x.startswith('reviews/') or x.startswith('reports/')):
            first = first_line(os.path.join(wt, x))
            print('verdict line of %s: %s' % (x, first))
    print('RESULT session %s %s %s' % (role, jid, first or 'written'))
    return 0


# =============================================================== selftest

FIXTURE_GATE = r'''#!/usr/bin/env python3
"""Fake gate for campaign.py selftest: FAKEGATE_CONTROL maps a card to pass, fail or slow:<s>."""
import json, os, sys, time
card = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else 'all'
ctl = json.load(open(os.environ['FAKEGATE_CONTROL'])) if os.environ.get('FAKEGATE_CONTROL') else {}
b = ctl.get(card, 'pass')
print('fake gate for %s: %s' % (card, b))
if b.startswith('slow:'):
    time.sleep(float(b.split(':')[1])); b = 'pass'
print('RESULT gate %s %s 1s %s' % (card, 'PASS' if b == 'pass' else 'FAIL', '0 failed' if b == 'pass' else 'failed: prove %s' % card))
sys.exit(0 if b == 'pass' else 1)
'''

FIXTURE_MAKEFILE = '''MAKEFLAGS += --no-print-directory
CARD ?=
BASE ?=
gate:
\t@python3 fakegate.py $(CARD)
'''


def fixture_card(cid, deps='none', tier='standard', cap='10M'):
    return ('# %s: fake%s\n- Property: P1\n- Functions: fake%s (upstream/sqlite3.c:1)\n'
            '- In-scope callees, with approved contracts: none\n- Boundary callees, with ledger entries: none\n'
            '- In-scope callers, whose call sites must satisfy the requires: none\n- Depends on: %s\n'
            '- May change: proofs/%s/harness.c, proofs/%s/Makefile, proofs/%s/NOTES.md, reports/%s-b*.md\n'
            '- Cap: builder %s; reviewer half that. Tier: %s\n- Notes: selftest fixture\n') % (
        cid, cid[2:], cid[2:], deps, cid, cid, cid, cid, cap, tier)


class SelfTest:
    PHASE_A = {
        'C-01': ('approved and merged', {}),
        'C-02': ('a rejection whose second round answers the review', {'C-02/reviewer/1': ['reject'], 'C-02/builder/2': ['answer-review']}),
        'C-03': ('three rejections', {'C-03/reviewer/*': ['reject']}),
        'C-04': ('a crash that it resumes', {'C-04/builder/1': ['crash', 'done']}),
        'C-05': ('three crashes in one round', {'C-05/builder/1': ['crash', 'crash', 'crash']}),
        'C-06': ('a usage limit pauses the vendor until the reset', {'C-06/builder/1': ['limit', 'done']}),
        'C-07': ('a builder that changes a file outside May change', {'C-07/builder/1': ['outside']}),
        'C-08': ('a builder that commits a file outside May change', {'C-08/builder/1': ['commit-outside']}),
        'C-09': ('a reviewer that changes a tracked file, twice', {'C-09/reviewer/1': ['touch-tracked', 'touch-tracked']}),
        'C-10': ('a reviewer that changes a tracked file once, then is rerun', {'C-10/reviewer/1': ['touch-tracked', 'approve']}),
        'C-11': ('a gate failure after APPROVE', {}),
        'C-12': ('a session that reaches its cap', {'C-12/builder/1': ['burn']}),
        'C-13': ('a card whose dependency is not merged', {}),
        'C-14': ('a builder that writes its own review file', {'C-14/builder/1': ['own-review']}),
        'C-15': ('a reviewer on the builder\'s vendor', {}),
        'C-16': ('a card branch that gains a commit after its review', {'C-16/reviewer/1': ['slow:4']}),
        'C-17': ('a FINDING the reviewer approves goes to triage, not merge', {'C-17/builder/1': ['finding']}),
        'C-18': ('an expired login pauses the vendor with a triage item, not counted against the card',
                 {'C-18/builder/1': ['auth', 'done']}),
        'C-19': ('a builder that leaves a symlink on a May change path', {'C-19/builder/1': ['symlink']}),
        'C-20': ('a builder that leaves an executable harness.c', {'C-20/builder/1': ['exec-mode']}),
    }
    PHASE_B = {
        'C-21': ('kill -9 the daemon mid-session', {'C-21/builder/1': ['slow:5', 'done']}),
        'C-22': ('kill -9 the session itself, then resume', {'C-22/builder/1': ['slow:30', 'done']}),
        'C-23': ('kill -9 daemon and merge job mid-merge', {}),
        'C-24': ('kill -9 the daemon mid-merge (merge job survives)', {}),
    }

    def __init__(self, keep):
        import tempfile
        # not under /tmp: a reviewer's sandbox gets a private /tmp, and the fixture's fake CLIs must stay visible
        self.base = tempfile.mkdtemp(prefix='campaign-selftest-', dir='/var/tmp' if os.path.isdir('/var/tmp') else None)
        self.keep = keep
        self.primary = os.path.join(self.base, 'proving-sqlite')
        self.wt = self.primary + '-wt'
        self.home = os.path.join(self.base, 'home')
        self.results = []
        self.ctl = os.path.join(self.base, 'fake-control.json')
        self.gctl = os.path.join(self.base, 'gate-control.json')
        self.fstate = os.path.join(self.home, '.claude', 'fakecli')    # writable inside a reviewer's sandbox
        self.marker = os.path.join('/tmp', 'campaign-selftest-marker-%d' % os.getpid())

    def ok(self, name, cond, detail=''):
        self.results.append((name, bool(cond)))
        print('%s %s%s' % ('ok  ' if cond else 'FAIL', name, '' if cond or not detail else '\n     | ' + str(detail)[:1500].replace('\n', '\n     | ')))
        sys.stdout.flush()

    def env(self):
        e = dict(os.environ)
        e['PATH'] = os.path.join(self.home, 'bin') + ':' + e.get('PATH', '')
        e['HOME'] = self.home
        e['FAKECLI_CONTROL'] = self.ctl
        e['FAKECLI_STATE'] = self.fstate
        e['FAKECLI_PROBE'] = json.dumps({
            'host /tmp': self.marker, 'state/': os.path.join(self.wt, 'state', 'state.json'),
            'main checkout': os.path.join(self.wt, 'main', 'cards'), '~/.codex': os.path.join(self.home, '.codex', 'sessions'),
            'primary checkout files': os.path.join(self.primary, 'PROGRESS.md'),
            'other worktree': os.path.join(self.wt, 'C-02', 'cards')})
        e['FAKEGATE_CONTROL'] = self.gctl
        e['CAMPAIGN_TICK'] = '0.3'
        for k in list(e):
            if k in STRIP_ENV or any(k.startswith(x) for x in STRIP_ENV_PREFIX):
                del e[k]
        # planted: campaign.py must strip these from every session it starts
        e['ANTHROPIC_API_KEY'] = 'selftest-fake-key'
        e['OPENAI_API_KEY'] = 'selftest-fake-key'
        e['CLAUDE_CODE_SESSION_ID'] = 'selftest-orchestrator-session'
        return e

    def camp(self, *args, check=False, timeout=120):
        p = subprocess.run([sys.executable, os.path.join(self.primary, 'tools', 'campaign.py')] + list(args),
                           cwd=self.primary, env=self.env(), capture_output=True, text=True, timeout=timeout)
        if check and p.returncode != 0:
            raise CampaignError('campaign.py %s failed: %s' % (' '.join(args), p.stdout + p.stderr))
        return p

    def state(self):
        path = os.path.join(self.wt, 'state', 'state.json')
        return json.load(open(path)) if os.path.exists(path) else {'cards': {}, 'jobs': {}, 'merge_queue': []}

    def journal(self):
        return read_jsonl(os.path.join(self.wt, 'state', 'journal.jsonl'))

    def fakelog(self):
        return read_jsonl(os.path.join(self.fstate, 'fakecli.log'))

    def build_fixture(self):
        os.makedirs(os.path.join(self.home, '.claude'))
        os.makedirs(os.path.join(self.home, '.codex', 'sessions'))
        open(os.path.join(self.home, '.claude.json'), 'w').write('{}')
        # the fake CLIs live outside the repo, as the real ones do: a reviewer's sandbox hides the primary checkout
        shutil.copytree(os.path.join(TOOLS, 'fakecli'), os.path.join(self.home, 'bin'), ignore=shutil.ignore_patterns('__pycache__'))
        open(self.marker, 'w').write('host /tmp marker\n')
        open(os.path.join(self.home, '.gitconfig'), 'w').write('[user]\n\tname = selftest\n\temail = selftest@example.invalid\n')
        os.makedirs(self.primary)
        shutil.copytree(TOOLS, os.path.join(self.primary, 'tools'), ignore=shutil.ignore_patterns('__pycache__', 'tests'))
        src_root = os.path.dirname(TOOLS)
        for f in ('AGENTS.md', '.gitignore'):
            if os.path.exists(os.path.join(src_root, f)):
                shutil.copy(os.path.join(src_root, f), os.path.join(self.primary, f))
        if os.path.isdir(os.path.join(src_root, 'agents')):
            shutil.copytree(os.path.join(src_root, 'agents'), os.path.join(self.primary, 'agents'))
        open(os.path.join(self.primary, 'Makefile'), 'w').write(FIXTURE_MAKEFILE)
        open(os.path.join(self.primary, 'fakegate.py'), 'w').write(FIXTURE_GATE)
        open(os.path.join(self.primary, 'PROGRESS.md'), 'w').write('# fixture progress\n')
        os.makedirs(os.path.join(self.primary, 'cards'))
        specs = {k: ('none', 'standard', '10M') for k in list(self.PHASE_A) + list(self.PHASE_B)}
        specs['C-13'] = ('C-03', 'standard', '10M')
        specs['C-12'] = ('none', 'standard', '1M')
        specs['C-15'] = ('none', 'high', '10M')
        for cid, (deps, tier, cap) in specs.items():
            open(os.path.join(self.primary, 'cards', cid + '.md'), 'w').write(fixture_card(cid, deps, tier, cap))
        # the one fixture change to sessions.toml: high-tier reviewers on codex, to test the vendor refusal
        sp = os.path.join(self.primary, 'tools', 'sessions.toml')
        s = open(sp).read()
        s = re.sub(r'(\[roles\.reviewer\.high\]\nvendor = )"claude"', r'\1"codex"', s)
        open(sp, 'w').write(s)
        ctl = {'limit_reset_seconds': 6, 'C-01/reviewer/1': ['probe']}
        for spec in list(self.PHASE_A.values()) + list(self.PHASE_B.values()):
            ctl.update(spec[1])
        json.dump(ctl, open(self.ctl, 'w'))
        json.dump({'C-11': 'fail', 'C-23': 'slow:8', 'C-24': 'slow:8'}, open(self.gctl, 'w'))
        env = self.env()
        for cmd in (['init', '-q', '-b', 'main'], ['add', '-A'], ['commit', '-qm', 'fixture']):
            subprocess.run(['git'] + cmd, cwd=self.primary, env=env, check=True, capture_output=True)

    def wait_for(self, pred, timeout, during=None):
        t0 = now()
        while now() - t0 < timeout:
            st = self.state()
            if during:
                during(st)
            if pred(st):
                return True
            time.sleep(0.3)
        return False

    def settled(self, cards):
        def pred(st):
            if st.get('merge_queue'):
                return False
            if any(j['state'] in ('running', 'limit') for j in st.get('jobs', {}).values()):
                return False
            for cid in cards:
                c = st['cards'].get(cid)
                if not c or c['state'] not in ('merged', 'triage', 'parked', 'waiting'):
                    return False
            return True
        return pred

    def main_log(self, rev='main'):
        return git(['log', '--first-parent', '--format=%H%x00%B%x01', rev], cwd=self.primary)

    def unit_checks(self):
        """In-process checks of the session guards (decisions C5 and C6): no daemon, no CLI."""
        p = P(self.primary)
        sess = load_sessions(self.primary)
        home = os.path.expanduser('~')
        rwt = os.path.join(p.wt, 'C-01-r1')

        def argv(vendor, key='start', edit=None):
            role = 'builder' if vendor == 'codex' else 'reviewer'
            v, m, e, cfg = role_config(sess, role, 'standard')
            a = fill(cfg[key], dir=rwt if vendor == 'claude' else os.path.join(p.wt, 'C-01'), model=m, effort=e,
                     session='S', home=home, wtroot=p.wt, repo=p.primary)
            return edit(a) if edit else a

        def probs(vendor, edit=None):
            return command_problems(vendor, argv(vendor, edit=edit), rwt if vendor == 'claude' else os.path.join(p.wt, 'C-01'), p)
        ok_now = not probs('codex') and not probs('claude') and not command_problems(
            'codex', argv('codex', 'resume'), os.path.join(p.wt, 'C-01'), p) and not command_problems('claude', argv('claude', 'resume'), rwt, p)
        self.ok('sessions.toml\'s codex and claude commands, start and resume, pass the session guards', ok_now,
                [probs('codex'), probs('claude')])

        def drop(pair):
            return lambda a: [x for i, x in enumerate(a) if not (x == pair[1] and i and a[i - 1] == pair[0]) and not (
                x == pair[0] and i + 1 < len(a) and a[i + 1] == pair[1])]
        cases = [
            ('codex without the workspace-write sandbox', 'codex', drop(('-c', 'sandbox_mode="workspace-write"')), 'sandbox_mode'),
            ('codex with approvals on', 'codex', lambda a: [x.replace('"never"', '"on-request"') for x in a], 'approval_policy'),
            ('codex with the sandbox bypassed', 'codex', lambda a: a[:2] + ['--dangerously-bypass-approvals-and-sandbox'] + a[2:], 'not allowed'),
            ('codex with a second sandbox_mode', 'codex', lambda a: a[:-1] + ['-c', 'sandbox_mode="danger-full-access"', '-'], 'exactly once'),
            ('claude without bwrap', 'claude', lambda a: a[a.index('claude'):], 'bwrap'),
            ('claude with bypassPermissions', 'claude', lambda a: [x if x != 'auto' else 'bypassPermissions' for x in a], 'not allowed'),
            ('bwrap with a shared /tmp', 'claude', lambda a: a[:a.index('/tmp') - 1] + ['--bind', '/tmp', '/tmp'] + a[a.index('/tmp') + 1:], '/tmp'),
            ('bwrap that leaves ~/.codex visible', 'claude', drop(('--tmpfs', os.path.join(home, '.codex'))), '.codex'),
            ('bwrap that leaves the other worktrees and state/ visible', 'claude', drop(('--tmpfs', p.wt)), 'state'),
            ('bwrap that binds / writable afterwards', 'claude', lambda a: a[:a.index('--chdir')] + ['--bind', '/', '/'] + a[a.index('--chdir'):], 'writable'),
        ]
        for name, vendor, edit, needle in cases:
            pr = probs(vendor, edit)
            self.ok('session guard refuses %s' % name, pr and any(needle in x for x in pr), pr)
        bad_sess = json.loads(json.dumps(sess))
        bad_sess['roles']['builder']['standard']['vendor'] = 'claude'
        try:
            role_config(bad_sess, 'builder', 'standard')
            refused = None
        except SessionRefused as e:
            refused = str(e)
        self.ok('campaign.py refuses a sessions.toml that puts builders on claude', refused and 'runs builder sessions on codex' in refused, refused)

        class FakeSt:
            d = {'triage_seq': 0, 'jobs': {}, 'job_seq': 0}

            def journal(self, *a, **k):
                pass
        st = FakeSt()

        class FakeCard:
            tier = 'standard'
            cap_reviewer = 1000000
        c = {'id': 'C-01', 'state': 'merged', 'round': 2, 'history': [], 'builder_vendor': 'claude', 'review_attempt': 0}
        Campaign(p).start_reviewer(st, c, FakeCard(), sess, rereview='contract change in C-02')
        self.ok('a re-review is refused when its reviewer would share the vendor that built the card\'s last round',
                c['state'] == 'triage' and 'refused to start a reviewer' in (c.get('reason') or '') and 're-review' in c['reason'], c)

    def run(self):
        self.build_fixture()
        print('selftest fixture: %s' % self.base)
        self.unit_checks()
        a_cards = sorted(self.PHASE_A)
        p = self.camp('start', '--no-tmux', '--cards', ','.join(a_cards))
        self.ok('start: primary checkout moves to orch, main gets its own checkout',
                p.returncode == 0 and current_branch(self.primary) == 'orch' and
                current_branch(os.path.join(self.wt, 'main')) == 'main', p.stdout + p.stderr)
        start_sha = git(['rev-parse', 'main'], cwd=self.primary)
        meddled = {}

        def intervene(st):
            # C-16: once its reviewer runs, the card branch gains a commit
            c = st['cards'].get('C-16') or {}
            j = st['jobs'].get(c.get('job') or '') or {}
            if c.get('state') == 'reviewing' and j.get('role') == 'reviewer' and j.get('state') == 'running' and 'C-16' not in meddled:
                w = os.path.join(self.wt, 'C-16')
                open(os.path.join(w, 'proofs', 'C-16', 'NOTES.md'), 'a').write('late change\n')
                subprocess.run(['git', 'commit', '-qam', 'late commit after review started'], cwd=w, env=self.env(), capture_output=True)
                meddled['C-16'] = True
            # the usage-limit pause: record codex starts while codex is paused
            for v, x in (st.get('vendors') or {}).items():
                if x.get('paused_until', 0) > now():
                    meddled.setdefault('pause_seen', x['paused_until'])
            # the auth pause: Zach hasn't signed in yet (resume-vendor refuses), then has (it resumes)
            cx = (st.get('vendors') or {}).get('codex') or {}
            if cx.get('auth_failed') and 'auth' not in meddled:
                meddled['auth'] = {'triage': dict((st.get('vendor_triage') or {}).get('codex') or {})}
                time.sleep(2)
                flag = os.path.join(self.home, '.fakecli-logged-out')
                open(flag, 'w').write('x')
                meddled['auth']['refused'] = self.camp('resume-vendor', 'codex').returncode
                os.remove(flag)
                r = self.camp('resume-vendor', 'codex')
                meddled['auth']['resumed'] = r.returncode
                meddled['auth']['out'] = r.stdout[-400:]
        done = self.wait_for(self.settled(a_cards), 420, during=intervene)
        st = self.state()
        self.ok('phase A settles (every card merged, in triage, or waiting)', done,
                json.dumps({k: (v['state'], v.get('reason')) for k, v in st['cards'].items()}, indent=0))
        cs = st['cards']
        S = lambda k: (cs.get(k) or {}).get('state')  # noqa: E731
        R = lambda k: (cs.get(k) or {}).get('reason') or ''  # noqa: E731
        log_main = self.main_log()
        self.ok('C-01 %s' % self.PHASE_A['C-01'][0], S('C-01') == 'merged' and 'Campaign-Merge: C-01' in log_main, R('C-01'))
        fl = self.fakelog()
        b2 = [x for x in fl if x['key'] == 'C-02/builder/2']
        self.ok('C-02 %s' % self.PHASE_A['C-02'][0], S('C-02') == 'merged' and b2 and 'reviews/C-02-r1.md' in b2[0]['prompt'], R('C-02'))
        self.ok('C-03 %s go to triage' % self.PHASE_A['C-03'][0], S('C-03') == 'triage' and 'third REJECT' in R('C-03'), R('C-03'))
        b4 = [x for x in fl if x['key'] == 'C-04/builder/1']
        self.ok('C-04 %s (with the CLI\'s resume command) and merges' % self.PHASE_A['C-04'][0],
                S('C-04') == 'merged' and len(b4) == 2 and b4[1]['resume'] and b4[1]['sid'] == b4[0]['sid'], [(x['resume'], x['sid']) for x in b4])
        self.ok('C-05 %s go to triage' % self.PHASE_A['C-05'][0], S('C-05') == 'triage' and 'three interruptions' in R('C-05'), R('C-05'))
        jr = self.journal()
        pause = [e for e in jr if e['kind'] == 'vendor-pause' and e.get('vendor') == 'codex']
        ok6 = S('C-06') == 'merged' and pause and cs['C-06']['interruptions'] == 0
        if pause:
            until = dt.datetime.fromisoformat(pause[0]['until']).timestamp()
            pts = dt.datetime.fromisoformat(pause[0]['ts']).timestamp()
            starts_in_pause = [e for e in jr if e['kind'] == 'session-start' and e.get('vendor') == 'codex'
                               and pts + 0.5 < dt.datetime.fromisoformat(e['ts']).timestamp() < until - 1]
            ok6 = ok6 and not starts_in_pause and pause[0].get('parsed')
        self.ok('C-06 %s, without counting against the card' % self.PHASE_A['C-06'][0], ok6,
                {'state': S('C-06'), 'pause': pause[:1], 'interruptions': cs.get('C-06', {}).get('interruptions')})
        cb = lambda k: git(['log', '--format=%s', 'main..card/%s' % k], cwd=self.primary, check=False)  # noqa: E731
        self.ok('C-07 %s: triage, nothing committed' % self.PHASE_A['C-07'][0],
                S('C-07') == 'triage' and 'outside its May change' in R('C-07') and 'builder round' not in cb('C-07'), R('C-07') + ' | ' + cb('C-07'))
        self.ok('C-08 %s: triage' % self.PHASE_A['C-08'][0], S('C-08') == 'triage' and 'tools/evil2.py' in R('C-08'), R('C-08'))
        disc = [e for e in jr if e['kind'] == 'review-discarded']
        self.ok('C-09 %s: discarded, rerun once, then triage' % self.PHASE_A['C-09'][0],
                S('C-09') == 'triage' and sum(1 for e in disc if e.get('card') == 'C-09') == 2, R('C-09'))
        self.ok('C-10 %s and merges' % self.PHASE_A['C-10'][0],
                S('C-10') == 'merged' and sum(1 for e in disc if e.get('card') == 'C-10') == 1, R('C-10'))
        self.ok('C-11 %s: triage with the gate log, main unchanged' % self.PHASE_A['C-11'][0],
                S('C-11') == 'triage' and 'gate failed' in R('C-11') and 'Campaign-Merge: C-11' not in log_main, R('C-11'))
        capj = [j for j in st['jobs'].values() if j.get('card') == 'C-12']
        self.ok('C-12 %s: stopped at the cap, allowed changes committed, triage' % self.PHASE_A['C-12'][0],
                S('C-12') == 'triage' and 'cap' in R('C-12') and any(j.get('cap_reached') for j in capj)
                and 'builder round 1 (builder reached cap)' in cb('C-12') and cs['C-12']['tokens_builder'] < 3_000_000,
                (R('C-12'), cs.get('C-12', {}).get('tokens_builder'), cb('C-12')))
        self.ok('C-13 %s stays waiting and never starts' % self.PHASE_A['C-13'][0],
                S('C-13') == 'waiting' and not any(j.get('card') == 'C-13' for j in st['jobs'].values()), S('C-13'))
        self.ok('C-14 %s: triage' % self.PHASE_A['C-14'][0], S('C-14') == 'triage' and 'reviews/C-14-r1.md' in R('C-14'), R('C-14'))
        self.ok('C-15 %s: refused, triage' % self.PHASE_A['C-15'][0],
                S('C-15') == 'triage' and 'refused to start a reviewer' in R('C-15')
                and not any(j.get('card') == 'C-15' and j.get('role') == 'reviewer' for j in st['jobs'].values()), R('C-15'))
        self.ok('C-16 %s: triage, not merged' % self.PHASE_A['C-16'][0],
                meddled.get('C-16') and S('C-16') == 'triage' and 'moved or changed' in R('C-16') and 'Campaign-Merge: C-16' not in log_main, R('C-16'))
        self.ok('C-17 %s' % self.PHASE_A['C-17'][0], S('C-17') == 'triage' and 'FINDING approved' in R('C-17'), R('C-17'))
        au = meddled.get('auth') or {}
        ap = [e for e in jr if e['kind'] == 'vendor-auth-pause' and e.get('vendor') == 'codex']
        ar = [e for e in jr if e['kind'] == 'vendor-auth-resume' and e.get('vendor') == 'codex']
        starts_in_auth = []
        if ap and ar:
            t_a = dt.datetime.fromisoformat(ap[0]['ts']).timestamp()
            t_r = dt.datetime.fromisoformat(ar[0]['ts']).timestamp()
            starts_in_auth = [e for e in jr if e['kind'] == 'session-start' and e.get('vendor') == 'codex'
                              and t_a + 0.5 < dt.datetime.fromisoformat(e['ts']).timestamp() < t_r - 0.5]
        self.ok('C-18 %s; resume-vendor refuses while logged out, then resumes it, and it merges' % self.PHASE_A['C-18'][0],
                S('C-18') == 'merged' and cs['C-18']['interruptions'] == 0 and ap and ar and not starts_in_auth
                and 'sign in again' in (au.get('triage') or {}).get('reason', '') and au.get('refused') == 1 and au.get('resumed') == 0
                and not st.get('vendor_triage', {}).get('codex'),
                {'state': S('C-18'), 'auth': au, 'starts_in_auth': starts_in_auth, 'pause': ap[:1], 'resume': ar[:1]})
        self.ok('C-19 %s: triage, nothing committed' % self.PHASE_A['C-19'][0],
                S('C-19') == 'triage' and 'symlink' in R('C-19') and 'builder round' not in cb('C-19'), R('C-19') + ' | ' + cb('C-19'))
        self.ok('C-20 %s: triage, nothing committed' % self.PHASE_A['C-20'][0],
                S('C-20') == 'triage' and '100755' in R('C-20') and 'builder round' not in cb('C-20'), R('C-20') + ' | ' + cb('C-20'))
        pr_ = [x for x in self.fakelog() if x.get('probe') is not None]
        seen = pr_[0]['probe'] if pr_ else {}
        self.ok('a reviewer\'s sandbox hides the host /tmp, state/, main\'s checkout, other worktrees, ~/.codex and the '
                'primary checkout, and its own worktree is writable',
                pr_ and seen.get('own worktree writable') and not any(v for k, v in seen.items() if k != 'own worktree writable'),
                seen)
        # every commit on main's first-parent history since start carries a Campaign: trailer
        recs = [r for r in git(['log', '--first-parent', '--format=%H%x00%B%x01', '%s..main' % start_sha], cwd=self.primary).split('\x01') if r.strip()]
        bad = [r.strip()[:60] for r in recs if 'Campaign:' not in r]
        self.ok('every commit campaign.py put on main carries a Campaign: trailer (%d commits)' % len(recs), recs and not bad, bad)
        # sessions: a reviewer never ran on the vendor that built its round
        same = [j['id'] for j in st['jobs'].values() if j.get('role') == 'reviewer' and not j.get('rereview')
                and j.get('vendor') == (cs.get(j.get('card')) or {}).get('builder_vendor')]
        self.ok('no reviewer ran on its round\'s builder vendor', not same, same)
        # lands
        pr = self.primary
        orch0 = git(['rev-parse', 'HEAD'], cwd=pr)
        os.makedirs(os.path.join(pr, 'proofs', 'C-01'), exist_ok=True)
        open(os.path.join(pr, 'proofs', 'C-01', 'sneak.c'), 'w').write('/* a proof via land */\n')
        subprocess.run(['git', 'add', '-A'], cwd=pr, env=self.env(), check=True)
        subprocess.run(['git', 'commit', '-qm', 'sneak a proof'], cwd=pr, env=self.env(), check=True)
        p = self.camp('land')
        self.ok('a land that touches proofs/ is refused', p.returncode != 0 and 'proofs/C-01/sneak.c' in p.stdout, p.stdout + p.stderr)
        subprocess.run(['git', 'reset', '-q', '--hard', orch0], cwd=pr, env=self.env(), check=True)
        open(os.path.join(pr, 'PROGRESS.md'), 'a').write('orchestrator note\n')
        subprocess.run(['git', 'commit', '-qam', 'progress'], cwd=pr, env=self.env(), check=True)
        p = self.camp('land')
        landed = self.wait_for(lambda s: not s.get('merge_queue') and any(l.get('ok') for l in s.get('lands', [])), 60)
        ml = git(['show', 'main:PROGRESS.md'], cwd=pr, check=False)
        self.ok('a land of PROGRESS.md is queued and lands on main with a trailer',
                p.returncode == 0 and landed and 'orchestrator note' in ml and 'Campaign: land orch' in self.main_log(), p.stdout + p.stderr)
        # every commit campaign.py made, on any branch, carries a trailer: its merges of main into card branches and
        # into orch included (checkpoint 0, decision C8). Excluded: commits the fixture's fake sessions and this test
        # make themselves, which campaign.py refuses or that the orchestrator writes.
        theirs = ('sneaky', 'late commit after review started', 'progress', 'sneak a proof')
        allc = [r for r in git(['log', '--branches', '--format=%H%x00%B%x01', '^' + start_sha], cwd=self.primary).split('\x01') if r.strip()]
        allc = [r for r in allc if r.split('\x00', 1)[1].strip().split('\n')[0] not in theirs]
        m_card = [r for r in allc if 'Merge main into card/' in r]
        m_orch = [r for r in allc if 'Merge main into orch' in r]
        bad = [r.split('\x00', 1)[1].strip()[:70] for r in allc if 'Campaign:' not in r]
        self.ok('every commit campaign.py made on any branch carries a Campaign: trailer, its merges of main into card '
                'branches (%d) and orch (%d) included (%d commits)' % (len(m_card), len(m_orch), len(allc)),
                allc and m_card and m_orch and not bad, bad)
        p = self.camp('status')
        self.ok('status prints every card, the triage and merge queues, pauses and the last full gate',
                all(k in p.stdout for k in ('C-01', 'triage queue:', 'merge queue:', 'vendor pauses:', 'last full gate:')), p.stdout)
        self.camp('stop', timeout=60)
        # ---------------------------------------------------------------- phase B: kill -9
        b_cards = sorted(self.PHASE_B)
        p = self.camp('start', '--no-tmux', '--cards', ','.join(b_cards))
        killed = {}

        def daemon_pid():
            try:
                return int(open(os.path.join(self.wt, 'state', 'daemon.pid')).read())
            except (OSError, ValueError):
                return None

        def restart():
            time.sleep(1)
            self.camp('start', '--no-tmux')

        def chaos(st):
            cs2 = st['cards']
            j21 = st['jobs'].get((cs2.get('C-21') or {}).get('job') or '') or {}
            if 'k1' not in killed and j21.get('state') == 'running' and j21.get('role') == 'builder' and now() - j21.get('started', now()) > 1:
                os.kill(daemon_pid(), signal.SIGKILL)
                killed['k1'] = True
                restart()
            j22 = st['jobs'].get((cs2.get('C-22') or {}).get('job') or '') or {}
            cp = os.path.join(j22.get('dir', '/nonexistent'), 'child.pid')
            if 'k2' not in killed and j22.get('role') == 'builder' and os.path.exists(cp) and now() - j22.get('started', now()) > 2:
                try:
                    os.kill(int(open(cp).read()), signal.SIGKILL)
                    killed['k2'] = True
                except (OSError, ValueError):
                    pass
            for k, key in (('k3', 'C-23'), ('k4', 'C-24')):
                mj = [j for j in st['jobs'].values() if j['kind'] == 'merge' and j.get('card') == key and j['state'] == 'running']
                if k not in killed and mj and now() - mj[0].get('started', now()) > 2:
                    os.kill(daemon_pid(), signal.SIGKILL)
                    if k == 'k3':
                        try:
                            os.killpg(int(open(os.path.join(mj[0]['dir'], 'pid')).read()), signal.SIGKILL)
                        except (OSError, ValueError):
                            pass
                    killed[k] = True
                    restart()
        done = self.wait_for(self.settled(b_cards), 300, during=chaos)
        st = self.state()
        cs = st['cards']
        jr = self.journal()
        log_main = self.main_log()
        starts = {}
        for e in jr:
            if e['kind'] == 'session-start' and e.get('card') in b_cards and not e.get('resume'):
                starts[(e['card'], e['role'], e['round'])] = starts.get((e['card'], e['role'], e['round']), 0) + 1
        self.ok('phase B settles', done, json.dumps({k: (v['state'], v.get('reason')) for k, v in cs.items() if k in b_cards}))
        self.ok('kill -9 of the daemon mid-session: restart neither loses nor repeats the session (C-21 merged, one start per session)',
                killed.get('k1') and cs['C-21']['state'] == 'merged' and starts.get(('C-21', 'builder', 1)) == 1
                and len([x for x in self.fakelog() if x['key'] == 'C-21/builder/1']) == 1, starts)
        f22 = [x for x in self.fakelog() if x['key'] == 'C-22/builder/1']
        self.ok('kill -9 of a session: it is resumed in the same worktree and the card merges (C-22)',
                killed.get('k2') and cs['C-22']['state'] == 'merged' and len(f22) == 2 and f22[1]['resume'] and f22[0]['cwd'] == f22[1]['cwd'], f22)
        n23 = log_main.count('Campaign-Merge: C-23')
        n24 = log_main.count('Campaign-Merge: C-24')
        self.ok('kill -9 of daemon and merge job mid-merge: the merge is redone once, never twice (C-23)',
                killed.get('k3') and cs['C-23']['state'] == 'merged' and n23 == 1, (cs['C-23'], n23))
        self.ok('kill -9 of the daemon mid-merge: the surviving merge job\'s result is taken once (C-24)',
                killed.get('k4') and cs['C-24']['state'] == 'merged' and n24 == 1, (cs['C-24'], n24))
        p = self.camp('finish', timeout=120)
        self.ok('finish: primary checkout back on main with orch merged, main\'s checkout removed',
                p.returncode == 0 and current_branch(self.primary) == 'main' and not os.path.isdir(os.path.join(self.wt, 'main'))
                and 'orchestrator note' in open(os.path.join(self.primary, 'PROGRESS.md')).read(), p.stdout + p.stderr)
        # API-key variables never reach a session (they were planted in campaign.py's own environment)
        fl = self.fakelog()
        leaked = sorted(set(k for x in fl for k in x.get('apikeys', []) + x.get('claude_vars', [])))
        self.ok('no session saw the API-key or CLAUDE_CODE_ variables planted in campaign.py\'s environment (%d sessions)' % len(fl),
                fl and not leaked, leaked)

    def cleanup(self):
        try:
            os.remove(self.marker)
        except OSError:
            pass
        for pidf in glob.glob(os.path.join(self.wt, 'state', 'jobs', '*', 'pid')):
            try:
                os.killpg(int(open(pidf).read()), signal.SIGKILL)
            except (OSError, ValueError):
                pass
        try:
            os.kill(int(open(os.path.join(self.wt, 'state', 'daemon.pid')).read()), signal.SIGKILL)
        except (OSError, ValueError):
            pass
        if not self.keep:
            shutil.rmtree(self.base, ignore_errors=True)


def cmd_selftest(a):
    t = SelfTest(a.keep)
    try:
        t.run()
    except Exception as e:  # report, don't hide
        import traceback
        traceback.print_exc()
        t.ok('selftest ran to the end without an exception', False, '%s: %s' % (type(e).__name__, e))
    finally:
        t.cleanup()
    n = sum(1 for _, ok in t.results if ok)
    print('RESULT selftest %s %d/%d%s' % ('PASS' if n == len(t.results) and t.results else 'FAIL', n, len(t.results),
                                         (' (kept %s)' % t.base) if a.keep else ''))
    return 0 if n == len(t.results) and t.results else 1


# =============================================================== main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('start')
    s.add_argument('--cards')
    s.add_argument('--no-tmux', action='store_true')
    for n in ('stop', 'finish', 'status', 'daemon', 'land'):
        sub.add_parser(n)
    s = sub.add_parser('wait')
    s.add_argument('--max', help=argparse.SUPPRESS)
    for n in ('retry', 'park'):
        s = sub.add_parser(n)
        s.add_argument('card')
        s.add_argument('--note')
    s = sub.add_parser('reopen')
    s.add_argument('card')
    s.add_argument('--for', dest='for_', required=True)
    s.add_argument('--note')
    s = sub.add_parser('session')
    s.add_argument('role')
    s = sub.add_parser('resume-vendor')
    s.add_argument('vendor')
    s = sub.add_parser('selftest')
    s.add_argument('--keep', action='store_true')
    s = sub.add_parser('_job')
    s.add_argument('dir')
    s = sub.add_parser('_merge')
    s.add_argument('dir')
    a = ap.parse_args()
    if a.cmd == '_job':
        return cmd_job(a.dir)
    if a.cmd == '_merge':
        return cmd_merge(a.dir)
    fn = {'start': cmd_start, 'stop': cmd_stop, 'finish': cmd_finish, 'status': cmd_status, 'daemon': cmd_daemon,
          'land': cmd_land, 'wait': cmd_wait, 'retry': cmd_retry, 'park': cmd_park, 'reopen': cmd_reopen,
          'session': cmd_session, 'selftest': cmd_selftest, 'resume-vendor': cmd_resume_vendor}[a.cmd]
    try:
        return fn(a)
    except (CampaignError, GitError, cardlib.CardFormatError) as e:
        print('campaign.py %s: %s' % (a.cmd, e))
        return 2


if __name__ == '__main__':
    sys.exit(main())
