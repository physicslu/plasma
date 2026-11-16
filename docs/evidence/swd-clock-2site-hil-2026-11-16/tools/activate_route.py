"""Activation-only B1-B3 (fpga_load false) of the Manager-equivalent Bundle for one Route root. No DUT/SWD operation.
usage: activate_route.py WORKTREE ROUTES_DIR IMAGE.bin FILENAME OUT.json"""
import json, sys, hashlib
from pathlib import Path
wt = Path(sys.argv[1]); sys.path[:0] = [str(wt / "scripts"), str(wt / "software/python")]
from plasma_opf import bundle_v3 as b
import plasma_program as p
routes = [r for r in b.load_routes(Path(sys.argv[2])) if "erase" in r.capabilities["operations"]]
assert len(routes) == 1
route = routes[0]
image = Path(sys.argv[3]).read_bytes()
built = b.build_user_image_bundle(route, image, filename=sys.argv[4])
resource = b.resource_set_descriptor(route)
out = {"route_id": route.route_id, "flash_profile": route.flash_profile,
       "resource_set_sha256": b.resource_set_sha256(resource),
       "bundle_sha256": built.archive_sha256, "bundle_size": len(built.archive)}
Path(sys.argv[5]).with_suffix(".zip").write_bytes(built.archive)
HOST = "192.168.2.99"
client = p.open_bootstrap(HOST, p.owner_token(HOST, None))
out["before"] = {k: client.assets_status().get(k) for k in ("state", "asset_set_sha256", "generation")}
sel = p.Selection(archive=built.archive, bundle_sha=built.archive_sha256, firmware_package="", firmware_sha="",
                  firmware_size=0, profile=route.profile_id if hasattr(route, "profile_id") else "",
                  provider="openocd-platform-reference", target="STM32F103C8T6", site=2)
try:
    out["activation"] = p.activate(client, sel)
except p.ProgramDenied as e:
    out["activation"] = {"result": "DENIED", "reason": str(e)}
out["after"] = {k: client.assets_status().get(k) for k in ("state", "asset_set_sha256", "generation")}
Path(sys.argv[5]).write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
