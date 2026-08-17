# Activate this repository's git hooks (commit-msg, pre-push).
# Usage: .\scripts\setup-git-hooks.ps1

$ErrorActionPreference = "Stop"

$RepoRoot = git rev-parse --show-toplevel 2>$null
if (-not $RepoRoot) {
    Write-Error "Not inside a git repository"
    exit 1
}

$HooksDir = Join-Path $RepoRoot ".githooks"
if (-not (Test-Path $HooksDir)) {
    Write-Error "$HooksDir not found"
    exit 1
}

git -C $RepoRoot config core.hooksPath .githooks

Write-Host "[OK] core.hooksPath set to .githooks"
Write-Host ""
Write-Host "Active hooks:"
Get-ChildItem -Path $HooksDir -File | ForEach-Object { Write-Host "  - $($_.Name)" }
Write-Host ""
Write-Host "These hooks enforce conventional commit messages and branch naming."
Write-Host "See CLAUDE.md and CONTRIBUTING.md for the full workflow rules."
