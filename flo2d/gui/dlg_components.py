# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright ? 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os

from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtWidgets import QApplication

from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from .ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("components")


class ComponentsDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs, in_or_out):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)

        QApplication.setOverrideCursor(Qt.WaitCursor)

        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.uc = UserCommunication(iface, "FLO-2D")
        self.gutils = GeoPackageUtils(con, iface)
        self.current_lyr = None
        self.components = []
        self.in_or_out = in_or_out

        self.components_buttonBox.accepted.connect(self.select_components)
        self.select_all_chbox.clicked.connect(self.unselect_all)

        self.setFixedSize(self.size())

        self.populate_components_dialog()

        QApplication.restoreOverrideCursor()

    def populate_components_dialog(self):
        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")
        self.file_lbl.setText(last_dir)

        if self.in_or_out == "in":
            self.setWindowTitle("FLO-2D Components to Import")
            self.components_note_lbl.setVisible(False)
            self.mannings_n_and_Topo_chbox.setVisible(False)

            if os.path.isfile(last_dir + r"\CHAN.DAT"):
                if os.path.getsize(last_dir + r"\CHAN.DAT") > 0:
                    self.channels_chbox.setChecked(True)
                    self.channels_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\ARF.DAT"):
                if os.path.getsize(last_dir + r"\ARF.DAT") > 0:
                    self.reduction_factors_chbox.setChecked(True)
                    self.reduction_factors_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\STREET.DAT"):
                if os.path.getsize(last_dir + r"\STREET.DAT") > 0:
                    self.streets_chbox.setChecked(True)
                    self.streets_chbox.setEnabled(True)

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
                    self.levees_chbox.setChecked(True)
                    self.levees_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\MULT.DAT"):
                if os.path.getsize(last_dir + r"\MULT.DAT") > 0:
                    self.multiple_channels_chbox.setChecked(True)
                    self.multiple_channels_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\SIMPLE_MULT.DAT"):
                if os.path.getsize(last_dir + r"\SIMPLE_MULT.DAT") > 0:
                    self.multiple_channels_chbox.setChecked(True)
                    self.multiple_channels_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\BREACH.DAT"):
                if os.path.getsize(last_dir + r"\BREACH.DAT") > 0:
                    self.breach_chbox.setChecked(True)
                    self.breach_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\GUTTER.DAT"):
                if os.path.getsize(last_dir + r"\GUTTER.DAT") > 0:
                    self.gutters_chbox.setChecked(True)
                    self.gutters_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\INFIL.DAT"):
                if os.path.getsize(last_dir + r"\INFIL.DAT") > 0:
                    self.infiltration_chbox.setChecked(True)
                    self.infiltration_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\FPXSEC.DAT"):
                if os.path.getsize(last_dir + r"\FPXSEC.DAT") > 0:
                    self.floodplain_xs_chbox.setChecked(True)
                    self.floodplain_xs_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\SED.DAT"):
                if os.path.getsize(last_dir + r"\SED.DAT") > 0:
                    self.mud_and_sed_chbox.setChecked(True)
                    self.mud_and_sed_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\EVAPOR.DAT"):
                if os.path.getsize(last_dir + r"\EVAPOR.DAT") > 0:
                    self.evaporation_chbox.setChecked(True)
                    self.evaporation_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\HYSTRUC.DAT"):
                if os.path.getsize(last_dir + r"\HYSTRUC.DAT") > 0:
                    self.hydr_struct_chbox.setChecked(True)
                    self.hydr_struct_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\RAIN.DAT"):
                if os.path.getsize(last_dir + r"\RAIN.DAT") > 0:
                    self.rain_chbox.setChecked(True)
                    self.rain_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\SWMMFLO.DAT"):
                if os.path.getsize(last_dir + r"\SWMMFLO.DAT") > 0:
                    self.storm_drain_chbox.setChecked(True)
                    self.storm_drain_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\TOLSPATIAL.DAT"):
                if os.path.getsize(last_dir + r"\TOLSPATIAL.DAT") > 0:
                    self.spatial_tolerance_chbox.setChecked(True)
                    self.spatial_tolerance_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\FPFROUDE.DAT"):
                if os.path.getsize(last_dir + r"\FPFROUDE.DAT") > 0:
                    self.spatial_froude_chbox.setChecked(True)
                    self.spatial_froude_chbox.setEnabled(True)

        elif self.in_or_out == "out":
            self.setWindowTitle("FLO-2D Components to Export")

            sql = """SELECT name, value FROM cont;"""
            options = {o: v if v is not None else "" for o, v in self.gutils.execute(sql).fetchall()}

            if options["ICHANNEL"] == "0":
                self.channels_chbox.setText("*" + self.channels_chbox.text() + "*")

            if options["IEVAP"] == "0":
                self.evaporation_chbox.setText("*" + self.evaporation_chbox.text() + "*")

            if options["IHYDRSTRUCT"] == "0":
                self.hydr_struct_chbox.setText("*" + self.hydr_struct_chbox.text() + "*")

            if options["IMULTC"] == "0":
                self.multiple_channels_chbox.setText("*" + self.multiple_channels_chbox.text() + "*")

            if options["INFIL"] == "0":
                self.infiltration_chbox.setText("*" + self.infiltration_chbox.text() + "*")

            if options["IRAIN"] == "0":
                self.rain_chbox.setText("*" + self.rain_chbox.text() + "*")

            if options["ISED"] == "0" and options["MUD"] == "0":
                self.mud_and_sed_chbox.setText("*" + self.mud_and_sed_chbox.text() + "*")

            if options["IWRFS"] == "0":
                self.reduction_factors_chbox.setText("*" + self.reduction_factors_chbox.text() + "*")

            if options["LEVEE"] == "0":
                self.levees_chbox.setText("*" + self.levees_chbox.text() + "*")

            if options["MSTREET"] == "0":
                self.streets_chbox.setText("*" + self.streets_chbox.text() + "*")

            if options["SWMM"] == "0":
                self.storm_drain_chbox.setText("*" + self.storm_drain_chbox.text() + "*")

            self.components_note_lbl.setVisible(True)

            if not self.gutils.is_table_empty("chan"):
                self.channels_chbox.setChecked(True)
                self.channels_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("blocked_cells"):
                self.reduction_factors_chbox.setChecked(True)
                self.reduction_factors_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("streets"):
                self.streets_chbox.setChecked(True)
                self.streets_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("outflow_cells"):
                self.outflow_elements_chbox.setChecked(True)
                self.outflow_elements_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("inflow") or not self.gutils.is_table_empty("reservoirs"):
                self.inflow_elements_chbox.setChecked(True)
                self.inflow_elements_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("levee_data"):
                self.levees_chbox.setChecked(True)
                self.levees_chbox.setEnabled(True)

            # Multiple channels:
            if options["IMULTC"] == "1":
                if self.gutils.is_table_empty("mult_cells") and self.gutils.is_table_empty("simple_mult_cells"):
                    QApplication.restoreOverrideCursor()
                    self.uc.show_info(
                        "WARNING 130222.0843: there aren't mult channels or simple mult channels in the project!\n\nThe IMULTC switch will be turned off."
                    )
                    self.gutils.set_cont_par("IMULTC", 0)
                    # self.multiple_channels_chbox.setChecked(False)
                    # self.multiple_channels_chbox.setEnabled(False)
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                else:  # There are Mult or simple channels cells:
                    if self.gutils.is_table_empty("mult"):
                        # There are mult or simple channels but 'mult' (globals) is empty: set globals:
                        self.gutils.fill_empty_mult_globals()
                    self.multiple_channels_chbox.setChecked(True)
                    self.multiple_channels_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("breach"):
                self.breach_chbox.setChecked(True)
                self.breach_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("gutter_cells"):
                self.gutters_chbox.setChecked(True)
                self.gutters_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("infil"):
                self.infiltration_chbox.setChecked(True)
                self.infiltration_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("fpxsec"):
                self.floodplain_xs_chbox.setChecked(True)
                self.floodplain_xs_chbox.setEnabled(True)

            # Mud and Sediment Transport:
            ISED = self.gutils.get_cont_par("ISED")
            MUD = self.gutils.get_cont_par("MUD")
            if ISED == "1" or MUD in ["1", "2"]:
                if not self.gutils.is_table_empty("mud") or not self.gutils.is_table_empty("sed"):
                    self.mud_and_sed_chbox.setChecked(True)
                    self.mud_and_sed_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("evapor"):
                self.evaporation_chbox.setChecked(True)
                self.evaporation_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("struct"):
                self.hydr_struct_chbox.setChecked(True)
                self.hydr_struct_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("rain"):
                self.rain_chbox.setChecked(True)
                self.rain_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("swmmflo"):
                self.storm_drain_chbox.setChecked(True)
                self.storm_drain_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("spatialshallow") and not self.gutils.is_table_empty(
                "spatialshallow_cells"
            ):
                self.spatial_shallow_n_chbox.setChecked(True)
                self.spatial_shallow_n_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("tolspatial"):
                self.spatial_tolerance_chbox.setChecked(True)
                self.spatial_tolerance_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("fpfroude"):
                self.spatial_froude_chbox.setChecked(True)
                self.spatial_froude_chbox.setEnabled(True)

            if not self.gutils.is_table_empty("grid"):
                self.mannings_n_and_Topo_chbox.setChecked(True)
                self.mannings_n_and_Topo_chbox.setEnabled(True)

        else:
            QApplication.restoreOverrideCursor()
            self.uc.show_info("ERROR 240619.0704: Wrong components in/out selection!")

    def select_components(self):
        if self.channels_chbox.isChecked():
            self.components.append("Channels")

        if self.reduction_factors_chbox.isChecked():
            self.components.append("Reduction Factors")

        if self.streets_chbox.isChecked():
            self.components.append("Streets")

        if self.outflow_elements_chbox.isChecked():
            self.components.append("Outflow Elements")

        if self.inflow_elements_chbox.isChecked():
            self.components.append("Inflow Elements")

        if self.levees_chbox.isChecked():
            self.components.append("Levees")

        if self.multiple_channels_chbox.isChecked():
            self.components.append("Multiple Channels")

        if self.breach_chbox.isChecked():
            self.components.append("Breach")

        if self.gutters_chbox.isChecked():
            self.components.append("Gutters")

        if self.infiltration_chbox.isChecked():
            self.components.append("Infiltration")

        if self.floodplain_xs_chbox.isChecked():
            self.components.append("Floodplain Cross Sections")

        if self.mud_and_sed_chbox.isChecked():
            self.components.append("Mudflow and Sediment Transport")

        if self.evaporation_chbox.isChecked():
            self.components.append("Evaporation")

        if self.hydr_struct_chbox.isChecked():
            self.components.append("Hydraulic  Structures")

        if self.mudflo_chbox.isChecked():
            self.components.append("MODFLO-2D")

        if self.rain_chbox.isChecked():
            self.components.append("Rain")

        if self.storm_drain_chbox.isChecked():
            self.components.append("Storm Drain")

        if self.spatial_shallow_n_chbox.isChecked():
            self.components.append("Spatial Shallow-n")

        if self.spatial_tolerance_chbox.isChecked():
            self.components.append("Spatial Tolerance")

        if self.spatial_froude_chbox.isChecked():
            self.components.append("Spatial Froude")

        if self.mannings_n_and_Topo_chbox.isChecked():
            self.components.append("Manning's n and Topo")

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
        if self.mannings_n_and_Topo_chbox.isEnabled():
            self.mannings_n_and_Topo_chbox.setChecked(select)
