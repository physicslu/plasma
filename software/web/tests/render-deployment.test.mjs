import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("Render build uses the canonical standalone Control Station runtime", async () => {
  const build = await readFile(new URL("../../../scripts/render-build.sh", import.meta.url), "utf8");

  assert.match(build, /npm run build:product/);
  assert.match(build, /dist\/standalone\/server\.js/);
  assert.doesNotMatch(build, /npm run build:render/);
  assert.doesNotMatch(build, /dist-render/);
});

test("public Render demo composes Console BFF -> Manager -> loopback Mock PPU Gateway", async () => {
  const start = await readFile(new URL("../../../scripts/render-start.sh", import.meta.url), "utf8");

  assert.match(start, /python -m plasma_server\.server/);
  assert.match(start, /-m plasma_web\.gateway/);
  assert.match(start, /--host 127\.0\.0\.1/);
  assert.match(start, /python -m plasma_manager\.server/);
  assert.match(start, /PLASMA_CONTROL_STATION_MODE="managed"/);
  assert.match(start, /PLASMA_MANAGER_API_URL="http:\/\/127\.0\.0\.1:/);
  assert.match(start, /PLASMA_MANAGER_PPU_ALIAS="\$\{ppu_alias\}"/);
  assert.match(start, /HOST="0\.0\.0\.0"/);
  assert.match(start, /node "\$\{console_root\}\/server\.js"/);
  assert.doesNotMatch(start, /--static-root/);
  assert.doesNotMatch(start, /dist-render/);
});

test("deployment identity is explicit opt-in metadata on the product BFF", async () => {
  const route = await readFile(new URL("../app/deployment.json/route.ts", import.meta.url), "utf8");

  assert.match(route, /PLASMA_DEPLOYMENT_IDENTITY_ENABLED/);
  assert.match(route, /PLASMA_DEPLOYMENT_IDENTITY_SERVICE/);
  assert.match(route, /RENDER_GIT_COMMIT/);
  assert.match(route, /RENDER_GIT_BRANCH/);
  assert.match(route, /Cache-Control.*no-store/s);
  assert.match(route, /status: 404/);
});
