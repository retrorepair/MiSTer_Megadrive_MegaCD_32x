derive_pll_clocks
derive_clock_uncertainty

set_multicycle_path -to {*Hq2x*} -setup 4
set_multicycle_path -to {*Hq2x*} -hold 3

set_multicycle_path -from [get_clocks { *|pll|pll_inst|altera_pll_i|*[0].*|divclk}] -to {ascal|*} -setup 4
set_multicycle_path -from [get_clocks { *|pll|pll_inst|altera_pll_i|*[0].*|divclk}] -to {ascal|*} -hold 3

# SDRAM read data / busy (107 MHz clk_ram, outclk 0) into the 32X interface's negedge-clk_sys samplers: the data is
# stable long before it is used (ROM_WAIT handshake) and the busy flag is resynchronised, so the crossing is not a
# timed path. Upstream S32X_MiSTer reports these as its only failing paths.
set_false_path -from [get_registers {emu|sdram|dout*}] -to [get_registers {emu|S32X|s32x_if|CDI_SYNC*}]
set_false_path -from [get_registers {emu|sdram|ram_req*}] -to [get_registers {emu|S32X|s32x_if|ROM_WAIT_SYNC*}]
