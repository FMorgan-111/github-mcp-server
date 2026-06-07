# Versioning & Rollback

## Semantic Versioning

This project follows [SemVer](https://semver.org/): `MAJOR.MINOR.PATCH`

| Bump | When |
|------|------|
| MAJOR (`1.0.0`) | Breaking API changes (tool removed, parameter renamed) |
| MINOR (`0.2.0`) | New tool added, new feature, non-breaking |
| PATCH (`0.1.1`) | Bug fix, security patch, docs update |

## Release Checklist

```bash
# 1. Update version in pyproject.toml
# 2. Update CHANGELOG.md
# 3. Commit
git add pyproject.toml CHANGELOG.md
git commit -m "release: v0.2.0"

# 4. Tag
git tag -a v0.2.0 -m "v0.2.0 — <summary>"
git push origin main --tags

# 5. Build & publish
rm -rf dist/
python3 -m build
python3 -m twine upload dist/*

# 6. GitHub Release
gh release create v0.2.0 --title "v0.2.0 — <summary>" --notes-file <(sed -n '/## \[0.2.0/,/## \[/p' CHANGELOG.md)
```

## Rollback

### PyPI: yank a bad release

Yanking hides the release from new installs but doesn't break existing ones:

```bash
# Yank (hide from pip install)
python3 -m twine upload --skip-existing --verbose dist/mcp_github_agent-0.1.0* 2>/dev/null
# Then yank via PyPI web UI: https://pypi.org/manage/project/mcp-github-agent/releases/

# Or via API (requires token with delete permission):
curl -X POST https://pypi.org/project/mcp-github-agent/0.1.0/ \
  -H "Authorization: token pypi-..." \
  -F action=yank
```

### Git: revert a bad commit

```bash
# Revert the release commit
git revert <commit-hash> -m "revert: v0.2.0 — <reason>"
git push origin main
```

### Full unpublish (emergency)

```bash
# PyPI: delete release via web UI (irreversible)
# Git: delete the tag
git tag -d v0.2.0
git push origin :refs/tags/v0.2.0
```

## Current Version

**v0.1.0** — Initial release (2026-06-07)
