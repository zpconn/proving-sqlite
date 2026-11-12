#!/usr/bin/env python3
"""scan.py: mechanical rules on proofs (GOAL.md §3.4, agents/builder/GOAL.md §2.7).

Rejects:
  1. any __CPROVER_assume outside a harness's /* SETUP */ ... /* END SETUP */ block, and any assume
     in a setup block that reads data (an array subscript or a unary '*');
  2. any option that turns a check off: proofs/CHECKS must hold every required check and no --no-*
     option; card Makefiles are declarative (tools/prove.py), so they carry no flags; no
     `#pragma CPROVER` or `_Pragma` anywhere;
  3. any compile flag beyond proofs/CONFIGS: a harness's first line must be `#include "sqlite3.c"`,
     so nothing is #defined before SQLite is compiled;
  4. unwinding without unwinding assertions (CHECKS must hold --unwinding-assertions);
  5. a boundary contract (for a function no card proves) that doesn't name its ledger entry
     (`Ledger: A-NNN`, which must exist in LEDGER.md once LEDGER.md exists), or, when that entry gives its
     clause as a ~~~ block, isn't that clause word for word (comments and spacing aside); and a ~~~ clause
     in LEDGER.md for a function no card proves with no proofs/contracts/<fn>.h (checkpoint 1, D2);
  6. a harness, predicate or contract file that defines a function SQLite's code names, or any
     function named __CPROVER_*;
  7. PROOF spans anywhere but between a loop's header and body (for/while: after the condition's ')';
     do-while: after `do`), outside the functions its card names, or holding anything but
     __CPROVER_assigns(...) __CPROVER_loop_invariant(...)... __CPROVER_decreases(...), in that order;
  8. contracts used by REPLACE that are not in proofs/contracts/<fn>.h, or contract_<fn> declared
     anywhere else; for an in-scope callee, no card ENFORCEs it;
  9. zero-filling tricks in harnesses and predicates: calloc, memset, `= {` initializers, and
     file-scope object definitions (static storage is zero-initialized);
 10. (checkpoint 0, decision C) functions that end or redirect a path, which hides it from every later check as an
     assume would: abort, exit, _Exit, longjmp and their kin, __VERIFIER_*, and __CPROVER_array_set,
     __CPROVER_array_replace and __CPROVER_array_copy, which write bytes wholesale; in harnesses, predicates,
     specs and contracts;
 11. in each harness entry function (a proof's ENTRY): return or goto; anything but exactly one SETUP block;
     statements before it other than declarations; in it, anything but declarations, __CPROVER_assume of
     primitives, allocations and field or pointer assignments that read no data; and a call under proof (the
     ENFORCE function, else the first call to a card function) that comes before END SETUP, is missing, or
     sits inside a condition or loop, which would hide the inputs that skip it. SETUP blocks outside entry
     functions. (Checkpoint 0 follow-up 2:) between END SETUP and the call under proof, anything but
     declarations and snapshots (no stores through pointers or subscripts, assignments, calls or control flow).
     A snapshot is exactly `S[k] = X[k];` with a constant k, or the whole body of
     `for(i = <const>; i < <const>; ++i)` as `S[i] = X[i]`, no braces, where S is an array declared once in the
     entry function (not a pointer, not static, no initializer), i a plain local declared there and used by no
     other snapshot loop, and neither appears in the call's statement or in SETUP; in SETUP,
     taking an address, `->` but in `p->field = value`, string literals, casts to pointer types but on malloc,
     naming a local array outside sizeof, and a data pointer assigned anything but a malloc result, pointer
     arithmetic on one, or 0; anywhere in a harness, any preprocessor directive but #include (so no macro hides a
     statement from these rules), line splices, digraphs and trigraphs, loop and function contract clauses
     (PROOF included), __builtin_* outside HARNESS_BUILTINS, __attribute__ and asm. (Auditor recheck item 1:)
     every call in an entry function to a card function (or ENFORCEd one), or to a sqlite3.c function-like macro
     that expands to one, takes only `id`, `&id` or `x + y` (x a data pointer, y another identifier) as each
     argument, every name in it a local variable the entry function declares before or in SETUP (and an entry
     function declares nothing static, extern or thread-local, and its declarations name no macro that sqlite3.c,
     proof.h or an included header #defines: only C keywords and typedef names), so any narrowing of the inputs
     sits in SETUP, where the reviewer checks it; such a name used other than as a call, or named outside an
     entry function (a helper or file scope), fails too;
 12. files in proofs/C-NN/ but harness.c, Makefile, NOTES.md and the ignored build/ directory; files in
     overlay/ but sqlite3.c; files in proofs/include/ but proof.h and preds.h; symlinks anywhere under
     proofs/, overlay/ or tests/repro/; preprocessor directives a harness or header has no use for
     (#import, #embed, #line, any #pragma but once);
 13. with --base: a change to proofs/include/preds.h that removes or alters anything it held (it may only
     gain predicates);
 14. a card whose functions are not all in some proof's COVER (coverage would not look at them);
 15. (checkpoint 0 follow-up 4) in proofs/include/preds.h, proofs/contracts/ and proofs/spec/, any #define but
     the include guard (`#ifndef G` first, then `#define G`, G all-caps ending in _H and unused by sqlite3.c)
     and any #undef: a macro could change an existing predicate's or SQLite name's meaning while rule 13 still
     sees every item preds.h held.

Usage: tools/scan.py [--root DIR] [--card C-NN [--base REF]] [--overlay FILE]
  --card limits the harness rules to one card and, with --base, requires every PROOF span that
  differs from REF to lie in that card's functions.
Ends with: RESULT scan PASS|FAIL <n> problems
"""
import argparse
import os
import re
import subprocess
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import cards as cardlib  # noqa: E402
import overlay as ov  # noqa: E402
import prove  # noqa: E402

REQUIRED_CHECKS = ['--bounds-check', '--pointer-check', '--pointer-overflow-check', '--pointer-primitive-check',
                   '--signed-overflow-check', '--undefined-shift-check', '--div-by-zero-check',
                   '--float-div-by-zero-check', '--malloc-may-fail', '--malloc-fail-null', '--unwinding-assertions']
FORBIDDEN_OPTION_RX = re.compile(r'--no-[a-z-]+|--malloc-fail-assert|--partial-loops|--unwinding-assertions=false'
                                 r'|--property\b|--cover\b|--assume\b|--nondet-static')
LOOP_FUNCS = {'__CPROVER_loop_entry', '__CPROVER_forall', '__CPROVER_exists', '__CPROVER_object_whole',
              '__CPROVER_object_from', '__CPROVER_object_upto', '__CPROVER_r_ok', '__CPROVER_w_ok',
              '__CPROVER_rw_ok', '__CPROVER_same_object', '__CPROVER_POINTER_OFFSET', '__CPROVER_POINTER_OBJECT',
              '__CPROVER_OBJECT_SIZE', '__CPROVER_typed_target', 'sizeof'}
C_KEYWORDS = {'if', 'while', 'for', 'switch', 'return', 'sizeof', 'do', 'else', 'case', 'goto'}
# Rule 10: names that end a path (an assume by another name) or overwrite bytes wholesale. Matched as identifiers,
# not only calls, so a function pointer to one is caught too.
PATH_ENDERS = ['abort', 'exit', '_Exit', '_exit', 'quick_exit', 'at_quick_exit', 'atexit', 'longjmp', 'siglongjmp',
               '_longjmp', '__builtin_longjmp', 'setjmp', 'sigsetjmp', '_setjmp', '__builtin_setjmp', 'thrd_exit',
               'pthread_exit', '__builtin_trap', '__builtin_unreachable', '__CPROVER_array_set',
               '__CPROVER_array_replace', '__CPROVER_array_copy', '__CPROVER_havoc_object', '__CPROVER_havoc_slice']
PATH_ENDERS_RX = re.compile(r'\b(%s|__VERIFIER_[A-Za-z0-9_]*)\b' % '|'.join(re.escape(x) for x in PATH_ENDERS))
# Rule 11: calls a SETUP statement may make
SETUP_CALLS = {'malloc', 'sizeof', '__CPROVER_assume', '__CPROVER_r_ok', '__CPROVER_w_ok', '__CPROVER_rw_ok',
               '__CPROVER_same_object', '__CPROVER_POINTER_OFFSET', '__CPROVER_POINTER_OBJECT', '__CPROVER_OBJECT_SIZE'}
DEREF_RX = re.compile(r'(^|[(,!=<>&|?:~+\-])\s*\*')
# Rule 11 (checkpoint 0 follow-up 2): what a harness may not hold anywhere
HARNESS_BUILTINS = {'__builtin_expect', '__builtin_offsetof', '__builtin_clz', '__builtin_clzl', '__builtin_clzll',
                    '__builtin_ctz', '__builtin_ctzl', '__builtin_ctzll', '__builtin_popcount', '__builtin_popcountl',
                    '__builtin_popcountll', '__builtin_bswap16', '__builtin_bswap32', '__builtin_bswap64'}
