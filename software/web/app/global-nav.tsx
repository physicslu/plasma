"use client";

import { useSyncExternalStore, type MouseEvent } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useI18n } from "./i18n";
import {
  getPpuExecutionActivityCount,
  subscribePpuExecutionActivity,
} from "./plasma-api";
import {
  getBatchExecutionActivityCount,
  subscribeBatchExecutionActivity,
} from "./batch-execution-activity";
import { PRODUCT_MODE_ROUTES, productModeForPath } from "./product-mode";
import ThemeSwitch from "./theme-switch";

function subscribeHydration(): () => void {
  return () => {};
}

export function GlobalNav() {
  const pathname = usePathname();
  const { locale, setLocale, t } = useI18n();
  const hydrated = useSyncExternalStore(subscribeHydration, () => true, () => false);
  const ppuExecutionCount = useSyncExternalStore(
    subscribePpuExecutionActivity,
    getPpuExecutionActivityCount,
    () => 0,
  );
  const batchExecutionCount = useSyncExternalStore(
    subscribeBatchExecutionActivity,
    getBatchExecutionActivityCount,
    () => 0,
  );
  const executionCount = ppuExecutionCount + batchExecutionCount;

  // Render is a client-routed Vite shell. After hydration the browser URL is
  // authoritative even if a framework pathname adapter is temporarily stale.
  // Keep SSR on the framework pathname, then converge on window.location.
  const routePath = hydrated && typeof window !== "undefined" ? window.location.pathname : pathname;
  const activeMode = productModeForPath(routePath);
  const entryActive = routePath === "/demo";
  const devicesActive = routePath === "/devices" || routePath.startsWith("/devices/");
  const navigationLocked = Boolean(activeMode) && executionCount > 0;
  const productionLocked = navigationLocked && activeMode !== "production";
  const engineeringLocked = navigationLocked && activeMode !== "engineering";
  const lockReason = locale === "zh-TW"
    ? "PPU / Batch 執行中，完成或取消後才可切換模式。"
    : "Mode switching is locked while PPU jobs or a server Batch are active.";

  function blockLockedNavigation(event: MouseEvent<HTMLAnchorElement>, locked: boolean) {
    if (!locked) return;
    event.preventDefault();
    event.stopPropagation();
  }

  return (
    <header className="globalAppNav">
      <Link
        className="globalAppNavBrand"
        href="/demo"
        aria-label="Plasma demo entry"
        aria-disabled={navigationLocked || undefined}
        tabIndex={navigationLocked ? -1 : undefined}
        title={navigationLocked ? lockReason : undefined}
        onClick={event => blockLockedNavigation(event, navigationLocked)}
      >
        <span>P</span>
        <b>PLASMA</b>
      </Link>

      <div className="globalNavControls">
        <nav className="globalProductNav" aria-label={t("mode.label")}>
          <Link
            href="/demo"
            aria-current={entryActive ? "page" : undefined}
            aria-disabled={navigationLocked || undefined}
            tabIndex={navigationLocked ? -1 : undefined}
            title={navigationLocked ? lockReason : undefined}
            onClick={event => blockLockedNavigation(event, navigationLocked)}
          >
            {t("nav.entry")}
          </Link>
          <Link
            href={PRODUCT_MODE_ROUTES.production}
            aria-current={activeMode === "production" ? "page" : undefined}
            aria-disabled={productionLocked || undefined}
            tabIndex={productionLocked ? -1 : undefined}
            title={productionLocked ? lockReason : undefined}
            onClick={event => blockLockedNavigation(event, productionLocked)}
          >
            {t("mode.production")}
          </Link>
          <Link
            href={PRODUCT_MODE_ROUTES.engineering}
            aria-current={activeMode === "engineering" ? "page" : undefined}
            aria-disabled={engineeringLocked || undefined}
            tabIndex={engineeringLocked ? -1 : undefined}
            title={engineeringLocked ? lockReason : undefined}
            onClick={event => blockLockedNavigation(event, engineeringLocked)}
          >
            {t("mode.engineering")}
          </Link>
        </nav>

        {navigationLocked && (
          <span className="globalExecutionGuard" role="status" aria-live="polite" title={lockReason}>
            EXECUTION BUSY · {executionCount}
          </span>
        )}

        {(activeMode || devicesActive) && <ThemeSwitch className="globalThemeSwitch" />}

        <div className="globalLocale" role="group" aria-label="Language" aria-busy={!hydrated}>
          <button type="button" disabled={!hydrated} onClick={() => setLocale("zh-TW")} aria-pressed={locale === "zh-TW"}>{t("locale.zh")}</button>
          <button type="button" disabled={!hydrated} onClick={() => setLocale("en-US")} aria-pressed={locale === "en-US"}>{t("locale.en")}</button>
        </div>
      </div>
    </header>
  );
}
