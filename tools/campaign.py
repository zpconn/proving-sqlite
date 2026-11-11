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
import stat
import shlex
import subprocess
import sys
import threading
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
MAX_BUILDER_ROUNDS = 6           # checkpoint 1, D4: May change lines list reports b1-b6; round 7 goes to triage for Zach
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
    """sessions.toml, parsed, with '_sha256' the hash of the bytes it was parsed from (each session-start entry in
    the journal records it)."""
    path = os.path.join(main_dir, 'tools', 'sessions.toml')
    with open(path, 'rb') as f:
        raw = f.read()
    sess = tomllib.loads(raw.decode('utf-8'))
    sess['_sha256'] = hashlib.sha256(raw).hexdigest()
    return sess


# The command lines campaign.py accepts (checkpoint 0 follow-up 5). sessions.toml must hold exactly these: a
# session's command differs from this only where campaign.py fills a placeholder ({model}, {effort}, {session},
# {dir}, {home}, {wtroot}, {repo}, and {config}, a reviewer's own Claude config directory). A CLI flag change is a
# change here, to tools/, not to sessions.toml alone. evidence/bringup/10-cli.md and 13-checkpoint0.md justify each.
_CODEX_SAFE = ['--ignore-user-config', '--strict-config',
               '-c', 'sandbox_mode="workspace-write"', '-c', 'approval_policy="never"',
               '-c', 'sandbox_workspace_write.exclude_slash_tmp=true',
               '-c', 'web_search="disabled"',
               '-c', 'background_terminal_max_timeout=3600000', '-c', 'features.code_mode.default_exec_yield_time_ms=3600000',
               '--disable', 'apps', '--disable', 'plugins', '--disable', 'remote_plugin', '--disable', 'tool_suggest',
               '--disable', 'multi_agent', '--disable', 'multi_agent_v2', '--disable', 'image_generation',
               '--disable', 'browser_use', '--disable', 'browser_use_external', '--disable', 'computer_use',
               '--disable', 'in_app_browser', '--disable', 'goals', '--disable', 'hooks', '--disable', 'memories',
               '-m', '{model}', '-c', 'model_reasoning_effort="{effort}"', '-']
# On WSL /etc/resolv.conf is a link to this file; with /mnt hidden, DNS needs it back (read-only). prepare_mounts
# drops the bind where the file does not exist.
WSL_RESOLV = '/mnt/wsl/resolv.conf'
# Checkpoint 1, Q2 and Q4: every session starts inside bubblewrap with all of $HOME and /mnt hidden (on WSL,
# /mnt/wslg/distro is a second view of /, home included), and $HOME read-only; only what the CLI needs is bound back.
_BWRAP_BASE = ['bwrap', '--ro-bind', '/', '/', '--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp',
               '--tmpfs', '/run/user', '--unsetenv', 'DBUS_SESSION_BUS_ADDRESS', '--unsetenv', 'XDG_RUNTIME_DIR',
               '--tmpfs', '/mnt', '--ro-bind', WSL_RESOLV, WSL_RESOLV, '--remount-ro', '/mnt', '--tmpfs', '{home}']
_BWRAP_TAIL = ['--tmpfs', '{wtroot}', '--tmpfs', '{repo}', '--ro-bind', '{repo}/.git', '{repo}/.git']
# claude: its install, read-only; its own config directory and the worktree, writable
_BWRAP = (_BWRAP_BASE +
          ['--ro-bind', '{home}/.local/share/claude', '{home}/.local/share/claude',
           '--ro-bind', '{home}/.local/bin/claude', '{home}/.local/bin/claude',
           # kept from checkpoint 0 (Q4), though the $HOME tmpfs covers them; ~/.config/gh, ~/.aws and ~/.docker no longer
           # get their own (~/.aws may be a link into /mnt/c, which would put a mount point under the hidden /mnt)
           '--tmpfs', '{home}/.codex', '--tmpfs', '{home}/.claude', '--ro-bind', '/dev/null', '{home}/.claude.json'] +
          _BWRAP_TAIL +
          ['--bind', '{config}', '{config}', '--setenv', 'CLAUDE_CONFIG_DIR', '{config}',
           '--bind', '{dir}', '{dir}', '--remount-ro', '{home}', '--chdir', '{dir}'])
# codex: node and codex (under nvm), read-only; ~/.codex, writable (its login, which codex refreshes in place under a
# lock, and its session logs, which resume reads), less what it would load from there: the bundled skills, the
# approval rules (Zach's interactive allow-list: `git push`, `gh repo create --push`, ...) and memories, each behind an
# empty read-only tmpfs; and the worktree, writable. codex's own workspace-write sandbox runs inside this one.
CODEX_HIDDEN = ('{home}/.codex/skills', '{home}/.codex/rules', '{home}/.codex/memories')
# What codex would load from the ~/.codex it needs, or from /etc/codex, and that no flag or mount turns off: none exists
# today, and campaign.py refuses to start a codex session if one appears (checkpoint 1, Q2)
CODEX_REFUSE = ('{home}/.codex/AGENTS.md', '{home}/.codex/AGENTS.override.md', '{home}/.codex/hooks.json',
                '{home}/.codex/agents', '/etc/codex')
_BWRAP_CODEX = (_BWRAP_BASE +
                ['--ro-bind', '{home}/.nvm', '{home}/.nvm', '--bind', '{home}/.codex', '{home}/.codex'] +
                [x for d in CODEX_HIDDEN for x in ('--tmpfs', d, '--remount-ro', d)] + _BWRAP_TAIL +
                ['--bind', '{dir}', '{dir}', '--remount-ro', '{home}', '--chdir', '{dir}'])
# checkpoint 1, Q2: no skills or commands (the account's synced skills land in the config directory at startup), and
# no MCP servers but --mcp-config's, which is never given (the account's claude.ai connectors included)
_CLAUDE_TAIL = ['--disable-slash-commands', '--strict-mcp-config', '--model', '{model}', '--effort', '{effort}', '--permission-mode', 'auto',
                '--output-format', 'stream-json', '--verbose', '--include-partial-messages']
SESSION_COMMANDS = {
    'codex': {'start': _BWRAP_CODEX + ['codex', 'exec', '--json'] + _CODEX_SAFE,
              'resume': _BWRAP_CODEX + ['codex', 'exec', 'resume', '{session}', '--json'] + _CODEX_SAFE,
              'login_check': ['codex', 'login', 'status']},
    'claude': {'start': _BWRAP + ['claude', '-p'] + _CLAUDE_TAIL,
               'resume': _BWRAP + ['claude', '-p', '--resume', '{session}'] + _CLAUDE_TAIL,
               'login_check': ['claude', 'auth', 'status']},
}
# bwrap cannot mount over these when they are absent; with nothing there, there is nothing to hide
OPTIONAL_HIDES = ('{home}/.config/gh', '{home}/.aws', '{home}/.docker')


def template_problems(vendor, key, argv):
    """[] if sessions.toml's `key` command for `vendor` is SESSION_COMMANDS' exactly, else what differs."""
    want = (SESSION_COMMANDS.get(vendor) or {}).get(key)
    if want is None:
        return ['campaign.py has no %s command for %s' % (key, vendor)]
    if argv == want:
        return []
    i = next((k for k in range(min(len(argv), len(want))) if argv[k] != want[k]), min(len(argv), len(want)))
    got_s = argv[i] if i < len(argv) else '(end)'
    want_s = want[i] if i < len(want) else '(end)'
    return ['sessions.toml\'s %s %s command differs from campaign.py\'s at argument %d: %r where campaign.py has %r; '
            'only placeholders may vary, and campaign.py fills them' % (vendor, key, i, got_s, want_s)]


# auditor recheck item 2: the values campaign.py puts in for {model} and {effort}. One argv word of letters, digits,
# '.', '_' and '-', not starting with '-' (so never an option), and nothing a shell or a codex -c value would read.
PLACEHOLDER_VALUE_RX = re.compile(r'[A-Za-z0-9._][A-Za-z0-9._-]*')


def role_value_problems(where, model, effort):
    """[] if model and effort may fill {model} and {effort}, else why not."""
    return ['%s %s %r is not a plain name (^[A-Za-z0-9._-]+$, no leading dash)' % (where, k, v)
            for k, v in (('model', model), ('effort', effort))
            if not (isinstance(v, str) and PLACEHOLDER_VALUE_RX.fullmatch(v))]


def sessions_problems(sess):
    """Every command template in sessions.toml that is not SESSION_COMMANDS', and every role's model or effort
    that is not a plain name (cmd_start refuses to start)."""
    probs = []
    for vendor, cmds in SESSION_COMMANDS.items():
        vc = (sess.get('vendors') or {}).get(vendor) or {}
        for key in cmds:
            probs += template_problems(vendor, key, vc.get(key))
    for role, tiers in sorted((sess.get('roles') or {}).items()):
        for tier, rc in sorted((tiers or {}).items()):
            rc = rc if isinstance(rc, dict) else {}
            probs += role_value_problems('sessions.toml roles.%s.%s' % (role, tier), rc.get('model'), rc.get('effort'))
    return probs


