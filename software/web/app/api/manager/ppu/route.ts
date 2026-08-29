import { managerApiBase, managerPpuAlias } from "../manager-bff";

export async function GET(): Promise<Response> {
  try {
    managerApiBase();
    const ppuAlias = managerPpuAlias();
    return Response.json(
      { ok: true, managed: true, ppu_alias: ppuAlias },
      { status: 200, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } },
    );
  } catch {
    return Response.json(
      { ok: false, managed: false, error: { code: "manager_bff_misconfigured", message: "Managed PPU routing is not configured" } },
      { status: 503, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } },
    );
  }
}
