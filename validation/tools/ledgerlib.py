"""Read ledger.patch's per-process counter files and violation logs.

Counter file layout: struct LedgerShm in ledger.patch (util.c).  Counter
names come from the enum ledger.patch adds to sqliteInt.h, so this stays in
step with the patch.
"""
import os, re, struct, glob, collections

HERE = os.path.dirname(os.path.abspath(__file__))
PATCH = os.path.join(HERE, '..', 'ledger.patch')

def counter_names():
    txt = open(PATCH).read()
    m = re.search(r'\+#define LEDGER_HMAX (\d+)', txt)
    hmax = int(m.group(1))
    body = txt[txt.index('+enum {'):txt.index('+  LC_NCOUNTER')]
    body = '\n'.join(l[1:] for l in body.splitlines())
    body = re.sub(r'/\*.*?\*/', '', body, flags=re.S)
    names = []
    for tok in body.replace('enum {', '').split(','):
        tok = tok.strip()
        if not tok:
            continue
        if '=' in tok:
            name = tok.split('=')[0].strip()
            if name.startswith('LH_'):
                names.extend('%s[%d]' % (name, i) for i in range(hmax + 1))
            continue
        if tok == 'LC_NSCALAR':
            continue
        names.append(tok)
    return names, hmax

NAMES, HMAX = counter_names()
HDR = struct.Struct('<8siiii512s512s2048s')

def read_counter_file(path):
    data = open(path, 'rb').read()
    if len(data) < HDR.size:
        return None
    magic, ncount, pid, flags, hmax, exe, cwd, cmd = HDR.unpack_from(data)
    if not magic.startswith(b'LEDGER2'):
        return None
    assert ncount == len(NAMES) and hmax == HMAX, (path, ncount, len(NAMES))
    vals = struct.unpack_from('<%dq' % ncount, data, HDR.size)
    dec = lambda b: b.split(b'\0', 1)[0].decode('utf-8', 'replace')
    return dict(pid=pid, flags=flags, exe=dec(exe), cwd=dec(cwd),
                cmd=dec(cmd).strip(), counters=dict(zip(NAMES, vals)))

def read_counter_dir(d):
    out = []
    for p in sorted(glob.glob(os.path.join(d, 'c.*.bin'))):
        r = read_counter_file(p)
        if r:
            r['file'] = p
            out.append(r)
    return out

def read_violations(d):
    """Each record: dict with entry, header fields, args, backtrace list."""
    recs = []
    for p in sorted(glob.glob(os.path.join(d, 'v.*.log'))):
        cur = None
        for line in open(p, errors='replace'):
            line = line.rstrip('\n')
            if line.startswith('=== LEDGER VIOLATION '):
                cur = dict(entry=line.split()[-1], bt=[], file=p)
                section = 'hdr'
            elif line == '=== END':
                if cur:
                    recs.append(cur)
                cur = None
            elif cur is not None:
                if line == 'backtrace:':
                    section = 'bt'
                elif line == 'maps:':
                    section = 'maps'
                elif section == 'bt':
                    cur['bt'].append(line.strip())
                elif section == 'hdr' and ': ' in line:
                    k, v = line.split(': ', 1)
                    cur[k] = v
    return recs

def parse_args(s):
    """'k=v k=v ...' -> dict (values without spaces)."""
    d = {}
    for m in re.finditer(r'(\S+?)=(\S*)', s or ''):
        d.setdefault(m.group(1), m.group(2))
    return d

def total(records, pred=lambda r: True):
    c = collections.Counter()
    for r in records:
        if pred(r):
            c.update({k: v for k, v in r['counters'].items() if v})
    return c

def hist(counter, base):
    return [counter.get('%s[%d]' % (base, i), 0) for i in range(HMAX + 1)]
