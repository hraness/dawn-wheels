"""Exercises the wheels just built, by name: python smoke.py pyworld cymem docopt."""

import sys

names = set(sys.argv[1:])

if "pyworld" in names:
    import numpy as np
    import pyworld as pw

    # The calls DAWN's voice makes, analysis then synthesis at 5 ms frames, on
    # a second of a 220 Hz sawtooth: rich in harmonics, as a voice is (harvest
    # hears a bare sine as unvoiced).
    fs, period = 24000, 5.0
    t = np.arange(fs) / fs
    x = 0.3 * ((220 * t) % 1.0 - 0.5)
    f0, times = pw.harvest(x, fs, f0_floor=70, f0_ceil=600, frame_period=period)
    sp = pw.cheaptrick(x, f0, times, fs)
    ap = pw.d4c(x, f0, times, fs)
    y = pw.synthesize(f0, sp, ap, fs, period)
    voiced = f0[f0 > 0]
    assert voiced.size > len(f0) // 2, "harvest found too little voicing"
    assert abs(float(np.median(voiced)) - 220) < 2, f"harvest heard {np.median(voiced)} Hz"
    assert np.isfinite(y).all() and abs(len(y) - len(x)) <= fs * period / 1000
    print(f"pyworld: f0 {float(np.median(voiced)):.2f} Hz, {len(y)} samples resynthesized")

if "cymem" in names:
    from cymem.cymem import Pool

    pool = Pool()
    assert pool.size == 0
    print("cymem: a pool opens")

if "docopt" in names:
    from docopt import docopt

    assert docopt("usage: x [--loud]", argv=["--loud"]) == {"--loud": True}
    print("docopt: parses")
