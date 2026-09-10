# Engineering Operator UI Design System

**Status: Current**

本文件定義 EMode operator surfaces 的共用 UI contract。目標不是讓不同頁面「看起來差不多」，而是讓它們在共同 presentation 與 interaction primitive 上只有一個 owner，同時保留 Settings、Diagnostics、PPU/Site 各自的 workflow 與 domain semantics。

## 1. Ownership

跨 Settings / Diagnostics / PPU-Site 共用的 React component primitives：

- `software/web/app/operator-ui/operator-surface.tsx`

跨 operator surfaces 共用的 card、field、input/select 與 primary/secondary action presentation owner：

- `software/web/app/operator-ui/operator-surface-primitives.css`

Settings composition 的 canonical implementation：

- `software/web/app/operator-ui/settings-ui.tsx`
- `software/web/app/operator-ui/settings-ui.css`

`settings-ui.tsx` 可以保留 Settings-specific API，例如 `SettingsPage`、`SettingsGrid`、`SettingsGuide` 與 revision presentation，但 common card / field / action / message structure 必須委派給 `operator-surface.tsx`，不能再建立第二套實作。

Diagnostics 與 PPU/Site 也可以保留自己的 domain composition。Loopback path、PPU state dimensions、Site reconciliation、table layout 等都不是 generic operator component 的責任；只有真正跨 domain 重複的 presentation/interaction primitive 才進入 shared owner。

## 2. Shared React primitives

`operator-surface.tsx` 目前提供窄幅、可組合的共用元件：

- `OperatorCard`：共同 Card semantic container 與 shared visual class。
- `OperatorField`：label、control、unit、hint 的共同 field 結構。
- `OperatorActions`：operator action group 的共同容器。
- `OperatorButton`：secondary / primary / danger action 的共同 button contract。
- `OperatorMessage`：error / success / info / warning message 的共同 semantic wrapper。

這些 primitives 不知道 Gateway、Mock、Loopback、PPU、Site、`desired_revision`、`If-Match`、runtime reconciliation 或 hardware topology。若 shared primitive 開始承載這些 domain nouns，代表 abstraction boundary 已經過寬，應回退到 domain component。

目前 adoption：

- Settings：`SettingsCard`、`SettingsField`、`SettingsActions`、`SettingsMessage` 委派到 operator primitives；Settings-specific composition API 對既有 caller 保持穩定。
- Diagnostics：`DiagnosticsTestCard` 委派到 `OperatorCard`；Loopback-specific controls/path/result logic 保持在 diagnostics domain。
- PPU/Site：Programming Site Desired configuration 的 Card、action group、buttons 與 messages 使用 operator primitives；Draft / Desired / Runtime、CAS conflict、reconciliation 與 table semantics 保持在 PPU/Site domain。

這是 intentional incremental migration。PPU Registry / Network 等既有 surface 可以繼續使用 compatibility visual classes，但新增或重構共同 interaction 時應優先採用 operator primitives，而不是複製 markup/CSS。

## 3. Settings composition primitives

Settings-specific composition 仍由 `settings-ui.tsx` 擁有：

- `SettingsPage`：頁面標題、subtitle、revision badge 與頁面寬度。
- `SettingsTabs`：只有在同一個 Settings surface 真的存在兩個以上可切換分類時才使用；不得為單一分類建立裝飾性 tab。
- `SettingsCard`：Settings-facing adapter，底層使用 `OperatorCard`。
- `SettingsGrid`：1–4 欄 responsive settings layout。
- `SettingsField`：Settings-facing adapter，底層使用 `OperatorField`。
- `SettingsActions`：Settings-facing adapter，底層使用 `OperatorActions`。
- `SettingsMessage`：Settings-facing adapter，底層使用 `OperatorMessage`。
- `SettingsMetaGrid`：server-authoritative revision/profile/seed 等摘要。
- `SettingsGuide`：Operator Guide、測試方法、顯式 `1：2：3：` 號次與 caution。

Gateway Settings 與 Mock Settings 必須使用 shared Settings UI。未來新增 Engineering Settings surface 也必須優先使用這些 primitives，不得自行複製一套 Card、Field、Action、Revision badge 或 Operator Guide 樣式。

## 4. Canonical visual contract

目前共同 operator surface 以 Loopback Test 的 control density 為基準：

- 10 px radius 的主要 operator Card；
- shared Field label 使用 10 px、750 weight；
- input / select 使用 36 px minimum control height、6 px radius、11 px monospaced control text；
- primary / secondary action 使用 38 px minimum action height、6 px radius、11 px sans action text；
- primary action 使用 shared cyan treatment；
- danger action 使用 shared red treatment；
- disabled action 只改變 state treatment，不改變 geometry；
- common Card / Field / Action presentation 由 `operator-surface-primitives.css` 管理。

