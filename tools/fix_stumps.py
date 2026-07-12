#!/usr/bin/env python3
"""Post-process RecompiledFuncs: chain truncated overlapping functions.

N64Recomp truncates a function's decode at the next function symbol in the same
section, WITHOUT emitting the fall-through. Overlapping IDO mid-entries (our
extra_funcs additions for cross-overlay shared tails) therefore become "stumps":
a few instructions, then the C body just ends -- returning early without the
original tail (skipping logic AND the stack restore; this class caused the
boot84 saved-s0 corruption).

For every RECOMP_FUNC body that does not end in a `return;`, look up the
same-section function starting at (last decoded address + 4) and append a
tail-call to it. Run after every tools/recomp_loop.py invocation (see CLAUDE.md
build loop).
"""
import re, glob, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# name -> (section, vram); (section, vram) -> name
dump = open(os.path.join(ROOT, 'syms', 'dump.toml'), encoding='utf-8').read()
sec_positions = [(m.start(), m.group(1)) for m in re.finditer(r'^name = "(\w+)"', dump, re.M)]
name2sec = {}
by_sec_vram = {}
for m in re.finditer(r'\{ name = "(\w+)", vram = (0x[0-9A-Fa-f]+)', dump):
    sec = None
    for pos, s in sec_positions:
        if pos < m.start(): sec = s
        else: break
    name2sec[m.group(1)] = sec
    by_sec_vram[(sec, int(m.group(2), 16))] = m.group(1)

fixed = 0
for path in sorted(glob.glob(os.path.join(ROOT, 'RecompiledFuncs', 'funcs_*.c'))):
    src = open(path, 'rb').read().decode('utf-8', errors='replace')
    out = src
    for m in re.finditer(r'RECOMP_FUNC void (\w+)\(uint8_t\* rdram, recomp_context\* ctx\) \{(.*?)(^;\})', src, re.S | re.M):
        name, body, close = m.group(1), m.group(2), m.group(3)
        tail_lines = [x for x in body.rstrip().split('\n')[-8:]]
        if any('return;' in x for x in tail_lines):
            continue
        addrs = re.findall(r'// (0x[0-9A-F]{8}):', body)
        if not addrs:
            continue
        sec = name2sec.get(name)
        if sec is None:
            # N64Recomp emits some injected entries as static_N_XXXXXXXX; resolve the
            # section by the body's first decoded address if it's unique in dump.toml.
            first = int(addrs[0], 16)
            cands = [s for (s, v) in by_sec_vram if v == first]
            if len(cands) == 1:
                sec = cands[0]
            else:
                print('SKIP %s: ambiguous/unknown section for 0x%08X (%s)' % (name, first, cands))
                continue
        nxt = int(addrs[-1], 16) + 4
        succ = by_sec_vram.get((sec, nxt))
        if succ is None:
            continue
        patch = ('\n    /* [wm2k fix_stumps] N64Recomp truncated this overlapping function at the next\n'
                 '       same-section symbol without the fall-through; chain it. */\n'
                 '    %s(rdram, ctx);\n    return;\n' % succ)
        out = out.replace(m.group(0), 'RECOMP_FUNC void %s(uint8_t* rdram, recomp_context* ctx) {%s%s%s' %
                          (name, body, patch, close), 1)
        print('chained %s (%s) -> %s at 0x%08X' % (name, sec, succ, nxt))
        fixed += 1
    if out != src:
        open(path, 'wb').write(out.encode('utf-8'))
print(fixed, 'stumps chained')
