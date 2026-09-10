import { createHash } from "node:crypto";
import { expect, test } from "@playwright/test";

const alias = "ppu-a";
const uploadId = "a".repeat(32);
const token = "bootstrap-pairing-token-0123456789abcdef";

const registry = {
  ok: true,
  service: "plasma-manager",
  contract_version: "1",
  mutable: true,
  storage: "file",
  ppus: [
    {
      alias,
      endpoint: "http://192.168.77.10:18080",
      lifecycle: "pending",
      registered_at: "2026-09-10T00:00:00+00:00",
      updated_at: "2026-09-10T00:00:00+00:00",
    },
  ],
};

function fleet(active = false) {
  return {
    ok: true,
    contract_version: "1",
    observed_at: "2026-09-10T00:00:00+00:00",
    degraded: false,
    summary: {
      configured_ppus: 1,
      reachable_ppus: 1,
      ready_ppus: 0,
      current_ppus: 1,
      stale_ppus: 0,
      unknown_ppus: 0,
      reported_sites: 1,
      enabled_sites: 1,
      identity_conflicts: 0,
    },
    manager: {
      cache_age_s: 0.1,
      poll_interval_s: 2,
      refresh_healthy: true,
      observation_store: { mode: "memory", healthy: true, writable: true },
    },
    ppus: [
      {
        alias,
        identity: {
          ppu_id: "ppu-runtime-1",
          facility_id: "lab",
          model: "PYNQ-Z2",
          display_name: "Runtime Test PPU",
        },
        transport_state: "reachable",
        execution_state: active ? "running" : "ready",
        observation: {
          state: "current",
          last_success_at: "2026-09-10T00:00:00+00:00",
          stale_age_s: 0.1,
        },
        topology: {
          source: "current",
          site_count: 1,
          enabled_site_count: 1,
          sites: [
            {
              site_id: 1,
              enabled: true,
              state: active ? "program" : "ready",
              current_job_id: active ? "job-active" : null,
              latest_job: null,
              interface: "mock",
              target: null,
            },
          ],
        },
        current_capacity: { site_count: 1, enabled_site_count: 1 },
        identity_conflict: false,
        degraded: false,
      },
    ],
  };
}

function bootstrapStatus(paired: boolean, deployment: Record<string, unknown> | null = null) {
  return {
    ok: true,
    ppu_alias: alias,
    bootstrap_endpoint_policy: "same-host-port-18081",
    pairing: {
      paired,
      device_id: paired ? "ppu-device-1234567890abcdef12345678" : null,
      device_match: paired,
      credential_persistence: "manager-device-bound-file",
      updated_at: paired ? "2026-09-10T00:00:01+00:00" : null,
    },
    bootstrap: {
      schema_version: 1,
      bootstrap: { api_version: "1", version: "0.1.0", state: "bootstrap_ready" },
      identity: {
        device_id: "ppu-device-1234567890abcdef12345678",
        ppu_id: "ppu-runtime-1",
        facility_id: "lab",
        hardware_revision: "pynq-z2-rev1",
      },
      runtime: {
        state: "runtime_absent",
        release_id: null,
        product_version: null,
        git_sha: null,
        target: null,
        reason: null,
      },
      fpga: {
        pl_version: null,
        pl_compatibility: "not_managed",
        pl_qualification: "not_qualified",
      },
      capabilities: {
        runtime_deployment: true,
        identity_update: false,
        fpga_update: false,
      },
      deployment,
    },
  };
}

