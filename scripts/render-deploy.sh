#!/usr/bin/env bash
set -Eeuo pipefail

say() {
  printf '[plasmactl] %s\n' "$*"
}

die() {
  printf '[plasmactl] ERROR: %s\n' "$*" >&2
  exit 1
}

hook="${PLASMA_RENDER_DEPLOY_HOOK_URL:-}"

command -v curl >/dev/null 2>&1 || die "找不到必要指令：curl"
[[ -n "$hook" ]] || die "未設定 PLASMA_RENDER_DEPLOY_HOOK_URL；請先在 Render Settings 取得 secret Deploy Hook URL"

case "$hook" in
  https://api.render.com/deploy/*) ;;
  *) die "PLASMA_RENDER_DEPLOY_HOOK_URL 必須是 https://api.render.com/deploy/..." ;;
esac

case "$hook" in
  *\?ref=*|*\&ref=*)
    die "Render Deploy Hook 不可包含 ref=；Plasma 只允許部署 linked branch 的 latest commit，以免停用 Auto-Deploy"
    ;;
esac

say "觸發 Render linked branch 的 latest commit deployment"
if ! curl \
  --fail \
  --silent \
  --show-error \
  --request POST \
  --output /dev/null \
  "$hook"; then
  die "Render Deploy Hook 請求失敗"
fi

say "Render 部署已觸發；這代表 request accepted，不代表新 runtime 已完成 health acceptance"
