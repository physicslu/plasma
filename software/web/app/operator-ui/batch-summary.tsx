import { useEffect } from "react";
import type { ReactNode } from "react";
import { useI18n } from "../i18n";
import {
  batchSummaryChannelFromAriaLabel,
  clearBatchSummaryLiveMetrics,
  publishBatchSummaryLiveMetrics,
} from "./batch-summary-live";
import { OperatorPanelHeader } from "./operator-panel";
import "./batch-summary.css";

export type OperatorKpi = {
  key: string;
  label: string;
  value: ReactNode;
  tone?: "neutral" | "info" | "pass" | "fail";
};

export type BatchSummaryProps = {
  items: OperatorKpi[];
  ariaLabel: string;
  title?: string;
  meta?: ReactNode;
};

function numericKpi(items: OperatorKpi[], keys: string[]): number | null {
  const item = items.find(candidate => keys.includes(candidate.key));
  return typeof item?.value === "number" && Number.isFinite(item.value) ? item.value : null;
}

export function BatchSummary({
  items,
  ariaLabel,
  title,
  meta,
}: BatchSummaryProps) {
  const { locale } = useI18n();
  const hasManufacturingYield = items.some(item => item.key === "yield");
  const liveChannel = batchSummaryChannelFromAriaLabel(ariaLabel);
  const liveSites = numericKpi(items, ["sites", "production-sites"]);
  const liveProcessedIc = numericKpi(items, ["processed-ic"]);
  const liveTotalIc = numericKpi(items, ["total-ic"]);

  useEffect(() => {
    if (!liveChannel) return;
    if (liveSites === null || liveProcessedIc === null || liveTotalIc === null) {
      clearBatchSummaryLiveMetrics(liveChannel);
      return;
    }
    publishBatchSummaryLiveMetrics(liveChannel, {
      sites: liveSites,
      processedIc: liveProcessedIc,
      totalIc: liveTotalIc,
    });
  }, [liveChannel, liveProcessedIc, liveSites, liveTotalIc]);

  useEffect(() => () => {
    if (liveChannel) clearBatchSummaryLiveMetrics(liveChannel);
  }, [liveChannel]);

  return (
    <section className={`batchSummary ${title ? "has-title" : ""}`.trim()} aria-label={ariaLabel}>
      {title && <OperatorPanelHeader title={title} meta={meta} />}
      <div className="batchSummaryGrid">
        {items.map(item => (
          <article key={item.key} data-kpi={item.key} data-tone={item.tone ?? "neutral"}>
            <small>{item.label}</small>
            <b>{item.value}</b>
          </article>
        ))}
      </div>
      {hasManufacturingYield && (
        <p className="batchSummaryYieldNote">
          <b>{locale === "zh-TW" ? "Yield 定義" : "Yield definition"}</b>
          <span>
            {locale === "zh-TW"
              ? "PASS / (PASS + FAIL)；設備、通訊或基礎設施 ERROR 不計入 DUT FAIL 與 Yield 分母。"
              : "PASS / (PASS + FAIL); equipment, communication, and infrastructure ERROR states are excluded from DUT FAIL and the Yield denominator."}
          </span>
        </p>
      )}
    </section>
  );
}
