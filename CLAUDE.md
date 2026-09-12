# CLAUDE.md

Working notes for Granumid, a MIDI sampler written in JSFX (EEL2) for REAPER.
`README.md` documents the plug-in for users; this file is the stuff you need
before changing the code.

## Testing

JSFX only runs inside REAPER, so `tests/` carries a small EEL2 interpreter and
JSFX host stub that load the real `.jsfx` and its imports, run the sections, and
inspect the MIDI that comes out. **Run both suites after any change** — they are
the only verification available without the DAW.

```
python3 tests/test_granumid.py     # 54 checks: engine, modes, slicing, env, filter, UI
lua5.4  tests/test_import.lua      # 18 checks: the importer's SMF reader
```

The interpreter lives in `tests/eel2.py` (lexer/parser), `tests/runtime.py`
(evaluator, builtins, host stubs) and `tests/jsfx.py` (section splitting,
imports). If you use an EEL2 feature the project does not use yet, you will
probably have to teach the interpreter about it — that is expected and cheap.
It does not implement FFT/MDCT, `@sample`, MIDI buses or real drawing, and
`gfx_showmenu()` always returns "nothing selected".

The harness is ~1000x slower than real JSFX. **This says nothing about the
plug-in's performance**: EEL2 is JIT-compiled to native code, so 256 grains is
cheap in REAPER. Don't "optimise" based on harness timings.

## JSFX / EEL2 constraints that shaped this design

These were all confirmed against the official reference (reaper.fm/sdk/js) and
several of them are not obvious.

**Language**

- **No recursion.** A function may only call functions declared *before* it.
  This is why `import` order in `Granumid.jsfx` is core → engine → ui, and why
  e.g. `gm_voice_kill` is declared above `gm_voice_release`. Sorting and binary
  search are iterative for the same reason (`gm_heapsort`, `gm_find_ev`).
- **`%` is integer-only.** It converts the absolute values of both operands to
  integers. Never use it for float modulo — wrap by hand:
  `x = x - floor((x - a) / L) * L` (see `gm_grain_spawn`).
- **`==` is fuzzy** (equal within 1e-5), and conditionals treat any value with
  magnitude below 1e-5 as false. Use `===` when you need exactness.
- **Imported files must only *define functions* in their `@init`.** Statements
  placed there are not guaranteed to run when the importing file has its own
  `@init`. All initialisation happens in `Granumid.jsfx`'s `@init`, which calls
  `gm_init_consts()` / `gm_ui_consts()` / `gm_build_ui()` / `gm_reset_state()`.
- `sliderN:name=default<...>` variable-name syntax would break `slider(i)`
  access, which the table-driven GUI depends on. That is why sliders are plain
  `sliderN` and `gm_apply_params()` fans them out into named globals by hand.

**Files**

- There is **no reliable way to read arbitrary binary bytes.** You get media
  files via `file_riff`, numeric tokens from `.txt`, and a `file_string` that is
  only documented as binary-safe inside `@serialize`. Hence: no SMF parsing in
  JSFX, and the `.txt` token format in `docs/FORMAT.md`.
- A file slider (`slider1:/granumid:default.txt:Source File`) browses
  `<REAPER resource path>/Data/<dir>` and lists only `.wav`, `.txt`, `.ogg` and
  `.raw`. The format had to be one of those; `.txt` is the readable one.
- A `.txt` opened with `file_open()` tokenises into numbers separated by commas
  or newlines. `#` and `;` start comments, and `NAME = 1.0` lines are consumed as
  symbolic constants rather than records.
- **`file_open(slider1)` and `strcpy_fromslider(str, slider1)` need the literal
  `sliderN` token at the call site.** The compiler special-cases it; you cannot
  pass the value through a variable or a function parameter. That is why the
  file is opened inline in `@block` rather than inside a loader function.
- `gm_load_handle()` reads exactly `noteCount` records from the header instead of
  relying on EOF detection, because text-mode `file_avail()` semantics at the
  last token are ambiguous in the docs.

**Sections and state**

- `ext_noinit = 1` stops `@init` running on every transport start. Combined with
  a **non-empty `@serialize`** (which prevents memory being re-zeroed), the
  loaded phrase survives playback starts. Both are required; don't remove either.
