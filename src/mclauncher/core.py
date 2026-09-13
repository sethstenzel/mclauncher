"""Core Minecraft install/launch logic.

No Microsoft/Mojang authentication is used: the player UUID is derived from the
username the same way vanilla servers do for offline-mode players, so a home
server running with online-mode=false sees a stable identity per name.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable
from urllib.request import Request, urlopen

from . import __version__ as LAUNCHER_VERSION  # single source of truth for the version

LAUNCHER_NAME = "MCLauncher"

VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
JAVA_RUNTIME_ALL_URL = (
    "https://piston-meta.mojang.com/v1/products/java-runtime/"
    "2ec0cc96c44e5a76b9c8b7c39df7210883d12871/all.json"
)
RESOURCES_URL = "https://resources.download.minecraft.net"
USER_AGENT = f"{LAUNCHER_NAME}/{LAUNCHER_VERSION}"

DOWNLOAD_THREADS = 16

LogFn = Callable[[str], None]
ProgressFn = Callable[[int, int, str], None]


# --------------------------------------------------------------------------- #
# platform helpers
# --------------------------------------------------------------------------- #
def os_name() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "osx"
    return "linux"


def os_arch() -> str:
    m = platform.machine().lower()
    if m in ("amd64", "x86_64"):
        return "x86_64"
    if m in ("i386", "i686", "x86"):
        return "x86"
    if m in ("arm64", "aarch64"):
        return "arm64"
    return m


def natives_arch_bits() -> str:
    return "64" if os_arch() in ("x86_64", "arm64") else "32"


def java_platform_key() -> str:
    name, arch = os_name(), os_arch()
    if name == "windows":
        return {
            "x86_64": "windows-x64",
            "x86": "windows-x86",
            "arm64": "windows-arm64",
        }.get(arch, "windows-x64")
    if name == "osx":
        return "mac-os-arm64" if arch == "arm64" else "mac-os"
    return "linux-i386" if arch == "x86" else "linux"


def default_game_dir() -> Path:
    if os_name() == "windows":
        return Path(os.environ.get("APPDATA", Path.home())) / ".minecraft"
    if os_name() == "osx":
        return Path.home() / "Library" / "Application Support" / "minecraft"
    return Path.home() / ".minecraft"


def launcher_data_dir() -> Path:
    if os_name() == "windows":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif os_name() == "osx":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / LAUNCHER_NAME


# --------------------------------------------------------------------------- #
# offline identity
# --------------------------------------------------------------------------- #
def offline_uuid(username: str) -> uuid.UUID:
    """The UUID a vanilla offline-mode server assigns to a player name."""
    digest = bytearray(hashlib.md5(f"OfflinePlayer:{username}".encode("utf-8")).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30  # version 3
    digest[8] = (digest[8] & 0x3F) | 0x80  # RFC 4122 variant
    return uuid.UUID(bytes=bytes(digest))


USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")


def validate_username(name: str) -> str | None:
    if not USERNAME_RE.match(name or ""):
        return "3-16 characters: letters, numbers, underscore"
    return None


# --------------------------------------------------------------------------- #
# http / download
# --------------------------------------------------------------------------- #
def http_bytes(url: str, retries: int = 3, timeout: int = 30) -> bytes:
    last: Exception | None = None
    for _ in range(retries):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # transient network errors are common here
            last = exc
    raise RuntimeError(f"download failed: {url} ({last})")


def http_json(url: str) -> dict:
    return json.loads(http_bytes(url).decode("utf-8"))


@dataclass
class DownloadItem:
    url: str
    dest: Path
    sha1: str | None = None
    size: int | None = None

    def is_present(self) -> bool:
        if not self.dest.is_file():
            return False
        if self.size is not None and self.dest.stat().st_size != self.size:
            return False
        return True


class Cancelled(Exception):
    pass


# --------------------------------------------------------------------------- #
# version metadata
# --------------------------------------------------------------------------- #
@dataclass
class VersionEntry:
    id: str
    type: str
    url: str
    release_time: str


def manifest_cache_path() -> Path:
    return launcher_data_dir() / "version_manifest_v2.json"


def _parse_manifest(data: dict) -> list[VersionEntry]:
    return [
        VersionEntry(v["id"], v["type"], v["url"], v.get("releaseTime", ""))
        for v in data.get("versions", [])
    ]


def cached_versions() -> list[VersionEntry]:
    """The last manifest we saw, so the UI has something to show immediately."""
    cache = manifest_cache_path()
    if not cache.is_file():
        return []
    try:
        return _parse_manifest(json.loads(cache.read_text(encoding="utf-8")))
    except Exception:
        return []


def fetch_versions(max_age: float = 900) -> list[VersionEntry]:
    """Version list from Mojang, falling back to the cached copy when offline."""
    cache = manifest_cache_path()
    if max_age and cache.is_file():
        age = time.time() - cache.stat().st_mtime
        if age < max_age:
            versions = cached_versions()
            if versions:
                return versions
    try:
        raw = http_bytes(VERSION_MANIFEST_URL)
    except Exception:
        versions = cached_versions()
        if versions:
            return versions
        raise
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(raw)
    return _parse_manifest(json.loads(raw.decode("utf-8")))


def rules_allow(rules: list | None, features: dict | None = None) -> bool:
    if not rules:
        return True
    features = features or {}
    allowed = False
    for rule in rules:
        action = rule.get("action") == "allow"
        ok = True
        osr = rule.get("os")
        if osr:
            if "name" in osr and osr["name"] != os_name():
                ok = False
            if "arch" in osr and osr["arch"] != os_arch():
                ok = False
            if "version" in osr and not re.search(osr["version"], platform.release()):
                ok = False
        for key, want in (rule.get("features") or {}).items():
            if bool(features.get(key, False)) != bool(want):
                ok = False
        if ok:
            allowed = action
    return allowed


def maven_to_path(name: str) -> str:
    """`group:artifact:version[:classifier][@ext]` -> maven relative path."""
    parts = name.split(":")
    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) > 3 else None
    ext = "jar"
    if classifier and "@" in classifier:
        classifier, ext = classifier.split("@", 1)
    elif "@" in version:
        version, ext = version.split("@", 1)
    filename = f"{artifact}-{version}"
    if classifier:
        filename += f"-{classifier}"
    filename += f".{ext}"
    return "/".join(group.split(".") + [artifact, version, filename])


@dataclass
class LaunchPlan:
    version_id: str
    java: Path
    classpath: list[Path]
    natives_dir: Path
    main_class: str
    jvm_args: list[str]
    game_args: list[str]
    game_dir: Path


class Installer:
    """Downloads everything a version needs, then builds its launch command."""

    def __init__(
        self,
        game_dir: Path | str,
        log: LogFn | None = None,
        progress: ProgressFn | None = None,
    ) -> None:
        self.game_dir = Path(game_dir)
        self.log = log or (lambda m: None)
        self.progress = progress or (lambda d, t, label: None)
        self.cancel = threading.Event()

    # -- paths ------------------------------------------------------------- #
    @property
    def versions_dir(self) -> Path:
        return self.game_dir / "versions"

    @property
    def libraries_dir(self) -> Path:
        return self.game_dir / "libraries"

    @property
    def assets_dir(self) -> Path:
        return self.game_dir / "assets"

    # -- downloading ------------------------------------------------------- #
    def _check_cancel(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()

    def _download_one(self, item: DownloadItem) -> None:
        self._check_cancel()
        item.dest.parent.mkdir(parents=True, exist_ok=True)
        data = http_bytes(item.url)
        if item.sha1:
            got = hashlib.sha1(data).hexdigest()
            if got != item.sha1:
                raise RuntimeError(f"checksum mismatch for {item.url}")
        # Unique scratch name: two launchers downloading the same file at the
        # same time must not write through each other's partial copy.
        tmp = item.dest.with_name(f"{item.dest.name}.{os.getpid()}-{threading.get_ident()}.part")
        try:
            tmp.write_bytes(data)
            tmp.replace(item.dest)
        finally:
            tmp.unlink(missing_ok=True)

    def download_all(self, items: Iterable[DownloadItem], label: str) -> None:
        todo = [i for i in items if not i.is_present()]
        total = len(todo)
        if not total:
            self.progress(1, 1, f"{label}: up to date")
            return
        self.log(f"{label}: {total} file(s) to download")
        done = 0
        lock = threading.Lock()
        errors: list[Exception] = []

        def work(item: DownloadItem) -> None:
            nonlocal done
            try:
                self._download_one(item)
            except Cancelled:
                pass
            except Exception as exc:
                with lock:
                    errors.append(exc)
            with lock:
                done += 1
                self.progress(done, total, f"{label} ({done}/{total})")

        with ThreadPoolExecutor(max_workers=DOWNLOAD_THREADS) as pool:
            list(pool.map(work, todo))
        self._check_cancel()
        if errors:
            raise RuntimeError(f"{label}: {len(errors)} download(s) failed - {errors[0]}")

    # -- version json ------------------------------------------------------ #
    def version_json_path(self, version_id: str) -> Path:
        return self.versions_dir / version_id / f"{version_id}.json"

    def load_version(
        self, version_id: str, manifest: dict[str, VersionEntry] | None = None
    ) -> dict:
        """Load a version json, downloading it if missing, resolving inheritance."""
        path = self.version_json_path(version_id)
        if not path.is_file():
            if manifest is None:
                manifest = {v.id: v for v in fetch_versions()}
            entry = manifest.get(version_id)
            if entry is None:
                raise RuntimeError(f"unknown version: {version_id}")
            self.log(f"fetching metadata for {version_id}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(http_bytes(entry.url))
        data = json.loads(path.read_text(encoding="utf-8"))
        parent_id = data.get("inheritsFrom")
        if parent_id:  # modded profiles (Fabric/Forge) chain onto a vanilla version
            data = merge_versions(self.load_version(parent_id, manifest), data)
        return data

    # -- pieces ------------------------------------------------------------ #
    def _client_jar(self, version: dict) -> Path:
        jar_id = version.get("jar", version["id"])
        dest = self.versions_dir / jar_id / f"{jar_id}.jar"
        info = (version.get("downloads") or {}).get("client")
        if info:
            self.download_all(
                [DownloadItem(info["url"], dest, info.get("sha1"), info.get("size"))],
                "client jar",
            )
        elif not dest.is_file():
            raise RuntimeError(f"no client jar available for {jar_id}")
        return dest

    def _libraries(self, version: dict) -> tuple[list[Path], list[tuple[Path, dict]]]:
        """Returns (classpath entries, [(jar, extract rules)] to unpack as natives)."""
        items: list[DownloadItem] = []
        classpath: list[Path] = []
        natives: list[tuple[Path, dict]] = []
        seen: set[str] = set()

        for lib in version.get("libraries", []):
            if not rules_allow(lib.get("rules")):
                continue
            name = lib.get("name", "")
            downloads = lib.get("downloads") or {}
            artifact = downloads.get("artifact")

            if artifact or "classifiers" not in downloads:
                rel = (artifact or {}).get("path") or maven_to_path(name)
                if rel not in seen:
                    seen.add(rel)
                    dest = self.libraries_dir / rel
                    classpath.append(dest)
                    url = (artifact or {}).get("url")
                    if not url:
                        base = lib.get("url") or "https://libraries.minecraft.net/"
                        url = base.rstrip("/") + "/" + rel
                    items.append(
                        DownloadItem(
                            url, dest, (artifact or {}).get("sha1"), (artifact or {}).get("size")
                        )
                    )

            # pre-1.19 natives: a per-OS classifier jar that gets unzipped
            classifier = (lib.get("natives") or {}).get(os_name())
            if classifier:
                classifier = classifier.replace("${arch}", natives_arch_bits())
                native = (downloads.get("classifiers") or {}).get(classifier)
                if native:
                    dest = self.libraries_dir / native["path"]
                    items.append(
                        DownloadItem(native["url"], dest, native.get("sha1"), native.get("size"))
                    )
                    natives.append((dest, lib.get("extract") or {}))

        self.download_all(items, "libraries")
        return classpath, natives

    def _extract_natives(self, natives: list[tuple[Path, dict]], natives_dir: Path) -> None:
        if not natives:
            natives_dir.mkdir(parents=True, exist_ok=True)
            return

        # Re-extracting on every launch would pull the natives out from under a
        # copy of the game that another launcher already started from this same
        # folder, so only do it when the contents would actually change.
        marker = natives_dir / ".natives.json"
        signature = sorted(
            f"{jar.name}:{jar.stat().st_size if jar.is_file() else 0}" for jar, _ in natives
        )
        if marker.is_file():
            try:
                if json.loads(marker.read_text(encoding="utf-8")) == signature:
                    self.log("natives already extracted")
                    return
            except Exception:
                pass

        shutil.rmtree(natives_dir, ignore_errors=True)
        natives_dir.mkdir(parents=True, exist_ok=True)
        self.log(f"extracting {len(natives)} native archive(s)")
        for jar, extract in natives:
            exclude = extract.get("exclude", [])
            with zipfile.ZipFile(jar) as zf:
                for member in zf.namelist():
                    if member.endswith("/") or member.startswith("META-INF/"):
                        continue
                    if any(member.startswith(ex) for ex in exclude):
                        continue
                    with zf.open(member) as src, open(natives_dir / Path(member).name, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        marker.write_text(json.dumps(signature), encoding="utf-8")

    def _assets(self, version: dict) -> tuple[Path, str]:
        info = version.get("assetIndex")
        if not info:
            return self.assets_dir, version.get("assets", "legacy")

        index_path = self.assets_dir / "indexes" / f"{info['id']}.json"
        self.download_all(
            [DownloadItem(info["url"], index_path, info.get("sha1"), info.get("size"))],
            "asset index",
        )
        index = json.loads(index_path.read_text(encoding="utf-8"))
        objects = index.get("objects", {})

        items = []
        for obj in objects.values():
            h = obj["hash"]
            dest = self.assets_dir / "objects" / h[:2] / h
            items.append(DownloadItem(f"{RESOURCES_URL}/{h[:2]}/{h}", dest, h, obj.get("size")))
        self.download_all(items, "assets")

        # Pre-1.7 versions read loose files instead of the hashed object store.
        if index.get("virtual") or index.get("map_to_resources"):
            root = (
                self.game_dir / "resources"
                if index.get("map_to_resources")
                else self.assets_dir / "virtual" / "legacy"
            )
            self.log("copying legacy assets")
            for name, obj in objects.items():
                h = obj["hash"]
                src = self.assets_dir / "objects" / h[:2] / h
                dst = root / name
                if src.is_file() and (
                    not dst.is_file() or dst.stat().st_size != src.stat().st_size
                ):
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dst)
            if index.get("virtual"):
                return root, info["id"]
        return self.assets_dir, info["id"]

    def _logging_config(self, version: dict) -> str | None:
        client = (version.get("logging") or {}).get("client")
        if not client:
            return None
        info = client["file"]
        dest = self.assets_dir / "log_configs" / info["id"]
        self.download_all(
            [DownloadItem(info["url"], dest, info.get("sha1"), info.get("size"))], "log config"
        )
        argument = client.get("argument", "-Dlog4j.configurationFile=${path}")
        return argument.replace("${path}", str(dest))

    # -- java -------------------------------------------------------------- #
    def ensure_java(self, version: dict, explicit: str = "") -> Path:
        if explicit:
            p = Path(explicit)
            if not p.is_file():
                raise RuntimeError(f"configured Java path does not exist: {p}")
            return p

        info = version.get("javaVersion") or {}
        component = info.get("component", "jre-legacy")
        want_major = int(info.get("majorVersion", 8))

        installed = runtime_java_path(component)
        if installed:
            return installed

        system = find_system_java(want_major)
        if system:
            self.log(f"using system Java {want_major}+: {system}")
            return system

        return self.download_java_runtime(component)

    def download_java_runtime(self, component: str) -> Path:
        self.log(f"downloading Java runtime '{component}' from Mojang (one time)")
        available = http_json(JAVA_RUNTIME_ALL_URL)
        plat = java_platform_key()
        entries = (available.get(plat) or {}).get(component) or []
        if not entries:
            raise RuntimeError(
                f"Mojang has no '{component}' runtime for {plat}; set a Java path manually"
            )
        manifest = http_json(entries[0]["manifest"]["url"])
        root = runtime_dir(component)

        items: list[DownloadItem] = []
        links: list[tuple[Path, str]] = []
        executables: list[Path] = []
        for rel, spec in manifest.get("files", {}).items():
            target = root / rel
            kind = spec.get("type")
            if kind == "directory":
                target.mkdir(parents=True, exist_ok=True)
            elif kind == "file":
                raw = spec["downloads"]["raw"]
                items.append(DownloadItem(raw["url"], target, raw.get("sha1"), raw.get("size")))
                if spec.get("executable"):
                    executables.append(target)
            elif kind == "link":
                links.append((target, spec.get("target", "")))
        self.download_all(items, f"java runtime ({component})")

        for target, dest in links:
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    os.symlink(dest, target)
            except OSError:
                pass  # Windows without developer mode; harmless for these runtimes
        for exe in executables:
            try:
                exe.chmod(exe.stat().st_mode | 0o111)
            except OSError:
                pass

        java = runtime_java_path(component)
        if not java:
            raise RuntimeError(f"java runtime install looks incomplete under {root}")
        return java

    # -- the whole job ----------------------------------------------------- #
    def prepare(
        self,
        version_id: str,
        username: str,
        ram_mb: int = 4096,
        extra_jvm: str = "",
        java_path: str = "",
    ) -> LaunchPlan:
        self.game_dir.mkdir(parents=True, exist_ok=True)
        version = self.load_version(version_id)
        self.log(f"preparing {version['id']} ({version.get('type', '?')})")

        client_jar = self._client_jar(version)
        classpath, natives = self._libraries(version)
        natives_dir = self.versions_dir / version["id"] / "natives"
        self._extract_natives(natives, natives_dir)
        assets_root, assets_index = self._assets(version)
        log_arg = self._logging_config(version)
        java = self.ensure_java(version, java_path)

        classpath = classpath + [client_jar]
        subst = {
            "auth_player_name": username,
            "version_name": version["id"],
            "game_directory": str(self.game_dir),
            "assets_root": str(assets_root),
            "game_assets": str(assets_root),
            "assets_index_name": assets_index,
            "auth_uuid": offline_uuid(username).hex,
            "auth_access_token": "0",
            "auth_session": "0",
            "clientid": "0",
            "auth_xuid": "0",
            "user_type": "msa" if "arguments" in version else "legacy",
            "user_properties": "{}",
            "version_type": version.get("type", "release"),
            "natives_directory": str(natives_dir),
            "launcher_name": LAUNCHER_NAME,
            "launcher_version": LAUNCHER_VERSION,
            "classpath": os.pathsep.join(str(p) for p in classpath),
            "classpath_separator": os.pathsep,
            "library_directory": str(self.libraries_dir),
        }

        jvm_args, game_args = resolve_arguments(version, subst)
        ram_mb = max(512, int(ram_mb))
        prefix = [f"-Xmx{ram_mb}M", f"-Xms{min(512, ram_mb)}M"]
        if log_arg:
            prefix.append(log_arg)
        if os_name() == "osx" and "-XstartOnFirstThread" not in jvm_args:
            prefix.append("-XstartOnFirstThread")
        prefix += [a for a in extra_jvm.split() if a]

        return LaunchPlan(
            version_id=version["id"],
            java=java,
            classpath=classpath,
            natives_dir=natives_dir,
            main_class=version["mainClass"],
            jvm_args=prefix + jvm_args,
            game_args=game_args,
            game_dir=self.game_dir,
        )


def merge_versions(parent: dict, child: dict) -> dict:
    skip = ("libraries", "arguments", "minecraftArguments")
    merged = dict(parent)
    merged.update({k: v for k, v in child.items() if k not in skip})
    merged["libraries"] = child.get("libraries", []) + parent.get("libraries", [])
    if "arguments" in parent or "arguments" in child:
        merged["arguments"] = {
            key: parent.get("arguments", {}).get(key, []) + child.get("arguments", {}).get(key, [])
            for key in ("game", "jvm")
        }
    if "minecraftArguments" in child:
        merged["minecraftArguments"] = child["minecraftArguments"]
    return merged


def _flatten_arg(arg, features: dict) -> list[str]:
    if isinstance(arg, str):
        return [arg]
    if not rules_allow(arg.get("rules"), features):
        return []
    value = arg.get("value", [])
    return [value] if isinstance(value, str) else list(value)


def substitute(text: str, subst: dict) -> str:
    return re.sub(r"\$\{(\w+)\}", lambda m: str(subst.get(m.group(1), m.group(0))), text)


def resolve_arguments(version: dict, subst: dict) -> tuple[list[str], list[str]]:
    features = {
        "is_demo_user": False,
        "has_custom_resolution": False,
        "has_quick_plays_support": False,
        "is_quick_play_singleplayer": False,
        "is_quick_play_multiplayer": False,
        "is_quick_play_realms": False,
    }
    if "arguments" in version:
        jvm: list[str] = []
        game: list[str] = []
        for arg in version["arguments"].get("jvm", []):
            jvm += _flatten_arg(arg, features)
        for arg in version["arguments"].get("game", []):
            game += _flatten_arg(arg, features)
    else:
        jvm = ["-Djava.library.path=${natives_directory}", "-cp", "${classpath}"]
        game = (version.get("minecraftArguments") or "").split()
    return [substitute(a, subst) for a in jvm], [substitute(a, subst) for a in game]


# --------------------------------------------------------------------------- #
# java discovery
# --------------------------------------------------------------------------- #
def runtime_dir(component: str) -> Path:
    return launcher_data_dir() / "runtime" / component / java_platform_key()


def runtime_java_path(component: str) -> Path | None:
    root = runtime_dir(component)
    exe = "javaw.exe" if os_name() == "windows" else "java"
    candidates = [
        root / "bin" / exe,
        root / component / "bin" / exe,
        root / component / "jre.bundle" / "Contents" / "Home" / "bin" / exe,
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def java_major(java: Path) -> int | None:
    exe = java
    if java.name.lower() == "javaw.exe":
        console = java.with_name("java.exe")
        if console.is_file():
            exe = console
    try:
        out = subprocess.run(
            [str(exe), "-version"],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return None
    text = (out.stderr or "") + (out.stdout or "")
    m = re.search(r'version "(\d+)(?:\.(\d+))?', text)
    if not m:
        return None
    major = int(m.group(1))
    return int(m.group(2) or 0) if major == 1 else major


def _java_candidates() -> list[Path]:
    exe = "javaw.exe" if os_name() == "windows" else "java"
    found: list[Path] = []
    home = os.environ.get("JAVA_HOME")
    if home:
        found.append(Path(home) / "bin" / exe)
    on_path = shutil.which("java")
    if on_path:
        found.append(Path(on_path))
    if os_name() == "windows":
        roots = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        ]
        vendors = ("Java", "Eclipse Adoptium", "Microsoft", "Zulu", "Amazon Corretto", "BellSoft")
        for root in roots:
            for vendor in vendors:
                base = root / vendor
                if base.is_dir():
                    found.extend(jdk / "bin" / exe for jdk in base.iterdir() if jdk.is_dir())
            official = root / "Minecraft Launcher" / "runtime"
            if official.is_dir():
                found.extend(official.glob(f"*/*/*/bin/{exe}"))
    return [p for p in found if p.is_file()]


def find_system_java(want_major: int) -> Path | None:
    for candidate in _java_candidates():
        major = java_major(candidate)
        if major is None:
            continue
        # Old versions break on newer JVMs, so only accept "newer is fine" for 17+.
        if major == want_major or (want_major >= 17 and major >= want_major):
            return candidate
    return None


# --------------------------------------------------------------------------- #
# launching
# --------------------------------------------------------------------------- #
def build_command(plan: LaunchPlan, server: str = "", fullscreen: bool = False) -> list[str]:
    cmd = [str(plan.java), *plan.jvm_args, plan.main_class, *plan.game_args]
    if server:
        host, _, port = server.partition(":")
        cmd += ["--server", host, "--port", port or "25565"]
    if fullscreen and "--fullscreen" not in cmd:
        cmd.append("--fullscreen")
    return cmd


def launch(
    plan: LaunchPlan,
    log: LogFn | None = None,
    server: str = "",
    fullscreen: bool = False,
    capture_output: bool = True,
) -> subprocess.Popen:
    """Start the game.

    With capture_output=False the game's output goes to nothing instead of a
    pipe, so it keeps running happily after the launcher exits. (A pipe nobody
    reads fills up and freezes the game once it has logged ~64 KB.) The game
    still writes its own logs/latest.log either way.
    """
    log = log or (lambda m: None)
    cmd = build_command(plan, server, fullscreen)
    log(f"launching {plan.version_id} with {plan.java.name}")
    plan.game_dir.mkdir(parents=True, exist_ok=True)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if not capture_output:
        # own process group: the game outlives the launcher cleanly
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen(
        cmd,
        cwd=str(plan.game_dir),
        stdout=subprocess.PIPE if capture_output else subprocess.DEVNULL,
        stderr=subprocess.STDOUT if capture_output else subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=flags,
    )


# --------------------------------------------------------------------------- #
# settings
# --------------------------------------------------------------------------- #
@dataclass
class Settings:
    username: str = ""
    usernames: list[str] = field(default_factory=list)
    version: str = ""
    game_dir: str = field(default_factory=lambda: str(default_game_dir()))
    java_path: str = ""
    ram_mb: int = 4096
    jvm_args: str = ""
    show_snapshots: bool = False
    server: str = ""
    fullscreen: bool = False
    close_on_launch: bool = False

    def remember_username(self, name: str) -> None:
        """Keep the most recently launched name first in the profile list."""
        name = (name or "").strip()
        if not name:
            return
        self.usernames = [name] + [u for u in self.usernames if u.lower() != name.lower()]
        del self.usernames[12:]
        self.username = name

    def forget_username(self, name: str) -> None:
        self.usernames = [u for u in self.usernames if u != name]
        if self.username == name:
            self.username = self.usernames[0] if self.usernames else ""

    @classmethod
    def path(cls) -> Path:
        return launcher_data_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
            known = set(cls.__dataclass_fields__)
            return cls(**{k: v for k, v in data.items() if k in known})
        except Exception:
            return cls()

    def save(self) -> None:
        """Write atomically: another launcher may be saving at the same moment."""
        target = self.path()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
        try:
            tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
            tmp.replace(target)
        finally:
            tmp.unlink(missing_ok=True)
