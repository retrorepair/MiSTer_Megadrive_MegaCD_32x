# Report the worst setup paths whatever their sign, so a build that only just closes can be
# investigated the same way as one that fails.
#   quartus_sta -t <repo>/tools/sta_worst.tcl <ProjectName> [npaths]
set proj [lindex $quartus(args) 0]
set n [expr {[llength $quartus(args)] > 1 ? [lindex $quartus(args) 1] : 25}]
project_open $proj
create_timing_netlist -model slow
read_sdc
update_timing_netlist
foreach_in_collection p [get_timing_paths -setup -npaths $n -detail summary] {
	puts [format "PATH %8.3f  %-80s -> %s" [get_path_info $p -slack] \
		[get_node_info -name [get_path_info $p -from]] \
		[get_node_info -name [get_path_info $p -to]]]
}
delete_timing_netlist
project_close
