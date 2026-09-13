"""Bump the version, then build the release executable.

    uv run python tools/release.py            # patch: 1.0.0 -> 1.0.1
    uv run python tools/release.py minor      # minor: 1.0.3 -> 1.1.0
    uv run python tools/release.py major      # major: 1.4.2 -> 2.0.0
    uv run python tools/release.py --set 2.5.0
    uv run python tools/release.py --no-bump  # rebuild the current version
    uv run python tools/release.py --dry-run  # show what would happen

`src/mclauncher/__init__.py` holds the canonical version; pyproject.toml is kept
in step with it. If the build fails, both files are put back as they were.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = ROOT / "src" / "mclauncher" / "__init__.py"
PYPROJECT = ROOT / "pyproject.toml"
LOCKFILE = ROOT / "uv.lock"
RELEASES = ROOT / "releases"

VERSION_RE = re.compile(r'^(__version__\s*=\s*)"(\d+)\.(\d+)\.(\d+)"', re.M)


def read_version() -> tuple[int, int, int]:
    match = VERSION_RE.search(INIT.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit(f"no __version__ = \"x.y.z\" found in {INIT}")
    return int(match.group(2)), int(match.group(3)), int(match.group(4))


def bump(version: tuple[int, int, int], part: str) -> tuple[int, int, int]:
    major, minor, patch = version
    if part == "major":
        return major + 1, 0, 0
    if part == "minor":
        return major, minor + 1, 0
    return major, minor, patch + 1


def set_init_version(text: str, version: str) -> str:
    new, count = VERSION_RE.subn(lambda m: f'{m.group(1)}"{version}"', text, count=1)
    if count != 1:
        raise SystemExit("could not rewrite __version__")
    return new


def set_pyproject_version(text: str, version: str) -> str:
    """Rewrite `version = ...` inside [project] only, leaving other tables alone."""
    out, section, done = [], "", False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped
        elif section == "[project]" and not done and re.match(r'version\s*=\s*"', stripped):
            line = f'version = "{version}"\n'
            done = True
        out.append(line)
    if not done:
        raise SystemExit("no version field found under [project] in pyproject.toml")
    return "".join(out)


def embedded_version(exe: Path) -> str | None:
    """Read the version resource Windows shows in the file's properties."""
    if not sys.platform.startswith("win"):
        return None
    import ctypes
    import ctypes.wintypes as wintypes

    if not exe.is_file():
        return None
    version_dll = ctypes.WinDLL("version.dll")
    version_dll.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    version_dll.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    version_dll.GetFileVersionInfoW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p
    ]
    version_dll.VerQueryValueW.argtypes = [
        ctypes.c_void_p, wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint),
    ]

    path = str(exe)
    size = version_dll.GetFileVersionInfoSizeW(path, None)
    if not size:
        return None
    buffer = ctypes.create_string_buffer(size)
    if not version_dll.GetFileVersionInfoW(path, 0, size, buffer):
        return None
    block = ctypes.c_void_p()
    length = ctypes.c_uint()
    if not version_dll.VerQueryValueW(buffer, "\\", ctypes.byref(block), ctypes.byref(length)):
        return None
    fixed = ctypes.cast(block, ctypes.POINTER(ctypes.c_uint32 * 13)).contents
    ms, ls = fixed[2], fixed[3]  # dwFileVersionMS, dwFileVersionLS
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"


