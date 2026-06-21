#!/usr/bin/env bash
# =============================================================================
# w0_w58_merge_gate.sh  --  W0 OVERWATCH merge-back audit for the W58 lane.
#
# Deterministic, halt-on-first-failure gate for the concurrent W68 execution
# session's feat/w68-tooling-reconciliation branch BEFORE the guarded push to
# master. Read-only: audits the PUSHED remote ref, spins an EPHEMERAL detached
# worktree for env-dependent checks, and tears it down. Never pushes, never
# mutates the W0 checkout or the W68 session's worktree.
#
# Sections (per the W0 gate spec):
#   1. Isolation integrity        2. Cherry-pick scope (a2126a5 only)
#   3. Source-of-Truth ledger     4. Harvest reproducibility (clean regen)
#   5. Test gate (pytest -n auto)
#   ---> MERGE-READINESS verdict (read-only FF check; prints push cmd). NO PUSH.
#
# Usage:
#   tools/w0_w58_merge_gate.sh [BRANCH] [--local] [--skip-harvest] [--skip-tests]
#     BRANCH         default: feat/w68-tooling-reconciliation
#     --local        audit the LOCAL branch ref instead of origin/<BRANCH>
#     --skip-harvest skip section 4 (run it manually at the seat)
#     --skip-tests   skip section 5
#
# Exit: 0 = all green (cleared for the manual guarded push); 1 = a check failed.
# =============================================================================
set -u

# ---- config -----------------------------------------------------------------
BRANCH="feat/w68-tooling-reconciliation"
USE_LOCAL=0
SKIP_HARVEST=0
SKIP_TESTS=0
EXPECTED_BASE="c516e26"          # known-good origin/master at gate authoring
OVERWATCH_BRANCH="feat/w67-phase3"
PYTHON="C:/Python314/python.exe"
SW_REDIST="C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS/api/redist"
DEAD_SHAS="283d0d5 cc8664b aa78b2e 22ea48c"  # orphaned by the IP-scrub rewrite

for arg in "$@"; do
  case "$arg" in
    --local)        USE_LOCAL=1 ;;
    --skip-harvest) SKIP_HARVEST=1 ;;
    --skip-tests)   SKIP_TESTS=1 ;;
    --*)            echo "unknown flag: $arg" >&2; exit 2 ;;
    *)              BRANCH="$arg" ;;
  esac
done

# ---- reporting helpers ------------------------------------------------------
C_OK=$'\033[32m'; C_NO=$'\033[31m'; C_HD=$'\033[36m'; C_Z=$'\033[0m'
TMP_WT=""
cleanup() { [ -n "$TMP_WT" ] && git worktree remove --force "$TMP_WT" >/dev/null 2>&1; }
trap cleanup EXIT

section() { printf '\n%s== %s ==%s\n' "$C_HD" "$1" "$C_Z"; }
ok()      { printf '  %sPASS%s  %s\n' "$C_OK" "$C_Z" "$1"; }
info()    { printf '        %s\n' "$1"; }
die()     { printf '  %sFAIL%s  %s\n' "$C_NO" "$C_Z" "$1" >&2; \
            printf '\n%sGATE HALTED -- merge BLOCKED. Bounce back to the W68 session.%s\n' "$C_NO" "$C_Z" >&2; \
            exit 1; }

cd "$(git rev-parse --show-toplevel)" || die "not in a git repo"

# Resolve the ref we audit (what's PUSHED, unless --local).
git fetch origin --tags --quiet 2>/dev/null \
  || printf '        WARN: git fetch failed (offline/no-creds) -- using cached origin/master %s\n' "$(git rev-parse --short origin/master)"
if [ "$USE_LOCAL" -eq 1 ]; then AUDIT_REF="$BRANCH"; else AUDIT_REF="origin/$BRANCH"; fi
git rev-parse --verify --quiet "$AUDIT_REF^{commit}" >/dev/null \
  || die "audit ref '$AUDIT_REF' does not exist (has the W68 session pushed?)"
AUDIT_SHA="$(git rev-parse --short "$AUDIT_REF")"
MASTER_SHA="$(git rev-parse origin/master)"
printf '%sW0 W58 MERGE GATE%s  ref=%s (%s)  vs origin/master=%s\n' \
  "$C_HD" "$C_Z" "$AUDIT_REF" "$AUDIT_SHA" "$(git rev-parse --short origin/master)"

# =============================================================================
section "1. ISOLATION INTEGRITY"
# 1a. My overwatch checkout has no TRACKED modifications. Untracked W0 tooling
# and artifacts (harvests, _results, the gate scripts) are EXPECTED and harmless
# -- the audit runs against the pushed ref in an ephemeral worktree, so the
# checkout's untracked files never leak into it. Only staged/tracked edits matter.
[ -z "$(git status --porcelain --untracked-files=no)" ] \
  || die "W0 checkout has uncommitted TRACKED changes -- stash/commit before auditing"
