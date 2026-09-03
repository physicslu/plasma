import { expect, test } from "@playwright/test";

const registry = {
  ok: true,
  service: "plasma-manager",
  contract_version: "1",
  mutable: true,
  storage: "file",
  ppus: [
    {
      alias: "ppu-a",
      endpoint: "http://192.168.77.10:18080",
      lifecycle: "commissioned",
      registered_at: "2026-09-03T00:00:00+00:00",
      updated_at: "2026-09-03T00:00:00+00:00",
    },
  ],
};

const fleet = {
  ok: true,
  contract_version: "1",
  observed_at: "2026-09-03T00:00:00+00:00",
  degraded: false,
  summary: {
    configured_ppus: 1,
    reachable_ppus: 1,
    ready_ppus: 1,
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
      alias: "ppu-a",
      identity: {
        ppu_id: "ppu-static-1",
        facility_id: "lab-a",
        model: "PYNQ-Z2",
        display_name: "Static Test PPU",
      },
      transport_state: "reachable",
      execution_state: "ready",
      observation: {
        state: "current",
        last_success_at: "2026-09-03T00:00:00+00:00",
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
            state: "ready",
            current_job_id: null,
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

const network = {
  ok: true,
  rest_contract_version: "3",
  ppu_network_settings: {
    revision: 2,
    interface: "eth0",
    mode: "static",
    address: "192.168.77.21",
    prefix_length: 24,
    gateway: null,
    dns_servers: [],
  },
  activation: {
    supported: true,
    state: "idle",
    committed_revision: 1,
  },
};

const completed = {
  transaction_id: "tx-static-1",
  request_key: "browser-generated",
  request_fingerprint: "f".repeat(64),
  alias: "ppu-a",
  state: "completed",
  old_endpoint: "http://192.168.77.10:18080",
  candidate_endpoint: "http://192.168.77.21:18080",
  ppu_id: "ppu-static-1",
  desired_revision: 2,
  activation_id: "activation-1",
  rollback_timeout_s: 20,
  rollback_deadline_epoch_s: 100,
  started_at: "2026-09-03T00:00:00+00:00",
  updated_at: "2026-09-03T00:00:01+00:00",
  error_code: null,
  error_message: null,
};

test("PPU Network commissions Static IPv4 through the Manager-owned transaction only", async ({ page }) => {
  let commissioningPostCount = 0;
  let directActivationRequests = 0;
  let postedBody: unknown = null;
  let idempotencyKey: string | null = null;
  let commissioningExists = false;

  await page.route(/\/api\/manager\/registry$/, route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(registry),
  }));
  await page.route(/\/api\/fleet$/, route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(fleet),
  }));
  await page.route(/\/api\/manager\/registry\/ppu-a\/network$/, route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(network),
  }));
  await page.route(/\/api\/manager\/registry\/ppu-a\/network-commissioning$/, async route => {
    if (route.request().method() === "GET") {
      if (!commissioningExists) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ ok: false, error: { code: "network_commissioning_not_found", message: "none" } }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, commissioning: completed }),
      });
      return;
    }

    commissioningPostCount += 1;
    commissioningExists = true;
    postedBody = route.request().postDataJSON();
    idempotencyKey = route.request().headers()["idempotency-key"] ?? null;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, commissioning: completed, registry }),
    });
  });
  await page.route(/\/api\/settings\/ppu-network\/activation(?:\/.*)?$/, route => {
    directActivationRequests += 1;
    return route.fulfill({ status: 500, body: "browser must not call PPU activation directly" });
  });

  await page.goto("/engineering");
  await page.getByRole("button", { name: "PPU / Sites", exact: true }).click();

  await expect(page.getByRole("heading", { name: "PPU Network Configuration", exact: true })).toBeVisible();
  const managerTxn = page.locator(".ppuSiteSummary span").filter({ hasText: "Manager Txn" });
  await expect(managerTxn).toContainText("Manager Txn none");
  const commissionButton = page.getByRole("button", { name: "Commission Static Network", exact: true });
  await expect(commissionButton).toBeEnabled();
  await commissionButton.click();

  await expect(page.getByText(/Static IPv4 commissioning completed/)).toBeVisible();
  await expect(page.getByText(/candidate Plasma Gateway Endpoint/)).toContainText("192.168.77.21:18080");
  expect(commissioningPostCount).toBe(1);
  expect(directActivationRequests).toBe(0);
  expect(idempotencyKey).toMatch(/^ppu-network-commissioning-/);
  expect(postedBody).toEqual({
    desired: {
      mode: "static",
      address: "192.168.77.21",
      prefix_length: 24,
      gateway: null,
      dns_servers: [],
    },
    rollback_timeout_s: 20,
  });
});

test("Static commissioning stays fail-closed when the PPU has no activation helper", async ({ page }) => {
  await page.route(/\/api\/manager\/registry$/, route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(registry),
  }));
  await page.route(/\/api\/fleet$/, route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(fleet),
  }));
  await page.route(/\/api\/manager\/registry\/ppu-a\/network$/, route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      ...network,
      activation: { supported: false, state: "not_implemented", committed_revision: null },
    }),
  }));
  await page.route(/\/api\/manager\/registry\/ppu-a\/network-commissioning$/, route => route.fulfill({
    status: 404,
    contentType: "application/json",
    body: JSON.stringify({ ok: false, error: { code: "network_commissioning_not_found", message: "none" } }),
  }));

  await page.goto("/engineering");
  await page.getByRole("button", { name: "PPU / Sites", exact: true }).click();

  await expect(page.getByText(/Commissioning unavailable:/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Commission Static Network", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Save Desired Network", exact: true })).toBeDisabled();
});
