#!/usr/bin/env python3
"""Mirror SKILL.md directories from configured upstream Git repositories.

The script uses PyYAML for strict config parsing and otherwise standard-library
operations, so it runs reproducibly on GitHub-hosted runners. Upstream files are copied into
vendor/<source-name>/<skill-name>/; local skills under skills/ are never touched.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any
from pathlib import Path

SOURCE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def parse_sources(path: Path) -> list[dict[str, Any]]:
    """Parse sources.yml using a real YAML parser (never execute YAML)."""
    try:
        import yaml
    except ImportError as exc:
        raise ValueError("PyYAML is required to parse .github/sources.yml") from exc
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc
    if data is None:
        return []
    if not isinstance(data, dict) or set(data) - {"sources"}:
        raise ValueError("sources.yml must contain only a 'sources' mapping")
    entries = data.get("sources", [])
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise ValueError("'sources' must be a list")
    result: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("each source must be a mapping")
        if set(entry) - {"name", "repository", "ref", "paths"}:
            raise ValueError("source fields may only be name, repository, ref, and paths")
        normalized = {str(k): v for k, v in entry.items() if v is not None}
        paths = normalized.get("paths")
        if paths is not None:
            if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
                raise ValueError("source paths must be a non-empty list of strings")
            for path_value in paths:
                path_obj = Path(path_value)
                if path_obj.is_absolute() or ".." in path_obj.parts or path_obj == Path("."):
                    raise ValueError(f"unsafe source path: {path_value!r}")
            normalized["paths"] = paths
        result.append(normalized)
    return result


def run(command: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def source_name(source: dict[str, Any]) -> str:
    name = source.get("name", "").strip()
    if not name or not SOURCE_NAME_RE.fullmatch(name):
        raise ValueError(
            f"Invalid source name {name!r}; use letters, numbers, '.', '_' or '-'."
        )
    return name


def skill_name(source: dict[str, Any], skill_md: Path, checkout: Path) -> str:
    relative = skill_md.relative_to(checkout)
    if relative.parent == Path("."):
        candidate = source_name(source)
    else:
        candidate = relative.parent.name
    if not SOURCE_NAME_RE.fullmatch(candidate):
        raise ValueError(
            f"Cannot derive a safe skill directory from {relative}; "
            "rename the upstream skill directory to use letters, numbers, '.', '_' or '-'."
        )
    return candidate


def sync_source(source: dict[str, Any], vendor_root: Path, temp_root: Path, blocked_names: set[str] | None = None) -> int:
    name = source_name(source)
    repository = source.get("repository", "").strip()
    if not repository or repository.startswith("https://github.com/OWNER/"):
        raise ValueError(
            f"Source {name!r} still uses the placeholder repository URL; configure a real URL in .github/sources.yml."
        )
    ref = source.get("ref", "").strip()
    checkout = temp_root / name
    clone = ["git", "clone", "--depth", "1"]
    if ref:
        clone += ["--branch", ref]
    clone += ["--", repository, str(checkout)]
    run(clone)

    selected_paths = source.get("paths")
    skill_files = sorted(p for p in checkout.rglob("SKILL.md") if ".git" not in p.parts)
    if selected_paths:
        allowed = [checkout / path for path in selected_paths]
        skill_files = [p for p in skill_files if any(p == base / "SKILL.md" or base in p.parents for base in allowed)]
    if not skill_files:
        raise ValueError(f"No SKILL.md files found in upstream source {name!r}.")

    destination = vendor_root / name
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    seen: set[str] = set()
    copied = 0
    for skill_md in skill_files:
        dest_name = skill_name(source, skill_md, checkout)
        if blocked_names is not None and dest_name in blocked_names:
            raise ValueError(f"Skill directory name {dest_name!r} collides with another source or local skill.")
        if dest_name in seen:
            raise ValueError(
                f"Source {name!r} contains multiple skills mapping to vendor/{name}/{dest_name}."
            )
        seen.add(dest_name)
        dest_dir = destination / dest_name
        source_dir = skill_md.parent
        if source_dir == checkout:
            dest_dir.mkdir(parents=True)
            for child in checkout.iterdir():
                if child.name == ".git":
                    continue
                target = dest_dir / child.name
                if child.is_dir():
                    shutil.copytree(child, target)
                else:
                    shutil.copy2(child, target)
        else:
            shutil.copytree(source_dir, dest_dir)
        copied += 1
    print(f"Synced {copied} skill(s) from {name} into {destination}")
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    config = (args.config or root / ".github/sources.yml").resolve()
    vendor_root = root / "vendor"
    vendor_root.mkdir(parents=True, exist_ok=True)
    try:
        sources = parse_sources(config)
    except (OSError, ValueError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    if not sources:
        print("No upstream sources configured; vendor/ left unchanged.")
        return 0
    try:
        names = [source_name(source) for source in sources]
        if len(names) != len(set(names)):
            raise ValueError("Each configured upstream source must have a unique name.")
        with tempfile.TemporaryDirectory(prefix="skillfish-sync-") as temp_dir:
            staged = Path(temp_dir) / "vendor"
            if vendor_root.exists():
                shutil.copytree(vendor_root, staged)
            else:
                staged.mkdir()
            blocked = {p.name for p in (root / "skills").iterdir() if p.is_dir()} if (root / "skills").exists() else set()
            blocked |= {p.name for p in staged.iterdir() if p.is_dir()}
            total = 0
            for source in sources:
                source_name_value = source_name(source)
                old = staged / source_name_value
                if old.exists():
                    blocked -= {p.name for p in old.iterdir() if p.is_dir()}
                total += sync_source(source, staged, Path(temp_dir), blocked)
                blocked |= {p.name for p in (staged / source_name_value).iterdir() if p.is_dir()}
            backup = Path(temp_dir) / "vendor-old"
            vendor_root.rename(backup)
            try:
                staged.rename(vendor_root)
            except Exception:
                # Restore the original tree if the replacement fails.
                if not vendor_root.exists() and backup.exists():
                    backup.rename(vendor_root)
                raise
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"Sync failed: {exc}", file=sys.stderr)
        return 1
    print(f"Synced {total} skill(s) total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