def bounded_worktree_read(w, rel, timeout=10):
    """Selftest (auditor recheck item 3): read_worktree_file(w, rel) in a thread, as (kind, detail), kind 'refused'
    (WorktreeFileError), 'read', 'error', 'missing' (no such helper) or 'hung'. A read that blocks (a plain open() of
    a FIFO waits for a writer) is reported as 'hung' after `timeout` seconds, and unblocked by opening the FIFO for
    writing, so the check fails instead of hanging the selftest."""
    g = globals()
    helper, err = g.get('read_worktree_file'), g.get('WorktreeFileError')
    if helper is None:
        return ('missing', 'campaign.py has no read_worktree_file')
    box = []

    def go():
        try:
            helper(w, rel)
            box.append(('read', rel))
        except Exception as ex:
            box.append(('refused' if err and isinstance(ex, err) else 'error', '%s: %s' % (type(ex).__name__, ex)))
    th = threading.Thread(target=go, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        try:
            os.close(os.open(os.path.join(w, rel), os.O_WRONLY | os.O_NONBLOCK))
        except OSError:
            pass
        th.join(2)
        return ('hung', 'reading %s did not return within %d s' % (rel, timeout))
    return box[0]


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
    probs = role_value_problems('sessions.toml roles.%s.%s' % (role, tier), rc.get('model'), rc.get('effort'))
    if probs:
        raise SessionRefused('; '.join(probs))
    vcfg = dict(sess['vendors'][vendor])
    vcfg['_sessions_sha256'] = sess.get('_sha256')
    return vendor, rc['model'], rc['effort'], vcfg


CODEX_FORBIDDEN = {'--dangerously-bypass-approvals-and-sandbox', '--yolo', '--full-auto', '--approve-for-me', '-s',
                   '--sandbox', '-a', '--ask-for-approval', '--add-dir', '--oss', '-p', '--profile'}
CLAUDE_FORBIDDEN = {'--dangerously-skip-permissions', '--allow-dangerously-skip-permissions', '--bare',
                    '--add-dir', '--permission-prompt-tool', '--settings', '--mcp-config', '--plugin-dir'}


BWRAP_ARITY = {'--ro-bind': 2, '--bind': 2, '--dev-bind': 2, '--ro-bind-try': 2, '--bind-try': 2, '--dev-bind-try': 2,
               '--symlink': 2, '--setenv': 2, '--unsetenv': 1, '--tmpfs': 1, '--dev': 1, '--proc': 1, '--chdir': 1,
               '--dir': 1, '--remount-ro': 1, '--perms': 1, '--size': 1, '--file': 2, '--bind-data': 2,
               '--ro-bind-data': 2, '--chmod': 2, '--uid': 1, '--gid': 1, '--hostname': 1, '--args': 1, '--userns': 1,
               '--userns2': 1, '--pidns': 1, '--seccomp': 1, '--add-seccomp-fd': 1, '--exec-label': 1, '--file-label': 1,
               '--lock-file': 1, '--sync-fd': 1, '--block-fd': 1, '--userns-block-fd': 1, '--info-fd': 1,
               '--json-status-fd': 1, '--cap-add': 1, '--cap-drop': 1, '--argv0': 1, '--overlay-src': 1,
               '--overlay': 3, '--tmp-overlay': 1, '--ro-overlay': 1}


def split_bwrap(argv):
    """(bwrap's own arguments, the command it runs), by each option's arity: the command is the first word that is
    not an option or an option's argument (a path such as ~/.local/share/claude is never taken for the CLI)."""
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == '--':
            return argv[1:i], argv[i + 1:]
        if not a.startswith('--'):
            return argv[1:i], argv[i:]
        i += 1 + BWRAP_ARITY.get(a, 0)
    return argv[1:], []


def command_problems(vendor, argv, wt, p):
    """Why a filled session command line is refused (checkpoint 0, decisions C5 and C6; follow-ups 6 and 8;
    checkpoint 1, Q2 and Q4), or []. A second line behind template_problems, on what will actually run.
    Both vendors: bubblewrap first, with / read-only; hidden behind a tmpfs: /tmp, /run/user (desktop services), /mnt,
    all of $HOME, the worktree root (../<repo>-wt: state/ and every other worktree) and the primary checkout (its .git
    read-only); $HOME remounted read-only after the binds into it; DBUS_SESSION_BUS_ADDRESS and XDG_RUNTIME_DIR unset;
    the worktree the last mount at its path, writable. Nothing else is bound back but, for claude: its install
    (~/.local/share/claude, ~/.local/bin/claude) read-only, /dev/null over ~/.claude.json, ~/.codex, ~/.claude,
    ~/.config/gh, ~/.aws and ~/.docker behind their own tmpfs, and CLAUDE_CONFIG_DIR, the session's own directory under
    state/claude-config/, writable; for codex: ~/.nvm (node and codex) read-only, ~/.codex writable, with its skills,
    rules and memories behind an empty read-only tmpfs.
    Then, codex: `codex exec` with sandbox_mode="workspace-write" and approval_policy="never", each set once,
    sandbox_workspace_write.exclude_slash_tmp=true (no shared /tmp; the session's TMPDIR is in its worktree) and no
    other sandbox_workspace_write key, and none of the flags that loosen either; claude: `claude -p` in auto
    permission mode."""
    home = os.path.expanduser('~')
    probs = []
    if vendor not in ('codex', 'claude'):
        return ['unknown vendor %s' % vendor]
    if not argv or os.path.basename(argv[0]) != 'bwrap':
        return ['a %s session must start with bwrap' % vendor]
    bw, cl = split_bwrap(argv)
    if not cl or os.path.basename(cl[0]) != vendor:
        return ['no %s command after bwrap (found %s)' % (vendor, cl[:1])]
    mounts, setenv, unsetenv, i = [], [], [], 0
    while i < len(bw):
        a = bw[i]
        if a in ('--ro-bind', '--bind', '--dev-bind', '--ro-bind-try', '--bind-try', '--dev-bind-try', '--symlink'):
            mounts.append((a, bw[i + 1], bw[i + 2]))
            i += 3
        elif a == '--setenv':
            setenv.append((bw[i + 1], bw[i + 2]))
            i += 3
        elif a == '--unsetenv':
            unsetenv.append(bw[i + 1])
            i += 2
        elif a in ('--tmpfs', '--dev', '--proc', '--chdir', '--dir', '--remount-ro', '--perms', '--size'):
            mounts.append((a, bw[i + 1], bw[i + 1]))
            i += 2
        else:
            mounts.append((a, None, None))
            i += 1
    real = lambda x: os.path.realpath(x)  # noqa: E731
    if not mounts or mounts[0] != ('--ro-bind', '/', '/'):
        probs.append('bwrap must begin with --ro-bind / /')
    cfgdir = None
    if vendor == 'claude':
        cfg = [v for k, v in setenv if k == 'CLAUDE_CONFIG_DIR']
        if len(cfg) != 1 or [k for k, _ in setenv] != ['CLAUDE_CONFIG_DIR']:
            probs.append('bwrap must set CLAUDE_CONFIG_DIR, once, and no other variable (found %s)' % setenv)
        cfgdir = real(cfg[0]) if len(cfg) == 1 else None
        if cfgdir and os.path.dirname(cfgdir) != real(os.path.join(p.state, 'claude-config')):
            probs.append('CLAUDE_CONFIG_DIR %s is not a session directory under state/claude-config/' % cfg[0])
    elif setenv:
        probs.append('bwrap sets no variable for codex (found %s)' % setenv)
    for var in ('DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR'):
        if var not in unsetenv:
            probs.append('bwrap must unset %s' % var)
    codex_home = real(os.path.join(home, '.codex'))
    codex_hidden = [real(x.replace('{home}', home)) for x in CODEX_HIDDEN]
    if vendor == 'claude':
        allowed_rw = {real(wt)} | ({cfgdir} if cfgdir else set())
        allowed_ro = {real(os.path.join(home, '.local', 'share', 'claude')), real(os.path.join(home, '.local', 'bin', 'claude'))}
        allowed_remount = {real(home), '/mnt'}
    else:
        allowed_rw = {real(wt), codex_home}
        allowed_ro = {real(os.path.join(home, '.nvm'))}
        allowed_remount = {real(home), '/mnt'} | set(codex_hidden)
    allowed_ro.add(real(os.path.join(p.primary, '.git')))
    allowed_ro.add(real(WSL_RESOLV))
    claude_json = real(os.path.join(home, '.claude.json'))
    for kind, src, dst in mounts:
        if kind in ('--bind', '--dev-bind', '--bind-try', '--dev-bind-try') and (real(dst) not in allowed_rw or real(src) != real(dst)):
            probs.append('bwrap binds %s writable; only %s may be' % (dst, ', '.join(sorted(allowed_rw))))
        if kind in ('--ro-bind', '--ro-bind-try') and (src, dst) != ('/', '/') and \
                not (real(src) == real(dst) and real(dst) in allowed_ro) and \
                not (vendor == 'claude' and (src, real(dst)) == ('/dev/null', claude_json)):
            probs.append('bwrap read-only binds %s; only / and %s are bound back read-only' % (dst, ', '.join(sorted(allowed_ro))))
        if kind == '--remount-ro' and real(dst) not in allowed_remount:
            probs.append('bwrap remounts %s read-only; only %s may be' % (dst, ', '.join(sorted(allowed_remount))))
        if kind in ('--symlink', '--perms', '--size', '--dir') or kind not in (
                '--ro-bind', '--bind', '--dev-bind', '--ro-bind-try', '--bind-try', '--dev-bind-try', '--tmpfs', '--dev',
                '--proc', '--chdir', '--remount-ro', '--die-with-parent', '--new-session', '--unshare-pid', '--unshare-ipc'):
            probs.append('bwrap option %s not allowed' % kind)
    order = [(k, real(d) if d else d) for k, s_, d in mounts]

    def last_mount_at(path):
        """The last mount whose destination is path or one of its parents, as bwrap applies them in order
        (a --remount-ro changes flags, not what is mounted, so it is skipped)."""
        rp = real(path)
        hit = None
        for k, d in order:
            if d and k not in ('--chdir', '--remount-ro') and (rp == d or rp.startswith(d.rstrip('/') + '/')):
                hit = (k, d)
        return hit

    def remounted_ro_after(path):
        """--remount-ro path comes after every mount at or under path."""
        rp = real(path)
        last_under = max([n for n, (k, d) in enumerate(order) if d and k not in ('--chdir', '--remount-ro')
                          and (d == rp or d.startswith(rp.rstrip('/') + '/'))] or [-1])
        return any(k == '--remount-ro' and d == rp and n > last_under for n, (k, d) in enumerate(order))
    must_hide = ['/tmp', '/run/user/%d' % os.getuid(), '/mnt', home, p.wt, p.primary, os.path.join(p.wt, 'state'),
                 os.path.join(p.wt, 'main'), os.path.join(p.wt, 'merge'), os.path.join(home, '.claude'),
                 os.path.join(home, '.ssh'), os.path.join(home, '.gitconfig'), os.path.join(home, '.bashrc')]
    if vendor == 'claude':
        must_hide += [os.path.join(home, '.codex')]
        must_hide += [x for x in (os.path.join(home, '.config', 'gh'), os.path.join(home, '.aws'), os.path.join(home, '.docker'))
                      if os.path.exists(x)]
    else:
        must_hide += codex_hidden
    for hidden in must_hide:
        if real(hidden) in (real(wt),):
            continue
        hit = last_mount_at(hidden)
        if not hit or hit[0] != '--tmpfs':
            probs.append('bwrap must hide %s behind a --tmpfs (last mount there: %s)' % (hidden, hit))
    for own in [home, '/mnt'] + (codex_hidden if vendor == 'codex' else []):
        if last_mount_at(own) != ('--tmpfs', real(own)):
            probs.append('bwrap must hide %s behind a tmpfs of its own (found %s)' % (own, last_mount_at(own)))
    for ro in ['/mnt', home] + (codex_hidden if vendor == 'codex' else []):
        if not remounted_ro_after(ro):
            probs.append('bwrap must remount %s read-only after every mount into it' % ro)
    if vendor == 'claude':
        for own in (os.path.join(home, '.claude'), os.path.join(home, '.codex')):
            if last_mount_at(own) != ('--tmpfs', real(own)):
                probs.append('bwrap must keep %s behind its own --tmpfs (checkpoint 0; Q4 keeps it), found %s' % (own, last_mount_at(own)))
    if vendor == 'claude' and os.path.exists(claude_json) and last_mount_at(claude_json) != ('--ro-bind', claude_json):
        probs.append('bwrap must cover ~/.claude.json with /dev/null (last mount there: %s)' % (last_mount_at(claude_json),))
    hit = last_mount_at(wt)
    if not hit or hit != ('--bind', real(wt)):
        probs.append('the worktree %s must be the last mount at its path, writable (found %s)' % (wt, hit))
    if cfgdir and last_mount_at(cfgdir) != ('--bind', cfgdir):
        probs.append('CLAUDE_CONFIG_DIR %s must be the last mount at its path, writable (found %s)' % (cfgdir, last_mount_at(cfgdir)))
    if vendor == 'codex':
        there = [x.replace('{home}', home) for x in CODEX_REFUSE if os.path.lexists(x.replace('{home}', home))]
        if there:
            probs.append('codex would load %s (global instructions, hooks, agents or system config); remove it, or hide it '
                         'in campaign.py\'s bwrap, before starting a builder' % ', '.join(there))
        if len(cl) < 2 or cl[1] != 'exec':
            probs.append('a codex session must run `codex exec` inside bwrap')
        sets = [cl[i + 1] for i, a in enumerate(cl[:-1]) if a in ('-c', '--config')]
        sb = [x for x in sets if x.split('=', 1)[0].strip() in ('sandbox_mode',)]
        ap = [x for x in sets if x.split('=', 1)[0].strip() in ('approval_policy', 'ask_for_approval')]
        if sb != ['sandbox_mode="workspace-write"']:
            probs.append('codex must set sandbox_mode="workspace-write" exactly once (found %s)' % sb)
        if ap != ['approval_policy="never"']:
            probs.append('codex must set approval_policy="never" exactly once (found %s)' % ap)
        ws = [x for x in sets if x.split('=', 1)[0].strip().startswith('sandbox_workspace_write')]
        if ws != ['sandbox_workspace_write.exclude_slash_tmp=true']:
            probs.append('codex must set sandbox_workspace_write.exclude_slash_tmp=true once and no other '
                         'sandbox_workspace_write key (found %s)' % ws)
        loose = [x for x in sets if x.split('=', 1)[0].strip().startswith(('sandbox_permissions', 'permissions',
                                                                          'default_permissions', 'shell_environment_policy'))]
        if loose:
            probs.append('codex settings that loosen the sandbox: %s' % loose)
        bad = [a for a in cl if a in CODEX_FORBIDDEN or a.startswith('--sandbox=') or a.startswith('--profile=')]
        if bad:
            probs.append('codex flags not allowed: %s' % bad)
        return probs
    if len(cl) < 2 or cl[1] != '-p':
        probs.append('claude must run as `claude -p`')
    if 'bypassPermissions' in cl or any(a in CLAUDE_FORBIDDEN for a in cl):
        probs.append('claude flags not allowed: %s' % [a for a in cl if a in CLAUDE_FORBIDDEN or a == 'bypassPermissions'])
    if 'auto' not in [cl[i + 1] for i, a in enumerate(cl[:-1]) if a == '--permission-mode']:
        probs.append('claude must run with --permission-mode auto')
    for flag in ('--disable-slash-commands', '--strict-mcp-config'):
        if flag not in cl:
            probs.append('claude must run with %s (checkpoint 1, Q2: no skills, no MCP servers)' % flag)
    return probs


def fill(argv, **kw):
    out = []
    for a in argv:
        for k, v in kw.items():
            a = a.replace('{%s}' % k, str(v))
        out.append(a)
    return out


def prepare_mounts(argv, home):
    """Make a filled bwrap command line mountable: each --tmpfs destination by its real path (bwrap resolves an
    absolute symlink inside its own new root, where its target may not be mounted yet), created if missing; and
    drop a hide of an optional config directory, or the /dev/null over ~/.claude.json, when nothing is there."""
    if not argv or os.path.basename(argv[0]) != 'bwrap':
        return argv
    optional = {os.path.realpath(x.replace('{home}', home)) for x in OPTIONAL_HIDES}
    out, i = [], 0
    ci = len(argv) - len(split_bwrap(argv)[1])
    while i < len(argv):
        a = argv[i]
        if i < ci and a == '--tmpfs' and i + 1 < len(argv):
            d = argv[i + 1]
            r = os.path.realpath(d)
            if not os.path.exists(r):
                if r in optional or os.path.islink(d):
                    i += 2
                    continue
                os.makedirs(r, exist_ok=True)   # bwrap cannot create a mount point under a read-only /
            out += [a, r]
            i += 2
            continue
        if i < ci and a == '--ro-bind' and i + 2 < len(argv) and argv[i + 1] in ('/dev/null', WSL_RESOLV):
            if not os.path.exists(argv[i + 2]):
                i += 3
                continue
        out.append(a)
        i += 1
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
        json.dump({'argv': argv, 'cwd': cwd, 'env': job.get('env') or {}}, f, indent=1)
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
        env = dict(os.environ, **(c.get('env') or {}))
        proc = subprocess.Popen(['nice', '-n', '10'] + c['argv'], cwd=c['cwd'], stdin=inp, stdout=out, stderr=err, env=env)
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
    if template_problems(vendor, 'login_check', cmd):
        return False, '; '.join(template_problems(vendor, 'login_check', cmd))
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


def first_word(text):
    """The verdict word of a report or review: its first non-blank line's first word, markup removed."""
    if text is None:
        return None
    if isinstance(text, bytes):
        text = text.decode('utf-8', 'replace')
    for line in text.split('\n'):
        s = re.sub(r'[*#`_]', '', line).strip()
        if s:
            return s.split()[0].rstrip(':.')
    return None


class WorktreeFileError(Exception):
    """A file campaign.py reads or writes in a session's worktree is not what it must be (checkpoint 0 follow-up 7)."""


def _dir_fd(wt, parts, create=False):
    """An fd for wt/<parts...>, each part opened with O_NOFOLLOW: None if a part is missing (and not created);
    WorktreeFileError if a part is a symlink or not a directory."""
    fd = os.open(wt, os.O_RDONLY | os.O_DIRECTORY)
    for part in parts:
        if create:
            try:
                os.mkdir(part, 0o755, dir_fd=fd)
            except FileExistsError:
                pass
        try:
            nfd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        except FileNotFoundError:
            os.close(fd)
            return None
        except OSError as e:
            os.close(fd)
            raise WorktreeFileError('%s in the worktree is not a real directory (%s)' % (part, e.strerror))
        os.close(fd)
        fd = nfd
    return fd


def read_worktree_file(wt, rel, limit=4 << 20):
    """The bytes of wt/rel, or None if it does not exist. Raises WorktreeFileError unless every directory on the way
    is a real one and the file is a regular file: lstat first, then open with O_NOFOLLOW|O_NONBLOCK (a FIFO would
    otherwise block the daemon) and check again on the open file."""
    parts = rel.split('/')
    dfd = _dir_fd(wt, parts[:-1])
    if dfd is None:
        return None
    try:
        try:
            st_ = os.stat(parts[-1], dir_fd=dfd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(st_.st_mode):
            raise WorktreeFileError('%s is not a regular file (%s)' % (rel, filetype(st_.st_mode)))
        try:
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
        except OSError as e:
            raise WorktreeFileError('%s cannot be opened as a regular file (%s)' % (rel, e.strerror))
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise WorktreeFileError('%s is not a regular file' % rel)
            chunks, n = [], 0
            while n <= limit:
                b = os.read(fd, 1 << 16)
                if not b:
                    break
                chunks.append(b)
                n += len(b)
            if n > limit:
                raise WorktreeFileError('%s is larger than %d bytes' % (rel, limit))
            return b''.join(chunks)
        finally:
            os.close(fd)
    finally:
        os.close(dfd)


def write_worktree_usage(wt, text):
    """Write wt/.campaign/usage, only if .campaign is a real directory in the worktree and usage, if present, is a
    regular file with one link; opened with O_NOFOLLOW (checkpoint 0 follow-up 7). Raises WorktreeFileError."""
    dfd = _dir_fd(wt, ['.campaign'], create=True)
    try:
        try:
            st_ = os.stat('usage', dir_fd=dfd, follow_symlinks=False)
            if not stat.S_ISREG(st_.st_mode) or st_.st_nlink != 1:
                raise WorktreeFileError('.campaign/usage is not a regular file with one link (%s, %d links)' % (
                    filetype(st_.st_mode), st_.st_nlink))
        except FileNotFoundError:
            pass
        try:
            fd = os.open('usage', os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o644, dir_fd=dfd)
        except OSError as e:
            raise WorktreeFileError('.campaign/usage cannot be opened as a regular file (%s)' % e.strerror)
        try:
            fs = os.fstat(fd)
            if not stat.S_ISREG(fs.st_mode) or fs.st_nlink != 1:
                raise WorktreeFileError('.campaign/usage is not a regular file with one link')
            os.ftruncate(fd, 0)
            os.write(fd, text.encode())
        finally:
            os.close(fd)
    finally:
        os.close(dfd)


def filetype(mode):
    for test, name in ((stat.S_ISLNK, 'symlink'), (stat.S_ISFIFO, 'FIFO'), (stat.S_ISDIR, 'directory'),
                       (stat.S_ISSOCK, 'socket'), (stat.S_ISCHR, 'character device'), (stat.S_ISBLK, 'block device')):
        if test(mode):
            return name
    return 'regular file' if stat.S_ISREG(mode) else 'unknown type'


# A reviewer's Claude config directory (checkpoint 0 follow-up 6): fresh for each session chain, under state/ (hidden
# from every session), holding only a copy of the login. Nothing a reviewer writes there reaches another session.
CLAUDE_JSON_KEYS = ('oauthAccount', 'userID', 'hasCompletedOnboarding')
CRED_KEYS = {'accessToken', 'refreshToken', 'expiresAt', 'scopes', 'subscriptionType', 'subscriptionTypeSource',
             'rateLimitTier', 'refreshTokenExpiresAt'}


def _write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def seed_claude_config(cfg):
    """Create cfg (mode 700) and copy in the login: ~/.claude/.credentials.json, and from ~/.claude.json only the
    account keys a signed-in session needs. A resumed session keeps its own .claude.json and transcripts."""
    home = os.path.expanduser('~')
    os.makedirs(os.path.dirname(cfg), exist_ok=True)
    os.makedirs(cfg, mode=0o700, exist_ok=True)
    os.chmod(cfg, 0o700)
    src = os.path.join(home, '.claude', '.credentials.json')
    if os.path.exists(src):
        _write_private(os.path.join(cfg, '.credentials.json'), open(src, 'rb').read())
    cj = os.path.join(cfg, '.claude.json')
    if not os.path.lexists(cj):
        try:
            full = json.load(open(os.path.join(home, '.claude.json')))
        except (OSError, ValueError):
            full = {}
        _write_private(cj, json.dumps({k: full[k] for k in CLAUDE_JSON_KEYS if k in full}).encode())


def release_claude_config(job):
    """After a reviewer session: if it refreshed the login (same account, a later expiry, only known keys), copy the
    new tokens back to ~/.claude/.credentials.json, since a refresh can retire the old ones; then remove the
    session's copy. Returns what it did."""
    cfg = job.get('config')
    if not cfg:
        return None
    mine = os.path.join(cfg, '.credentials.json')
    main = os.path.join(os.path.expanduser('~'), '.claude', '.credentials.json')
    did = 'removed'
    try:
        st_ = os.lstat(mine)
    except FileNotFoundError:
        return 'none'
    try:
        if stat.S_ISREG(st_.st_mode) and st_.st_size < 65536:
            new = json.loads(open(mine, 'rb').read()).get('claudeAiOauth')
            old = json.load(open(main)).get('claudeAiOauth')
            if (isinstance(new, dict) and isinstance(old, dict) and set(new) <= CRED_KEYS and set(new) == set(old)
                    and all(isinstance(new[k], str) for k in ('accessToken', 'refreshToken'))
                    and isinstance(new.get('expiresAt'), (int, float)) and new['expiresAt'] > old.get('expiresAt', 0)
                    and new.get('subscriptionType') == old.get('subscriptionType')
                    and (new['accessToken'], new['refreshToken']) != (old['accessToken'], old['refreshToken'])):
                tmp = main + '.campaign-tmp'
                _write_private(tmp, json.dumps({'claudeAiOauth': new}).encode())
                os.replace(tmp, main)
                did = 'refreshed login copied back'
    except (OSError, ValueError, AttributeError):
        pass
    try:
        os.remove(mine)
    except OSError:
        pass
    return did


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
        'Work only in this directory (%s). /tmp is not writable: put scratch files in $TMPDIR, which is tmp/ here '
        '(git ignores it). Do not commit, branch or merge: campaign.py commits what you '
        'leave when you exit, and only the paths on your card\'s May change line.' % wt,
        LONG_RUN_CODEX + ' proofs/HOWTO.md records how proofs are built here: run them with tools/prove.py, never make '
        'in a card directory.',
    ]
    return '\n\n'.join(lines) + '\n'


def prompt_reviewer(cid, rnd, commit, builder_report, rereview=None, repros=None):
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
        'Run proofs with tools/prove.py (proofs/HOWTO.md), never make in a card directory: make would run the '
        'builder\'s Makefile.',
    ]
    if repros:
        lines.append('campaign.py built and ran the round\'s repro files with its fixed command, against unmodified '
                     'upstream, under ASan and UBSan, in a sandbox with no network and no $HOME. Their output is in '
                     '.campaign/repro/ in your worktree: %s. Judge from that output; do not build or run them yourself.'
                     % '; '.join('%s (%s)' % (k, v) for k, v in sorted(repros.items())))
    return '\n\n'.join(lines) + '\n'


