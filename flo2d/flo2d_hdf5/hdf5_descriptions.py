# Dataset - Description

CONTROL = {
    "CONT": "Control Parameters Data",
    "TOLER": "Numerical Stability Control Data",
    "TOLSPATIAL": "Spatially Variable Tolerance Values"
    # "AMANN": "Increment n Value at runtime",
    # "CELLSIZE": "Cellsize",
    # "COURANTC": "Courant Stability C",
    # "COURANTFP": "Courant Stability FP",
    # "COURANTST": "Courant Stability St",
    # "COURCHAR_C": "Stability Line 2 Character ID",
    # "COURCHAR_T": "Stability Line 3 Character",
    # "DEPRESSDEPTH": "Depress Depth",
    # "DEPTHDUR": "Depth Duration",
    # "DEPTOL": "Percent Change in Depth",
    # "ENCROACH": "Encroachment Analysis Depth",
    # "ENDTIMTEP": "End time for time series output",
    # "FROUDL": "Global Limiting Froude",
    # "GRAPTIM": "Graphical Update Interval",
    # "IARFBLOCKMOD": "Global ARF=1 revision",
    # "IBACKUP": "Backup Switch",
    # "ICHANNEL": "Channel Switch",
    # "IDEBRV": "Debris Switch",
    # "IDEPLT": "Plot Hydrograph",
    # "IEVAP": "Evaporation Switch",
    # "IFLOODWAY": "Floodway Analysis Switch",
    # "IHOURDAILY": "Basetime Switch Hourly / Daily",
    # "IHYDRSTRUCT": "Hydraulic Structure Switch",
    # "IMODFLOW": "Modflow Switch",
    # "IMULTC": "Multiple Channel Switch",
    # "INFIL": "Infiltration Switch",
    # "IRAIN": "Rain Switch",
    # "ISED": "Sediment Transport Switch",
    # "ITIMTEP": "Time Series Selection Switch",
    # "IWRFS": "Building Switch",
    # "LEVEE": "Levee Switch",
    # "LGPLOT": "Graphic Mode",
    # "MANNING": "Global n Value Adjustment",
    # "METRIC": "Metric Switch",
    # "MSTREET": "Street Switch",
    # "MUD": "Mudflow Switch",
    # "NOPRTC": "Detailed Channel Output Options",
    # "NOPRTFP": "Detailed Floodplain Output Options",
    # "NXPRT": "Detailed FP cross section output.",
    # "PROJ": "Projection",
    # "SHALLOWN": "Shallow n Value",
    # "SIMUL": "Simulation Time",
    # "STARTIMTEP": "Start time for time series output",
    # "SWMM": "Storm Drain Switch",
    # "TIME_ACCEL": "Timestep Sensitivity",
    # "TIMTEP": "Time Series Output Interval",
    # "TOLGLOBAL": "Low flow exchange limit",
    # "TOUT": "Output Data Interval",
    # "WAVEMAX": "Wavemax Sensitivity",
    # "XARF": "Global Area Reduction",
    # "XCONC": "Global Sediment Concentration",
    # "build": "Executable Build"
}

GRID = {
    "GRIDCODE": "Grid code",
    "MANNING": "Global n Value Adjustment",
    "COORDINATES": "Longitude - Latitude",
    "ELEVATION": "Elevation",
    "NEIGHBOURS": "Neighbours"
}

NEIGHBORS = {
    "E": "East neighbor",
    "N": "North neighbor",
    "NE": "Northeast neighbor",
    "NW": "Northwest neighbor",
    "S": "South neighbor",
    "SE": "Southeast neighbor",
    "SW": "Soutwest neighbor",
    "W": "West neighbor",
}

STORMDRAIN = {
    "SWMMFLO": "Storm Drain Data File",
    "SWMMFLORT": "Storm Drain Type 4 Rating Table File",
    "SWMMOUTF": "Storm Drain Outfall ID Data File",
}

