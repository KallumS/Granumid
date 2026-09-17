"""A small EEL2 (JSFX) interpreter - enough of the language to execute and test
Midular's engine outside REAPER."""
import math, re, sys

# ------------------------------------------------------------------ tokenizer
KEYWORDS = {'function', 'local', 'instance', 'globals', 'global'}
OPS = ['===', '!==', '<<=', '>>=', '==', '!=', '<=', '>=', '<<', '>>', '&&', '||',
       '+=', '-=', '*=', '/=', '%=', '^=', '|=', '&=', '~=',
       '+', '-', '*', '/', '%', '^', '<', '>', '!', '&', '|', '~', '?', ':',
       '(', ')', '[', ']', ',', ';', '=']

class Tok:
    __slots__ = ('k', 'v', 'line')
    def __init__(self, k, v, line): self.k, self.v, self.line = k, v, line
    def __repr__(self): return f'{self.k}:{self.v!r}'

def tokenize(src):
    toks, i, n, line = [], 0, len(src), 1
    while i < n:
        c = src[i]
        if c == '\n':
            line += 1; i += 1; continue
        if c in ' \t\r':
            i += 1; continue
        if src.startswith('//', i):
            j = src.find('\n', i); i = n if j < 0 else j; continue
        if src.startswith('/*', i):
            j = src.find('*/', i + 2)
            if j < 0: j = n
            line += src.count('\n', i, j); i = j + 2; continue
        if c == '"':
            j, buf = i + 1, []
            while j < n and src[j] != '"':
                if src[j] == '\\' and j + 1 < n:
                    e = src[j + 1]
                    buf.append({'n': '\n', 't': '\t', '\\': '\\', '"': '"'}.get(e, e)); j += 2
                else:
                    buf.append(src[j]); j += 1
            toks.append(Tok('str', ''.join(buf), line)); i = j + 1; continue
        if c == "'":
            j = src.find("'", i + 1)
            if j < 0: raise SyntaxError(f'line {line}: unterminated char literal')
            v = 0
            for ch in src[i + 1:j]: v = v * 256 + ord(ch)
            toks.append(Tok('num', float(v), line)); i = j + 1; continue
        if c == '#':
            m = re.match(r'#[A-Za-z_][A-Za-z0-9_.]*', src[i:])
            if m:
                toks.append(Tok('nstr', m.group(0), line)); i += m.end()
            else:
                toks.append(Tok('tmpstr', '#', line)); i += 1
            continue
        if c == '$':
            m = re.match(r"\$x[0-9A-Fa-f]+", src[i:])
            if m: toks.append(Tok('num', float(int(m.group(0)[2:], 16)), line)); i += m.end(); continue
            m = re.match(r"\$'(.)'", src[i:])
            if m: toks.append(Tok('num', float(ord(m.group(1))), line)); i += m.end(); continue
            m = re.match(r"\$~(\d+)", src[i:])
            if m: toks.append(Tok('num', float((1 << int(m.group(1))) - 1), line)); i += m.end(); continue
            m = re.match(r"\$(pi|phi|e)\b", src[i:])
            if m:
                toks.append(Tok('num', {'pi': math.pi, 'phi': (1 + 5 ** .5) / 2, 'e': math.e}[m.group(1)], line))
                i += m.end(); continue
            raise SyntaxError(f'line {line}: bad $ escape')
        m = re.match(r'0[xX][0-9A-Fa-f]+', src[i:])
        if m: toks.append(Tok('num', float(int(m.group(0), 16), ), line)); i += m.end(); continue
        m = re.match(r'(\d+\.\d*|\.\d+|\d+)', src[i:])
        if m:
            # EEL2 has NO scientific notation: "1.0e-9" lexes as the number 1.0
            # followed by the identifier `e`, which REAPER rejects as a syntax
            # error. Reproduce that here rather than silently accepting it.
            if re.match(r'[eE][-+]?\d', src[i + m.end():]):
                raise SyntaxError(
                    'line %d: EEL2 has no scientific notation (%s%s) - '
                    'write the number out in full' %
                    (line, m.group(0), src[i + m.end():i + m.end() + 4]))
            toks.append(Tok('num', float(m.group(0)), line)); i += m.end(); continue
        m = re.match(r'[A-Za-z_][A-Za-z0-9_.]*', src[i:])
        if m:
            w = m.group(0)
            toks.append(Tok('kw' if w in KEYWORDS else 'id', w, line)); i += m.end(); continue
        for op in OPS:
            if src.startswith(op, i):
                toks.append(Tok('op', op, line)); i += len(op); break
        else:
            raise SyntaxError(f'line {line}: unexpected {c!r}')
    toks.append(Tok('eof', None, line))
    return toks

