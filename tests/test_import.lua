--[[ Tests midular_import.lua's Standard MIDI File reader without REAPER.

       lua5.4 tests/test_import.lua
--]]

local here = (arg[0] or ''):match('^(.*)[/\\]') or '.'

local pass, fail = 0, 0
local function check(label, cond, detail)
  if cond then pass = pass + 1 else fail = fail + 1 end
  print(string.format('  %-52s %s%s', label, cond and 'ok' or 'FAIL',
                      detail and ('   ' .. detail) or ''))
end

-- ---------------------------------------------------------------- fixture
local function vlq(n)
  local out = { n % 128 }
  n = math.floor(n / 128)
  while n > 0 do
    table.insert(out, 1, (n % 128) + 128)
    n = math.floor(n / 128)
  end
  return string.char(table.unpack(out))
end

local function u32(n)
  return string.char(math.floor(n / 16777216) % 256, math.floor(n / 65536) % 256,
                     math.floor(n / 256) % 256, n % 256)
end

local function u16(n) return string.char(math.floor(n / 256) % 256, n % 256) end
local function chunk(tag, data) return tag .. u32(#data) .. data end

local TPQ = 480

-- track 0: tempo 120, 3/4, a marker on beat 3
local t0 = vlq(0) .. '\xff\x51\x03' .. string.char(0x07, 0xa1, 0x20)
        .. vlq(0) .. '\xff\x58\x04' .. string.char(3, 2, 24, 8)
        .. vlq(TPQ * 3) .. '\xff\x06' .. vlq(4) .. 'mk01'
        .. vlq(0) .. '\xff\x2f\x00'

-- track 1: four notes using running status and note-on-velocity-0 for note-offs
local notes = { { 0, TPQ, 60, 100 }, { TPQ, TPQ // 2, 64, 90 },
                { TPQ, TPQ, 67, 80 }, { TPQ * 3, TPQ * 2, 72, 110 } }
local events = {}
for _, n in ipairs(notes) do
  events[#events + 1] = { n[1], n[3], n[4] }
  events[#events + 1] = { n[1] + n[2], n[3], 0 }
end
table.sort(events, function(a, b)
  if a[1] ~= b[1] then return a[1] < b[1] end
  return (a[3] == 0 and 0 or 1) < (b[3] == 0 and 0 or 1)
end)
local t1, last, running = '', 0, nil
for _, e in ipairs(events) do
  t1 = t1 .. vlq(e[1] - last); last = e[1]
  if running ~= 0x90 then t1 = t1 .. string.char(0x90); running = 0x90 end
  t1 = t1 .. string.char(e[2], e[3])
end
t1 = t1 .. vlq(0) .. '\xff\x2f\x00'

local mid = chunk('MThd', u16(1) .. u16(2) .. u16(TPQ)) .. chunk('MTrk', t0) .. chunk('MTrk', t1)

-- ------------------------------------------------------ load as a library
local path = here .. '/../Scripts/midular_import.lua'
local src = assert(io.open(path)):read('*a')
src = src:gsub('reaper%.Undo_BeginBlock%(%)%s*main%(%)%s*reaper%.Undo_EndBlock%b()', '')
src = src .. '\nreturn { parse_smf = parse_smf, write_phrase = write_phrase, sanitize = sanitize }\n'
reaper = { ShowMessageBox = function() end }
local M = assert(load(src, 'midular_import'))()

print('\nStandard MIDI File reader')
local ph, err = M.parse_smf(mid)
check('parses the file', ph ~= nil, err)
check('reads the tempo meta event', ph.tempo == 120, tostring(ph.tempo))
check('reads the time signature', ph.tsnum == 3 and ph.tsden == 4,
      ph.tsnum .. '/' .. ph.tsden)
check('pairs all four notes', #ph.notes == 4, tostring(#ph.notes))
check('converts ticks to beats', ph.notes[1][1] == 0 and ph.notes[1][2] == 1)
check('handles running status', ph.notes[2][3] == 64 and ph.notes[2][2] == 0.5)
check('treats note-on velocity 0 as note-off', ph.notes[4][2] == 2)
check('keeps channel and velocity', ph.notes[1][4] == 100 and ph.notes[1][5] == 0)
check('reads marker meta events', #ph.markers == 1 and ph.markers[1] == 3)
check('rounds the length out to whole bars', ph.length == 6, tostring(ph.length))

print('\nrejection and naming')
local bad, berr = M.parse_smf('not a midi file at all')
check('rejects a non-MIDI file', bad == nil, tostring(berr))
check('sanitize strips unsafe characters', M.sanitize('My Loop #1!') == 'My Loop _1_.txt')
check('sanitize supplies a name', M.sanitize('') == 'phrase.txt')
check('sanitize keeps an existing extension', M.sanitize('a.txt') == 'a.txt')

print('\nwriter')
local tmp = os.tmpname()
check('writes a source file', M.write_phrase(ph, tmp))
local out = assert(io.open(tmp)):read('*a')
os.remove(tmp)
check('starts with the magic number', out:match('\n7473\n') ~= nil)
check('declares the right note count', out:match('\n4\n') ~= nil)
check('emits one record per note', select(2, out:gsub('\n[%d%.]+, [%d%.]+, %d+, %d+, %d+', '')) == 4)

print(string.format('\n%d passed, %d failed', pass, fail))
os.exit(fail > 0 and 1 or 0)
