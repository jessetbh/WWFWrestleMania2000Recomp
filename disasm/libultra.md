# libultra identification evidence — WWF WrestleMania 2000

How the named functions in `tools/gen_symbols.py`'s `RENAME` map were
identified. Convention inherited from the sister projects (World Tour's
`disasm/libultra.md` holds the original per-function evidence chain; Revenge
transfers from World Tour, and this project transfers from Revenge).

## Primary method: fingerprint transfer from Revenge

WrestleMania 2000 ships a newer libultra than Revenge's (a 2.0J+ build — its
`__osDisableInt` is the `__OSGlobalIntMask` revision), but the two are close
enough for masked-body matching. `tools/recon2.py`..`recon4.py` masked every
address-bearing field (16-bit immediates of I-type ALU/loads/stores, 26-bit
j/jal targets) in each of Revenge's named fixed-segment functions and matched
the full masked bodies against this ROM's fixed segment:

- **27/39 matched uniquely.** Each unique full-body masked match inherits the
  Revenge name and, transitively, the original identification evidence from
  World Tour's `disasm/libultra.md`.
- Ambiguous multi-candidate matches were resolved by the raw MMIO immediates
  and field offsets the candidates touch (the same discrimination method the
  sisters used) — resolutions live as comments in `tools/gen_symbols.py`
  next to each `RENAME`.

## Crash-loop finds

Functions the fingerprints missed (this libultra generation diverges from
Revenge's in these bodies) were identified during boot bring-up by the
crash-loop method proven on Revenge: boot until the unidentified callee
faults or spins, then match the fault's register/MMIO evidence against the
libultra source the family targets. Found this way:
`osCreatePiManager`, `osCartRomInit`, `osAiSetNextBuffer`, and the idle
thread's parent `osCreateThread` chain.

## Save hardware (SaveType = Sram)

`func_80000A88` builds an SRAM `OSPiHandle` — baseAddress `0xA8000000`,
device type 3, domain-2 timings — and the save driver (ovl_a
`func_800F03C0` / `func_800F4B1C`, `OSIoMesg` statics at `0x80118548`) DMAs
through it. The game additionally uses a Controller Pak for created-wrestler
storage; the port backs cart SRAM and the pak with separate files.

## Stub classifications

The `[patches] stubs` block in `wm2k.toml` (cache ops, exception/TLB kernel
internals, `__osSetCompare`, the NMI trampoline) was audited function by
function: each is live-called-and-correctly-inert or dead under the
ultramodern runtime, matching the sisters' stub sets. `osYieldThread`'s no-op
(via stubbed `func_80036DFC`) is known, documented behavior.
