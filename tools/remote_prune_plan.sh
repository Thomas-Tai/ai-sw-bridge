#!/usr/bin/env bash
# =============================================================================
#  remote_prune_plan.sh — PRE-LAUNCH REMOTE SANITIZATION (DESTRUCTIVE)
# =============================================================================
#  WHAT THIS DOES: deletes stale branches and closes stale Dependabot PRs on
#  the GitHub REMOTE so the repository's public face is just `master` (+ the
#  release branch + tags) before a private -> public flip.
#
#  THIS IS A DESTRUCTIVE REMOTE OPERATION. It rewrites what the world sees.
#  - Run it ONLY after the business decision to go public is final, counsel has
#    finalized LICENSE/CLA (Gate 4), and the pre-publication scan is clean
#    (docs/human_gates_runbook.md, appendix).
#  - It does NOT touch `master` or any tag. It deletes only the named stale
#    worker branches and the Dependabot branches/PRs enumerated below.
#  - Deleted branches remain RECOVERABLE locally: every commit is still in your
#    local object store and in ../ai-sw-bridge-pre-ipscrub.bundle. A deleted
#    remote branch can be restored with `git push origin <sha>:refs/heads/<name>`.
#
#  Authoritative state captured 2026-06-26 via `gh pr list` + `git ls-remote`.
#  RE-VERIFY before running (see the DRY-RUN section) — the remote may have moved.
# =============================================================================
set -euo pipefail

REMOTE="origin"

# --- Guard: refuse to run unless the operator has explicitly opted in --------
if [[ "${I_HAVE_DECIDED_TO_GO_PUBLIC:-}" != "yes" ]]; then
  cat >&2 <<'MSG'
REFUSING TO RUN. This is a destructive, pre-launch remote sweep.
When you have (1) decided source-available is the strategy, (2) finalized the
license with counsel, and (3) confirmed the pre-publication scan is clean, run:

    I_HAVE_DECIDED_TO_GO_PUBLIC=yes bash tools/remote_prune_plan.sh
MSG
  exit 1
fi

# --- DRY-RUN: show exactly what exists right now, before touching anything ----
echo "== Current remote branches (BEFORE) =="
git ls-remote --heads "$REMOTE"
echo
echo "== Open PRs (BEFORE) =="
gh pr list --state open
echo
echo "Proceeding in 5s — Ctrl-C to abort..."
sleep 5

# --- Safety assertion: master must be present and is never a delete target ----
git ls-remote --heads "$REMOTE" | grep -q 'refs/heads/master$' \
  || { echo "ABORT: 'master' not found on $REMOTE — refusing to proceed." >&2; exit 1; }

# --- 1) Close the 5 stale Dependabot PRs AND delete their branches ------------
#  `--delete-branch` closes the PR cleanly (no zombie in the PR queue) and
#  removes the underlying dependabot/* branch in one step.
#  PR# -> branch (verified 2026-06-26):
#    2 -> dependabot/github_actions/softprops/action-gh-release-3
#    3 -> dependabot/github_actions/gitleaks/gitleaks-action-3
#    4 -> dependabot/github_actions/actions/checkout-7
#    5 -> dependabot/pip/black-26.5.1
#    6 -> dependabot/pip/pillow-gte-10.0-and-lt-13
for pr in 2 3 4 5 6; do
  echo "-- closing PR #$pr (+ deleting its branch) --"
  gh pr close "$pr" \
    --delete-branch \
    --comment "Closing as part of pre-public-launch repo sanitization. The dependency update itself is tracked; re-evaluate/merge after launch." \
    || echo "   (PR #$pr already closed or branch gone — skipping)"
done

# --- 2) Delete the 4 stale feature/worker branches ---------------------------
for b in \
  feat/w58-doc-trueup \
  feat/w68-curve-driven-pattern \
  feat/w68-fill-pattern \
  feat/w68-fillet-faceround
do
  echo "-- deleting remote branch $b --"
  git push "$REMOTE" --delete "$b" \
    || echo "   ($b already gone — skipping)"
done

# --- 3) Prune local remote-tracking refs + show the result -------------------
git fetch "$REMOTE" --prune
echo
echo "== Current remote branches (AFTER) =="
git ls-remote --heads "$REMOTE"
echo
echo "== Open PRs (AFTER) =="
gh pr list --state open
echo
echo "Done. Expected AFTER state: only 'master' (+ your release branch once pushed)."

# =============================================================================
#  IMPORTANT — DEPENDABOT WILL RESPAWN unless you stop it.
#  Closing a Dependabot PR does not stop Dependabot from re-opening it on its
#  next scan. Before/after this prune, pick ONE:
#    (a) PREFERRED: merge these updates instead of closing — they are real and
#        security-relevant (gitleaks-action 2->3, actions/checkout 5->7, etc.).
#        Merge needs CI green (restore Actions) or a reviewed manual merge.
#    (b) Tell Dependabot to drop a specific update so it won't reappear:
#        gh pr comment <num> --body "@dependabot ignore this major version"
#    (c) Pause Dependabot entirely: comment out / remove the update entries in
#        .github/dependabot.yml (or disable it in repo Settings -> Code security).
# =============================================================================