ok "W0 checkout ($OVERWATCH_BRANCH) has no tracked modifications (untracked tooling ok)"
# 1b. origin/master is where we expect (warn-only -- it may have legitimately advanced).
if [ "$(git rev-parse --short origin/master)" = "$EXPECTED_BASE" ]; then
  ok "origin/master at expected baseline $EXPECTED_BASE"
else
  info "NOTE: origin/master ($(git rev-parse --short origin/master)) != authoring baseline $EXPECTED_BASE (advanced?) -- verify intentional"
fi
# 1c. Their branch is rooted in the CURRENT master, not orphaned/dead history.
MB="$(git merge-base origin/master "$AUDIT_REF")"
[ "$MB" = "$MASTER_SHA" ] \
  || die "merge-base($AUDIT_REF, origin/master)=$(git rev-parse --short "$MB") != origin/master -- branch is NOT off current master (diverged or off dead history)"
ok "branch rooted at current origin/master ($(git rev-parse --short "$MASTER_SHA"))"
# 1d. No dead (scrubbed) SHA is reachable from the branch.
for s in $DEAD_SHAS; do
  if git rev-parse --verify --quiet "$s^{commit}" >/dev/null 2>&1; then
    git merge-base --is-ancestor "$s" "$AUDIT_REF" 2>/dev/null \
      && die "DEAD scrubbed SHA $s is reachable from $AUDIT_REF -- resurrected history"
  fi
done
ok "no scrubbed/dead SHA reachable from the branch"

# =============================================================================
section "2. CHERRY-PICK SCOPE (a2126a5 only)"
git rev-parse --verify --quiet "a2126a5^{commit}" >/dev/null \
  || die "a2126a5 not resolvable -- cannot validate the cherry-pick source"
# 2a. Branch == master + exactly the delta we expect (no surprise commits).
NCOMMITS="$(git rev-list --count origin/master.."$AUDIT_REF")"
info "$NCOMMITS commit(s) ahead of origin/master:"
git log --oneline --no-decorate origin/master.."$AUDIT_REF" | sed 's/^/          /'
# 2b. No merge commits (must be a linear FF-able branch).
[ "$(git rev-list --merges --count origin/master.."$AUDIT_REF")" -eq 0 ] \
  || die "branch contains MERGE commits -- expected linear cherry-pick; rebase in their worktree"
ok "linear history, no merge commits"
# 2c. a2126a5 ADDED files must be byte-identical (pure cherry-pick additions, e.g.
# the .ps1 scripts -- no legitimate reason to differ). MODIFIED files are
# conflict-resolution-prone (.gitignore "kept both blocks", _api_extract_input.json
# "accepted grown version") so they differ from a2126a5 BY DESIGN -> verify present
# + flag for MANUAL review, do NOT demand byte-identity (the brittle check that
# false-failed the real W58 merge). DELETED files (api_reference.*) must stay absent.
a2_add=0; a2_rev=0
while IFS=$'\t' read -r status path; do
  [ -z "${path:-}" ] && continue
  case "$status" in
    A*)
      git cat-file -e "$AUDIT_REF:$path" 2>/dev/null || die "a2126a5-ADDED file missing on branch: $path"
      if diff -q <(git show "a2126a5:$path" 2>/dev/null) <(git show "$AUDIT_REF:$path" 2>/dev/null) >/dev/null; then
        info "ADDED byte-matches a2126a5: $path"; a2_add=$((a2_add+1))
      else
        die "a2126a5-ADDED file diverges (pure additions MUST match a2126a5): $path"
      fi ;;
    M*)
      git cat-file -e "$AUDIT_REF:$path" 2>/dev/null || die "a2126a5-MODIFIED file missing on branch: $path"
      info "MODIFIED present -- conflict-resolution-prone, MANUAL REVIEW: $path"; a2_rev=$((a2_rev+1)) ;;
    D*)
      git cat-file -e "$AUDIT_REF:$path" 2>/dev/null \
        && die "a2126a5-DELETED file reappeared on branch: $path" \
        || info "DELETED stays absent: $path" ;;
  esac
done < <(git diff-tree --no-commit-id -r --name-status a2126a5)
ok "a2126a5 additions byte-match ($a2_add); $a2_rev modified file(s) flagged for manual review; deletions absent"
# 2d. 808a192 must NOT have come along: DEFERRED.md must equal master's form.
if diff -q <(git show "origin/master:docs/DEFERRED.md" 2>/dev/null) \
           <(git show "$AUDIT_REF:docs/DEFERRED.md" 2>/dev/null) >/dev/null; then
  ok "docs/DEFERRED.md identical to master (808a192 superseded line NOT reintroduced)"
else
  die "docs/DEFERRED.md differs from master -- 808a192 hem line may have been dragged in; inspect: git diff origin/master:$AUDIT_REF -- docs/DEFERRED.md"
fi

