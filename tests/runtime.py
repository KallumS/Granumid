"""Runtime for the mini EEL2 interpreter: memory, strings, builtins, and a JSFX
host stub (sliders, MIDI, file I/O, gfx no-ops)."""
import math, os, re, time
from eel2 import tokenize, Parser

TRUE_EPS = 0.00001
MEMSIZE = 500000

def truthy(v):  return abs(v) >= TRUE_EPS
def i32(v):     return int(v) & 0xFFFFFFFF
def toint(v):   return int(v)

class EelError(Exception): pass

class Frame(dict): pass

class Interp:
    def __init__(self):
        self.mem = [0.0] * MEMSIZE
        self.g = {}
        self.funcs = {}
        self.strs = {}
        self.named = {}
        self.next_named = 3000
        self.next_lit = 5000
        self.lits = {}
        self.tmp = 2000
        self.midi_out = []          # (offset, m1, m2, m3)
        self.midi_in = []
        self.files = {}             # handle -> [tokens], pos
        self.file_paths = {}        # index -> path
        self.nfh = 1
        self.loopguard = 4000000
        self.gfx_stub = 0
        self.trace_calls = 0

    # ---------------------------------------------------------------- strings
    def lit(self, s):
        if s not in self.lits:
            self.lits[s] = self.next_lit
            self.strs[self.next_lit] = s
            self.next_lit += 1
        return float(self.lits[s])

    def nstr(self, name):
        if name not in self.named:
            self.named[name] = self.next_named
            self.strs[self.next_named] = ''
            self.next_named += 1
        return float(self.named[name])

    def sget(self, sid): return self.strs.get(int(sid), '')
    def sset(self, sid, v): self.strs[int(sid)] = v

    # ------------------------------------------------------------------- eval
    def run(self, node, f):
        return self.ev(node, f)

    def ev(self, n, f):
        k = n[0]
        if k == 'num':    return n[1]
        if k == 'var':    return self.getvar(n[1], f)
        if k == 'strlit': return self.lit(n[1])
        if k == 'nstr':   return self.nstr(n[1])
        if k == 'tmpstr':
            self.tmp = 2000 + ((self.tmp - 2000 + 1) % 64)
            self.strs.setdefault(self.tmp, '')
            return float(self.tmp)
        if k == 'block':
            r = 0.0
            for s in n[1]: r = self.ev(s, f)
            return r
        if k == 'index':
            a = int(self.ev(n[1], f) + self.ev(n[2], f) + 0.00001)
            if a < 0 or a >= MEMSIZE: raise EelError(f'memory index out of range: {a}')
            return self.mem[a]
        if k == 'if':
            if truthy(self.ev(n[1], f)): return self.ev(n[2], f)
            return self.ev(n[3], f) if n[3] is not None else 0.0
        if k == 'logic':
            op, an, bn = n[1], n[2], n[3]
            av = self.ev(an, f)
            if op == '&&':
                if not truthy(av): return 0.0
                return 1.0 if truthy(self.ev(bn, f)) else 0.0
            if truthy(av): return 1.0
            return 1.0 if truthy(self.ev(bn, f)) else 0.0
        if k == 'un':
            v = self.ev(n[2], f)
            if n[1] == '!': return 0.0 if truthy(v) else 1.0
            if n[1] == '-': return -v
            return v
        if k == 'bin':   return self.binop(n[1], n[2], n[3], f)
        if k == 'assign':return self.assign(n[1], n[2], n[3], f)
        if k == 'call':  return self.call(n[1], n[2], f)
        if k == 'func':
            self.funcs[n[1]] = n
            return 0.0
        raise EelError(f'unknown node {k}')

    def getvar(self, name, f):
        if f is not None and name in f: return f[name]
        return self.g.get(name, 0.0)

    def setvar(self, name, v, f):
        if f is not None and name in f: f[name] = v
        else: self.g[name] = v
        return v

    def binop(self, op, an, bn, f):
        a = self.ev(an, f)
        b = self.ev(bn, f)
        if op == '+': return a + b
        if op == '-': return a - b
        if op == '*': return a * b
        if op == '/': return a / b if b != 0 else 0.0
        if op == '^': 
            try: return math.pow(a, b)
            except (ValueError, OverflowError): return 0.0
        if op == '%':
            ib = int(abs(b))
            return float(int(abs(a)) % ib) if ib else 0.0
        if op == '<<': return float(i32(a) << (int(b) & 31))
        if op == '>>': return float(int(a) >> (int(b) & 31))
        if op == '|': return float(int(a) | int(b))
        if op == '&': return float(int(a) & int(b))
        if op == '~': return float(int(a) ^ int(b))
        if op == '==': return 1.0 if abs(a - b) < TRUE_EPS else 0.0
        if op == '!=': return 0.0 if abs(a - b) < TRUE_EPS else 1.0
        if op == '===': return 1.0 if a == b else 0.0
        if op == '!==': return 0.0 if a == b else 1.0
        if op == '<': return 1.0 if a < b else 0.0
        if op == '>': return 1.0 if a > b else 0.0
        if op == '<=': return 1.0 if a <= b else 0.0
        if op == '>=': return 1.0 if a >= b else 0.0
        raise EelError(f'bad operator {op}')

    def assign(self, op, lhs, rhs, f):
        v = self.ev(rhs, f)
        if op != '=':
            cur = self.ev(lhs, f)
            o = op[0]
            v = self.binop(o, ('num', cur), ('num', v), f)
        if lhs[0] == 'var':
            return self.setvar(lhs[1], v, f)
        if lhs[0] == 'index':
            a = int(self.ev(lhs[1], f) + self.ev(lhs[2], f) + 0.00001)
            if a < 0 or a >= MEMSIZE: raise EelError(f'memory write out of range: {a}')
            self.mem[a] = v
            return v
        if lhs[0] == 'nstr':
            self.sset(self.nstr(lhs[1]), self.sget(v)); return v
        if lhs[0] == 'call' and lhs[1] == 'slider':
            idx = int(self.ev(lhs[2][0], f))
            self.g['slider%d' % idx] = v
            return v
        raise EelError(f'cannot assign to {lhs[0]}')

    # ------------------------------------------------------------------ calls
    def call(self, name, args, f):
        if name in RAW: return RAW[name](self, args, f)
        if name in self.funcs:
            fn = self.funcs[name]
            _, _, params, locs, body = fn
            nf = Frame()
            for i, p in enumerate(params):
                nf[p] = self.ev(args[i], f) if i < len(args) else 0.0
            key = '__loc__' + name
            store = self.g.setdefault(key, {})
            for l in locs:
                nf[l] = store.get(l, 0.0)
            r = self.ev(body, nf)
            for l in locs:
                store[l] = nf[l]
            return r
        if name in BUILTIN:
            return BUILTIN[name](self, [self.ev(a, f) for a in args])
        if name.startswith('gfx_') or name.startswith('mouse'):
            for a in args: self.ev(a, f)
            return 0.0
        raise EelError(f'unknown function {name}()')

