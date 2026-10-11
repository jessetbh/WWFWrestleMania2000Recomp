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

def add_header(lines, header, why):
    """Prepend an extra #include (e.g. stdlib.h for getenv) if missing."""
    if not any(('#include <%s>' % header) in l for l in lines):
        lines.insert(0, '#include <%s>  /* [wm2k HAND-EDIT] %s */\n' % (header, why))

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
    add_header(lines, 'stdlib.h', 'getenv for the WCW_TRACE gate')
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
'''    /* [wm2k diag] music-start tracing (hand-edit, dies on regen; opt-in WCW_TRACE=1 --
       it prints every service tick and would flood user logs) */
    { static int wm2k_trace = -1; if (wm2k_trace < 0) wm2k_trace = getenv("WCW_TRACE") != NULL;
      if (wm2k_trace) fprintf(stderr, "[wm2k][music] f53C8 sp=0x%08X slot=%d s0=0x%08X cur2E6=%d nxt2E8=%d st2FC=0x%08X arg2FE=0x%04X\\n",
            (unsigned)ctx->r29, (int)(int16_t)ctx->r18, (unsigned)ctx->r16, (int)(int16_t)MEM_H(0X2E6, ctx->r16),
            (int)(int16_t)MEM_H(0X2E8, ctx->r16), (unsigned)MEM_W(0X2FC, ctx->r16), (unsigned)(uint16_t)MEM_HU(0X2FE, ctx->r16)); }''')
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
    add_header(lines, 'stdlib.h', 'getenv for the WCW_TRACE gate')
    if any('[wm2k][rope]' in l for l in lines):
        save_lines('funcs_7.c', lines); return
    rng = body_range(lines, 'func_8001DD50')
    lo, hi = rng
    if lo is None:
        return
    ok = insert_after(lines, (lo, min(lo + 4, hi)), '    int c1cs = 0;', lf(
'''    { /* [wm2k HAND-EDIT ropeprobe] rope strip evaluator: log dest buffer, rope
         index and caller for the first calls + first calls after each 4096
         (session 8 part 4 rope hunt; garbage strips = dest 0x33C5D0..0x33C990).
         Opt-in via WCW_TRACE=1 -- the trickle would land in user logs. */
        static int wm2k_trace = -1;
        static unsigned wm2k_rope_n = 0;
        unsigned n = ++wm2k_rope_n;
        if (wm2k_trace < 0) wm2k_trace = getenv("WCW_TRACE") != NULL;
        if (wm2k_trace && (n <= 120 || (n & 0xFFF) < 24))
            fprintf(stderr, "[wm2k][rope] dest=0x%08X idx=%d ra=0x%08X n=%u\\n",
                (unsigned)ctx->r4, (int)(int32_t)ctx->r5, (unsigned)ctx->r31, n);
    }'''), 'funcs_7 ropeprobe')
    if ok:
        save_lines('funcs_7.c', lines)
        print('funcs_7.c: rope probe re-added')


# [wm2k][rt] Ray tracing experiment (exp/raytracing; src/game/raytracing.cpp): hand RT64
# the real camera. RT64 only uses it while ray tracing is active (menu option or WCW_RT).
def rt_hand_edits():
    import os as _os
    funcs = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), 'RecompiledFuncs')
    def _load(fn):
        with open(_os.path.join(funcs, fn), 'rb') as f:
            return f.read().decode('utf-8', errors='replace').splitlines(keepends=True)
    def _save(fn, lines):
        with open(_os.path.join(funcs, fn), 'wb') as f:
            f.write(''.join(lines).encode('utf-8'))
    def _body(lines, name):
        sig = 'RECOMP_FUNC void %s(' % name
        start = next((i for i, l in enumerate(lines) if l.startswith(sig)), None)
        if start is None:
            return None, None
        end = next((i for i in range(start, len(lines)) if lines[i].rstrip('\r\n') == ';}'), None)
        return start, end
    def _insert_after_all(fn, func, anchor, text, expect):
        lines = _load(fn)
        if any('[wm2k][rt]' in l for l in lines[slice(*_body(lines, func))] if l):
            return '%s already present' % func
        lo, hi = _body(lines, func)
        if lo is None or hi is None:
            raise SystemExit('rt: cannot locate %s in %s' % (func, fn))
        hits = [i for i in range(lo, hi) if lines[i].rstrip('\r\n') == anchor]
        if len(hits) != expect:
            raise SystemExit('rt: anchor %r matched %d times in %s (expected %d)' % (anchor, len(hits), func, expect))
        for i in reversed(hits):
            lines[i + 1:i + 1] = text
        _save(fn, lines)
        return '%s (%d site(s))' % (func, len(hits))
    done = []
    # The latch sits in the matrix multiply func_800016A8 calls, not in func_800016A8 itself:
    # mods hook func_800016A8 (AkiMods' camera) and a hooked function is recompiled from the
    # ROM without hand-edits. Older generated files had it in func_800016A8: strip that site.
    lines = _load('funcs_0.c')
    old = next((i for i, l in enumerate(lines) if '[wm2k][rt] camera latch: a1 = P, a2 = V' in l), None)
    if old is not None:
        del lines[old:old + 3]
        _save('funcs_0.c', lines)
        done.append('removed old latch in func_800016A8')
    done.append(_insert_after_all('funcs_0.c', 'func_80002048', '    int c1cs = 0;', [
        '    { /* [wm2k][rt] camera latch: a0 = V, a1 = P, a2 = product (the camera matrix when called from the camera builder) */\n',
        '      extern void wcw_rt_latch_camera_multiply(uint8_t* rdram, uint32_t view_vaddr, uint32_t proj_vaddr, uint32_t dest_vaddr);\n',
        '      wcw_rt_latch_camera_multiply(rdram, (uint32_t)ctx->r4, (uint32_t)ctx->r5, (uint32_t)ctx->r6); }\n'], 1))
    done.append(_insert_after_all('funcs_1.c', 'func_800033D4', '    func_80002E40(rdram, ctx);', [
        '    { /* [wm2k][rt] after the frame DL head is returned in v0 */\n',
        '      extern uint32_t wcw_rt_emit_camera(uint8_t* rdram, uint32_t gfx);\n',
        '      ctx->r2 = (int64_t)(int32_t)wcw_rt_emit_camera(rdram, (uint32_t)ctx->r2); }\n'], 1))
    return 'rt camera hand-off: ' + '; '.join(done)

