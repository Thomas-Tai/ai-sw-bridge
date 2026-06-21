#!/usr/bin/env bash
# =============================================================================
# w0_feature_lane_gate.sh  --  W0 OVERWATCH reception gate for the W68 offline
# feature lanes (fillet_face_fullround / curve_driven_pattern / fill_pattern).
#
# Sibling of w0_w58_merge_gate.sh, shaped for DORMANT feature lanes rather than
# the W58 tooling reconciliation. Read-only: audits the PUSHED remote ref, runs
# offline tests in an EPHEMERAL detached worktree, tears it down. Never pushes,
# never mutates the W0 checkout or any lane worktree.
#
# A feature lane passes reception at OFFLINE-GREEN + DORMANT — NOT shipped.
# Shipping needs (a) its merge slot behind W58 -> Route-C, and (b) the serial
# live-seat proof that flips SPIKE_STATUS UNFIRED->GREEN. This gate certifies
# (a)-readiness and dormancy ONLY; the seat-proof is a separate W0 step.
#
# Sections:
#   1. Isolation     -- only the lane's 3 files touched; shared files untouched
#   2. Dormancy      -- SPIKE_STATUS=UNFIRED; registry does not advertise the kind
#   3. Offline tests -- pytest -n auto green (suite + the lane's test file)
#   ---> RECEIPT verdict (read-only): offline-green + dormant, queued. NO MERGE.
#
# Usage:
#   tools/w0_feature_lane_gate.sh <kind> [--local] [--skip-tests] [--lane-test-only]
#     <kind>           one of: fillet_face_fullround | curve_driven_pattern | fill_pattern
#                      (or any kind; branch/files are derived by convention)
#     --local          audit the LOCAL branch ref instead of origin/<branch>
#     --skip-tests     skip section 3
#     --lane-test-only run only tests/features/test_<kind>.py, not the full suite
#
# Exit: 0 = received (offline-green + dormant); 1 = a check failed.
# =============================================================================
set -u

KIND=""
USE_LOCAL=0
SKIP_TESTS=0
LANE_TEST_ONLY=0
PYTHON="C:/Python314/python.exe"

for arg in "$@"; do
  case "$arg" in
    --local)          USE_LOCAL=1 ;;
    --skip-tests)     SKIP_TESTS=1 ;;
    --lane-test-only) LANE_TEST_ONLY=1 ;;
    --*)              echo "unknown flag: $arg" >&2; exit 2 ;;
    *)                KIND="$arg" ;;
  esac
done
[ -n "$KIND" ] || { echo "usage: $0 <kind> [--local] [--skip-tests] [--lane-test-only]" >&2; exit 2; }

# kind -> branch (known lanes; convention fallback for any other kind)
case "$KIND" in
  fillet_face_fullround) BRANCH="feat/w68-fillet-faceround" ;;
  curve_driven_pattern)  BRANCH="feat/w68-curve-driven-pattern" ;;
  fill_pattern)          BRANCH="feat/w68-fill-pattern" ;;
  *)                     BRANCH="feat/w68-${KIND}" ;;
esac

# The ONLY files a lane is permitted to add/modify.
HANDLER="src/ai_sw_bridge/features/${KIND}.py"
SPIKE="spikes/v0_2x/spike_${KIND}.py"
TEST="tests/features/test_${KIND}.py"
ALLOWED=("$HANDLER" "$SPIKE" "$TEST")

C_OK=$'\033[32m'; C_NO=$'\033[31m'; C_HD=$'\033[36m'; C_Z=$'\033[0m'
TMP_WT=""
cleanup() { [ -n "$TMP_WT" ] && git worktree remove --force "$TMP_WT" >/dev/null 2>&1; }
trap cleanup EXIT
section() { printf '\n%s== %s ==%s\n' "$C_HD" "$1" "$C_Z"; }
ok()    { printf '  %sPASS%s  %s\n' "$C_OK" "$C_Z" "$1"; }
info()  { printf '        %s\n' "$1"; }
die()   { printf '  %sFAIL%s  %s\n' "$C_NO" "$C_Z" "$1" >&2; \
          printf '\n%sLANE REJECTED -- bounce back to the %s author.%s\n' "$C_NO" "$KIND" "$C_Z" >&2; exit 1; }

