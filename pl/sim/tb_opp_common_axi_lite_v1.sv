`timescale 1ns/1ps
module tb;
  reg clk=0; always #5 clk=~clk;
  reg rstn=0;
  reg [11:0] awaddr=0, araddr=0;
  reg awvalid=0,wvalid=0,arvalid=0,bready=0,rready=0;
  reg [31:0] wdata=0;
  reg [3:0] wstrb=0;
  wire awready,wready,arready,bvalid,rvalid;
  wire [1:0] bresp,rresp;
  wire [31:0] rdata;
  opp_common_axi_lite_v1 dut(
    .aclk(clk),.aresetn(rstn),
    .s_axi_awaddr(awaddr),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
    .s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
    .s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(bready),
    .s_axi_araddr(araddr),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
    .s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(rready)
  );
  task send_aw(input [11:0] addr);
    begin
      @(negedge clk); awaddr=addr; awvalid=1;
      @(posedge clk); if(!awready) $fatal(1,"AW not ready");
      @(negedge clk); awvalid=0;
    end
  endtask
  task send_w(input [31:0] data,input [3:0] strb);
    begin
      @(negedge clk); wdata=data; wstrb=strb; wvalid=1;
      @(posedge clk); if(!wready) $fatal(1,"W not ready");
      @(negedge clk); wvalid=0;
    end
  endtask
  task expect_b(input [1:0] resp);
    begin
      wait(bvalid); #1;
      if(bresp!==resp) $fatal(1,"BRESP %b expected %b",bresp,resp);
      repeat(3) begin @(posedge clk); #1; if(!bvalid) $fatal(1,"BVALID dropped under backpressure"); end
      @(negedge clk); bready=1;
      @(negedge clk); bready=0;
    end
  endtask
  task read_check(input [11:0] addr,input [31:0] data,input [1:0] resp);
    begin
      @(negedge clk); araddr=addr; arvalid=1;
      @(posedge clk); if(!arready) $fatal(1,"AR not ready");
      @(negedge clk); arvalid=0;
      wait(rvalid); #1;
      if(rdata!==data || rresp!==resp) $fatal(1,"Read %h got %h resp %b",addr,rdata,rresp);
      repeat(3) begin @(posedge clk); #1; if(!rvalid || rdata!==data) $fatal(1,"R unstable under backpressure"); end
      @(negedge clk); rready=1;
      @(negedge clk); rready=0;
    end
  endtask
  initial begin
    repeat(4) @(negedge clk); rstn=1;
    read_check(12'h000,32'h4d534c50,2'b00);
    read_check(12'h004,32'h00010000,2'b00);
    read_check(12'h100,32'h0,2'b10);
    read_check(12'h041,32'h0,2'b10);
    send_aw(12'h040); repeat(3) @(negedge clk); send_w(32'h12345678,4'hf); expect_b(2'b00);
    read_check(12'h040,32'h12345678,2'b00);
    send_w(32'habcdef00,4'b0011); repeat(2) @(negedge clk); send_aw(12'h040); expect_b(2'b00);
    read_check(12'h040,32'h1234ef00,2'b00);
    send_aw(12'h000); send_w(32'hffffffff,4'hf); expect_b(2'b10);
    read_check(12'h040,32'h1234ef00,2'b00);
    send_aw(12'h040); send_w(32'hffffffff,4'h0); expect_b(2'b00);
    read_check(12'h040,32'h1234ef00,2'b00);
    $display("OPP AXI4-Lite simulation PASS");
    $finish;
  end
  initial begin #100000; $fatal(1,"timeout"); end
endmodule
