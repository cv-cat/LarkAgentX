"""Parse the JS schema-registry literals from schemas_all.json and generate .proto files."""
import json
import os
import re
from collections import defaultdict

DIR = os.environ.get('LARK_WORK_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'work'))
OUT_DIR = os.environ.get('LARK_PROTO_OUT', os.path.dirname(os.path.abspath(__file__)) + '/out/proto')

# ---------- JS object literal parser ----------

class JSParser:
    def __init__(self, s):
        self.s = s
        self.i = 0
        self.n = len(s)

    def skip_ws(self):
        while self.i < self.n and self.s[self.i] in ' \t\r\n':
            self.i += 1

    def peek(self):
        self.skip_ws()
        return self.s[self.i] if self.i < self.n else ''

    def parse_value(self):
        self.skip_ws()
        c = self.s[self.i]
        if c == '{':
            return self.parse_object()
        if c == '[':
            return self.parse_array()
        if c in '"\'':
            return self.parse_string()
        if c == '!':  # !0 -> true, !1 -> false
            if self.s[self.i:self.i+2] == '!0':
                self.i += 2
                return True
            if self.s[self.i:self.i+2] == '!1':
                self.i += 2
                return False
            raise ValueError('bad ! at %d' % self.i)
        # number or identifier
        m = re.match(r'-?(?:0x[0-9a-fA-F]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)', self.s[self.i:])
        if m:
            tok = m.group(0)
            self.i += len(tok)
            if tok.startswith('0x') or tok.startswith('-0x'):
                return int(tok, 16)
            return float(tok) if ('.' in tok or 'e' in tok or 'E' in tok) else int(tok)
        m = re.match(r'[A-Za-z_$][A-Za-z0-9_$.]*', self.s[self.i:])
        if m:
            tok = m.group(0)
            self.i += len(tok)
            if tok == 'true':
                return True
            if tok == 'false':
                return False
            if tok in ('undefined', 'null', 'void'):
                return None
            return {'__raw__': tok}
        raise ValueError('unexpected %r at %d' % (self.s[self.i:self.i+20], self.i))

    def parse_string(self):
        q = self.s[self.i]
        self.i += 1
        out = []
        while self.i < self.n:
            c = self.s[self.i]
            if c == '\\':
                nxt = self.s[self.i+1]
                if nxt == 'n':
                    out.append('\n')
                elif nxt == 't':
                    out.append('\t')
                elif nxt == 'r':
                    out.append('\r')
                elif nxt == 'u':
                    out.append(chr(int(self.s[self.i+2:self.i+6], 16)))
                    self.i += 4
                elif nxt == 'x':
                    out.append(chr(int(self.s[self.i+2:self.i+4], 16)))
                    self.i += 2
                else:
                    out.append(nxt)
                self.i += 2
                continue
            if c == q:
                self.i += 1
                return ''.join(out)
            out.append(c)
            self.i += 1
        raise ValueError('unterminated string')

    def parse_key(self):
        self.skip_ws()
        c = self.s[self.i]
        if c in '"\'':
            return self.parse_string()
        m = re.match(r'[A-Za-z_$][A-Za-z0-9_$]*|\d+', self.s[self.i:])
        if not m:
            raise ValueError('bad key at %d: %r' % (self.i, self.s[self.i:self.i+20]))
        self.i += len(m.group(0))
        return m.group(0)

    def parse_object(self):
        obj = {}
        assert self.s[self.i] == '{'
        self.i += 1
        while True:
            self.skip_ws()
            if self.s[self.i] == '}':
                self.i += 1
                return obj
            key = self.parse_key()
            self.skip_ws()
            assert self.s[self.i] == ':', 'expected : at %d' % self.i
            self.i += 1
            obj[key] = self.parse_value()
            self.skip_ws()
            if self.s[self.i] == ',':
                self.i += 1

    def parse_array(self):
        arr = []
        assert self.s[self.i] == '['
        self.i += 1
        while True:
            self.skip_ws()
            if self.s[self.i] == ']':
                self.i += 1
                return arr
            arr.append(self.parse_value())
            self.skip_ws()
            if self.s[self.i] == ',':
                self.i += 1


# ---------- proto generation ----------

SCALARS = {
    'string': 'string', 'bytes': 'bytes', 'bool': 'bool',
    'int32': 'int32', 'int64': 'int64', 'uint32': 'uint32', 'uint64': 'uint64',
    'sint32': 'sint32', 'sint64': 'sint64', 'fixed32': 'fixed32', 'fixed64': 'fixed64',
    'sfixed32': 'sfixed32', 'sfixed64': 'sfixed64', 'float': 'float', 'double': 'double',
}

def sanitize_ident(name):
    name = re.sub(r'[^A-Za-z0-9_]', '_', str(name))
    if name and name[0].isdigit():
        name = '_' + name
    return name

class ProtoGen:
    def __init__(self, ns, all_namespaces, merged=False):
        self.ns = ns
        self.all_ns = all_namespaces
        self.merged = merged
        self.unresolved = set()
        self.imports = set()
        self.lines = []

    def resolve_type(self, t, local_names):
        if t in SCALARS:
            return SCALARS[t]
        if '.' in t:
            head = t.split('.')[0]
            if head in local_names:  # same-namespace nested ref, e.g. Chat.Type
                return t
            if head in self.all_ns:  # cross-package
                if self.merged:
                    return t  # resolves via enclosing message-scope in merged file
                self.imports.add(head)
                return '.' + t
            self.unresolved.add(t)
            return t
        if t in local_names:
            return t
        # might be a nested type of current message chain - emit as-is and note
        return t

    def gen_enum(self, name, body, indent):
        pad = '    ' * indent
        self.lines.append('%senum %s {' % (pad, sanitize_ident(name)))
        values = body.get('values', {})
        has_zero = any((int(v) if isinstance(v, float) and float(v).is_integer() else v) == 0 for v in values.values())
        if not has_zero:
            self.lines.append('%s    %s_UNSPECIFIED = 0;  // injected: proto3 requires a zero value' % (pad, sanitize_ident(name).upper()))
        for vn, vv in values.items():
            if isinstance(vv, float) and vv.is_integer():
                vv = int(vv)
            self.lines.append('%s    %s = %s;' % (pad, sanitize_ident(vn), vv))
        self.lines.append('%s}' % pad)

    def gen_message(self, name, body, indent):
        pad = '    ' * indent
        ident = sanitize_ident(name)
        self.lines.append('%smessage %s {' % (pad, ident))
        fields = body.get('fields', {})
        nested = body.get('nested', {})
        oneofs = body.get('oneofs', {})
        oneof_fields = set()
        for oname, odef in oneofs.items():
            for fn in (odef.get('oneof') or []):
                oneof_fields.add(fn)
        local_names = set(nested.keys())
        # plain fields first
        for fname, fdef in fields.items():
            if fname in oneof_fields:
                continue
            self.gen_field(fname, fdef, indent + 1, local_names)
        # oneofs
        for oname, odef in oneofs.items():
            self.lines.append('%s    oneof %s {' % (pad, sanitize_ident(oname)))
            for fn in (odef.get('oneof') or []):
                if fn in fields:
                    self.gen_field(fn, fields[fn], indent + 2, local_names, in_oneof=True)
            self.lines.append('%s    }' % pad)
        # nested
        for nname, nbody in nested.items():
            if 'values' in nbody:
                self.gen_enum(nname, nbody, indent + 1)
            else:
                self.gen_message(nname, nbody, indent + 1)
        self.lines.append('%s}' % pad)

    def gen_field(self, fname, fdef, indent, local_names, in_oneof=False):
        pad = '    ' * indent
        t = fdef.get('type', 'bytes')
        fid = fdef.get('id')
        if isinstance(fid, float) and fid.is_integer():
            fid = int(fid)
        rule = fdef.get('rule')
        key_type = fdef.get('keyType')
        opts = fdef.get('options') or {}
        tname = self.resolve_type(t, local_names)
        label = ''
        if rule == 'repeated' and not key_type:
            label = 'repeated '
        comment = ''
        opt_parts = []
        if opts.get('deprecated'):
            opt_parts.append('deprecated = true')
        if opts.get('packed') is False:
            opt_parts.append('packed = false')
        if 'default' in opts and not in_oneof:
            comment = '  // default: %s' % (opts['default'],)
        opt_str = ' [%s]' % ', '.join(opt_parts) if opt_parts else ''
        if key_type:
            kt = self.resolve_type(key_type, local_names)
            self.lines.append('%smap<%s, %s> %s = %s%s;%s' % (pad, kt, tname, sanitize_ident(fname), fid, opt_str, comment))
        else:
            if in_oneof:
                prefix = ''
            elif label:
                prefix = label
            else:
                prefix = 'optional '
            self.lines.append('%s%s%s %s = %s%s;%s' % (pad, prefix, tname, sanitize_ident(fname), fid, opt_str, comment))


def main():
    schemas = json.load(open(os.path.join(DIR, 'schemas_all.json'), encoding='utf-8'))
    by_ns = defaultdict(dict)
    parse_errors = []
    for full_name, body in schemas.items():
        ns, name = full_name.split('.', 1)
        try:
            parsed = JSParser(body).parse_value()
        except Exception as e:
            parse_errors.append((full_name, str(e)))
            continue
        by_ns[ns][name] = parsed

    print('namespaces:', len(by_ns), 'parse errors:', len(parse_errors))
    for e in parse_errors[:10]:
        print('  ERR', e)

    all_ns = set(by_ns.keys())
    os.makedirs(OUT_DIR, exist_ok=True)
    stats = []
    all_unresolved = defaultdict(set)
    for ns in sorted(by_ns):
        gen = ProtoGen(ns, all_ns)
        for name in sorted(by_ns[ns]):
            body = by_ns[ns][name]
            if 'values' in body and 'fields' not in body:
                gen.gen_enum(name, body, 0)
            else:
                gen.gen_message(name, body, 0)
            gen.lines.append('')
        header = ['syntax = "proto3";', '', 'package %s;' % sanitize_ident(ns), '']
        header.append('// Auto-generated from Feishu web-client-next worklet schema registry (2026-07-25)')
        header.append('')
        for imp in sorted(gen.imports - {ns}):
            header.append('import "%s.proto";' % sanitize_ident(imp))
        if gen.imports - {ns}:
            header.append('')
        path = os.path.join(OUT_DIR, '%s.proto' % sanitize_ident(ns))
        open(path, 'w', encoding='utf-8').write('\n'.join(header + gen.lines))
        stats.append((ns, len(by_ns[ns])))
        if gen.unresolved:
            all_unresolved[ns] = gen.unresolved

    print('written %d proto files to %s' % (len(stats), OUT_DIR))
    for ns, cnt in stats:
        print('  %-30s %d' % (ns, cnt))
    if all_unresolved:
        print('unresolved type refs (kept as-is):')
        for ns, s in all_unresolved.items():
            print('  %s: %s' % (ns, sorted(s)[:10]))

    # merged single file (compilable; namespaces wrapped as messages to avoid
    # import cycles and enum-value collisions)
    merged_lines = ['syntax = "proto3";', '', 'package lark;', '',
                    '// Merged view of all namespaces (each namespace wrapped as a message).',
                    '// Auto-generated from Feishu web-client-next worklet schema registry (2026-07-25)', '']
    for ns in sorted(by_ns):
        gen = ProtoGen(ns, all_ns, merged=True)
        merged_lines.append('message %s {' % sanitize_ident(ns))
        for name in sorted(by_ns[ns]):
            body = by_ns[ns][name]
            if 'values' in body and 'fields' not in body:
                gen.gen_enum(name, body, 1)
            else:
                gen.gen_message(name, body, 1)
            gen.lines.append('')
        merged_lines.extend(gen.lines)
        merged_lines.append('}')
        merged_lines.append('')
    open(os.path.join(OUT_DIR, 'lark_all.proto'), 'w', encoding='utf-8').write('\n'.join(merged_lines))
    print('written merged lark_all.proto')

    # break import cycles in per-namespace files (protoc forbids them; the
    # merged lark_all.proto remains the fully compilable version)
    graph = {}
    for ns in by_ns:
        path = os.path.join(OUT_DIR, '%s.proto' % sanitize_ident(ns))
        if not os.path.exists(path):
            continue
        lines = open(path, encoding='utf-8').read().splitlines()
        imps = [re.match(r'import "(.+)\.proto";', l).group(1) for l in lines if re.match(r'import ".+\.proto";', l)]
        graph[ns] = (path, lines, imps)

    def find_cycle():
        visited, stack = set(), []
        def dfs(u):
            visited.add(u)
            stack.append(u)
            for v in graph.get(u, (None, None, []))[2]:
                if v not in graph:
                    continue
                if v in stack:
                    return stack[stack.index(v):] + [v]
                if v not in visited:
                    r = dfs(v)
                    if r:
                        return r
            stack.pop()
            return None
        for u in graph:
            if u not in visited:
                r = dfs(u)
                if r:
                    return r
        return None

    broken = []
    while True:
        cyc = find_cycle()
        if not cyc:
            break
        # drop the import edge from the alphabetically-last file in the cycle
        a, b = cyc[-2], cyc[-1]
        frm, to = (a, b) if a > b else (b, a)
        # ensure 'to' is actually imported by 'frm'; otherwise pick any edge
        edges = [(cyc[i], cyc[i+1]) for i in range(len(cyc)-1)]
        if (frm, to) not in edges:
            frm, to = edges[-1]
        path, lines, imps = graph[frm]
        new_lines = []
        for l in lines:
            if l == 'import "%s.proto";' % to:
                new_lines.append('// import "%s.proto";  // removed to break an import cycle; use lark_all.proto to compile' % to)
                continue
            new_lines.append(l)
        open(path, 'w', encoding='utf-8').write('\n'.join(new_lines))
        graph[frm] = (path, new_lines, [i for i in imps if i != to])
        broken.append((frm, to))
    if broken:
        print('broke import cycles:', broken)

    # fidelity-preserving fixup for the entities<->pan cycle:
    # keep pan -> entities intact; in entities.proto downgrade the two
    # .pan.VisitInfo refs to bytes (field numbers unchanged) so that
    # entities.proto (the core namespace) compiles standalone.
    ent_path = os.path.join(OUT_DIR, 'entities.proto')
    pan_path = os.path.join(OUT_DIR, 'pan.proto')
    if os.path.exists(ent_path) and os.path.exists(pan_path):
        ent = open(ent_path, encoding='utf-8').read()
        ent = ent.replace('.pan.VisitInfo', 'bytes /* orig type: .pan.VisitInfo (see pan.proto) */')
        ent = ent.replace('import "pan.proto";',
                          '// import "pan.proto";  // removed to break the entities<->pan cycle')
        open(ent_path, 'w', encoding='utf-8').write(ent)
        pan = open(pan_path, encoding='utf-8').read()
        pan = pan.replace('// import "entities.proto";  // removed to break an import cycle; use lark_all.proto to compile',
                          'import "entities.proto";')
        open(pan_path, 'w', encoding='utf-8').write(pan)
        print('applied entities/pan cycle fixup')


if __name__ == '__main__':
    main()