CONTRACT_CLAUSE_RX = re.compile(r'\b(__CPROVER_(?:loop_invariant|decreases|assigns|frees|loop_entry|requires|ensures)'
                                r'|PROOF(?=\s*\())')
PTR_CAST_RX = re.compile(r'\(\s*(?:(?:const|volatile|struct|union|enum|unsigned|signed)\s+)*[A-Za-z_]\w*'
                         r'(?:\s+[A-Za-z_]\w*)*[\s*]*\*[\s*]*\)')
LHS_ARROW_RX = re.compile(r'[A-Za-z_]\w*\s*->\s*[A-Za-z_]\w*(?:\s*\.\s*[A-Za-z_]\w*)*')
TOKEN_RX = re.compile(r'[A-Za-z_]\w*|0[xX][0-9a-fA-F]+\w*|\d+\w*|->|&&|\|\||\+\+|--|[<>=!]=|<<|>>|.', re.S)
CARD_DIR_FILES = {'harness.c', 'Makefile', 'NOTES.md'}
ALLOWED_DIRECTIVES = {'include', 'define', 'undef', 'if', 'ifdef', 'ifndef', 'elif', 'else', 'endif', 'error', 'pragma'}


class Scan:
    def __init__(self, root):
        self.root = root
        self.problems = []
        self.overlay_macros = {}  # sqlite3.c function-like macro name -> identifiers in its replacement text
        self.overlay_defines = set()  # every name sqlite3.c #defines, in any branch
        self._system_macros = {}  # (system includes) -> the names gcc defines with them, over every configuration

    def bad(self, where, msg):
        self.problems.append('%s: %s' % (where, msg))

    def rel(self, p):
        return os.path.relpath(p, self.root)


def strip_comments(text):
    """Replace comments with spaces, keeping newlines and string literals, so token rules see
    only code. SETUP markers are found on the raw text separately."""
    out = []
    i, n = 0, len(text)
    while i < n:
        if text.startswith('/*', i):
            j = text.find('*/', i + 2)
            j = n if j < 0 else j + 2
            out.append(re.sub(r'[^\n]', ' ', text[i:j]))
            i = j
        elif text.startswith('//', i):
            j = text.find('\n', i)
            j = n if j < 0 else j
            out.append(' ' * (j - i))
            i = j
        elif text[i] in '"\'':
            q = text[i]
            j = i + 1
            while j < n and text[j] != q and text[j] != '\n':
                if text[j] == '\\':
                    j += 1
                j += 1
            out.append(text[i:j + 1])
            i = j + 1
        else:
            out.append(text[i])
            i += 1
    return ''.join(out)


def balanced(text, i):
    """text[i] == '(' ; return index just past the matching ')'."""
    depth = 0
    n = len(text)
    while i < n:
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def top_level_functions(code):
    """Yield (name, start offset, body start, body end) of function definitions at brace depth 0."""
    depth = 0
    i, n = 0, len(code)
    out = []
    last_stmt_end = 0
    while i < n:
        c = code[i]
        if c == '{':
            if depth == 0:
                head = code[last_stmt_end:i]
                m = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*$', head, re.S)
                if m and m.group(1) not in C_KEYWORDS and not re.search(r'\b(struct|union|enum)\s*$', head[:m.start()]):
                    j = i
                    d = 0
                    while j < n:
                        if code[j] == '{':
                            d += 1
                        elif code[j] == '}':
                            d -= 1
                            if d == 0:
                                break
                        j += 1
                    out.append((m.group(1), last_stmt_end + m.start(), i, j))
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                last_stmt_end = i + 1
        elif c == ';' and depth == 0:
            last_stmt_end = i + 1
        elif c == '\n' and depth == 0 and code[last_stmt_end:i].lstrip().startswith('#'):
            last_stmt_end = i + 1
        i += 1
    return out


def file_scope_objects(code):
    """Top-level declarations ending in ';' that define objects (not functions, types, externs)."""
    out = []
    depth = 0
    start = 0
    for i, c in enumerate(code):
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                start = i + 1
        elif c == ';' and depth == 0:
            stmt = code[start:i].strip()
            start = i + 1
            lines = [ln for ln in stmt.split('\n') if not ln.strip().startswith('#')]
            stmt = ' '.join(lines).strip()
            if not stmt:
                continue
            if re.match(r'^(typedef|extern|struct|union|enum)\b', stmt) and not re.search(r'\}\s*[A-Za-z_]', stmt):
                continue
            if re.search(r'\)\s*(__CPROVER_\w+\s*\(.*)?$', stmt, re.S) and '=' not in stmt.split('(')[0]:
                continue  # function declaration (possibly with contract clauses)
            out.append(stmt[:80])
        elif c == '\n' and depth == 0 and code[start:i].strip().startswith('#'):
            start = i + 1
    return out


