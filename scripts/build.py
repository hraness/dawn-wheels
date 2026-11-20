#!/usr/bin/env python3
"""Builds this repository's wheels for one target.

    python scripts/build.py <target> <out-dir>

<target> is darwin-arm64, linux-x86_64, linux-aarch64, or any for the pure
Python wheels. Run it with the CPython 3.12 the wheels are for, on the
machine they are for: the workflow uses uv's CPython 3.12.14 on macOS and
the manylinux_2_28 image's CPython 3.12 on Linux.

Each source in sources.txt for the target is fetched from PyPI and checked
against its SHA-256. It is built without build isolation, by the tools
pinned with hashes in requirements/build.txt, so nothing unpinned is
fetched. Every licence text in the source goes into the wheel. A Linux
wheel is then repaired by auditwheel to manylinux_2_28; a macOS wheel must
link nothing outside the system. Last, the wheels are
installed into a fresh environment beside the pinned numpy and setuptools
and exercised by scripts/smoke.py.
"""

import base64
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ("darwin-arm64", "linux-x86_64", "linux-aarch64", "any")
LICENSE_NAMES = ("licence", "license", "copying", "notice")
# Zip entries carry this time, so a rebuild of the same inputs can match.
SOURCE_DATE_EPOCH = "315532800"


def sources(target):
    for line in (ROOT / "sources.txt").read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, version, targets, sha256, url = line.split()
        if target in targets.split(","):
            yield name, version, sha256, url


def run(*args, **kwargs):
    print("+", " ".join(str(a) for a in args), flush=True)
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def fetch(url, sha256, into):
    if not url.startswith("https://files.pythonhosted.org/"):
        sys.exit(f"{url}: sources come from PyPI's file host")
    request = urllib.request.Request(url, headers={"User-Agent": "dawn-wheels-build"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    got = hashlib.sha256(data).hexdigest()
    if got != sha256:
        sys.exit(f"{url}: sha256 {got}, not {sha256}")
    path = into / url.rsplit("/", 1)[1]
    path.write_bytes(data)
    return path


def environment(path):
    run(sys.executable, "-m", "venv", path)
    python = path / "bin" / "python"
    run(python, "-m", "pip", "install", "--no-input", "--require-hashes",
        "--only-binary", ":all:", "--no-deps", "-r", ROOT / "requirements" / "build.txt")
    return python


def host():
    system = {"Darwin": "darwin", "Linux": "linux"}.get(platform.system(), platform.system())
    return f"{system}-{platform.machine()}"


def add_licenses(wheel, sdist):
    """Puts every licence text in the source into the wheel's dist-info.

    setuptools copies only the top-level ones, and pyworld's binary carries
    the WORLD vocoder, whose BSD licence is in lib/World and must travel with
    it. A text the wheel already has is not added twice.
    """
    texts = {}
    with tarfile.open(sdist, "r:gz") as source:
        for member in source.getmembers():
            path = member.name.split("/", 1)[-1]
            if member.isfile() and "/" in member.name and Path(path).name.lower().startswith(LICENSE_NAMES):
                texts[path] = source.extractfile(member).read()
    with zipfile.ZipFile(wheel) as archive:
        entries = [(info, archive.read(info)) for info in archive.infolist()]
    [record] = [info for info, _ in entries if info.filename.endswith(".dist-info/RECORD")]
    licenses = record.filename.rsplit("/", 1)[0] + "/licenses/"
    have = {hashlib.sha256(data).digest() for info, data in entries if info.filename.startswith(licenses)}
    added = {
        licenses + path: data
        for path, data in sorted(texts.items())
        if hashlib.sha256(data).digest() not in have
    }
    if not added:
        return
    lines = [line for line in dict((i.filename, d) for i, d in entries)[record.filename].decode().splitlines() if line]
    own = [line for line in lines if line.startswith(record.filename + ",")]
    lines = [line for line in lines if line not in own]
    for name, data in added.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        lines.append(f"{name},sha256={digest},{len(data)}")
    lines += own
    rewritten = wheel.with_suffix(".tmp")
    with zipfile.ZipFile(rewritten, "w", zipfile.ZIP_DEFLATED) as archive:
        for info, data in entries:
            if info.filename != record.filename:
                archive.writestr(info, data)
        for name, data in added.items():
            archive.writestr(zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), data, zipfile.ZIP_DEFLATED)
        archive.writestr(record, "\n".join(lines) + "\n")
    rewritten.replace(wheel)
    print(f"{wheel.name}: added {', '.join(added)}")


def system_only(wheel, scratch):
    """A macOS wheel's libraries may link only what every Mac has."""
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(scratch)
    for library in scratch.rglob("*.so"):
        linked = run("otool", "-L", library, capture_output=True, text=True).stdout
        for line in linked.splitlines()[1:]:
            path = line.strip().split(" (", 1)[0]
            if not path.startswith(("/usr/lib/", "/System/Library/")):
                sys.exit(f"{wheel.name}: {library.name} links {path}")


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in TARGETS:
        sys.exit(__doc__)
    target, out = sys.argv[1], Path(sys.argv[2]).resolve()
    if sys.version_info[:2] != (3, 12):
        sys.exit(f"build with CPython 3.12, not {platform.python_version()}")
    if target != "any" and host() != target:
        sys.exit(f"{target} wheels are built on {target}, not on {host()}")
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, SOURCE_DATE_EPOCH=SOURCE_DATE_EPOCH, PIP_DISABLE_PIP_VERSION_CHECK="1")
    if target == "darwin-arm64":
        env.update(MACOSX_DEPLOYMENT_TARGET="11.0", ARCHFLAGS="-arch arm64")
    with tempfile.TemporaryDirectory() as scratch:
        scratch = Path(scratch)
        build = environment(scratch / "build")
        names, wheels = [], []
        for name, version, sha256, url in sources(target):
            sdist = fetch(url, sha256, scratch)
            raw, fixed = scratch / f"{name}-raw", scratch / f"{name}-fixed"
            raw.mkdir()
            fixed.mkdir()
            run(build, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "--no-index",
                "--no-cache-dir", "-w", raw, sdist, env=env)
            [wheel] = raw.glob("*.whl")
            add_licenses(wheel, sdist)
            if wheel.name.endswith("-none-any.whl"):
                shutil.copy2(wheel, fixed)
            elif target.startswith("linux-"):
                arch = target.split("-", 1)[1]
                run("auditwheel", "repair", "--plat", f"manylinux_2_28_{arch}", "-w", fixed, wheel, env=env)
            else:
                system_only(wheel, scratch / f"{name}-unpacked")
                shutil.copy2(wheel, fixed)
            [wheel] = fixed.glob("*.whl")
            if not wheel.name.startswith(f"{name}-{version}-"):
                sys.exit(f"{wheel.name} is not {name} {version}")
            shutil.copy2(wheel, out / wheel.name)
            names.append(name)
            wheels.append(out / wheel.name)
        if not wheels:
            sys.exit(f"nothing to build for {target}")
        smoke = environment(scratch / "smoke")
        run(smoke, "-m", "pip", "install", "--no-deps", "--no-index", *wheels)
        run(smoke, "-I", ROOT / "scripts" / "smoke.py", *names)
    for wheel in wheels:
        print(hashlib.sha256(wheel.read_bytes()).hexdigest(), wheel.name)


if __name__ == "__main__":
    main()