def check_source_versions(version: str) -> list[str]:
    """Catch hardcoded version strings that a bump would silently leave behind."""
    problems = []
    core = (ROOT / "src" / "mclauncher" / "core.py").read_text(encoding="utf-8")
    if re.search(r'^LAUNCHER_VERSION\s*=\s*"', core, re.M):
        problems.append("core.py defines its own LAUNCHER_VERSION instead of using __version__")
    pyproject_version = re.search(
        r'(?m)^version\s*=\s*"([^"]+)"', PYPROJECT.read_text(encoding="utf-8")
    )
    if not pyproject_version or pyproject_version.group(1) != version:
        problems.append(f"pyproject.toml version is not {version}")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description="Bump the version and build a release")
    parser.add_argument(
        "part", nargs="?", default="patch", choices=("major", "minor", "patch"),
        help="which number to increase (default: patch)",
    )
    parser.add_argument("--set", dest="exact", help="use this exact version instead of bumping")
    parser.add_argument("--no-bump", action="store_true", help="rebuild without changing the version")
    parser.add_argument("--standalone", action="store_true", help="folder build instead of onefile")
    parser.add_argument("--console", action="store_true", help="keep a console window (debugging)")
    parser.add_argument("--clean", action="store_true", help="wipe build/ first")
    parser.add_argument("--clean-releases", action="store_true", help="also empty releases/")
    parser.add_argument("--tag", action="store_true", help="also create a git tag v<version>")
    parser.add_argument("--dry-run", action="store_true", help="show the plan, change nothing")
    args = parser.parse_args()

    old = read_version()
    old_str = ".".join(map(str, old))

    if args.no_bump:
        new_str = old_str
    elif args.exact:
        if not re.fullmatch(r"\d+\.\d+\.\d+", args.exact):
            raise SystemExit(f"--set expects x.y.z, got {args.exact!r}")
        new_str = args.exact
    else:
        new_str = ".".join(map(str, bump(old, args.part)))

    label = "rebuilding" if new_str == old_str else f"{old_str} -> {new_str}"
    print(f"[release] version: {label}", flush=True)

    init_before = INIT.read_text(encoding="utf-8")
    pyproject_before = PYPROJECT.read_text(encoding="utf-8")

    if args.dry_run:
        print("[release] dry run: no files written, no build started", flush=True)
        return

    lock_before = LOCKFILE.read_text(encoding="utf-8") if LOCKFILE.is_file() else None
    if new_str != old_str:
        INIT.write_text(set_init_version(init_before, new_str), encoding="utf-8")
        PYPROJECT.write_text(set_pyproject_version(pyproject_before, new_str), encoding="utf-8")
        print(f"[release] wrote {INIT.name} and {PYPROJECT.name}", flush=True)
        # uv.lock records the project version too; refresh it so a release does
        # not leave the repository dirty.
        locked = subprocess.run(
            ["uv", "lock", "--quiet"], cwd=ROOT, capture_output=True, text=True
        )
        if locked.returncode == 0:
            print(f"[release] refreshed {LOCKFILE.name}", flush=True)
        else:
            print(f"[release] note: could not refresh {LOCKFILE.name} ({locked.stderr.strip()})", flush=True)

    cmd = [sys.executable, str(ROOT / "build.py")]
    for flag in ("standalone", "console", "clean", "clean_releases"):
        if getattr(args, flag):
            cmd.append("--" + flag.replace("_", "-"))
    print(f"[release] building: {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=ROOT)

    if result.returncode != 0:
        INIT.write_text(init_before, encoding="utf-8")
        PYPROJECT.write_text(pyproject_before, encoding="utf-8")
        if lock_before is not None:
            LOCKFILE.write_text(lock_before, encoding="utf-8")
        raise SystemExit(f"[release] build failed; version rolled back to {old_str}")

    if args.tag:
        tag = f"v{new_str}"
        tagged = subprocess.run(["git", "tag", tag], cwd=ROOT)
        print(f"[release] {'tagged ' + tag if tagged.returncode == 0 else 'could not create tag ' + tag}", flush=True)

    problems = check_source_versions(new_str)

    print(f"\n[release] {new_str} is in {RELEASES}:", flush=True)
    artifacts = sorted(RELEASES.glob(f"*{new_str}*"))
    if not artifacts:
        problems.append(f"no artifact named *{new_str}* was produced")
    for item in artifacts:
        size = (
            item.stat().st_size
            if item.is_file()
            else sum(p.stat().st_size for p in item.rglob("*") if p.is_file())
        )
        exe = item if item.is_file() else item / "MCLauncher.exe"
        stamped = embedded_version(exe) if exe.is_file() else None
        detail = f"file version {stamped}" if stamped else "no version resource"
        print(f"    {item.name}  ({size / 1e6:.0f} MB, {detail})")
        if stamped and not stamped.startswith(new_str + "."):
            problems.append(f"{item.name} reports version {stamped}, expected {new_str}.x")

    if problems:
        print("\n[release] VERSION CHECK FAILED:", flush=True)
        for problem in problems:
            print(f"    - {problem}", flush=True)
        raise SystemExit(1)
    print(f"[release] version check passed: everything reports {new_str}", flush=True)


if __name__ == "__main__":
    main()
