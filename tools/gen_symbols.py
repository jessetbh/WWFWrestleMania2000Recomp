#!/usr/bin/env python3
"""Generate N64Recomp symbol TOML (syms/dump.toml) from splat output — WM2000.

Same approach as Revenge's generator (symbol-TOML mode; spimdisasm emits
`nonmatching <name>, <size>` + per-instruction `/* ROM VRAM WORD */` comments).
One [[section]] per asm file; overlays are ordinary sections (librecomp tracks
their loads by rom address).

RENAME transfers libultra knowledge. Unlike WT->Revenge (different libultra
generations, fingerprints didn't transfer), Revenge->WM2000 transferred almost
wholesale: 27/39 full-body masked-fingerprint matches plus resolved ambiguities
(tools/recon2.py..recon4.py, 2026-07-07). Evidence per function lives in
Revenge's tools/gen_symbols.py + WT's disasm/libultra.md; the WM2000 addresses
below each came from a unique byte-level match against the Revenge function of
that name (or the documented resolution in recon3/recon4 output).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASM = ROOT / "disasm" / "asm"
OUT = ROOT / "syms" / "dump.toml"

RENAME = {
    # host-collision rename, same as WT/Revenge (splat left it unnamed here; the
    # entry stub at 0x1000 jr's to it):
    "main": "game_main",
    "func_80000460": "game_main",
    # game_main's FIRST jal (Revenge/WT's exact pattern), body verified 2026-07-07:
    # FCR31=0x01000800, PIF terminate-boot SI loop at 0x1FC007FC, exception-vector
    # preamble (func_80036780) copied to 0x80000000/80/100/180.
    "func_80036498": "osInitialize",

    # --- libultra: naming a function makes N64Recomp auto-ignore it (built-in set in
    #     N64Recomp/src/symbol_lists.cpp) so the runtime provides it.
    # Fingerprint-transferred from Revenge (unique full-body masked match):
    "func_8002A2C0": "__osRestoreInt",
    "func_8002A2E0": "osSetIntMask",
    "func_8002A700": "osEPiStartDma",
    "func_8002B8A0": "osAiSetFrequency",
    "func_8002F8E0": "osContInit",
    "func_8002FC50": "osVirtualToPhysical",
    "func_80031840": "osCreateMesgQueue",
    "func_80031870": "osJamMesg",
    "func_800319B0": "osRecvMesg",
    "func_80031AE0": "osSendMesg",
    "func_80031CC0": "osSpTaskLoad",
    "func_80031ECC": "osSpTaskStartGo",
    "func_80031F00": "osSpTaskYield",
    "func_80031F20": "osSpTaskYielded",
    "func_80031F70": "__osSiRawStartDma",
    "func_80032200": "osCreateThread",
    "func_800322D0": "osGetThreadPri",
    "func_800322F0": "osSetThreadPri",
    "func_800323C0": "osStartThread",
    "func_80032570": "osGetTime",
    "func_80032B90": "osCreateViManager",
    "func_80032ED0": "osViSetEvent",
    "func_80032F30": "osViSetMode",
    "func_80032F80": "osViSetSpecialFeatures",
    "func_800330F0": "osViSetYScale",
    "func_80033140": "osViSwapBuffer",
    "func_800334A0": "osViBlack",
    # Ambiguity resolutions (recon3.py): raw MMIO immediates discriminate.
    "func_8002B880": "osAiGetLength",   # lw AI_LEN 0xA4500004
    "func_8002B890": "osAiGetStatus",   # lw AI_STATUS 0xA450000C
    "func_80038260": "__osSiDeviceBusy",# lw SI_STATUS 0xA4800018 & 3
    # (rom 0x382F0 = lw SP_STATUS & 0x1C = __osSpDeviceBusy — left unnamed, only
    #  reached through the osSpTask* set which is already runtime-provided.)
    # Vi getters: same adjacent 0x40-apart pair as Revenge (Current first, Next
    # second); both open with jal __osDisableInt.
    "func_80032B10": "osViGetCurrentFramebuffer",
    "func_80032B50": "osViGetNextFramebuffer",
    # recon4.py identifications:
    # exact 3-word body: mfc0 v0,C0_COUNT; jr ra; nop
    "func_80037690": "osGetCount",
    # 2.0J+ __OSGlobalIntMask revision (full body at rom 0x2AE50 verified: mfc0/mtc0
    # SR with __OSGlobalIntMask 0x80059B50 filtering), ends where __osRestoreInt
    # (0x8002A2C0, fingerprint-matched) begins.
    "func_8002A250": "__osDisableInt",
    # of 4 six-word-prefix candidates, the one directly after osSendMesg — matching
    # libultra's source order in Revenge (osSendMesg -> osSetEventMesg).
    "func_80031C10": "osSetEventMesg",
    # boot1 crash (2026-07-07, PI_STATUS raw read from thread func_800004D0 —
    # Revenge's 2nd-boot-crash pattern verbatim): the thread calls A380 then A7F0.
    # A380 ran clean and its effects were logged (pri-150 devmgr thread entry
    # 0x8002A970 created, osSetEventMesg event=8 OS_EVENT_PI msg=0x22222222) =
    # osCreatePiManager. A7F0 faulted reading PI_STATUS and its body unpacks
    # PI_BSD_DOM1_LAT/PGS/RLS/PWD from the ROM-header bus config = osCartRomInit.
    "func_8002A380": "osCreatePiManager",
    "func_8002A7F0": "osCartRomInit",
    # boot2/boot3 crashes: the thread's NEXT call after osCartRomInit. Saves DOM1
    # timing regs, probes, then READS 0xA6000000 (64DD drive-ROM IPL header) =
    # osDriveRomInit (librecomp shim exists). First attempt neutered its PI MMIO
    # with instruction patches (tools/gen_mmio_patches.py) — superseded by this
    # rename, patches removed.
    "func_80022540": "osDriveRomInit",
    # boot8 crash (audio thread func_80026F18 → B9C0 → 37550 raw AI_STATUS read —
    # Revenge's 7th-iteration pattern verbatim): B9C0 has the even-samples -0x2000
    # adjust, calls func_80037550 (__osAiDeviceBusy, dead once this is runtime-
    # provided) and osVirtualToPhysical = osAiSetNextBuffer. All of Revenge's
    # libultra set is now accounted for.
    "func_8002B9C0": "osAiSetNextBuffer",
    # NOTE Revenge input invariant: rename ONLY osContInit + __osSiRawStartDma +
    # __osSiDeviceBusy; do NOT rename osContStartReadData (kills the raw-SI path).
}

# Extra function entry points injected into dump.toml that splat cannot express:
# j-referenced entries living INSIDE another sized function (IDO multi-entry
# shared-tail clusters; Revenge's EXTRA_FUNCS mechanism). N64Recomp recompiles each
# independently from ROM bytes, so the overlap just duplicates a little code.
# Populated automatically by tools/recomp_loop.py from N64Recomp "Unhandled branch"
# errors, one "section name vram size" line per entry in syms/extra_funcs.txt.
EXTRA_FUNCS = {}
_extra_file = Path(__file__).resolve().parent.parent / "syms" / "extra_funcs.txt"
if _extra_file.exists():
    for l in open(_extra_file):
        parts = l.split()
        if len(parts) == 4:
            EXTRA_FUNCS.setdefault(parts[0], []).append(
                (parts[1], int(parts[2], 16), int(parts[3], 16)))

# Functions suppressed as symbols (continuation fragments merged into an earlier
# function).
SKIP = set()
_skip_file = ROOT / "syms" / "skip_functions.txt"
if _skip_file.exists():
    SKIP = {l.strip() for l in open(_skip_file) if l.strip()}

FUNC_RE = re.compile(r"^nonmatching (\S+), (0x[0-9A-Fa-f]+)")
GLABEL_RE = re.compile(r"^glabel (\S+)")
INSN_RE = re.compile(r"^\s*/\* ([0-9A-Fa-f]+) ([0-9A-Fa-f]{8}) ([0-9A-Fa-f]{8}) \*/")

SECTION_NAMES = {
    "1000.s": "entry",
    "4C160.s": "ovl_a",
    "73390.s": "ovl_b",
    "809D0.s": "ovl_c",
    "D2720.s": "ovl_d",
}

def parse_file(path):
    """Return (rom_start, vram_start, rom_end, [(name, vram, size)])."""
    funcs = []
    pending_size = None
    pending_name = None
    first = None
    last = None
    for line in open(path, encoding="utf-8"):
        m = FUNC_RE.match(line)
        if m:
            pending_name, pending_size = m.group(1), int(m.group(2), 16)
            continue
        m = GLABEL_RE.match(line)
        if m and pending_name == m.group(1):
            funcs.append([pending_name, None, pending_size])
            continue
        m = INSN_RE.match(line)
        if m:
            rom, vram = int(m.group(1), 16), int(m.group(2), 16)
            if first is None:
                first = (rom, vram)
            last = (rom, vram)
            if funcs and funcs[-1][1] is None:
                funcs[-1][1] = vram
    if first is None:
        return None
    return first[0], first[1], last[0] + 4, [(n, v, s) for n, v, s in funcs if v is not None]

def main():
    sections = []
    for path in sorted(ASM.glob("*.s")):
        parsed = parse_file(path)
        if not parsed:
            continue
        rom, vram, rom_end, funcs = parsed
        if path.name == "1000.s":
            name = "entry"
            funcs = [("entrypoint", vram, 0x38)] if not funcs else funcs
        elif path.name in SECTION_NAMES:
            name = SECTION_NAMES[path.name]
        else:
            name = f"main_{rom:X}"
        sections.append((name, rom, vram, rom_end - rom, funcs))

    OUT.parent.mkdir(exist_ok=True)
    unused = set(RENAME) - {"main"}
    with open(OUT, "w", newline="\n") as f:
        f.write("# Autogenerated from splat disassembly by tools/gen_symbols.py\n")
        total = 0
        seen = {}
        for name, rom, vram, size, funcs in sections:
            f.write(f"\n[[section]]\nname = \"{name}\"\n")
            f.write(f"rom = 0x{rom:08X}\nvram = 0x{vram:08X}\nsize = 0x{size:X}\n\n")
            f.write("functions = [\n")
            funcs = sorted(list(funcs) + EXTRA_FUNCS.get(name, []), key=lambda t: t[1])
            for fn, fv, fs in funcs:
                if fn in SKIP:
                    continue
                unused.discard(fn)
                fn = RENAME.get(fn, fn)
                # disambiguate names colliding across same-vram overlays (WT scheme)
                if fn in seen and seen[fn] != (name, fv):
                    fn = f"{fn}_{name}"
                seen[fn] = (name, fv)
                f.write(f"    {{ name = \"{fn}\", vram = 0x{fv:08X}, size = 0x{fs:X} }},\n")
                total += 1
            f.write("]\n")
    print(f"wrote {OUT}: {len(sections)} sections, {total} functions")
    if unused:
        print("WARNING: RENAME keys not found in splat output (splat merged/missed them):")
        for k in sorted(unused):
            print(f"  {k} -> {RENAME[k]}")

if __name__ == "__main__":
    main()
