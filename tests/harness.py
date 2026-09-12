import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jsfx import Plugin
from runtime import truthy

SRATE = 48000.0

class Host:
    def __init__(self, path, srcfile=None):
        self.p = Plugin(path)
        self.p.compile()
        ip = self.p.ip
        ip.g.update(dict(srate=SRATE, num_ch=2.0, samplesblock=0.0, tempo=120.0,
                         play_state=1.0, play_position=0.0, beat_position=0.0,
                         ts_num=4.0, ts_denom=4.0, gfx_w=920.0, gfx_h=600.0,
                         mouse_x=-1.0, mouse_y=-1.0, mouse_cap=0.0, mouse_wheel=0.0,
                         gfx_texth=12.0, gfx_ext_retina=1.0))
        if srcfile: ip.file_paths[0] = srcfile
        self.beat = 0.0
        self.p.run('init')
        self.p.run('slider')

    @property
    def ip(self): return self.p.ip

    def set_slider(self, n, v):
        self.ip.g['slider%d' % n] = float(v)
        self.p.run('slider')

    def block(self, nsamples, midi=None, tempo=120.0):
        ip = self.ip
        ip.g['samplesblock'] = float(nsamples)
        ip.g['tempo'] = float(tempo)
        ip.g['beat_position'] = self.beat
        ip.midi_in = list(midi or [])
        ip.midi_out = []
        self.p.run('block')
        self.beat += nsamples * tempo / 60.0 / SRATE
        return list(ip.midi_out)

    def gfx(self):
        self.p.run('gfx')

def note_on(off, p, v, ch=0):  return (off, 0x90 | ch, p, v)
def note_off(off, p, ch=0):    return (off, 0x80 | ch, p, 0)

def summarize(events, base=0):
    out = []
    for off, m1, m2, m3 in events:
        kind = 'on ' if (m1 & 0xF0) == 0x90 and m3 > 0 else 'off'
        out.append((base + off, kind, m2, m3, m1 & 0x0F))
    return out
