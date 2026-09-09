derive_pll_clocks
derive_clock_uncertainty

# The Hq2x filter is replaced by a plain line doubler (sys/hq2x.sv), whose registers all run on the pixel
# clock, so its 4-cycle multicycle exception is gone. Keeping it also CRASHED Quartus 17.0 outright: with the
# smaller module most nodes matching the {*Hq2x*} wildcard are optimised away, and both quartus_fit (during
# physical synthesis) and quartus_sta die in sta_find_duplicates_of_deleted_net_name /
# add_keeper_to_vector_if_wildcard_matches while expanding the wildcard over deleted nets.

set_multicycle_path -from [get_clocks { *|pll|pll_inst|altera_pll_i|*[0].*|divclk}] -to {ascal|*} -setup 4
set_multicycle_path -from [get_clocks { *|pll|pll_inst|altera_pll_i|*[0].*|divclk}] -to {ascal|*} -hold 3

# (No false paths for the SDRAM -> 32X crossing: the cartridge port is registered in clk_sys both ways, so the
# path does not exist. The wildcard versions of these also crashed quartus_fit 17.0 in
# sta_find_duplicates_of_deleted_net_name after physical synthesis retimed the registers they named.)
