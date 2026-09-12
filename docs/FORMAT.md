# Granumid source format (`.txt`)

## Why a text file

JSFX has no Standard MIDI File reader. What it *does* have is a documented text
mode: a file-slider (`slider1:/granumid:default.txt:Source File`) browses
`<REAPER resource path>/Data/<dir>` for `.wav`, `.txt`, `.ogg` and `.raw` files,
and a `.txt` opened with `file_open()` is tokenised into numbers separated by
commas or newlines, with `#` and `;` starting comments. `file_var()` then reads
one number at a time.

So a Granumid source is just a list of numbers. It stays readable, diffable and
hand-editable, and `granumid_import.lua` writes it from either a MIDI item or a
`.mid` file on disk.

## Layout

Whitespace, newlines and commas are all equivalent separators. Comments run from
`#` or `;` to the end of the line. Values are read strictly in order.

### Header — 12 records

| # | Field | Notes |
| --- | --- | --- |
| 1 | `magic` | must be `7473`, otherwise the file is rejected |
| 2 | `version` | currently `1` |
| 3 | `lengthBeats` | total phrase length in quarter notes; `0` means "derive from the last note end" |
| 4 | `noteCount` | number of note records that follow (max 32768) |
| 5 | `tempo` | the phrase's own tempo in BPM, used by Warp = *Free* |
| 6 | `tsNum` | time signature numerator, used for bar grids |
| 7 | `tsDen` | time signature denominator |
| 8 | `markerCount` | number of marker records after the notes (max 256) |
| 9–12 | reserved | write `0` |

### Notes — 5 records each

| Field | Range |
| --- | --- |
| `startBeat` | quarter notes from the start of the phrase |
| `lengthBeats` | quarter notes, clamped to a minimum of 0.001 |
| `pitch` | 0–127 |
| `velocity` | 1–127 |
| `channel` | 0–15 |

Notes do not have to be sorted; Granumid builds its own forward and reverse
orderings when the file is loaded.

### Markers — 1 record each

Positions in quarter notes, used by the **Manual Markers** slice method. They
are expected in ascending order. Markers edited in the plug-in are stored in the
project rather than written back to the file, and take precedence over the
file's own markers once edited.

## Example

```
# Granumid MIDI source
7473            # magic
1               # version
4.000000        # length in beats
3               # note count
120.000000      # source tempo
4, 4            # time signature
1               # marker count
0, 0, 0, 0      # reserved

# startBeat, lengthBeats, pitch, velocity, channel
0.000000, 0.500000, 60, 100, 0
1.000000, 0.500000, 64,  90, 0
2.000000, 1.000000, 67,  80, 0

# markers
2.000000
```

## Limits

* 32768 notes per phrase
* 256 markers
* 128 slices produced by the slice analyser
* 256 grains and 16 voices at once, 512 simultaneously sounding output notes
