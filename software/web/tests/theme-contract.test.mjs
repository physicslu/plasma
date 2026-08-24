import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

test("Pmod, Emode and global IC Selector expose one persistent Light Dark theme contract", async () => {
  const themeSwitch = await fs.readFile(new URL("../app/theme-switch.tsx", import.meta.url), "utf8");
  const globalNav = await fs.readFile(new URL("../app/global-nav.tsx", import.meta.url), "utf8");
  const globals = await fs.readFile(new URL("../app/globals.css", import.meta.url), "utf8");
  const productionTheme = await fs.readFile(new URL("../app/fleet/operator-feedback.css", import.meta.url), "utf8");
  const engineering = await fs.readFile(new URL("../app/engineering/engineering.css", import.meta.url), "utf8");

  assert.match(themeSwitch, /THEME_STORAGE_KEY\s*=\s*"plasma-theme"/);
  assert.match(themeSwitch, /data-theme-choice="light"/);
  assert.match(themeSwitch, /data-theme-choice="dark"/);
  assert.match(themeSwitch, /document\.documentElement\.dataset\.theme\s*=\s*theme/);
  assert.match(globalNav, /\(activeMode \|\| devicesActive\)\s*&&\s*<ThemeSwitch/);
  assert.match(globals, /\[data-theme="dark"\]/);
  assert.match(globals, /color-scheme:\s*dark/);
  assert.match(productionTheme, /\[data-theme="dark"\]\s+\.productionPrototypePage/);
  assert.match(productionTheme, /\[data-theme="dark"\]\s+\.productionRuntimeBoard/);
  assert.match(productionTheme, /\[data-theme="dark"\]\s+\.productionSitePrototype\.site-failed/);
  assert.match(engineering, /background:\s*var\(--navy\)/);
  assert.match(engineering, /background:\s*var\(--panel\)/);
});
