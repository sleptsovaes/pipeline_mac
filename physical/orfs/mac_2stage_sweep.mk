export PLATFORM = sky130hd
export DESIGN_NAME = mac_2stage

export VERILOG_FILES = $(MAC_REPO)/rtl/mac_2stage.sv
export SDC_FILE = $(MAC_REPO)/physical/constraints/mac_sweep.sdc

export CORE_UTILIZATION = 40
export PLACE_DENSITY_LB_ADDON = 0.20
export TNS_END_PERCENT = 100