# -------------------------------------------------------------- raw builtins
def _loop(ip, args, f):
    n = int(ip.ev(args[0], f))
    body = args[1] if len(args) > 1 else ('num', 0.0)
    r = 0.0
    n = min(n, 1000000)
    for _ in range(max(n, 0)):
        r = ip.ev(body, f)
    return r

def _while(ip, args, f):
    r = 0.0
    cnt = 0
    if len(args) >= 2:
        while truthy(ip.ev(args[0], f)):
            r = ip.ev(args[1], f)
            cnt += 1
            if cnt > 1000000: raise EelError('while() exceeded 1,000,000 iterations')
    else:
        while True:
            r = ip.ev(args[0], f)
            cnt += 1
            if not truthy(r): break
            if cnt > 1000000: raise EelError('while() exceeded 1,000,000 iterations')
    return r

def _midirecv(ip, args, f):
    if not ip.midi_in: return 0.0
    off, m1, m2, m3 = ip.midi_in.pop(0)
    names = [a[1] for a in args if a[0] == 'var']
    vals = [off, m1, m2, m3] if len(args) >= 4 else [off, m1, m2 + m3 * 256]
    for nm, v in zip(names, vals): ip.setvar(nm, float(v), f)
    return float(m1)

def _file_var(ip, args, f):
    h = int(ip.ev(args[0], f))
    fh = ip.files.get(h)
    v = 0.0
    if fh and fh['pos'] < len(fh['toks']):
        v = fh['toks'][fh['pos']]; fh['pos'] += 1
    if args[1][0] == 'var': ip.setvar(args[1][1], v, f)
    return v

