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
     (`Ledger: A-NNN`, which must exist in LEDGER.md once LEDGER.md exists);
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
     functions;
 12. files in proofs/C-NN/ but harness.c, Makefile, NOTES.md and the ignored build/ directory; files in
     overlay/ but sqlite3.c; files in proofs/include/ but proof.h and preds.h; symlinks anywhere under
     proofs/, overlay/ or tests/repro/; preprocessor directives a harness or header has no use for
     (#import, #embed, #line, any #pragma but once);
 13. with --base: a change to proofs/include/preds.h that removes or alters anything it held (it may only
     gain predicates);
 14. a card whose functions are not all in some proof's COVER (coverage would not look at them).

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
CARD_DIR_FILES = {'harness.c', 'Makefile', 'NOTES.md'}
ALLOWED_DIRECTIVES = {'include', 'define', 'undef', 'if', 'ifdef', 'ifndef', 'elif', 'else', 'endif', 'error', 'pragma'}


class Scan:
    def __init__(self, root):
        self.root = root
        self.problems = []

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


def setup_statement_problem(stmt):
    """Rule 11: what a SETUP statement may be. None if allowed."""
    t = stmt.strip()
    bad_calls = [c for c in calls_in(t) if c not in SETUP_CALLS]
    if re.search(r'[{}]', t) or re.search(r'\b(if|while|for|switch|do|else|case|return|goto)\b', t):
        return 'a SETUP block holds straight-line statements only'
    if bad_calls:
        return 'a SETUP block may call only malloc and CPROVER primitives (calls %s)' % ', '.join(sorted(set(bad_calls)))
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


def check_entries(s, where, raw, code, proofs, card):
    """Rule 11, for each proof's ENTRY function."""
    defs = {name: (start, b, e) for name, start, b, e in top_level_functions(code)}
    setup_rx = re.compile(r'/\*\s*SETUP\s*\*/')
    end_rx = re.compile(r'/\*\s*END SETUP\s*\*/')
    entry_ranges = []
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
        setups = [m for m in setup_rx.finditer(raw, b, e)]
        ends = [m for m in end_rx.finditer(raw, b, e)]
        if len(setups) != 1 or len(ends) != 1 or ends[0].start() < setups[0].end():
            s.bad(where, 'entry function %s must hold exactly one /* SETUP */ ... /* END SETUP */ block (found %d and %d)' % (
                ent, len(setups), len(ends)))
            continue
        sa, sb = setups[0].start(), ends[0].end()
        for off, st in split_statements(code[b + 1:sa], b + 1):
            if not is_declaration(st):
                s.bad(where, 'line %d: before SETUP, entry function %s may only declare variables: %s' % (
                    code.count('\n', 0, off + len(st) - len(st.lstrip())) + 1, ent, ' '.join(st.split())[:80]))
        for off, st in split_statements(code[setups[0].end():ends[0].start()], setups[0].end()):
            why = setup_statement_problem(st)
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
    for m in setup_rx.finditer(raw):
        if not any(b <= m.start() < e for b, e in entry_ranges):
            s.bad(where, 'line %d: SETUP block outside an entry function' % (raw.count('\n', 0, m.start()) + 1))


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
    check_entries(s, where, raw, code, proofs, card)


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


def check_contract_files(s, sqlite_ids, all_cards, enforced):
    d = os.path.join(s.root, 'proofs', 'contracts')
    proved = set()
    for c in all_cards.values():
        proved.update(c.functions)
    ledger_ids = None
    lp = os.path.join(s.root, 'LEDGER.md')
    if os.path.exists(lp):
        ledger_ids = set(re.findall(r'^## (A-[0-9]{3})\b', open(lp).read(), re.M))
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
            check_directives(s, where, code)
            check_path_enders(s, where, code)
            check_assumes(s, where, raw, code, allow_setup=False)
            check_zero_fill(s, where, code)
            check_function_defs(s, where, code, sqlite_ids)
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
    try:
        all_cards = cardlib.load_all(s.root)
    except cardlib.CardFormatError as e:
        s.bad('cards/', str(e))
        all_cards = {}
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
