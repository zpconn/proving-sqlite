"""Shared helpers for overlay/sqlite3.c: finding PROOF(...) spans, stripping them, and mapping
overlay lines to upstream lines.

A PROOF span is exactly the characters from the token `PROOF(` to its matching `)`. Whitespace
belongs inside the parentheses: deleting the span must leave upstream byte for byte. For example
upstream `while( i<n ){` becomes `while( i<n )PROOF(\n  __CPROVER_assigns(i) ...\n){`.
"""
import bisect
import re

SPAN_START = re.compile(rb'(?<![A-Za-z0-9_])PROOF\(')


class SpanError(Exception):
    pass


def find_spans(data: bytes):
    """Return a list of (start, end) byte offsets of PROOF spans; data[start:end] is the span.
    Parentheses are matched; string and character literals and comments inside are honoured."""
    spans = []
    pos = 0
    while True:
        m = SPAN_START.search(data, pos)
        if not m:
            break
        start = m.start()
        i = m.end()  # just after '('
        depth = 1
        n = len(data)
        while i < n and depth:
            c = data[i:i + 1]
            if c in (b'"', b"'"):
                q = c
                i += 1
                while i < n and data[i:i + 1] != q:
                    if data[i:i + 1] == b'\\':
                        i += 1
                    i += 1
                i += 1
                continue
            if data[i:i + 2] == b'/*':
                j = data.find(b'*/', i + 2)
                if j < 0:
                    raise SpanError('unterminated comment in PROOF span at byte %d' % start)
                i = j + 2
                continue
            if data[i:i + 2] == b'//':
                j = data.find(b'\n', i)
                i = n if j < 0 else j
                continue
            if c == b'(':
                depth += 1
            elif c == b')':
                depth -= 1
            i += 1
        if depth:
            raise SpanError('unbalanced PROOF span starting at byte %d' % start)
        spans.append((start, i))
        pos = i
    return spans


def comment_and_literal_ranges(data: bytes):
    """Byte ranges [start, end) of comments and string/char literals in C source, lexed from the
    top of the file. PROOF( inside one of these is not a real span."""
    out = []
    i = 0
    n = len(data)
    while i < n:
        c = data[i]
        if data.startswith(b'/*', i):
            j = data.find(b'*/', i + 2)
            j = n if j < 0 else j + 2
            out.append((i, j))
            i = j
        elif data.startswith(b'//', i):
            j = data.find(b'\n', i)
            j = n if j < 0 else j
            out.append((i, j))
            i = j
        elif c in (0x22, 0x27):  # " or '
            j = i + 1
            while j < n and data[j] != c and data[j] != 0x0a:
                if data[j] == 0x5c:
                    j += 1
                j += 1
            out.append((i, j + 1))
            i = j + 1
        else:
            i += 1
    return out


def span_lexical_problems(data: bytes, spans):
    """Each span must start in code, not inside a comment or literal, and must itself hold no
    comment, literal, preprocessor '#', or backslash. Returns a list of problem strings."""
    probs = []
    ranges = comment_and_literal_ranges(data)
    starts = [r[0] for r in ranges]
    for s, e in spans:
        k = bisect.bisect_right(starts, s) - 1
        if k >= 0 and ranges[k][0] <= s < ranges[k][1]:
            probs.append('PROOF span at overlay line %d starts inside a comment or literal' % line_of(data, s))
            continue
        body = data[s:e]
        for tok in (b'/*', b'*/', b'//', b'"', b"'", b'#', b'\\'):
            if tok in body:
                probs.append('PROOF span at overlay line %d contains %r' % (line_of(data, s), tok.decode()))
                break
    return probs


def strip_spans(data: bytes):
    spans = find_spans(data)
    out = []
    pos = 0
    for s, e in spans:
        out.append(data[pos:s])
        pos = e
    out.append(data[pos:])
    return b''.join(out), spans


def line_of(data: bytes, offset: int) -> int:
    return data.count(b'\n', 0, offset) + 1


class LineMap:
    """Maps overlay line numbers to upstream line numbers (1-based). A line inside a multi-line
    span maps to the upstream line the span sits on."""

    def __init__(self, overlay: bytes):
        self.spans = find_spans(overlay)
        # newline offsets in overlay that lie inside spans
        self._removed_nl = []
        for s, e in self.spans:
            k = overlay.find(b'\n', s, e)
            while k >= 0:
                self._removed_nl.append(k)
                k = overlay.find(b'\n', k + 1, e)
        self._nl = [m.start() for m in re.finditer(b'\n', overlay)]

    def upstream_line(self, overlay_line: int) -> int:
        # offset of the start of overlay_line
        if overlay_line <= 1:
            start = 0
        else:
            start = self._nl[overlay_line - 2] + 1
        removed = bisect.bisect_left(self._removed_nl, start)
        return overlay_line - removed


def function_ranges(upstream: bytes, names):
    """Return {name: (first_line, last_line)} in upstream for each named function definition:
    from the line that names it to the line of its closing brace. The naming line starts with a
    declaration specifier, contains `name(`, and is followed (before any ';') by the body's '{'."""
    text = upstream.decode('latin-1')
    res = {}
    for name in names:
        pat = re.compile(r'^[A-Za-z_][^\n;]*[ *]' + re.escape(name) + r'\(', re.M)
        for m in pat.finditer(text):
            i = _skip_to_body(text, m.end())
            if i is None:
                continue
            j = _match_brace(text, i)
            res[name] = (text.count('\n', 0, m.start()) + 1, text.count('\n', 0, j) + 1)
            break
    return res


def _skip_code(text, i):
    """If text[i] starts a comment or literal, return the index just past it, else None."""
    if text.startswith('/*', i):
        j = text.find('*/', i + 2)
        return len(text) if j < 0 else j + 2
    if text.startswith('//', i):
        j = text.find('\n', i)
        return len(text) if j < 0 else j
    c = text[i]
    if c in '"\'':
        j = i + 1
        while j < len(text) and text[j] != c:
            if text[j] == '\\':
                j += 1
            j += 1
        return j + 1
    return None


def _skip_to_body(text, i):
    """From just after `name(`, skip the parameter list; return the index of the body's '{', or
    None if a ';' comes first (a declaration)."""
    depth = 1
    n = len(text)
    while i < n:
        k = _skip_code(text, i)
        if k is not None:
            i = k
            continue
        c = text[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif depth == 0 and c == ';':
            return None
        elif depth == 0 and c == '{':
            return i
        i += 1
    return None


def _match_brace(text, i):
    depth = 0
    n = len(text)
    while i < n:
        k = _skip_code(text, i)
        if k is not None:
            i = k
            continue
        c = text[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n - 1
