"""Host-only SWD-01/02 RTL + line-level target acceptance."""
from pathlib import Path
from cocotb_test.simulator import run

PL = Path(__file__).resolve().parents[1]


def test_swd_transaction_virtual_target():
    run(
        simulator='icarus',
        verilog_sources=[str(PL / p) for p in [
            'rtl/site/swd_waveform_engine.sv',
            'rtl/site/swd_transaction_master.sv',
            'verification/sva/swd_transaction_checks.sv',
            'sim/swd_transaction_tb.sv',
        ]],
        toplevel='swd_transaction_tb', module='test_swd_transaction',
        compile_args=['-g2012'], timescale='1ns/1ps', waves=True,
        python_search=[str(PL/'verification/cocotb'),str(PL/'verification/models')],
        sim_build=str(PL/'build/swd01-02/sim'),
    )


def test_assertion_checker_detects_stalled_response_mutation(tmp_path):
    """Prove simulator evaluates the assertion, with deliberate invalid stimulus."""
    import subprocess
    source=tmp_path/'checker_tb.sv'
    source.write_text('''module checker_tb;
logic clk=0, rst_n=0, valid=0;
logic [31:0] data=0;
always #5 clk=~clk;
swd_transaction_checks checker_i(.clk(clk),.rst_n(rst_n),.busy(1'b0),
 .cmd_ready(1'b0),.resp_valid(valid),.resp_ready(1'b0),.resp_status(4'd0),
 .resp_ack(3'd1),.resp_rdata(data),.resp_data_valid(1'b1),.resp_attempts(9'd1),
 .swclk(1'b0),.swdio_oe(1'b0),.phy_start(1'b0),.phy_busy(1'b0),
 .elapsed(32'd0),.deadline(32'd10));
initial begin
 #10 rst_n=1; valid=1;
 #10 data=32'd1;
 #20 $finish;
end
endmodule
''')
    image=tmp_path/'checker.vvp'
    subprocess.run(['iverilog','-g2012','-s','checker_tb','-o',str(image),
                    str(source),str(PL/'verification/sva/swd_transaction_checks.sv')],
                   check=True,capture_output=True,text=True)
    result=subprocess.run(['vvp',str(image)],capture_output=True,text=True)
    assert result.returncode != 0
    assert 'Response changed under backpressure' in result.stdout
