#!/usr/bin/env python3
"""Fake codex and claude CLIs for `tools/campaign.py selftest`. Never used in a real campaign: only the selftest
puts tools/fakecli/ first on PATH. Reads the prompt on stdin, works out card, role and round, and acts out the
behavior FAKECLI_CONTROL names for that (card/role/round, attempt), emitting each vendor's event format:
codex --json events plus a rollout log under $HOME/.codex/sessions (running token counts), or claude stream-json.

Behaviors: done, approve, reject, needs-zach, finding, stuck, crash, limit, auth (the login has expired), outside,
commit-outside, own-review, symlink (a May change path left as a symlink), exec-mode (an executable harness.c),
touch-tracked, probe (a session records what its sandbox lets it see, then approves or reports DONE), burn, slow:<seconds>,
answer-review, missing (exit 0, no report), usage-symlink (a builder replaces .campaign/usage with a symlink to
$FAKECLI_OUTSIDE, waits for campaign.py to write it, then reports DONE), report-fifo (a builder's report is a FIFO).
`codex login status` and `claude auth status` report logged in unless $HOME/.fakecli-logged-out exists. Attempt
counters and the log are kept by the selftest, reached through the unix socket $FAKECLI_SOCKET: a sandboxed reviewer
can write nothing outside its worktree and its own config directory.
"""
import json
import socket
import os
import re
import subprocess
import sys
import time
import uuid

vendor = sys.argv[1]
argv = sys.argv[2:]
if argv[:2] in (['login', 'status'], ['auth', 'status']):
    if os.path.exists(os.path.join(os.path.expanduser('~'), '.fakecli-logged-out')):
        print('Not logged in' if vendor == 'codex' else '{"loggedIn": false}')
        sys.exit(1)
    print('Logged in using ChatGPT' if vendor == 'codex' else '{"loggedIn": true, "authMethod": "claude.ai"}')
    sys.exit(0)
CTRL = os.environ.get('FAKECLI_CONTROL')
ctrl = json.load(open(CTRL)) if CTRL and os.path.exists(CTRL) else {}


def rpc(op, **kw):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(os.environ['FAKECLI_SOCKET'])
    s.sendall((json.dumps(dict(kw, op=op)) + '\n').encode())
    buf = b''
    while not buf.endswith(b'\n'):
        b = s.recv(65536)
        if not b:
            break
        buf += b
    s.close()
    return json.loads(buf or b'{}')


def log(entry):
    rpc('log', entry=entry)


prompt = sys.stdin.read()
cwd = os.getcwd()
resume = (vendor == 'codex' and argv[:2] == ['exec', 'resume']) or (vendor == 'claude' and '--resume' in argv)
sid = None
if resume:
    sid = argv[2] if vendor == 'codex' else argv[argv.index('--resume') + 1]


m = re.search(r'cards/(C-[0-9]{2})\.md', prompt)
role = 'builder' if 'builder session' in prompt else ('reviewer' if 'reviewer session' in prompt else None)
rm = re.search(r'This is round (\d+)', prompt) or re.search(r'builder round (\d+)', prompt) or re.search(r'reviews/C-[0-9]{2}-r(\d+)\.md', prompt)
card, rnd = (m.group(1) if m else None), (int(rm.group(1)) if rm else None)
if resume:
    info = rpc('session', sid=sid).get('info')
    if info:
        card, role, rnd = info['card'], info['role'], info['round']
        if role is None:
            role = 'builder' if vendor == 'codex' else 'reviewer'
if sid is None:
    sid = str(uuid.uuid4())
key = '%s/%s/%s' % (card, role, rnd)


attempt = rpc('bump', key=key, sid=sid, info={'card': card, 'role': role, 'round': rnd})['n']
default = 'done' if role == 'builder' else 'approve'
seq = ctrl.get(key) or ctrl.get('%s/%s/*' % (card, role)) or [default]
beh = seq[attempt] if attempt < len(seq) else seq[-1]
log({'t': time.time(), 'vendor': vendor, 'argv': argv, 'key': key, 'attempt': attempt, 'behavior': beh,
     'resume': resume, 'sid': sid, 'cwd': cwd, 'pid': os.getpid(), 'prompt': prompt[:400], 'tmpdir': os.environ.get('TMPDIR'),
     'apikeys': sorted(k for k in os.environ if k.endswith('_API_KEY') or k == 'ANTHROPIC_AUTH_TOKEN'),
     'claude_vars': sorted(k for k in os.environ if k.startswith('CLAUDE_CODE_') or k == 'CLAUDECODE')})

