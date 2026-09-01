# Engineering Settings UI Design System

**Status: Current**

本文件定義 EMode 設定頁的共用 UI contract。目標不是讓不同設定頁「看起來差不多」，而是讓它們使用同一組 component、同一份 visual ownership 與同一套 operator interaction pattern。

## 1. Ownership

Settings composition 的 canonical implementation：

- `software/web/app/operator-ui/settings-ui.tsx`
- `software/web/app/operator-ui/settings-ui.css`

跨 Settings / Diagnostics 共用的 card、field、input/select 與 primary/secondary action presentation owner：

- `software/web/app/operator-ui/operator-surface-primitives.css`

Gateway Settings 與 Mock Settings 必須使用 shared Settings UI。未來新增的 Engineering Settings surface 也必須優先使用這些 primitives，不得自行複製一套 Card、Field、Action、Revision badge 或 Operator Guide 樣式。

Loopback Test 是目前 operator control density 的 visual reference。Settings 與 Diagnostics 可以有不同 workflow composition，但共同的 Card chrome、Field typography、Input/Select geometry 與 Action button geometry 必須由 `operator-surface-primitives.css` 統一擁有，不能各自在 `settings-ui.css`、`loopback-test.css` 或其他 mode-local stylesheet 重新定義。

## 2. Shared primitives

Settings composition primitives：

- `SettingsPage`：頁面標題、subtitle、revision badge 與頁面寬度。
- `SettingsTabs`：只有在同一個 Settings surface 真的存在兩個以上可切換分類時才使用；不得為單一分類建立裝飾性 tab。
- `SettingsCard`：設定區塊與 server-authoritative summary 的共同容器。
- `SettingsGrid`：1–4 欄 responsive settings layout。
- `SettingsField`：label、control、unit、hint。
- `SettingsActions`：Apply / Cancel 等 operator action group。
- `SettingsMessage`：error / success / info 狀態。
- `SettingsMetaGrid`：server-authoritative revision/profile/seed 等摘要。
- `SettingsGuide`：Operator Guide、測試方法、顯式 `1：2：3：` 號次與 caution。

Shared operator surface presentation：

- Settings Card 與 Diagnostics Card 共用 border / background / radius / shadow。
- Settings Field 與 Diagnostics Field 共用 label、input/select 與 helper text density。
- Settings Actions 與 Loopback execution actions 共用 secondary / primary / disabled / hover treatment。

## 3. Canonical visual contract

目前共同 operator surface 以 Loopback Test 的 control density 為基準：

- 10 px radius 的主要 operator Card；
- shared Field label 使用 10 px、750 weight；
- input / select 使用 36 px minimum control height、6 px radius、11 px monospaced control text；
- primary / secondary action 使用 38 px minimum action height、6 px radius、11 px sans action text；
- primary action 使用 shared cyan treatment；
- disabled action 只改變 state treatment，不改變 geometry；
- common Card / Field / Action presentation 由 `operator-surface-primitives.css` 管理。

Settings 自己仍保留 composition responsibility：

- top-aligned settings canvas；
- page header 承擔 eyebrow、title、subtitle 與 revision；
- `SettingsGrid` 決定 1–4 column responsive layout；
- Settings Card 內部 spacing；
- revision badge；
- 14 px / 1.7 line-height Operator Guide body、numbering、caution 與 responsive layout。

Gateway 與 Mock 不得再透過 mode-local CSS 覆寫共同 Card / Field / Action 屬性。Loopback 只保留 path、length-mode、results table 等 diagnostics domain-specific presentation。

## 4. Domain-specific CSS boundary

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

Local stylesheet 不應重新定義：

- common operator Card border / background / radius / shadow；
- shared field label / input / select geometry；
- shared primary / secondary action geometry；
- Settings page header / revision badge；
- Applied Configuration meta cards；
- Operator Guide layout / typography / numbering / caution。

若 shared primitives 無法支援新的合理需求，先擴充 shared owner，再讓新頁面使用，不要在單頁建立永久 override。

## 5. Runtime ownership is unchanged

UI 共用只處理 presentation 與 interaction pattern，不改變設定資料 ownership：

- Gateway communication settings 仍由 Gateway server 保存，Batch START 時凍結 communication policy revision。
- Mock Runtime settings 仍由 Gateway server 保存，Batch START 時凍結 Profile revision 與 resolved seed。
- UI draft 不等於 server source of truth；只有成功 Apply 後的 server response 才是 authoritative state。

## 6. Validation contract

變更 Settings / Diagnostics 共用 UI 時至少執行：

1. Web lint。
2. Build + source/SSR tests。
3. Playwright E2E。
4. 受影響的 Runtime Acceptance（若相關 workflow 被觸發）。

Source contract 必須驗證：

- Settings 與 Loopback 都載入同一個 `operator-surface-primitives.css` owner；
- common Card / Field / Action geometry 不再存在於 mode-local stylesheet；
- shared input/select 維持 36 px minimum height、6 px radius、11 px monospaced text；
- shared action 維持 38 px minimum height、6 px radius、11 px action text；
- Settings Guide、revision 與 Settings-specific responsive composition 仍由 Settings UI ownership 管理。

Browser regression 應比較 Gateway / Mock / Loopback 的 shared Card、Field 與 primary action computed style，避免「source 看似共用、實際 geometry 已漂移」的 regression。

## 7. Review rule

新增或修改 Engineering Settings / Diagnostics page 時，review 應先回答：

> 這個 UI 是跨 operator surface 的共同 presentation、Settings composition，還是 domain-specific requirement？

- common Card / Field / Action presentation → `operator-ui/operator-surface-primitives.css`；
- Settings composition / guide / revision → `operator-ui/settings-ui.*`；
- domain-specific layout → 對應頁面的 local stylesheet。

不要讓同一層 presentation 同時存在兩個 owner。
