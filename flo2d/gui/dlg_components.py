# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright ? 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os

from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtWidgets import QApplication, QMessageBox

from ..flo2d_ie.flo2d_parser import ParseDAT
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from .ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("components")


class ComponentsDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs, in_or_out):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)

        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.uc = UserCommunication(iface, "FLO-2D")
        self.gutils = GeoPackageUtils(con, iface)
        self.current_lyr = None
        self.components = []
        self.component_actions = {} # Stores each component's export decision/status (e.g., "export_only", "export_and_turn_on", or "skipped")
        self.in_or_out = in_or_out

        self.components_buttonBox.accepted.connect(self.select_components)
        self.select_all_chbox.clicked.connect(self.unselect_all)

        self.setFixedSize(self.size())

        self.populate_components_dialog()

    def populate_components_dialog(self):
        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")
        self.file_lbl.setText(last_dir)

        self.data_rb.setVisible(False)
        self.hdf5_rb.setVisible(False)

        if self.in_or_out == "in":
            self.setWindowTitle("FLO-2D Components to Import")
            self.components_note_lbl.setVisible(False)
            self.mannings_n_and_Topo_chbox.setVisible(False)

            parser = ParseDAT()
            cont = parser.parse_cont(last_dir + r"\CONT.DAT")

            if os.path.isfile(last_dir + r"\CHAN.DAT"):
                if os.path.getsize(last_dir + r"\CHAN.DAT") > 0:
                    self.channels_chbox.setEnabled(True)
                    if cont and cont['ICHANNEL'] != '0':
                        self.channels_chbox.setChecked(True)

            if os.path.isfile(last_dir + r"\ARF.DAT"):
                if os.path.getsize(last_dir + r"\ARF.DAT") > 0:
                    self.reduction_factors_chbox.setEnabled(True)
                    if cont and cont['IWRFS'] != '0':
                        self.reduction_factors_chbox.setChecked(True)

            if os.path.isfile(last_dir + r"\STREET.DAT"):
                if os.path.getsize(last_dir + r"\STREET.DAT") > 0:
                    self.streets_chbox.setEnabled(True)
                    if cont and cont['MSTREET'] != '0':
                        self.streets_chbox.setChecked(True)

            if os.path.isfile(last_dir + r"\OUTFLOW.DAT"):
                if os.path.getsize(last_dir + r"\OUTFLOW.DAT") > 0:
                    self.outflow_elements_chbox.setChecked(True)
                    self.outflow_elements_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\INFLOW.DAT"):
                if os.path.getsize(last_dir + r"\INFLOW.DAT") > 0:
                    self.inflow_elements_chbox.setChecked(True)
                    self.inflow_elements_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\LEVEE.DAT"):
                if os.path.getsize(last_dir + r"\LEVEE.DAT") > 0:
                    self.levees_chbox.setEnabled(True)
                    if cont and cont['LEVEE'] != '0':
                        self.levees_chbox.setChecked(True)

            if os.path.isfile(last_dir + r"\MULT.DAT"):
                if os.path.getsize(last_dir + r"\MULT.DAT") > 0:
                    self.multiple_channels_chbox.setEnabled(True)
                    if cont and cont['IMULTC'] != '0':
                        self.multiple_channels_chbox.setChecked(True)

            if os.path.isfile(last_dir + r"\SIMPLE_MULT.DAT"):
                if os.path.getsize(last_dir + r"\SIMPLE_MULT.DAT") > 0:
                    self.multiple_channels_chbox.setEnabled(True)
                    if cont and cont['IMULTC'] != '0':
                        self.multiple_channels_chbox.setChecked(True)

            if os.path.isfile(last_dir + r"\BREACH.DAT"):
                if os.path.getsize(last_dir + r"\BREACH.DAT") > 0:
                    self.breach_chbox.setEnabled(True)
                    if cont and cont['LEVEE'] != '0':
                        self.breach_chbox.setChecked(True)

            if os.path.isfile(last_dir + r"\GUTTER.DAT"):
                if os.path.getsize(last_dir + r"\GUTTER.DAT") > 0:
                    self.gutters_chbox.setChecked(True)
                    self.gutters_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\INFIL.DAT"):
                if os.path.getsize(last_dir + r"\INFIL.DAT") > 0:
                    self.infiltration_chbox.setEnabled(True)
                    if cont and cont['INFIL'] != '0':
                        self.infiltration_chbox.setChecked(True)

            if os.path.isfile(last_dir + r"\FPXSEC.DAT"):
                if os.path.getsize(last_dir + r"\FPXSEC.DAT") > 0:
                    self.floodplain_xs_chbox.setChecked(True)
                    self.floodplain_xs_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\SED.DAT"):
                if os.path.getsize(last_dir + r"\SED.DAT") > 0:
                    self.mud_and_sed_chbox.setEnabled(True)
                    if cont and (cont['MUD'] != '0' or cont['ISED'] != '0'):
                        self.mud_and_sed_chbox.setChecked(True)

            if os.path.isfile(last_dir + r"\EVAPOR.DAT"):
                if os.path.getsize(last_dir + r"\EVAPOR.DAT") > 0:
                    self.evaporation_chbox.setEnabled(True)
                    if cont and cont['IEVAP'] != '0':
                        self.evaporation_chbox.setChecked(True)

            if os.path.isfile(last_dir + r"\HYSTRUC.DAT"):
                if os.path.getsize(last_dir + r"\HYSTRUC.DAT") > 0:
                    self.hydr_struct_chbox.setEnabled(True)
                    if cont and cont['IHYDRSTRUCT'] != '0':
                        self.hydr_struct_chbox.setChecked(True)

            if os.path.isfile(last_dir + r"\RAIN.DAT"):
                if os.path.getsize(last_dir + r"\RAIN.DAT") > 0:
                    self.rain_chbox.setEnabled(True)
                    if cont and cont['IRAIN'] != '0':
                        self.rain_chbox.setChecked(True)

            if (os.path.isfile(last_dir + r"\SWMMFLO.DAT") or
                    os.path.isfile(last_dir + r"\SWMMOUTF.DAT") or
                    os.path.isfile(last_dir + r"\SWMM.INP")):
                if ((os.path.isfile(last_dir + r"\SWMMFLO.DAT") and os.path.getsize(last_dir + r"\SWMMFLO.DAT") > 0) or
                        (os.path.isfile(last_dir + r"\SWMMOUTF.DAT") and os.path.getsize(last_dir + r"\SWMMOUTF.DAT") > 0) or
                        (os.path.isfile(last_dir + r"\SWMM.INP") and os.path.getsize(last_dir + r"\SWMM.INP") > 0)):
                    self.storm_drain_chbox.setEnabled(True)
                    if cont and cont['SWMM'] != '0':
                        self.storm_drain_chbox.setChecked(True)

            if os.path.isfile(last_dir + r"\TOLSPATIAL.DAT"):
                if os.path.getsize(last_dir + r"\TOLSPATIAL.DAT") > 0:
                    self.spatial_tolerance_chbox.setChecked(True)
                    self.spatial_tolerance_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\FPFROUDE.DAT"):
                if os.path.getsize(last_dir + r"\FPFROUDE.DAT") > 0:
                    self.spatial_froude_chbox.setChecked(True)
                    self.spatial_froude_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\STEEP_SLOPEN.DAT"):
                if os.path.getsize(last_dir + r"\STEEP_SLOPEN.DAT") > 0:
                    self.spatial_steep_slopen_chbox.setChecked(True)
                    self.spatial_steep_slopen_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\LID_VOLUME.DAT"):
                if os.path.getsize(last_dir + r"\LID_VOLUME.DAT") > 0:
                    self.spatial_lid_volume_chbox.setChecked(True)
                    self.spatial_lid_volume_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\SHALLOWN_SPATIAL.DAT"):
                if os.path.getsize(last_dir + r"\SHALLOWN_SPATIAL.DAT") > 0:
                    self.spatial_shallow_n_chbox.setChecked(True)
                    self.spatial_shallow_n_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\TAILINGS.DAT"):
                if os.path.getsize(last_dir + r"\TAILINGS.DAT") > 0:
                    self.tailings_chbox.setChecked(True)
                    self.tailings_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\TAILINGS_CV.DAT"):
                if os.path.getsize(last_dir + r"\TAILINGS_CV.DAT") > 0:
                    self.tailings_chbox.setChecked(True)
                    self.tailings_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\TAILINGS_STACK_DEPTH.DAT"):
                if os.path.getsize(last_dir + r"\TAILINGS_STACK_DEPTH.DAT") > 0:
                    self.tailings_chbox.setChecked(True)
                    self.tailings_chbox.setEnabled(True)

        elif self.in_or_out == "out":
            self.setWindowTitle("FLO-2D Components to Export")
            self.file_lbl.setText(last_dir)
            show_note = False

            sql = """SELECT name, value FROM cont;"""
            options = {o: v if v is not None else "" for o, v in self.gutils.execute(sql).fetchall()}

            if options["ICHANNEL"] == "0" and not self.gutils.is_table_empty("chan"):
                self.channels_chbox.setText("*" + self.channels_chbox.text() + "*")
                show_note = True

            if options["IEVAP"] == "0" and not self.gutils.is_table_empty("evapor"):
                self.evaporation_chbox.setText("*" + self.evaporation_chbox.text() + "*")
                show_note = True

            if options["IHYDRSTRUCT"] == "0" and not self.gutils.is_table_empty("struct"):
                self.hydr_struct_chbox.setText("*" + self.hydr_struct_chbox.text() + "*")
                show_note = True

            if options["IMULTC"] == "0" and not (
                self.gutils.is_table_empty("mult_cells") and self.gutils.is_table_empty("simple_mult_cells")
            ):
                self.multiple_channels_chbox.setText("*" + self.multiple_channels_chbox.text() + "*")
                show_note = True

            if options["INFIL"] == "0" and not self.gutils.is_table_empty("infil"):
                self.infiltration_chbox.setText("*" + self.infiltration_chbox.text() + "*")
                show_note = True

            if options["IRAIN"] == "0" and not self.gutils.is_table_empty("rain"):
                self.rain_chbox.setText("*" + self.rain_chbox.text() + "*")
                show_note = True

            if options["IWRFS"] == "0" and not self.gutils.is_table_empty("blocked_cells"):
                self.reduction_factors_chbox.setText("*" + self.reduction_factors_chbox.text() + "*")
                show_note = True

            if options["LEVEE"] == "0" and not self.gutils.is_table_empty("levee_data"):
                self.levees_chbox.setText("*" + self.levees_chbox.text() + "*")
                show_note = True

            if options["MSTREET"] == "0" and not self.gutils.is_table_empty("streets"):
                self.streets_chbox.setText("*" + self.streets_chbox.text() + "*")
                show_note = True

            if options["SWMM"] == "0" and not self.gutils.is_table_empty("swmmflo"):
                self.storm_drain_chbox.setText("*" + self.storm_drain_chbox.text() + "*")
                show_note = True

            self.components_note_lbl.setVisible(show_note)

            if not self.gutils.is_table_empty("chan"):
                self.channels_chbox.setChecked(options["ICHANNEL"] != "0")
                self.channels_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("blocked_cells"):
                self.reduction_factors_chbox.setChecked(options["IWRFS"] != "0")
                self.reduction_factors_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("streets"):
                self.streets_chbox.setChecked(options["MSTREET"] != "0")
                self.streets_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("outflow_cells"):
                self.outflow_elements_chbox.setChecked(True)
                self.outflow_elements_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("inflow") or not self.gutils.is_table_empty("reservoirs") or not self.gutils.is_table_empty("tailing_reservoirs"):
                self.inflow_elements_chbox.setChecked(True)
                self.inflow_elements_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("levee_data"):
                self.levees_chbox.setChecked(options["LEVEE"] != "0")
                self.levees_chbox.setEnabled(True)

            if (not self.gutils.is_table_empty("mult_cells")) or (not self.gutils.is_table_empty("simple_mult_cells")):
                # If there are mult/simple_mult cells but 'mult' (globals) is empty, set globals:
                if self.gutils.is_table_empty("mult"):
                    self.gutils.fill_empty_mult_globals()
                # Pre-check if CONT switch is ON; otherwise enabled but unchecked.
                self.multiple_channels_chbox.setChecked(options["IMULTC"] != "0")
                self.multiple_channels_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("breach"):
                qry = "SELECT ilevfail FROM levee_general"
                row = self.gutils.execute(qry).fetchone()
                if row[0] == 2:
                    self.breach_chbox.setChecked(True)
                    self.breach_chbox.setEnabled(True)
                else:
                    self.breach_chbox.setChecked(False)
                    self.breach_chbox.setEnabled(False)

            if not self.gutils.is_table_empty("gutter_cells"):
                self.gutters_chbox.setChecked(True)
                self.gutters_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("infil"):
                self.infiltration_chbox.setChecked(options["INFIL"] != "0")
                self.infiltration_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("fpxsec"):
                self.floodplain_xs_chbox.setChecked(True)
                self.floodplain_xs_chbox.setEnabled(True)

            # Mud and Sediment Transport:
            ISED = self.gutils.get_cont_par("ISED")
            MUD = self.gutils.get_cont_par("MUD")

            ised_off = (ISED is None) or (str(ISED) != "1")
            mud_off = (MUD is None) or (str(MUD) not in ("1", "2"))

            # If BOTH are effectively OFF (set to None)
            if ised_off and mud_off:
                self.mud_and_sed_chbox.setChecked(False)
                self.mud_and_sed_chbox.setEnabled(False)
            else:
                # At least one mode is ON (Mud/debris, Sediment, or Two phase).
                # Enable the checkbox if there is any mud/sed data in the project.
                mud_has_data = not self.gutils.is_table_empty("mud")
                sed_has_data = not self.gutils.is_table_empty("sed")
                if mud_has_data or sed_has_data:
                    self.mud_and_sed_chbox.setEnabled(True)
                    self.mud_and_sed_chbox.setChecked(True)  # checked since a mode is ON
                else:
                    # No data: leave it unchecked; you can also choose to keep it disabled if you prefer.
                    self.mud_and_sed_chbox.setChecked(False)
                    self.mud_and_sed_chbox.setEnabled(False)

            if not self.gutils.is_table_empty("evapor"):
                self.evaporation_chbox.setChecked(options["IEVAP"] != "0")
                self.evaporation_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("struct"):
                self.hydr_struct_chbox.setChecked(options["IHYDRSTRUCT"] != "0")
                self.hydr_struct_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("rain"):
                self.rain_chbox.setChecked(options["IRAIN"] != "0")
                self.rain_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("swmmflo"):
                self.storm_drain_chbox.setChecked(options["SWMM"] != "0")
                self.storm_drain_chbox.setEnabled(True)

            if  not self.gutils.is_table_empty("spatialshallow_cells"):
                self.spatial_shallow_n_chbox.setChecked(True)
                self.spatial_shallow_n_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("tolspatial_cells"):
                self.spatial_tolerance_chbox.setChecked(True)
                self.spatial_tolerance_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("fpfroude_cells"):
                self.spatial_froude_chbox.setChecked(True)
                self.spatial_froude_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("steep_slope_n_cells"):
                self.spatial_steep_slopen_chbox.setChecked(True)
                self.spatial_steep_slopen_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("lid_volume_cells"):
                self.spatial_lid_volume_chbox.setChecked(True)
                self.spatial_lid_volume_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("grid"):
                self.mannings_n_and_Topo_chbox.setChecked(True)
                self.mannings_n_and_Topo_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("tailing_cells"):
                self.tailings_chbox.setChecked(True)
                self.tailings_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("outrc"):
                self.outrc_chbox.setChecked(True)
                self.outrc_chbox.setEnabled(True)

        else:
            QApplication.restoreOverrideCursor()
            self.uc.show_info("ERROR 240619.0704: Wrong components in/out selection!")

    # (Name, checkbox_attr, table_name_or_tuple, cont_key_or_tuple)
    component_specs = [
        ("Channels", "channels_chbox", "chan", "ICHANNEL"),
        ("Evaporation", "evaporation_chbox", "evapor", "IEVAP"),
        ("Hydraulic Structures", "hydr_struct_chbox", "struct", "IHYDRSTRUCT"),
        ("Infiltration", "infiltration_chbox", "infil", "INFIL"),
        ("Rain", "rain_chbox", "rain", "IRAIN"),
        ("Levees", "levees_chbox", "levee_data", "LEVEE"),
        ("Streets", "streets_chbox", "streets", "MSTREET"),
        ("Reduction Factors", "reduction_factors_chbox", "blocked_cells", "IWRFS"),
        ("Storm Drain", "storm_drain_chbox", "swmmflo", "SWMM"),
        ("Multiple Channel", "multiple_channels_chbox", ("mult_cells", "simple_mult_cells"), "IMULTC"),
    ]

    def select_components(self):
        # reset each time in case dialog instance is reused
        self.components = []
        self.component_actions = {}

        # CONT/DAT-governed components
        for comp_name, chbox_attr, table_name, cont_key in self.component_specs:
            checkbox = getattr(self, chbox_attr)

            # skip if not checked
            if not checkbox.isChecked():
                self.component_actions[comp_name] = "skipped"
                continue

            # has_data: accept one or many tables
            if isinstance(table_name, (list, tuple, set)):
                has_data = any(not self.gutils.is_table_empty(t) for t in table_name)
            else:
                has_data = not self.gutils.is_table_empty(table_name)

            # CONT state: accept one or many keys
            if isinstance(cont_key, (list, tuple, set)):
                is_on = any(str(self.gutils.get_cont_par(k)) != "0" for k in cont_key)
            else:
                is_on = str(self.gutils.get_cont_par(cont_key)) != "0"

            # EXPORT mode, data exists, but switch(es) are OFF → ask user how to proceed
            if self.in_or_out == "out" and has_data and not is_on:
                title = f"{comp_name} switch is OFF"
                msg = (
                    f"The CONT.DAT switch for <b>{comp_name}</b> is currently <b>OFF</b>."
                    "<br><br>How would you like to proceed?"
                )
                user_choice = self.uc.dialog_with_2_customized_buttons(title, msg, "Export ONLY","Export and Switch ON",)
                if user_choice == QMessageBox.Yes: # Export Only
                    decision = "export_only"
                elif user_choice == QMessageBox.No: # Export and Switch On
                    decision = "export_and_turn_on"
                else:
                    decision = "skipped" # Close / Cancel
                if decision in ("export_only", "export_and_turn_on"):
                    self.components.append(comp_name)
                self.component_actions[comp_name] = decision
            else:
                # already ON, or no data, or import mode
                self.components.append(comp_name)
                self.component_actions[comp_name] = "normal"

        if self.mud_and_sed_chbox.isChecked():
            self.components.append("Mudflow and Sediment Transport")

        if self.outflow_elements_chbox.isChecked():
            self.components.append("Outflow Elements")

        if self.inflow_elements_chbox.isChecked():
            self.components.append("Inflow Elements")

        if self.breach_chbox.isChecked():
            self.components.append("Breach")

        if self.gutters_chbox.isChecked():
            self.components.append("Gutters")

        if self.floodplain_xs_chbox.isChecked():
            self.components.append("Floodplain Cross Sections")

        if self.mudflo_chbox.isChecked():
            self.components.append("MODFLO-2D")

        if self.spatial_shallow_n_chbox.isChecked():
            self.components.append("Spatial Shallow-n")

        if self.spatial_tolerance_chbox.isChecked():
            self.components.append("Spatial Tolerance")

        if self.spatial_froude_chbox.isChecked():
            self.components.append("Spatial Froude")

        if self.spatial_steep_slopen_chbox.isChecked():
            self.components.append("Spatial Steep Slope-n")

        if self.spatial_lid_volume_chbox.isChecked():
            self.components.append("LID Volume")

        if self.mannings_n_and_Topo_chbox.isChecked():
            self.components.append("Manning's n and Topo")

        if self.tailings_chbox.isChecked():
            self.components.append("Tailings")

        if self.outrc_chbox.isChecked():
            self.components.append("Surface Water Rating Tables")

    def unselect_all(self):
        self.check_components(self.select_all_chbox.isChecked())

    def check_components(self, select=True):
        if self.channels_chbox.isEnabled():
            self.channels_chbox.setChecked(select)
        if self.reduction_factors_chbox.isEnabled():
            self.reduction_factors_chbox.setChecked(select)
        if self.streets_chbox.isEnabled():
            self.streets_chbox.setChecked(select)
        if self.outflow_elements_chbox.isEnabled():
            self.outflow_elements_chbox.setChecked(select)
        if self.inflow_elements_chbox.isEnabled():
            self.inflow_elements_chbox.setChecked(select)
        if self.levees_chbox.isEnabled():
            self.levees_chbox.setChecked(select)
        if self.multiple_channels_chbox.isEnabled():
            self.multiple_channels_chbox.setChecked(select)
        if self.breach_chbox.isEnabled():
            self.breach_chbox.setChecked(select)
        if self.gutters_chbox.isEnabled():
            self.gutters_chbox.setChecked(select)
        if self.infiltration_chbox.isEnabled():
            self.infiltration_chbox.setChecked(select)
        if self.floodplain_xs_chbox.isEnabled():
            self.floodplain_xs_chbox.setChecked(select)
        if self.mud_and_sed_chbox.isEnabled():
            self.mud_and_sed_chbox.setChecked(select)
        if self.evaporation_chbox.isEnabled():
            self.evaporation_chbox.setChecked(select)
        if self.hydr_struct_chbox.isEnabled():
            self.hydr_struct_chbox.setChecked(select)
        if self.mudflo_chbox.isEnabled():
            self.mudflo_chbox.setChecked(select)
        if self.rain_chbox.isEnabled():
            self.rain_chbox.setChecked(select)
        if self.storm_drain_chbox.isEnabled():
            self.storm_drain_chbox.setChecked(select)
        if self.spatial_shallow_n_chbox.isEnabled():
            self.spatial_shallow_n_chbox.setChecked(select)
        if self.spatial_tolerance_chbox.isEnabled():
            self.spatial_tolerance_chbox.setChecked(select)
        if self.spatial_froude_chbox.isEnabled():
            self.spatial_froude_chbox.setChecked(select)
        if self.spatial_steep_slopen_chbox.isEnabled():
            self.spatial_steep_slopen_chbox.setChecked(select)
        if self.spatial_lid_volume_chbox.isEnabled():
            self.spatial_lid_volume_chbox.setChecked(select)
        if self.mannings_n_and_Topo_chbox.isEnabled():
            self.mannings_n_and_Topo_chbox.setChecked(select)
