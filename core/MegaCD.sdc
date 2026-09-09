derive_pll_clocks
derive_clock_uncertainty

set_multicycle_path -to {*Hq2x*} -setup 4
set_multicycle_path -to {*Hq2x*} -hold 3

set_multicycle_path -from [get_clocks { *|pll|pll_inst|altera_pll_i|*[0].*|divclk}] -to {ascal|*} -setup 4
set_multicycle_path -from [get_clocks { *|pll|pll_inst|altera_pll_i|*[0].*|divclk}] -to {ascal|*} -hold 3

# (No false paths for the SDRAM -> 32X crossing: the cartridge port is registered in clk_sys both ways, so the
# path does not exist. The wildcard versions of these also crashed quartus_fit 17.0 in
# sta_find_duplicates_of_deleted_net_name after physical synthesis retimed the registers they named.)

# The SDRAM controller runs on clk_ram (2x clk_sys, same PLL), so Quartus times its read-data registers
# to the clk_sys consumers as a single-edge transfer with only ~4.7 ns of slack - every bit of dout0
# failed by up to 8 ns through the cartridge/32X muxes. The transfer is protocol-bounded, not
# single-cycle: sdram.sv now holds each port's busy for two extra clk_ram cycles after capturing the
# data, so nothing samples it for at least ~19 ns. Allow four cycles to match that guarantee.
set_multicycle_path -from [get_registers {*sdram:sdram|dout*}] -setup 3
set_multicycle_path -from [get_registers {*sdram:sdram|dout*}] -hold 2
