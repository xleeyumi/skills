# Skillfish skill registry

A GitHub repository for sharing multiple Agent Skills. Each skill is an independent directory with a `SKILL.md` file, so `skillfish` can discover and install it directly:

```bash
npx skillfish add xleeyumi/skills
```

## Layout

```text
skills/<name>/SKILL.md              # locally authored skills
vendor/<source>/<name>/SKILL.md     # generated skills mirrored from upstream
.github/sources.yml                 # upstream repositories and refs
.github/scripts/sync_skills.py      # upstream sync
.github/scripts/validate_skills.py  # frontmatter and layout checks
.github/workflows/sync-upstream-skills.yml
.github/workflows/validate-skills.yml
```

The local `skills/repository-maintenance` skill is a starter skill for maintaining this registry. Add further local skills under `skills/<name>/`, keeping one directory per skill. Every `SKILL.md` must begin with YAML frontmatter containing non-empty `name` and `description` fields.

## Configure upstream sync

Edit `.github/sources.yml` to add or change upstream repositories and optional path whitelists:

```yaml
sources:
  - name: upstream-example
    repository: https://github.com/OWNER/UPSTREAM_SKILLS_REPO.git
    ref: main
    paths: [skills/example]  # optional whitelist; omit to sync every skill
```

The checked-in workflow runs daily and can also be started manually. It clones each configured ref, finds every `SKILL.md` (or only the directories/files listed in optional `paths`), and copies each selected skill directory to `vendor/<source>/<name>/`. Local content under `skills/` is never modified. The workflow validates the result, then commits and pushes only generated `vendor/` changes. The checked-in configuration selectively mirrors OpenAI’s `skill-creator` and `playwright` skills.

You can run the same checks locally:

```bash
python3 .github/scripts/sync_skills.py
python3 .github/scripts/validate_skills.py
```

The sync script uses Python and PyYAML 6.0.2 for strict YAML parsing and intentionally does not execute anything from an upstream repository. Install it (`python3 -m pip install PyYAML==6.0.2`) before running locally. Review vendored skill instructions before using them.

## skillfish discovery notes

`skillfish` 1.0.x recursively inspects a GitHub repository's default branch for files named exactly `SKILL.md`, then reads their frontmatter. The `skills/<name>/SKILL.md` layout therefore works with automatic discovery, while the generated `vendor/<source>/<name>/SKILL.md` layout keeps upstream skills isolated from local names.