# =============================================================================
section "3. SOURCE-OF-TRUTH LEDGER (one ledger only)"
tracked_count() { git ls-tree -r "$AUDIT_REF" --name-only | grep -E "$1" -c || true; }
N_APIREF="$(tracked_count '^docs/api_reference\.(json|md)$')"
N_FULL="$(tracked_count '^docs/sw_api_full\.(json|md)$')"
info "tracked: api_reference.* = $N_APIREF file(s) ; sw_api_full.* = $N_FULL file(s)"
if   [ "$N_APIREF" -gt 0 ] && [ "$N_FULL" -eq 0 ]; then WINNER="api_reference"; LOSER="sw_api_full"
elif [ "$N_FULL" -gt 0 ] && [ "$N_APIREF" -eq 0 ]; then WINNER="sw_api_full";  LOSER="api_reference"
elif [ "$N_APIREF" -eq 0 ] && [ "$N_FULL" -eq 0 ]; then WINNER="(none-tracked: gitignored-generated)"; LOSER="?"
else die "BOTH ledgers tracked (api_reference=$N_APIREF, sw_api_full=$N_FULL) -- double-ledger NOT resolved"
fi
ok "single tracked ledger family -> winner: $WINNER ; loser purged: $LOSER"
# If winner is gitignored-generated, it MUST be declared in .gitignore.
if [ "$WINNER" = "(none-tracked: gitignored-generated)" ]; then
  git show "$AUDIT_REF:.gitignore" 2>/dev/null | grep -Eq 'api_reference|sw_api_full' \
    || die "no ledger tracked AND none gitignored -- winner is untracked-and-unmanaged (forbidden)"
  ok ".gitignore declares the generated ledger (managed-as-generated)"
fi

# =============================================================================
# Ephemeral worktree for env-dependent checks (4 & 5). Audits the PUSHED ref.
need_worktree=0
{ [ "$SKIP_HARVEST" -eq 0 ] || [ "$SKIP_TESTS" -eq 0 ]; } && need_worktree=1
if [ "$need_worktree" -eq 1 ]; then
  TMP_WT="$(git rev-parse --show-toplevel)/../.w0_gate_wt_$AUDIT_SHA"
  git worktree add --detach --quiet "$TMP_WT" "$AUDIT_REF" \
    || die "could not create ephemeral worktree at $TMP_WT"
fi

section "4. HARVEST REPRODUCIBILITY (clean regen)"
if [ "$SKIP_HARVEST" -eq 1 ]; then
  info "SKIPPED (--skip-harvest) -- run the harvest manually at the seat and confirm clean status"
else
  HARVEST_REL="$(git ls-tree -r "$AUDIT_REF" --name-only | grep -E 'export_full_sw_api\.ps1$' | head -n1 || true)"
  [ -n "$HARVEST_REL" ] || die "export_full_sw_api.ps1 not found on branch -- cannot verify regen"
  [ -d "$SW_REDIST" ] || die "SW redist not found at '$SW_REDIST' -- run at the seat or --skip-harvest"
  info "running: $HARVEST_REL (against live redist) in ephemeral worktree"
  ( cd "$TMP_WT" && powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$HARVEST_REL" ) \
    || die "harvest script exited non-zero -- pipeline broken"
  # The invariant: a clean regen leaves NO tracked modification and NO unmanaged
  # new ledger artifact. (committed-canonical -> identical bytes -> clean;
  # gitignored-generated -> artifact ignored -> clean. drift/stale -> modified.)
  DIRTY="$(cd "$TMP_WT" && git status --porcelain)"
  if [ -n "$DIRTY" ]; then
    info "post-regen git status:"; printf '%s\n' "$DIRTY" | sed 's/^/          /'
    die "harvest regen produced a dirty tree -- committed ledger is STALE or emits an unmanaged/renamed artifact"
  fi
  ok "harvest regenerates CLEAN against live redist (no drift, no unmanaged output)"
fi

section "5. TEST GATE (pytest -n auto)"
if [ "$SKIP_TESTS" -eq 1 ]; then
  info "SKIPPED (--skip-tests)"
else
  [ -x "$PYTHON" ] || command -v "$PYTHON" >/dev/null 2>&1 || die "python not found at $PYTHON"
  info "running: PYTHONPATH=src pytest -n auto -q (in ephemeral worktree)"
  if ( cd "$TMP_WT" && PYTHONPATH=src "$PYTHON" -m pytest -n auto -q ); then
    ok "pytest -n auto GREEN"
  else
    die "pytest -n auto reported failures -- suite not green"
  fi
fi

# =============================================================================
section "MERGE-READINESS (read-only -- NO PUSH)"
if git merge-base --is-ancestor origin/master "$AUDIT_REF"; then
  ok "branch is a strict FAST-FORWARD descendant of origin/master"
  printf '\n%sALL CHECKS GREEN -- cleared for the W0 guarded push (run MANUALLY):%s\n' "$C_OK" "$C_Z"
  cat <<EOF

  gh repo view Thomas-Tai/ai-sw-bridge --json isPrivate --jq .isPrivate
  # confirm -> true, then in the SAME guard:
  git push origin $AUDIT_REF:master    # NO --force ; FF only

EOF
  exit 0
else
  die "branch is NOT a fast-forward of origin/master -- REJECT. The W68 session owns the detangle in their isolated worktree (FF-or-reject; W0 does not conflict-resolve)."
fi
