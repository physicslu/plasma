"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, useSyncExternalStore, type FormEvent, type MouseEvent } from "react";
import { useI18n } from "../i18n";
import {
  clearSecurityBearerToken,
  getSecurityTransportServerState,
  getSecurityTransportState,
  setSecurityBearerToken,
  subscribeSecurityTransport,
} from "../security-transport";
import {
  getSecurityPrincipal,
  principalHasPermission,
  SecurityProfileError,
  type SecurityPrincipal,
} from "../security-profile";
import { useWorkspaceSession } from "../workspace-session";
import "./demo.css";

type SecurityProfile = "viewer" | "operator" | "engineer" | "admin";

const SECURITY_PROFILES: Array<{
  id: SecurityProfile;
  label: string;
  descriptionZh: string;
  descriptionEn: string;
}> = [
  {
    id: "viewer",
    label: "VIEWER",
    descriptionZh: "唯讀查看狀態、Batch 與 Catalog；不授予 IC 執行權限。",
    descriptionEn: "Read status, Batch and catalog data without IC execution permission.",
  },
  {
    id: "operator",
    label: "OPERATOR",
    descriptionZh: "量產操作角色，可執行允許範圍內的 Erase / Program / Verify / Read。",
    descriptionEn: "Production operator for allowed Erase / Program / Verify / Read scopes.",
  },
  {
    id: "engineer",
    label: "ENGINEER",
    descriptionZh: "包含 Operator 能力，並可使用 Engineering / Mock 工程功能。",
    descriptionEn: "Operator capabilities plus Engineering and Mock engineering functions.",
  },
  {
    id: "admin",
    label: "ADMIN",
    descriptionZh: "完整 Gateway 管理與工程權限，用於初期管理與驗證。",
    descriptionEn: "Full Gateway administration and engineering permissions for initial validation.",
  },
];

function roleSummary(principal: SecurityPrincipal): string {
  return principal.roles.length > 0 ? principal.roles.join(", ") : "custom permissions";
}

