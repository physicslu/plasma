#!/usr/bin/env bash
set -Eeuo pipefail

script_path="$(readlink -f "${BASH_SOURCE[0]}")"
repo="$(cd "$(dirname "$script_path")/../.." && pwd)"
gitignore="$repo/.gitignore"
clineignore="$repo/.clineignore"

gitignore_patterns=(
  '.env'
  '.env.*'
  '!.env.example'
  '!.env.sample'
  '*.pem'
  '*.key'
  '*.p8'
  '*.p12'
  '*.pfx'
  '*.jks'
  'credentials.*'
  'secrets.*'
)

clineignore_patterns=(
  '.env'
  '.env.*'
  '*.pem'
  '*.key'
  '*.p8'
  '*.p12'
  '*.pfx'
  '*.jks'
  'credentials.*'
  'secrets.*'
)

missing=0
for pattern in "${gitignore_patterns[@]}"; do
  if ! grep -Fqx -- "$pattern" "$gitignore"; then
    printf 'ERROR: missing secret exclusion in .gitignore: %s\n' "$pattern" >&2
    missing=1
  fi
done

for pattern in "${clineignore_patterns[@]}"; do
  if ! grep -Fqx -- "$pattern" "$clineignore"; then
    printf 'ERROR: missing secret exclusion in .clineignore: %s\n' "$pattern" >&2
    missing=1
  fi
done

if (( missing )); then
  exit 1
fi

is_secret_like_path() {
  local path="$1" base="${1##*/}"
  case "$base" in
    .env.example|.env.sample)
      return 1
      ;;
    .env|.env.*|*.pem|*.key|*.p8|*.p12|*.pfx|*.jks|credentials.*|secrets.*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

tracked_secret_file=0
while IFS= read -r -d '' path; do
  if is_secret_like_path "$path"; then
    printf 'ERROR: secret-like file is tracked by Git: %s\n' "$path" >&2
    tracked_secret_file=1
  fi
done < <(git -C "$repo" ls-files -z)

if (( tracked_secret_file )); then
  exit 1
fi

if [[ "$(git -C "$repo" rev-parse --is-shallow-repository)" == "false" ]]; then
  historical_secret_file=0
  while IFS= read -r path; do
    [[ -n "$path" ]] || continue
    if is_secret_like_path "$path"; then
      historical_secret_file=1
      break
    fi
  done < <(git -C "$repo" log --all --format= --name-only --)

  if (( historical_secret_file )); then
    printf 'ERROR: Git history contains a secret-like filename; audit history before release.\n' >&2
    exit 1
  fi

  history_signature='ghp_[[:alnum:]]{30,}|github_pat_[[:alnum:]_]{30,}|AKIA[0-9A-Z]{16}|-----BEGIN ([A-Z0-9 ]+ )?PRIVATE KEY-----'
  if git -C "$repo" log --all -p --no-color -- | grep -Eq -- "$history_signature"; then
    printf 'ERROR: Git history contains a high-confidence credential signature; rotate and purge it before release.\n' >&2
    exit 1
  fi
else
  printf 'NOTICE: shallow clone; historical credential scan skipped.\n'
fi

printf 'Repository secret-file safety checks passed.\n'
