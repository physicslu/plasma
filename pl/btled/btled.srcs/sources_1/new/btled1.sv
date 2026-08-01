`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 2026/08/01 08:57:51
// Design Name: 
// Module Name: button_led
// Project Name: 
// Target Devices: 
// Tool Versions: 
// Description: 
// 
// Dependencies: 
// 
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
// 
//////////////////////////////////////////////////////////////////////////////////
// Test edit from Mac VS Code

module btled(
    input  logic [3:0] btn, 
    output logic [3:0] led
    );
    
    
    //--------------------------------------------------------------------------
    // Combinational Logic
    //--------------------------------------------------------------------------

    
    assign led = btn;
    
    
endmodule