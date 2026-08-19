"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useI18n } from "./i18n";
import { PRODUCT_MODE_ROUTES, productModeForPath } from "./product-mode";

export function GlobalNav() {
  const pathname = usePathname();
  const { locale, setLocale, t } = useI18n();
  const activeMode = productModeForPath(pathname);
  const entryActive = pathname === "/demo";

  return (
    <header className="globalAppNav">
      <Link className="globalAppNavBrand" href="/demo" aria-label="Plasma demo entry">
        <span>P</span>
        <b>PLASMA</b>
      </Link>

      <div className="globalNavControls">
        <nav className="globalProductNav" aria-label={t("mode.label")}>
          <Link href="/demo" aria-current={entryActive ? "page" : undefined}>
            {t("nav.entry")}
          </Link>
          <Link href={PRODUCT_MODE_ROUTES.production} aria-current={activeMode === "production" ? "page" : undefined}>
            {t("mode.production")}
          </Link>
          <Link href={PRODUCT_MODE_ROUTES.engineering} aria-current={activeMode === "engineering" ? "page" : undefined}>
            {t("mode.engineering")}
          </Link>
        </nav>

        <div className="globalLocale" role="group" aria-label="Language">
          <button type="button" onClick={() => setLocale("zh-TW")} aria-pressed={locale === "zh-TW"}>{t("locale.zh")}</button>
          <button type="button" onClick={() => setLocale("en-US")} aria-pressed={locale === "en-US"}>{t("locale.en")}</button>
        </div>
      </div>
    </header>
  );
}