# Checkpoint 1, fix 2: builder-written repro files are built and run by campaign.py, never by a session, with one
# fixed command, against main's unmodified upstream/sqlite3.c, under ASan and UBSan, in a sandbox with no network
# (--unshare-all), no $HOME, /mnt hidden, an empty environment, and nothing writable but its own output directory.
REPRO_RX = re.compile(r'^tests/repro/F-draft-(C-[0-9]{2})-([1-3])\.c$')
REPRO_CC = ['cc', '-std=gnu11', '-g', '-O1', '-fno-omit-frame-pointer', '-fsanitize=address,undefined',
            '-fno-sanitize-recover=undefined', '-I', '/tmp/repro/upstream', '-o', '/tmp/repro/out/repro',
            '/tmp/repro/src/repro.c', '-lm', '-lpthread', '-ldl']
REPRO_RUN = ['/tmp/repro/out/repro']
REPRO_TIMEOUTS = (1800, 300)      # seconds: compiling sqlite3.c with sanitizers, then the run


def repro_sandbox(home, upstream_dir, src, out):
    return ['bwrap', '--ro-bind', '/', '/', '--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp', '--tmpfs', '/run/user',
            '--tmpfs', '/mnt', '--remount-ro', '/mnt', '--tmpfs', home, '--remount-ro', home,
            '--ro-bind', upstream_dir, '/tmp/repro/upstream', '--ro-bind', src, '/tmp/repro/src/repro.c',
            '--bind', out, '/tmp/repro/out', '--unshare-all', '--die-with-parent', '--new-session', '--clearenv',
            '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'HOME', '/nonexistent',
            '--setenv', 'ASAN_OPTIONS', 'detect_leaks=0:abort_on_error=0',
            '--setenv', 'UBSAN_OPTIONS', 'print_stacktrace=1:halt_on_error=1', '--chdir', '/tmp/repro/out']


