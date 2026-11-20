import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

test("Pmod, Emode and global IC Selector expose one persistent Light Dark theme contract", async () => {
  const themeSwitch = await fs.readFile(new URL("../app/theme-switch.tsx", import.meta.url), "utf8");
  const globalNav = await fs.readFile(new URL("../app/global-nav.tsx", import.meta.url), "utf8");
  const globals = await fs.readFile(new URL("../app/globals.css", import.meta.url), "utf8");
  const productionFactory = await fs.readFile(new URL("../app/fleet/factory-console-v2.css", import.meta.url), "utf8");
  const engineering = await fs.readFile(new URL("../app/engineering/engineering.css", import.meta.url), "utf8");
  const engineeringProgramming = await fs.readFile(new URL("../app/engineering/programming-workspace-v2.css", import.meta.url), "utf8");

  assert.match(themeSwitch, /THEME_STORAGE_KEY\s*=\s*"plasma-theme"/);
  assert.match(themeSwitch, /data-theme-choice="light"/);
  assert.match(themeSwitch, /data-theme-choice="dark"/);
  assert.match(themeSwitch, /document\.documentElement\.dataset\.theme\s*=\s*theme/);
  assert.match(globalNav, /window\.location\.pathname/);
  assert.match(globalNav, /const devicesActive = routePath === "\/devices" \|\| routePath\.startsWith\("\/devices\/"\)/);
  assert.match(globalNav, /\(activeMode \|\| devicesActive\)\s*&&\s*<ThemeSwitch/);
  assert.doesNotMatch(globalNav, /pmod-theme\.css/);
  assert.match(globals, /\[data-theme="dark"\]/);
  assert.match(globals, /color-scheme:\s*dark/);
  assert.match(productionFactory, /\[data-theme="dark"\]\s+\.factoryConsoleV2\s*\{/);
  assert.match(productionFactory, /\[data-theme="dark"\][\s\S]*\.factorySiteLedCard\.state-faulted/);
  assert.match(productionFactory, /\[data-theme="dark"\][\s\S]*\.factoryConsoleV2 \.operatorPanel/);
  assert.match(engineering, /background:\s*var\(--navy\)/);
  assert.match(engineering, /background:\s*var\(--panel\)/);
  assert.match(engineeringProgramming, /\.engineeringProgrammingV2Header \.engineeringGateway input\s*\{[^}]*color:\s*var\(--text,/s);
  assert.match(engineeringProgramming, /\.engineeringProgrammingV2Header \.engineeringGateway > b\s*\{[^}]*color:\s*var\(--text,/s);
  assert.match(engineeringProgramming, /\.engineeringProgrammingV2Header \.engineeringGateway input:disabled\s*\{[^}]*opacity:\s*1/s);
});

test("IC Management fields use theme tokens and never fall back to dark surfaces in light mode", async () => {
  const css = await fs.readFile(new URL("../app/ic-management/style.css", import.meta.url), "utf8");
  const globalCss = await fs.readFile(new URL("../app/globals.css", import.meta.url), "utf8");
  const controls = css.match(/\.icManagement input,\.icManagement textarea,\.icManagement select\s*\{([^}]*)\}/)?.[1];
  assert.ok(controls, "shared IC Management input, textarea and select rule must exist");
  assert.match(controls, /background:\s*var\(--panel-2\)/);
  assert.match(controls, /color:\s*var\(--text\)/);
  assert.match(controls, /caret-color:\s*var\(--text\)/);
  assert.doesNotMatch(controls, /var\(--surface|background:\s*#[\da-f]+/i);
  assert.match(css, /\.icManagement input::placeholder,\.icManagement textarea::placeholder\s*\{[^}]*color:\s*var\(--muted\);[^}]*opacity:\s*1/s);
  for (const rule of [
    globalCss.match(/:root\s*\{([^}]*)\}/)?.[1],
    globalCss.match(/\[data-theme="dark"\]\s*\{([^}]*)\}/)?.[1],
  ]) {
    assert.ok(rule, "both Light and Dark palettes must exist");
    for (const token of ["--panel-2", "--text", "--muted"]) {
      assert.match(rule, new RegExp(`\\b${token}:\\s*#[0-9a-f]{3,8}`, "i"));
    }
  }
});
