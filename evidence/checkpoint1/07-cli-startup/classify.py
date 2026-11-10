"""Q2 (checkpoint 1): what each CLI loads, or looks for, at startup outside its worktree. Reads strace -f -e trace=%file
logs of one session each (probe.py ran the command campaign.py runs, filled and checked by it) and sorts the paths
by kind. Status per path: present (a call on it succeeded), absent (every call failed), unresolved (only calls strace
printed as unfinished). Usage: classify.py <label> <strace log> <worktree> [<label> <log> <wt> ...]"""
import re, sys
HOME = '/home/zpconn'
KINDS = [
    ('global instructions', r'(/\.codex/AGENTS(\.override)?\.md|/\.claude/CLAUDE\.md|/etc/claude-code/CLAUDE\.md|/claude-config/[^/]+/CLAUDE\.md)$'),
    ('instructions in parent directories', r'/(AGENTS|CLAUDE|CLAUDE\.local)\.md$'),
    ('hooks', r'hooks\.json$|/hooks(/|$)'),
    ('skills', r'/skills(/|$)|SKILL\.md$'),
    ('plugins', r'plugin\.json$|/plugins(/|$)'),
    ('MCP servers', r'mcp[^/]*\.json$'),
    ('memory', r'memor(y|ies)'),
    ('approval rules', r'/rules(/|$)|\.rules$'),
    ('agents and commands', r'/\.claude/(agents|commands|output-styles)(/|$)|/\.codex/agents(/|$)'),
    ('settings and managed policy', r'(config\.toml|requirements\.toml|managed[^/]*|settings[^/]*\.json|/\.claude\.json|reg\.exe|active_config|configs/default\.json)$|/etc/codex$|/etc/claude-code$'),
    ('login', r'(auth\.json|\.credentials\.json)$'),
    ('shell profile', r'/(\.bashrc|\.bash_profile|\.bash_login|\.profile|\.cargo/env)$|^/etc/profile'),
    ('git configuration', r'/(\.gitconfig|gitconfig)$|/\.config/git/'),
]
def parse(log):
    st = {}
    for line in open(log, errors='replace'):
        m = re.search(r'^\d+\s+\w+\((?:AT_FDCWD|\d+)?,?\s*"([^"]+)"', line)
        if not m or not m.group(1).startswith('/'):
            continue
        p = m.group(1)
        s = st.setdefault(p, set())
        if '<unfinished' in line:
            s.add('u')
        elif '= -1' in line:
            s.add('f')
        else:
            s.add('ok')
    return {p: ('present' if 'ok' in s else 'absent' if 'f' in s else 'unresolved') for p, s in st.items()}
args = sys.argv[1:]
for i in range(0, len(args), 3):
    label, log, wt = args[i:i + 3]
    st = parse(log)
    print('## %s' % label)
    for kind, rx in KINDS:
        rows = sorted((p, s) for p, s in st.items() if re.search(rx, p) and not p.startswith(wt + '/')
                      and '/node_modules/' not in p and '/.nvm/versions/' not in p and '/sessions/' not in p)
        if rows:
            print('### %s' % kind)
            for p, s in rows:
                print('- %-10s %s' % (s, p.replace(HOME, '~')))
    print()
