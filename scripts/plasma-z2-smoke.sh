#!/usr/bin/env bash
# Operator-run SSH deploy + live smoke, no GitHub Actions/Stage Orchestrator.
set -Eeuo pipefail
export LC_ALL=C
usage() {
  echo 'Usage: bash scripts/plasma-z2-smoke.sh --target <SSH-alias-or-user@host> [--plan]'
}
target=""
plan=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) [[ $# -ge 2 ]] || { usage; exit 2; }; target="$2"; shift 2 ;;
    --plan) plan=1; shift ;;
    *) usage; exit 2 ;;
  esac
done
[[ "$target" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.@-]{0,252}$ ]] ||
  { echo 'DENIED: valid --target required'; exit 2; }
command -v git >/dev/null && command -v tar >/dev/null &&
command -v sha256sum >/dev/null || { echo 'DENIED: host tools missing'; exit 2; }
cd "$(git rev-parse --show-toplevel)"
repo="$(git remote get-url origin)"
[[ "$repo" == 'https://github.com/physicslu/plasma' ||
   "$repo" == 'https://github.com/physicslu/plasma.git' ||
   "$repo" == 'git@github.com:physicslu/plasma' ||
   "$repo" == 'git@github.com:physicslu/plasma.git' ]] ||
  { echo 'DENIED: unexpected Git origin'; exit 2; }
git fetch --quiet origin refs/pull/1167/head
sha="$(git rev-parse --verify 'FETCH_HEAD^{commit}')"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || exit 2
work="$(mktemp -d)"
remote=""
cleanup() {
  if [[ -n "$remote" && $plan == 0 ]]; then
    ssh -o StrictHostKeyChecking=yes -- "$target" "rm -rf -- '$remote'" >/dev/null 2>&1 || true
  fi
  rm -rf -- "$work"
}
trap cleanup EXIT
mkdir -p "$work/src"
sources=(
  pl/hil/f1b.py
  pl/hil/path2_f1b_minimal_stage.py
  pl/hil/path2_f1b_dev_risk.py pl/hil/path2_z2_target_guard.py
  pl/hil/swd04/one_shot.py
  pl/hil/swd04/development.py pl/hil/swd04/contract.py
  pl/hil/swd04/collect.py pl/hil/swd04/staging.py
  software/python/plasma_interfaces/linux_mmio.py
  scripts/z2/plasma-path2-root-entry
  scripts/z2/plasma-z2-ssh-smoke-target.sh
)
git archive --format=tar "$sha" -- "${sources[@]}" | tar -xf - -C "$work/src"
printf '%s\n' "$sha" > "$work/src/.plasma-path2-source-commit"
(
  cd "$work/src"
  while IFS= read -r -d '' f; do
    sha256sum "$f" | sed 's@  ./@  @'
  done < <(find . -type f \( -name '*.py' -o -name '.plasma-path2-source-commit' \) -print0 | sort -z)
) > "$work/src/.plasma-path2-source-sha256"
(cd "$work/src" && sha256sum -c --status .plasma-path2-source-sha256) ||
  { echo 'DENIED: local bundle verification failed'; exit 2; }
tar -cf "$work/bundle.tar" -C "$work/src" .
echo "SOURCE_PIN=$sha"
echo "BUNDLE_SHA256=$(sha256sum "$work/bundle.tar" | cut -d' ' -f1)"
if [[ "$plan" == 1 ]]; then
  echo 'RESULT=NOT_RUN PLAN_ONLY; no SSH, Z2 deployment, FPGA or DUT operation'
  exit 0
fi
# Use the operator's existing SSH config, host-key pin and interactive sudo.
remote="$(ssh -o StrictHostKeyChecking=yes -- "$target" \
  'umask 077; mktemp -d /tmp/plasma-z2.XXXXXXXX')"
[[ "$remote" =~ ^/tmp/plasma-z2\.[a-zA-Z0-9]{8}$ ]] ||
  { echo 'DENIED: remote staging path invalid'; exit 2; }
scp -q -o StrictHostKeyChecking=yes -- "$work/bundle.tar" \
  "$target:$remote/bundle.tar"
scp -q -o StrictHostKeyChecking=yes -- \
  "$work/src/scripts/z2/plasma-z2-ssh-smoke-target.sh" "$target:$remote/target.sh"
expected="$(sha256sum "$work/src/scripts/z2/plasma-z2-ssh-smoke-target.sh" | cut -d' ' -f1)"
actual="$(ssh -o StrictHostKeyChecking=yes -- "$target" \
  "sha256sum '$remote/target.sh' | cut -d' ' -f1")"
[[ "$actual" == "$expected" ]] || { echo 'DENIED: remote installer hash mismatch'; exit 2; }
log_dir="$HOME/.local/state/plasma"
mkdir -p "$log_dir"
chmod 0700 "$log_dir"
log="$log_dir/z2-smoke-$(date -u +%Y%m%dT%H%M%SZ)-$sha.log"
echo "LOG=$log"
echo 'DEPLOY_START: SWPC SSH -> Z2 sudo; sudo may prompt interactively'
ssh -tt -o StrictHostKeyChecking=yes -- "$target" \
  "sudo /bin/bash '$remote/target.sh' '$remote/bundle.tar' '$sha'" |
  tee "$log"
