# Tests

JSFX only runs inside REAPER, which makes it awkward to check that a change to
the engine still produces the right notes. `eel2.py` / `runtime.py` / `jsfx.py`
are a small EEL2 interpreter and JSFX host stub that load `Midular.jsfx` and its
imports, run `@init` / `@slider` / `@block` / `@gfx`, and record the MIDI that
comes out — so the playback engine can be tested like ordinary code.

```
python3 tests/test_midular.py     # engine, modes, slicing, envelope, filter, UI
lua5.4  tests/test_import.lua      # the ReaScript importer's SMF reader
```

Both print a per-check report and exit non-zero on failure.

## What the interpreter covers

Enough of EEL2 to run this project: the operator set and its precedence,
`? :`, `while()` in both forms, `loop()`, user functions with `local()`,
memory via `[]`, strings (named, slot and literal), and the JSFX host surface
that Midular touches — `slider()`, `sliderchange()`, `midisend()`/`midirecv()`,
the `file_*` text-mode reader, and `gfx_*` as no-ops that still evaluate their
arguments. It is a test tool, not a REAPER replacement: it does not implement
FFT/MDCT, `@sample`, MIDI buses, or real drawing, and `gfx_showmenu()` always
returns "nothing selected".

## Caveats

The interpreter is roughly a thousand times slower than the real thing, so the
256-grain stress test takes a few seconds. Timing assertions allow a sample or
two of slack because positions are accumulated in floating point.
