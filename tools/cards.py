"""Parse cards/C-NN.md (GOAL.md Appendix B). campaign.py, scan.py and gate.py read cards only
through this module, so the line formats live in one place:

  # C-NN: <functions>
  - Property: P1 | P2 | P3
  - Functions: <name> (upstream/sqlite3.c:<line>), ...
  - In-scope callees, with approved contracts: ...
  - Boundary callees, with ledger entries: ...
  - In-scope callers, whose call sites must satisfy the requires: ...
  - Unreached callees, bodies removed: <name> (upstream/sqlite3.c:<line>), ... | none    (optional; see below)
  - Depends on: C-NN, C-NN (not a callee: <reason>), ... | none
  - May change: <path>, <path>, ...
  - Cap: builder <N>M; reviewer half that. Tier: high | standard
  - Notes: ...

A Depends on item whose card proves none of this card's callees (in-scope or boundary) gives its reason in
parentheses (checkpoint 1, fix 5); depends_problems() checks it, and scan.py reports what it finds.

"Unreached callees, bodies removed" names callees the card's requires exclude. tools/prove.py removes their bodies
(goto-instrument --remove-function-body) before drop-unused-functions in each of the card's proofs, so DFCC never
loads what they reach (checkpoint 1 fix 1: os_unix's syscall table aborts DFCC). A call to one that a proof does
reach fails it: under DFCC as "undefined function should be unreachable", otherwise as a function without a body.
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


def parse_depends(cid, dep):
    """'C-04, C-14 (not a callee: why)' -> (['C-04', 'C-14'], {'C-14': 'not a callee: why'})."""
    if dep.strip().lower() in ('', 'none', '-'):
        return [], {}
    items, depth, cur = [], 0, ''
    for ch in dep:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth < 0:
                raise CardFormatError('%s: unbalanced ")" in Depends on' % cid)
        if ch == ',' and depth == 0:
            items.append(cur)
            cur = ''
        else:
            cur += ch
    if depth != 0:
        raise CardFormatError('%s: unbalanced "(" in Depends on' % cid)
    items.append(cur)
    out, reasons = [], {}
    for it in items:
        m = re.match(r'^\s*(C-[0-9]{2})\s*(?:\((.*)\))?\s*\.?\s*$', it, re.S)
        if not m:
            raise CardFormatError('%s: Depends on item %r is not C-NN or C-NN (reason)' % (cid, it.strip()))
        out.append(m.group(1))
        if m.group(2) is not None:
            if not m.group(2).strip():
                raise CardFormatError('%s: Depends on %s has an empty reason' % (cid, m.group(1)))
            reasons[m.group(1)] = m.group(2).strip()
    return out, reasons


def depends_problems(cards):
    """Each Depends on item names a card, and one whose card proves none of this card's callees gives a reason."""
    probs = []
    for k, c in sorted(cards.items()):
        callees = set(c.in_scope_callees) | set(c.boundary_callees)
        for d in c.depends:
            if d not in cards:
                probs.append('%s: Depends on %s, which has no card' % (k, d))
            elif not (set(cards[d].functions) & callees) and d not in c.depends_reason:
                probs.append('%s: Depends on %s, whose functions (%s) are not its callees; give the reason in '
                             'parentheses, or drop it (checkpoint 1, fix 5)' % (k, d, ', '.join(cards[d].functions)))
    return probs


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
        self.depends, self.depends_reason = parse_depends(cid, dep)
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
        un = fields.get('Unreached callees, bodies removed', 'none')
        self.unreached_callees = re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*\(upstream/sqlite3\.c:\d+\)', un)
        if un.strip().lower() not in ('', 'none') and not self.unreached_callees:
            raise CardFormatError('%s: Unreached callees line must be "<name> (upstream/sqlite3.c:<line>), ..." or none' % cid)
        both = sorted(set(self.unreached_callees) & set(self.functions))
        if both:
            raise CardFormatError('%s: %s is both a function of the card and an unreached callee' % (cid, ', '.join(both)))

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
    seen.discard(cid)   # sharing a function with a caller makes the walk come back to cid itself
    return sorted(seen)


def callers_of_direct(cards, cid):
    fns = set(cards[cid].functions)
    return [k for k, c in cards.items() if k != cid and
            (cid in c.depends or fns & (set(c.functions) | set(c.in_scope_callees)))]
