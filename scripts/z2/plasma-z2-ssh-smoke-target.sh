#!/usr/bin/env bash
# Z2 installer and live smoke; invoked explicitly over operator SSH.
set -Eeuo pipefail
export LC_ALL=C
[[ $# == 3 && $(id -u) == 0 ]] || { echo 'DENIED: root plus bundle, Git SHA, bundle SHA required'; exit 2; }
bundle="$1"; sha="$2"; bundle_sha="$3"
[[ "$sha" =~ ^[0-9a-f]{40}$ && -f "$bundle" && ! -L "$bundle" ]] || exit 2
[[ "$bundle_sha" =~ ^[0-9a-f]{64}$ &&
   "$(sha256sum "$bundle" | cut -d' ' -f1)" == "$bundle_sha" ]] ||
  { echo 'DENIED: bundle bytes changed'; exit 2; }
[[ "$(uname -m)" == armv7l && -x /opt/plasma/python/3.12.13/bin/python3 ]] ||
  { echo 'DENIED: Z2 ARMv7 native Python not installed'; exit 2; }
root=/root/plasma-path2-approved
entry=/usr/local/libexec/plasma/z2-path2-root-entry
state_file="$root/.plasma-f1b-site1-development-state.json"
[[ ! -L "$root" && ! -L "$entry" ]] || { echo 'DENIED: symlink'; exit 2; }
if [[ -e "$state_file" ]]; then
  old_state="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("status","UNKNOWN"))' "$state_file" 2>/dev/null || echo UNKNOWN)"
  [[ "$old_state" == BASE ]] || { echo 'DENIED: prior FPGA image not BASE'; exit 2; }
fi
[[ "$(cat /sys/class/fpga_manager/fpga0/state)" == operating ]] || { echo 'DENIED: Manager state'; exit 2; }
# "operating" alone does not identify a Golden FPGA image.
last="$(dmesg 2>/dev/null | grep -E 'fpga_manager.*: writing .* to Xilinx FPGA Manager' | tail -n 1 || true)"
[[ "$last" == *'writing base.bin to Xilinx FPGA Manager'* ]] ||
  { echo 'DENIED: Golden Image not positively observed'; exit 2; }

work="$(mktemp -d /root/.plasma-z2-smoke.XXXXXXXX)"
trap 'rm -rf -- "$work"' EXIT
mkdir "$work/src"
while IFS= read -r path; do
  [[ "$path" == ./* && "$path" != *'../'* && "$path" != *'/..' ]] ||
    { echo 'DENIED: unsafe archive path'; exit 2; }
done < <(tar -tf "$bundle")
tar -xf "$bundle" -C "$work/src" --no-same-owner --no-same-permissions
src="$work/src"
[[ -z "$(find "$src" -type l -print -quit)" ]] || { echo 'DENIED: symlink source'; exit 2; }
[[ -f "$src/.plasma-path2-source-commit" &&
   "$(cat "$src/.plasma-path2-source-commit")" == "$sha" &&
   -f "$src/scripts/z2/plasma-path2-root-entry" &&
   -f "$src/pl/hil/path2_f1b_minimal_stage.py" ]] || { echo 'DENIED: incomplete bundle'; exit 2; }
(cd "$src" && sha256sum --check --status .plasma-path2-source-sha256) ||
  { echo 'DENIED: source Manifest mismatch'; exit 2; }

# Existing, pinned firmware: neither image is downloaded or built here.
base_sha="$(sed -n -E "s/^BASE_SHA = '([0-9a-f]{64})'$/\1/p" "$src/pl/hil/f1b.py")"
candidate_sha="$(sed -n -E "s/^BIN_SHA = '([0-9a-f]{64})'$/\1/p" "$src/pl/hil/f1b.py")"
[[ "$base_sha" =~ ^[0-9a-f]{64}$ && "$candidate_sha" =~ ^[0-9a-f]{64}$ ]] || exit 2
[[ "$(sha256sum /lib/firmware/base.bin | cut -d' ' -f1)" == "$base_sha" &&
   "$(sha256sum /lib/firmware/plasma-f1b-owner-20261020-once.bin | cut -d' ' -f1)" == "$candidate_sha" ]] ||
  { echo 'DENIED: firmware digest mismatch'; exit 2; }

# Do not discard the root-owned historical state checkpoint.
if [[ -f "$state_file" ]]; then cp -p "$state_file" "$src/"; fi
mkdir -p /usr/local/libexec/plasma
chown -R root:root "$src"
find "$src" -type d -exec chmod 0755 {} +
find "$src" -type f -exec chmod 0644 {} +
if [[ -f "$src/.plasma-f1b-site1-development-state.json" ]]; then
  chmod 0600 "$src/.plasma-f1b-site1-development-state.json"
fi
install -o root -g root -m 0755 "$src/scripts/z2/plasma-path2-root-entry" "$work/entry"
rm -rf "$src/scripts"
backup="/root/.plasma-path2-backup-$(date -u +%Y%m%dT%H%M%SZ)-$sha"
[[ ! -e "$backup" ]] || exit 2
old=0
if [[ -d "$root" ]]; then mv "$root" "$backup"; old=1; fi
if ! mv "$src" "$root"; then
  if [[ $old == 1 ]]; then mv "$backup" "$root"; fi
  echo 'FAIL: source install; existing root restored'; exit 2
fi
if ! install -o root -g root -m 0755 "$work/entry" "$entry.next" ||
   ! mv -f "$entry.next" "$entry"; then
  rm -f "$entry.next"
  mv "$root" "$work/failed"
  if [[ $old == 1 ]]; then mv "$backup" "$root"; fi
  echo 'FAIL: Root Entry install; manual version review required'; exit 2
fi
echo "DEPLOY_PASS SOURCE_SHA=$sha"

# Check authentic Z2 receipts, not merely an exit status.
checked_boot=""
run_op() {
  local op="$1" valid="$2" output boot
  if ! output="$("$entry" "$op" "$sha" 2>&1)"; then
    echo "FAIL: $op Root command" >&2
    return 1
  fi
  if ! boot="$(printf '%s\n' "$output" | python3 -c '
import sys,json
op,expected=sys.argv[1:]
r=[x for x in sys.stdin.read().splitlines() if x.startswith("PLASMA_PATH2_STAGE=")]
if len(r)!=1: sys.exit(2)
try: d=json.loads(r[0].split("=",1)[1])
except (ValueError,TypeError): sys.exit(2)
if d.get("stage")!=op or d.get("result") not in expected.split(","): sys.exit(2)
if not isinstance(d.get("boot_id"),str) or len(d["boot_id"])<8: sys.exit(2)
if op=="test" and (d.get("read32_count")!=3 or d.get("write32_count")!=0): sys.exit(2)
print(d["boot_id"])
' "$op" "$valid")"; then
    echo "FAIL: $op receipt" >&2
    return 1
  fi
  [[ -z "$checked_boot" || "$boot" == "$checked_boot" ]] ||
    { echo 'FAIL: boot ID changed' >&2; return 1; }
  checked_boot="$boot"
  echo "PASS: $op BOOT_ID=$boot"
}
safe_recover() {
  local observed
  observed="$(python3 -c '
import json,sys
try:
 d=json.load(open(sys.argv[1]))
 print(d.get("status","UNKNOWN"),d.get("boot_id",""))
except Exception: print("UNKNOWN")
' "$root/.plasma-f1b-site1-development-state.json")"
  if [[ "$observed" == "F1B $checked_boot" ]]; then
    echo 'RECOVERY: guarded Restore requested from confirmed F1B checkpoint'
    run_op restore RESTORED_VERIFIED,ALREADY_RESTORED ||
      echo 'RECOVERY_UNKNOWN: manual recovery required'
  else
    echo 'RECOVERY_UNKNOWN: state not proven recoverable; no blind reload'
  fi
}
if ! run_op download LOADED_AND_HELD; then
  echo 'RESULT=FAIL RECOVERY=MANUAL_REVIEW'; exit 1
fi
if ! run_op test IDENTITY_PASS; then
  safe_recover
  echo 'RESULT=FAIL TEST=FAIL'; exit 1
fi
if ! run_op restore RESTORED_VERIFIED,ALREADY_RESTORED; then
  echo 'RESULT=FAIL RESTORE=UNKNOWN'; exit 1
fi
echo "RESULT=PASS SOURCE_SHA=$sha MMIO_READS=3 MMIO_WRITES=0 RESTORE=PASS"
