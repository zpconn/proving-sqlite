#!/usr/bin/env python3
"""prove.py: build and run a card's CBMC proofs, coverage, the include check and the configuration probe.

  prove.py includes --card-dir proofs/C-NN [--config c]: preprocess the harness and fail on any file it pulls in
  but the overlay's sqlite3.c, proofs/{include,contracts,spec}/*.h and system headers (the gate runs it).

Every proof is one translation unit: the card's harness.c, whose first line is
`#include "sqlite3.c"` (the overlay, found with -I), followed by contracts and predicates. Per
configuration the pipeline is:

  goto-cc <CONFIGS flags> -include proof.h -I overlay -I proofs/include -I proofs -c harness.c
  goto-cc --function <entry>                     (link; one goto program per proof)
  goto-instrument --remove-function-body f ...   (the proof's REPLACE functions and the card's unreached callees)
  goto-instrument --drop-unused-functions
  goto-instrument --show-goto-functions --json-ui (card-call argument types; see card_call_type_problems)
  goto-instrument --dfcc <entry> [--enforce-contract f/contract_f] [--replace-call-with-contract g/contract_g]...
                  [--apply-loop-contracts]       (only if the proof uses contracts)
  goto-instrument --slice-global-inits
  cbmc <every option in proofs/CHECKS> [--unwindset ...] [solver] [--object-bits n]

A proof with <name>_CONTRACTS := legacy (only the cards in LEGACY_CARDS: T-006, Zach 2026-11-10,
evidence/approvals/T-006-dfcc-loop-pointer/) uses CBMC's legacy contracts instead of DFCC:
  goto-cc ... -c <build>/<name>.legacy.c         (harness.c, then each ENFORCE and REPLACE function redeclared with
                                                  the clauses of its proofs/contracts/<fn>.h, generated at every build)
  link, remove-bodies, drop-unused and the argument-type check as above
  goto-instrument --replace-call-with-contract g ...   then   --apply-loop-contracts   then   --enforce-contract f
That order is required: with loop contracts applied before the replacement, a replaced callee whose body is removed
can write outside the loop's assigns unchecked (evidence/approvals/T-006-dfcc-loop-pointer/, the callee-frame toy).
The legacy engine reads clauses only from a function's own declaration (it can't use contract_<fn>), so each one is
copied, mechanically, from its header's contract_<fn> declaration with only the name changed; there is no stored
copy to diverge, and the build key includes the generated text, so a header edit always rebuilds. A replaced callee
with a static local aborts the legacy enforce pass (T-012): such a callee keeps its body.
  cbmc ... --conversion-check --property <id>... (the %float-to-int pass, when such properties exist)

Bodies are removed before drop-unused-functions (checkpoint 1, fix 1): otherwise drop-unused keeps everything a
replaced or unreached callee reaches, and for sqlite3VdbeMemSetNull's callers that includes os_unix's syscall table,
on whose close/read/fcntl64 DFCC aborts with an invariant violation. A replaced function's calls become its contract;
an unreached callee (cards/C-NN.md, "Unreached callees, bodies removed") that a proof does reach fails it, under DFCC
as "undefined function should be unreachable", without DFCC as a function without a body.

A proof also FAILS if CBMC reports a function without a body: calls to it would be unconstrained. It also FAILS
if, in the entry function, a call to a card function passes an argument whose type, before any cast, is not the
parameter's: a `u32 value` passed for a u64 parameter is narrowed by its declaration, which scan cannot see.

The card's Makefile is declarative (tools/scan.py enforces it):
  CARD := C-NN
  PROOFS := <name> ...
  <name>_ENTRY := <harness function>                 required
  <name>_ENFORCE := <fn>/contract_<fn>               at most one (DFCC checks one contract per run)
  <name>_REPLACE := <fn>/contract_<fn> ...           callees replaced by their contracts
  <name>_LOOPS := contracts | unwind | none          default none
  <name>_UNWINDSET := <fn>.<loop>:<bound>,...        bounds for unwound loops; assertions always on
  <name>_SOLVER := --smt2 | --z3 | --sat-solver cadical | --sat-solver minisat2 | --sat-solver glucose
  <name>_OBJECT_BITS := <8..16>
  <name>_COVER := <fn> ...                           functions whose lines coverage reports
  <name>_CONTRACTS := dfcc | legacy                 default dfcc; legacy only for LEGACY_CARDS (T-006)
  include ../Makefile.common

Every command prints one RESULT line last, e.g.
  RESULT prove C-03 lp64-le PASS 212s 1843 properties 0 failed
"""
import argparse
import json
import os
import re
import resource
import shlex
import signal
import subprocess
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import overlay as ov  # noqa: E402
import cards as cardlib  # noqa: E402

DEFAULT_TIMEOUT = 600          # seconds per CBMC run, per configuration (GOAL.md §0.9)
MEM_LIMIT = 12 * 1024 ** 3     # address-space cap per tool process, so CBMC fails instead of swapping
ALLOWED_SOLVERS = ['', '--smt2', '--z3', '--sat-solver cadical', '--sat-solver minisat2',
                   '--sat-solver glucose']
FLOAT2INT_DIRECTIVE = '%float-to-int'
# Zach, 2026-11-10 (evidence/approvals/T-006-dfcc-loop-pointer/): CBMC's legacy contracts, opted into per proof, only
# for the cards whose loops carry a pointer that DFCC can't encode (T-006). Every other proof stays on DFCC.
LEGACY_CARDS = ('C-15', 'C-17')
CONTRACT_CLAUSE_RX = re.compile(r'__CPROVER_(requires|ensures|assigns|frees)\b')
LEGACY_STATIC_ABORT = 'Expected an assignment of the form `symbol_exprt := side_effect_expr_nondett`'

IDENT = r'[A-Za-z_][A-Za-z0-9_]*'
RE_PAIR = re.compile(r'^(%s)/contract_(%s)$' % (IDENT, IDENT))
RE_UNWIND = re.compile(r'^%s\.[0-9]+:[0-9]+$' % IDENT)


class CardError(Exception):
    pass


# ---------------------------------------------------------------- configuration files

def read_configs(root=ROOT):
    """proofs/CONFIGS: `name  goto-cc flags...` per line; '#' comments."""
    cfgs = []
    with open(os.path.join(root, 'proofs', 'CONFIGS')) as f:
        for line in f:
            line = line.split('#', 1)[0].strip()
            if not line:
                continue
            parts = shlex.split(line)
            cfgs.append((parts[0], parts[1:]))
    return cfgs


def read_checks(root=ROOT):
    """proofs/CHECKS: option lines and %directives. Returns (options, float2int) where float2int
    is (extra option, description regex) or None."""
    opts, f2i = [], None
    with open(os.path.join(root, 'proofs', 'CHECKS')) as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            if s.startswith(FLOAT2INT_DIRECTIVE):
                rest = s[len(FLOAT2INT_DIRECTIVE):].strip()
                opt, pat = rest.split(None, 1)
                f2i = (opt, pat)
            elif s.startswith('--'):
                opts.extend(shlex.split(s))
            else:
                raise CardError('proofs/CHECKS: unrecognised line %r' % s)
    return opts, f2i