- `@serialize` may run before `@init`, so it calls `gm_init_consts()` first —
  otherwise the memory-map constants are 0 and it would write over the note
  buffer at address 0.
- **MIDI processing belongs in `@block`**, with sample offsets inside the block.
  There is no `@sample` section and there shouldn't be.
- **`tempo`, `beat_position`, `play_state` and `ts_num`/`ts_denom` are not valid
  in `@gfx`.** Cache anything the UI needs during `@block` — `gm_ratio` exists
  purely because the status line used to call `gm_warp_ratio()` from `@gfx`.
- `@gfx` runs on a different thread from audio. UI writes to shared memory
  (markers, sliders) are racy by design; keep them small and idempotent.

## Architecture invariants

- **One absolute sample clock.** `gm_now` advances by `samplesblock` each block;
  everything (voice starts, note-offs, grain cycles, quantised triggers) is
  scheduled in absolute samples and converted to a block offset only at
  `midisend` time.
- **Reverse is a mirrored timeline, not a backwards scan.** Forward playback
  walks source time; reverse walks `srclen - t`. Two pre-sorted index arrays
  (`ORD_FWD`/`KEY_FWD` and `ORD_REV`/`KEY_REV`) let both directions use the same
  monotonically increasing scan, so note lengths survive and ping-pong is just a
  segment mirror plus a re-seek (`gm_stream_end`).
- **Stream pool indices are fixed:** voice `i` owns stream `i`; grain `g` owns
  stream `MAX_VOICES + g`. Voices reserve a *contiguous* run of grain slots
  (`gm_grain_reserve`), shrinking the request if the pool is busy.
- **Output notes are keyed by `chan*128 + pitch`.** A pair can only sound once at
  a time in MIDI, so `gm_note_on` emits the previous note-off first. Never emit a
  note-on you cannot later turn off: if the 512-slot pool is full the note is
  dropped deliberately.
- **Parameters fan out in `@block`, not `@slider`.** The GUI writes sliders
  directly, and the host does not reliably re-run `@slider` for those writes.
  `@slider` only sets `gm_slice_dirty`.
- Slice rebuilding is guarded by a hash of everything it depends on
  (`gm_apply_params`), so it is not recomputed every block.
- The memory map is one place: `gm_init_consts()` in `granumid_core.jsfx-inc`.
  Change offsets there and nowhere else, and mind the `MAX_*` ceilings
  (32768 notes, 256 markers, 128 slices, 16 voices, 256 grains, 512 sounding).

## Adding or changing a parameter

A slider lives in two places that must agree:

1. the `sliderN:` declaration in `Granumid.jsfx`
2. a matching `gm_ctl_cell(...)` in `gm_build_ui()`, which repeats the default,
   min, max and step so the knob can map its range

`gm_apply_params()` then needs a line to read it. The UI test asserts that every
slider from 2 upwards has exactly one control, that control defaults match the
declarations, that nothing falls outside the window and that no two controls
share a cell — so a mismatch fails the suite rather than shipping.

## Unverified in REAPER

The plug-in has never been loaded in the DAW. Four things the harness cannot
check, in rough order of likelihood:

1. `import <name>.jsfx-inc` resolving from the plug-in's own folder (all four
   files must sit together in `Effects/Granumid/`)
2. The file-list enumeration in `gm_scan_files()`, which steps `slider1` and
   reads back `strcpy_fromslider` to discover the available phrases
3. Exact text-mode `file_avail()` behaviour at EOF (mitigated as described above)
4. `sliderchange()` / `slider_automate()` masks for sliders above 32, where the
   bitmask exceeds 32 bits

If someone reports a bug, check these before suspecting the engine.

## Agreed next steps (not yet implemented)

Discussed and chosen over rewriting as VST3/CLAP:

1. **Serialize the phrase itself**, not just the markers, so projects are
   self-contained and don't depend on a file in `Data/granumid/` on whatever
   machine opens them.
2. **Have `granumid_import.lua` select the phrase it just wrote** in the focused
   Granumid instance. The file slider is an ordinary indexed parameter, so the
   script can set it once it knows the file's alphabetical position in the folder.

## Conventions

- GPL v3; every source file carries a short header comment.
- Comments explain *why* — particularly where a JSFX constraint forced the shape
  of the code. Don't strip those; they are the map back to this file.