cd "$(git rev-parse --show-toplevel)" || die "not in a git repo"
# Fetch is best-effort: when auditing a LOCAL branch with no network/credentials
# the cached origin/master is authoritative (nobody can push to move it).
git fetch origin --tags --quiet 2>/dev/null \
  || printf '        WARN: git fetch failed (offline/no-creds) -- using cached origin/master %s\n' "$(git rev-parse --short origin/master)"
if [ "$USE_LOCAL" -eq 1 ]; then REF="$BRANCH"; else REF="origin/$BRANCH"; fi
git rev-parse --verify --quiet "$REF^{commit}" >/dev/null \
  || die "ref '$REF' does not exist (has the $KIND lane pushed?)"
MASTER="$(git rev-parse origin/master)"
printf '%sW0 FEATURE-LANE GATE%s  kind=%s  ref=%s (%s)  base=origin/master (%s)\n' \
  "$C_HD" "$C_Z" "$KIND" "$REF" "$(git rev-parse --short "$REF")" "$(git rev-parse --short "$MASTER")"

# =============================================================================
section "1. ISOLATION (only the lane's 3 files)"
# Compare against the MERGE-BASE (where the lane branched), NOT current master.
# Otherwise every in-flight lane trips the shared-file guard the moment master
# ships anything (the new lane's _register_lane lines look like a "modification"
# of __init__.py to an absolute master:ref diff). Staleness != tampering.
MERGE_BASE="$(git merge-base "$MASTER" "$REF")"
if ! git merge-base --is-ancestor "$MASTER" "$REF" >/dev/null 2>&1; then
  info "STALE: ref is not a descendant of current origin/master ($(git rev-parse --short "$MASTER")) -- branched at $(git rev-parse --short "$MERGE_BASE"); a rebase is required before its merge slot (isolation is judged against the merge-base, so a clean-but-stale lane still passes here)."
fi
mapfile -t CHANGED < <(git diff --name-only "$MERGE_BASE...$REF")
[ "${#CHANGED[@]}" -gt 0 ] || die "branch changes nothing vs its merge-base"
info "changed files (vs merge-base):"; printf '          %s\n' "${CHANGED[@]}"
is_allowed() { local f="$1"; for a in "${ALLOWED[@]}"; do [ "$f" = "$a" ] && return 0; done; return 1; }
for f in "${CHANGED[@]}"; do
  is_allowed "$f" || die "OUT-OF-LANE file touched: $f (allowed: ${ALLOWED[*]})"
done
# Belt-and-suspenders: the shared/forbidden files must be byte-identical to what
# the lane BRANCHED FROM (merge-base) -- i.e. the lane itself did not touch them.
for guard in "src/ai_sw_bridge/features/__init__.py" "src/ai_sw_bridge/features/verify.py" "src/ai_sw_bridge/mutate.py"; do
  if ! diff -q <(git show "$MERGE_BASE:$guard" 2>/dev/null) <(git show "$REF:$guard" 2>/dev/null) >/dev/null; then
    die "shared file modified by the lane: $guard (registry/substrate/mutate are W0-only)"
  fi