def parse_card_makefile(path):
    """Parse the declarative card Makefile. Returns dict of variables. Raises CardError on any
    line that is not a simple assignment, comment, blank, or the include."""
    vars_ = {}
    with open(path) as f:
        lines = f.read().split('\n')
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        s = raw.strip()
        if not s or s.startswith('#'):
            continue
        if s == 'include ../Makefile.common':
            continue
        m = re.match(r'^(%s)\s*:?=\s*(.*)$' % IDENT, s)
        if not m:
            raise CardError('%s: line %d is not NAME := value: %r' % (path, i, raw))
        name, val = m.group(1), m.group(2)
        if '$' in val or '`' in val:
            raise CardError('%s: line %d: no make expansions or shell in values' % (path, i))
        if '#' in val:
            val = val.split('#', 1)[0]
        vars_[name] = val.strip()
    return vars_


class Proof:
    def __init__(self, name, v):
        g = lambda k, d='': v.get('%s_%s' % (name, k), d)  # noqa: E731
        self.name = name
        self.entry = g('ENTRY')
        if not re.match('^%s$' % IDENT, self.entry or ''):
            raise CardError('%s_ENTRY must name the harness function' % name)
        self.enforce = g('ENFORCE').split()
        self.replace = g('REPLACE').split()
        self.loops = g('LOOPS', 'none') or 'none'
        self.unwindset = g('UNWINDSET')
        self.solver = ' '.join(g('SOLVER').split())
        self.object_bits = g('OBJECT_BITS')
        self.cover = g('COVER').split()
        self.contracts = g('CONTRACTS', 'dfcc') or 'dfcc'
        if len(self.enforce) > 1:
            raise CardError('%s_ENFORCE: at most one function per proof (DFCC checks one contract per run)' % name)
        for p in self.enforce + self.replace:
            if not RE_PAIR.match(p) or RE_PAIR.match(p).group(1) != RE_PAIR.match(p).group(2):
                raise CardError('%s: %r must be <fn>/contract_<fn>' % (name, p))
        if self.contracts not in ('dfcc', 'legacy'):
            raise CardError('%s_CONTRACTS must be dfcc or legacy' % name)
        if self.loops not in ('contracts', 'unwind', 'none'):
            raise CardError('%s_LOOPS must be contracts, unwind or none' % name)
        if self.unwindset:
            for item in self.unwindset.split(','):
                if not RE_UNWIND.match(item.strip()):
                    raise CardError('%s_UNWINDSET item %r must be fn.N:K' % (name, item))
        if self.solver not in ALLOWED_SOLVERS:
            raise CardError('%s_SOLVER %r not one of %s' % (name, self.solver, ALLOWED_SOLVERS))
        if self.object_bits and not (self.object_bits.isdigit() and 8 <= int(self.object_bits) <= 16):
            raise CardError('%s_OBJECT_BITS must be 8..16' % name)
        if not self.cover:
            self.cover = [p.split('/')[0] for p in self.enforce]
        self.enforced = [p.split('/')[0] for p in self.enforce]

    def uses_contracts(self):
        return bool(self.enforce or self.replace or self.loops == 'contracts')

    def uses_dfcc(self):
        return self.contracts == 'dfcc' and self.uses_contracts()

    def uses_legacy(self):
        return self.contracts == 'legacy' and self.uses_contracts()


def load_card(card_dir):
    mk = os.path.join(card_dir, 'Makefile')
    v = parse_card_makefile(mk)
    card = v.get('CARD')
    if not card or not re.match(r'^C-[0-9]{2}$', card):
        raise CardError('%s: CARD := C-NN missing' % mk)
    if os.path.basename(os.path.normpath(card_dir)) != card:
        raise CardError('%s: CARD %s does not match its directory' % (mk, card))
    names = v.get('PROOFS', '').split()
    if not names:
        raise CardError('%s: PROOFS is empty' % mk)
    allowed = {'CARD', 'PROOFS'}
    for n in names:
        for k in ('ENTRY', 'ENFORCE', 'REPLACE', 'LOOPS', 'UNWINDSET', 'SOLVER', 'OBJECT_BITS', 'COVER', 'CONTRACTS'):
            allowed.add('%s_%s' % (n, k))
    extra = sorted(set(v) - allowed)
    if extra:
        raise CardError('%s: variables not allowed: %s' % (mk, ' '.join(extra)))
    proofs = [Proof(n, v) for n in names]
    legacy = [p.name for p in proofs if p.contracts == 'legacy']
    if legacy and card not in LEGACY_CARDS:
        raise CardError('%s: %s_CONTRACTS := legacy, but only %s may use CBMC\'s legacy contracts (T-006)' % (
            mk, legacy[0], ', '.join(LEGACY_CARDS)))
    return card, proofs


def _strip_comments(text):
    return re.sub(r'//[^\n]*', '', re.sub(r'/\*.*?\*/', lambda m: ' ' * len(m.group(0)), text, flags=re.S))


