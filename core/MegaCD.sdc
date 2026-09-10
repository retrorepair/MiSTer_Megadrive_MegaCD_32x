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

# The remaining failures are the rest of the same crossing. clk_ram (outclk_0, counter[0]) and clk_sys
# (outclk_1, counter[1]) come from one PLL, so Quartus times transfers between them against the closest
# edge pair (~4.7 ns) even though every such transfer here is handshake-bounded and stable for many
# cycles:
#   clk_ram -> clk_sys : SDRAM read data and per-port busy. sdram.sv holds busy two extra clk_ram cycles
#                        after capturing the data, so nothing samples either for ~19 ns.
#   clk_sys -> clk_ram : SDRAM request address/strobes from the MD arbiter and the SH-2 bus controllers,
#                        held by the requester for the whole access; and the video path into video_mixer,
#                        where pixel data is stable for ~16 clk_ram cycles at a 6.7 MHz pixel rate.
set_multicycle_path -from [get_clocks {*|pll|pll_inst|altera_pll_i|*counter[0].output_counter|divclk}] \
                    -to   [get_clocks {*|pll|pll_inst|altera_pll_i|*counter[1].output_counter|divclk}] -setup 3
set_multicycle_path -from [get_clocks {*|pll|pll_inst|altera_pll_i|*counter[0].output_counter|divclk}] \
                    -to   [get_clocks {*|pll|pll_inst|altera_pll_i|*counter[1].output_counter|divclk}] -hold 2
set_multicycle_path -from [get_clocks {*|pll|pll_inst|altera_pll_i|*counter[1].output_counter|divclk}] \
                    -to   [get_clocks {*|pll|pll_inst|altera_pll_i|*counter[0].output_counter|divclk}] -setup 2
set_multicycle_path -from [get_clocks {*|pll|pll_inst|altera_pll_i|*counter[1].output_counter|divclk}] \
                    -to   [get_clocks {*|pll|pll_inst|altera_pll_i|*counter[0].output_counter|divclk}] -hold 1

# The 32X samples the cartridge data bus into CDI_SYNC on the clk_sys NEGEDGE, so Quartus gives the
# whole path from an address register (the MD arbiter's MBUS_A, or an SH-2's bus controller) through
# the cartridge module's SRAM range comparator and output mux only half a period - 9.3 ns for a path
# that measures 8.5 ns, most of it routing on a device that is 77% full. Which side of that line a
# build lands on is placement luck, and that is exactly the condition that used to make builds flip
# between working and dead.
#
# It is not a single-cycle transfer. CDI_SYNC has exactly ONE consumer, IF.sv:895 `MD_ROM_DO <=
# CDI_SYNC` in state RS_MD_READ, and that state cannot be reached until at least two clocks after the
# address settles: the state machine starts from AS_N_SYNC/CE0_N_SYNC, which are themselves sampled a
# clock later, and then passes through RS_MD_RW. The address and the cartridge data behind it are held
# by the requester for the whole access. Allow the sample a full extra period to settle; an early
# sample is simply never read.
set_multicycle_path -to [get_registers {*S32X_IF*|CDI_SYNC*}] -setup 2
set_multicycle_path -to [get_registers {*S32X_IF*|CDI_SYNC*}] -hold 1
