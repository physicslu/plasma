"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useI18n } from "./i18n";

const scopeItems = [
  { href: "/demo", labelKey: "nav.entry" },
  { href: "/ppu", labelKey: "nav.singlePpu" },
  { href: "/fleet", labelKey: "nav.fleet" },
] as const;

function isScopeActive(pathname: string, href: string): boolean {
  if (href === "/ppu") return pathname === "/" || pathname === "/ppu" || pathname.startsWith("/ppu/");
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function GlobalNav() {
  const pathname = usePathname();
  const { locale, setLocale, t } = useI18n();
  const productionActive = pathname === "/fleet" || pathname.startsWith("/fleet/");
  const engineeringActive = pathname === "/engineering" || pathname.startsWith("/engineering/");

  return (
    <header className="globalAppNav">
      <Link className="globalAppNavBrand" href="/demo" aria-label="Plasma demo entry">
        <span>P</span>
        <b>PLASMA</b>
      </Link>

      <div className="globalNavControls">
        <nav className="globalScopeNav" aria-label="Plasma scope navigation">
          {scopeItems.map(item => {
            const active = isScopeActive(pathname, item.href);
            return (
              <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined}>
                {t(item.labelKey)}
              </Link>
            );
          })}
        </nav>

        <nav className="globalModeNav" aria-label={t("mode.label")}>
          <Link href="/fleet" aria-current={productionActive ? "page" : undefined}>
            {t("mode.production")}
          </Link>
          <Link href="/engineering" aria-current={engineeringActive ? "page" : undefined}>
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
