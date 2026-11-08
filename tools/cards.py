"""Parse cards/C-NN.md (GOAL.md Appendix B). campaign.py, scan.py and gate.py read cards only
through this module, so the line formats live in one place:

  # C-NN: <functions>
  - Property: P1 | P2 | P3
  - Functions: <name> (upstream/sqlite3.c:<line>), ...
  - In-scope callees, with approved contracts: ...
  - Boundary callees, with ledger entries: ...
  - In-scope callers, whose call sites must satisfy the requires: ...
  - Depends on: C-NN, C-NN | none
  - May change: <path>, <path>, ...
  - Cap: builder <N>M; reviewer half that. Tier: high | standard
  - Notes: ...
"""
import os
import re

CARD_RE = re.compile(r'^C-[0-9]{2}$')


class CardFormatError(Exception):
    pass


def _tokens(s):
    return [t.strip() for t in re.split(r'[,\s]+', s) if t.strip()]


def parse_cap(s):
    m = re.match(r'^\s*([0-9]+(?:\.[0-9]+)?)\s*([kKmMbB]?)', s)
    if not m:
        raise CardFormatError('bad cap %r' % s)
    n = float(m.group(1))
    mult = {'': 1, 'k': 1e3, 'm': 1e6, 'b': 1e9}[m.group(2).lower()]
    return int(n * mult)


class Card:
    def __init__(self, cid, text, path=None):
        self.id = cid
        self.path = path
        self.text = text
        fields = {}
        title = None
        for line in text.split('\n'):
            if line.startswith('# ') and title is None:
                title = line[2:].strip()
            m = re.match(r'^- ([A-Za-z][A-Za-z ,\-]*?):\s*(.*)$', line)
            if m:
                fields.setdefault(m.group(1).strip(), m.group(2).strip())
        self.title = title or ''
        if not self.title.startswith(cid + ':'):
            raise CardFormatError('%s: first line must be "# %s: <functions>"' % (cid, cid))
        self.fields = fields
        self.property = fields.get('Property', '').strip()
        self.functions = re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*\(upstream/sqlite3\.c:\d+\)', fields.get('Functions', ''))
        dep = fields.get('Depends on')
        if dep is None:
            raise CardFormatError('%s: missing "- Depends on:" line' % cid)
        self.depends = [] if dep.strip().lower() in ('', 'none', '-') else _tokens(dep)
        for d in self.depends:
            if not CARD_RE.match(d):
                raise CardFormatError('%s: Depends on item %r is not C-NN' % (cid, d))
        mc = fields.get('May change')
        if mc is None:
            raise CardFormatError('%s: missing "- May change:" line' % cid)
        self.may_change = [p.strip().rstrip('.') for p in mc.split(',') if p.strip()]
        capline = fields.get('Cap')
        if capline is None:
            raise CardFormatError('%s: missing "- Cap:" line' % cid)
        m = re.match(r'^builder\s+(\S+);\s*reviewer half that\.\s*Tier:\s*(high|standard)\s*$', capline)
        if not m:
            raise CardFormatError('%s: Cap line must be "builder <N>M; reviewer half that. Tier: high|standard"' % cid)
        self.cap_builder = parse_cap(m.group(1))
        self.cap_reviewer = self.cap_builder // 2
        self.tier = m.group(2)
        self.in_scope_callees = re.findall(r'([A-Za-z_][A-Za-z0-9_]*)', fields.get('In-scope callees, with approved contracts', ''))
        self.boundary_callees = re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*\(', fields.get('Boundary callees, with ledger entries', ''))

    def allows(self, path):
        """True if repo-relative path is on the May change line. An entry ending in '/' covers the
        directory; an entry with '*' is a glob over one path component."""
        for p in self.may_change:
            if p.endswith('/') and path.startswith(p):
                return True
            if '*' in p:
                rx = '^' + re.escape(p).replace(r'\*', '[^/]*') + '$'
                if re.match(rx, path):
                    return True
            if path == p:
                return True
        return False


def load(root, cid):
    path = os.path.join(root, 'cards', cid + '.md')
    with open(path) as f:
        return Card(cid, f.read(), path)


def load_all(root):
    d = os.path.join(root, 'cards')
    out = {}
    if not os.path.isdir(d):
        return out
    for n in sorted(os.listdir(d)):
        m = re.match(r'^(C-[0-9]{2})\.md$', n)
        if m:
            out[m.group(1)] = load(root, m.group(1))
    return out


def callers_of(cards, cid):
    """Cards whose proofs call card cid's functions: they depend on it, or list one of its functions
    among their own functions or in-scope callees. Transitive."""
    target = cards[cid]
    fns = set(target.functions)
    direct = set()
    for k, c in cards.items():
        if k == cid:
            continue
        if cid in c.depends or fns & (set(c.functions) | set(c.in_scope_callees)):
            direct.add(k)
    seen = set()
    todo = list(direct)
    while todo:
        k = todo.pop()
        if k in seen:
            continue
        seen.add(k)
        todo.extend(x for x in callers_of_direct(cards, k) if x not in seen)
    return sorted(seen)


def callers_of_direct(cards, cid):
    fns = set(cards[cid].functions)
    return [k for k, c in cards.items() if k != cid and
            (cid in c.depends or fns & (set(c.functions) | set(c.in_scope_callees)))]
