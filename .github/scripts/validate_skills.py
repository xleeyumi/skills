#!/usr/bin/env python3
"""Validate skillfish-compatible SKILL.md files in skills/ and vendor/."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

KEY_RE = re.compile(r"^(name|description):\s*(.*?)\s*$")


def parse_frontmatter(path: Path) -> tuple[str | None, str | None, str | None]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return None, None, f"cannot read file: {exc}"
    if not lines or lines[0].strip() != "---":
        return None, None, "missing opening YAML frontmatter delimiter ('---')"
    end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        return None, None, "missing closing YAML frontmatter delimiter ('---')"
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        match = KEY_RE.match(line)
        if match:
            value = match.group(2).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1].strip()
            fields[match.group(1)] = value
    missing = [key for key in ("name", "description") if not fields.get(key)]
    if missing:
        return fields.get("name"), fields.get("description"), (
            "missing required frontmatter field(s): " + ", ".join(missing)
        )
    return fields["name"], fields["description"], None


def expected_layout(path: Path, root: Path) -> str | None:
    relative = path.relative_to(root)
    if relative.parts[0] == "skills":
        if len(relative.parts) != 3 or relative.parts[-1] != "SKILL.md":
            return "local skills must use skills/<name>/SKILL.md"
    elif relative.parts[0] == "vendor":
        if len(relative.parts) != 4 or relative.parts[-1] != "SKILL.md":
            return "vendor skills must use vendor/<source>/<name>/SKILL.md"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    root = args.root.resolve()
    files = sorted(
        p
        for base in (root / "skills", root / "vendor")
        if base.exists()
        for p in base.rglob("SKILL.md")
        if p.is_file()
    )
    if not files:
        print("No SKILL.md files found under skills/ or vendor/.", file=sys.stderr)
        return 1
    failures: list[str] = []
    names: dict[str, Path] = {}
    directory_names: dict[str, Path] = {}
    for path in files:
        layout_error = expected_layout(path, root)
        if layout_error:
            failures.append(f"{path.relative_to(root)}: {layout_error}")
        name, _description, error = parse_frontmatter(path)
        if error:
            failures.append(f"{path.relative_to(root)}: {error}")
        elif name:
            normalized = re.sub(r"[\s_]+", "-", name.strip().lower())
            previous = names.get(normalized)
            if previous:
                failures.append(
                    f"{path.relative_to(root)}: duplicate normalized skill name {name!r}; "
                    f"already declared by {previous.relative_to(root)}"
                )
            else:
                names[normalized] = path
        skill_dir = path.parent.name
        previous_dir = directory_names.get(skill_dir)
        if previous_dir and previous_dir != path.parent:
            failures.append(f"{path.relative_to(root)}: duplicate skill directory name {skill_dir!r}; already used by {previous_dir.relative_to(root)}")
        else:
            directory_names[skill_dir] = path.parent
    if failures:
        print("Skill validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"Validated {len(files)} SKILL.md file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
