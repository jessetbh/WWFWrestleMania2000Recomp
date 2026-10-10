"""HFR spike: frame-interpolation matrix hooks (from PR #5's No Mercy hand-edits) for other AKI games.

Run from a game repo root after readd_hand_edits.py:  python tools/hfr_hand_edits.py

The camera multiply (out = A * camera) hands RT64 each object's camera-independent matrix A,
keyed by the output address; guMtxF2L forwards that key to the fixed-point matrix the game
uploads with gSPForceMatrix. Implemented in RT64 (rt64_rsp.cpp, wcw_nomercy_* functions).
"""
import glob, os, sys

GAMES = {
    # repo folder: (camera multiply, guMtxF2L, camera matrix)
    'Wm2kRecomp': ('func_80002048', 'func_80033560', 0x80057198),
    'Vpw2Recomp': ('func_80002108', 'func_80034340', 0x80056F78),
}

LF = chr(10)


def find_game():
    here = os.path.basename(os.getcwd())
    for name in GAMES:
        if here == name or here.startswith(name + '-'):
            return name
    sys.exit('hfr_hand_edits: unknown game folder %r' % here)


def func_file(func):
    for path in sorted(glob.glob('RecompiledFuncs/funcs_*.c')):
        if ('RECOMP_FUNC void %s(' % func) in open(path, encoding='utf-8', errors='replace').read():
            return path
    sys.exit('hfr_hand_edits: %s not found' % func)


def insert(path, func, marker, decls, body):
    text = open(path, encoding='utf-8', newline='').read()
    if marker in text:
        return '%s already present' % func
    nl = (chr(13) + LF) if (chr(13) + LF) in text else LF
    start = text.index('RECOMP_FUNC void %s(' % func)
    anchor = '    int c1cs = 0;' + nl
    at = text.index(anchor, start) + len(anchor)
    text = text[:at] + ''.join(body).replace(LF, nl) + text[at:]
    last_include = text.rfind(nl + '#include')
    eol = text.index(nl, last_include + len(nl)) + len(nl)
    text = text[:eol] + ''.join(decls).replace(LF, nl) + text[eol:]
    open(path, 'w', encoding='utf-8', newline='').write(text)
    return '%s -> %s' % (func, os.path.basename(path))


name = find_game()
mult, f2l, camera = GAMES[name]

matrix_decls = [
    '#include <string.h>  /* [wcw hfr] memcpy for the matrix hook */' + LF,
    '/* [wcw hfr] interpolation matrix hooks, implemented in RT64 (rt64_rsp.cpp). */' + LF,
    'extern void wcw_nomercy_process_multiply(uint32_t destAddr, uint32_t opBAddr, uint32_t srcAddr, const float* aMatrix16, const float* bMatrix16);' + LF,
    'extern void wcw_nomercy_invalidate_local_matrix(uint32_t destAddr);' + LF,
]
matrix_hook = [
    '    { /* [wcw hfr] %s is a 4x4 multiply (out = A * B). When B is the camera matrix' % mult + LF,
    "         (0x%08X), pass A (the object's camera-independent matrix) and B to RT64, keyed by" % camera + LF,
    '         the output address; otherwise drop any stale entry for that address. */' + LF,
    '        uint32_t wcw_dst = (uint32_t)ctx->r6;' + LF,
    '        if ((uint32_t)ctx->r5 == 0x%08Xu) {' % camera + LF,
    '            float wcw_a[16], wcw_b[16];' + LF,
    '            for (int wcw_i = 0; wcw_i < 16; wcw_i++) {' + LF,
    '                uint32_t wcw_abits = (uint32_t)MEM_W(ctx->r4, wcw_i * 4);' + LF,
    '                uint32_t wcw_bbits = (uint32_t)MEM_W(ctx->r5, wcw_i * 4);' + LF,
    '                memcpy(&wcw_a[wcw_i], &wcw_abits, sizeof(float));' + LF,
    '                memcpy(&wcw_b[wcw_i], &wcw_bbits, sizeof(float));' + LF,
    '            }' + LF,
    '            wcw_nomercy_process_multiply(wcw_dst, (uint32_t)ctx->r5, (uint32_t)ctx->r4, wcw_a, wcw_b);' + LF,
    '        }' + LF,
    '        else {' + LF,
    '            wcw_nomercy_invalidate_local_matrix(wcw_dst);' + LF,
    '        }' + LF,
    '    }' + LF,
]
f2l_decls = [
    '/* [wcw hfr] interpolation matrix hook, implemented in RT64 (rt64_rsp.cpp). */' + LF,
    'extern void wcw_nomercy_forward_local_matrix(uint32_t srcAddr, uint32_t dstAddr);' + LF,
]
f2l_hook = [
    "    /* [wcw hfr] %s is guMtxF2L. Move the matrix hook's entry from the float source (a0)" % f2l + LF,
    '       to the fixed-point destination (a1) that gSPForceMatrix uploads. */' + LF,
    '    wcw_nomercy_forward_local_matrix((uint32_t)ctx->r4, (uint32_t)ctx->r5);' + LF,
]

print('hfr_hand_edits (%s): %s; %s' % (
    name,
    insert(func_file(mult), mult, 'wcw_nomercy_process_multiply(wcw_dst', matrix_decls, matrix_hook),
    insert(func_file(f2l), f2l, 'wcw_nomercy_forward_local_matrix((uint32_t)', f2l_decls, f2l_hook)))
