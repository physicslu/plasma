import Link from "next/link";
import "./demo.css";

export default function DemoLandingPage() {
  return (
    <main className="demoLanding">
      <section className="demoHero">
        <div className="demoBrand"><span>P</span><div><b>PLASMA</b><small>PROGRAMMING PLATFORM</small></div></div>
        <p className="demoEyebrow">PLASMA PRODUCT ENTRY</p>
        <h1>Choose Product Mode</h1>
        <p className="demoLead">Plasma 的產品層只保留兩種模式：量產模式與工程模式。多 PPU aggregation、Manager 與單機 PPU Console 都是模式底下的實作能力，不再作為平行的產品模式。</p>

        <div className="demoChoices">
          <Link className="demoCard fleet" href="/fleet">
            <div className="demoCardHead"><span>01</span><b>Production Mode</b></div>
            <h2>Factory Production Console</h2>
            <p>工廠操作介面：同畫面監控多台 PPU × Sites、PASS / FAIL、批次選取與 Factory Log。</p>
            <dl><div><dt>Product Mode</dt><dd>production</dd></div><div><dt>Manager</dt><dd>Read-only aggregation</dd></div></dl>
            <strong>Open Production Mode →</strong>
          </Link>

          <Link className="demoCard" href="/engineering">
            <div className="demoCardHead"><span>02</span><b>Engineering Mode</b></div>
            <h2>Engineering Workspace</h2>
            <p>工程與維護工作台：PPU / Sites、Programming、Diagnostics、Logs、Tools 與後續低階功能。</p>
            <dl><div><dt>Product Mode</dt><dd>engineering</dd></div><div><dt>PPU Console</dt><dd>Engineering capability</dd></div></dl>
            <strong>Open Engineering Mode →</strong>
          </Link>
        </div>

        <div className="demoBoundary">
          <b>Architecture boundary</b>
          <span>Manager aggregation failure does not stop local PPU programming.</span>
        </div>
      </section>
    </main>
  );
}
