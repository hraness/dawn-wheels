# dawn-wheels

Prebuilt Python wheels for the few packages in [DAWN](https://dawnav.com)'s voice environment that PyPI has only as source for the machines DAWN runs on. With them, DAWN installs that environment on an Apple Silicon Mac or on Linux without a compiler, and pins every file in it by its SHA-256.

| Package | Version | Wheels                                                           |
| ------- | ------- | ---------------------------------------------------------------- |
| pyworld | 0.3.5   | CPython 3.12: macOS 11+ on arm64, manylinux_2_28 x86_64, aarch64 |
| cymem   | 2.0.10  | CPython 3.12: manylinux_2_28 aarch64                             |
| docopt  | 0.6.2   | any Python 3                                                     |

## How it works

```
sources.txt           PyPI URL and SHA-256 of each source release
      │
      ▼
scripts/build.py      fetch, check the hash, build without build isolation
      │               using requirements/build.txt (every file pinned by hash)
      │                 macOS   GitHub's macos-15, uv's CPython 3.12.14
      │                 Linux   manylinux_2_28 image pinned by digest,
      │                         then auditwheel repair
      ▼
scripts/smoke.py      install the wheels into a fresh environment and run them
      │
      ▼  (tag v*)
release               the wheels and SHA256SUMS as an immutable release,
                      each wheel with a build provenance attestation
```

Each wheel is built on the machine it is for, from the source release named in `sources.txt` and no other file. The build adds every licence text from the source to the wheel's `dist-info/licenses`, so pyworld's wheel carries the WORLD vocoder's licence beside pyworld's own.

## Check a wheel

```sh
gh release download v1 --repo hraness/dawn-wheels --pattern 'pyworld-*'
gh attestation verify pyworld-0.3.5-cp312-cp312-macosx_11_0_arm64.whl --repo hraness/dawn-wheels
```

## Build one

```sh
python3.12 -I scripts/build.py darwin-arm64 dist   # or linux-x86_64, linux-aarch64, any
```

A machine builds only its own target. `requirements/build.txt` is made from `requirements/build.in` with uv:

```sh
uv pip compile --universal --python-version 3.12 --generate-hashes \
  --no-header --no-annotate requirements/build.in -o requirements/build.txt
```

## Licences

The scripts here are MIT (`LICENSE`). Each wheel is its project's code under its project's licences, which the wheel carries: pyworld (MIT, with the WORLD vocoder under its modified BSD licence), cymem (MIT) and docopt (MIT).