export default function DemoLandingPage() {
  const { locale, t } = useI18n();
  const { apiBase, hydrated } = useWorkspaceSession();
  const transport = useSyncExternalStore(
    subscribeSecurityTransport,
    getSecurityTransportState,
    getSecurityTransportServerState,
  );
  const zh = locale === "zh-TW";
  const [selectedProfile, setSelectedProfile] = useState<SecurityProfile | null>(null);
  const [tokenDraft, setTokenDraft] = useState("");
  const [principal, setPrincipal] = useState<SecurityPrincipal | null>(null);
  const [profileChecking, setProfileChecking] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);

  // Probe once for the selected Gateway after hydration. On a canonical
  // non-secure Gateway this is a harmless 404 and the existing landing page is
  // unchanged. On a secure Gateway E4101 activates the security transport.
  // The /demo entry owns credential changes itself, so credentialRevision is
  // intentionally not an effect dependency; this avoids racing the explicit
  // login request with a second identity probe.
  useEffect(() => {
    if (!hydrated) return;
    let active = true;
    void getSecurityPrincipal(apiBase)
      .then(identity => {
        if (!active) return;
        setPrincipal(identity);
        setProfileError(null);
      })
      .catch(error => {
        if (!active) return;
        setPrincipal(null);
        if (error instanceof SecurityProfileError && error.errorCode === "E4101") {
          setProfileError(null);
        } else if (getSecurityTransportState().securityDetected) {
          setProfileError(error instanceof Error ? error.message : "Security profile request failed");
        }
      });
    return () => { active = false; };
  }, [apiBase, hydrated]);

  const selectedMatchesPrincipal = selectedProfile === null
    || principal === null
    || principal.roles.includes(selectedProfile);

  const secureAccessRequired = transport.securityDetected && principal === null;
  const productionDisabled = secureAccessRequired
    || (principal !== null && !principalHasPermission(principal, "status.read"));
  const engineeringDisabled = secureAccessRequired
    || (principal !== null && !principalHasPermission(principal, "engineering.session.write"));
  const devicesDisabled = secureAccessRequired
    || (principal !== null && !principalHasPermission(principal, "catalog.read"));

  const scopeSummary = useMemo(() => {
    if (!principal) return "";
    return principal.scopes.map(scope => {
      const sites = scope.site_ids === "*" ? "*" : scope.site_ids.join(",");
      return `${scope.facility_id} / ${scope.ppu_id} / Sites ${sites}`;
    }).join(" · ");
  }, [principal]);

  async function authenticate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProfile) {
      setProfileError(zh ? "請先選擇預期的 Security Profile。" : "Select the expected Security Profile first.");
      return;
    }
    setProfileChecking(true);
    setProfileError(null);
    setPrincipal(null);
    try {
      setSecurityBearerToken(tokenDraft);
      const identity = await getSecurityPrincipal(apiBase);
      setPrincipal(identity);
      setTokenDraft("");
    } catch (error) {
      clearSecurityBearerToken();
      setProfileError(error instanceof Error ? error.message : "Authentication failed");
    } finally {
      setProfileChecking(false);
    }
  }

  function signOut() {
    clearSecurityBearerToken();
    setPrincipal(null);
    setTokenDraft("");
    setProfileError(null);
  }

  function blockDisabledNavigation(event: MouseEvent<HTMLAnchorElement>, disabled: boolean) {
    if (!disabled) return;
    event.preventDefault();
    event.stopPropagation();
  }

  return (
    <main className="demoLanding" data-route-marker="Choose a Demo">
      <section className="demoHero">
        <div className="demoBrand"><span>P</span><div><b>PLASMA</b><small>PROGRAMMING PLATFORM</small></div></div>
        <p className="demoEyebrow">{t("demo.eyebrow")}</p>
        <h1>{t("demo.title")}</h1>
        <p className="demoLead">{t("demo.lead")}</p>

        {transport.securityDetected && (
          <section className="demoSecurity" aria-label="Plasma Security Profile">
            <div className="demoSecurityHead">
              <div>
                <p>REMOTE WRITE SECURITY</p>
                <h2>{zh ? "選擇測試身份" : "Choose a test profile"}</h2>
                <span>
                  {zh
                    ? "Profile 只代表你預期測試的角色；真正權限永遠由 Bearer Token 對應的 Backend Principal 決定。"
                    : "The profile is only the expected test role. The Bearer token's backend Principal remains the authority."}
                </span>
              </div>
              <strong className={principal ? "ready" : "required"}>
                {principal ? "AUTHENTICATED" : profileChecking ? "CHECKING" : "AUTH REQUIRED"}
              </strong>
            </div>

            <div className="demoProfileGrid" role="radiogroup" aria-label="Expected Security Profile">
              {SECURITY_PROFILES.map(profile => (
                <button
                  key={profile.id}
                  type="button"
                  className={selectedProfile === profile.id ? "selected" : ""}
                  role="radio"
                  aria-checked={selectedProfile === profile.id}
                  onClick={() => setSelectedProfile(profile.id)}
                >
                  <b>{profile.label}</b>
                  <span>{zh ? profile.descriptionZh : profile.descriptionEn}</span>
                </button>
              ))}
            </div>

            {!principal ? (
              <form className="demoCredential" onSubmit={authenticate}>
                <label>
                  Bearer Token
                  <input
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    value={tokenDraft}
                    onChange={event => setTokenDraft(event.target.value)}
                    placeholder={zh ? "貼上測試 Token" : "Paste test token"}
                  />
                </label>
                <button type="submit" disabled={profileChecking || !selectedProfile || !tokenDraft.trim()}>
                  {profileChecking ? (zh ? "驗證中…" : "Checking…") : (zh ? "驗證並進入" : "Authenticate")}
                </button>
              </form>
            ) : (
              <div className="demoPrincipal" role="status">
                <div>
                  <small>PRINCIPAL</small>
                  <b>{principal.id}</b>
                </div>
                <div>
                  <small>ROLE</small>
                  <b>{roleSummary(principal)}</b>
                </div>
                <div className="scope">
                  <small>SCOPE</small>
                  <b>{scopeSummary}</b>
                </div>
                <button type="button" onClick={signOut}>{zh ? "清除身份" : "Clear identity"}</button>
              </div>
            )}

            {!selectedMatchesPrincipal && principal && (
              <div className="demoSecurityWarning" role="alert">
                {zh
                  ? `你選擇 ${selectedProfile?.toUpperCase()}，但 Backend Token 實際驗證為 ${roleSummary(principal)}。系統只採用 Backend 權限。`
                  : `You selected ${selectedProfile?.toUpperCase()}, but the backend authenticated ${roleSummary(principal)}. Only backend permissions are used.`}
              </div>
            )}
            {profileError && <div className="demoSecurityError" role="alert">{profileError}</div>}
          </section>
        )}

        <div className="demoChoices">
          <Link
            className={`demoCard fleet ${productionDisabled ? "disabled" : ""}`}
            href="/fleet"
            aria-disabled={productionDisabled || undefined}
            tabIndex={productionDisabled ? -1 : undefined}
            onClick={event => blockDisabledNavigation(event, productionDisabled)}
          >
            <div className="demoCardHead"><span>01</span><b>{t("mode.production")}</b></div>
            <h2>{t("demo.production.title")}</h2>
            <p>{t("demo.production.description")}</p>
            <strong>{productionDisabled ? (zh ? "需要授權" : "Authentication required") : t("demo.production.open")}</strong>
          </Link>

          <Link
            className={`demoCard ${engineeringDisabled ? "disabled" : ""}`}
            href="/engineering"
            aria-disabled={engineeringDisabled || undefined}
            tabIndex={engineeringDisabled ? -1 : undefined}
            onClick={event => blockDisabledNavigation(event, engineeringDisabled)}
          >
            <div className="demoCardHead"><span>02</span><b>{t("mode.engineering")}</b></div>
            <h2>{t("demo.engineering.title")}</h2>
            <p>{t("demo.engineering.description")}</p>
            <strong>{engineeringDisabled ? (zh ? "目前身份不可進入" : "Not permitted for this identity") : t("demo.engineering.open")}</strong>
          </Link>

          <Link
            className={`demoCard utility ${devicesDisabled ? "disabled" : ""}`}
            href="/devices"
            aria-disabled={devicesDisabled || undefined}
            tabIndex={devicesDisabled ? -1 : undefined}
            onClick={event => blockDisabledNavigation(event, devicesDisabled)}
          >
            <div className="demoCardHead"><span>03</span><b>{zh ? "料號查詢" : "IC LOOKUP"}</b></div>
            <h2>IC Selector</h2>
            <p>
              {zh
                ? "直接輸入 ICPN／IC identifier 查詢 Vendor、Family、OCD mapping 與目前可用的驗證證據。"
                : "Search an ICPN or IC identifier directly for Vendor, Family, OCD mapping, and currently available validation evidence."}
            </p>
            <strong>{devicesDisabled ? (zh ? "目前身份不可查詢" : "Not permitted for this identity") : (zh ? "查詢 IC 料號 →" : "Open IC Selector →")}</strong>
          </Link>
        </div>

        <div className="demoBoundary">
          <b>{t("demo.boundary.title")}</b>
          <span>{t("demo.boundary.description")}</span>
        </div>
      </section>
    </main>
  );
}
