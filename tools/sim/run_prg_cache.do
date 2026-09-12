# ModelSim ASE (ships with Quartus 17.0 Lite) - self-checking test of core/rtl/prg_cache.sv.
#   cd tools/sim
#   /c/intelFPGA_lite/17.0/modelsim_ase/win32aloem/vsim.exe -c -do run_prg_cache.do
# Add +EN=0 or +NOHIT=1 to the vsim line to exercise the OSD bypass / no-hit modes.
vlib work
vlog -sv -quiet ../../core/rtl/prg_cache.sv tb_prg_cache.sv
vsim -c -quiet work.tb_prg_cache -do "run -all; quit -f"
