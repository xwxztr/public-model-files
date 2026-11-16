"""External preparation machine only: package already-installed reviewed files.

No network calls, dependency installs or lifecycle scripts are executed here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.0"
SOURCE_DIRS = ("src", "windows", "tests", "tools", "docs", "licenses", "evidence")
SOURCE_FILES = (".gitignore", "README.md", "SECURITY.md", "LICENSE", "THIRD_PARTY_NOTICES.md",
                "host-config.example.json", "vendor-package.json", "vendor-lock.json",
                "SOURCES.json", "DEPENDENCIES.json", "npm-audit.json", "Verify-Downloads.ps1")


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_tree(root):
    for path in (root, *root.rglob("*")):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"link/reparse point forbidden in payload: {path.name}")


def source_paths():
    paths = []
    for name in SOURCE_FILES:
        path = ROOT / name
        if not path.is_file(): raise ValueError(f"missing source file {name}")
        paths.append(path)
    for folder in SOURCE_DIRS:
        for path in (ROOT / folder).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and not path.name.endswith(".pyc"):
                paths.append(path)
    return sorted(paths)


def build():
    payload = ROOT / "payload"
    if not (payload / "runtime/python/python.exe").is_file(): raise ValueError("missing runtime")
    for directory in ("src", "windows"):
        dest = payload / directory
        dest.mkdir(exist_ok=True)
        names = ("guard.py", "configure.py") if directory == "src" else ("Bootstrap.ps1", "Run-Agent.ps1")
        for name in names: shutil.copy2(ROOT / directory / name, dest / name)
    vendor = ROOT / "vendor"
    # npm .bin junctions are unnecessary: launchers use explicit reviewed paths.
    target = payload / "vendor"
    if target.exists():
        if sha256(target / "package-lock.json") != sha256(vendor / "package-lock.json"):
            raise ValueError("stale staged vendor: replace it explicitly after reviewing the new lock")
    else:
        shutil.copytree(vendor, target, ignore=shutil.ignore_patterns(".bin"))
    check_tree(payload)
    files = [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha256(p), "bytes": p.stat().st_size}
             for p in sorted(payload.rglob("*")) if p.is_file()]
    manifest = ROOT / "payload-manifest.json"
    manifest.write_text(json.dumps({"format": 1, "version": VERSION, "files": files}, indent=2), encoding="utf-8")
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    sources = source_paths()
    variants = {f"Internal-Agent-Source-{VERSION}.zip": sources,
                f"Internal-Agent-Windows-x64-{VERSION}.zip": sources + [manifest] + [ROOT / f["path"] for f in files]}
    for name, paths in variants.items():
        print(f"Building {name}: {len(paths)} files", flush=True)
        with zipfile.ZipFile(output / name, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            for path in paths: archive.write(path, path.relative_to(ROOT).as_posix())
    for source, name in ((ROOT / "docs/INSTALL.zh-CN.md", "INSTALL.zh-CN.md"),
                         (ROOT / "docs/AUDIT.zh-CN.md", "AUDIT.zh-CN.md"),
                         (ROOT / "docs/ACCEPTANCE.zh-CN.md", "ACCEPTANCE.zh-CN.md"),
                         (ROOT / "docs/VALIDATION.zh-CN.md", "VALIDATION.zh-CN.md")):
        shutil.copy2(source, output / name)
    shutil.copy2(ROOT / "Verify-Downloads.ps1", output / "Verify-Downloads.ps1")
    sums = "".join(f"{sha256(p)}  {p.name}\n" for p in sorted(output.iterdir()) if p.is_file() and p.name != "SHA256SUMS.txt")
    (output / "SHA256SUMS.txt").write_text(sums, encoding="ascii")
    print(json.dumps({"payload_files": len(files), "payload_bytes": sum(f["bytes"] for f in files),
                      "archives": [{"name": n, "bytes": (output / n).stat().st_size} for n in variants]}), flush=True)


if __name__ == "__main__":
    build()
