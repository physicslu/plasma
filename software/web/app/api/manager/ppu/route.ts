import { managerApiBase, managerPpuAlias, managerRoutingRequired } from "../manager-bff";

export async function GET(): Promise<Response> {
  let managedRequired = false;
  try {
    managedRequired = managerRoutingRequired();
  } catch {
    return Response.json(
      {
        ok: false,
        managed: true,
        configured: false,
        error: { code: "manager_bff_misconfigured", message: "Managed PPU routing mode is invalid" },
      },
      { status: 503, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } },
    );
  }

  try {
    managerApiBase();
    const ppuAlias = managerPpuAlias();
    return Response.json(
      { ok: true, managed: true, configured: true, ppu_alias: ppuAlias },
      { status: 200, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } },
    );
  } catch {
    return Response.json(
      {
        ok: false,
        managed: managedRequired,
        configured: false,
        error: { code: "manager_bff_misconfigured", message: "Managed PPU routing is not configured" },
      },
      { status: 503, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } },
    );
  }
}
