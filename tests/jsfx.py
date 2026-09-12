"""Loads a .jsfx (plus its imports) into the mini EEL2 interpreter."""
import os, re
from eel2 import tokenize, Parser
from runtime import Interp, truthy

SECT = re.compile(r'^@(init|slider|block|sample|serialize|gfx)\b(.*)$')

def split_sections(src):
    header, sections, cur = [], {}, None
    for line in src.splitlines():
        m = SECT.match(line.strip())
        if m:
            cur = m.group(1)
            sections.setdefault(cur, [])
            continue
        (sections[cur] if cur else header).append(line)
    return '\n'.join(header), {k: '\n'.join(v) for k, v in sections.items()}

SLIDER_NUM = re.compile(r'^slider(\d+)\s*:\s*([-+0-9.eE]+)\s*<')
SLIDER_FILE = re.compile(r'^slider(\d+)\s*:\s*/')

def parse_header(header, ip):
    imports = []
    for line in header.splitlines():
        line = line.split('//')[0].strip()
        if line.startswith('import '):
            imports.append(line[7:].strip())
            continue
        m = SLIDER_NUM.match(line)
        if m:
            ip.g['slider%s' % m.group(1)] = float(m.group(2))
            continue
        m = SLIDER_FILE.match(line)
        if m:
            ip.g['slider%s' % m.group(1)] = 0.0
    return imports

class Plugin:
    def __init__(self, path):
        self.ip = Interp()
        self.dir = os.path.dirname(os.path.abspath(path))
        src = open(path).read()
        header, self.sect = split_sections(src)
        imports = parse_header(header, self.ip)
        self.inc = []
        for imp in imports:
            isrc = open(os.path.join(self.dir, imp)).read()
            _, isect = split_sections(isrc)
            self.inc.append((imp, isect))

    def compile(self):
        self.ast = {}
        for name, isect in self.inc:
            for sname, body in isect.items():
                self.ast.setdefault(sname, []).append((name, Parser(tokenize(body)).parse_program()))
        for sname, body in self.sect.items():
            self.ast.setdefault(sname, []).append(('main', Parser(tokenize(body)).parse_program()))

    def run(self, section):
        for _, tree in self.ast.get(section, []):
            self.ip.ev(tree, None)

    def declare_funcs(self):
        """Register every function definition (imports first, main last)."""
        for sname in ('init',):
            for _, tree in self.ast.get(sname, []):
                for node in tree[1]:
                    if node[0] == 'func':
                        self.ip.funcs[node[1]] = node