RAW = {'loop': _loop, 'while': _while, 'midirecv': _midirecv, 'file_var': _file_var}

# ------------------------------------------------------------ value builtins
def _sprintf(ip, a):
    dst, fmt = a[0], ip.sget(a[1])
    out, ai, i = [], 2, 0
    while i < len(fmt):
        c = fmt[i]
        if c != '%': out.append(c); i += 1; continue
        j = i + 1
        while j < len(fmt) and fmt[j] not in 'diufeEgGxXcs%': j += 1
        spec = fmt[i:j + 1]
        conv = fmt[j] if j < len(fmt) else '%'
        i = j + 1
        if conv == '%': out.append('%'); continue
        v = a[ai] if ai < len(a) else 0.0
        ai += 1
        if conv in 'diu': out.append((spec[:-1] + 'd') % int(v))
        elif conv in 'xX': out.append(spec % int(v))
        elif conv == 'c': out.append(chr(int(v) & 0xFF))
        elif conv == 's': out.append(spec % ip.sget(v))
        else: out.append(spec % float(v))
    ip.sset(dst, ''.join(out))
    return dst

def _memset(ip, a):
    d, v, l = int(a[0]), a[1], int(a[2])
    for i in range(d, min(d + l, MEMSIZE)): ip.mem[i] = v
    return a[0]

def _memcpy(ip, a):
    d, s, l = int(a[0]), int(a[1]), int(a[2])
    ip.mem[d:d + l] = ip.mem[s:s + l]
    return a[0]

def _file_open(ip, a):
    idx = int(a[0])
    path = ip.file_paths.get(idx)
    if path is None or not os.path.exists(path): return -1.0
    txt = open(path).read()
    toks = []
    for line in txt.splitlines():
        line = re.split(r'[;#]', line, 1)[0]
        for t in re.split(r'[,\s]+', line.strip()):
            if not t: continue
            if '=' in t: continue
            try: toks.append(float(t))
            except ValueError: pass
    h = ip.nfh; ip.nfh += 1
    ip.files[h] = {'toks': toks, 'pos': 0, 'text': True}
    return float(h)

def _file_avail(ip, a):
    fh = ip.files.get(int(a[0]))
    if not fh: return 0.0
    return 1.0 if fh['pos'] < len(fh['toks']) else 0.0

def _file_mem(ip, a):
    h, off, ln = int(a[0]), int(a[1]), int(a[2])
    fh = ip.files.get(h)
    if not fh: return 0.0
    n = min(ln, len(fh['toks']) - fh['pos'])
    for i in range(n): ip.mem[off + i] = fh['toks'][fh['pos'] + i]
    fh['pos'] += n
    return float(n)

def _midisend(ip, a):
    off = int(a[0]); m1 = int(a[1])
    if len(a) >= 4: m2, m3 = int(a[2]), int(a[3])
    else:
        v = int(a[2]); m2, m3 = v & 0xFF, (v >> 8) & 0xFF
    ip.midi_out.append((off, m1, m2, m3))
    return a[1]

def _slider(ip, a): return ip.g.get('slider%d' % int(a[0]), 0.0)

