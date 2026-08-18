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

tracked_secret_file=0
while IFS= read -r -d '' path; do
  base="${path##*/}"
  case "$base" in
    .env.example|.env.sample)
      continue
      ;;
    .env|.env.*|*.pem|*.key|*.p8|*.p12|*.pfx|*.jks|credentials.*|secrets.*)
      printf 'ERROR: secret-like file is tracked by Git: %s\n' "$path" >&2
      tracked_secret_file=1
      ;;
  esac
done < <(git -C "$repo" ls-files -z)

if (( tracked_secret_file )); then
  exit 1
fi

printf 'Repository secret-file safety checks passed.\n'
