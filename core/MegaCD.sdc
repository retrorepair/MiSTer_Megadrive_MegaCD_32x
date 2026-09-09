derive_pll_clocks
derive_clock_uncertainty

set_multicycle_path -to {*Hq2x*} -setup 4
set_multicycle_path -to {*Hq2x*} -hold 3

set_multicycle_path -from [get_clocks { *|pll|pll_inst|altera_pll_i|*[0].*|divclk}] -to {ascal|*} -setup 4
set_multicycle_path -from [get_clocks { *|pll|pll_inst|altera_pll_i|*[0].*|divclk}] -to {ascal|*} -hold 3

# (No false paths for the SDRAM -> 32X crossing: the cartridge port is registered in clk_sys both ways, so the
# path does not exist. The wildcard versions of these also crashed quartus_fit 17.0 in
# sta_find_duplicates_of_deleted_net_name after physical synthesis retimed the registers they named.)
