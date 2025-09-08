from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication

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

def hycross_dataframe_from_hdf5_scenarios(hdf5_file, fpxs_id):
    """
    Function to get HYCROSS data from hdf5 using numpy arrays.
    """
    scenario_data = {}
    with h5py.File(hdf5_file, 'r') as hdf:
        for j in range(1, 6):
            base_path = f"Scenario {j}/Floodplain Cross Sections"
            try:
                time_series = hdf[f"{base_path}/Time Series"][()]
                struct_data = hdf[f"{base_path}/Floodplain XS {fpxs_id}"][()]
                flow_width = struct_data[:, 0]
                ave_depth = struct_data[:, 1]
                wse = struct_data[:, 2]
                velocity = struct_data[:, 3]
                discharge = struct_data[:, 4]
                data = np.core.records.fromarrays(
                    [time_series, flow_width, ave_depth, wse, velocity, discharge],
                    names='Time, Flow Width, Ave. Depth, WSE, Velocity, Discharge'
                )
                scenario_data[f"S{j}"] = data
            except KeyError:
                continue
        return scenario_data

def hychan_dataframe_from_hdf5_scenarios(hdf5_file, mode):
    """
    Function to get HYCHAN data from hdf5 using numpy arrays.
    """
    scenario_dict = {}
    with h5py.File(hdf5_file, 'r') as hdf:
        for j in range(1, 6):
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                fid_dict = {}
                if mode == "peaks":
                    dataset_path = hdf[f"Scenario {j}/Channels/Profiles"]

                    for name, obj in dataset_path.items():
                        fid_dict[name] = obj[()]

                    # Just store the raw rows into the dictionary
                    scenario_dict[f"S{j}"] = fid_dict
                else:
                    dataset_path = hdf[f"Scenario {j}/Channels/Cross Sections"]

                    for name, obj in dataset_path.items():
                        fid_dict[name] = obj[()]

                    # Just store the raw rows into the dictionary
                    scenario_dict[f"S{j}"] = fid_dict
            except KeyError:
                continue
            finally:
                QApplication.restoreOverrideCursor()
        return scenario_dict

def crossq_dataframe_from_hdf5_scenarios(hdf5_file, grid_element):
    """
    Function to get CROSSQ data from hdf5 using numpy arrays.
    """
    scenario_dict = {}
    with h5py.File(hdf5_file, 'r') as hdf:
        for j in range(1, 6):
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                dataset = hdf[f"Scenario {j}/Floodplain Cross Sections/Cells/{grid_element}"][()]
                time_series = hdf[f"Scenario {j}/Floodplain Cross Sections/Time Series"][()]

                # Just store the raw rows into the dictionary
                scenario_dict[f"S{j}"] = [time_series, dataset]

            except KeyError:
                continue
            finally:
                QApplication.restoreOverrideCursor()
        return scenario_dict