home = os.path.expanduser('~')
rollout = os.path.join(home, '.codex', 'sessions', '2026', '01', '01', 'rollout-2026-01-01T00-00-00-%s.jsonl' % sid)
total = {'input_tokens': 0, 'cached_input_tokens': 0, 'cache_write_input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}
if vendor == 'codex' and os.path.exists(rollout):
    for line in open(rollout):
        e = json.loads(line)
        if e.get('payload', {}).get('type') == 'token_count':
            total = e['payload']['info']['total_token_usage']


def emit(obj):
    sys.stdout.write(json.dumps(obj) + '\n')
    sys.stdout.flush()


def spend(n_in, n_out):
    if vendor == 'codex':
        total['input_tokens'] += n_in
        total['output_tokens'] += n_out
        total['total_tokens'] = total['input_tokens'] + total['output_tokens']
        os.makedirs(os.path.dirname(rollout), exist_ok=True)
        with open(rollout, 'a') as f:
            f.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {'total_token_usage': dict(total)}}}) + '\n')
    else:
        emit({'type': 'stream_event', 'event': {'type': 'message_delta', 'usage': {'input_tokens': n_in, 'cache_read_input_tokens': 0,
                                                                                  'cache_creation_input_tokens': 0, 'output_tokens': n_out}}})


if vendor == 'codex':
    emit({'type': 'thread.started', 'thread_id': sid})
else:
    emit({'type': 'system', 'subtype': 'init', 'session_id': sid, 'apiKeySource': 'none', 'model': 'fake'})


