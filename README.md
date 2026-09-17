# Midular

A MIDI sampler for REAPER, written in JSFX.

Midular treats a MIDI phrase the way Ableton's Simpler or Bitwig's Sampler treat
an audio file: you load a source, map it across the keyboard, and shape it with a
filter, an envelope, warping and looping. The difference is that every stage
operates on **notes** rather than samples — nothing here renders audio, it emits
MIDI for whatever instrument sits after it in the chain.

```
MIDI in ──▶ trigger ──▶ [ mode engine ] ──▶ [ note filter ] ──▶ [ amp envelope ] ──▶ MIDI out
                        classic / one-shot     LP HP BP notch        A D S R
                        slice   / granular
```

## Install

1. Copy these four files into `<REAPER resource path>/Effects/Midular/`
   (Options → Show REAPER resource path):

   ```
   Midular.jsfx
   midular_core.jsfx-inc
   midular_engine.jsfx-inc
   midular_ui.jsfx-inc
   ```

   They must stay in the same folder — the `.jsfx-inc` files are imported by name.

2. Copy `Data/midular/` into `<REAPER resource path>/Data/` so the folder
   `<resource>/Data/midular/` exists and contains `default.txt`. This is the
   folder the **Source File** selector browses.

3. Copy `Scripts/midular_import.lua` anywhere and add it with
   Actions → Show action list → New action → Load ReaScript.

4. Add **JS: Midular** to a track, ahead of whatever instrument should play the
   notes.

## Importing a phrase

JSFX cannot read `.mid` files directly, so phrases are converted once into a
small text format that JSFX reads natively (see [docs/FORMAT.md](docs/FORMAT.md)).
`midular_import.lua` does the conversion two ways:

* **Select one or more MIDI items** and run the action — it captures those items,
  including take markers and any project markers inside them.
* **Select nothing** and run the action — it asks for a `.mid` file on disk and
  parses it (format 0 and 1, running status, tempo and time-signature meta
  events, SMPTE or ticks-per-quarter division, marker meta events).

Either way you are asked for a name, and the result lands in
`<resource>/Data/midular/`. Click Midular's file button to pick it up.

## Modes

| Mode | Behaviour |
| --- | --- |
| **Classic** | Polyphonic. Each held key plays the phrase, looping for as long as the key is down. Keys transpose (or repitch, see Key Tracking). |
| **One-Shot** | Monophonic. One trigger plays the phrase from start to finish; note-off is ignored. Retrigger behaviour is Restart, Ignore or Legato. |
| **Slice** | The phrase is chopped and the pieces are laid out from *Map Root* upwards, one slice per key. |
| **Granular** | Up to 256 grains read small windows of the phrase at once, each with its own position, direction and pitch offset. |

### Slicing

Five ways to decide where the cuts go:

* **Divisions** — *n* equal pieces across the region.
* **Beats** — a fixed musical grid (1/32 … 2 bars).
* **Onsets** — note starts, clustered by *Sensitivity*. Low sensitivity groups
  loosely and ignores quiet notes; high sensitivity cuts at every distinct start.
* **Pitch Changes** — a new slice whenever the leading (highest) pitch of an
  onset group changes.
* **Manual Markers** — markers carried in from the import, plus any you place in
  the editor. **Ctrl-click** the piano roll to add one, **right-click** to remove
  the nearest. Edited markers are saved with the project.

### Granular

*Grains* sets how many windows are live at once (1–256) and *Size* how much of
the phrase each one reads. *Spread* decides where they sit — `Even` splits the
region into parallel slots and starts them together, `Random` scatters them,
`Cloud` clusters them around a centre. *Motion* drifts that centre across the
phrase in source-beats per project-beat; *Spray* jitters each new grain.
*Direction* runs grains forwards, backwards, alternating or randomly, and
*Pitch Spread* detunes each one. *Density* is the duty cycle of a grain slot —
below 100% each grain waits before respawning, opening gaps in the cloud.
Grains fade in and out with a raised-cosine velocity window.

## The signal path

**Note filter.** A filter that removes notes instead of frequencies. *Cutoff* is
a note number; *Slope* is how many semitones it takes to fade from full to
silent past the corner; *Width* sets the band for bandpass/notch; *Resonance*
emphasises notes sitting at the corner; *Key Track* moves the cutoff with the
played key. Anything whose weight falls below *Threshold* is dropped outright —
the rest just lose velocity. Filtered-out notes are drawn greyed in the roll.

**Amp envelope.** A standard ADSR sampled at each note-on and applied to
velocity, with a *Curve* control that bends it and an *Amount* that blends it
against the untouched velocity. Releasing a key plays the phrase out through the
release stage rather than cutting it off.

**Warping.** *Free* plays at the phrase's own recorded tempo, *Sync* locks it to
the project (so 1 source beat = 1 project beat), *Fixed Length* stretches the
whole phrase to a set number of beats. *Speed* multiplies whichever you pick.
*Start Mode* chooses between retriggering from the region start and locking to
the project timeline so voices stay phase-aligned to the grid, and *Trigger
Quantize* delays a trigger to the next 1/16 … 1 bar.

**Looping.** *Region Start/Length* trims the part of the phrase that plays at
all; *Loop Start/Length* sets the loop inside it, so playback can run in from
before the loop point the way a sampler does. *Loop Mode* is Forward, Reverse or
Ping-Pong, and *Loop Count* can stop it after *n* passes. *Reverse* mirrors the
phrase — the last note plays first and note lengths are preserved.

## Interface

The piano roll shows the loaded phrase with the region shaded, loop bounds in
amber, slice boundaries and their numbers in green, markers in violet, and a
live playhead for every sounding voice or grain. The five tabs below hold the
controls.

* Drag a knob vertically; hold **ctrl/cmd** for fine adjustment.
* **Double-click** a knob to reset it to its default.
* The mouse wheel nudges whatever is under the pointer.
* Click the file name in the header to switch source phrases.

## Notes on behaviour

* The plug-in consumes the notes that trigger it; enable **MIDI Thru** to pass
  them through as well. CC, pitch bend, aftertouch and SysEx always pass.
* The sustain pedal (CC64) is honoured, and CC120/CC123 or stopping the
  transport silences everything cleanly.
* **Output Channel** 0 keeps each source note's own channel; 1–16 forces one.
* A `(channel, pitch)` pair can only sound once at a time in MIDI, so a repeat
  of a note that is already sounding emits its note-off first. Up to 512 output
  notes can be sounding at once.

## Tests

JSFX normally only runs inside REAPER. `tests/` carries a small EEL2 interpreter
and JSFX host stub so the engine can be exercised as ordinary code — it loads the
real `.jsfx` and its imports, runs the sections, and inspects the MIDI that comes
out.

```
python3 tests/test_midular.py     # engine, modes, slicing, envelope, filter, UI
lua5.4  tests/test_import.lua      # the importer's Standard MIDI File reader
```

See [tests/README.md](tests/README.md) for what the interpreter does and does not
cover.

## Repository layout

```
Midular.jsfx               plug-in: description, sliders, sections
midular_core.jsfx-inc      memory map, sorting, source loading, slice analysis
midular_engine.jsfx-inc    note pool, envelope, filter, streams, voices, grains
midular_ui.jsfx-inc        @gfx interface
Scripts/midular_import.lua ReaScript importer (MIDI items or .mid files)
Data/midular/default.txt   demo phrase, installed into <resource>/Data/midular/
docs/FORMAT.md              source file format
tests/                      EEL2 interpreter and test suites (development only)
```

## Licence

GPL v3 — see [LICENSE](LICENSE).
