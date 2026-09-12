function disabled(): Response {
  return Response.json(
    { ok: false, error: { code: "deployment_identity_disabled", message: "Deployment identity is not exposed" } },
    { status: 404, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } },
  );
}

export async function GET(): Promise<Response> {
  if (process.env.PLASMA_DEPLOYMENT_IDENTITY_ENABLED !== "1") return disabled();

  const service = (process.env.PLASMA_DEPLOYMENT_IDENTITY_SERVICE ?? "plasma-control-station").trim();
  return Response.json(
    {
      schema_version: 1,
      service: service || "plasma-control-station",
      platform: process.env.RENDER === "true" ? "render" : "local",
      git_commit: process.env.RENDER_GIT_COMMIT?.trim() || null,
      git_branch: process.env.RENDER_GIT_BRANCH?.trim() || null,
    },
    { headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } },
  );
}
