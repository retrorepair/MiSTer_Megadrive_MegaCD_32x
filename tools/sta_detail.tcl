# Full detail for the single worst setup path: where the time actually goes.
#   quartus_sta -t <repo>/tools/sta_detail.tcl <ProjectName>
project_open [lindex $quartus(args) 0]
create_timing_netlist -model slow
read_sdc
update_timing_netlist
report_timing -setup -npaths 1 -detail full_path -panel_name "worst" -stdout
delete_timing_netlist
project_close