def run_repros(wt, cid, upstream_dir, outroot):
    """Build and run each tests/repro/F-draft-<cid>-<k>.c in wt; write <outroot>/F-draft-<cid>-<k>.txt with the fixed
    commands, exit codes and output. Returns {relpath: summary}. A symlink or non-regular file is not built."""
    res = {}
    d = os.path.join(wt, 'tests', 'repro')
    names = sorted(n for n in (os.listdir(d) if os.path.isdir(d) else []) if REPRO_RX.match('tests/repro/' + n)
                   and REPRO_RX.match('tests/repro/' + n).group(1) == cid)
    home = os.path.expanduser('~')
    for n in names:
        rel = 'tests/repro/' + n
        src = os.path.join(d, n)
        txt = os.path.join(outroot, n[:-2] + '.txt')
        os.makedirs(outroot, exist_ok=True)
        st_ = os.lstat(src)
        if not stat.S_ISREG(st_.st_mode):
            open(txt, 'w').write('not built: %s is not a regular file\n' % rel)
            res[rel] = 'not a regular file'
            continue
        if not os.path.isfile(os.path.join(upstream_dir, 'sqlite3.c')):
            open(txt, 'w').write('not built: %s/sqlite3.c is missing\n' % upstream_dir)
            res[rel] = 'not built: no upstream'
            continue
        out = os.path.join(outroot, n[:-2] + '.build')
        shutil.rmtree(out, ignore_errors=True)
        os.makedirs(out)
        lines = ['campaign.py built and ran %s (checkpoint 1, fix 2): against main\'s upstream/sqlite3.c (%s), in a '
                 'sandbox with no network, no $HOME and an empty environment.' % (rel, sha256_file(os.path.join(upstream_dir, 'sqlite3.c')))]
        summary = []
        for step, cmd, tmo in (('build', REPRO_CC, REPRO_TIMEOUTS[0]), ('run', REPRO_RUN, REPRO_TIMEOUTS[1])):
            lines.append('$ ' + ' '.join(cmd))
            try:
                pr = subprocess.run(['nice', '-n', '10'] + repro_sandbox(home, upstream_dir, src, out) + cmd,
                                    capture_output=True, timeout=tmo)
                body = (pr.stdout + pr.stderr).decode('utf-8', 'replace')
                rc = pr.returncode
            except subprocess.TimeoutExpired as e:
                body = ((e.stdout or b'') + (e.stderr or b'')).decode('utf-8', 'replace') + '\n(timed out after %d s)' % tmo
                rc = 'timeout'
            lines.append(body[-60000:])
            lines.append('exit: %s' % rc)
            summary.append('%s exit %s' % (step, rc))
            if step == 'build' and rc != 0:
                break
        if any(x in '\n'.join(lines) for x in ('ERROR: AddressSanitizer', 'runtime error:')):
            summary.append('sanitizer report')
        open(txt, 'w').write('\n'.join(lines) + '\n')
        shutil.rmtree(out, ignore_errors=True)
        res[rel] = ', '.join(summary)
    return res


