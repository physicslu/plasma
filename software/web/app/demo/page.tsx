import Link from "next/link";
import "./demo.css";

export default function DemoLandingPage() {
  return (
    <main className="demoLanding">
      <section className="demoHero">
        <div className="demoBrand"><span>P</span><div><b>PLASMA</b><small>PROGRAMMING PLATFORM</small></div></div>
        <p className="demoEyebrow">PLASMA DEMONSTRATION ENTRY</p>
        <h1>Choose a Demo</h1>
        <p className="demoLead">單台 PPU 與多 PPU Fleet 是兩個不同的 operating scope。PPU 可獨立執行；Manager/Fleet 只提供選配的集中觀測能力。</p>

        <div className="demoChoices">
          <Link className="demoCard" href="/ppu">
            <div className="demoCardHead"><span>01</span><b>Single PPU Demo</b></div>
            <h2>Plasma PPU Console</h2>
            <p>操作單一 PPU 的 Site：Erase / Program / Verify / Read、批次執行、取消與即時狀態。</p>
            <dl><div><dt>Execution</dt><dd>Local PPU</dd></div><div><dt>Manager</dt><dd>Not required</dd></div></dl>
            <strong>Open Single PPU Demo →</strong>
          </Link>

          <Link className="demoCard fleet" href="/fleet">
            <div className="demoCardHead"><span>02</span><b>Manager / Fleet Demo</b></div>
            <h2>Plasma Fleet Overview</h2>
            <p>跨 Facility / PPU 查看 current、stale、unknown、Site topology 與目前可用 capacity。</p>
            <dl><div><dt>Execution</dt><dd>Read-only</dd></div><div><dt>Manager</dt><dd>Opt-in</dd></div></dl>
            <strong>Open Fleet Demo →</strong>
          </Link>
        </div>

        <div className="demoBoundary">
          <b>Architecture boundary</b>
          <span>Fleet/Manager failure does not stop local PPU programming.</span>
        </div>
      </section>
    </main>
  );
}
