import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const guidancePath = new URL("../app/operator-ui/production-workflow-guidance.css", import.meta.url);
const programmingJobPath = new URL("../app/operator-ui/programming-job-panel.tsx", import.meta.url);

async function source(url) {
  return readFile(url, "utf8");
}

test("PMode operation guidance exposes SET workflow and distinct FAIL/ERROR semantics without owning execution logic", async () => {
  const [css, programmingJob] = await Promise.all([
    source(guidancePath),
    source(programmingJobPath),
  ]);

  assert.match(programmingJob, /import "\.\/production-workflow-guidance\.css";/);
  assert.match(css, /1 SELECT SITES\s+→\s+2 SET PRODUCTION SITES\s+→\s+3 CONFIGURE IC \/ IMAGE \/ OPS\s+→\s+4 START PROGRAMMING/);
  assert.match(css, /1 選設備 \/ Site\s+→\s+2 SET 生產範圍\s+→\s+3 選 IC \/ Image \/ 操作\s+→\s+4 開始燒錄/);
  assert.match(css, /SCOPE · /);
  assert.match(css, /FAIL = DUT \/ Site programming failure · ERROR = equipment \/ communication failure · ERROR is excluded from DUT FAIL and Yield\./);
  assert.match(css, /FAIL = 晶片 \/ Site 燒錄失敗 · ERROR = 設備 \/ 通訊異常 · ERROR 不計入 DUT FAIL 與 Yield。/);
  assert.match(css, /factoryLegend i\[data-state="error"\][\s\S]*background:\s*#f97316/);
  assert.match(css, /factorySiteLedCard\.state-error[\s\S]*border-color:\s*#fdba74/);

  for (const forbidden of [
    "createServerBatch",
    "cancelServerBatch",
    "evaluateBatchReadiness",
    "fetch(",
    "sessionStorage",
    "localStorage",
  ]) {
    assert.equal(css.includes(forbidden), false, `presentation guidance must not own execution token: ${forbidden}`);
  }
});
