#!/usr/bin/env python3
"""Re-apply the RecompiledFuncs hand-edit diagnostics after a regen.

Every N64Recomp regen wipes the hand-edits documented in CLAUDE.md /
docs/bringup-plan.md. This script re-applies all of them (idempotent, safe to
re-run). Run it AFTER tools/fix_stumps.py + tools/fix_switches.py:

  funcs_1.c  : [wm2k][trap]  invalid-music-id canary (fires only if the toml
               clamp patch at 0x80003DF0 is reached = slot corruption is back)
  funcs_21.c : [wm2k][music] per-slot music service trace (func_800F53C8)
  funcs_8.c  : [wm2k][sreg]  s-reg canary + repair after each dispatch call in
               func_800222D8's loop (sites after_4..after_10); sp drift log-only.
               ctx GPRs are 64-bit SIGN-EXTENDED: constants are 0xFFFFFFFF8xxx.
  funcs_0.c  : [wm2k][spprobe] net-sp-change probes in func_80000744 (loop-top
               DMA streamer) and func_80000870 (overlay-entry trampoline)

Anchors are exact generated lines (ending-agnostic: generated files are CRLF,
insertions are LF, the compiler doesn't care). If an anchor is missing the
script FAILS LOUDLY -- regen output changed shape; re-derive the edit from
docs/bringup-plan.md session 7 and update this script.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUNCS = os.path.join(ROOT, 'RecompiledFuncs')

failures = []

def load_lines(fn):
    with open(os.path.join(FUNCS, fn), 'rb') as f:
        return f.read().decode('utf-8', errors='replace').splitlines(keepends=True)

def save_lines(fn, lines):
    with open(os.path.join(FUNCS, fn), 'wb') as f:
        f.write(''.join(lines).encode('utf-8'))

def body_range(lines, func_name):
    start = end = None
    sig = 'RECOMP_FUNC void %s(' % func_name
    for i, l in enumerate(lines):
        if start is None and l.startswith(sig):
            start = i
        elif start is not None and l.rstrip('\r\n') == ';}':
            end = i
            break
    if start is None or end is None:
        failures.append('%s: cannot locate %s' % (func_name, sig))
    return start, end

def insert_after(lines, idx_range, anchor, text, tag):
    """Insert text (list of LF-terminated lines) after the unique line whose
    stripped content == anchor, within idx_range."""
    lo, hi = idx_range
    if lo is None:
        return False
    hits = [i for i in range(lo, hi) if lines[i].rstrip('\r\n') == anchor]
    if len(hits) != 1:
        failures.append('%s: anchor %r matched %d times' % (tag, anchor, len(hits)))
        return False
    lines[hits[0] + 1:hits[0] + 1] = text
    return True

def add_stdio(fn, why):
    lines = load_lines(fn)
    if any('#include <stdio.h>' in l for l in lines):
        return lines, False
    lines.insert(0, '#include <stdio.h>  /* [wm2k HAND-EDIT] %s */\n' % why)
    return lines, True

def lf(block):
    return [l + '\n' for l in block.split('\n')]

# ---------------- funcs_1.c : invalid-music-id trap canary ----------------
def do_funcs_1():
    lines, _ = add_stdio('funcs_1.c', 'for the trap canary')
    if any('[wm2k][trap]' in l for l in lines):
        save_lines('funcs_1.c', lines); return
    rng = body_range(lines, 'func_80003DD4')
    ok = insert_after(lines, rng, '    // 0x80003DF0: addiu       $a1, $zero, 0x1', lf(
'''    /* [wm2k diag] only reached with INVALID music id; toml patch resolves as song 1. Canary. */
    fprintf(stderr, "[wm2k][trap] func_80003DD4 invalid id (clamped to 1): a0=0x%08X a1(id)=0x%08X\\n", (unsigned)ctx->r4, (unsigned)ctx->r5);'''), 'funcs_1 trap')
    if ok:
        save_lines('funcs_1.c', lines)
        print('funcs_1.c: trap canary re-added')

# ---------------- funcs_21.c : music service trace ----------------
def do_funcs_21():
    lines, _ = add_stdio('funcs_21.c', 'for the music trace')
    if any('[wm2k][music]' in l for l in lines):
        save_lines('funcs_21.c', lines); return
    rng = body_range(lines, 'func_800F53C8')
    # after the s0 = base+stride*slot compute (0x800F5408's code line)
    lo, hi = rng
    idx = None
    for i in range(lo or 0, hi or 0):
        if lines[i].rstrip('\r\n') == '    // 0x800F5408: addu        $s0, $a0, $v0':
            idx = i + 1  # its code line
            break
    if idx is None:
        failures.append('funcs_21: 0x800F5408 anchor missing')
        return
    lines[idx + 1:idx + 1] = lf(
'''    /* [wm2k diag] music-start tracing (hand-edit, dies on regen) */
    fprintf(stderr, "[wm2k][music] f53C8 sp=0x%08X slot=%d s0=0x%08X cur2E6=%d nxt2E8=%d st2FC=0x%08X arg2FE=0x%04X\\n",
            (unsigned)ctx->r29, (int)(int16_t)ctx->r18, (unsigned)ctx->r16, (int)(int16_t)MEM_H(0X2E6, ctx->r16),
            (int)(int16_t)MEM_H(0X2E8, ctx->r16), (unsigned)MEM_W(0X2FC, ctx->r16), (unsigned)(uint16_t)MEM_HU(0X2FE, ctx->r16));''')
    save_lines('funcs_21.c', lines)
    print('funcs_21.c: music trace re-added')

# ---------------- funcs_8.c : s-reg canary + repair ----------------
CANARY = '''    {{ /* [wm2k HAND-EDIT sreg canary] s0-s3 are loop invariants in func_800222D8
         (64-bit SIGN-EXTENDED in ctx!); a callee returning with any of them wrong
         is the boot85/88 post-match corruption. Log the site, repair s-regs so the
         run continues; sp mismatch is log-only. */
        static unsigned wm2k_hits_after_{n} = 0;
        static unsigned long long wm2k_sp_seen_after_{n} = 0;
        if (wm2k_sp_seen_after_{n} == 0) wm2k_sp_seen_after_{n} = ctx->r29;
        else if (ctx->r29 != wm2k_sp_seen_after_{n})
            fprintf(stderr, "[wm2k][sreg] SP DRIFT site=after_{n} sp=%016llX first-seen=%016llX\\n",
                (unsigned long long)ctx->r29, wm2k_sp_seen_after_{n});
        if (ctx->r19 != 0xFFFFFFFF80047E90ull || ctx->r18 != 0xFFFFFFFF80047EB4ull ||
            ctx->r17 != 0xFFFFFFFF80047ED8ull || ctx->r16 != 0xFFFFFFFF80047EFCull) {{
            wm2k_hits_after_{n}++;
            if (wm2k_hits_after_{n} <= 50 || (wm2k_hits_after_{n} & 0xFF) == 0)
                fprintf(stderr, "[wm2k][sreg] site=after_{n} hits=%u s0=%016llX s1=%016llX s2=%016llX s3=%016llX sp=%016llX\\n",
                    wm2k_hits_after_{n}, (unsigned long long)ctx->r16, (unsigned long long)ctx->r17,
                    (unsigned long long)ctx->r18, (unsigned long long)ctx->r19,
                    (unsigned long long)ctx->r29);
            ctx->r19 = 0xFFFFFFFF80047E90ull; ctx->r18 = 0xFFFFFFFF80047EB4ull;
            ctx->r17 = 0xFFFFFFFF80047ED8ull; ctx->r16 = 0xFFFFFFFF80047EFCull;
        }}
    }}'''

def do_funcs_8():
    lines, _ = add_stdio('funcs_8.c', 'for the sreg canary')
    if any('[wm2k][sreg]' in l for l in lines):
        save_lines('funcs_8.c', lines); return
    added = 0
    for n in range(4, 11):
        rng = body_range(lines, 'func_800222D8')
        if insert_after(lines, rng, '    after_%d:' % n, lf(CANARY.format(n=n)),
                        'funcs_8 after_%d' % n):
            added += 1
    save_lines('funcs_8.c', lines)
    print('funcs_8.c: %d/7 sreg canaries re-added' % added)

# ---------------- funcs_0.c : sp probes ----------------
def sp_probe(lines, func_name, restore_line, check_block, decl_block, tag):
    rng = body_range(lines, func_name)
    lo, hi = rng
    if lo is None:
        return
    # declarations right after the c1cs decl
    if not insert_after(lines, (lo, min(lo + 5, hi)), '    int c1cs = 0;', lf(decl_block), tag + ' decl'):
        return
    # re-scope after insertion, find the sp-restore immediately before the return
    lo, hi = body_range(lines, func_name)
    idx = None
    for i in range(lo, hi - 1):
        if (lines[i].rstrip('\r\n') == restore_line and
                lines[i + 1].rstrip('\r\n') == '    return;'):
            idx = i + 1
            break
    if idx is None:
        failures.append(tag + ': restore+return anchor missing')
        return
    lines[idx:idx] = lf(check_block)
    print('funcs_0.c: %s probe re-added' % func_name)

def do_funcs_0():
    lines, _ = add_stdio('funcs_0.c', 'for the sp probes')
    if '[wm2k][spprobe]' not in ''.join(lines):
        sp_probe(lines, 'func_80000744', '    ctx->r29 = ADD32(ctx->r29, 0X48);',
'''    if (ctx->r29 != wm2k_sp_in)
        fprintf(stderr, "[wm2k][spprobe] func_80000744 LEAK in=%016llX out=%016llX a0=%08X a1=%08X\\n",
            (unsigned long long)wm2k_sp_in, (unsigned long long)ctx->r29,
            (unsigned)wm2k_a0_in, (unsigned)wm2k_a1_in);''',
'''    /* [wm2k HAND-EDIT sp probe] boot91: thread 6's loop sp leaked 0x18 inside the
       loop-top call during the post-match swap-back; catch the net leak here. */
    uint64_t wm2k_sp_in = ctx->r29;
    uint64_t wm2k_a0_in = ctx->r4, wm2k_a1_in = ctx->r5;''', 'funcs_0 744')
        sp_probe(lines, 'func_80000870', '    ctx->r29 = ADD32(ctx->r29, 0X18);',
'''    if (ctx->r29 != wm2k_sp_in)
        fprintf(stderr, "[wm2k][spprobe] func_80000870 LEAK in=%016llX out=%016llX (overlay entry chain)\\n",
            (unsigned long long)wm2k_sp_in, (unsigned long long)ctx->r29);''',
'''    /* [wm2k HAND-EDIT sp probe] see func_80000744 */
    uint64_t wm2k_sp_in = ctx->r29;''', 'funcs_0 870')
    save_lines('funcs_0.c', lines)

# ---------------- funcs_7.c : rope evaluator probe ----------------
def do_funcs_7():
    lines, _ = add_stdio('funcs_7.c', 'for the rope probe')
    if any('[wm2k][rope]' in l for l in lines):
        save_lines('funcs_7.c', lines); return
    rng = body_range(lines, 'func_8001DD50')
    lo, hi = rng
    if lo is None:
        return
    ok = insert_after(lines, (lo, min(lo + 4, hi)), '    int c1cs = 0;', lf(
'''    { /* [wm2k HAND-EDIT ropeprobe] rope strip evaluator: log dest buffer, rope
         index and caller for the first calls + first calls after each 4096
         (session 8 part 4 rope hunt; garbage strips = dest 0x33C5D0..0x33C990). */
        static unsigned wm2k_rope_n = 0;
        unsigned n = ++wm2k_rope_n;
        if (n <= 120 || (n & 0xFFF) < 24)
            fprintf(stderr, "[wm2k][rope] dest=0x%08X idx=%d ra=0x%08X n=%u\\n",
                (unsigned)ctx->r4, (int)(int32_t)ctx->r5, (unsigned)ctx->r31, n);
    }'''), 'funcs_7 ropeprobe')
    if ok:
        save_lines('funcs_7.c', lines)
        print('funcs_7.c: rope probe re-added')

do_funcs_1()
do_funcs_21()
do_funcs_8()
do_funcs_0()
do_funcs_7()

if failures:
    print('\nFAILURES:')
    for f in failures:
        print('  ' + f)
    sys.exit(1)
print('all hand-edits present')
