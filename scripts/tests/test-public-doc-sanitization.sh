#!/usr/bin/env bash
set -Eeuo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo"

# Public documentation should describe roles and interfaces without publishing
# operator-specific infrastructure identifiers. Keep these patterns generic so
# the guard itself does not preserve a previously exposed value.
patterns=(
  '/home/[[:alnum:]_.-]+/'
  '/storage/projects/'
  '[[:alnum:]_.-]+@[[:alnum:]_.-]*swpc'
  'tail[[:alnum:]-]*\.ts\.net'
  'DESKTOP-[[:alnum:]_-]+'
)

targets=(README.md docs)
failed=0

for pattern in "${patterns[@]}"; do
  files=()
  while IFS= read -r file; do
    files+=("$file")
  done < <(grep -RIlE --include='*.md' -- "$pattern" "${targets[@]}" 2>/dev/null || true)
  if ((${#files[@]})); then
    printf 'ERROR: public documentation contains an operator-specific identifier pattern:\n' >&2
    printf '  %s\n' "${files[@]}" >&2
    failed=1
  fi
done

if ((failed)); then
  printf '%s\n' \
    'Replace personal usernames, private hostnames, and site-specific absolute paths with role-based placeholders.' >&2
  exit 1
fi

printf 'Public documentation sanitization checks passed.\n'
