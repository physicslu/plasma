import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const entry = readFileSync(new URL("../app/demo/page.tsx", import.meta.url), "utf8");
const profile = readFileSync(new URL("../app/security-profile.ts", import.meta.url), "utf8");
const transport = readFileSync(new URL("../app/security-transport.ts", import.meta.url), "utf8");


test("entry exposes the four expected test profiles without making them authority", () => {
  for (const role of ["viewer", "operator", "engineer", "admin"]) {
    assert.match(entry, new RegExp(`id: "${role}"`));
  }
  assert.match(entry, /Backend Principal/);
  assert.match(entry, /principal\.roles\.includes\(selectedProfile\)/);
  assert.doesNotMatch(entry, /localStorage\.setItem\([^\n]*(?:profile|role|token)/i);
});


test("security identity is fetched from the authenticated backend boundary", () => {
  assert.match(profile, /\/api\/security\/me/);
  assert.match(transport, /"\/api\/security"/);
  assert.match(entry, /getSecurityPrincipal\(apiBase\)/);
  assert.match(entry, /setSecurityBearerToken\(tokenDraft\)/);
});


test("entry navigation derives capability from backend permissions", () => {
  assert.match(entry, /principalHasPermission\(principal, "status\.read"\)/);
  assert.match(entry, /principalHasPermission\(principal, "engineering\.session\.write"\)/);
  assert.match(entry, /principalHasPermission\(principal, "catalog\.read"\)/);
});
