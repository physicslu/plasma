# Engineering Settings UI Design System

**Status: Current**

本文件定義 EMode 設定頁的共用 UI contract。目標不是讓不同設定頁「看起來差不多」，而是讓它們使用同一組 component、同一份 visual token 與同一套 operator interaction pattern。

## 1. Ownership

Canonical implementation：

- `software/web/app/operator-ui/settings-ui.tsx`
- `software/web/app/operator-ui/settings-ui.css`

Gateway Settings 與 Mock Settings 必須使用這套 shared Settings UI。未來新增的 Engineering Settings surface 也必須優先使用這些 primitives，不得自行複製一套 Card、Field、Action、Revision badge 或 Operator Guide 樣式。

Mock Settings 是目前批准的 **visual reference surface**。它不是另一套 CSS ownership；實際 canonical implementation 仍在 shared Settings UI。Gateway 與其他 EMode Settings 頁面應以 Mock 的 control density、page composition 與 operator hierarchy 為基準，透過 shared primitives 實現。

## 2. Shared primitives

目前共用 primitives：

- `SettingsPage`：頁面標題、subtitle、revision badge 與頁面寬度。
- `SettingsTabs`：只有在同一個 Settings surface 真的存在兩個以上可切換分類時才使用；不得為單一分類建立裝飾性 tab。
- `SettingsCard`：設定區塊與 server-authoritative summary 的共同容器。
- `SettingsGrid`：1–4 欄 responsive settings layout。
- `SettingsField`：label、control、unit、hint。
- `SettingsActions`：Apply / Reset 等 operator action。
- `SettingsMessage`：error / success / info 狀態。
- `SettingsMetaGrid`：server-authoritative revision/profile/seed 等摘要。
- `SettingsGuide`：Operator Guide、測試方法、顯式 `1：2：3：` 號次與 caution。

## 3. Canonical visual contract

目前 Mock Settings 的批准視覺語言是 shared Settings UI 的 reference，包含：

- top-aligned settings canvas；
- page header 承擔 eyebrow、title、subtitle 與 revision，主要 control card 不重複一層 page title；
- 10 px radius 的主要 Settings Card；
- 22 px card padding；
- 桌面版基準 control row 使用 3-column density；Gateway 即使只有兩個欄位，也沿用同一欄寬節奏，而不是把兩個 input 拉滿整張卡；
- 13 px field label；
- input / select 使用 40 px 固定 control height、7 px radius、14 px monospaced control text；
- Apply / Reset 使用 40 px canonical action height、7 px radius、14 px action text；
- disabled action 只改變 state treatment，不改變 control geometry；
- 14 px / 1.7 line-height Operator Guide body；
- primary action 使用 shared cyan treatment；
- revision badge、guide、caution、responsive breakpoints 全由 shared stylesheet 管理。

Gateway 與 Mock 不得再透過 mode-local CSS 覆寫這些共同屬性。Gateway 不再保留只有單一 `Gateway` 項目的 Settings tab，避免同一 Design System 出現不同 page composition。

## 4. Domain-specific CSS boundary

Local stylesheet 只允許描述該設定 domain 本身無法由 shared primitives 表達的結構。例如 Mock 可保留：

- E/P/V/R operation table layout；
- operation table column / row formatting；
- loading / fatal-load error placeholder。

Local stylesheet 不應重新定義：

- Settings page header；
- revision badge；
- Settings Card border / background / radius / padding；
- field label / input / select；
- Apply / Reset button；
- Applied Configuration meta cards；
- Operator Guide layout / typography / numbering / caution。

若 shared primitives 無法支援新的合理需求，先擴充 shared Settings UI，再讓新頁面使用，不要在單頁建立永久 override。

## 5. Runtime ownership is unchanged

Settings UI 共用只處理 presentation 與 interaction pattern，不改變設定資料 ownership：

- Gateway communication settings 仍由 Gateway server 保存，Batch START 時凍結 communication policy revision。
- Mock Runtime settings 仍由 Gateway server 保存，Batch START 時凍結 Profile revision 與 resolved seed。
- UI draft 不等於 server source of truth；只有成功 Apply 後的 server response 才是 authoritative state。

## 6. Validation contract

變更 Settings UI 時至少執行：

1. Web lint。
2. Build + source/SSR tests。
3. Playwright E2E。
4. Mock CD Browser Runtime Acceptance（若相關 workflow 被觸發）。

Browser regression 必須至少驗證 Gateway / Mock 的 shared Card、Guide、primary action 與 Field computed style 一致，並額外比較 input/select 與 primary action 的實際高度，避免「CSS property 名義共用、實際 control geometry 已漂移」的 regression。Field column density 由各 surface 使用 shared `SettingsGrid` 的 source contract 保護；Card / Guide 高度與實際欄寬可因 domain content 與可用畫布寬度不同，不應誤設為跨頁完全相等的 invariant。兩頁也必須維持 `settingsActive` top-aligned canvas。

## 7. Review rule

新增或修改 Engineering Settings page 時，review 應先回答：

> 這個 UI 是 shared Settings primitive 可以表達的共同需求，還是 domain-specific requirement？

若屬共同需求，修改應落在 `operator-ui/settings-ui.*`。只有真正的 domain-specific layout 才留在頁面本地 CSS。