def contract_declaration(text, fn):
    """The declaration of contract_<fn> in a contracts header, comments removed: (start, end, text). Exactly one."""
    t = _strip_comments(text)
    hits = [m for m in re.finditer(r'\bcontract_%s\s*\(' % re.escape(fn), t)]
    if len(hits) != 1:
        raise CardError('proofs/contracts/%s.h: %d declarations of contract_%s, want exactly one' % (fn, len(hits), fn))
    p = hits[0].start()
    start = max(t.rfind(';', 0, p), t.rfind('}', 0, p)) + 1
    nl = t.rfind('\n#', 0, p)                          # after the last preprocessor line, too
    if nl >= start:
        start = t.index('\n', nl + 1) + 1
    depth, i = 0, hits[0].end() - 1
    while i < len(t):
        c = t[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif c == ';' and depth == 0:
            return start, i + 1, t[start:i + 1].strip()
        i += 1
    raise CardError('proofs/contracts/%s.h: contract_%s\'s declaration has no closing ;' % (fn, fn))


def legacy_redeclaration(text, fn):
    """<fn> redeclared with exactly contract_<fn>'s clauses: the header's declaration with only its name changed."""
    decl = contract_declaration(text, fn)[2]
    out = re.sub(r'\bcontract_%s(\s*\()' % re.escape(fn), lambda m: fn + m.group(1), decl, count=1)
    # the check that the two can't diverge: the redeclaration is the header's declaration, token for token, but the name
    norm = lambda s: re.sub(r'\s+', ' ', s).strip()  # noqa: E731
    if norm(out.replace(fn + '(', 'contract_' + fn + '(', 1)) != norm(decl) or not CONTRACT_CLAUSE_RX.search(decl):
        raise CardError('proofs/contracts/%s.h: the legacy redeclaration does not match contract_%s' % (fn, fn))
    return out


def header_clause_problems(root=ROOT):
    """B2 (Zach, 2026-11-10): proofs/include/ headers carry no function contract clauses, and a contracts header puts
    clauses only on contract_<name> declarations. Under the legacy engine (T-006) a clause anywhere else would attach
    a contract of its own to a SQLite function; under DFCC it is meaningless. Every build checks this."""
    probs = []
    d = os.path.join(root, 'proofs', 'include')
    for n in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if n.endswith('.h') and n != 'proof.h':
            if CONTRACT_CLAUSE_RX.search(_strip_comments(open(os.path.join(d, n), errors='replace').read())):
                probs.append('proofs/include/%s carries a function contract clause (contracts live in proofs/contracts/)' % n)
    d = os.path.join(root, 'proofs', 'contracts')
    for n in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not n.endswith('.h'):
            continue
        t = '\n'.join(l for l in _strip_comments(open(os.path.join(d, n), errors='replace').read()).split('\n')
                      if not l.lstrip().startswith('#'))
        depth, start = 0, 0
        for i, c in enumerate(t + ';'):
            if c in '({':
                depth += 1
            elif c in ')}':
                depth -= 1
            elif c == ';' and depth == 0:
                stmt, start = t[start:i], i + 1
                if CONTRACT_CLAUSE_RX.search(stmt):
                    m = re.search(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(', stmt)
                    if not m or not m.group(1).startswith('contract_'):
                        probs.append('proofs/contracts/%s puts contract clauses on %s, not on a contract_<name> '
                                     'declaration' % (n, m.group(1) if m else '?'))
    return probs


def legacy_source(card_dir, proof):
    """The legacy translation unit: harness.c, then each ENFORCE and REPLACE function redeclared from its header."""
    harness = os.path.join(card_dir, 'harness.c')
    if CONTRACT_CLAUSE_RX.search(_strip_comments(open(harness, errors='replace').read())):
        raise CardError('%s: a legacy proof\'s harness may carry no function contract clauses: under the legacy engine '
                        'a redeclaration there would attach a contract of its own to a SQLite function' % harness)
    parts = ['/* Generated by tools/prove.py for proof %s (legacy contracts, T-006). Do not edit: it is rebuilt from '
             'proofs/contracts/ at every build. */' % proof.name, '#include "%s"' % os.path.abspath(harness)]
    for pair in proof.enforce + proof.replace:
        fn = pair.split('/')[0]
        hdr = os.path.join(ROOT, 'proofs', 'contracts', fn + '.h')
        if not os.path.exists(hdr):
            raise CardError('%s: no proofs/contracts/%s.h to generate its legacy contract from' % (proof.name, fn))
        parts.append('/* from proofs/contracts/%s.h */\n%s' % (fn, legacy_redeclaration(open(hdr, errors='replace').read(), fn)))
    return '\n'.join(parts) + '\n'


# ---------------------------------------------------------------- running tools

def _limits():
    os.setsid()
    try:
        resource.setrlimit(resource.RLIMIT_AS, (MEM_LIMIT, MEM_LIMIT))
    except (ValueError, OSError):
        pass


def run(cmd, log, timeout=None, cwd=None, stdout_path=None):
    """Run cmd under nice -n 10 in its own process group, output to log file (standard output to stdout_path
    instead, if given). Returns (returncode or 'timeout', seconds)."""
    t0 = time.time()
    with open(log, 'w') as lf, open(stdout_path or os.devnull, 'w') as of:
        lf.write('$ ' + ' '.join(shlex.quote(c) for c in cmd) + '\n')
        lf.flush()
        p = subprocess.Popen(['nice', '-n', '10'] + cmd, stdout=of if stdout_path else lf, stderr=subprocess.STDOUT
                             if not stdout_path else lf, cwd=cwd, preexec_fn=_limits)
        try:
            rc = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait()
            rc = 'timeout'
    return rc, time.time() - t0


RE_RESULT = re.compile(r'^\[([^\]]+)\] (?:line (\d+) )?(.*): (SUCCESS|FAILURE|UNKNOWN|ERROR)$')
RE_NOBODY = re.compile(r'no body for (?:function|callee) (\S+)')


def parse_cbmc(text):
    props = []
    for line in text.split('\n'):
        m = RE_RESULT.match(line.strip())
        if m:
            props.append({'id': m.group(1), 'line': int(m.group(2)) if m.group(2) else None,
                          'desc': m.group(3), 'status': m.group(4)})
    verdict = None
    if 'VERIFICATION SUCCESSFUL' in text:
        verdict = 'SUCCESSFUL'
    elif 'VERIFICATION FAILED' in text:
        verdict = 'FAILED'
    elif 'VERIFICATION ERROR' in text:
        verdict = 'ERROR'
    nobody = sorted(set(RE_NOBODY.findall(text)))
    return props, verdict, nobody


def parse_show_properties(text):
    """Return [(id, description)] from cbmc --show-properties output."""
    out = []
    cur = None
    for line in text.split('\n'):
        m = re.match(r'^Property (\S+):$', line.strip())
        if m:
            cur = [m.group(1), []]
            out.append(cur)
        elif cur is not None and line.startswith('  '):
            cur[1].append(line.strip())
    return [(i, ' '.join(d)) for i, d in out]


# ---------------------------------------------------------------- build

def goto_type(t):
    """A goto type as a comparable string (structure and widths; the JSON carries no qualifiers or C names)."""
    ns = t.get('namedSub') or {}
    i = t.get('id')
    if i in ('unsignedbv', 'signedbv', 'floatbv', 'fixedbv', 'c_bool', 'bv'):
        return '%s[%s]' % (i, (ns.get('width') or {}).get('id'))
    if i == 'pointer':
        return goto_type(t['sub'][0]) + '*'
    if i == 'array':
        return goto_type(t['sub'][0]) + '[]'
    if i in ('struct_tag', 'union_tag', 'c_enum_tag'):
        return '%s %s' % (i, (ns.get('identifier') or {}).get('id'))
    if i == 'code':
        return 'code'
    return i or '?'


def _strip_casts(e):
    while e.get('id') == 'typecast':
        e = e['sub'][0]
    return e


def _etype(e):
    return goto_type((e.get('namedSub') or {}).get('type') or {})


def _name(e):
    return ((e.get('namedSub') or {}).get('identifier') or {}).get('id', '?').split('::')[-1]


def arg_type_problem(arg, ptype):
    """None if a card-call argument has the parameter's type before any cast, else why not. The forms are scan's
    (x, &x, p + k), as goto-cc writes them: a symbol; address_of a symbol, or of element 0 of an array (decay);
    and p + k, where p must have the parameter's type and k be size_t, the unsigned type of p's pointer width."""
    e = _strip_casts(arg)
    i = e.get('id')
    if i == 'symbol' or (i == 'address_of' and _strip_casts(e['sub'][0]).get('id') in ('symbol', 'index')):
        if i == 'address_of' and e['sub'][0].get('id') == 'index':
            ix = e['sub'][0]
            if ix['sub'][0].get('id') != 'symbol' or ix['sub'][1].get('id') != 'constant':
                return 'an element address that is not an array\'s start'
            shown = _name(ix['sub'][0])
        else:
            shown = _name(e if i == 'symbol' else e['sub'][0])
        if _etype(e) != ptype:
            return '%s has type %s before any cast; the parameter has %s' % (shown, _etype(e), ptype)
        return None
    if i == '+' and len(e.get('sub', [])) == 2:
        x, y = _strip_casts(e['sub'][0]), _strip_casts(e['sub'][1])
        if x.get('id') != 'symbol' or y.get('id') != 'symbol':
            return 'p + k with an operand that is not a variable'
        if _etype(x) != ptype:
            return '%s has type %s before any cast; the parameter has %s' % (_name(x), _etype(x), ptype)
        width = ((((x.get('namedSub') or {}).get('type') or {}).get('namedSub') or {}).get('width') or {}).get('id')
        size_t = 'unsignedbv[%s]' % width
        if not width or _etype(y) != size_t:
            return 'the offset %s has type %s; it must be size_t (%s)' % (_name(y), _etype(y), size_t)
        return None
    return 'an argument of the form %s, not x, &x or p + k' % i


def card_call_type_problems(funcs_json, entry, funcs, required=()):
    """From goto-instrument --show-goto-functions --json-ui on the linked program (before DFCC): for each call in
    `entry` to one of `funcs` (sqlite3.c macros are already expanded to their calls), each argument whose type before
    any cast is not the parameter's. size_t is the unsigned type of pointer width. Also a problem (auditor
    2026-11-09 night): an entry with no checked call to each of `required` (the proof's ENFORCE function), or, for a
    proof without one, no checked card call at all, so the check cannot pass by finding nothing."""
    data = json.loads(funcs_json, strict=False)
    fns = next((x['functions'] for x in data if isinstance(x, dict) and 'functions' in x), None)
    if fns is None:
        return ['goto-instrument printed no functions']
    body = next((f for f in fns if f.get('name') == entry), None)
    if body is None:
        return ['entry function %s is not in the goto program' % entry]
    probs, calls, checked = [], 0, set()
    for ins in body.get('instructions', []):
        if ins.get('instructionId') != 'FUNCTION_CALL':
            continue
        sub = ins['code']['sub']
        callee, args = sub[1], (sub[2].get('sub') or [])
        line = (ins.get('sourceLocation') or {}).get('line', '?')
        if callee.get('id') != 'symbol':
            probs.append('line %s: a call through a function pointer in %s' % (line, entry))
            continue
        fn = _name(callee)
        if fn not in funcs:
            continue
        calls += 1
        checked.add(fn)
        params = [goto_type(q['namedSub']['type']) for q in
                  ((callee['namedSub']['type'].get('namedSub') or {}).get('parameters') or {}).get('sub', [])]
        if len(params) != len(args):
            probs.append('line %s: %s takes %d arguments, called with %d' % (line, fn, len(params), len(args)))
            continue
        for k, (a, pt) in enumerate(zip(args, params)):
            why = arg_type_problem(a, pt)
            if why:
                probs.append('line %s: argument %d of %s: %s (a narrower declared type narrows the input)' % (
                    line, k + 1, fn, why))
    for fn in sorted(set(required) - checked):
        probs.append('%s makes no direct call to %s, the function under proof, so no argument of it was checked' % (
            entry, fn))
    if not required and not calls:
        probs.append('%s makes no direct call to a card function (%s), so no argument was checked' % (
            entry, ', '.join(sorted(funcs))))
    return probs


def card_functions(card_dir, proof):
    """The card's functions (cards/C-NN.md), with the proof's ENFORCE and COVER functions."""
    out = set(proof.enforced) | set(proof.cover)
    try:
        out |= set(cardlib.load(ROOT, os.path.basename(os.path.normpath(card_dir))).functions)
    except Exception:   # no cards/ (a tool-test fixture): the Makefile's functions only
        pass
    return out


def card_unreached(card_dir):
    """The card's unreached callees (cards/C-NN.md); none for a tool-test fixture without cards/."""
    path = os.path.join(ROOT, 'cards', os.path.basename(os.path.normpath(card_dir)) + '.md')
    if not os.path.exists(path):
        return []
    return cardlib.load(ROOT, os.path.basename(os.path.normpath(card_dir))).unreached_callees


def bodies_to_remove(card_dir, proof):
    """Functions whose bodies build_proof removes before drop-unused: REPLACE functions and unreached callees."""
    out = set(p.split('/')[0] for p in proof.replace) | set(card_unreached(card_dir))
    clash = sorted(out & (set(proof.enforced) | set(proof.cover)))
    if clash:
        raise CardError('%s: %s would lose its body but is enforced or covered' % (proof.name, ', '.join(clash)))
    return sorted(out)


def build_proof(card_dir, proof, cfg_name, cfg_flags, overlay_dir, bdir, log):
    """Build the instrumented goto program for one proof and config. Returns (path, error)."""
    os.makedirs(bdir, exist_ok=True)
    hp = header_clause_problems()
    if hp:
        return None, '; '.join(hp)
    obj = os.path.join(bdir, 'harness.o.goto')
    harness = os.path.join(card_dir, 'harness.c')
    stamp = os.path.join(bdir, 'harness.o.stamp')
    key = json.dumps([cfg_flags, os.path.abspath(overlay_dir), _mtimes(card_dir, overlay_dir)])
    if proof.uses_legacy():
        try:
            src = legacy_source(card_dir, proof)
        except (CardError, OSError) as e:
            return None, str(e)
        harness = os.path.join(bdir, proof.name + '.legacy.c')
        with open(harness, 'w') as f:
            f.write(src)
        obj = os.path.join(bdir, proof.name + '.legacy.o.goto')
        stamp = os.path.join(bdir, proof.name + '.legacy.o.stamp')
        key = json.dumps([cfg_flags, os.path.abspath(overlay_dir), _mtimes(card_dir, overlay_dir), src])
    if not (os.path.exists(obj) and os.path.exists(stamp) and open(stamp).read() == key):
        cmd = ['goto-cc'] + cfg_flags + ['-include', os.path.join(ROOT, 'proofs', 'include', 'proof.h'),
                                         '-I', overlay_dir, '-I', os.path.join(ROOT, 'proofs', 'include'),
                                         '-I', os.path.join(ROOT, 'proofs'), '-c', harness, '-o', obj]
        rc, _ = run(cmd, log + '.goto-cc', timeout=900)
        if rc != 0:
            return None, 'goto-cc failed (%s); see %s' % (rc, log + '.goto-cc')
        with open(stamp, 'w') as f:
            f.write(key)
    p0 = os.path.join(bdir, proof.name + '.0.goto')
    steps = [(['goto-cc', '--function', proof.entry, obj, '-o', p0], 'link')]
    try:
        nobody = bodies_to_remove(card_dir, proof)
    except (CardError, cardlib.CardFormatError) as e:
        return None, str(e)
    if nobody:
        p0b = os.path.join(bdir, proof.name + '.0b.goto')
        cmd = ['goto-instrument']
        for f in nobody:
            cmd += ['--remove-function-body', f]
        steps.append((cmd + [p0, p0b], 'remove-bodies'))
    else:
        p0b = p0
    p1 = os.path.join(bdir, proof.name + '.1.goto')
    steps.append((['goto-instrument', '--drop-unused-functions', p0b, p1], 'drop-unused'))
    for cmd, tag in steps:
        rc, _ = run(cmd, log + '.' + tag, timeout=900)
        if rc != 0:
            return None, '%s failed (%s); see %s' % (tag, rc, log + '.' + tag)
    steps = []
    # auditor 2026-11-09 evening: each card-call argument has its parameter's type before any cast
    fj = os.path.join(bdir, proof.name + '.functions.json')
    rc, _ = run(['goto-instrument', '--show-goto-functions', '--json-ui', p1], log + '.arg-types', timeout=900,
                stdout_path=fj)
    if rc != 0:
        return None, 'goto-instrument --show-goto-functions failed (%s); see %s' % (rc, log + '.arg-types')
    try:
        probs = card_call_type_problems(open(fj, errors='replace').read(), proof.entry, card_functions(card_dir, proof),
                                        proof.enforced)
    except (ValueError, KeyError, IndexError, TypeError) as e:
        probs = ['could not read the goto program\'s calls: %s: %s' % (type(e).__name__, e)]
    finally:
        os.remove(fj)
    if probs:
        with open(log + '.arg-types', 'a') as f:
            f.write('\n'.join(probs) + '\n')
        return None, 'card-call argument types: ' + '; '.join(probs)
    cur = p1
    if proof.uses_dfcc():
        p2 = os.path.join(bdir, proof.name + '.2.goto')
        cmd = ['goto-instrument', '--dfcc', proof.entry]
        for e in proof.enforce:
            cmd += ['--enforce-contract', e]
        for r in proof.replace:
            cmd += ['--replace-call-with-contract', r]
        if proof.loops == 'contracts':
            cmd += ['--apply-loop-contracts']
        cmd += [cur, p2]
        steps.append((cmd, 'dfcc'))
        cur = p2
    elif proof.uses_legacy():
        # replace, then loops, then enforce: the order the callee-frame toy requires (T-006)
        passes = [('legacy-replace', sum([['--replace-call-with-contract', r.split('/')[0]] for r in proof.replace], [])),
                  ('legacy-loops', ['--apply-loop-contracts'] if proof.loops == 'contracts' else []),
                  ('legacy-enforce', sum([['--enforce-contract', e.split('/')[0]] for e in proof.enforce], []))]
        for k, (tag, opts) in enumerate(p for p in passes if p[1]):
            nxt = os.path.join(bdir, proof.name + '.2%s.goto' % 'abc'[k])
            steps.append((['goto-instrument'] + opts + [cur, nxt], tag))
            cur = nxt
    p3 = os.path.join(bdir, proof.name + '.goto')
    steps.append((['goto-instrument', '--slice-global-inits', cur, p3], 'slice-global-inits'))
    for cmd, tag in steps:
        rc, _ = run(cmd, log + '.' + tag, timeout=900)
        if rc != 0:
            hint = ''
            if tag.startswith('legacy-') and LEGACY_STATIC_ABORT in open(log + '.' + tag, errors='replace').read():
                hint = (' (T-012: the legacy engine aborts when a replaced callee has a static local; keep that callee\'s '
                        'body, that is, leave it off REPLACE)')
            return None, '%s failed (%s); see %s%s' % (tag, rc, log + '.' + tag, hint)
    for f in (p0, p0b, p1, os.path.join(bdir, proof.name + '.2.goto')) + tuple(
            os.path.join(bdir, proof.name + '.2%s.goto' % x) for x in 'abc'):
        if os.path.exists(f):
            os.remove(f)
    return p3, None


def _mtimes(card_dir, overlay_dir):
    paths = [os.path.join(card_dir, 'harness.c'), os.path.join(overlay_dir, 'sqlite3.c')]
    for sub in ('proofs/include', 'proofs/contracts', 'proofs/spec'):
        d = os.path.join(ROOT, sub)
        if os.path.isdir(d):
            for n in sorted(os.listdir(d)):
                paths.append(os.path.join(d, n))
    out = []
    for p in paths:
        try:
            st = os.stat(p)
            out.append([p, st.st_mtime_ns, st.st_size])
        except FileNotFoundError:
            out.append([p, None])
    return out


def cbmc_base(proof, goto, checks, drop_unwinding_assertions=False):
    cmd = ['cbmc', goto] + [c for c in checks if not (drop_unwinding_assertions and c == '--unwinding-assertions')]
    if proof.unwindset:
        cmd += ['--unwindset', proof.unwindset]
    if proof.solver:
        cmd += proof.solver.split()
    if proof.object_bits:
        cmd += ['--object-bits', proof.object_bits]
    return cmd


# ---------------------------------------------------------------- prove

def prove_one(card, card_dir, proof, cfg_name, cfg_flags, overlay_dir, build_root, timeout, trace):
    bdir = os.path.join(build_root, cfg_name)
    os.makedirs(bdir, exist_ok=True)
    log = os.path.join(bdir, proof.name)
    res = {'card': card, 'proof': proof.name, 'config': cfg_name, 'status': 'FAIL', 'seconds': 0,
           'properties': 0, 'failed': 0, 'failures': [], 'error': None, 'float_to_int_properties': 0}
    t0 = time.time()
    goto, err = build_proof(card_dir, proof, cfg_name, cfg_flags, overlay_dir, bdir, log)
    if err:
        res['error'] = err
        res['seconds'] = round(time.time() - t0)
        return res
    checks, f2i = read_checks()
    cmd = cbmc_base(proof, goto, checks)
    if trace:
        cmd.append('--trace')
    rc, secs = run(cmd, log + '.cbmc', timeout=timeout)
    text = open(log + '.cbmc', errors='replace').read()
    props, verdict, nobody = parse_cbmc(text)
    res['properties'] = len(props)
    res['failures'] = [p for p in props if p['status'] != 'SUCCESS']
    if rc == 'timeout':
        res['error'] = 'cbmc timed out after %ds; see %s' % (timeout, log + '.cbmc')
    elif verdict is None:
        res['error'] = 'cbmc gave no verdict (rc %s); see %s' % (rc, log + '.cbmc')
    elif verdict == 'ERROR':
        res['error'] = 'cbmc VERIFICATION ERROR; see %s' % (log + '.cbmc')
    if nobody:
        res['error'] = (res['error'] + '; ' if res['error'] else '') + \
            'functions without a body are called (unconstrained): ' + ', '.join(nobody)
    # float-to-integer pass
    if f2i and not res['error']:
        opt, pat = f2i
        rx = re.compile(pat)
        rc2, _ = run(cbmc_base(proof, goto, checks) + [opt, '--show-properties'], log + '.f2i-show', timeout=timeout)
        ids = [i for i, d in parse_show_properties(open(log + '.f2i-show', errors='replace').read()) if rx.search(d)]
        res['float_to_int_properties'] = len(ids)
        if rc2 != 0:
            res['error'] = 'float-to-int --show-properties failed (%s); see %s' % (rc2, log + '.f2i-show')
        elif ids:
            cmd2 = cbmc_base(proof, goto, checks) + [opt]
            for i in ids:
                cmd2 += ['--property', i]
            if trace:
                cmd2.append('--trace')
            rc3, s3 = run(cmd2, log + '.f2i', timeout=timeout)
            secs += s3
            t2 = open(log + '.f2i', errors='replace').read()
            p2, v2, _ = parse_cbmc(t2)
            res['properties'] += len(p2)
            res['failures'] += [p for p in p2 if p['status'] != 'SUCCESS']
            if rc3 == 'timeout' or v2 not in ('SUCCESSFUL', 'FAILED'):
                res['error'] = 'float-to-int pass gave no verdict (%s); see %s' % (rc3, log + '.f2i')
    res['failed'] = len(res['failures'])
    res['seconds'] = round(time.time() - t0)
    res['cbmc_seconds'] = round(secs)
    if not res['error'] and res['failed'] == 0 and verdict == 'SUCCESSFUL':
        res['status'] = 'PASS'
    with open(log + '.json', 'w') as f:
        json.dump(res, f, indent=1)
    return res


def select_configs(config):
    cfgs = read_configs()
    if config in (None, '', 'all'):
        return cfgs
    sel = [c for c in cfgs if c[0] == config]
    if not sel:
        raise CardError('unknown CONFIG %r; proofs/CONFIGS has %s' % (config, ', '.join(c[0] for c in cfgs)))
    return sel


def cmd_prove(a):
    card_dir = os.path.abspath(a.card_dir)
    try:
        card, proofs = load_card(card_dir)
        cfgs = select_configs(a.config)
    except (CardError, OSError) as e:
        print('prove: %s' % e)
        print('RESULT prove %s %s FAIL 0s 0 properties 0 failed' % (os.path.basename(card_dir), a.config or 'all'))
        return 1
    build_root = a.build_dir or os.path.join(card_dir, 'build')
    overlay_dir = os.path.abspath(a.overlay or os.path.join(ROOT, 'overlay'))
    total = {'s': 0, 'p': 0, 'f': 0, 'ok': True}
    summary = []
    for cname, cflags in cfgs:
        cs = {'s': 0, 'p': 0, 'f': 0, 'ok': True}
        for proof in proofs:
            r = prove_one(card, card_dir, proof, cname, cflags, overlay_dir, build_root, a.timeout, a.trace)
            summary.append(r)
            for fl in r['failures'][:20]:
                print('  FAILED %s %s [%s] line %s %s' % (proof.name, cname, fl['id'], fl['line'], fl['desc']))
            if r['error']:
                print('  ERROR %s %s: %s' % (proof.name, cname, r['error']))
            print('RESULT prove %s/%s %s %s %ds %d properties %d failed' % (
                card, proof.name, cname, r['status'], r['seconds'], r['properties'], r['failed']))
            sys.stdout.flush()
            cs['s'] += r['seconds']
            cs['p'] += r['properties']
            cs['f'] += r['failed']
            cs['ok'] = cs['ok'] and r['status'] == 'PASS'
        if len(cfgs) > 1:
            print('RESULT prove %s %s %s %ds %d properties %d failed' % (
                card, cname, 'PASS' if cs['ok'] else 'FAIL', cs['s'], cs['p'], cs['f']))
        for k in ('s', 'p', 'f'):
            total[k] += cs[k]
        total['ok'] = total['ok'] and cs['ok']
    with open(os.path.join(build_root, 'prove-summary.json'), 'w') as f:
        json.dump(summary, f, indent=1)
    label = cfgs[0][0] if len(cfgs) == 1 else 'all'
    print('RESULT prove %s %s %s %ds %d properties %d failed' % (
        card, label, 'PASS' if total['ok'] else 'FAIL', total['s'], total['p'], total['f']))
    return 0 if total['ok'] else 1


# ---------------------------------------------------------------- coverage

RE_COVER = re.compile(r'^\[([^\]]+)\] file (\S+) line (\d+) function (\S+) block (\d+) \(lines (.*)\): (SATISFIED|FAILED)$')


def parse_cover(text, overlay_path):
    """Return list of (function, set(overlay lines), satisfied) for blocks in overlay_path."""
    out = []
    base = os.path.basename(overlay_path)
    for line in text.split('\n'):
        m = RE_COVER.match(line.strip())
        if not m:
            continue
        fn = m.group(4)
        sat = m.group(7) == 'SATISFIED'
        lines = set()
        for part in m.group(6).split(';'):
            part = part.strip()
            fm = re.match(r'^(.*):([^:]*):([0-9,\- ]+)$', part)
            if not fm:
                continue
            if os.path.basename(fm.group(1)) != base:
                continue
            for rng in fm.group(3).split(','):
                rng = rng.strip()
                if '-' in rng:
                    lo, hi = rng.split('-')
                    lines.update(range(int(lo), int(hi) + 1))
                elif rng:
                    lines.add(int(rng))
        if lines:
            out.append((fn, lines, sat))
    return out


def cover_one(card, card_dir, proof, cfg_name, cfg_flags, overlay_dir, build_root, timeout):
    bdir = os.path.join(build_root, cfg_name)
    log = os.path.join(bdir, proof.name + '.cover')
    res = {'card': card, 'proof': proof.name, 'config': cfg_name, 'functions': {}, 'error': None}
    goto, err = build_proof(card_dir, proof, cfg_name, cfg_flags, overlay_dir, bdir, log)
    if err:
        res['error'] = err
        return res
    checks, _ = read_checks()
    cmd = cbmc_base(proof, goto, checks, drop_unwinding_assertions=True) + ['--cover', 'location']
    rc, secs = run(cmd, log + '.cbmc', timeout=timeout)
    text = open(log + '.cbmc', errors='replace').read()
    if rc == 'timeout' or '** coverage results' not in text and 'coverage results' not in text:
        res['error'] = 'coverage run gave no results (%s); see %s' % (rc, log + '.cbmc')
        return res
    ovpath = os.path.join(overlay_dir, 'sqlite3.c')
    lm = ov.LineMap(open(ovpath, 'rb').read())
    blocks = parse_cover(text, ovpath)
    for fn in proof.cover:
        body = fn + '_wrapped_for_contract_checking' if fn in proof.enforced else fn
        mine = [(l, s) for f, l, s in blocks if f == body]
        all_lines, unc = set(), set()
        for l, s in mine:
            all_lines |= l
            if not s:
                unc |= l
        res['functions'][fn] = {
            'goal_lines': sorted(lm.upstream_line(x) for x in all_lines),
            'uncovered': sorted(set(lm.upstream_line(x) for x in unc)),
            'uncovered_blocks': uncovered_regions(sorted(set(lm.upstream_line(x) for x in all_lines)),
                                                  set(lm.upstream_line(x) for x in unc)),
            'blocks': len(mine), 'blocks_failed': sum(1 for _, s in mine if not s)}
        if not mine:
            res['error'] = 'no coverage goals found for %s (is it reached? is the name right?)' % fn
    res['seconds'] = round(secs)
    with open(log + '.json', 'w') as f:
        json.dump(res, f, indent=1)
    return res


def uncovered_regions(goal_lines, uncovered):
    """The function's uncovered blocks at source level. `cbmc --cover location` reports one goal per instruction,
    with overlapping line sets, so a straight-line stretch of dead code is several goals. A block here is a maximal
    run of uncovered goal lines with no covered goal line between them."""
    out, cur = [], []
    for x in goal_lines:
        if x in uncovered:
            cur.append(x)
        elif cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


RE_UNREACHED = re.compile(r'^\s*[-*]\s+sqlite3\.c:(\d+)(?:-(\d+))?(?::|\s+[\u2014\u2013-])\s*(\S.*)$')


def unreached_entries(card_dir):
    """The entries under the heading "## Unreached lines" in NOTES.md, up to the next heading (checkpoint 0, decision
    C3 and follow-up 3). Each non-blank line there is one entry, `- sqlite3.c:<line>: <reason>` or
    `- sqlite3.c:<a>-<b>: <reason>`, or the single line `- none`. Returns (entries, problems), each entry
    (notes line number, lo, hi, text). A line cited anywhere else in NOTES.md explains nothing."""
    p = os.path.join(card_dir, 'NOTES.md')
    if not os.path.exists(p):
        return [], []
    entries, probs, inside = [], [], False
    for n, line in enumerate(open(p, errors='replace'), 1):
        h = re.match(r'^\s*#+\s*(.*?)\s*#*\s*$', line)
        if h:
            inside = re.match(r'(?i)^unreached lines\b', h.group(1)) is not None
            continue
        t = line.strip()
        if not inside or not t or re.fullmatch(r'(?i)[-*]?\s*none\.?', t):
            continue
        m = RE_UNREACHED.match(line)
        if not m:
            probs.append('NOTES.md:%d: not an entry; write one line or range per entry, then its reason: '
                         '"- sqlite3.c:<line>: <reason>": %s' % (n, t[:80]))
            continue
        lo, hi, why = int(m.group(1)), int(m.group(2) or m.group(1)), m.group(3).strip()
        if hi < lo:
            probs.append('NOTES.md:%d: range %d-%d runs backwards' % (n, lo, hi))
        elif 'sqlite3.c:' in why:
            probs.append('NOTES.md:%d: one line or range per entry (this one names more): %s' % (n, t[:80]))
        elif not re.search(r'[A-Za-z]{3}', why):
            probs.append('NOTES.md:%d: the entry for sqlite3.c:%s gives no reason' % (n, m.group(0).split('sqlite3.c:')[1].split(':')[0]))
        else:
            entries.append((n, lo, hi, t))
    return entries, probs


def check_unreached(entries, blocks):
    """Which entries the run supports. blocks: the uncovered blocks (uncovered_regions) of every proof,
    configuration and function in this run, each a list of upstream lines. A single line must be in an uncovered block; a range must lie within
    one uncovered block, both ends in it. An entry naming a line this run covers, or no coverage goal at all,
    fails. Returns (explained lines, problems)."""
    unc = set(x for b in blocks for x in b)
    explained, probs = set(), []
    for n, lo, hi, t in entries:
        if lo == hi:
            if lo in unc:
                explained.add(lo)
            else:
                probs.append('NOTES.md:%d: sqlite3.c:%d is listed as unreached, but no proof or configuration in this '
                             'run leaves it uncovered' % (n, lo))
            continue
        if any(lo in b and hi in b and min(b) <= lo and hi <= max(b) for b in blocks):
            explained.update(x for x in range(lo, hi + 1) if x in unc)
        else:
            covered = sorted(x for x in range(lo, hi + 1) if x not in unc)
            probs.append('NOTES.md:%d: sqlite3.c:%d-%d is not within one uncovered block of this run%s' % (
                n, lo, hi, (' (it includes lines the run covers or that are no coverage goal, e.g. %s)' %
                            ', '.join(map(str, covered[:5]))) if covered else ''))
    return explained, probs


def cmd_coverage(a):
    card_dir = os.path.abspath(a.card_dir)
    try:
        card, proofs = load_card(card_dir)
        cfgs = select_configs(a.config)
    except (CardError, OSError) as e:
        print('coverage: %s' % e)
        print('RESULT coverage %s %s FAIL' % (os.path.basename(card_dir), a.config or 'all'))
        return 1
    build_root = a.build_dir or os.path.join(card_dir, 'build')
    overlay_dir = os.path.abspath(a.overlay or os.path.join(ROOT, 'overlay'))
    entries, entry_probs = unreached_entries(card_dir)
    ok = True
    tot_goal, tot_unc, tot_unexpl = 0, 0, 0
    allres = []
    for cname, cflags in cfgs:
        for proof in proofs:
            r = cover_one(card, card_dir, proof, cname, cflags, overlay_dir, build_root, a.timeout)
            allres.append(r)
            if r['error']:
                print('  ERROR %s %s: %s' % (proof.name, cname, r['error']))
                ok = False
    blocks = [b for r in allres for d in r['functions'].values() for b in d.get('uncovered_blocks', [])]
    explained, check_probs = check_unreached(entries, blocks)
    for pr in entry_probs + check_probs:
        print('  coverage: %s' % pr)
        ok = False
    for r in allres:
        for fn, d in r['functions'].items():
            unexpl = [x for x in d['uncovered'] if x not in explained]
            tot_goal += len(set(d['goal_lines']))
            tot_unc += len(d['uncovered'])
            tot_unexpl += len(unexpl)
            print('  coverage %s %s %s: %d/%d lines; uncovered %s%s' % (
                r['proof'], r['config'], fn, len(set(d['goal_lines'])) - len(d['uncovered']), len(set(d['goal_lines'])),
                ', '.join('sqlite3.c:%d' % x for x in d['uncovered']) or 'none',
                ('; NOT EXPLAINED under "## Unreached lines" in NOTES.md: ' + ', '.join('sqlite3.c:%d' % x for x in unexpl)) if unexpl else ''))
            if unexpl:
                ok = False
    os.makedirs(build_root, exist_ok=True)
    with open(os.path.join(build_root, 'coverage-summary.json'), 'w') as f:
        json.dump(allres, f, indent=1)
    label = cfgs[0][0] if len(cfgs) == 1 else 'all'
    print('RESULT coverage %s %s %s %d/%d lines %d uncovered %d unexplained' % (
        card, label, 'PASS' if ok else 'FAIL', tot_goal - tot_unc, tot_goal, tot_unc, tot_unexpl))
    return 0 if ok else 1


# ---------------------------------------------------------------- includes

def include_problems(card_dir, cfg_flags, overlay_dir):
    """Preprocess the harness as build_proof compiles it and list every file it pulls in (GCC's linemarkers).
    Allowed: the harness itself, the overlay's sqlite3.c, proofs/include/*.h, proofs/contracts/*.h, proofs/spec/*.h
    and system headers (under /usr/include, /usr/lib/gcc, /usr/local/include). Returns (files, problems)."""
    harness = os.path.join(card_dir, 'harness.c')
    cmd = ['goto-cc'] + cfg_flags + ['-E', '-include', os.path.join(ROOT, 'proofs', 'include', 'proof.h'),
                                     '-I', overlay_dir, '-I', os.path.join(ROOT, 'proofs', 'include'),
                                     '-I', os.path.join(ROOT, 'proofs'), harness]
    p = subprocess.run(['nice', '-n', '10'] + cmd, capture_output=True, text=True, errors='replace')
    if p.returncode != 0:
        return [], ['preprocessing failed: %s' % (p.stderr.strip()[-400:] or p.returncode)]
    files = set()
    for m in re.finditer(r'^#\s*\d+\s+"((?:[^"\\]|\\.)*)"', p.stdout, re.M):
        files.add(m.group(1))
    allowed_dirs = [os.path.join(os.path.realpath(ROOT), 'proofs', d) for d in ('include', 'contracts', 'spec')]
    ok_exact = {os.path.realpath(harness), os.path.realpath(os.path.join(overlay_dir, 'sqlite3.c'))}
    probs = []
    for f in sorted(files):
        if f.startswith('<') and f.endswith('>'):
            continue        # <built-in>, <command-line>
        rp = os.path.realpath(f if os.path.isabs(f) else os.path.join(card_dir, f))
        if rp in ok_exact:
            continue
        if os.path.dirname(rp) in allowed_dirs and rp.endswith('.h'):
            continue
        if any(rp.startswith(d) for d in ('/usr/include/', '/usr/lib/gcc/', '/usr/local/include/')) \
                and not rp.startswith(os.path.realpath(ROOT) + '/'):
            continue
        probs.append('includes %s, which is not the overlay, proofs/{include,contracts,spec}/*.h or a system header' % f)
    return sorted(files), probs


def cmd_includes(a):
    card_dir = os.path.abspath(a.card_dir)
    overlay_dir = os.path.abspath(a.overlay or os.path.join(ROOT, 'overlay'))
    name = os.path.basename(os.path.normpath(card_dir))
    try:
        cfgs = select_configs(a.config)
    except (CardError, OSError) as e:
        print('includes: %s' % e)
        print('RESULT includes %s %s FAIL' % (name, a.config or 'all'))
        return 1
    ok = True
    for cname, cflags in cfgs:
        files, probs = include_problems(card_dir, cflags, overlay_dir)
        for pr in probs:
            print('  includes %s %s: %s' % (name, cname, pr))
        ok = ok and not probs
        print('  includes %s %s: %d files, %d not allowed' % (name, cname, len(files), len(probs)))
    print('RESULT includes %s %s %s' % (name, cfgs[0][0] if len(cfgs) == 1 else 'all', 'PASS' if ok else 'FAIL'))
    return 0 if ok else 1


# ---------------------------------------------------------------- configuration probe

def expectations(name):
    m = re.match(r'^(lp64|ilp32)-(le|be)$', name)
    if not m:
        raise CardError('configuration name %r is not <lp64|ilp32>-<le|be>' % name)
    w = 8 if m.group(1) == 'lp64' else 4
    le = m.group(2) == 'le'
    # -be models 64-bit PowerPC, whose plain char is unsigned; -le models x86 and i386, whose plain char is signed
    return {'EXPECT_PTR': w, 'EXPECT_LONG': w, 'EXPECT_LOW_BYTE': 4 if le else 1,
            'EXPECT_BYTEORDER': 1234 if le else 4321, 'EXPECT_CHAR_UNSIGNED': 0 if le else 1}


def cmd_probe(a):
    """Build tools/probe/config_probe.c against the overlay under each configuration and check
    that word size, byte order and SQLite's byte-order macros are what the name says."""
    overlay_dir = os.path.abspath(a.overlay or os.path.join(ROOT, 'overlay'))
    build_root = a.build_dir or os.path.join(ROOT, 'proofs', 'build', 'probe')
    os.makedirs(build_root, exist_ok=True)
    ok = True
    for cname, cflags in select_configs(a.config):
        exp = expectations(cname)
        bdir = os.path.join(build_root, cname)
        os.makedirs(bdir, exist_ok=True)
        defs = ['-D%s=%d' % kv for kv in sorted(exp.items())]
        g0 = os.path.join(bdir, 'probe.0.goto')
        g1 = os.path.join(bdir, 'probe.1.goto')
        g2 = os.path.join(bdir, 'probe.goto')
        steps = [
            ['goto-cc'] + cflags + ['-include', os.path.join(ROOT, 'proofs', 'include', 'proof.h'), '-I', overlay_dir]
            + defs + ['--function', 'probe', os.path.join(TOOLS, 'probe', 'config_probe.c'), '-o', g0],
            ['goto-instrument', '--drop-unused-functions', g0, g1],
            ['goto-instrument', '--slice-global-inits', g1, g2]]
        err = None
        for i, s in enumerate(steps):
            rc, _ = run(s, os.path.join(bdir, 'step%d.log' % i), timeout=900)
            if rc != 0:
                err = 'step %d failed (%s); see %s' % (i, rc, os.path.join(bdir, 'step%d.log' % i))
                break
        if not err:
            checks, _ = read_checks()
            rc, _ = run(['cbmc', g2] + checks, os.path.join(bdir, 'cbmc.log'), timeout=a.timeout)
            props, verdict, nobody = parse_cbmc(open(os.path.join(bdir, 'cbmc.log')).read())
            asserts = [p for p in props if '.assertion.' in p['id']]
            for p in asserts:
                print('  probe %s: %s: %s' % (cname, p['desc'], p['status']))
            if verdict != 'SUCCESSFUL' or len(asserts) < 9:
                err = 'probe verdict %s with %d assertions' % (verdict, len(asserts))
        if err:
            print('  probe %s: %s' % (cname, err))
            ok = False
        print('RESULT probe %s %s' % (cname, 'FAIL' if err else 'PASS'))
    print('RESULT probe all %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('prove', 'coverage', 'probe', 'includes'):
        s = sub.add_parser(name)
        s.add_argument('--card-dir', default='.')
        s.add_argument('--config', default='all')
        s.add_argument('--overlay', default=None, help='directory holding the sqlite3.c to prove against')
        s.add_argument('--build-dir', default=None)
        s.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT)
        s.add_argument('--trace', action='store_true')
    a = ap.parse_args()
    return {'prove': cmd_prove, 'coverage': cmd_coverage, 'probe': cmd_probe, 'includes': cmd_includes}[a.cmd](a)


if __name__ == '__main__':
    sys.exit(main())