async function openRuntimeDeployment(page: import("@playwright/test").Page, active = false) {
  await page.route(/\/api\/manager\/registry$/, route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(registry),
  }));
  await page.route(/\/api\/fleet$/, route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(fleet(active)),
  }));
  await page.goto("/engineering");
  await page.getByRole("button", { name: "PPU / Sites", exact: true }).click();
  await page.getByRole("button", { name: "Runtime 部署", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Runtime Deployment", level: 2, exact: true })).toBeVisible();
}

test("Runtime Deployment pairs, uploads a verified kit, and starts deployment without an FPGA action", async ({ page }) => {
  let paired = false;
  let deployment: Record<string, unknown> | null = null;
  let pairBody: unknown = null;
  let createBody: unknown = null;
  let chunkBody: Record<string, unknown> | null = null;
  let commitBody: unknown = null;
  let deploymentBody: unknown = null;
  let fpgaRequests = 0;

  await page.route(/\/api\/manager\/registry\/ppu-a\/bootstrap(?:\/.*)?$/, async route => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (request.method() === "GET" && pathname.endsWith("/bootstrap")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(bootstrapStatus(paired, deployment)) });
      return;
    }
    if (pathname.endsWith("/bootstrap/pair")) {
      pairBody = request.postDataJSON();
      paired = true;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(bootstrapStatus(true, deployment)) });
      return;
    }
    if (pathname.endsWith("/bootstrap/uploads")) {
      createBody = request.postDataJSON();
      const body = createBody as { size: number; sha256: string };
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, upload: { upload_id: uploadId, state: "receiving", size: body.size, sha256: body.sha256, received_bytes: 0 } }),
      });
      return;
    }
    if (pathname.endsWith(`/bootstrap/uploads/${uploadId}/chunks`)) {
      chunkBody = request.postDataJSON() as Record<string, unknown>;
      const data = Buffer.from(String(chunkBody.data_base64), "base64");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, upload: { upload_id: uploadId, state: "receiving", size: data.length, sha256: String(chunkBody.sha256), received_bytes: data.length } }),
      });
      return;
    }
    if (pathname.endsWith(`/bootstrap/uploads/${uploadId}/commit`)) {
      commitBody = request.postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, upload: { upload_id: uploadId, state: "committed", size: 18, sha256: "unused", received_bytes: 18 } }),
      });
      return;
    }
    if (pathname.endsWith("/bootstrap/deployments")) {
      deploymentBody = request.postDataJSON();
      deployment = {
        transaction_id: "deploy-1",
        state: "succeeded",
        upload_id: uploadId,
        started_at_epoch_s: 1,
        updated_at_epoch_s: 2,
        error: null,
        result: { result: "PASS" },
      };
      await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ ok: true, deployment }) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false, error: { code: "unexpected_route" } }) });
  });
  await page.route(/fpga|bitstream/i, route => {
    fpgaRequests += 1;
    return route.fulfill({ status: 500, body: "FPGA mutation must not be called" });
  });

  await openRuntimeDeployment(page);

  await expect(page.getByText("bootstrap ready", { exact: true })).toBeVisible();
  await expect(page.getByText("Reserved / Disabled", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /FPGA|bitstream/i })).toHaveCount(0);

  await page.getByLabel("Bootstrap Pairing Token", { exact: true }).fill(token);
  await page.getByRole("button", { name: "Pair Bootstrap", exact: true }).click();
  await expect(page.getByText("Paired", { exact: true })).toBeVisible();
  expect(pairBody).toEqual({ token });

  const kitName = "plasma-z2-ps-kit.tar.gz";
  const kitBytes = Buffer.from("plasma-z2-kit-test");
  const digest = createHash("sha256").update(kitBytes).digest("hex");
  await page.getByLabel("Z2 PS Kit", { exact: true }).setInputFiles({ name: kitName, mimeType: "application/gzip", buffer: kitBytes });
  await page.getByLabel("SHA256 Sidecar", { exact: true }).setInputFiles({
    name: `${kitName}.sha256`,
    mimeType: "text/plain",
    buffer: Buffer.from(`${digest}  ${kitName}\n`),
  });

  await expect(page.getByRole("button", { name: "Deploy Runtime", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Deploy Runtime", exact: true }).click();
  await expect(page.getByText(/Runtime deployment accepted by PPU Bootstrap/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "succeeded", exact: true })).toBeVisible();

  expect(createBody).toEqual({ size: kitBytes.length, sha256: digest });
  expect(chunkBody).not.toBeNull();
  expect(chunkBody?.offset).toBe(0);
  expect(chunkBody?.sha256).toBe(digest);
  expect(Buffer.from(String(chunkBody?.data_base64), "base64")).toEqual(kitBytes);
  expect(commitBody).toEqual({ action: "commit" });
  expect(deploymentBody).toEqual({
    upload_id: uploadId,
    ppu_id: "ppu-a",
    facility_id: "lab",
    display_name: "ppu-a",
  });
  expect(fpgaRequests).toBe(0);
});

test("Runtime Deployment is fail-closed while the selected PPU has active execution", async ({ page }) => {
  await page.route(/\/api\/manager\/registry\/ppu-a\/bootstrap$/, route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(bootstrapStatus(true, null)),
  }));

  await openRuntimeDeployment(page, true);

  await expect(page.getByText(/Runtime deployment is blocked while this PPU has active Site execution/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Deploy Runtime", exact: true })).toBeDisabled();
});
