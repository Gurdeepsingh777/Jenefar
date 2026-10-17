---
name: rea_changelog_update
version: "1.0"
description: Prepare release changelogs from verified Git history, pull requests, release baselines and known contributor metadata.
keywords:
  - changelog
  - release notes
  - version release
  - contributor attribution
  - git history
  - REA
connectors:
  - github
  - rea
permissions:
  - repository_read
  - evidence_based_analysis
enabled_by_default: true
---
# Release Changelog Update

Use when the user requests release notes/changelog preparation. This skill prepares content only; it does not authorize merging, tagging or publishing.

1. Pin the base branch SHA, release baseline/tag, target revision, proposed version and repository release conventions.
2. Inventory commits and associated pull requests in the exact range. Inspect ambiguous PRs/diffs before making claims.
3. Keep attribution evidence-based: preserve unresolved identities as unknown; do not invent handles, coauthors or issue-reporters.
4. Rewrite only the requested version section using project conventions (Highlights, Changes, Fixes and breaking changes where applicable).
5. Avoid repeating the same work in several sections. Include cross-repository links when issue numbers would be ambiguous.
6. Separate user-visible changes from internal tests/CI/docs, retain provenance, and validate against the project's own release checks.
7. Report the baseline, target, sources, command output and any attribution or history gaps.

Never merge, tag, publish or edit unrelated release sections without explicit authorization.