BUILTIN = {
    'sin': lambda ip, a: math.sin(a[0]), 'cos': lambda ip, a: math.cos(a[0]),
    'tan': lambda ip, a: math.tan(a[0]), 'asin': lambda ip, a: math.asin(max(-1, min(1, a[0]))),
    'acos': lambda ip, a: math.acos(max(-1, min(1, a[0]))), 'atan': lambda ip, a: math.atan(a[0]),
    'atan2': lambda ip, a: math.atan2(a[0], a[1]),
    'sqr': lambda ip, a: a[0] * a[0], 'sqrt': lambda ip, a: math.sqrt(max(a[0], 0.0)),
    'pow': lambda ip, a: (math.pow(a[0], a[1]) if not (a[0] == 0 and a[1] < 0) else 0.0),
    'exp': lambda ip, a: math.exp(min(a[0], 700)), 'log': lambda ip, a: math.log(a[0]) if a[0] > 0 else 0.0,
    'log10': lambda ip, a: math.log10(a[0]) if a[0] > 0 else 0.0,
    'abs': lambda ip, a: abs(a[0]), 'min': lambda ip, a: min(a[0], a[1]), 'max': lambda ip, a: max(a[0], a[1]),
    'sign': lambda ip, a: float((a[0] > 0) - (a[0] < 0)),
    'rand': lambda ip, a: __import__('random').random() * (a[0] if a else 1.0),
    'floor': lambda ip, a: float(math.floor(a[0])), 'ceil': lambda ip, a: float(math.ceil(a[0])),
    'invsqrt': lambda ip, a: 1.0 / math.sqrt(a[0]) if a[0] > 0 else 0.0,
    'memset': _memset, 'memcpy': _memcpy,
    'freembuf': lambda ip, a: 0.0, '__memtop': lambda ip, a: float(MEMSIZE),
    'strlen': lambda ip, a: float(len(ip.sget(a[0]))),
    'strcpy': lambda ip, a: (ip.sset(a[0], ip.sget(a[1])), a[0])[1],
    'strcat': lambda ip, a: (ip.sset(a[0], ip.sget(a[0]) + ip.sget(a[1])), a[0])[1],
    'strcmp': lambda ip, a: float((ip.sget(a[0]) > ip.sget(a[1])) - (ip.sget(a[0]) < ip.sget(a[1]))),
    'stricmp': lambda ip, a: float((ip.sget(a[0]).lower() > ip.sget(a[1]).lower()) - (ip.sget(a[0]).lower() < ip.sget(a[1]).lower())),
    'str_getchar': lambda ip, a: float(ord(ip.sget(a[0])[int(a[1])])) if 0 <= int(a[1]) < len(ip.sget(a[0])) else 0.0,
    'str_setchar': lambda ip, a: _setchar(ip, a),
    'sprintf': _sprintf,
    'strcpy_fromslider': lambda ip, a: (ip.sset(a[0], ip.slider_name(int(a[1]))), a[0])[1],
    'slider': _slider,
    'sliderchange': lambda ip, a: 0.0, 'slider_automate': lambda ip, a: 0.0, 'slider_show': lambda ip, a: 0.0,
    'midisend': _midisend, 'midisend_buf': lambda ip, a: 0.0, 'midisend_str': lambda ip, a: 0.0,
    'file_open': _file_open, 'file_close': lambda ip, a: ip.files.pop(int(a[0]), None) and 0.0,
    'file_avail': _file_avail, 'file_mem': _file_mem,
    'file_rewind': lambda ip, a: 0.0, 'file_text': lambda ip, a: 1.0, 'file_string': lambda ip, a: 0.0,
    'time_precise': lambda ip, a: time.time(), 'time': lambda ip, a: time.time(),
}

def _setchar(ip, a):
    s = ip.sget(a[0]); off = int(a[1]); ch = chr(int(a[2]) & 0xFF)
    if off == len(s): s += ch
    elif 0 <= off < len(s): s = s[:off] + ch + s[off + 1:]
    ip.sset(a[0], s)
    return a[0]

Interp.slider_name = lambda self, idx: os.path.basename(self.file_paths.get(int(self.g.get('slider1', 0.0)), ''))