`operatorCard` / `operatorField` / `operatorButton` 是新的 generic visual selectors。既有 `.settingsCard`、`.diagnosticsTestCard`、`.ppuSiteCard`、`.settingsActions button`、`.loopbackExecutionActions button`、`.ppuSiteButton` 仍可在 migration 期間由同一個 CSS owner 維持相同 geometry；不得在 mode-local stylesheet 再複製這些 shared geometry。

Settings 自己仍保留 composition responsibility：

- top-aligned settings canvas；
- page header 承擔 eyebrow、title、subtitle 與 revision；
- `SettingsGrid` 決定 1–4 column responsive layout；
- Settings Card 內部 spacing；
- revision badge；
- 14 px / 1.7 line-height Operator Guide body、numbering、caution 與 responsive layout。

## 5. Domain-specific CSS boundary

Local stylesheet 只允許描述該 domain 本身無法由 shared primitives 表達的結構。例如 Mock 可保留：

- E/P/V/R operation table layout；
- operation table column / row formatting；
- loading / fatal-load error placeholder。

Loopback 可保留：

- path node / segment；
- payload length mode selector；
- number field unit composition；
- results table / result badge；
- Loopback-specific responsive layout。

PPU/Site 可保留：

- Lifecycle / Connectivity / Health dimension presentation；
- readiness / validation detail；
- Site topology table；
- Draft / Desired / Runtime reconciliation flow；
- conflict / dirty badges；
- PPU Network and registry-specific composition。

Local stylesheet 不應重新定義：

- common operator Card border / background / radius / shadow；
- shared field label / input / select geometry；
- shared primary / secondary action geometry；
- Settings page header / revision badge；
- Applied Configuration meta cards；
- Operator Guide layout / typography / numbering / caution。

若 shared primitives 無法支援新的合理需求，先擴充 shared owner，再讓新頁面使用。不要在單頁建立永久 override，也不要為了「統一」而把 domain workflow 搬進 generic component。

## 6. Runtime ownership is unchanged

UI 共用只處理 presentation 與 interaction pattern，不改變設定資料 ownership：

- Gateway communication settings 仍由 Gateway server 保存，Batch START 時凍結 communication policy revision。
- Mock Runtime settings 仍由 Gateway server 保存，Batch START 時凍結 Profile revision 與 resolved seed。
- PPU Site Desired configuration 仍由 PPU canonical configuration 保存，CAS / `If-Match` ownership 不變。
- UI draft 不等於 server source of truth；只有成功 Apply / Save 後的 server response 才是 authoritative Desired state。
- Site Desired → Runtime activation 仍是後續 capability；本 design-system work 不新增 restart / hot-apply semantics。

## 7. Validation contract

變更 Settings / Diagnostics / PPU-Site 共用 UI 時至少執行：

1. Web lint。
2. Build + source/SSR tests。
3. Playwright E2E。
4. 受影響的 Runtime Acceptance（若相關 workflow 被觸發）。

Source contract 必須驗證：

- `operator-surface.tsx` 保持 domain-neutral；
- Settings adapter components 委派到 operator primitives；
- Diagnostics 與至少一個 PPU/Site operational surface 實際消費 shared component primitives；
- Settings、Loopback 與 PPU/Site 都由同一個 `operator-surface-primitives.css` owner 維持 common geometry；
- shared input/select 維持 36 px minimum height、6 px radius、11 px monospaced text；
- shared action 維持 38 px minimum height、6 px radius、11 px action text；
- Settings Guide、revision 與 Settings-specific responsive composition 仍由 Settings UI ownership 管理；
- UI component reuse 不得改變 Site CAS、runtime boundary 或 hardware evidence boundary。

相關 source regression：

- `software/web/tests/settings-ui-design-system-contract.test.mjs`
- `software/web/tests/operator-surface-component-contract.test.mjs`
- `software/web/tests/diagnostics-loopback-contract.test.mjs`
- Site Desired CAS / UI contract tests。

Browser regression 應比較 Gateway / Mock / Loopback / PPU-Site 的 shared Card 與 action computed style，避免「source 看似共用、實際 geometry 已漂移」的 regression。

## 8. Review rule

新增或修改 Engineering Settings / Diagnostics / PPU-Site page 時，review 應先回答：

> 這個 UI 是跨 operator surface 的共同 interaction/presentation、Settings composition，還是 domain-specific requirement？

- common React structure → `operator-ui/operator-surface.tsx`；
- common Card / Field / Action presentation → `operator-ui/operator-surface-primitives.css`；
- Settings composition / guide / revision → `operator-ui/settings-ui.*`；
- domain-specific layout / workflow → 對應頁面的 local component 與 stylesheet。

不要讓同一層 presentation 同時存在兩個 owner，也不要把 domain semantics 搬進 generic design-system layer。