BC = {
    "Inflow/INF_GLOBAL": "Inflow Global Data",
    "Inflow/INF_GRID": "Inflow Grid Data",
    "Inflow/RESERVOIRS": "Reservoirs Data",
    "Inflow/TS_INF_DATA": "Time Series Inflow Data",
    "Outflow/CH_OUT_GRID": "Channel Outflow Grids",
    "Outflow/FP_OUT_GRID": "Floodplain Outflow Grids",
    "Outflow/HYD_OUT_GRID": "Outflow Hydrograph Grids",
    "Outflow/QH_PARAMS": "Channel Depth-Discharge Power Regression Parameters",
    "Outflow/QH_PARAMS_GRID": "Channel Depth-Discharge Power Regression Grids",
    "Outflow/QH_TABLE": "Channel Depth-Discharge Data",
    "Outflow/QH_TABLE_GRID": "Channel Depth-Discharge Gris",
    "Outflow/TS_OUT_DATA": "Time-Stage Data",
    "Outflow/TS_OUT_GRID": "Time-Stage Grids",
}

CHANNEL = {
    "CHAN": "Channel Data",
    "CHANBANK": "Channel Bank Data",
    "XSEC": "Cross Section Data",
    "STREET": "Street Data"
}

HYSTRUCT = {
    "BRIDGE_VARIABLES": "Bridge Variables",
    "BRIDGE_XSEC": "Bridge Cross-sections",
    "CULVERT_EQUATIONS": "Generalized Culvert Equation",
    "RATING_CURVE": "Rating Curve",
    "RATING_TABLE": "Rating Table",
    "STORM_DRAIN": "Storm Drain Capacity",
    "STR_CONTROL": "Hydraulic Structure Data",
    "STR_NAME": "Hydraulic Structure Names",
}

INFIL = {
    "INFIL_METHOD": "Infiltration Method: 1 - Green-Ampt, 2 - SCS Curve, 3 - Both Green-Ampt and SCS, and 4 - Horton",
    "INFIL_GA_GLOBAL": "Green-Ampt Global Infiltration Data",
    "INFIL_GA_CELLS": "Green-Ampt Infiltration Data",
    "INFIL_CHAN_GLOBAL": "Channel Global Infiltration Data",
    "INFIL_CHAN_SEG": "Channel Segment Infiltration Data",
    "INFIL_CHAN_ELEMS": "Channel Grid Infiltration Data",
    "INFIL_SCS_GLOBAL": "SCS Global Infiltration Data",
    "INFIL_SCS_CELLS": "SCS Infiltration Data",
    "INFIL_HORTON_GLOBAL": "Horton Global Infiltration Data",
    "INFIL_HORTON_CELLS": "Horton Infiltration Data",
}

RAIN = {
    "RAIN_GLOBAL": "Global Rainfall Data",
    "RAIN_DATA": "Rainfall Data",
    "RAIN_ARF": "Rainfall ARF"
}

REDUCTION_FACTORS = {
    "ARF_GLOBAL": "Global revision to the ARF",
    "ARF_TOTALLY_BLOCKED": "Totally blocked grid elements",
    "ARF_PARTIALLY_BLOCKED": "Partially blocked gridd elements",
    "WRF": "Floodplain Width Reduction",
}

SPATIALLY_VARIABLE = {
    "TOLSPATIAL": "Spatially Variable Tolerance Values",
    "FPFROUDE": "Spatially Variable Froude Values",
    "SHALLOWN_SPATIAL": "Spatially Variable Shallow-n Values",
}

LEVEE = {
    "LEVEE": "Levee and Failure Data",
    "LEVEE_GLOBAL": "Levee Global Data",
    "LEVEE_DATA": "Levee Data",
    "LEVEE_FAILURE": "Levee Failure Data"
}

EVAPOR = {
    "EVAPOR": "Evaporation Data"
}

FLOODPLAIN = {
    "FPXSEC_DATA": "Floodplain Cross-Sections Data",
    "FPXSEC_GLOBAL": "Floodplain Cross-Sections Global",
}

GUTTER = {
    "GUTTER_GLOBAL": "Gutter Global Data",
    "GUTTER_DATA": "Gutter Global"
}

TAILINGS = {
    "TAILINGS": "Tailings Depth Data"
}