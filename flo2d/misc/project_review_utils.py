from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
try:
    import h5py
except ImportError:
    pass
import numpy as np

SCENARIO_COLOURS = [
    QColor("#1f77b4"),  # blue
    QColor("#d62728"),  # red
    QColor("#2ca02c"),  # green
    QColor("#9467bd"),  # purple
    QColor("#ff7f0e"),  # orange
]

SCENARIO_STYLES = [
    Qt.SolidLine,
    Qt.DashLine,
    Qt.DotLine,
    Qt.DashDotLine,
    Qt.DashDotDotLine,
]


def timdep_dataframe_from_hdf5_scenarios(hdf5_file, grid_element):
    """
    Function to get TIMDEP the data from hdf5 using numpy arrays.
    """
    scenario_data = {}
    with h5py.File(hdf5_file, 'r') as hdf:
        for j in range(1, 6):
            base_path = f"Scenario {j}/Time Dependent"
            try:
                time_series = hdf[f"{base_path}/Time Series"][()]
                flow_depth = hdf[f"{base_path}/Depth"][:, grid_element - 1]
                wse = hdf[f"{base_path}/WSE"][:, grid_element - 1]
                velocity = hdf[f"{base_path}/Velocity"][:, grid_element - 1]
                data = np.core.records.fromarrays(
                    [time_series, flow_depth, velocity, wse],
                    names='Time, Depth, Velocity, WSE'
                )
                scenario_data[f"S{j}"] = data
            except KeyError:
                continue
        return scenario_data


def hydrostruct_dataframe_from_hdf5_scenarios(hdf5_file, struct_name):
    """
    Function to get HYDROSTRUCT data from hdf5 using numpy arrays.
    """
    scenario_data = {}
    with h5py.File(hdf5_file, 'r') as hdf:
        for j in range(1, 6):
            base_path = f"Scenario {j}/Hydraulic Structures"
            try:
                time_series = hdf[f"{base_path}/Time Series"][()]
                struct_data = hdf[f"{base_path}/{struct_name}"][()]
                inflow = struct_data[:, 0]
                outflow = struct_data[:, 1]
                # Ensure the time series matches the inflow/outflow data
                if len(time_series) != len(inflow) or len(time_series) != len(outflow):
                    # remove the last element to match lengths
                    time_series = time_series[:-1]
                data = np.core.records.fromarrays(
                    [time_series, inflow, outflow],
                    names='Time, Inflow, Outflow'
                )
                scenario_data[f"S{j}"] = data
            except KeyError:
                continue
        return scenario_data