def sha256_file(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def prompt_resume(kind):
    return ('Your session was interrupted. Continue the task you were given, from where you left off; your '
            'instructions are unchanged and are in agents/%s/GOAL.md. Do not repeat work already complete.\n' % kind)


def prompt_oneoff(role, n):
    if role == 'spec-review':
        return ('You are a reviewer session in the proving-sqlite project, on the vendor that did not write the file '
                'you review. Read GOAL.md §2 (P3), PROPERTIES.md (P3, which states the departures), AGENTS.md, and '
                'proofs/spec/record_format.h. Check ref_serial_get and ref_serial_bytes against the serial type table '
                'in SQLite\'s file format document at the pin, section 2.1 "Record Format": evidence/spec/fileformat2.html '
                '(evidence/spec/README.md gives its source and hashes), row by row, and check that each departure '
                'PROPERTIES.md P3 lists is written out and that nothing else departs from the table. It must be at most '
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

    @staticmethod
    def usage_text(wt, used, cap):
        pct = 100.0 * used / cap if cap else 0
        return ('tokens_used %d\ncap %d\npercent %.1f\n' % (used, cap, pct) +
                '# %d of %d tokens (%.1f%%) used by this card\'s %s sessions so far; at 80%% report STUCK.\n' % (
                    used, cap, pct, 'builder' if '-r' not in os.path.basename(wt) else 'reviewer'))

    def write_usage_before(self, wt, used, cap):
        """Before a session starts: refuse it (the card goes to triage) if .campaign/usage cannot be written safely."""
        try:
            write_worktree_usage(wt, self.usage_text(wt, used, cap))
        except WorktreeFileError as e:
            raise SessionRefused('not starting a session: %s' % e)

    def write_usage_file(self, st, job, used, cap):
        """Write .campaign/usage in the job's worktree. If .campaign or usage has been replaced by something that is
        not a real directory or a regular file, write nothing, stop the session and mark it for triage."""
        wt = job['wt']
        if job.get('tamper'):
            return
        try:
            write_worktree_usage(wt, self.usage_text(wt, used, cap))
        except WorktreeFileError as e:
            job['tamper'] = str(e)
            st.journal('tamper', job=job['id'], card=job.get('card'), why=str(e))
            kill_job(job)

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
        """Start a session, or raise SessionRefused if sessions.toml's command is not campaign.py's
        (template_problems) or the filled command line fails command_problems."""
        job.update(vendor=vendor, model=model, effort=effort, wt=wt)
        key = 'resume' if resume_of and resume_of.get('cli_session') else 'start'
        probs = template_problems(vendor, key, vcfg.get(key)) + role_value_problems('the session\'s', model, effort)
        cfg = ''
        if vendor == 'claude' and not probs:
            cfg = (resume_of or {}).get('config') or os.path.join(self.p.state, 'claude-config', job['id'])
            seed_claude_config(cfg)
            job['config'] = cfg
        home = os.path.expanduser('~')
        places = dict(dir=wt, model=model, effort=effort, home=home, wtroot=self.p.wt, repo=self.p.primary, config=cfg,
                      session=(resume_of or {}).get('cli_session') or '')
        argv = prepare_mounts(fill(vcfg.get(key) or [], **places), home) if not probs else []
        if not probs:
            probs = command_problems(vendor, argv, wt, self.p)
        if probs:
            job['state'] = 'refused'
            job['outcome'] = 'refused: ' + '; '.join(probs)
            release_claude_config(job)
            st.journal('session-refused', job=job['id'], card=job.get('card'), vendor=vendor, why='; '.join(probs))
            raise SessionRefused('refused to start a %s session: %s' % (vendor, '; '.join(probs)))
        if vendor == 'codex':
            # its own scratch space (checkpoint 0 follow-up 8): /tmp is not writable, TMPDIR is tmp/ in the worktree,
            # which .gitignore ignores; a new round starts with it empty
            tmpd = os.path.join(wt, 'tmp')
            if not resume_of and os.path.isdir(tmpd) and not os.path.islink(tmpd):
                shutil.rmtree(tmpd, ignore_errors=True)
            if os.path.islink(tmpd):
                os.remove(tmpd)
            os.makedirs(tmpd, exist_ok=True)
            job['env'] = {'TMPDIR': tmpd}
        if resume_of and resume_of.get('cli_session'):
            job['resumed_from'] = resume_of['id']
            job['cli_session'] = resume_of['cli_session']
            if vendor == 'codex':
                job['codex_base'] = resume_of.get('codex_last_total') or {}
                job['rollout'] = resume_of.get('rollout')
        st.journal('session-start', job=job['id'], card=job.get('card'), role=job.get('role'), vendor=vendor,
                   model=model, round=job.get('round'), resume=bool(resume_of),
                   sessions_sha256=vcfg.get('_sessions_sha256'))
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
        if resume_job is None:
            nxt = c['round'] + 1
            report = 'reports/%s-b%d.md' % (cid, nxt)
            if nxt > MAX_BUILDER_ROUNDS or not card.allows(report):
                # checkpoint 1, D4: never start a round whose report the May change line doesn't list
                c['job'] = None
                self.set_state(st, c, 'triage', 'builder round %d not started: the limit is %d rounds, and %s is %s on '
                               'the May change line (decision D4); Zach decides whether to extend the card' % (
                                   nxt, MAX_BUILDER_ROUNDS, report, 'listed' if card.allows(report) else 'not'))
                return
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
        self.write_usage_before(wt, c['tokens_builder'], card.cap_builder)
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
        self.write_usage_before(wt, c['tokens_reviewer'], card.cap_reviewer)
        repros = None
        if resume_job is None and rereview is None and c.get('builder_verdict') == 'FINDING':
            # checkpoint 1, fix 2: campaign.py, not the reviewer, builds and runs the repro files
            outroot = os.path.join(self.p.state, 'repro', '%s-r%d' % (cid, c['round']))
            repros = run_repros(wt, cid, os.path.join(self.p.main_dir(), 'upstream'), outroot)
            dest = os.path.join(wt, '.campaign', 'repro')
            os.makedirs(dest, exist_ok=True)
            for n in os.listdir(outroot) if os.path.isdir(outroot) else []:
                if n.endswith('.txt'):
                    shutil.copy(os.path.join(outroot, n), os.path.join(dest, n))
            st.journal('repro', card=cid, round=c['round'], results=repros)
        job = new_job(st, 'reviewer', card=cid, role='reviewer', round=c['round'], tier=card.tier, commit=commit,
                      rereview=rereview)
        if resume_job and resume_job.get('cli_session'):
            prompt = prompt_resume('reviewer')
        else:
            prompt = prompt_reviewer(cid, c['round'], commit, 'reports/%s-b%d.md' % (cid, c['round']), rereview, repros)
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
        self.write_usage_file(st, job, used, cap)
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
        rel = release_claude_config(job)
        if rel and rel.startswith('refreshed'):
            st.journal('claude-login-refreshed', job=job['id'])
        if job.get('tamper'):
            c['job'] = None
            job['outcome'] = 'tamper: ' + job['tamper']
            if job['role'] == 'reviewer':
                self.remove_wt(job['wt'])
            self.set_state(st, c, 'triage', '%s session stopped: %s (nothing committed)' % (job['role'], job['tamper']))
            self.record_tokens(job)
            return
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
        try:
            verdict = first_word(read_worktree_file(wt, 'reports/%s-b%d.md' % (cid, c['round'])))
        except WorktreeFileError as e:
            job['outcome'] = 'report not a regular file'
            self.set_state(st, c, 'triage', 'builder\'s report: %s (nothing committed)' % e)
            return
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
        try:
            text = read_worktree_file(wt, rname)
        except WorktreeFileError as e:
            job['outcome'] = 'review not a regular file'
            self.remove_wt(wt)
            self.set_state(st, c, 'triage', 'reviewer\'s verdict: %s (review discarded)' % e)
            return
        verdict = first_word(text)
        if verdict is None:
            self.interrupted(st, c, card, job, sess, 'ended without its verdict (exit %s)' % job['rc'])
            return
        job['outcome'] = verdict
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
        # mid-campaign: mutants of cards with no proofs on main are pending (checkpoint 1, D1); the full gate after the
        # last merge, below in do_land's sha-None branch, allows none
        ok, last, failing = run_gate(p, mw, ['ALLOW_PENDING=1'], glog)
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
    sp = sessions_problems(load_sessions(p.main_dir()))
    if sp:
        raise CampaignError('tools/sessions.toml: ' + '; '.join(sp))
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
        st.d['tmux'] = not a.no_tmux      # finish kills the tmux session only if this campaign made it (T-004)
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
        own_tmux = bool(st.d.get('tmux'))
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
    if own_tmux:   # never another campaign's session: the selftest's finish once killed the live campaign's (T-004)
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
            release_claude_config(job)
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
    verdicts = {}
    for x in paths:
        if x.endswith('.md') and (x.startswith('reviews/') or x.startswith('reports/')):
            try:
                verdicts[x] = first_word(read_worktree_file(wt, x))
            except WorktreeFileError as e:
                print('%s: %s; nothing committed (worktree %s kept)' % (x, e, wt))
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
    for x, v in verdicts.items():
        first = v
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


def tempfile_dir(base):
    import tempfile
    return tempfile.mkdtemp(prefix='unit-', dir=base)


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
        'C-25': ('a builder that leaves .campaign/usage as a symlink to a file outside its worktree',
                 {'C-25/builder/1': ['usage-symlink']}),
        'C-26': ('a builder whose report is a FIFO', {'C-26/builder/1': ['report-fifo']}),
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
        self.fstate = os.path.join(self.base, 'fakecli-state')    # the fake CLIs reach it through self.sock
        self.sock = os.path.join(self.base, 'fakecli.sock')
        self.server = None
        self.outside = os.path.join(self.base, 'outside-target.txt')   # C-25's symlink points here
        self.marker = os.path.join('/tmp', 'campaign-selftest-marker-%d' % os.getpid())

    def start_fake_server(self):
        """Attempt counters and the fake CLIs' log, behind a unix socket: a reviewer's sandbox can connect to it
        (the fixture is visible read-only) but can write no shared file."""
        import socketserver
        import threading
        lock = threading.Lock()
        test = self
        os.makedirs(self.fstate, exist_ok=True)

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                line = self.rfile.readline()
                if not line:
                    return
                with lock:
                    resp = test.fake_op(json.loads(line))
                self.wfile.write((json.dumps(resp) + '\n').encode())

        class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True
        self.server = Server(self.sock, Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def fake_op(self, req):
        sf = os.path.join(self.fstate, 'fakecli.state')
        s = json.load(open(sf)) if os.path.exists(sf) else {'counters': {}, 'sessions': {}}
        if req['op'] == 'log':
            with open(os.path.join(self.fstate, 'fakecli.log'), 'a') as f:
                f.write(json.dumps(req['entry']) + '\n')
            return {}
        if req['op'] == 'session':
            return {'info': s['sessions'].get(req['sid'])}
        n = s['counters'].get(req['key'], 0)
        s['counters'][req['key']] = n + 1
        s['sessions'][req['sid']] = req['info']
        json.dump(s, open(sf, 'w'))
        return {'n': n}

    def ok(self, name, cond, detail=''):
        self.results.append((name, bool(cond)))
        print('%s %s%s' % ('ok  ' if cond else 'FAIL', name, '' if cond or not detail else '\n     | ' + str(detail)[:1500].replace('\n', '\n     | ')))
        sys.stdout.flush()

    def env(self):
        e = dict(os.environ)
        e['PATH'] = ':'.join([os.path.join(self.home, 'bin'), os.path.join(self.home, '.local', 'bin'),
                              os.path.join(self.home, '.nvm', 'bin'), e.get('PATH', '')])
        e['HOME'] = self.home
        e.pop('TMUX', None)                                # never the caller's tmux server
        e['TMUX_TMPDIR'] = os.path.join(self.base, 'tmux')
        e['FAKECLI_CONTROL'] = self.ctl
        e['FAKECLI_SOCKET'] = self.sock
        e['FAKECLI_OUTSIDE'] = self.outside
        e['FAKECLI_PROBE'] = json.dumps({
            'host /tmp': self.marker, 'state/': os.path.join(self.wt, 'state', 'state.json'),
            'main checkout': os.path.join(self.wt, 'main', 'cards'), '~/.codex': os.path.join(self.home, '.codex', 'sessions'),
            'primary checkout files': os.path.join(self.primary, 'PROGRESS.md'),
            'other worktree': os.path.join(self.wt, 'C-02', 'cards'),
            '~/.claude (other sessions\' transcripts)': os.path.join(self.home, '.claude', 'projects', 'orchestrator.jsonl'),
            '~/.claude login': os.path.join(self.home, '.claude', '.credentials.json'),
            '/run/user/<uid>': '/run/user/%d' % os.getuid(),
            '~/.config/gh': os.path.join(self.home, '.config', 'gh', 'hosts.yml'),
            '~/.aws': os.path.join(self.home, '.aws', 'credentials'),
            '~/.docker': os.path.join(self.home, '.docker', 'config.json'),
            # checkpoint 1, Q2 and Q4
            '$HOME (~/.gitconfig)': os.path.join(self.home, '.gitconfig'), '~/.ssh': os.path.join(self.home, '.ssh', 'id_fake'),
            '~/.codex/rules (approval allow-list)': os.path.join(self.home, '.codex', 'rules', 'default.rules'),
            '~/.codex/skills': os.path.join(self.home, '.codex', 'skills', 'fake', 'SKILL.md'),
            '~/.codex/memories': os.path.join(self.home, '.codex', 'memories', 'm.md'),
            '/mnt (on WSL, /mnt/wslg/distro shows all of /)': next(
                (os.path.join('/mnt', x) for x in sorted(os.listdir('/mnt')) if x != 'wsl') if os.path.isdir('/mnt') else iter(()),
                '/mnt/none')})
        # present in campaign.py's environment, as on a desktop session: a reviewer's sandbox must unset them
        e['DBUS_SESSION_BUS_ADDRESS'] = 'unix:path=/run/user/%d/bus' % os.getuid()
        e['XDG_RUNTIME_DIR'] = '/run/user/%d' % os.getuid()
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
        os.makedirs(os.path.join(self.home, '.claude', 'projects'))
        os.makedirs(os.path.join(self.home, '.codex', 'sessions'))
        open(os.path.join(self.home, '.claude', 'projects', 'orchestrator.jsonl'), 'w').write('{"orchestrator": 1}\n')
        open(os.path.join(self.home, '.claude', 'settings.json'), 'w').write('{"hooks": {}}\n')
        open(os.path.join(self.home, '.claude', '.credentials.json'), 'w').write(json.dumps({'claudeAiOauth': {
            'accessToken': 'fake-access', 'refreshToken': 'fake-refresh', 'expiresAt': 4102444800000,
            'scopes': ['user:inference'], 'subscriptionType': 'max'}}))
        open(os.path.join(self.home, '.claude.json'), 'w').write(json.dumps({
            'oauthAccount': {'emailAddress': 'selftest@example.invalid'}, 'userID': 'fake', 'hasCompletedOnboarding': True,
            'projects': {'/elsewhere': {'note': 'another project'}}}))
        for rel, text in (('.config/gh/hosts.yml', 'github.com:\n  oauth_token: fake\n'),
                          ('.aws/credentials', '[default]\naws_secret_access_key = fake\n'),
                          ('.docker/config.json', '{"auths": {}}\n')):
            os.makedirs(os.path.dirname(os.path.join(self.home, rel)), exist_ok=True)
            open(os.path.join(self.home, rel), 'w').write(text)
        open(self.outside, 'w').write('outside the worktree\n')
        # the fake CLIs live outside the repo, as the real ones do: a reviewer's sandbox hides the primary checkout.
        # Inside a session's sandbox, $HOME is hidden but for each CLI's install (checkpoint 1, Q2 and Q4), so the fakes
        # sit where the real ones do, ~/.local/bin/claude and ~/.nvm, and run fake.py from outside $HOME
        shutil.copytree(os.path.join(TOOLS, 'fakecli'), os.path.join(self.home, 'bin'), ignore=shutil.ignore_patterns('__pycache__'))
        fsrc = os.path.join(self.base, 'fakecli-src')
        shutil.copytree(os.path.join(TOOLS, 'fakecli'), fsrc, ignore=shutil.ignore_patterns('__pycache__'))
        for rel, v in (('.local/bin/claude', 'claude'), ('.nvm/bin/codex', 'codex')):
            w = os.path.join(self.home, rel)
            os.makedirs(os.path.dirname(w), exist_ok=True)
            open(w, 'w').write('#!/bin/sh\nexec python3 %s %s "$@"\n' % (shlex.quote(os.path.join(fsrc, 'fake.py')), v))
            os.chmod(w, 0o755)
        os.makedirs(os.path.join(self.home, '.local', 'share', 'claude'))
        for rel, text in (('.codex/rules/default.rules', 'prefix_rule(pattern=["git", "push"], decision="allow")\n'),
                          ('.codex/skills/fake/SKILL.md', '---\nname: fake\n---\n'), ('.codex/memories/m.md', 'x\n'),
                          ('.ssh/id_fake', 'not a key\n')):
            os.makedirs(os.path.dirname(os.path.join(self.home, rel)), exist_ok=True)
            open(os.path.join(self.home, rel), 'w').write(text)
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
        ctl = {'limit_reset_seconds': 6, 'C-01/reviewer/1': ['probe'], 'C-01/builder/1': ['probe']}
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
            # every card starts in waiting: until the daemon has started a session for one of them, a phase whose
            # cards are all waiting has not begun (a poll before its first pass counted it as settled)
            if not any(j.get('card') in cards for j in st.get('jobs', {}).values()):
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
                     session='S', home=home, wtroot=p.wt, repo=p.primary,
                     config=os.path.join(p.state, 'claude-config', 'J0000-unit'))
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
            ('codex with the sandbox bypassed', 'codex', lambda a: a[:a.index('exec') + 1] + ['--dangerously-bypass-approvals-and-sandbox'] + a[a.index('exec') + 1:], 'not allowed'),
            # checkpoint 1, Q2 and Q4: both vendors in bubblewrap, $HOME and /mnt hidden and read-only
            ('codex without bwrap', 'codex', lambda a: a[a.index('codex'):], 'bwrap'),
            ('codex bwrap that leaves $HOME visible', 'codex', drop(('--tmpfs', home)), 'hide %s ' % home),
            ('codex bwrap that leaves /mnt visible (/mnt/wslg/distro is a second view of /)', 'codex', drop(('--tmpfs', '/mnt')), 'hide /mnt'),
            ('codex bwrap that leaves $HOME writable', 'codex', drop(('--remount-ro', home)), 'remount %s read-only' % home),
            ('codex bwrap that shows ~/.codex/rules (Zach\'s allow-list: git push, ...)', 'codex',
             drop(('--tmpfs', os.path.join(home, '.codex', 'rules'))), '.codex/rules'),
            ('codex bwrap that lets codex install skills into ~/.codex/skills', 'codex',
             drop(('--remount-ro', os.path.join(home, '.codex', 'skills'))), '.codex/skills'),
            ('codex bwrap that binds ~/.ssh back', 'codex', lambda a: a[:a.index('--chdir')] + [
                '--ro-bind', os.path.join(home, '.ssh'), os.path.join(home, '.ssh')] + a[a.index('--chdir'):], 'read-only binds'),
            ('claude with skills and commands (the account\'s synced skills)', 'claude',
             lambda a: [x for x in a if x != '--disable-slash-commands'], '--disable-slash-commands'),
            ('claude with MCP servers from anywhere but --mcp-config (claude.ai connectors)', 'claude',
             lambda a: [x for x in a if x != '--strict-mcp-config'], '--strict-mcp-config'),
            ('claude bwrap that leaves $HOME visible', 'claude', drop(('--tmpfs', home)), 'hide %s ' % home),
            ('claude bwrap that leaves /mnt visible', 'claude', drop(('--tmpfs', '/mnt')), 'hide /mnt'),
            ('claude bwrap that leaves $HOME writable', 'claude', drop(('--remount-ro', home)), 'remount %s read-only' % home),
            ('claude bwrap that binds all of ~/.local back', 'claude', lambda a: a[:a.index('--chdir')] + [
                '--ro-bind', os.path.join(home, '.local'), os.path.join(home, '.local')] + a[a.index('--chdir'):], 'read-only binds'),
            ('codex with a second sandbox_mode', 'codex', lambda a: a[:-1] + ['-c', 'sandbox_mode="danger-full-access"', '-'], 'exactly once'),
            ('claude without bwrap', 'claude', lambda a: a[a.index('claude'):], 'bwrap'),
            ('claude with bypassPermissions', 'claude', lambda a: [x if x != 'auto' else 'bypassPermissions' for x in a], 'not allowed'),
            ('bwrap with a shared /tmp', 'claude', lambda a: a[:a.index('/tmp') - 1] + ['--bind', '/tmp', '/tmp'] + a[a.index('/tmp') + 1:], '/tmp'),
            ('bwrap that leaves ~/.codex visible', 'claude', drop(('--tmpfs', os.path.join(home, '.codex'))), '.codex'),
            ('bwrap that leaves the other worktrees and state/ visible', 'claude', drop(('--tmpfs', p.wt)), 'state'),
            ('bwrap that binds / writable afterwards', 'claude', lambda a: a[:a.index('--chdir')] + ['--bind', '/', '/'] + a[a.index('--chdir'):], 'writable'),
            # checkpoint 0 follow-up 8
            ('codex without sandbox_workspace_write.exclude_slash_tmp=true', 'codex',
             drop(('-c', 'sandbox_workspace_write.exclude_slash_tmp=true')), 'exclude_slash_tmp'),
            ('codex with exclude_slash_tmp=false', 'codex',
             lambda a: [x.replace('exclude_slash_tmp=true', 'exclude_slash_tmp=false') for x in a], 'exclude_slash_tmp'),
            ('codex with another sandbox_workspace_write key', 'codex',
             lambda a: a[:-1] + ['-c', 'sandbox_workspace_write.network_access=true', '-'], 'sandbox_workspace_write'),
            # checkpoint 0 follow-up 6
            ('bwrap that leaves /run/user/<uid> visible', 'claude', drop(('--tmpfs', '/run/user')), '/run/user'),
            ('bwrap that keeps DBUS_SESSION_BUS_ADDRESS', 'claude', drop(('--unsetenv', 'DBUS_SESSION_BUS_ADDRESS')), 'DBUS_SESSION_BUS_ADDRESS'),
            ('bwrap that keeps XDG_RUNTIME_DIR', 'claude', drop(('--unsetenv', 'XDG_RUNTIME_DIR')), 'XDG_RUNTIME_DIR'),
            ('bwrap that leaves ~/.claude visible', 'claude', drop(('--tmpfs', os.path.join(home, '.claude'))), '.claude'),
            ('bwrap that binds ~/.claude writable', 'claude', lambda a: a[:a.index('--chdir')] + [
                '--bind', os.path.join(home, '.claude'), os.path.join(home, '.claude')] + a[a.index('--chdir'):], 'writable'),
            ('bwrap that leaves ~/.claude.json readable', 'claude', lambda a: [x for i, x in enumerate(a) if not (
                a[i:i + 3] == ['--ro-bind', '/dev/null', os.path.join(home, '.claude.json')] or
                a[max(0, i - 1):i + 2] == ['--ro-bind', '/dev/null', os.path.join(home, '.claude.json')] or
                a[max(0, i - 2):i + 1] == ['--ro-bind', '/dev/null', os.path.join(home, '.claude.json')])], '.claude.json'),
            ('bwrap with CLAUDE_CONFIG_DIR set to ~/.claude', 'claude', lambda a: a[:a.index('CLAUDE_CONFIG_DIR') + 1] + [
                os.path.join(home, '.claude')] + a[a.index('CLAUDE_CONFIG_DIR') + 2:], 'CLAUDE_CONFIG_DIR'),
        ]
        for name, vendor, edit, needle in cases:
            try:
                pr = probs(vendor, edit)
            except ValueError as ex:      # the command line lacks what the case edits
                pr = ['case not applicable: %s' % ex]
            self.ok('session guard refuses %s' % name, pr and any(needle in x for x in pr), pr)
        # checkpoint 1, Q2: a ~/.codex/AGENTS.md (global instructions codex would load through the ~/.codex it needs)
        gi = os.path.join(home, '.codex', 'AGENTS.md')
        os.makedirs(os.path.dirname(gi), exist_ok=True)
        open(gi, 'w').write('global instructions\n')
        pr = probs('codex')
        os.remove(gi)
        self.ok('session guard refuses a codex session while ~/.codex/AGENTS.md exists', any('AGENTS.md' in x for x in pr), pr)
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

    def followup_checks(self):
        """Checkpoint 0 follow-ups 5, 7 and 8, in process: no daemon; sessions are not spawned."""
        p = P(self.primary)
        sess = load_sessions(self.primary)
        g = globals()
        uwt = os.path.join(self.base, 'unit-wt')
        os.makedirs(uwt, exist_ok=True)

        class FakeSt:
            d = {'triage_seq': 0, 'jobs': {}, 'job_seq': 0}
            entries = []

            def journal(self, kind, **k):
                self.entries.append(dict(k, kind=kind))
        spawned = []
        orig = g['spawn_runner']
        g['spawn_runner'] = lambda p_, job, argv, cwd, text: spawned.append((job['id'], argv, dict(job.get('env') or {})))
        try:
            def start(vendor, key, edit, n):
                role = 'builder' if vendor == 'codex' else 'reviewer'
                v, m, e, cfg = role_config(sess, role, 'standard')
                cfg = dict(cfg)
                cfg[key] = edit(list(cfg[key]))
                st = FakeSt()
                st.entries = []
                job = {'id': 'J%04d-unit' % n, 'kind': 'session', 'role': role, 'card': 'C-01', 'round': 1}
                try:
                    Campaign(p).start_session(st, job, v, m, e, cfg, uwt, 'prompt')
                    return None, job, st
                except SessionRefused as ex:
                    return str(ex), job, st
            same = lambda a: a  # noqa: E731
            for n, (name, vendor, edit, needle) in enumerate([
                    ('a codex command without --disable apps (a change the flag guard does not catch)', 'codex',
                     lambda a: [x for i, x in enumerate(a) if not (x == 'apps' or (x == '--disable' and a[i + 1] == 'apps'))], 'differs'),
                    ('a codex command with an extra -c setting', 'codex', lambda a: a[:-1] + ['-c', 'model_verbosity="high"', '-'], 'differs'),
                    ('a claude command whose --effort is a literal, not {effort}', 'claude',
                     lambda a: [x if x != '{effort}' else 'max' for x in a], 'differs')]):
                refused, job, st = start(vendor, 'start', edit, 10 + n)
                self.ok('sessions.toml is refused: %s' % name, refused and needle in refused
                        and not any(s[0] == job['id'] for s in spawned), refused)
            # auditor recheck item 2: {model} and {effort} values are plain names, never an option or a quote
            for n, (field, value) in enumerate([('model', '--dangerously-bypass-approvals-and-sandbox'),
                                                ('model', '-o'), ('effort', 'high" -c sandbox_mode="danger-full-access'),
                                                ('effort', 'high\n'), ('model', 'a b'), ('model', ''), ('effort', 5)]):
                role, vendor = ('builder', 'codex') if n % 2 == 0 else ('reviewer', 'claude')
                bad = json.loads(json.dumps(sess))
                bad['roles'][role]['standard'][field] = value
                try:
                    role_config(bad, role, 'standard')
                    rc_refused = None
                except SessionRefused as ex:
                    rc_refused = str(ex)
                v, m, e, cfg = role_config(sess, role, 'standard')
                m, e = (value, e) if field == 'model' else (m, value)
                job = {'id': 'J%04d-unit' % (30 + n), 'kind': 'session', 'role': role, 'card': 'C-01', 'round': 1}
                st = FakeSt()
                st.entries = []
                try:
                    Campaign(p).start_session(st, job, v, m, e, cfg, uwt, 'prompt')
                    ss_refused = None
                except SessionRefused as ex:
                    ss_refused = str(ex)
                release_claude_config(job)
                sp_ = sessions_problems(bad)
                self.ok('a sessions.toml %s %s of %r is refused by role_config, start_session (before filling, nothing '
                        'spawned) and the start check' % (role, field, value),
                        rc_refused and 'not a plain name' in rc_refused and ss_refused and 'not a plain name' in ss_refused
                        and not any(s[0] == job['id'] for s in spawned) and not job.get('config')
                        and any('not a plain name' in x for x in sp_), (rc_refused, ss_refused, sp_))
            refused, job, st = start('codex', 'start', same, 20)
            sp = [s for s in spawned if s[0] == job['id']]
            ss = [x for x in st.entries if x['kind'] == 'session-start']
            self.ok('sessions.toml\'s own codex command starts; its session-start entry records sessions.toml\'s sha256',
                    not refused and sp and ss and ss[0].get('sessions_sha256') == sess.get('_sha256') and sess.get('_sha256'),
                    (refused, ss))
            self.ok('a codex session gets TMPDIR in its worktree (tmp/, created), not /tmp',
                    sp and sp[0][2].get('TMPDIR') == os.path.join(uwt, 'tmp') and os.path.isdir(os.path.join(uwt, 'tmp')),
                    sp[:1])
            refused, job, st = start('claude', 'start', same, 21)
            cfgd = job.get('config') or ''
            self.ok('a claude session gets its own CLAUDE_CONFIG_DIR under state/claude-config/, mode 700, seeded with '
                    'the login and only the account keys of ~/.claude.json',
                    not refused and cfgd.startswith(os.path.join(p.state, 'claude-config') + '/')
                    and stat.S_IMODE(os.stat(cfgd).st_mode) == 0o700
                    and os.path.exists(os.path.join(cfgd, '.credentials.json'))
                    and sorted(json.load(open(os.path.join(cfgd, '.claude.json')))) == ['hasCompletedOnboarding', 'oauthAccount', 'userID'],
                    (refused, cfgd))
            release_claude_config(job)     # no session ran: remove the copy of the login
            # sessions.toml as shipped passes; the campaign refuses to start on one that differs
            self.ok('the shipped sessions.toml has exactly campaign.py\'s command lines', not sessions_problems(sess),
                    sessions_problems(sess))
        except Exception as ex:   # an older campaign.py lacks these functions
            self.ok('follow-up 5/6/8 checks ran', False, '%s: %s' % (type(ex).__name__, ex))
        finally:
            g['spawn_runner'] = orig
        # checkpoint 1, fix 2: campaign.py builds and runs repro files itself, sandboxed: no network, no $HOME
        try:
            rdir = os.path.join(self.base, 'unit-repro')
            os.makedirs(os.path.join(rdir, 'upstream'), exist_ok=True)
            os.makedirs(os.path.join(rdir, 'wt', 'tests', 'repro'), exist_ok=True)
            open(os.path.join(rdir, 'upstream', 'sqlite3.c'), 'w').write(
                '#include <stdio.h>\n#include <stdlib.h>\nstatic int toyRead(const unsigned char *p, int i){ return p[i]; }\n')
            open(os.path.join(rdir, 'wt', 'tests', 'repro', 'F-draft-C-01-1.c'), 'w').write(
                '#include "sqlite3.c"\n#include <sys/socket.h>\n#include <netinet/in.h>\n#include <arpa/inet.h>\n'
                'int main(void){\n  printf("home readable: %%s\\n", fopen("%s", "r") ? "yes" : "no");\n'
                '  int s = socket(AF_INET, SOCK_STREAM, 0); struct sockaddr_in a = {0}; a.sin_family = AF_INET;\n'
                '  a.sin_port = htons(443); inet_pton(AF_INET, "1.1.1.1", &a.sin_addr);\n'
                '  printf("network: %%s\\n", (s >= 0 && connect(s, (struct sockaddr*)&a, sizeof a) == 0) ? "yes" : "no");\n'
                '  fflush(stdout);\n  unsigned char *p = malloc(2); return toyRead(p, 2);\n}\n' % os.path.join(self.home, '.gitconfig'))
            os.symlink('/etc/hostname', os.path.join(rdir, 'wt', 'tests', 'repro', 'F-draft-C-01-2.c'))
            rr = run_repros(os.path.join(rdir, 'wt'), 'C-01', os.path.join(rdir, 'upstream'), os.path.join(rdir, 'out'))
            t1 = open(os.path.join(rdir, 'out', 'F-draft-C-01-1.txt')).read()
            self.ok('fix 2: campaign.py builds and runs a repro with its fixed command under ASan and UBSan, in a sandbox where '
                    '$HOME is unreadable and the network unreachable; a symlinked repro is not built',
                    'build exit 0' in rr.get('tests/repro/F-draft-C-01-1.c', '') and 'sanitizer report' in rr['tests/repro/F-draft-C-01-1.c']
                    and ('ERROR: AddressSanitizer' in t1 or 'runtime error:' in t1)
                    and 'home readable: no' in t1 and 'network: no' in t1
                    and rr.get('tests/repro/F-draft-C-01-2.c') == 'not a regular file', (rr, t1[-1500:]))
            pr = prompt_reviewer('C-01', 2, 'abc', 'reports/C-01-b2.md', None, rr)
            self.ok('fix 2: the reviewer of a FINDING round is handed the output, told not to build or run repros, and '
                    'told never to run make in a card directory',
                    '.campaign/repro/' in pr and 'do not build or run them yourself' in pr and 'never make in a card directory' in pr, pr)
        except Exception as ex:
            self.ok('fix 2 checks ran', False, '%s: %s' % (type(ex).__name__, ex))
        # checkpoint 1, D4: a seventh builder round is never started; the card goes to triage instead
        try:
            spawned7 = []
            g['spawn_runner'] = lambda p_, job, argv, cwd, text: spawned7.append(job['id'])
            text = fixture_card('C-01').replace(', reports/C-01-b*.md', ''.join(', reports/C-01-b%d.md' % k for k in range(1, 7)))
            card6 = cardlib.Card('C-01', text)
            for rnd, want_triage in ((6, True), (2, None)):
                st = FakeSt()
                st.entries = []
                c = {'id': 'C-01', 'state': 'ready', 'round': rnd, 'epoch_rounds': 0, 'interruptions': 0, 'history': [],
                     'tokens_builder': 0, 'job': None, 'notes': []}
                if want_triage:
                    Campaign(p).start_builder_round(st, c, card6, sess)
                    self.ok('D4: a builder round past 6 is never started; the card goes to triage for Zach',
                            c['state'] == 'triage' and 'round 7 not started' in (c.get('reason') or '')
                            and 'D4' in c['reason'] and not spawned7, (c.get('reason'), spawned7))
                else:
                    short = cardlib.Card('C-01', text.replace(', reports/C-01-b3.md', ''))
                    Campaign(p).start_builder_round(st, c, short, sess)
                    self.ok('D4: nor is a round whose report the May change line does not list (b3 here)',
                            c['state'] == 'triage' and 'round 3 not started' in (c.get('reason') or '') and not spawned7,
                            (c.get('reason'), spawned7))
        except Exception as ex:
            self.ok('D4 checks ran', False, '%s: %s' % (type(ex).__name__, ex))
        finally:
            g['spawn_runner'] = orig
        # follow-up 7: the usage file and verdict files, directly
        try:
            target = os.path.join(self.base, 'unit-outside.txt')
            open(target, 'w').write('outside\n')
            cases = []
            for name, setup in [
                    ('.campaign/usage is a symlink to a file outside', lambda w: (os.makedirs(os.path.join(w, '.campaign')),
                                                                         os.symlink(target, os.path.join(w, '.campaign', 'usage')))),
                    ('.campaign/usage is a hard link to a file outside', lambda w: (os.makedirs(os.path.join(w, '.campaign')),
                                                                           os.link(target, os.path.join(w, '.campaign', 'usage')))),
                    ('.campaign is a symlink to a directory outside', lambda w: os.symlink(self.base, os.path.join(w, '.campaign')))]:
                w = tempfile_dir(self.base)
                setup(w)
                job = {'id': 'J0030-unit', 'wt': w, 'card': 'C-01', 'dir': w}
                FakeSt.entries = []
                Campaign(p).write_usage_file(FakeSt(), job, 5, 10)
                cases.append((name, bool(job.get('tamper')), open(target).read() == 'outside\n'
                              and not os.path.exists(os.path.join(self.base, 'usage'))))
            for name, tampered, untouched in cases:
                self.ok('campaign.py writes nothing when %s, and stops the session for triage' % name, tampered and untouched,
                        (tampered, untouched))
            w = tempfile_dir(self.base)
            os.makedirs(os.path.join(w, 'reports'))
            os.mkfifo(os.path.join(w, 'reports', 'C-01-b1.md'))
            os.symlink(target, os.path.join(w, 'reports', 'C-01-b2.md'))
            os.symlink(self.base, os.path.join(w, 'reviews'))
            got = [bounded_worktree_read(w, rel) for rel in ('reports/C-01-b1.md', 'reports/C-01-b2.md',
                                                              'reviews/fakecli.sock')]
            self.ok('a report that is a FIFO or a symlink, or a review under a symlinked reviews/, is refused, not read',
                    all(kind == 'refused' for kind, _ in got), got)
        except Exception as ex:
            self.ok('follow-up 7 checks ran', False, '%s: %s' % (type(ex).__name__, ex))

    def run(self):
        self.build_fixture()
        self.start_fake_server()
        print('selftest fixture: %s' % self.base)
        real_home = os.environ.get('HOME')
        os.environ['HOME'] = self.home      # the guards and seeding see the fixture's home, never the real login
        try:
            self.unit_checks()
            self.followup_checks()
        finally:
            os.environ['HOME'] = real_home
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
        fresh = {'cards': {c: {'state': 'waiting'} for c in a_cards}, 'jobs': {}, 'merge_queue': []}
        self.ok('a phase whose cards are all still waiting with no session run yet is not settled (the wait would '
                'end before the daemon\'s first pass)', not self.settled(a_cards)(fresh))
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
        self.ok('C-25 %s: triage, nothing committed, the outside file unchanged' % self.PHASE_A['C-25'][0],
                S('C-25') == 'triage' and '.campaign/usage' in R('C-25') and 'builder round' not in cb('C-25')
                and open(self.outside).read() == 'outside the worktree\n', R('C-25') + ' | ' + cb('C-25'))
        self.ok('C-26 %s: triage, nothing committed, and the daemon did not block on it' % self.PHASE_A['C-26'][0],
                S('C-26') == 'triage' and 'FIFO' in R('C-26') and 'builder round' not in cb('C-26'), R('C-26') + ' | ' + cb('C-26'))
        pr_ = [x for x in self.fakelog() if x.get('probe') is not None and x.get('vendor') == 'claude']
        seen = pr_[0]['probe'] if pr_ else {}
        positive = ('own worktree writable', 'own CLAUDE_CONFIG_DIR writable, with the login', 'wrote ~/.claude/.probe-write')
        self.ok('a reviewer\'s sandbox hides the host /tmp, state/, main\'s checkout, other worktrees, ~/.codex, the '
                'primary checkout, ~/.claude, ~/.claude.json, /run/user/<uid>, ~/.config/gh, ~/.aws and ~/.docker, unsets '
                'DBUS_SESSION_BUS_ADDRESS and XDG_RUNTIME_DIR; its own worktree and its own seeded CLAUDE_CONFIG_DIR are '
                'writable, and what it writes to ~/.claude never reaches the real one; and (checkpoint 1, Q4) the rest '
                'of $HOME (~/.gitconfig, ~/.ssh) and /mnt are hidden and $HOME is read-only',
                pr_ and all(seen.get(k) for k in positive[:2]) and len(seen) >= 24
                and not any(v for k, v in seen.items() if k not in positive)
                and not os.path.exists(os.path.join(self.home, '.claude', '.probe-write'))
                and not os.path.exists(os.path.join(self.home, '.probe-write')), seen)
        bp = [x for x in self.fakelog() if x.get('probe') is not None and x.get('vendor') == 'codex']
        bseen = bp[0]['probe'] if bp else {}
        bpos = ('own worktree writable', '~/.codex')
        self.ok('checkpoint 1, Q2: a builder\'s sandbox hides $HOME but ~/.codex (its login and session logs) and nvm, '
                'hides /mnt, ~/.ssh, ~/.gitconfig, ~/.claude, state/, other worktrees and the primary checkout, and inside '
                '~/.codex the approval rules, skills and memories; $HOME is read-only and its worktree writable',
                bp and all(bseen.get(k) for k in bpos) and len(bseen) >= 24
                and not any(v for k, v in bseen.items() if k not in bpos)
                and not os.path.exists(os.path.join(self.home, '.probe-write')), bseen)
        cfgs = [j.get('config') for j in st['jobs'].values() if j.get('vendor') == 'claude' and j['kind'] != 'oneoff']
        fresh = [j.get('config') for j in st['jobs'].values() if j.get('vendor') == 'claude' and not j.get('resumed_from')]
        left = glob.glob(os.path.join(self.wt, 'state', 'claude-config', '*', '.credentials.json'))
        self.ok('every claude session had its own CLAUDE_CONFIG_DIR under state/ (%d sessions), and no copy of the '
                'login is left once they end' % len(cfgs),
                cfgs and all(cfgs) and len(set(fresh)) == len(fresh) and not left, (cfgs, left))
        tm = [x for x in fl if x.get('vendor') == 'codex' and 'tmpdir' in x]
        self.ok('every codex session ran with TMPDIR in its own worktree (%d sessions)' % len(tm),
                tm and all(x['tmpdir'] == os.path.join(x['cwd'], 'tmp') for x in tm), [(x['cwd'], x['tmpdir']) for x in tm][:5])
        raw = subprocess.run(['git', 'show', 'main:tools/sessions.toml'], cwd=self.primary, capture_output=True).stdout
        h = hashlib.sha256(raw).hexdigest()
        ss = [e for e in jr if e['kind'] == 'session-start']
        self.ok('every session-start entry in the journal records sessions.toml\'s sha256 (%d entries)' % len(ss),
                ss and all(e.get('sessions_sha256') == h for e in ss), [e.get('sessions_sha256') for e in ss][:3])
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
        os.makedirs(os.path.join(self.base, 'tmux'), exist_ok=True)
        tm = subprocess.run(['tmux', 'new-session', '-d', '-s', 'campaign', 'sleep 600'], env=self.env(), capture_output=True, text=True)
        p = self.camp('finish', timeout=120)
        alive = subprocess.run(['tmux', 'has-session', '-t', 'campaign'], env=self.env(), capture_output=True).returncode == 0
        subprocess.run(['tmux', 'kill-server'], env=self.env(), capture_output=True)
        self.ok('finish of a campaign started with --no-tmux leaves a tmux session named campaign alone (T-004: the '
                'selftest\'s finish killed the live campaign\'s daemon)', tm.returncode == 0 and alive, tm.stderr)
        self.ok('finish: primary checkout back on main with orch merged, main\'s checkout removed',
                p.returncode == 0 and current_branch(self.primary) == 'main' and not os.path.isdir(os.path.join(self.wt, 'main'))
                and 'orchestrator note' in open(os.path.join(self.primary, 'PROGRESS.md')).read(), p.stdout + p.stderr)
        # API-key variables never reach a session (they were planted in campaign.py's own environment)
        fl = self.fakelog()
        leaked = sorted(set(k for x in fl for k in x.get('apikeys', []) + x.get('claude_vars', [])))
        self.ok('no session saw the API-key or CLAUDE_CODE_ variables planted in campaign.py\'s environment (%d sessions)' % len(fl),
                fl and not leaked, leaked)

    def cleanup(self):
        if self.server:
            self.server.shutdown()
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
