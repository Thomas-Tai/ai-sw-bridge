#!/usr/bin/env bash
# Fetch upstream reference repositories listed in docs/reference_repos.md.
#
# Usage:
#   ./tools/clone_references.sh
#
# Idempotent. New clones go under ./references/<name>/. Existing clones
# get `git fetch` + checkout to the pinned commit; nothing is force-reset
# so any local exploratory changes are preserved.
#
# The `references/` directory is gitignored — never committed back to
# this repo (the bridge would otherwise drag ~150 MB of public upstream
# code into every clone).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REFS_DIR="${REPO_ROOT}/references"
mkdir -p "${REFS_DIR}"

# Format: <local-name>|<git-url>|<pinned-commit-or-HEAD>|<short-description>
REPOS=(
  "SolidworksMCP-python|https://github.com/andrewbartels1/SolidworksMCP-python.git|82e505d88da07fd81acd66b3cd85f6da65323ee4|MIT — source of v0.13 W5.1/W5.2/W5.3/W5.6 ports (ComExecutor, adapter factory, sw_type_info, circuit_breaker)"
  "codestack-master|https://github.com/codestackdev/solidworks-api-examples.git|HEAD|Permissive — reference for SW API patterns; source of EquationMgr.Add2 3-arg dim-binding fix used in v0.2 Path-C builder"
  "solidworks-api|https://github.com/angelsix/solidworks-api.git|HEAD|MIT (2017) — C# add-in framework; reference for deferred L5 (see docs/DEFERRED.md)"
)

clone_or_update() {
  local name="$1"
  local url="$2"
  local pin="$3"
  local desc="$4"
  local target="${REFS_DIR}/${name}"

  echo "==> ${name}"
  echo "    ${desc}"

  if [ -d "${target}/.git" ]; then
    echo "    existing clone at ${target} -- fetching"
    git -C "${target}" fetch --quiet origin
  else
    echo "    cloning ${url} -> ${target}"
    git clone --quiet "${url}" "${target}"
  fi

  if [ "${pin}" = "HEAD" ]; then
    echo "    no pinned commit; leaving on default branch"
  else
    echo "    checking out pinned commit ${pin:0:12}"
    if ! git -C "${target}" checkout --quiet "${pin}" 2>/dev/null; then
      echo "    WARN: pin ${pin:0:12} not reachable; left on current ref"
    fi
  fi
  echo
}

for entry in "${REPOS[@]}"; do
  IFS='|' read -r name url pin desc <<< "${entry}"
  clone_or_update "${name}" "${url}" "${pin}" "${desc}"
done

echo "Done. Reference clones live under ${REFS_DIR}/"
echo "(gitignored — never committed to this repo)"
