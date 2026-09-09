# Report the worst failing setup paths. Run in the project dir after a build:
#   quartus_sta -t <repo>/tools/sta_paths.tcl <ProjectName> [npaths]
set proj [lindex $quartus(args) 0]
set n [expr {[llength $quartus(args)] > 1 ? [lindex $quartus(args) 1] : 40}]
project_open $proj
create_timing_netlist -model slow
read_sdc
update_timing_netlist
foreach_in_collection p [get_timing_paths -setup -npaths $n -detail summary] {
	set slack [get_path_info $p -slack]
	if {$slack >= 0} { continue }
	puts [format "PATH %8.3f  %-90s -> %s" $slack \
		[get_node_info -name [get_path_info $p -from]] \
		[get_node_info -name [get_path_info $p -to]]]
}
delete_timing_netlist
project_close