done
# No docs/ touch (W58's locked domain).
for f in "${CHANGED[@]}"; do case "$f" in docs/*) die "docs/ touched: $f (W58's locked domain)";; esac; done
ok "isolation clean -- only ${ALLOWED[*]} touched; __init__/verify/mutate/docs untouched"

# =============================================================================
# 1.5 is a STATIC SOURCE LINT, not a runtime check. The gate is offline (mocked
# COM) so it CANNOT prove a body actually selected -- that is the live seat's job.
# What it CAN catch is the source-level smell of the W68 IBody2 trap: a whole
# solid body (IBody2) is NOT an IEntity, so select_entity/IEntity.Select2 returns
# False for it and SelectByID2's body type string is "SOLIDBODY", never "BODY".
# (W68 indent/flex bounce, 2026-06-21; see reference_ibody2_select_not_ientity.)
section "1.5 BODY-SELECT SMELL (static -- IBody2 is NOT IEntity)"
HSRC="$(git show "$REF:$HANDLER")"
# HARD FAIL: a "BODY" selection-type STRING ARGUMENT is always wrong (-> "SOLIDBODY").
# Match the arg-position token (comma/paren before, comma after) so it catches the
# real call shape -- which is multi-line (SelectByID2( ... \n  name, "BODY", ... ) --
# while ignoring docstring prose like (never "BODY"). and the legit "SOLIDBODY".
if printf '%s' "$HSRC" | grep -Eq '[,(][[:space:]]*"BODY"[[:space:]]*,'; then
  die "handler passes a \"BODY\" selection-type argument -- a solid body's type string is \"SOLIDBODY\", not \"BODY\" (W68 IBody2 trap)"
fi
# WARN (heuristic, non-fatal): selecting a *body*-named ref via select_entity.
if printf '%s' "$HSRC" | grep -Eiq 'select_entity\([^)]*body'; then
  info "WARN: select_entity(...body...) in the handler -- IBody2 is NOT an IEntity;"
  info "      a whole solid body selects via body.Select(Append, Mark), never"
  info "      select_entity/IEntity.Select2 (returns False for bodies). Verify at seat."
fi
ok "no hard body-select trap (\"BODY\" literal) in the handler source"

# =============================================================================
section "2. DORMANCY (UNFIRED, not advertised)"
git cat-file -e "$REF:$HANDLER" 2>/dev/null || die "handler $HANDLER absent on branch"
if git show "$REF:$HANDLER" | grep -Eq '^[[:space:]]*SPIKE_STATUS[[:space:]]*=[[:space:]]*"UNFIRED"'; then
  ok "handler ships SPIKE_STATUS = \"UNFIRED\""
else
  die "handler does NOT declare SPIKE_STATUS=\"UNFIRED\" -- a lane must arrive dormant (W0 flips GREEN post-seat)"
fi

# =============================================================================
# Ephemeral worktree for the import/dormancy + test checks.
if [ "$SKIP_TESTS" -eq 0 ]; then
  TMP_WT="$(git rev-parse --show-toplevel)/../.w0_lane_wt_${KIND}"
  git worktree add --detach --quiet "$TMP_WT" "$REF" || die "could not create ephemeral worktree"
  # Registry must NOT advertise the kind (it isn't wired in __init__.py).
  info "checking the registry does not advertise '$KIND'"
  if ( cd "$TMP_WT" && PYTHONPATH=src "$PYTHON" -c "import sys; from ai_sw_bridge.features import HANDLER_REGISTRY; sys.exit(1 if '$KIND' in HANDLER_REGISTRY else 0)" ); then
    ok "HANDLER_REGISTRY does not advertise '$KIND' (dormant)"
  else
    die "'$KIND' IS advertised in HANDLER_REGISTRY -- lane is wired live, not dormant"
  fi
fi

section "3. OFFLINE TESTS (pytest -n auto)"
if [ "$SKIP_TESTS" -eq 1 ]; then
  info "SKIPPED (--skip-tests)"
else
  if [ "$LANE_TEST_ONLY" -eq 1 ]; then TARGET="$TEST"; LABEL="$TEST"; else TARGET=""; LABEL="full suite"; fi
  info "running: PYTHONPATH=src pytest -n auto -q $LABEL (ephemeral worktree)"
  if ( cd "$TMP_WT" && PYTHONPATH=src "$PYTHON" -m pytest -n auto -q $TARGET ); then
    ok "pytest -n auto GREEN ($LABEL)"
  else
    die "pytest -n auto reported failures ($LABEL)"
  fi
fi

# =============================================================================
section "RECEIPT (read-only -- NO MERGE, NO SEAT-FLIP)"
if git merge-base --is-ancestor origin/master "$REF"; then
  ok "branch is a clean fast-forward descendant of origin/master"
else
  info "NOTE: not a fast-forward of current origin/master (master advanced) -- rebase needed before its eventual merge slot"
fi
printf '\n%sRECEIVED: %s is OFFLINE-GREEN + DORMANT.%s\n' "$C_OK" "$KIND" "$C_Z"
cat <<EOF

  Still required before this ships (both serial, W0-owned):
    1. MERGE  -- behind W58 -> Route-C in the ratified order (guarded FF push).
    2. SEAT-PROOF -- fire spikes/v0_2x/spike_${KIND}.py on the live seat; confirm the
       effect-witness; only then flip SPIKE_STATUS UNFIRED->GREEN + wire __init__.py.
  Harvest the lane's reported residual unknowns into the seat-fire punch list.

EOF
exit 0