# --------------------------------------------------------------------- parser
# AST nodes are plain tuples: (kind, ...)
class Parser:
    def __init__(self, toks): self.t, self.i = toks, 0
    def peek(self, k=0): return self.t[self.i + k]
    def next(self): self.i += 1; return self.t[self.i - 1]
    def at(self, k, v=None):
        t = self.peek()
        return t.k == k and (v is None or t.v == v)
    def eat(self, k, v=None):
        if self.at(k, v): return self.next()
        return None
    def expect(self, k, v=None):
        t = self.eat(k, v)
        if t is None:
            p = self.peek()
            raise SyntaxError(f'line {p.line}: expected {v or k}, got {p.k}:{p.v!r}')
        return t

    def parse_program(self):
        stmts = []
        while not self.at('eof'):
            if self.at('kw', 'function'):
                stmts.append(self.parse_func())
            else:
                stmts.append(self.parse_assign())
                # EEL2 requires ';' between statements; only the last may omit it.
                if not self.at('op', ';') and not self.at('eof') and not self.at('kw', 'function'):
                    t = self.peek()
                    raise SyntaxError("line %d: missing ';' before %s:%r" % (t.line, t.k, t.v))
                while self.eat('op', ';'): pass
        return ('block', stmts)

    def parse_func(self):
        self.expect('kw', 'function')
        name = self.expect('id').v
        self.expect('op', '(')
        params = []
        while not self.at('op', ')'):
            params.append(self.expect('id').v.rstrip('*'))
            self.eat('op', ',')
        self.expect('op', ')')
        locals_ = []
        while self.at('kw'):
            kw = self.next().v
            self.expect('op', '(')
            while not self.at('op', ')'):
                locals_.append(self.expect('id').v)
                self.eat('op', ',')
            self.expect('op', ')')
        body = self.parse_paren_block()
        while self.eat('op', ';'): pass
        return ('func', name, params, locals_, body)

    def parse_paren_block(self):
        self.expect('op', '(')
        b = self.parse_block()
        self.expect('op', ')')
        return b

    def parse_block(self):
        stmts = []
        while True:
            while self.eat('op', ';'): pass
            if self.at('op', ')') or self.at('eof'): break
            stmts.append(self.parse_assign())
            if not self.at('op', ';'): break
        while self.eat('op', ';'): pass
        return ('block', stmts)

    ASSIGN = {'=', '+=', '-=', '*=', '/=', '%=', '^=', '|=', '&=', '~='}

    def parse_assign(self):
        lhs = self.parse_ternary()
        t = self.peek()
        if t.k == 'op' and t.v in self.ASSIGN:
            self.next()
            rhs = self.parse_assign()
            return ('assign', t.v, lhs, rhs)
        return lhs

    def parse_arg(self):
        stmts = [self.parse_assign()]
        while self.at('op', ';'):
            self.next()
            if self.at('op', ')') or self.at('op', ','):
                break
            stmts.append(self.parse_assign())
        return stmts[0] if len(stmts) == 1 else ('block', stmts)

    def parse_ternary(self):
        c = self.parse_or()
        if self.eat('op', '?'):
            a = self.parse_assign()
            b = None
            if self.eat('op', ':'):
                b = self.parse_assign()
            return ('if', c, a, b)
        return c

    def parse_or(self):
        n = self.parse_cmp()
        while self.at('op', '&&') or self.at('op', '||'):
            op = self.next().v
            n = ('logic', op, n, self.parse_cmp())
        return n

    CMP = {'==', '===', '!=', '!==', '<', '>', '<=', '>='}

    def parse_cmp(self):
        n = self.parse_bit()
        while self.peek().k == 'op' and self.peek().v in self.CMP:
            op = self.next().v
            n = ('bin', op, n, self.parse_bit())
        return n

    def parse_bit(self):
        n = self.parse_add()
        while self.peek().k == 'op' and self.peek().v in ('|', '&', '~'):
            op = self.next().v
            n = ('bin', op, n, self.parse_add())
        return n

    def parse_add(self):
        n = self.parse_mul()
        while self.peek().k == 'op' and self.peek().v in ('+', '-'):
            op = self.next().v
            n = ('bin', op, n, self.parse_mul())
        return n

    def parse_mul(self):
        n = self.parse_shift()
        while self.peek().k == 'op' and self.peek().v in ('*', '/'):
            op = self.next().v
            n = ('bin', op, n, self.parse_shift())
        return n

    def parse_shift(self):
        n = self.parse_mod()
        while self.peek().k == 'op' and self.peek().v in ('<<', '>>'):
            op = self.next().v
            n = ('bin', op, n, self.parse_mod())
        return n

    def parse_mod(self):
        n = self.parse_pow()
        while self.at('op', '%'):
            self.next()
            n = ('bin', '%', n, self.parse_pow())
        return n

    def parse_pow(self):
        n = self.parse_unary()
        if self.at('op', '^'):
            self.next()
            return ('bin', '^', n, self.parse_pow())
        return n

    def parse_unary(self):
        t = self.peek()
        if t.k == 'op' and t.v in ('!', '-', '+'):
            self.next()
            return ('un', t.v, self.parse_unary())
        return self.parse_postfix()

    def parse_postfix(self):
        n = self.parse_primary()
        while self.at('op', '['):
            self.next()
            idx = ('num', 0.0) if self.at('op', ']') else self.parse_assign()
            self.expect('op', ']')
            n = ('index', n, idx)
        return n

    def parse_primary(self):
        t = self.next()
        if t.k == 'num': return ('num', t.v)
        if t.k == 'str': return ('strlit', t.v)
        if t.k == 'nstr': return ('nstr', t.v)
        if t.k == 'tmpstr': return ('tmpstr',)
        if t.k == 'op' and t.v == '(':
            b = self.parse_block()
            self.expect('op', ')')
            return b
        if t.k == 'id':
            if self.at('op', '('):
                self.next()
                args = []
                while not self.at('op', ')'):
                    args.append(self.parse_arg())
                    if not self.eat('op', ','):
                        break
                self.expect('op', ')')
                # while(cond)(body) / loop(n)(body): a trailing parenthesised block
                if self.at('op', '(') and t.v in ('while', 'loop'):
                    args.append(self.parse_paren_block())
                return ('call', t.v, args)
            return ('var', t.v)
        raise SyntaxError(f'line {t.line}: unexpected {t.k}:{t.v!r}')