def write(rel, text):
    p = os.path.join(cwd, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w') as f:
        f.write(text)


def finish(rc=0):
    spend(1000, 100)
    if vendor == 'codex':
        emit({'type': 'turn.completed', 'usage': {'input_tokens': 1000, 'cached_input_tokens': 0, 'output_tokens': 100}})
    else:
        emit({'type': 'result', 'subtype': 'success', 'is_error': rc != 0, 'session_id': sid, 'result': 'fake done'})
    sys.exit(rc)


def builder_files(verdict):
    write('proofs/%s/harness.c' % card, '/* fake harness for %s round %s */\n' % (card, rnd))
    write('proofs/%s/NOTES.md' % card, 'fake notes\n')
    write('reports/%s-b%s.md' % (card, rnd), '%s\nfake report for %s round %s\n' % (verdict, card, rnd))


spend(5000, 500)
if beh.startswith('slow:'):
    time.sleep(float(beh.split(':')[1]))
    beh = default
if beh == 'crash':
    sys.stderr.write('fake: simulated crash\n')
    sys.exit(1)
if beh == 'missing':
    finish(0)
if beh == 'limit':
    reset = int(time.time()) + int(ctrl.get('limit_reset_seconds', 6))
    if vendor == 'codex':
        emit({'type': 'error', 'message': 'You’ve hit your usage limit. Upgrade to Pro or try again later.', 'resets_at': reset})
    else:
        emit({'type': 'result', 'is_error': True, 'result': 'Claude AI usage limit reached|%d' % reset})
    sys.exit(1)
if beh == 'auth':
    if vendor == 'codex':
        emit({'type': 'error', 'message': 'Your access token could not be refreshed. Please log out and sign in again.'})
    else:
        emit({'type': 'result', 'is_error': True, 'result': 'Failed to authenticate: OAuth token revoked. Please log in again.'})
    sys.exit(1)
if beh == 'burn':
    for _ in range(400):
        spend(150000, 1000)
        time.sleep(0.2)
    finish(0)


def probe():
    """Record what this session's sandbox lets it see and write (checkpoint 0 follow-up 6; checkpoint 1, Q2 and Q4)."""
    seen = {}
    for name, path in json.loads(os.environ.get('FAKECLI_PROBE') or '{}').items():
        seen[name] = os.path.exists(path)
    try:
        seen['~/.claude.json readable'] = bool(open(os.path.join(home, '.claude.json')).read())
    except OSError:
        seen['~/.claude.json readable'] = False
    for k in ('DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR'):
        seen['env ' + k] = k in os.environ
    try:
        open(os.path.join(cwd, '.probe-write'), 'w').write('x')
        seen['own worktree writable'] = True
    except OSError:
        seen['own worktree writable'] = False
    cfg = os.environ.get('CLAUDE_CONFIG_DIR') or ''
    try:
        if not cfg:
            raise OSError('CLAUDE_CONFIG_DIR unset')
        open(os.path.join(cfg, '.probe-write'), 'w').write('x')
        os.remove(os.path.join(cfg, '.probe-write'))
        seen['own CLAUDE_CONFIG_DIR writable, with the login'] = bool(cfg) and os.path.exists(os.path.join(cfg, '.credentials.json'))
    except OSError:
        seen['own CLAUDE_CONFIG_DIR writable, with the login'] = False
    try:
        open(os.path.join(home, '.claude', '.probe-write'), 'w').write('x')
        seen['wrote ~/.claude/.probe-write'] = True     # into a tmpfs: the selftest checks the host's stays absent
    except OSError:
        seen['wrote ~/.claude/.probe-write'] = False
    try:
        open(os.path.join(home, '.probe-write'), 'w').write('x')
        seen['wrote $HOME/.probe-write'] = True
    except OSError:
        seen['wrote $HOME/.probe-write'] = False
    log({'t': time.time(), 'vendor': vendor, 'key': key, 'probe': seen, 'cwd': cwd, 'config': cfg})
    os.remove(os.path.join(cwd, '.probe-write'))


if role == 'builder':
    if beh == 'probe':
        probe()
        builder_files('DONE')
    elif beh == 'outside':
        write('tools/evil.py', 'x = 1\n')
        builder_files('DONE')
    elif beh == 'commit-outside':
        write('tools/evil2.py', 'x = 2\n')
        subprocess.run(['git', 'add', 'tools/evil2.py'], cwd=cwd)
        subprocess.run(['git', '-c', 'user.name=fake', '-c', 'user.email=f@f', 'commit', '-qm', 'sneaky'], cwd=cwd)
        builder_files('DONE')
    elif beh == 'symlink':
        builder_files('DONE')
        os.remove(os.path.join(cwd, 'proofs', card, 'NOTES.md'))
        os.symlink('/etc/hostname', os.path.join(cwd, 'proofs', card, 'NOTES.md'))
    elif beh == 'usage-symlink':
        u = os.path.join(cwd, '.campaign', 'usage')
        os.makedirs(os.path.dirname(u), exist_ok=True)
        if os.path.lexists(u):
            os.remove(u)
        os.symlink(os.environ['FAKECLI_OUTSIDE'], u)
        time.sleep(3)             # campaign.py writes usage every tick
        builder_files('DONE')
    elif beh == 'report-fifo':
        builder_files('DONE')
        r = os.path.join(cwd, 'reports', '%s-b%s.md' % (card, rnd))
        os.remove(r)
        os.mkfifo(r)
    elif beh == 'exec-mode':
        builder_files('DONE')
        os.chmod(os.path.join(cwd, 'proofs', card, 'harness.c'), 0o755)
    elif beh == 'own-review':
        builder_files('DONE')
        write('reviews/%s-r%s.md' % (card, rnd), 'APPROVE\nI approve my own work\n')
    elif beh == 'answer-review':
        want = 'reviews/%s-r%d.md' % (card, rnd - 1)
        builder_files('DONE' if want in prompt else 'STUCK')
        write('reports/%s-b%s.md' % (card, rnd), ('DONE\nanswers %s\n' % want) if want in prompt else 'STUCK\nno review named\n')
    elif beh in ('finding', 'stuck'):
        builder_files(beh.upper())
    else:
        builder_files('DONE')
else:
    verdict = {'approve': 'APPROVE', 'reject': 'REJECT', 'needs-zach': 'NEEDS-ZACH', 'touch-tracked': 'APPROVE'}.get(beh, 'APPROVE')
    if beh == 'probe':
        probe()
    if beh == 'touch-tracked':
        with open(os.path.join(cwd, 'cards', '%s.md' % card), 'a') as f:
            f.write('\nreviewer was here\n')
    write('reviews/%s-r%s.md' % (card, rnd), '%s\nfake review of %s round %s\n' % (verdict, card, rnd))
finish(0)