# ---------------- frame interpolation (60 fps) matrix hooks ----------------
# [wm2k][hfr] RT64 interpolates models from their camera-independent matrices, which the game only
# exposes when it multiplies them with the camera. func_80002048 (out = A * B) hands A and the camera to
# RT64 keyed by the output address; guMtxF2L (func_80033560) moves the entry to the fixed-point matrix that
# gSPForceMatrix uploads (lib/rt64/src/hle/rt64_rsp.cpp, wcw_interp_* functions). Neither function
# is hooked by a mod. The hooks only store matrices; RT64 uses them only at a framerate above 30.
def hfr_hand_edits():
    done = []
    lines = load_lines('funcs_0.c')
    if not any('wcw_interp_process_multiply(wcw_dst' in l for l in lines):
        rng = body_range(lines, 'func_80002048')
        if insert_after(lines, rng, '    int c1cs = 0;', [
                '    { /* [wm2k][hfr] func_80002048 is a 4x4 multiply (out = A * B). When B is the camera matrix\n',
                "         (0x80057198), pass A (the object's camera-independent matrix) and B to RT64, keyed by\n",
                '         the output address; otherwise drop any stale entry for that address. */\n',
                '        extern void wcw_interp_process_multiply(uint32_t destAddr, uint32_t opBAddr, uint32_t srcAddr, const float* aMatrix16, const float* bMatrix16);\n',
                '        extern void wcw_interp_invalidate_local_matrix(uint32_t destAddr);\n',
                '        uint32_t wcw_dst = (uint32_t)ctx->r6;\n',
                '        if ((uint32_t)ctx->r5 == 0x80057198u) {\n',
                '            union { uint32_t u; float f; } wcw_bits;\n',
                '            float wcw_a[16], wcw_b[16];\n',
                '            for (int wcw_i = 0; wcw_i < 16; wcw_i++) {\n',
                '                wcw_bits.u = (uint32_t)MEM_W(ctx->r4, wcw_i * 4); wcw_a[wcw_i] = wcw_bits.f;\n',
                '                wcw_bits.u = (uint32_t)MEM_W(ctx->r5, wcw_i * 4); wcw_b[wcw_i] = wcw_bits.f;\n',
                '            }\n',
                '            wcw_interp_process_multiply(wcw_dst, (uint32_t)ctx->r5, (uint32_t)ctx->r4, wcw_a, wcw_b);\n',
                '        }\n',
                '        else {\n',
                '            wcw_interp_invalidate_local_matrix(wcw_dst);\n',
                '        }\n',
                '    }\n'], 'hfr-matrix'):
            save_lines('funcs_0.c', lines)
            done.append('matrix hook (func_80002048)')
    lines = load_lines('funcs_14.c')
    if not any('wcw_interp_forward_local_matrix((uint32_t)' in l for l in lines):
        rng = body_range(lines, 'func_80033560')
        if insert_after(lines, rng, '    int c1cs = 0;', [
                "    { /* [wm2k][hfr] func_80033560 is guMtxF2L. Move the matrix hook's entry from the float source (a0)\n",
                '         to the fixed-point destination (a1) that gSPForceMatrix uploads. */\n',
                '      extern void wcw_interp_forward_local_matrix(uint32_t srcAddr, uint32_t dstAddr);\n',
                '      wcw_interp_forward_local_matrix((uint32_t)ctx->r4, (uint32_t)ctx->r5); }\n'], 'hfr-f2l'):
            save_lines('funcs_14.c', lines)
            done.append('F2L hook (func_80033560)')
    return 'frame interpolation hooks: ' + ('; '.join(done) if done else 'present')

print(rt_hand_edits())
print(hfr_hand_edits())
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
