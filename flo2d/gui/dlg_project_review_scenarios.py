# -*- coding: utf-8 -*-
import os.path
import re
from collections import OrderedDict

from qgis._core import QgsApplication

from ..flo2dobjects import ChannelSegment

try:
    import h5py
except ImportError:
    pass
from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QFileDialog, QProgressDialog

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from .ui_utils import load_ui
from ..flo2d_ie.flo2d_parser import ParseDAT
from ..user_communication import UserCommunication, is_file_locked
import numpy as np

uiDialog, qtBaseClass = load_ui("project_review_scenarios")


class ProjectReviewScenariosDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, gutils):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.setupUi(self)
        self.iface = iface
        self.gutils = gutils
        self.parser = ParseDAT()

        self.uc = UserCommunication(iface, "FLO-2D")
        self.s = QSettings()

        self.populate_scenarios()

        # connections
        self.ok_btn.clicked.connect(self.save_scenarios)
        self.cancel_btn.clicked.connect(self.close_dlg)
        self.scenario1_btn.clicked.connect(lambda: self.select_scenario(1))
        self.scenario2_btn.clicked.connect(lambda: self.select_scenario(2))
        self.scenario3_btn.clicked.connect(lambda: self.select_scenario(3))
        self.scenario4_btn.clicked.connect(lambda: self.select_scenario(4))
        self.scenario5_btn.clicked.connect(lambda: self.select_scenario(5))

        self.del_scenario1_btn.clicked.connect(lambda: self.delete_scenario(1))
        self.del_scenario2_btn.clicked.connect(lambda: self.delete_scenario(2))
        self.del_scenario3_btn.clicked.connect(lambda: self.delete_scenario(3))
        self.del_scenario4_btn.clicked.connect(lambda: self.delete_scenario(4))
        self.del_scenario5_btn.clicked.connect(lambda: self.delete_scenario(5))

        self.n_scenarios = None

        self.select_all_chbox.toggled.connect(self.select_all_datasets)

        self.save_processed_results_file_btn.clicked.connect(self.save_processed_results_file)
        self.process_results_btn.clicked.connect(self.process_results)
        self.use_scenarios_grpbox.toggled.connect(self.populate_processed_results)

    def populate_scenarios(self):
        """
        Function to populate the scenarios on the Project Review - Scenarios
        """

        use_prs = self.gutils.get_cont_par("USE_SCENARIOS")

        scenario1 = self.gutils.get_cont_par("SCENARIO_1")
        self.scenario1_le.setText(scenario1)
        scenario2 = self.gutils.get_cont_par("SCENARIO_2")
        self.scenario2_le.setText(scenario2)
        scenario3 = self.gutils.get_cont_par("SCENARIO_3")
        self.scenario3_le.setText(scenario3)
        scenario4 = self.gutils.get_cont_par("SCENARIO_4")
        self.scenario4_le.setText(scenario4)
        scenario5 = self.gutils.get_cont_par("SCENARIO_5")
        self.scenario5_le.setText(scenario5)

        processed_results_file = self.gutils.get_cont_par("SCENARIOS_RESULTS")
        if processed_results_file:
            self.processed_results_le.setText(processed_results_file)

        if use_prs == '1':
            self.use_scenarios_grpbox.setChecked(True)
            self.process_results_grp.setEnabled(True)

        else:
            self.use_scenarios_grpbox.setChecked(False)
            self.process_results_grp.setEnabled(False)


    def select_scenario(self, scenario_n):
        """
        Function to select the scenario using the QToolButton
        """
        project_dir = self.s.value("FLO-2D/lastGdsDir")
        outdir = QFileDialog.getExistingDirectory(
            None,
            "Select scenario directory",
            directory=project_dir,
        )
        if outdir:
            if scenario_n == 1:
                self.scenario1_le.setText(outdir)
                self.gutils.set_cont_par("SCENARIO_1", outdir)
            if scenario_n == 2:
                self.scenario2_le.setText(outdir)
                self.gutils.set_cont_par("SCENARIO_2", outdir)
            if scenario_n == 3:
                self.scenario3_le.setText(outdir)
                self.gutils.set_cont_par("SCENARIO_3", outdir)
            if scenario_n == 4:
                self.scenario4_le.setText(outdir)
                self.gutils.set_cont_par("SCENARIO_4", outdir)
            if scenario_n == 5:
                self.scenario5_le.setText(outdir)
                self.gutils.set_cont_par("SCENARIO_5", outdir)

            self.uc.bar_info("Scenario saved!")
            self.uc.log_info("Scenario saved!")

    def delete_scenario(self, scenario_n):
        """
        Function to select the scenario using the QToolButton
        """
        if scenario_n == 1:
            self.scenario1_le.setText("")
            self.gutils.set_cont_par("SCENARIO_1", "")
        if scenario_n == 2:
            self.scenario2_le.setText("")
            self.gutils.set_cont_par("SCENARIO_2", "")
        if scenario_n == 3:
            self.scenario3_le.setText("")
            self.gutils.set_cont_par("SCENARIO_3", "")
        if scenario_n == 4:
            self.scenario4_le.setText("")
            self.gutils.set_cont_par("SCENARIO_4", "")
        if scenario_n == 5:
            self.scenario5_le.setText("")
            self.gutils.set_cont_par("SCENARIO_5", "")

        self.uc.bar_info("Scenario deleted!")
        self.uc.log_info("Scenario deleted!")

    def save_scenarios(self):
        """
        Function to save the scenarios to the QGIS settings
        """
        use_prs = self.use_scenarios_grpbox.isChecked()
        self.gutils.set_cont_par("USE_SCENARIOS", use_prs)

        scenario1 = self.scenario1_le.text()
        scenario2 = self.scenario2_le.text()
        scenario3 = self.scenario3_le.text()
        scenario4 = self.scenario4_le.text()
        scenario5 = self.scenario5_le.text()

        self.gutils.set_cont_par("SCENARIO_1", scenario1)
        self.gutils.set_cont_par("SCENARIO_2", scenario2)
        self.gutils.set_cont_par("SCENARIO_3", scenario3)
        self.gutils.set_cont_par("SCENARIO_4", scenario4)
        self.gutils.set_cont_par("SCENARIO_5", scenario5)

        output_hdf5 = self.processed_results_le.text()

        self.gutils.set_cont_par("SCENARIOS_RESULTS", output_hdf5)

        self.uc.bar_info("Scenarios saved!")
        self.uc.log_info("Scenarios saved!")

        self.close()

    def populate_processed_results(self):
        """
        Function to enable/disable the processed results
        """
        self.gutils.set_cont_par("USE_SCENARIOS", self.use_scenarios_grpbox.isChecked())
        if self.use_scenarios_grpbox.isChecked():
            self.process_results_grp.setEnabled(True)
        else:
            self.process_results_grp.setEnabled(False)

    def save_processed_results_file(self):
        """
        Function to set the hdf5 file into the line edit
        """
        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")
        output_hdf5, _ = QFileDialog.getSaveFileName(
            None,
            "Save processed results data into HDF5 format",
            directory=last_dir,
            filter="HDF5 file (*.hdf5; *.HDF5)",
        )
        if output_hdf5:
            self.processed_results_le.setText(output_hdf5)
            self.uc.bar_info("Processed results file path saved!")
            self.uc.log_info("Processed results file path saved!")

    def process_results(self):
        """
        Function to process the results into a hdf5 for easy display on the FLO-2D table and plot
        """
        processed_results_file = self.processed_results_le.text()

        # Check if file exists
        if is_file_locked(processed_results_file):
            self.uc.bar_error(
                f"The processed results file ({os.path.basename(processed_results_file)}) is currently open or locked by another process!")
            self.uc.log_info(
                f"The processed results file ({os.path.basename(processed_results_file)}) is currently open or locked by another process!")
            return

        # Remove existing file
        try:
            if os.path.exists(processed_results_file):
                os.remove(processed_results_file)
            else:
                pass
        except Exception as e:
            return

        self.gutils.set_cont_par("SCENARIOS_RESULTS", processed_results_file)

        scenario1 = self.gutils.get_cont_par("SCENARIO_1") if self.gutils.get_cont_par("SCENARIO_1") != "" else None
        scenario2 = self.gutils.get_cont_par("SCENARIO_2") if self.gutils.get_cont_par("SCENARIO_2") != "" else None
        scenario3 = self.gutils.get_cont_par("SCENARIO_3") if self.gutils.get_cont_par("SCENARIO_3") != "" else None
        scenario4 = self.gutils.get_cont_par("SCENARIO_4") if self.gutils.get_cont_par("SCENARIO_4") != "" else None
        scenario5 = self.gutils.get_cont_par("SCENARIO_5") if self.gutils.get_cont_par("SCENARIO_5") != "" else None
        scenarios = [scenario1, scenario2, scenario3, scenario4, scenario5]

        self.n_scenarios = len([s for s in scenarios if s is not None])

        if self.n_scenarios == 0:
            self.uc.bar_warn("No scenarios selected")
            self.uc.log_info("No scenarios selected")
            return False

        QgsApplication.setOverrideCursor(Qt.WaitCursor)

        if self.stormdrain_chbox.isChecked():
            self.process_swmmrpt(scenarios, processed_results_file)
            self.process_SWMMQIN(scenarios, processed_results_file)
            self.process_SWMMOUTFIN(scenarios, processed_results_file)

        if self.timdep_chbox.isChecked():
            self.process_timdep(scenarios, processed_results_file)

        if self.hydrostruct_chbox.isChecked():
            self.process_hydrostruct(scenarios, processed_results_file)

        if self.fpxs_chbox.isChecked():
            self.process_fpxs(scenarios, processed_results_file)
            self.process_fpxs_cells(scenarios, processed_results_file)

        if self.channels_chbox.isChecked():
            self.process_channels(scenarios, processed_results_file)

        self.uc.bar_info("The selected data was process successfully!")
        self.uc.log_info("The selected data was process successfully!")
        QgsApplication.restoreOverrideCursor()

    def process_channels(self, scenarios, processed_results_file):
        """
        Function to process HYCHAN.OUT file into the hdf5 file
        """

        progDialog = QProgressDialog("Processing HYCHAN.OUT...", None, 0, self.n_scenarios)
        progDialog.setModal(True)
        progDialog.setValue(0)
        progDialog.forceShow()

        for i, scenario in enumerate(scenarios, start=0):
            progDialog.setValue(i)
            QgsApplication.processEvents()
            if scenario:
                if os.path.exists(processed_results_file):
                    read_type = "a"
                else:
                    read_type = "w"
                with h5py.File(processed_results_file, read_type) as hdf:
                    hychan_profile_group = hdf.create_group(f"Scenario {i + 1}/Channels/Profiles")
                    hychan_xs_group= hdf.create_group(f"Scenario {i + 1}/Channels/Cross Sections")
                    HYCHAN_file = os.path.join(scenario, r"HYCHAN.OUT")

                    peaks_dict, _ = self.parser.parse_hychan(HYCHAN_file, mode="peaks")
                    ts_dict, _ = self.parser.parse_hychan(HYCHAN_file, mode="time_series")

                    for key, values in peaks_dict.items():
                        arr = np.array(values)
                        hychan_profile_group.create_dataset(key,
                                                   data=arr.T,
                                                   compression="gzip",
                                                   compression_opts=9)

                    for key, values in ts_dict.items():
                        arr = np.array(values)
                        hychan_xs_group.create_dataset(key,
                                                   data=arr.T,
                                                   compression="gzip",
                                                   compression_opts=9)

        progDialog.close()

    def process_fpxs(self, scenarios, processed_results_file):
        """
        Function to process the HYCROSS file into the hdf5 file
        """

        progDialog = QProgressDialog("Processing HYCROSS.OUT...", None, 0, self.n_scenarios)
        progDialog.setModal(True)
        progDialog.setValue(0)
        progDialog.forceShow()

        for i, scenario in enumerate(scenarios, start=0):
            progDialog.setValue(i)
            QgsApplication.processEvents()
            if scenario:
                if os.path.exists(processed_results_file):
                    read_type = "a"
                else:
                    read_type = "w"
                ts_created = False
                with h5py.File(processed_results_file, read_type) as hdf:
                    fpxs_group = hdf.create_group(f"Scenario {i + 1}/Floodplain Cross Sections")
                    HYCROSS_file = os.path.join(scenario, r"HYCROSS.OUT")
                    with open(HYCROSS_file, "r") as myfile:
                        while True:
                            try:
                                line = next(myfile)
                            except StopIteration:
                                break
                            if "THE MAXIMUM DISCHARGE FROM CROSS SECTION" in line:
                                fpxs_name = f'Floodplain XS {line.split()[6]}'
                                for _ in range(9):
                                    line = next(myfile)
                                time_list = []
                                data_list = []
                                while True:
                                    try:
                                        line = next(myfile)
                                    except StopIteration:
                                        break
                                    if not line.strip():
                                        break
                                    line = line.split()
                                    if line[0] == "VELOCITY":
                                        for _ in range(5):
                                            line = next(myfile)
                                            line = line.split()
                                    time_list.append(float(line[0]))
                                    data_list.append((float(line[1]), float(line[2]), float(line[3]), float(line[4]),
                                                      float(line[5])))
                                if not ts_created:
                                    fpxs_group.create_dataset("Time Series", data=time_list, compression="gzip",
                                                              compression_opts=9)
                                    ts_created = True
                                fpxs_group.create_dataset(fpxs_name, data=data_list, compression="gzip",
                                                          compression_opts=9)

        progDialog.close()

    def process_fpxs_cells(self, scenarios, processed_results_file):
        """
        Function to process the CROSSQ file into the hdf5 file
        """

        progDialog = QProgressDialog("Processing CROSSQ.OUT...", None, 0, self.n_scenarios)
        progDialog.setModal(True)
        progDialog.setValue(0)
        progDialog.forceShow()

        for i, scenario in enumerate(scenarios, start=0):
            progDialog.setValue(i)
            QgsApplication.processEvents()
            if not scenario:
                continue

            read_type = "a" if os.path.exists(processed_results_file) else "w"
            with h5py.File(processed_results_file, read_type) as hdf:
                # require_group avoids errors if the group already exists
                fpxs_group = hdf.require_group(f"Scenario {i + 1}/Floodplain Cross Sections/Cells")

                CROSSQ_file = os.path.join(scenario, "CROSSQ.OUT")
                with open(CROSSQ_file, "r", encoding="utf-8", errors="replace") as myfile:
                    pushback = None  # holds a header line for the next iteration

                    while True:
                        try:
                            # read either the saved header or the next line
                            line = pushback if pushback is not None else next(myfile)
                            pushback = None
                        except StopIteration:
                            break

                        parts = line.split()
                        if len(parts) == 3 and parts[0].isdigit():
                            grid = str(int(parts[0]))
                            discharge_list = [float(parts[2])]

                            # gather rows until the next header or a blank line
                            while True:
                                try:
                                    line = next(myfile)
                                except StopIteration:
                                    line = ""
                                if not line.strip():
                                    break
                                sp = line.split()
                                if len(sp) == 3 and sp[0].isdigit():
                                    # save this header for the outer loop
                                    pushback = line
                                    break
                                discharge_list.append(float(sp[1]))

                            # write dataset, overwrite if it already exists
                            if grid in fpxs_group:
                                del fpxs_group[grid]
                            fpxs_group.create_dataset(
                                grid,
                                data=discharge_list,
                                compression="gzip",
                                compression_opts=9,
                            )

        progDialog.close()

    def process_hydrostruct(self, scenarios, processed_results_file):
        """
        Function to process the HYDROSTRUCT file into the hdf5 file
        """

        progDialog = QProgressDialog("Processing HYDROSTRUCT.OUT...", None, 0, self.n_scenarios)
        progDialog.setModal(True)
        progDialog.setValue(0)
        progDialog.forceShow()

        for i, scenario in enumerate(scenarios, start=0):
            progDialog.setValue(i)
            QgsApplication.processEvents()
            if scenario:
                if os.path.exists(processed_results_file):
                    read_type = "a"
                else:
                    read_type = "w"
                ts_created = False
                with h5py.File(processed_results_file, read_type) as hdf:
                    hydrostruct = hdf.create_group(f"Scenario {i + 1}/Hydraulic Structures")
                    HYDROSTRUCT_file = os.path.join(scenario, r"HYDROSTRUCT.OUT")
                    with open(HYDROSTRUCT_file, "r") as myfile:
                        time_list = []
                        discharge_list = []
                        pattern = re.compile(
                            r"THE\s+MAXIMUM\s+DISCHARGE\s+FOR:\s+(.+?)\s+STRUCTURE\s+NO\.\s+(\d+)\s+IS:",
                            re.IGNORECASE
                        )
                        while True:
                            try:
                                line = next(myfile)
                                match = re.search(pattern, line)
                                if match:
                                    matched_structure_name = match.group(1)
                                    line = next(myfile)
                                    while True:
                                        try:
                                            line = next(myfile)
                                            line = line.split()
                                            if line:
                                                time_list.append(float(line[0]))
                                                discharge_list.append((float(line[1]), float(line[2])))
                                            else:
                                                break
                                        except StopIteration:
                                            break
                                    if not ts_created:
                                        hydrostruct.create_dataset("Time Series",
                                                                   data=time_list,
                                                                   compression="gzip",
                                                                   compression_opts=9)
                                        ts_created = True
                                    hydrostruct.create_dataset(matched_structure_name,
                                                               data=discharge_list,
                                                               compression="gzip",
                                                               compression_opts=9)
                                    time_list = []
                                    discharge_list = []
                            except StopIteration:
                                break

        progDialog.close()

    def process_timdep(self, scenarios, processed_results_file):
        """
        Function to process the TIMPDEP file into the hdf5 file
        """

        progDialog = QProgressDialog("Processing TIMDEP.HDF5...", None, 0, self.n_scenarios)
        progDialog.setModal(True)
        progDialog.setValue(0)
        progDialog.forceShow()

        for i, scenario in enumerate(scenarios, start=0):
            progDialog.setValue(i)
            QgsApplication.processEvents()
            if scenario:
                if os.path.exists(processed_results_file):
                    read_type = "a"
                else:
                    read_type = "w"
                timdep_file = os.path.join(scenario, r"TIMDEP.HDF5")
                with h5py.File(processed_results_file, read_type) as hdf:
                    time_dependent = hdf.create_group(f"Scenario {i + 1}/Time Dependent")
                    with h5py.File(timdep_file, "r") as timdep_hdf:
                        time_series = np.array(timdep_hdf['/TIMDEP NETCDF OUTPUT RESULTS/FLOW DEPTH/Times'])
                        time_series = time_series.flatten()
                        time_dependent.create_dataset("Time Series",
                                data=time_series,
                                compression="gzip",
                                compression_opts=9)

                        flow_depth = np.array(timdep_hdf['/TIMDEP NETCDF OUTPUT RESULTS/FLOW DEPTH/Values'])
                        time_dependent.create_dataset("Depth",
                                data=flow_depth,
                                compression="gzip",
                                compression_opts=9)

                        wse = np.array(timdep_hdf['/TIMDEP NETCDF OUTPUT RESULTS/Floodplain Water Surface Elevation/Values'])
                        time_dependent.create_dataset("WSE",
                                                   data=wse,
                                                   compression="gzip",
                                                   compression_opts=9)

                        velocity = np.array(timdep_hdf['/TIMDEP NETCDF OUTPUT RESULTS/Velocity MAG/Values'])
                        time_dependent.create_dataset("Velocity",
                                                   data=velocity,
                                                   compression="gzip",
                                                   compression_opts=9)
                        #
                        # channel_wse = np.array(timdep_hdf['/TIMDEP NETCDF OUTPUT RESULTS/Channel Water Surface Elevation/Values'])
                        # channel_wse_group.create_dataset("Channel WSE",
                        #                               data=channel_wse,
                        #                               compression="gzip",
                        #                               compression_opts=9)

        progDialog.close()

    def process_SWMMQIN(self, scenarios, hdf5_file):
        """
        Function to process the SWMMQIN.OUT file into the hdf5 file
        """

        progDialog = QProgressDialog("Processing SWMMQIN.OUT...", None, 0, self.n_scenarios)
        progDialog.setModal(True)
        progDialog.setValue(0)
        progDialog.forceShow()

        for i, scenario in enumerate(scenarios, start=0):
            progDialog.setValue(i)
            QgsApplication.processEvents()
            if scenario:
                SWMMQIN = scenario + r"/SWMMQIN.OUT"
                swmmqin_data = self.get_SWMMQIN(SWMMQIN)
                if os.path.exists(hdf5_file):
                    read_type = "a"
                else:
                    read_type = "w"
                with h5py.File(hdf5_file, read_type) as hdf:
                    group = hdf.create_group(f"Scenario {i + 1}/Storm Drain/SWMMQIN")
                    for key, values in swmmqin_data.items():
                        group.create_dataset(key,
                                data=values,
                                compression="gzip",
                                compression_opts=9)
        progDialog.close()

    def process_SWMMOUTFIN(self, scenarios, hdf5_file):
        """
        Function to process the SWMMOUTFIN.OUT file into the hdf5 file
        """

        progDialog = QProgressDialog("Processing SWMMOUTFIN.OUT...", None, 0, self.n_scenarios)
        progDialog.setModal(True)
        progDialog.setValue(0)
        progDialog.forceShow()

        for i, scenario in enumerate(scenarios, start=0):
            progDialog.setValue(i)
            QgsApplication.processEvents()
            if scenario:
                SWMMOUTFIN = scenario + r"/SWMMOUTFIN.OUT"
                swmmoutfin_data = self.get_SWMMOUTFIN(SWMMOUTFIN)
                if os.path.exists(hdf5_file):
                    read_type = "a"
                else:
                    read_type = "w"
                with h5py.File(hdf5_file, read_type) as hdf:
                    group = hdf.create_group(f"Scenario {i + 1}/Storm Drain/SWMMOUTFIN")
                    for key, values in swmmoutfin_data.items():
                        group.create_dataset(key,
                                             data=values,
                                             compression="gzip",
                                             compression_opts=9)
        progDialog.close()

    def process_swmmrpt(self, scenarios, hdf5_file):
        """
        Function to process the SWMM.rpt file into the hdf5 file
        """

        progDialog = QProgressDialog("Processing SWMM.RPT...", None, 0, self.n_scenarios)
        progDialog.setModal(True)
        progDialog.setValue(0)
        progDialog.forceShow()

        for i, scenario in enumerate(scenarios, start=0):
            progDialog.setValue(i)
            QgsApplication.processEvents()
            if scenario:
                swmm_rpt = scenario + r"/swmm.RPT"

                # Start with nodes and time data
                nodes = {}
                current_node = None
                links = {}
                current_link = None
                time_series = False
                data = []  # Dates
                time = []  # Times

                with open(swmm_rpt, 'r') as file:
                    for line in file:
                        # Detect end of relevant section
                        if re.match(r'  Analysis begun', line):
                            break

                        # Detect node name
                        node_match = re.match(r'  <<< Node (.*?) >>>', line)
                        if node_match:
                            if data and time:
                                time_series = True
                            current_node = node_match.group(1)
                            nodes[current_node] = []
                            continue

                        # Detect link name
                        link_match = re.match(r'  <<< Link (.*?) >>>', line)
                        if link_match:
                            current_link = link_match.group(1)
                            links[current_link] = []
                            continue

                        # Skip headers and separators
                        if re.match(r'[-]+', line) or not line.strip() or "Inflow" in line:
                            continue

                        # Parse node data lines
                        if current_node:
                            parts = re.split(r'\s+', line.strip())
                            if len(parts) >= 6 and parts[0] != "Date":  # Ensure it's a data row
                                # Populate time series data only once
                                if not time_series:
                                    data.append(parts[0])  # Date
                                    time.append(parts[1])  # Time
                                # Append node-specific data
                                nodes[current_node].append(parts[2:6])  # Extract Inflow, Flooding, Depth, Head

                        # Parse link data lines
                        if current_link:
                            parts = re.split(r'\s+', line.strip())
                            if len(parts) >= 6 and parts[0] != "Date":  # Ensure it's a data row
                                # Append node-specific data
                                links[current_link].append(parts[2:6])  # Extract flow, velocity, depth, percent

                # Convert node data to numpy arrays for HDF5 compatibility
                for node_name in nodes:
                    nodes[node_name] = np.array(nodes[node_name], dtype=float)

                # Convert link data to numpy arrays for HDF5 compatibility
                for link_name in links:
                    links[link_name] = np.array(links[link_name], dtype=float)

                if os.path.exists(hdf5_file):
                    read_type = "a"
                else:
                    read_type = "w"

                # Write to HDF5
                with h5py.File(hdf5_file, read_type) as hdf:
                    # Create the time dataset
                    time_group = hdf.create_group(f"Scenario {i + 1}/Storm Drain")
                    time_group.create_dataset(
                        "Time Series",
                        data=np.array(list(zip(data, time)), dtype="S"),  # Convert to fixed-width strings
                        compression="gzip",
                        compression_opts=9
                    )

                    # Create the group structure for nodes
                    nodes_group = hdf.create_group(f"Scenario {i + 1}/Storm Drain/Nodes")

                    # Create a dataset for each node
                    for node_name, node_data in nodes.items():
                        if len(node_data) > 0:  # Only write datasets with data
                            nodes_group.create_dataset(
                                node_name,
                                data=node_data,
                                compression="gzip",
                                compression_opts=9
                            )

                    # Create the group structure for links
                    links_group = hdf.create_group(f"Scenario {i + 1}/Storm Drain/Links")

                    # Create a dataset for each node
                    for link_name, link_data in links.items():
                        if len(link_data) > 0:  # Only write datasets with data
                            links_group.create_dataset(
                                link_name,
                                data=link_data,
                                compression="gzip",
                                compression_opts=9
                            )
        progDialog.close()

    def close_dlg(self):
        """
        Function to close the dialog
        """
        self.close()

    def get_SWMMQIN(self, SWMMQIN_file):
        data = OrderedDict()
        try:  # Read SWMMQIN_file.
            pd = ParseDAT()
            par = pd.single_parser(SWMMQIN_file)
            for row in par:
                if "INLET" in row:
                    cell = row[7]
                    inlet = row[11]
                    next(par)
                    data[inlet] = []
                    for row2 in par:
                        if len(row2) == 3:
                            time = row2[0]
                            discharge = row2[1]
                            return_flow = row2[2]
                            data[inlet].append(row2)
                        elif "INLET" in row2:
                            cell = row2[7]
                            inlet = row2[11]
                            next(par)
                            data[inlet] = []
        except Exception as e:
            self.uc.show_error("Error while reading file\n\n " + SWMMQIN_file, e)
        finally:
            return data

    def get_SWMMOUTFIN(self, SWMMOUTFIN_file):
        data = OrderedDict()
        try:  # Read SWMMOUTFIN_file.
            pd = ParseDAT()
            par = pd.single_parser(SWMMOUTFIN_file)
            for row in par:
                if "GRID" in row:
                    cell = row[2]
                    # channel_element=  row[5]
                    next(par)
                    data[cell] = []
                    for row2 in par:
                        if len(row2) == 2:
                            time = row2[0]
                            discharge = row2[1]
                            data[cell].append(row2)
                        elif "GRID" in row2:
                            cell = row2[2]
                            # channel_element=  row2[5]
                            next(par)
                            data[cell] = []
        except Exception as e:
            self.uc.show_error("Error while reading file\n\n " + SWMMOUTFIN_file, e)
        finally:
            return data

    def select_all_datasets(self):
        """
        Function to select all datasets
        """
        if self.select_all_chbox.isChecked():
            self.timdep_chbox.setChecked(True)
            self.stormdrain_chbox.setChecked(True)
            self.channels_chbox.setChecked(True)
            self.fpxs_chbox.setChecked(True)
            self.channels_chbox.setChecked(True)
            self.hydrostruct_chbox.setChecked(True)
        else:
            self.timdep_chbox.setChecked(False)
            self.stormdrain_chbox.setChecked(False)
            self.channels_chbox.setChecked(False)
            self.fpxs_chbox.setChecked(False)
            self.channels_chbox.setChecked(False)
            self.hydrostruct_chbox.setChecked(False)