def sqlite_identifiers(overlay_text):
    """Identifiers in sqlite3.c's code (comments removed by a fast regex; good enough for names)."""
    code = re.sub(r'/\*.*?\*/|//[^\n]*', ' ', overlay_text, flags=re.S)
    return set(re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\b', code))


def function_like_macros(overlay_text):
    """{name: identifiers in its replacement text} for each function-like #define in sqlite3.c."""
    text = re.sub(r'\\\r?\n', ' ', overlay_text)
    out = {}
    for m in re.finditer(r'^[ \t]*#[ \t]*define[ \t]+([A-Za-z_][A-Za-z0-9_]*)\(([^)\n]*)\)(.*)$', text, re.M):
        body = re.sub(r'/\*.*?\*/|//.*', ' ', m.group(3))
        out.setdefault(m.group(1), set()).update(re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\b', body))
    return out


DEFINE_RX = re.compile(r'^[ \t]*#[ \t]*define[ \t]+([A-Za-z_][A-Za-z0-9_]*)', re.M)


def defined_names(text):
    """Every name a C file #defines, in any #if branch (an over-approximation is what rule 11 wants)."""
    return set(DEFINE_RX.findall(re.sub(r'\\\r?\n', ' ', text)))


def project_header(root, inc):
    """The file a quoted include names, searched as prove.py's goto-cc line does (-I overlay -I proofs/include
    -I proofs), or None."""
    for d in ('overlay', os.path.join('proofs', 'include'), 'proofs'):
        f = os.path.join(root, d, inc)
        if os.path.isfile(f):
            return f
    return None


def harness_macros(s, where, code):
    """Rule 11 (auditor 2026-11-09 afternoon): every name a harness's translation unit may have #defined: sqlite3.c's,
    proof.h's (prove.py includes it first) and those of each header the harness includes, project headers followed
    through their own includes, and system headers as gcc preprocesses them for every configuration in
    proofs/CONFIGS (its predefined macros included)."""
    names = set(s.overlay_defines)
    seen, todo, system = set(), ['proof.h'], set()
    todo += [m.group(1) for m in re.finditer(r'^[ \t]*#[ \t]*include[ \t]*"([^"]+)"', code, re.M)]
    system |= set(re.findall(r'^[ \t]*#[ \t]*include[ \t]*(<[^>\n]+>)', code, re.M))
    while todo:
        inc = todo.pop()
        if inc in seen or inc == 'sqlite3.c':
            continue
        seen.add(inc)
        f = project_header(s.root, inc)
        if not f:
            continue
        text = strip_comments(open(f, errors='replace').read())
        names |= defined_names(text)
        todo += re.findall(r'^[ \t]*#[ \t]*include[ \t]*"([^"]+)"', text, re.M)
        system |= set(re.findall(r'^[ \t]*#[ \t]*include[ \t]*(<[^>\n]+>)', text, re.M))
    key = tuple(sorted(system))
    if key not in s._system_macros:
        got = set()
        try:
            configs = prove.read_configs(s.root)
        except Exception:
            configs = [('default', [])]
        for name, flags in configs or [('default', [])]:
            gflags = [f for f in flags if not f.startswith('--')]  # goto-cc's own (--big-endian) are not gcc's
            src = ''.join('#include %s\n' % i for i in key)
            try:
                p = subprocess.run(['gcc', '-dM', '-E', '-x', 'c'] + gflags + ['-'], input=src, capture_output=True,
                                   text=True, timeout=120)
            except (OSError, subprocess.TimeoutExpired) as e:
                p = None
                err = str(e)
            if p is None or p.returncode != 0:
                s.bad(where, 'cannot list the macros of %s for configuration %s (gcc -dM -E: %s)' % (
                    ', '.join(key) or 'no system headers', name, (p.stderr.strip()[:200] if p else err)))
                continue
            got |= defined_names(p.stdout)
        s._system_macros[key] = got
    return names | s._system_macros[key]


# ------------------------------------------------------------------- rules

def check_checks(s):
    p = os.path.join(s.root, 'proofs', 'CHECKS')
    if not os.path.exists(p):
        s.bad('proofs/CHECKS', 'missing')
        return
    text = open(p).read()
    opts = []
    for line in text.split('\n'):
        t = line.strip()
        if t.startswith('--'):
            opts.extend(t.split())
        elif t.startswith('%'):
            opts.extend(x for x in t.split() if x.startswith('--'))
    for r in REQUIRED_CHECKS:
        if r not in opts:
            s.bad('proofs/CHECKS', 'required option %s missing' % r)
    for o in opts:
        if FORBIDDEN_OPTION_RX.fullmatch(o) or o.startswith('--no-'):
            s.bad('proofs/CHECKS', 'option %s turns a check off or narrows what is checked' % o)
    if '%float-to-int' not in text:
        s.bad('proofs/CHECKS', 'the %float-to-int directive is missing')


def check_configs(s):
    p = os.path.join(s.root, 'proofs', 'CONFIGS')
    for name, flags in prove.read_configs(s.root):
        for f in flags:
            if not (f in ('-m64', '-m32', '--big-endian', '--little-endian', '-funsigned-char')
                    or re.match(r'^-DSQLITE_BYTEORDER=(1234|4321)$', f)):
                s.bad(s.rel(p), 'configuration %s: flag %s is not a word-size, byte-order or char-signedness flag' % (name, f))


def check_pragmas(s, where, code):
    if re.search(r'#\s*pragma\s+CPROVER', code) or '_Pragma' in code:
        s.bad(where, '#pragma CPROVER / _Pragma can turn checks off; not allowed')


def check_defines(s, where, code):
    for m in re.finditer(r'^[ \t]*#[ \t]*(define|undef)\b(.*)$', code, re.M):
        body = m.group(2)
        if re.search(r'__CPROVER|assume|##|\bPROOF\b|#\s*[A-Za-z_]', body):
            s.bad(where, 'macro may not mention __CPROVER, assume, PROOF, # or ##: %s' % m.group(0).strip()[:80])
    if '##' in code:
        s.bad(where, 'token pasting (##) not allowed')


def check_guard_only(s, where, code, sqlite_ids):
    """Rule 15: a shared header (preds.h, proofs/contracts/, proofs/spec/) #defines nothing but its include guard
    and #undefs nothing. A macro would let a header keep every item preds.h held, so the append-only rule passes,
    while changing what an existing predicate or a SQLite name means where it is used. The guard is `#ifndef G`
    as the file's first code, `#define G` (no value) as its next line, and G an all-caps name ending in _H that
    sqlite3.c does not use."""
    guard = None
    m = re.match(r'\s*#[ \t]*ifndef[ \t]+([A-Za-z_]\w*)[ \t]*\n[ \t]*#[ \t]*define[ \t]+(\1)[ \t]*(?:\n|$)', code)
    if m:
        g = m.group(1)
        if re.fullmatch(r'[A-Z][A-Z0-9_]*_H', g) and g not in sqlite_ids:
            guard = m.start(2)
        else:
            s.bad(where, 'include guard %s must be an all-caps name ending in _H that sqlite3.c does not use' % g)
    for d in re.finditer(r'^[ \t]*#[ \t]*(define|undef)\b[ \t]*(\S*)', code, re.M):
        if guard is not None and d.group(1) == 'define' and d.start(2) == guard:
            continue
        line = code.count('\n', 0, d.start()) + 1
        s.bad(where, 'line %d: #%s %s: a shared header may #define only its include guard, and #undef nothing'
              % (line, d.group(1), d.group(2)[:40]))


def check_assumes(s, where, raw, code, allow_setup):
    """__CPROVER_assume only inside SETUP blocks (if allow_setup), and never reading data."""
    blocks = []
    if allow_setup:
        for m in re.finditer(r'/\*\s*SETUP\s*\*/', raw):
            e = re.compile(r'/\*\s*END SETUP\s*\*/').search(raw, m.end())
            if not e:
                s.bad(where, 'SETUP block at line %d has no END SETUP' % (raw.count('\n', 0, m.start()) + 1))
                continue
            blocks.append((m.end(), e.start()))
    for m in re.finditer(r'\b(__CPROVER_assume|__builtin_assume|__CPROVER_precondition_assume)\b', code):
        line = code.count('\n', 0, m.start()) + 1
        if m.group(1) != '__CPROVER_assume':
            s.bad(where, 'line %d: %s not allowed' % (line, m.group(1)))
            continue
        inside = any(a <= m.start() < b for a, b in blocks)
        if not inside:
            s.bad(where, 'line %d: __CPROVER_assume outside a /* SETUP */ ... /* END SETUP */ block' % line)
            continue
        k = code.find('(', m.end())
        e = balanced(code, k) if k >= 0 else -1
        expr = code[k + 1:e - 1] if e > 0 else ''
        if '[' in expr:
            s.bad(where, 'line %d: setup assume subscripts an array (constrains data bytes?): %s' % (line, expr.strip()[:80]))
        if re.search(r'(^|[(,!=<>&|?:~+\-])\s*\*', expr):
            s.bad(where, 'line %d: setup assume dereferences a pointer (constrains data bytes?): %s' % (line, expr.strip()[:80]))


def check_zero_fill(s, where, code):
    for rx, what in ((r'\bcalloc\s*\(', 'calloc zero-fills'), (r'\bmemset\s*\(', 'memset fills bytes'),
                     (r'=\s*\{', 'brace initializers fix bytes'), (r'\bstatic\s+[^;()]*\[', 'static arrays are zero-initialized')):
        for m in re.finditer(rx, code):
            s.bad(where, 'line %d: %s' % (code.count('\n', 0, m.start()) + 1, what))
    for o in file_scope_objects(code):
        s.bad(where, 'file-scope object (zero-initialized static storage): %s' % o)


def check_function_defs(s, where, code, sqlite_ids, allow_contract_decl=None):
    for name, start, _, _ in top_level_functions(code):
        line = code.count('\n', 0, start) + 1
        if name.startswith('__CPROVER'):
            s.bad(where, 'line %d: defines %s' % (line, name))
        elif name in sqlite_ids:
            s.bad(where, 'line %d: defines %s, a name SQLite\'s code uses; use its code, CBMC\'s model or a ledger contract' % (line, name))
    for m in re.finditer(r'\b(contract_[A-Za-z0-9_]+)\s*\(', code):
        if allow_contract_decl != m.group(1):
            # a call to contract_x is never meaningful; a declaration outside proofs/contracts/ is a loophole
            s.bad(where, 'line %d: %s may be declared only in proofs/contracts/%s.h' % (
                code.count('\n', 0, m.start()) + 1, m.group(1), m.group(1)[len('contract_'):]))


def without_strings(code):
    """String and character literals emptied (lines are kept), so names inside messages aren't matched."""
    return re.sub(r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', '""', code)


def check_path_enders(s, where, code):
    """Rule 10."""
    c = without_strings(code)
    for m in PATH_ENDERS_RX.finditer(c):
        s.bad(where, 'line %d: %s ends or redirects a path (an assume by another name) or overwrites bytes wholesale; '
                     'not allowed' % (c.count('\n', 0, m.start()) + 1, m.group(1)))


def check_directives(s, where, code):
    """Rule 12: only the preprocessor directives a harness or header needs."""
    for m in re.finditer(r'^[ \t]*#[ \t]*([A-Za-z_]\w*)(.*)$', code, re.M):
        d, rest = m.group(1), m.group(2).strip()
        line = code.count('\n', 0, m.start()) + 1
        if d not in ALLOWED_DIRECTIVES:
            s.bad(where, 'line %d: #%s not allowed' % (line, d))
        elif d == 'pragma' and rest != 'once':
            s.bad(where, 'line %d: #pragma %s not allowed (only #pragma once)' % (line, rest[:40]))


def split_statements(text, base):
    """[(offset, statement)] split at ';' outside parentheses and brackets."""
    out, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        if ch in '([':
            depth += 1
        elif ch in ')]':
            depth -= 1
        elif ch == ';' and depth == 0:
            out.append((base + start, text[start:i]))
            start = i + 1
    if text[start:].strip():
        out.append((base + start, text[start:]))
    return [(o, x) for o, x in out if x.strip()]


def calls_in(text):
    return [m.group(1) for m in re.finditer(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(', text) if m.group(1) not in C_KEYWORDS or m.group(1) == 'sizeof']


def is_declaration(stmt):
    """A declaration without an initializer, or anything else that assigns, calls and branches on nothing."""
    return not re.search(r'[={}?]|\+\+|--', stmt) and all(c == 'sizeof' for c in calls_in(stmt)) and \
        not re.search(r'\b(if|while|for|switch|do|else|case|return|goto)\b', stmt)


def top_assignment(stmt):
    """(lhs, rhs) if stmt is `lhs = rhs` with one plain '=' outside parentheses, else None."""
    depth = 0
    for i, ch in enumerate(stmt):
        if ch in '([':
            depth += 1
        elif ch in ')]':
            depth -= 1
        elif ch == '=' and depth == 0:
            prev = stmt[i - 1] if i else ''
            nxt = stmt[i + 1] if i + 1 < len(stmt) else ''
            if prev in '=!<>+-*/%&|^' or nxt == '=':
                return None
            return stmt[:i], stmt[i + 1:]
    return None


STORAGE_CLASS_RX = re.compile(r'\b(static|extern|_Thread_local|thread_local|__thread)\b')


def declared_names(stmt):
    """The names a declaration statement declares (`T a, *b, c[4]`, `T *p = malloc(n)`); [] for anything else (an
    assignment, an assume, a call), so a name counts as a local only where the entry function declares it."""
    names = []
    if STORAGE_CLASS_RX.search(stmt):
        return []
    for i, d in enumerate(top_level_args(stmt)):
        head = re.sub(r'\[[^\]]*\]', ' ', d.split('=', 1)[0])
        if re.search(r'[(){}.*]\s*$|[(){}.]|->', head):
            return []
        ids = re.findall(r'[A-Za-z_][A-Za-z0-9_]*', head)
        if len(ids) < (2 if i == 0 else 1) or ids[-1] in C_KEYWORDS:
            return []
        names.append(ids[-1])
    return names


def unary_amp(t):
    """True if t takes an address: a '&' token not preceded by an operand."""
    toks = [x for x in TOKEN_RX.findall(t) if not x.isspace()]
    for i, x in enumerate(toks):
        if x == '&':
            prev = toks[i - 1] if i else None
            if prev is None or not (re.match(r'^[A-Za-z_0-9]', prev) and prev not in C_KEYWORDS or prev in (')', ']')):
                return True
    return False


def pointer_names(stmt):
    """Names a declaration declares as pointers (`T *a, *b`, `T *a = ...`)."""
    head = stmt.split('=', 1)[0] if '=' in stmt else stmt
    return set(re.findall(r'\*\s*([A-Za-z_]\w*)', head))


def array_names(stmt):
    head = stmt.split('=', 1)[0] if '=' in stmt else stmt
    return set(re.findall(r'\b([A-Za-z_]\w*)\s*\[', head))


def strip_parens(x):
    x = x.strip()
    while x.startswith('(') and balanced(x, 0) == len(x):
        x = x[1:-1].strip()
    return x


def pointer_rhs_ok(rhs, ptrs):
    """A data pointer may hold only a malloc result (cast or not), pointer arithmetic on a pointer that does, or 0."""
    r = strip_parens(rhs)
    m = re.match(r'^(?:\(\s*[A-Za-z_][\w\s]*\*[\s*]*\)\s*)?malloc\s*\(', r)
    if m and balanced(r, m.end() - 1) == len(r):
        return True
    if r in ('0', 'NULL'):
        return True
    m = re.match(r'^([A-Za-z_]\w*)\s*(?:[+-](.*))?$', r, re.S)
    return bool(m and m.group(1) in ptrs and not re.search(r'[*&"\[]|->', m.group(2) or ''))


def setup_statement_problem(stmt, ptrs=frozenset(), arrays=frozenset()):
    """Rule 11: what a SETUP statement may be. None if allowed. ptrs and arrays: the entry function's pointer and
    array variables."""
    t = stmt.strip()
    bad_calls = [c for c in calls_in(t) if c not in SETUP_CALLS]
    if re.search(r'[{}]', t) or re.search(r'\b(if|while|for|switch|do|else|case|return|goto)\b', t):
        return 'a SETUP block holds straight-line statements only'
    if bad_calls:
        return 'a SETUP block may call only malloc and CPROVER primitives (calls %s)' % ', '.join(sorted(set(bad_calls)))
    # checkpoint 0 follow-up 2
    if '"' in t:
        return 'a SETUP block may not hold string literals (they fix data bytes)'
    if unary_amp(t):
        return 'a SETUP block may not take an address (a pointer to a local or a field narrows what the code can reach)'
    nosize = re.sub(r'\bsizeof\s*\(', 'sizeof_(', t)
    named = [a for a in arrays if re.search(r'(?<!sizeof_\()\b%s\b' % re.escape(a), nosize)]
    if named:
        return 'a SETUP block may not name a local array outside sizeof (it stands for its address): %s' % ', '.join(sorted(named))
    a = top_assignment(t)
    arrows = t.count('->')
    if arrows and not (a and arrows == 1 and LHS_ARROW_RX.fullmatch(a[0].strip())):
        return 'a SETUP block may not read a member through a pointer (->); only `p->field = value` may use one'
    for m in PTR_CAST_RX.finditer(t):
        if re.search(r'\bsizeof\s*$', t[:m.start()]):
            continue
        if not re.match(r'\s*malloc\s*\(', t[m.end():]):
            return 'a SETUP block may cast to a data pointer type only a malloc result (%s)' % m.group(0)
    if a:
        lhs = a[0].strip()
        declared = re.search(r'\*\s*([A-Za-z_]\w*)$', lhs)       # `T *p = ...`
        is_ptr = bool(declared) or (re.fullmatch(r'[A-Za-z_]\w*', lhs) is not None and lhs in ptrs)
        if is_ptr and not pointer_rhs_ok(a[1], ptrs):
            return 'a data pointer may hold only a malloc result or pointer arithmetic on one'
    if re.match(r'^__CPROVER_assume\s*\(', t):
        e = balanced(t, t.index('('))
        return None if e == len(t) else 'an assume must be a statement of its own'
    if is_declaration(t):
        return None
    a = top_assignment(t)
    if a is None:
        return 'a SETUP block holds declarations, assumes and allocations or field and pointer assignments only'
    lhs, rhs = a
    if '[' in lhs or re.match(r'^\s*\*', lhs) or re.search(r'\+\+|--', t):
        return 'a SETUP assignment may not store through a subscript or a pointer (that fixes data bytes)'
    if '[' in rhs or DEREF_RX.search(rhs):
        return 'a SETUP assignment may not read through a subscript or a pointer (that copies data bytes)'
    return None


_INT = r'(?:0[xX][0-9a-fA-F]+|[0-9]+)'
_ID = r'[A-Za-z_][A-Za-z0-9_]*'
# the one store allowed between END SETUP and the call under proof (checkpoint 0 follow-up 2): `S[k] = X[k]` with a
# constant k, or the whole body of `for(i = <const>; i < <const>; ++i)` as `S[i] = X[i]`; no braces
SNAPSHOT_ALONE_RX = re.compile(r'(?P<S>%s)\s*\[\s*(?P<k>%s)\s*\]\s*=\s*(?P<X>%s)\s*\[\s*(?P=k)\s*\]' % (_ID, _INT, _ID))
SNAPSHOT_LOOP_RX = re.compile(
    r'for\s*\(\s*(?P<i>%s)\s*=\s*%s\s*;\s*(?P=i)\s*<\s*%s\s*;\s*\+\+\s*(?P=i)\s*\)\s*'
    r'(?P<S>%s)\s*\[\s*(?P=i)\s*\]\s*=\s*(?P<X>%s)\s*\[\s*(?P=i)\s*\]' % (_ID, _INT, _INT, _ID, _ID))


def _declarations_of(name, decls):
    """The declaration statements among decls that declare name at the entry function's top level."""
    return [d for d in decls if is_declaration(d) and re.search(r'(?<![A-Za-z0-9_.>])%s\b' % re.escape(name), d)
            and re.match(r'^\s*(?:%s\s+)+' % _ID, d)]


def snapshot_problem(snap, decls, call_stmt, setup_text, counters):
    """Why a snapshot statement is not the allowed form, or None. S must be an array declared once in the entry
    function (not a pointer, not static, no initializer); i, for the loop form, a plain local declared there and
    used by no other snapshot loop; and neither may appear in the call statement or in SETUP."""
    S, X = snap.group('S'), snap.group('X')
    i = snap.groupdict().get('i')
    names = [S, X] + ([i] if i else [])
    if len(set(names)) != len(names):
        return 'S, X and the loop counter must be different names'
    ds = _declarations_of(S, decls)
    if len(ds) != 1:
        return '%s must be declared once in the entry function, as an array (found %d declarations)' % (S, len(ds))
    d = ds[0]
    if re.search(r'\b(static|extern|register)\b', d):
        return '%s may not be static or extern' % S
    if not re.search(r'(?<![*A-Za-z0-9_])\s*%s\s*\[\s*%s\s*\]' % (re.escape(S), _INT), d) or \
            re.search(r'\*\s*%s\b' % re.escape(S), d):
        return '%s must be declared as an array with a constant size, not a pointer' % S
    if i:
        di = _declarations_of(i, decls)
        if len(di) != 1 or re.search(r'\b(static|extern)\b', di[0]) or re.search(r'\*\s*%s\b|\b%s\s*\[' % (
                re.escape(i), re.escape(i)), di[0]):
            return 'the loop counter %s must be a plain local declared once in the entry function' % i
        if i in counters:
            return 'the loop counter %s is assigned by another snapshot loop before the call' % i
        counters.append(i)
    for n in [S] + ([i] if i else []):
        if re.search(r'\b%s\b' % re.escape(n), call_stmt):
            return '%s appears in the call under proof\'s statement' % n
        if re.search(r'\b%s\b' % re.escape(n), setup_text):
            return '%s appears in SETUP' % n
    return None


def check_entries(s, where, raw, code, proofs, card, macros=frozenset()):
    """Rule 11, for each proof's ENTRY function. Returns {entry: (the data pointers, and all the local variables, it
    declares before SETUP or in it)}, for check_card_calls."""
    defs = {name: (start, b, e) for name, start, b, e in top_level_functions(code)}
    setup_rx = re.compile(r'/\*\s*SETUP\s*\*/')
    end_rx = re.compile(r'/\*\s*END SETUP\s*\*/')
    entry_ranges = []
    entry_ptrs = {}
    for proof in proofs:
        ent = proof.entry
        if ent not in defs:
            s.bad(where, '%s: entry function %s is not defined in harness.c' % (proof.name, ent))
            continue
        _, b, e = defs[ent]
        entry_ranges.append((b, e))
        body = code[b + 1:e]
        for m in re.finditer(r'\b(return|goto)\b', body):
            s.bad(where, 'line %d: %s in entry function %s (a path that skips the call under proof is an assume)' % (
                code.count('\n', 0, b + 1 + m.start()) + 1, m.group(1), ent))
        # auditor 2026-11-09: a static or thread-local local keeps its zero (or initializer) in a proof without
        # contracts, and an extern names a global; neither is an input the proof leaves free
        # auditor 2026-11-09 afternoon: declarations use only C keywords and typedef names, never a name some header
        # #defines (SQLITE_PRIVATE is static, SQLITE_EXTERN extern), so what scan reads is what the compiler sees
        sa0 = next((m.start() for m in setup_rx.finditer(raw, b, e)), e)
        frags, start, depth = [], b + 1, 0
        for i in range(b + 1, e):
            ch = code[i]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif depth == 0 and ch in ';{}':
                frags.append((start, code[start:i]))
                start = i + 1
        for off, fr in frags:
            if not fr.strip() or not (declared_names(fr) or off < sa0 or STORAGE_CLASS_RX.search(fr)):
                continue
            for part in top_level_args(fr):
                for n in sorted(set(re.findall(_ID, part.split('=', 1)[0])) & set(macros)):
                    s.bad(where, 'line %d: %s in a declaration in entry function %s is a macro (sqlite3.c or an included '
                                 'header #defines it): declarations use only C keywords and typedef names' % (
                        code.count('\n', 0, off + len(fr) - len(fr.lstrip())) + 1, n, ent))
        for m in STORAGE_CLASS_RX.finditer(blank_strings(body)):
            s.bad(where, 'line %d: %s declaration in entry function %s (a static keeps its initial value and an extern '
                         'is a global: declare inputs as plain locals)' % (
                code.count('\n', 0, b + 1 + m.start()) + 1, m.group(1), ent))
        setups = [m for m in setup_rx.finditer(raw, b, e)]
        ends = [m for m in end_rx.finditer(raw, b, e)]
        if len(setups) != 1 or len(ends) != 1 or ends[0].start() < setups[0].end():
            s.bad(where, 'entry function %s must hold exactly one /* SETUP */ ... /* END SETUP */ block (found %d and %d)' % (
                ent, len(setups), len(ends)))
            continue
        sa, sb = setups[0].start(), ends[0].end()
        ptrs, arrays, local = set(), set(), set()
        for off, st in split_statements(code[b + 1:sa], b + 1):
            if not is_declaration(st):
                s.bad(where, 'line %d: before SETUP, entry function %s may only declare variables: %s' % (
                    code.count('\n', 0, off + len(st) - len(st.lstrip())) + 1, ent, ' '.join(st.split())[:80]))
            ptrs |= pointer_names(st)
            arrays |= array_names(st)
            local.update(declared_names(st))
        setup_stmts = split_statements(code[setups[0].end():ends[0].start()], setups[0].end())
        for off, st in setup_stmts:
            if is_declaration(st) or (top_assignment(st) and not re.search(r'[\[\]>.]|^\s*\*', top_assignment(st)[0])):
                ptrs |= pointer_names(st)
                arrays |= array_names(st)
            local.update(declared_names(st))
        entry_ptrs[ent] = (frozenset(ptrs & local), frozenset(local))
        for off, st in setup_stmts:
            why = setup_statement_problem(st, frozenset(ptrs), frozenset(arrays))
            if why:
                s.bad(where, 'line %d: %s: %s' % (code.count('\n', 0, off + len(st) - len(st.lstrip())) + 1, why,
                                                    ' '.join(st.split())[:80]))
        targets = proof.enforced or (card.functions if card else [])
        if not targets:
            continue
        rx = re.compile(r'\b(%s)\s*\(' % '|'.join(re.escape(t) for t in targets))
        m = rx.search(code, sb, e)
        if not m:
            s.bad(where, 'entry function %s never calls the function under proof (%s) after END SETUP' % (ent, ', '.join(targets)))
            continue
        before = code[b + 1:m.start()]
        depth = before.count('{') - before.count('}')
        stmt_start = max(before.rfind(';'), before.rfind('{'), before.rfind('}'))
        prefix = before[stmt_start + 1:]
        if depth != 0 or re.search(r'\b(if|else|while|for|do|switch|case)\b|\?|&&|\|\|', prefix):
            s.bad(where, 'line %d: the call under proof (%s) must be a statement of %s\'s body, not inside a condition '
                         'or loop (that hides the inputs that skip it)' % (code.count('\n', 0, m.start()) + 1, m.group(1), ent))
        # checkpoint 0 follow-up 2: between END SETUP and the call under proof, nothing that could narrow its inputs
        # (a store through a pointer or subscript, a plain assignment, a call, any control flow): declarations only,
        # and snapshot copies (snapshot_problem) into local arrays the call never sees
        if depth == 0 and stmt_start >= 0 and b + 1 + stmt_start + 1 > sb:
            cs = b + 1 + stmt_start + 1
            region = split_statements(code[sb:cs], sb)
            decls = [x for _, x in split_statements(code[b + 1:sa], b + 1)] + [x for _, x in region if is_declaration(x)]
            call_stmt = split_statements(code[cs:e], cs)[0][1]
            setup_text = code[setups[0].end():ends[0].start()]
            counters = []
            for off, st in region:
                ln = code.count('\n', 0, off + len(st) - len(st.lstrip())) + 1
                snap = SNAPSHOT_ALONE_RX.fullmatch(st.strip()) or SNAPSHOT_LOOP_RX.fullmatch(st.strip())
                if snap:
                    why = snapshot_problem(snap, decls, call_stmt, setup_text, counters)
                    if why:
                        s.bad(where, 'line %d: snapshot before the call under proof (%s): %s: %s' % (
                            ln, m.group(1), why, ' '.join(st.split())[:80]))
                elif st.strip() and not is_declaration(st):
                    s.bad(where, 'line %d: between END SETUP and the call under proof (%s), entry function %s may only '
                                 'declare variables or snapshot into a local array (no stores, assignments, calls or '
                                 'control flow): %s' % (ln, m.group(1), ent, ' '.join(st.split())[:80]))
    for m in setup_rx.finditer(raw):
        if not any(b <= m.start() < e for b, e in entry_ranges):
            s.bad(where, 'line %d: SETUP block outside an entry function' % (raw.count('\n', 0, m.start()) + 1))
    return entry_ptrs


CARD_ARG_RX = re.compile(r'&\s*{0}|(?P<x>{0})\s*\+\s*(?P<y>{0})|{0}'.format(_ID))


def card_call_names(funcs, macros):
    """funcs, plus every sqlite3.c function-like macro whose expansion reaches one of them."""
    names = set(funcs)
    grew = True
    while grew:
        grew = False
        for n, ids in macros.items():
            if n not in names and ids & names:
                names.add(n)
                grew = True
    return names


def blank_strings(code):
    """String and character literals' contents replaced by spaces, offsets kept."""
    return re.sub(r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'',
                  lambda m: m.group(0)[0] + ' ' * (len(m.group(0)) - 2) + m.group(0)[-1], code)


def top_level_args(text):
    """text split at commas outside parentheses and brackets."""
    out, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        elif ch == ',' and depth == 0:
            out.append(text[start:i])
            start = i + 1
    out.append(text[start:])
    return out if text.strip() else []


def check_card_calls(s, where, code, proofs, card, entry_ptrs=None):
    """Rule 11 (auditor recheck item 1): a card function, or a sqlite3.c macro that expands to one, is named only as
    a call in an entry function, and each argument of that call is `id`, `&id` or `x + y`, so any narrowing of
    the inputs sits in SETUP. In `x + y` (auditor, 2026-11-08 late), x is a data pointer the entry function declares
    before SETUP or in it, and y another identifier: `value + value` would let the proof see only even values. Every
    name in an argument (auditor, 2026-11-09) is a local variable the entry function declares before SETUP or in
    it: a sqlite3.c macro, an enum constant or a global (SQLITE_ROW, sqlite3PendingByte) would fix the input."""
    entry_ptrs = entry_ptrs or {}
    funcs = set(card.functions if card else []) | {f for p in proofs for f in p.enforced}
    if not funcs:
        return
    names = card_call_names(funcs, s.overlay_macros)
    entries = {p.entry for p in proofs}
    ranges = [(name, b, e) for name, _, b, e in top_level_functions(code) if name in entries]
    blank = blank_strings(code)
    rx = re.compile(r'\b(%s)\b' % '|'.join(re.escape(n) for n in sorted(names, key=len, reverse=True)))
    for m in rx.finditer(blank):
        line = code.count('\n', 0, m.start()) + 1
        ent = next((name for name, b, e in ranges if b < m.start() < e), None)
        if ent is None:
            s.bad(where, 'line %d: %s, a card function or a macro that calls one, is named outside an entry function '
                         '(a helper or file-scope use would let its inputs be narrowed outside SETUP)' % (
                line, m.group(1)))
            continue
        j = m.end()
        while j < len(blank) and blank[j].isspace():
            j += 1
        k = balanced(blank, j) if blank[j:j + 1] == '(' else -1
        if k < 0:
            s.bad(where, 'line %d: %s is used other than as a call (a call through a pointer escapes the argument '
                         'rule)' % (line, m.group(1)))
            continue
        for arg in top_level_args(blank[j + 1:k - 1]):
            if not CARD_ARG_RX.fullmatch(arg.strip()):
                s.bad(where, 'line %d: argument `%s` of %s: a card function\'s arguments may be only id, &id or '
                             'id + id; narrow its inputs in SETUP, where the reviewer checks them' % (
                    line, ' '.join(arg.split())[:60], m.group(1)))
                continue
            am = CARD_ARG_RX.fullmatch(arg.strip())
            ptrs, local = entry_ptrs.get(ent, ((), ()))
            for n in re.findall(_ID, arg):
                if n not in local:
                    s.bad(where, 'line %d: argument `%s` of %s: %s is not a local variable %s declares before or in '
                                 'SETUP (a macro, enum constant or global fixes the input)' % (
                        line, ' '.join(arg.split())[:60], m.group(1), n, ent))
            if am.group('x') and (am.group('x') not in ptrs or am.group('y') == am.group('x')):
                s.bad(where, 'line %d: argument `%s` of %s: in x + y, x must be a data pointer %s declares before or '
                             'in SETUP, and y a different identifier (`v + v` or `n + p` narrows the inputs)' % (
                    line, ' '.join(arg.split())[:60], m.group(1), ent))


def check_card_dir_files(s, card_dir):
    """Rule 12: proofs/C-NN/ holds harness.c, Makefile, NOTES.md and the ignored build/ directory only."""
    for n in sorted(os.listdir(card_dir)):
        p = os.path.join(card_dir, n)
        if n == 'build' and os.path.isdir(p) and not os.path.islink(p):
            continue
        if n not in CARD_DIR_FILES or not os.path.isfile(p):
            s.bad(s.rel(p), 'proofs/C-NN/ may hold only harness.c, Makefile and NOTES.md (quoted includes resolve here first)')


def check_tree_files(s):
    """Rule 12: overlay/ and proofs/include/ hold their named files only; no symlink under proofs/, overlay/,
    tests/repro/."""
    for sub, names in (('overlay', {'sqlite3.c'}), ('proofs/include', {'proof.h', 'preds.h'})):
        d = os.path.join(s.root, sub)
        if os.path.isdir(d):
            for n in sorted(os.listdir(d)):
                if n not in names or not os.path.isfile(os.path.join(d, n)):
                    s.bad('%s/%s' % (sub, n), '%s/ may hold only %s' % (sub, ', '.join(sorted(names))))
    for sub in ('proofs', 'overlay', 'tests/repro'):
        d = os.path.join(s.root, sub)
        if os.path.islink(d):
            s.bad(sub, 'is a symlink')
            continue
        for dirpath, dirnames, filenames in os.walk(d):
            for n in dirnames + filenames:
                if os.path.islink(os.path.join(dirpath, n)):
                    s.bad(s.rel(os.path.join(dirpath, n)), 'symlink not allowed (its content would live outside git)')


def top_level_items(code):
    """Preprocessor lines, function definitions and declarations at file scope, whitespace-normalized. A function
    definition (a body whose header ends in ')') ends at its '}'; a struct, union, enum or initializer goes on to ';'."""
    items, depth, start, i, n = [], 0, 0, 0, len(code)
    func_body = False
    while i < n:
        c = code[i]
        if depth == 0 and c == '#' and code[start:i].strip() == '':
            j = code.find('\n', i)
            j = n if j < 0 else j
            items.append(' '.join(code[i:j].split()))
            start = i = j
            continue
        if c == '{':
            if depth == 0:
                func_body = code[start:i].rstrip().endswith(')')
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0 and func_body:
                items.append(' '.join(code[start:i + 1].split()))
                start = i + 1
        elif c == ';' and depth == 0:
            items.append(' '.join(code[start:i + 1].split()))
            start = i + 1
        i += 1
    if code[start:].strip():
        items.append(' '.join(code[start:].split()))
    return [x for x in items if x and x != ';']


def check_preds_growth(s, base):
    """Rule 13: every file-scope item preds.h held at base is still there, unchanged."""
    rel = 'proofs/include/preds.h'
    p = subprocess.run(['git', '-C', s.root, 'show', '%s:%s' % (base, rel)], capture_output=True)
    if p.returncode != 0:
        return   # preds.h did not exist at base
    old = top_level_items(strip_comments(p.stdout.decode('utf-8', 'replace')))
    cur_path = os.path.join(s.root, rel)
    new = top_level_items(strip_comments(open(cur_path, errors='replace').read())) if os.path.exists(cur_path) else []
    from collections import Counter
    missing = Counter(old) - Counter(new)
    for item in missing:
        s.bad(rel, 'may only gain predicates; this item it held at %s was removed or changed: %s' % (base, item[:100]))


def check_cover(s, card_dir, card, proofs):
    """Rule 14: every function the card names is in some proof's COVER."""
    if card is None or not proofs:
        return
    covered = set()
    for p in proofs:
        covered.update(p.cover)
    for f in card.functions:
        if f not in covered:
            s.bad(s.rel(os.path.join(card_dir, 'Makefile')), '%s is a function of %s but no proof\'s COVER names it' % (f, card.id))


def check_harness(s, card_dir, sqlite_ids, proofs=(), card=None):
    hp = os.path.join(card_dir, 'harness.c')
    where = s.rel(hp)
    if not os.path.exists(hp):
        s.bad(where, 'missing')
        return
    raw = open(hp, errors='replace').read()
    code = strip_comments(raw)
    first = next((ln.strip() for ln in code.split('\n') if ln.strip()), '')
    if first != '#include "sqlite3.c"':
        s.bad(where, 'first line of code must be #include "sqlite3.c" (nothing may be defined before SQLite is compiled)')
    for m in re.finditer(r'^[ \t]*#[ \t]*include[ \t]*(.*)$', code, re.M):
        inc = m.group(1).strip()
        okq = re.match(r'^"(sqlite3\.c|proof\.h|preds\.h|contracts/[A-Za-z0-9_]+\.h|spec/[A-Za-z0-9_]+\.h)"$', inc)
        oks = re.match(r'^<[a-z0-9_/]+\.h>$', inc)
        if not (okq or oks):
            s.bad(where, 'include %s not allowed' % inc)
        if inc == '"sqlite3.c"' and code.count('"sqlite3.c"') != 1:
            s.bad(where, 'sqlite3.c included more than once')
    check_pragmas(s, where, code)
    check_defines(s, where, code)
    check_directives(s, where, code)
    check_assumes(s, where, raw, code, allow_setup=True)
    check_zero_fill(s, where, code)
    check_function_defs(s, where, code, sqlite_ids)
    check_path_enders(s, where, code)
    check_harness_text(s, where, code)
    entry_ptrs = check_entries(s, where, raw, code, proofs, card, harness_macros(s, where, code))
    check_card_calls(s, where, code, proofs, card, entry_ptrs)


def check_harness_text(s, where, code):
    """Rule 11, anywhere in a harness (checkpoint 0 follow-up 2): no directive but #include, so no macro can hide a
    statement from the other rules; no line splices, digraphs or trigraphs, which spell tokens these rules look for
    differently; no loop or function contract clauses (an invariant on a harness loop is assumed after it); no
    __builtin_* outside HARNESS_BUILTINS (__builtin_unreachable and __builtin_assume are assumes); no __attribute__
    or asm."""
    def line(i):
        return code.count('\n', 0, i) + 1
    for m in re.finditer(r'^[ \t]*#[ \t]*([A-Za-z_]\w*)', code, re.M):
        if m.group(1) != 'include':
            s.bad(where, 'line %d: #%s: a harness may use no preprocessor directive but #include' % (line(m.start()), m.group(1)))
    c = without_strings(code)
    for m in re.finditer(r'\\[ \t]*\n', c):
        s.bad(where, 'line %d: backslash-newline (a line splice) not allowed in a harness' % line(m.start()))
    for m in re.finditer(r'<:|:>|<%|%>|%:', c):
        s.bad(where, 'line %d: digraph %s not allowed in a harness' % (line(m.start()), m.group(0)))
    for m in re.finditer(r'\?\?[=/\'()!<>\-]', c):
        s.bad(where, 'line %d: trigraph %s not allowed in a harness' % (line(m.start()), m.group(0)))
    for m in CONTRACT_CLAUSE_RX.finditer(c):
        s.bad(where, 'line %d: %s: no loop or function contract clauses in a harness (a harness loop\'s invariant is '
                     'assumed after it)' % (line(m.start()), m.group(1)))
    for m in re.finditer(r'\b__builtin_\w+', c):
        if m.group(0) not in HARNESS_BUILTINS:
            s.bad(where, 'line %d: %s not allowed in a harness (allowed: %s)' % (
                line(m.start()), m.group(0), ', '.join(sorted(HARNESS_BUILTINS))))
    for m in re.finditer(r'\b(__attribute__|__attribute|asm|__asm__|__asm)\b', c):
        s.bad(where, 'line %d: %s not allowed in a harness' % (line(m.start()), m.group(1)))


def check_card_makefile(s, card_dir):
    try:
        card, proofs = prove.load_card(card_dir)
    except prove.CardError as e:
        s.bad(s.rel(os.path.join(card_dir, 'Makefile')), str(e))
        return None, []
    raw = open(os.path.join(card_dir, 'Makefile')).read()
    if 'include ../Makefile.common' not in raw.split('\n'):
        s.bad(s.rel(os.path.join(card_dir, 'Makefile')), 'must include ../Makefile.common')
    return card, proofs


def ledger_clauses(text):
    """{(A-NNN, fn): clause}: each ~~~ block in a LEDGER.md entry that declares contract_<fn>."""
    out = {}
    for m in re.finditer(r'^## (A-[0-9]{3})\b.*?(?=^## |\Z)', text, re.M | re.S):
        for b in re.finditer(r'^[ \t]*~~~[ \t]*\n(.*?)^[ \t]*~~~', m.group(0), re.M | re.S):
            f = re.search(r'\bcontract_([A-Za-z_][A-Za-z0-9_]*)\s*\(', b.group(1))
            if f:
                out[(m.group(1), f.group(1))] = b.group(1)
    return out


def check_contract_files(s, sqlite_ids, all_cards, enforced):
    d = os.path.join(s.root, 'proofs', 'contracts')
    proved = set()
    for c in all_cards.values():
        proved.update(c.functions)
    ledger_ids = None
    clauses = {}
    lp = os.path.join(s.root, 'LEDGER.md')
    if os.path.exists(lp):
        ltext = open(lp).read()
        ledger_ids = set(re.findall(r'^## (A-[0-9]{3})\b', ltext, re.M))
        clauses = ledger_clauses(ltext)
    # checkpoint 1, D2: every boundary clause LEDGER.md gives as a ~~~ block exists as proofs/contracts/<fn>.h
    for (aid, fn), _ in sorted(clauses.items()):
        if fn not in proved and not os.path.exists(os.path.join(d, fn + '.h')):
            s.bad('LEDGER.md', '%s gives contract_%s, but proofs/contracts/%s.h does not exist' % (aid, fn, fn))
    if not os.path.isdir(d):
        return
    for n in sorted(os.listdir(d)):
        p = os.path.join(d, n)
        where = s.rel(p)
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\.h$', n)
        if not m:
            s.bad(where, 'contract files are proofs/contracts/<function>.h')
            continue
        fn = m.group(1)
        raw = open(p, errors='replace').read()
        code = strip_comments(raw)
        if fn not in sqlite_ids:
            s.bad(where, '%s is not a function in sqlite3.c' % fn)
        if not re.search(r'\bcontract_%s\s*\(' % re.escape(fn), code):
            s.bad(where, 'must declare contract_%s' % fn)
        check_pragmas(s, where, code)
        check_defines(s, where, code)
        check_guard_only(s, where, code, sqlite_ids)
        check_directives(s, where, code)
        check_path_enders(s, where, code)
        check_assumes(s, where, raw, code, allow_setup=False)
        check_function_defs(s, where, code, sqlite_ids, allow_contract_decl='contract_' + fn)
        for name, start, _, _ in top_level_functions(code):
            s.bad(where, 'contract files declare; they define no functions (%s)' % name)
        if fn not in proved:
            lm = re.search(r'Ledger:\s*(A-[0-9]{3})', raw)
            if not lm:
                s.bad(where, 'boundary contract (no card proves %s) must name its ledger entry: "Ledger: A-NNN"' % fn)
            elif ledger_ids is not None and lm.group(1) not in ledger_ids:
                s.bad(where, 'names %s, which LEDGER.md does not have' % lm.group(1))
            elif ledger_ids is not None:
                clause = clauses.get((lm.group(1), fn))
                if clause is None:
                    s.bad(where, 'LEDGER.md %s gives no ~~~ clause declaring contract_%s' % (lm.group(1), fn))
                elif ' '.join(code.split()) != ' '.join(clause.split()):
                    s.bad(where, 'is not LEDGER.md %s\'s clause word for word (comments aside); a boundary header is '
                                 'exactly its ledger clause (checkpoint 1, D2)' % lm.group(1))


def check_preds(s, sqlite_ids):
    for sub, allow_assume in (('proofs/include', False), ('proofs/spec', False)):
        d = os.path.join(s.root, sub)
        if not os.path.isdir(d):
            continue
        for n in sorted(os.listdir(d)):
            if n == 'proof.h' or not n.endswith('.h'):
                continue
            p = os.path.join(d, n)
            where = s.rel(p)
            raw = open(p, errors='replace').read()
            code = strip_comments(raw)
            check_pragmas(s, where, code)
            check_defines(s, where, code)
            check_guard_only(s, where, code, sqlite_ids)
            check_directives(s, where, code)
            check_path_enders(s, where, code)
            check_assumes(s, where, raw, code, allow_setup=False)
            check_zero_fill(s, where, code)
            check_function_defs(s, where, code, sqlite_ids)
            if sub == 'proofs/include' and re.search(r'__CPROVER_(requires|ensures|assigns|frees)\b', code):
                # B2 (Zach, 2026-11-10): under the legacy engine (T-006) a clause here would attach to a SQLite function
                s.bad(where, 'no function contract clauses in proofs/include/ (contracts live in proofs/contracts/<fn>.h '
                             'as contract_<fn>)')
    pp = os.path.join(s.root, 'proofs', 'include', 'proof.h')
    if os.path.exists(pp):
        body = strip_comments(open(pp).read())
        defs = [ln.strip() for ln in body.split('\n') if ln.strip().startswith('#') and 'define' in ln]
        if defs != ['#define PROOF_H', '#define PROOF(...) __VA_ARGS__']:
            s.bad('proofs/include/proof.h', 'must define only PROOF(...) as __VA_ARGS__ (found %s)' % defs)


def span_clause_problems(body, pred_names):
    """body is the text inside PROOF( ... ). Return a list of problems."""
    probs = []
    t = body.strip()
    order = []
    i = 0
    n = len(t)
    while i < n:
        while i < n and t[i].isspace():
            i += 1
        if i >= n:
            break
        m = re.match(r'(__CPROVER_assigns|__CPROVER_loop_invariant|__CPROVER_decreases)\s*\(', t[i:])
        if not m:
            probs.append('span holds something other than contract clauses: %r' % t[i:i + 40])
            return probs
        k = i + m.end() - 1
        e = balanced(t, k)
        if e < 0:
            probs.append('unbalanced clause')
            return probs
        order.append((m.group(1), t[k + 1:e - 1]))
        i = e
    kinds = [k for k, _ in order]
    if not kinds:
        probs.append('empty PROOF span')
        return probs
    seq = ''.join({'__CPROVER_assigns': 'a', '__CPROVER_loop_invariant': 'i', '__CPROVER_decreases': 'd'}[k] for k in kinds)
    if not re.fullmatch(r'ai+d', seq):
        probs.append('clauses must be __CPROVER_assigns, one or more __CPROVER_loop_invariant, __CPROVER_decreases, in that order (got %s)' % kinds)
    for kind, expr in order:
        e2 = re.sub(r'__CPROVER_(forall|exists)\s*\{[^{}]*\}', ' Q ', expr)
        if re.search(r'[;{}]', e2):
            probs.append('%s holds ; or braces outside a quantifier' % kind)
        if re.search(r'\+\+|--', e2):
            probs.append('%s holds ++ or --' % kind)
        if re.search(r'(?<![=!<>])=(?!=)', e2.replace('==>', '')):
            probs.append('%s holds an assignment' % kind)
        for fm in re.finditer(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(', e2):
            f = fm.group(1)
            if f not in LOOP_FUNCS and f not in pred_names and not re.fullmatch(r'(u8|u16|u32|u64|i8|i16|i64|int|unsigned|char|long|short|size_t)', f):
                probs.append('%s calls %s(), which is neither a CPROVER primitive nor a predicate in proofs/include/preds.h' % (kind, f))
        if re.search(r'__CPROVER_(assume|assert)', e2):
            probs.append('%s holds an assume or assert' % kind)
    return probs


def span_placement(text, s, e):
    """Where is the span? Return 'for', 'while', 'do' or an error string."""
    j = s - 1
    while j >= 0 and text[j].isspace():
        j -= 1
    k = e
    while k < len(text) and text[k].isspace():
        k += 1
    after = text[k:k + 1]
    if text[max(0, j - 1):j + 1] == 'do' and (j - 2 < 0 or not (text[j - 2].isalnum() or text[j - 2] == '_')):
        if after != '{':
            return 'a do-while span must be followed by the loop body\'s {'
        return 'do'
    if j >= 0 and text[j] == ')':
        depth = 0
        q = j
        while q >= 0:
            if text[q] == ')':
                depth += 1
            elif text[q] == '(':
                depth -= 1
                if depth == 0:
                    break
            q -= 1
        r = q - 1
        while r >= 0 and text[r].isspace():
            r -= 1
        w = re.search(r'([A-Za-z_][A-Za-z0-9_]*)$', text[max(0, r - 10):r + 1])
        if w and w.group(1) in ('for', 'while'):
            if after == ';':
                return 'a span after a do-while condition does not parse in CBMC 6.11; put it after `do`'
            return w.group(1)
    return 'a PROOF span must sit between a loop header and its body'


def check_overlay_spans(s, overlay_path, all_cards, card=None, base=None):
    data = open(overlay_path, 'rb').read()
    text = data.decode('latin-1')
    try:
        spans = ov.find_spans(data)
    except ov.SpanError as e:
        s.bad('overlay/sqlite3.c', str(e))
        return
    for p in ov.span_lexical_problems(data, spans):
        s.bad('overlay/sqlite3.c', p)
    upstream = open(os.path.join(s.root, 'upstream', 'sqlite3.c'), 'rb').read()
    allowed_fns = set()
    for c in all_cards.values():
        allowed_fns.update(c.functions)
    ranges = ov.function_ranges(upstream, sorted(allowed_fns))
    lm = ov.LineMap(data)
    pred_names = set()
    pp = os.path.join(s.root, 'proofs', 'include', 'preds.h')
    if os.path.exists(pp):
        pc = strip_comments(open(pp).read())
        pred_names = set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(', pc))
        pred_names -= C_KEYWORDS

    def fn_at(upline):
        for f, (a, b) in ranges.items():
            if a <= upline <= b:
                return f
        return None

    cur = []
    for (st, en) in spans:
        line = lm.upstream_line(text.count('\n', 0, st) + 1)
        where = 'overlay/sqlite3.c:%d (upstream line)' % line
        body = text[st + len('PROOF('):en - 1]
        for p in span_clause_problems(body, pred_names):
            s.bad(where, p)
        pl = span_placement(text, st, en)
        if pl not in ('for', 'while', 'do'):
            s.bad(where, pl)
        f = fn_at(line)
        if f is None:
            s.bad(where, 'PROOF span outside every card\'s functions')
        cur.append((f, text[st:en]))
    if card and base:
        try:
            old = subprocess.run(['git', '-C', s.root, 'show', '%s:overlay/sqlite3.c' % base],
                                 capture_output=True, check=True).stdout
        except subprocess.CalledProcessError as e:
            s.bad('overlay/sqlite3.c', 'cannot read %s:overlay/sqlite3.c: %s' % (base, e.stderr.decode()[:200]))
            return
        olm = ov.LineMap(old)
        otext = old.decode('latin-1')
        prev = []
        for st, en in ov.find_spans(old):
            prev.append((fn_at(olm.upstream_line(otext.count('\n', 0, st) + 1)), otext[st:en]))
        mine = set(all_cards[card].functions) if card in all_cards else set()
        from collections import Counter
        a, b = Counter(prev), Counter(cur)
        for (f, sp), cnt in ((a - b) + (b - a)).items():
            if f not in mine:
                s.bad('overlay/sqlite3.c', 'PROOF span changed in %s, which card %s does not name' % (f, card))


def check_replacements(s, all_cards, card_proofs):
    enforced = set()
    for cid, proofs in card_proofs.items():
        for p in proofs:
            enforced.update(p.enforced)
    proved = set()
    for c in all_cards.values():
        proved.update(c.functions)
    for cid, proofs in card_proofs.items():
        for p in proofs:
            for r in p.replace:
                fn = r.split('/')[0]
                if not os.path.exists(os.path.join(s.root, 'proofs', 'contracts', fn + '.h')):
                    s.bad('proofs/%s/Makefile' % cid, '%s replaces %s with a contract not in proofs/contracts/%s.h' % (p.name, fn, fn))
                if fn in proved and fn not in enforced:
                    s.bad('proofs/%s/Makefile' % cid, '%s replaces %s, but no card\'s proof ENFORCEs contract_%s' % (p.name, fn, fn))
    return enforced


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=os.path.dirname(TOOLS))
    ap.add_argument('--card')
    ap.add_argument('--base')
    ap.add_argument('--overlay')
    a = ap.parse_args()
    s = Scan(os.path.abspath(a.root))
    overlay_path = a.overlay or os.path.join(s.root, 'overlay', 'sqlite3.c')
    otext = open(overlay_path, 'rb').read().decode('latin-1')
    sqlite_ids = sqlite_identifiers(otext)
    s.overlay_macros = function_like_macros(otext)
    s.overlay_defines = defined_names(otext)
    try:
        all_cards = cardlib.load_all(s.root)
    except cardlib.CardFormatError as e:
        s.bad('cards/', str(e))
        all_cards = {}
    for prob in cardlib.depends_problems(all_cards):
        s.bad('cards/', prob)
    check_checks(s)
    check_configs(s)
    check_pragmas(s, 'overlay/sqlite3.c', '\n'.join(otext[st:en] for st, en in ov.find_spans(otext.encode('latin-1'))))
    card_dirs = sorted(d for d in os.listdir(os.path.join(s.root, 'proofs')) if re.match(r'^C-[0-9]{2}$', d)
                       and os.path.isdir(os.path.join(s.root, 'proofs', d)))
    card_proofs = {}
    for d in card_dirs:
        cd = os.path.join(s.root, 'proofs', d)
        if a.card and d != a.card:
            try:
                card_proofs[d] = prove.load_card(cd)[1]
            except prove.CardError:
                pass
            continue
        _, proofs = check_card_makefile(s, cd)
        card_proofs[d] = proofs
        check_card_dir_files(s, cd)
        check_harness(s, cd, sqlite_ids, proofs, all_cards.get(d))
        check_cover(s, cd, all_cards.get(d), proofs)
    enforced = check_replacements(s, all_cards, card_proofs)
    check_contract_files(s, sqlite_ids, all_cards, enforced)
    check_preds(s, sqlite_ids)
    check_overlay_spans(s, overlay_path, all_cards, a.card, a.base)
    check_tree_files(s)
    if a.base:
        check_preds_growth(s, a.base)
    for p in s.problems:
        print('scan: ' + p)
    if not s.problems:
        print('scan: %d card directories, contracts, predicates and overlay spans pass' % len(card_dirs))
    print('RESULT scan %s %d problems' % ('FAIL' if s.problems else 'PASS', len(s.problems)))
    return 1 if s.problems else 0


if __name__ == '__main__':
    sys.exit(main())
