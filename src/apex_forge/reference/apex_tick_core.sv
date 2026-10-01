// SPDX-License-Identifier: Apache-2.0
// Normalized-event simulation core. MAC, PHY, CRC validation and session adapters are external.
module apex_tick_core #(
    parameter integer INSTRUMENTS=8,
    parameter integer MAX_PENDING=16,
    parameter integer WINDOW_CYCLES=64
)(
    input wire clk, input wire reset,
    input wire recover, input wire [63:0] in_seq, input wire [15:0] in_instrument,
    input wire [31:0] in_price, in_qty, in_epoch,
    input wire [63:0] cfg_limit, input wire [31:0] cfg_rate_limit,
    input wire in_valid, input wire frame_ok, output wire in_ready,
    input wire terminal_valid, input wire [63:0] terminal_id,
    output reg out_valid, input wire out_ready,
    output reg [63:0] out_order_id, output reg [15:0] out_instrument,
    output reg [31:0] out_price, out_qty,
    output reg hold, output reg [63:0] exposure, expected,
    output reg [3:0] status
);
    reg [31:0] epoch, threshold, order_qty, rate_limit, rate_count;
    reg [63:0] max_exposure, next_id;
    integer window_count;
    reg [31:0] ask [0:INSTRUMENTS-1];
    reg occupied [0:MAX_PENDING-1];
    reg sent [0:MAX_PENDING-1];
    reg [63:0] identities [0:MAX_PENDING-1];
    reg [31:0] quantities [0:MAX_PENDING-1];
    integer i, free_slot, terminal_slot;
    wire [31:0] effective_rate = window_count==WINDOW_CYCLES-1 ? 0 : rate_count;
    assign in_ready = !hold && !terminal_valid && !recover && (!out_valid || out_ready);
    always @* begin
        free_slot=-1;terminal_slot=-1;
        for (integer k=0;k<MAX_PENDING;k=k+1) begin
            if (!occupied[k] && free_slot==-1) free_slot=k;
            if (occupied[k] && identities[k]==terminal_id &&
                (sent[k] || (out_valid && out_ready && out_order_id==identities[k]))) terminal_slot=k;
        end
    end
    always @(posedge clk) begin
        if (reset) begin
            hold<=1;epoch<=0;expected<=1;next_id<=1;exposure<=0;
            threshold<=100;order_qty<=1;max_exposure<=16;rate_limit<=16;
            rate_count<=0;window_count<=0;out_valid<=0;status<=0;
            out_order_id<=0;out_instrument<=0;out_price<=0;out_qty<=0;
            for(i=0;i<MAX_PENDING;i=i+1) begin occupied[i]<=0;sent[i]<=0;identities[i]<=0;quantities[i]<=0;end
            for(i=0;i<INSTRUMENTS;i=i+1) ask[i]<=0;
        end else begin
            status<=0;
            if(window_count==WINDOW_CYCLES-1) begin window_count<=0;rate_count<=0;end
            else window_count<=window_count+1;
            if(out_valid && out_ready) begin
                out_valid<=0;
                for(i=0;i<MAX_PENDING;i=i+1) if(occupied[i] && identities[i]==out_order_id) sent[i]<=1;
            end
            if(recover) begin
                if(hold && exposure==0 && (!out_valid || out_ready) && in_epoch>epoch && in_qty>0 && cfg_limit>0 && cfg_rate_limit>0 && in_seq>0) begin
                    hold<=0;epoch<=in_epoch;expected<=in_seq;threshold<=in_price;order_qty<=in_qty;
                    max_exposure<=cfg_limit;rate_limit<=cfg_rate_limit;rate_count<=0;window_count<=0;
                end
            end else if(terminal_valid) begin
                if(terminal_slot>=0) begin
                    exposure<=exposure-quantities[terminal_slot];occupied[terminal_slot]<=0;sent[terminal_slot]<=0;status<=8;
                end else status<=9;
            end else if(in_valid && in_ready) begin
                if(!frame_ok || in_epoch!=epoch || in_instrument>=INSTRUMENTS || in_price==0 || in_qty==0) begin hold<=1;status<=1;end
                else if(in_seq<expected) status<=2;
                else if(in_seq!=expected || expected==64'hffffffffffffffff) begin hold<=1;status<=3;end
                else begin
                    expected<=expected+1;ask[in_instrument]<=in_price;
                    if(in_price>threshold || in_qty<order_qty) status<=6;
                    else if(free_slot<0 || exposure+order_qty>max_exposure || effective_rate>=rate_limit) status<=4;
                    else if(next_id==64'hffffffffffffffff) begin hold<=1;status<=7;end
                    else begin
                        occupied[free_slot]<=1;sent[free_slot]<=0;identities[free_slot]<=next_id;quantities[free_slot]<=order_qty;
                        exposure<=exposure+order_qty;next_id<=next_id+1;rate_count<=effective_rate+1;
                        out_valid<=1;out_order_id<=next_id;out_instrument<=in_instrument;out_price<=in_price;out_qty<=order_qty;status<=5;
                    end
                end
            end
        end
    end
endmodule
