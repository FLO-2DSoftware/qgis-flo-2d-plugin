# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import traceback

from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication
from qgis.core import QgsFeatureRequest
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QInputDialog

from .table_editor_widget import StandardItemModel, StandardItem
from ..flo2d_tools.schematic_tools import FloodplainXS
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from .ui_utils import center_canvas, load_ui, set_icon, switch_to_selected

uiDialog, qtBaseClass = load_ui("fpxsec_editor")


class FPXsecEditorWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs, plot, table):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.con = None
        self.gutils = None
        self.fpxsec_lyr = None
        self.plot = plot
        self.uc = UserCommunication(iface, "FLO-2D")
        self.table = table
        self.tview = table.tview

        self.system_units = {
            "CMS": ["m", "mps", "cms"],
            "CFS": ["ft", "fps", "cfs"]
             }

        # set button icons
        set_icon(self.add_user_fpxs_btn, "add_fpxs.svg")
        set_icon(self.save_changes_btn, "mActionSaveAllEdits.svg")
        set_icon(self.revert_changes_btn, "mActionUndo.svg")
        set_icon(self.delete_fpxs_btn, "mActionDeleteSelected.svg")
        set_icon(self.schem_fpxs_btn, "schematize_fpxs.svg")
        set_icon(self.rename_fpxs_btn, "change_name.svg")
        parent_dir = os.path.dirname(os.path.abspath(__file__))
        idir = os.path.join(os.path.dirname(parent_dir), "img")
        for i in range(8):
            icon_file = "arrow_{}.svg".format(i + 1)
            self.flow_dir_cbo.setItemIcon(i, QIcon(os.path.join(idir, icon_file)))

        # connections
        self.add_user_fpxs_btn.clicked.connect(self.create_user_fpxs)
        self.save_changes_btn.clicked.connect(self.save_fpxs_lyr_edits)
        self.revert_changes_btn.clicked.connect(self.revert_fpxs_lyr_edits)
        self.delete_fpxs_btn.clicked.connect(self.delete_cur_fpxs)
        self.schem_fpxs_btn.clicked.connect(self.schematize_fpxs)
        self.rename_fpxs_btn.clicked.connect(self.rename_fpxs)
        self.fpxs_cbo.activated.connect(self.cur_fpxs_changed)
        self.flow_dir_cbo.activated.connect(self.save_fpxs)

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
            self.fpxsec_lyr = self.lyrs.data["user_fpxsec"]["qlyr"]
            self.report_chbox.setEnabled(True)
            nxprt = self.gutils.get_cont_par("NXPRT")
            if nxprt == "0":
                self.report_chbox.setChecked(False)
            elif nxprt == "1":
                self.report_chbox.setChecked(True)
            else:
                self.report_chbox.setChecked(False)
                self.set_report()
            self.report_chbox.stateChanged.connect(self.set_report)
            self.fpxsec_lyr.selectionChanged.connect(self.switch2selected)
            self.fpxsec_lyr.editingStopped.connect(self.populate_cbos)

    def switch2selected(self):
        switch_to_selected(self.fpxsec_lyr, self.fpxs_cbo)
        self.cur_fpxs_changed()

    def populate_cbos(self, fid=None, show_last_edited=True):
        self.fpxs_cbo.clear()
        qry = """SELECT fid, name, iflo FROM user_fpxsec ORDER BY name COLLATE NOCASE"""
        rows = self.gutils.execute(qry).fetchall()
        max_fid = self.gutils.get_max("user_fpxsec")
        cur_idx = 0
        for i, row in enumerate(rows):
            self.fpxs_cbo.addItem(row[1], row)
            if fid and row[0] == fid:
                cur_idx = i
            elif show_last_edited and row[0] == max_fid:
                cur_idx = i
        self.fpxs_cbo.setCurrentIndex(cur_idx)
        self.cur_fpxs_changed()

    def cur_fpxs_changed(self):
        row = self.fpxs_cbo.itemData(self.fpxs_cbo.currentIndex())
        if row is None:
            return
        self.fpxs_fid = row[0]
        row_flo = row[-1]
        flow_idx = row_flo - 1 if row_flo is not None else 0
        self.flow_dir_cbo.setCurrentIndex(flow_idx)
        self.lyrs.clear_rubber()
        if self.center_fpxs_chbox.isChecked():
            self.show_fpxs_rb()
            feat = next(self.fpxsec_lyr.getFeatures(QgsFeatureRequest(self.fpxs_fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def show_fpxs_rb(self):
        if not self.fpxs_fid:
            return
        self.lyrs.show_feat_rubber(self.fpxsec_lyr.id(), self.fpxs_fid)

    def create_user_fpxs(self):
        self.lyrs.enter_edit_mode("user_fpxsec")

    def save_fpxs_lyr_edits(self):
        if not self.lyrs.any_lyr_in_edit("user_fpxsec"):
            return
        self.lyrs.save_lyrs_edits("user_fpxsec")

    def rename_fpxs(self):
        if not self.fpxs_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, "Change name", "New name:")
        if not ok or not new_name:
            return
        if not self.fpxs_cbo.findText(new_name) == -1:
            msg = "WARNING 060319.1704: Floodplain cross-sections with name {} already exists in the database. Please, choose another name."
            msg = msg.format(new_name)
            self.uc.show_warn(msg)
            return
        self.fpxs_cbo.setItemText(self.fpxs_cbo.currentIndex(), new_name)
        self.save_fpxs()

    def revert_fpxs_lyr_edits(self):
        user_fpxs_edited = self.lyrs.rollback_lyrs_edits("user_fpxsec")
        if user_fpxs_edited:
            self.populate_cbos()

    def delete_cur_fpxs(self):
        if not self.fpxs_cbo.count():
            return
        q = "Are you sure, you want delete the current floodplain cross-section?"
        if not self.uc.question(q):
            return
        self.gutils.execute("DELETE FROM user_fpxsec WHERE fid = ?;", (self.fpxs_fid,))
        self.fpxsec_lyr.triggerRepaint()
        self.populate_cbos()

    def save_fpxs(self):
        if not self.fpxs_cbo.count():
            return
        row = self.fpxs_cbo.itemData(self.fpxs_cbo.currentIndex())
        fid = row[0]
        name = self.fpxs_cbo.currentText()
        iflo = self.flow_dir_cbo.currentText()
        qry = "UPDATE user_fpxsec SET name = ?, iflo = ? WHERE fid = ?;"
        if fid > 0:
            self.gutils.execute(
                qry,
                (
                    name,
                    iflo,
                    fid,
                ),
            )
        self.populate_cbos(fid=fid)

    def schematize_fpxs(self):
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return
        if self.gutils.is_table_empty("user_fpxsec"):
            self.uc.bar_warn(
                "There is no any user floodplain cross sections! " "Please digitize them before running the tool."
            )
            return
        try:
            fpxs = FloodplainXS(self.con, self.iface, self.lyrs)
            fpxs.schematize_floodplain_xs()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn(
                "WARNING 060319.1705: Process failed on schematizing floodplain cross-sections! "
                "Please check your User Layers."
            )
            return
        self.uc.show_info("Floodplain cross-sections schematized!")

    def set_report(self):
        if self.report_chbox.isChecked():
            self.gutils.set_cont_par("NXPRT", "1")
        else:
            self.gutils.set_cont_par("NXPRT", "0")

    def show_hydrograph(self, table, fid):
        """
        Function to load the hydrograph and flododplain hydraulics from HYCROSS.OUT
        """
        self.uc.clear_bar_messages()
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return False

        units = "CMS" if self.gutils.get_cont_par("METRIC") == "1" else "CFS"

        s = QSettings()

        HYCROSS_file = s.value("FLO-2D/lastHYCROSSFile", "")
        GDS_dir = s.value("FLO-2D/lastGdsDir", "")
        # Check if there is an HYCROSS.OUT file on the FLO-2D QSettings
        if not os.path.isfile(HYCROSS_file):
            HYCROSS_file = GDS_dir + r"/HYCROSS.OUT"
            # Check if there is an HYCROSS.OUT file on the export folder
            if not os.path.isfile(HYCROSS_file):
                self.uc.bar_warn(
                    "No HYCROSS.OUT file found. Please ensure the simulation has completed and verify the project export folder.")
                return
        # Check if the HYCROSS.OUT has data on it
        if os.path.getsize(HYCROSS_file) == 0:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("File  '" + os.path.basename(HYCROSS_file) + "'  is empty!")
            return

        with open(HYCROSS_file, "r") as myfile:
            while True:
                time_list = []
                discharge_list = []
                flow_width_list = []
                wse_list = []
                line = next(myfile)
                if "THE MAXIMUM DISCHARGE FROM CROSS SECTION" in line:
                    if line.split()[6] == str(fid):
                        for _ in range(9):
                            line = next(myfile)
                        while True:
                            try:
                                line = next(myfile)
                                if not line.strip():
                                    break
                                line = line.split()
                                time_list.append(float(line[0]))
                                discharge_list.append(float(line[5]))
                                flow_width_list.append(float(line[1]))
                                wse_list.append(float(line[3]))
                            except StopIteration:
                                break
                        break

        self.plot.clear()
        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)

        self.plot.plot.legend = None
        self.plot.plot.addLegend(offset=(0, 30))
        self.plot.plot.setTitle(title=f"Floodplain Cross Section - {fid}")
        self.plot.plot.setLabel("bottom", text="Time (hrs)")
        self.plot.plot.setLabel("left", text="")
        self.plot.add_item(f"Discharge ({self.system_units[units][2]})", [time_list, discharge_list], col=QColor(Qt.darkYellow), sty=Qt.SolidLine)
        self.plot.add_item(f"Flow Width ({self.system_units[units][0]})", [time_list, flow_width_list], col=QColor(Qt.black), sty=Qt.SolidLine, hide=True)
        self.plot.add_item(f"Water Surface Elevation ({self.system_units[units][0]})", [time_list, wse_list], col=QColor(Qt.darkGreen), sty=Qt.SolidLine, hide=True)

        try:  # Build table.
            discharge_data_model = StandardItemModel()
            self.tview.undoStack.clear()
            self.tview.setModel(discharge_data_model)
            discharge_data_model.clear()
            discharge_data_model.setHorizontalHeaderLabels(["Time (hours)",
                                                            f"Discharge ({self.system_units[units][2]})",
                                                            f"Flow Width ({self.system_units[units][0]})",
                                                            f"Water Surface Elevation ({self.system_units[units][0]})"])

            data = zip(time_list, discharge_list, flow_width_list, wse_list)
            for time, discharge, flow, wse in data:
                time_item = StandardItem("{:.2f}".format(time)) if time is not None else StandardItem("")
                discharge_item = StandardItem("{:.2f}".format(discharge)) if discharge is not None else StandardItem("")
                flow_item = StandardItem("{:.2f}".format(flow)) if flow is not None else StandardItem("")
                wse_item = StandardItem("{:.2f}".format(wse)) if wse is not None else StandardItem("")
                discharge_data_model.appendRow([time_item, discharge_item, flow_item, wse_item])

            self.tview.horizontalHeader().setStretchLastSection(True)
            for col in range(3):
                self.tview.setColumnWidth(col, 100)
            for i in range(discharge_data_model.rowCount()):
                self.tview.setRowHeight(i, 20)
            return
        except:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("Error while building table for hydraulic structure discharge!")
            return

    def show_cells_hydrograph(self, table, fid):
        """
        Function to load the floodplain cells hydrograph from CROSSQ.OUT
        """
        self.uc.clear_bar_messages()
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return False

        units = "CMS" if self.gutils.get_cont_par("METRIC") == "1" else "CFS"

        s = QSettings()

        CROSSQ_file = s.value("FLO-2D/lastCROSSQFile", "")
        GDS_dir = s.value("FLO-2D/lastGdsDir", "")
        # Check if there is a CROSSQ.OUT file on the FLO-2D QSettings
        if not os.path.isfile(CROSSQ_file):
            CROSSQ_file = GDS_dir + r"/CROSSQ.OUT"
            # Check if there is a CROSSQ.OUT file on the export folder
            if not os.path.isfile(CROSSQ_file):
                self.uc.bar_warn(
                    "No CROSSQ.OUT file found. Please ensure the simulation has completed and verify the project export folder.")
                return
        # Check if the CROSSQ.OUT has data on it
        if os.path.getsize(CROSSQ_file) == 0:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("File  '" + os.path.basename(CROSSQ_file) + "'  is empty!")
            return

        grid_fid = self.gutils.execute(f"SELECT grid_fid FROM fpxsec_cells WHERE fid = '{fid}'").fetchone()[0]

        with open(CROSSQ_file, "r") as myfile:
            while True:
                time_list = []
                discharge_list = []
                line = next(myfile)
                if len(line.split()) == 3 and line.split()[0] == str(grid_fid):
                    time_list.append(float(line.split()[1]))
                    discharge_list.append(float(line.split()[2]))
                    while True:
                        try:
                            line = next(myfile)
                            if len(line.split()) == 3:
                                break
                            time_list.append(float(line.split()[0]))
                            discharge_list.append(float(line.split()[1]))
                        except StopIteration:
                            break
                    break

        self.plot.clear()
        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)

        self.plot.plot.legend = None
        self.plot.plot.addLegend(offset=(0, 30))
        self.plot.plot.setTitle(title=f"Floodplain Cell - {grid_fid}")
        self.plot.plot.setLabel("bottom", text="Time (hrs)")
        self.plot.plot.setLabel("left", text="")
        self.plot.add_item(f"Discharge ({self.system_units[units][2]})", [time_list, discharge_list], col=QColor(Qt.darkYellow), sty=Qt.SolidLine)

        try:  # Build table.
            discharge_data_model = StandardItemModel()
            self.tview.undoStack.clear()
            self.tview.setModel(discharge_data_model)
            discharge_data_model.clear()
            discharge_data_model.setHorizontalHeaderLabels(["Time (hours)",
                                                            f"Discharge ({self.system_units[units][2]})"])

            data = zip(time_list, discharge_list)
            for time, discharge in data:
                time_item = StandardItem("{:.2f}".format(time)) if time is not None else StandardItem("")
                discharge_item = StandardItem("{:.2f}".format(discharge)) if discharge is not None else StandardItem("")
                discharge_data_model.appendRow([time_item, discharge_item])

            self.tview.horizontalHeader().setStretchLastSection(True)
            for col in range(3):
                self.tview.setColumnWidth(col, 100)
            for i in range(discharge_data_model.rowCount()):
                self.tview.setRowHeight(i, 20)
            return
        except:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("Error while building table for hydraulic structure discharge!")
            return