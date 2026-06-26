#!/usr/bin/env bash
# =============================================================================
#  release_v1.5_v1.6.sh — TURNKEY GATE-2 RELEASE (tags v1.5.0 + v1.6.0)
# =============================================================================
#  WHAT THIS DOES: cuts the v1.5.0 + v1.6.0 release exactly as documented in
#  docs/human_gates_runbook.md (Gate 2), with the W0 invariants enforced in code
#  instead of by hand:
#    - the repo MUST be private (isPrivate==true) before any push;
#    - the master advance MUST be a fast-forward (never --force);
#    - tag creation is idempotent (re-running is safe; existing tags are kept).
#
#  THIS PUSHES TO THE REMOTE (tags + a fast-forward of master). It is the
#  human-run packaging of the Gate-2 commands — an agent must not run it.
#  Run it ONLY after Gate 1 (Actions billing) is resolved OR you have chosen the
#  Actions-free manual path (then this script also publishes the Releases via
#  `gh release create`, step 5).
#
#  Boundaries captured 2026-06-26:
#    - origin/master  == 8cefd01   (the v1.5.0 boundary — v1.5.0 tags here)
#    - feat/w67-phase3 tip         (the v1.6.0 tip — v1.6.0 tags at HEAD)
#  RE-VERIFY before running (the DRY-RUN section prints the live SHAs).
# =============================================================================
set -euo pipefail

REMOTE="origin"
RELEASE_BRANCH="feat/w67-phase3"
V150_BOUNDARY="8cefd01"          # origin/master at the v1.5.0 line

# --- Guard: refuse to run unless the operator has explicitly opted in --------
if [[ "${I_HAVE_RESOLVED_BILLING_AND_AM_RELEASING:-}" != "yes" ]]; then
  cat >&2 <<'MSG'
REFUSING TO RUN. This pushes tags and fast-forwards master on the remote.
When Gate 1 (Actions billing) is resolved — or you have chosen the Actions-free
manual release path (docs/human_gates_runbook.md, Gate 1 Option A) — run:

    I_HAVE_RESOLVED_BILLING_AND_AM_RELEASING=yes bash tools/release_v1.5_v1.6.sh
MSG
  exit 1
fi

# --- DRY-RUN: print the live boundaries before touching anything -------------
echo "== Fetching remote state =="
git fetch "$REMOTE" --tags

TIP="$(git rev-parse "$RELEASE_BRANCH")"
ORIGIN_MASTER="$(git rev-parse "$REMOTE/master")"

echo
echo "== Release boundaries (live) =="
echo "  $REMOTE/master         : $ORIGIN_MASTER  (v1.5.0 tag target)"
echo "  $RELEASE_BRANCH tip    : $TIP  (v1.6.0 tag target)"
echo

# --- Invariant 1: repo MUST be private before any push -----------------------
PRIV="$(gh repo view --json isPrivate -q .isPrivate)"
if [[ "$PRIV" != "true" ]]; then
  echo "ABORT: gh reports isPrivate=$PRIV. W0 protocol pushes only to a PRIVATE repo." >&2
  exit 1
fi
echo "isPrivate==true ✓"

# --- Invariant 2: master advance MUST be a fast-forward ----------------------
if ! git merge-base --is-ancestor "$ORIGIN_MASTER" "$TIP"; then
  echo "ABORT: $REMOTE/master ($ORIGIN_MASTER) is NOT an ancestor of $RELEASE_BRANCH." >&2
  echo "       The master advance would not be a fast-forward. Refusing." >&2
  exit 1
fi
echo "fast-forward $REMOTE/master -> $RELEASE_BRANCH ✓ ($(git rev-list --count "$ORIGIN_MASTER..$TIP") commits)"

# --- Sanity: the v1.5.0 boundary should match where origin/master sits -------
if [[ "$ORIGIN_MASTER" != "$V150_BOUNDARY"* ]]; then
  echo "WARNING: $REMOTE/master ($ORIGIN_MASTER) != documented v1.5.0 boundary $V150_BOUNDARY." >&2
  echo "         Re-confirm the runbook before continuing (it may have moved)." >&2
fi

echo
echo "Proceeding in 5s — Ctrl-C to abort..."
sleep 5

# --- helper: create an annotated tag only if it doesn't already exist --------
make_tag() {  # $1=tag  $2=target-sha  $3=message
  local tag="$1" target="$2" msg="$3"
  if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    echo "-- tag $tag already exists ($(git rev-parse --short "$tag^{commit}")) — keeping it --"
  else
    echo "-- creating tag $tag at $(git rev-parse --short "$target") --"
    git tag -a "$tag" "$target" -m "$msg"
  fi
}

# --- 1) v1.5.0 — annotate + tag the already-published boundary ---------------
make_tag v1.5.0 "$ORIGIN_MASTER" "v1.5.0 — Runtime Resilience & Design Intelligence"
git push "$REMOTE" v1.5.0

# --- 2) Fast-forward origin/master to the v1.6.0 tip -------------------------
#  --ff-only makes git itself refuse a non-fast-forward; never --force.
echo "-- fast-forwarding $REMOTE/master -> $RELEASE_BRANCH --"
git push "$REMOTE" "$RELEASE_BRANCH:master"

# --- 3) v1.6.0 — tag at the NEW tip (NOT a2cbee4) ----------------------------
make_tag v1.6.0 "$TIP" "v1.6.0 — Self-healing batch + unified MCP write-gate"
git push "$REMOTE" v1.6.0

# --- 4) Show the result ------------------------------------------------------
git fetch "$REMOTE" --tags --prune
echo
echo "== Tags on remote (AFTER) =="
git ls-remote --tags "$REMOTE" | grep -E 'v1\.(5|6)\.0$' || echo "  (none yet — check push output above)"
echo

# --- 5) Actions-free publish (ONLY if CI/release.yml is NOT restored) --------
#  If Gate 1 is resolved and release.yml runs on tag push, it publishes the
#  GitHub Releases for you — SKIP this step. If you took the manual path
#  (Gate 1 Option A), publish them here. `gh release create` is a REST call,
#  not an Actions run, so it works even while the billing block stands.
cat <<'MSG'
NEXT — publish the GitHub Releases:

  If CI (release.yml) is restored, it auto-publishes on the tag push — you are done.

  If you are on the Actions-free manual path, publish by hand:
    gh release create v1.5.0 --title "v1.5.0 — Runtime Resilience & Design Intelligence" \
      --notes-file <(sed -n '/## \[1.5.0\]/,/## \[1.4.0\]/p' CHANGELOG.md)
    gh release create v1.6.0 --latest --title "v1.6.0 — Self-healing batch + unified MCP write-gate" \
      --notes-file <(sed -n '/## \[1.6.0\]/,/## \[1.5.0\]/p' CHANGELOG.md)

  Then confirm: gh release list
MSG

echo "Done. Tags pushed; master fast-forwarded to the v1.6.0 tip."
