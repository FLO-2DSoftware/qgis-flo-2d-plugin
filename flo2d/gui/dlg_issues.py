# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os, time
from qgis.core import *
from qgis.PyQt.QtCore import Qt, QSettings, QVariant, QModelIndex
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY
from qgis.PyQt.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QInputDialog,
    QFileDialog,
    QProgressDialog,
    QPushButton,
    QTableWidgetItem,
    QListView,
    QComboBox,
    QTableView,
    QCompleter,
    QTableWidget,
    qApp,
)
from .ui_utils import load_ui, set_icon, center_canvas, zoom, zoom_show_n_cells
from .table_editor_widget import StandardItemModel, StandardItem
from ..utils import copy_tablewidget_selection
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..gui.dlg_sampling_elev import SamplingElevDialog
from ..gui.dlg_sampling_buildings_elevations import SamplingBuildingsElevationsDialog
from ..flo2d_tools.grid_tools import grid_has_empty_elev, get_adjacent_cell_elevation
from qgis.PyQt.QtGui import QColor


# from ..flo2d_tools.conflicts import Conflicts

uiDialog, qtBaseClass = load_ui("errors_2")


class ErrorsDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None
        self.errors = []
        self.debug_directory = ""

        self.setup_connection()
        #         self.create_conflicts_layer_chck.setVisible(False)
        self.errors_OK_btn.accepted.connect(self.errors_OK)

    #         self.debug_file_radio.clicked.connect(self.DEBUG_file_clicked)
    #         self.current_project_radio.clicked.connect(self.current_project_clicked)

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def import_DEBUG_file(self):
        DEBUG_dir = QFileDialog.getExistingDirectory(
            None, "Select FLO-2D program folder", directory=self.debug_file_lineEdit.text()
        )
        if not DEBUG_dir:
            return
        self.debug_file_lineEdit.setText(DEBUG_dir)
        s = QSettings()
        s.setValue("FLO-2D/last_DEBUG", DEBUG_dir)

    def errors_OK(self):
        if self.current_project_radio.isChecked():
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                dlg_conflicts = CurrentConflictsDialog(self.con, self.iface, self.lyrs, "1000000", "All", "All")
                QApplication.restoreOverrideCursor()
                dlg_conflicts.exec_()
                self.lyrs.clear_rubber()
                return True
            except ValueError:
                # Forced error during contructor to stop showing dialog.
                pass
        elif self.debug_file_radio.isChecked():
            try:
                dlg_issues = IssuesFromDEBUGDialog(self.con, self.iface, self.lyrs)
                dlg_issues.exec_()
                self.lyrs.clear_rubber()
                QApplication.restoreOverrideCursor()

            except ValueError:
                # Forced error during contructor to stop showing dialog.
                QApplication.restoreOverrideCursor()
                pass

        else:  # Levee crests:
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                dlg_levee_crests = LeveeCrestsDialog(self.con, self.iface, self.lyrs)
                QApplication.restoreOverrideCursor()
                dlg_levee_crests.exec_()
                self.lyrs.clear_rubber()
                return True
            except ValueError:
                # Forced error during contructor to stop showing dialog.
                pass


uiDialog, qtBaseClass = load_ui("issues")


class IssuesFromDEBUGDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None
        self.ext = self.iface.mapCanvas().extent()
        self.n_grid_issues = 1000
        self.errors = []
        self.cells = []
        self.currentCell = None
        self.debug_directory = ""
        set_icon(self.find_cell_btn, "eye-svgrepo-com.svg")
        set_icon(self.zoom_in_btn, "zoom_in.svg")
        set_icon(self.zoom_out_btn, "zoom_out.svg")
        set_icon(self.previous_grid_issues_btn, "arrow_4.svg")
        set_icon(self.next_grid_issues_btn, "arrow_2.svg")
        self.previous_grid_issues_lbl.setText("Previous " + str(self.n_grid_issues))
        self.next_grid_issues_lbl.setText("Next " + str(self.n_grid_issues))

        self.setup_connection()
        self.issues_codes_cbo.activated.connect(self.codes_cbo_activated)
        self.errors_cbo.activated.connect(self.errors_cbo_activated)
        self.elements_cbo.activated.connect(self.elements_cbo_activated)
        self.find_cell_btn.clicked.connect(self.find_cell_clicked)
        self.description_tblw.cellClicked.connect(self.description_tblw_cell_clicked)
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        self.next_grid_issues_btn.clicked.connect(self.load_next_combo)
        self.previous_grid_issues_btn.clicked.connect(self.load_previous_combo)

        self.previous_grid_issues_lbl.setVisible(False)
        self.next_grid_issues_lbl.setVisible(False)
        self.previous_grid_issues_btn.setVisible(False)
        self.next_grid_issues_btn.setVisible(False)

        self.description_tblw.setSortingEnabled(False)
        self.description_tblw.setColumnWidth(2, 550)
        self.description_tblw.resizeRowsToContents()

        if not self.populate_issues():
            raise ValueError("Not a legal file!")
        else:

            #             self.populate_elements_cbo()
            self.populate_errors_cbo()

            self.issues_codes_cbo.setCurrentIndex(1)
            self.loadIssues()

            if self.currentCell:
                x, y = self.currentCell.geometry().centroid().asPoint()
                center_canvas(self.iface, x, y)
                cell_size = float(self.gutils.get_cont_par("CELLSIZE"))
                zoom_show_n_cells(iface, cell_size, 30)
                self.update_extent()

            self.import_other_issues_files()

            self.uc.clear_bar_messages()
            QApplication.restoreOverrideCursor()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_issues(self):
        """
        Reads DEBUG file.
        """
        self.uc.clear_bar_messages()

        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return False
        s = QSettings()

        last_dir = s.value("FLO-2D/lastDEBUGDir", s.value("FLO-2D/lastGdsDir"))
        debug_file, __ = QFileDialog.getOpenFileName(
            None, "Select DEBUG file to import", directory=last_dir, filter="(DEBUG* debug*"
        )
        if not debug_file:
            return False

        try:
            if not os.path.isfile(debug_file):
                self.uc.show_warn(os.path.basename(debug_file) + " is being used by another process!")
                return False
            elif os.path.getsize(debug_file) == 0:
                self.uc.show_warn(os.path.basename(debug_file) + " is empty!")
                return False
            else:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                qApp.processEvents()
                features = []
                grid = self.lyrs.data["grid"]["qlyr"]
                s.setValue("FLO-2D/lastDEBUGDir", debug_file)
                self.debug_directory = os.path.dirname(debug_file)

                self.elements_cbo.clear()
                self.elements_cbo.addItem(" ")

                self.errors_cbo.clear()
                self.errors_cbo.addItem(" ")

                seen = set(self.cells)
                with open(debug_file, "r") as f1:
                    for line in f1:
                        row = line.split(",")
                        if len(row) >= 3:
                            cell = row[0].strip()
                            iCell = int(cell)
                            if iCell <= 0:
                                iCell = 1
                                cell = "1"
                            if len(grid) >= iCell and iCell > 0:

                                description = ", ".join(row[2:]).strip()
                                self.errors.append([cell, row[1].strip(), description])
                                #                                 self.errors.append([cell, row[1].strip(), row[2].strip()])
                                # Create points for issues layer:
                                if cell not in seen:
                                    seen.add(cell)
                                    self.cells.append(iCell)
                                    feat = next(grid.getFeatures(QgsFeatureRequest(iCell)))
                                    x, y = feat.geometry().centroid().asPoint()
                                    features.append([x, y, iCell, description])  # x, y, cell, description
                #                                     features.append( [x, y, iCell, row[2].strip()] ) # x, y, cell, description

                shapefile = self.debug_directory + "/DEBUG.shp"
                name = "DEBUG"
                fields = [["cell", "I"], ["description", "S"]]
                if self.create_points_shapefile(shapefile, name, fields, features):
                    vlayer = self.iface.addVectorLayer(shapefile, "", "ogr")

                self.cells.sort()
                for cell in self.cells:
                    self.elements_cbo.addItem(str(cell))

                if self.errors:
                    QApplication.restoreOverrideCursor()
                    self.setWindowTitle(
                        str(len(self.errors))
                        + " Errors and Warnings in "
                        + os.path.basename(debug_file)
                        + " for "
                        + str(len(self.cells))
                        + " cells"
                    )
                    return True
                else:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_warn(
                        "There are no debug errors reported in file "
                        + os.path.basename(debug_file)
                        + ".\nIs its format correct?"
                    )
                    return False
        except UnicodeDecodeError:
            # non-text dat:
            self.uc.show_warn(os.path.basename(debug_file) + " is not a text file!")
            return False

    def import_other_issues_files(self):
        dlg_issues_files = IssuesFiles(self.con, self.iface, self.lyrs)
        ok = dlg_issues_files.exec_()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        if ok:
            if dlg_issues_files.files:
                if "Depressed" in dlg_issues_files.files:
                    file = self.debug_directory + "/DEPRESSED_ELEMENTS.OUT"
                    if not os.path.isfile(file):
                        QApplication.restoreOverrideCursor()
                        self.uc.show_warn(
                            "WARNING 090420.0807: " + os.path.basename(file) + " is being used by another process!"
                        )
                    elif os.path.getsize(file) == 0:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_warn(os.path.basename(file) + " is empty!")
                    else:
                        lyr = self.lyrs.get_layer_by_name("Depressed Elements", self.lyrs.group)
                        try:
                            QApplication.setOverrideCursor(Qt.WaitCursor)
                            qApp.processEvents()
                            features = []
                            with open(file, "r") as f:
                                for _ in range(4):
                                    next(f)
                                for row in f:
                                    values = row.split()
                                    if values:
                                        self.errors.append(
                                            [
                                                values[0],
                                                "9001",
                                                "DEPRESSED_ELEMENTS.OUT : Depressed Element by " + values[3],
                                            ]
                                        )

                                        features.append(
                                            [values[1], values[2], values[0], values[3]]
                                        )  # x, y, cell, elev
                        except Exception as e:
                            QApplication.restoreOverrideCursor()
                            self.close()
                            self.uc.show_error("ERROR 170519.0700: error while reading \n" + file + "!\n", e)

                        finally:
                            if features:
                                shapefile = self.debug_directory + "/Depressed Elements.shp"
                                name = "Depressed Elements"
                                fields = [["cell", "I"], ["min_elev", "D"]]
                                if self.create_points_shapefile(shapefile, name, fields, features):
                                    vlayer = self.iface.addVectorLayer(shapefile, "", "ogr")
                                QApplication.restoreOverrideCursor()

                if "Channels" in dlg_issues_files.files:
                    file = self.debug_directory + "/CHANBANKEL.CHK"
                    if not os.path.isfile(file):
                        QApplication.restoreOverrideCursor()
                        self.uc.show_warn(
                            "WARNING 090420.0808: " + os.path.basename(file) + " is being used by another process!"
                        )
                    elif os.path.getsize(file) == 0:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_warn(os.path.basename(file) + " is empty!")
                    else:
                        lyr = self.lyrs.get_layer_by_name("Channel Bank Elev Differences", self.lyrs.group)
                        try:
                            QApplication.setOverrideCursor(Qt.WaitCursor)
                            qApp.processEvents()
                            features = []
                            with open(file, "r") as f:
                                for _ in range(6):
                                    next(f)
                                for row in f:
                                    values = row.split()
                                    if values:
                                        self.errors.append(
                                            [values[0], "9002", "CHANBANKEL.CHK : Bank - Floodplain = " + values[5]]
                                        )

                                        features.append(
                                            [
                                                values[1],
                                                values[2],
                                                values[0],
                                                values[3],
                                                values[4],
                                                values[5],
                                                values[6],
                                            ]
                                        )  # x, y, cell, etc

                        except Exception as e:
                            QApplication.restoreOverrideCursor()
                            self.close()
                            self.uc.show_error("ERROR 170519.0704: error while reading " + file + "!\n", e)

                        finally:
                            if features:
                                shapefile = self.debug_directory + "/Channel Bank Elev Differences.shp"
                                name = "Channel Bank Elev Differences"
                                fields = [
                                    ["cell", "I"],
                                    ["bank_elev", "D"],
                                    ["floodplain_elev", "D"],
                                    ["difference", "D"],
                                    ["LB_RB", "S"],
                                ]
                                if self.create_points_shapefile(shapefile, name, fields, features):
                                    vlayer = self.iface.addVectorLayer(shapefile, "", "ogr")
                                QApplication.restoreOverrideCursor()

                if "Rim" in dlg_issues_files.files:
                    file = self.debug_directory + "/FPRIMELEV.OUT"
                    if not os.path.isfile(file):
                        QApplication.restoreOverrideCursor()
                        self.uc.show_warn(
                            "WARNING 090420.0806: " + os.path.basename(file) + " is being used by another process!"
                        )
                    elif os.path.getsize(file) == 0:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_warn(os.path.basename(file) + " is empty!")
                    else:
                        lyr = self.lyrs.get_layer_by_name("Flooplain Rim Differences", self.lyrs.group)
                        try:
                            QApplication.setOverrideCursor(Qt.WaitCursor)
                            qApp.processEvents()
                            grid = self.lyrs.data["grid"]["qlyr"]
                            features = []
                            with open(file, "r") as f:
                                for _ in range(1):
                                    next(f)
                                for row in f:
                                    values = row.split()
                                    if values:
                                        if values[0] != "GRID":
                                            self.errors.append(
                                                [values[0], "9003", "FPRIMELEV.OUT : Floodplain - Rim = " + values[3]]
                                            )
                                            cell = int(values[0])
                                            feat = next(grid.getFeatures(QgsFeatureRequest(cell)))
                                            x, y = feat.geometry().centroid().asPoint()

                                            features.append(
                                                [x, y, values[0], values[1], values[2], values[3], values[4]]
                                            )  # x, y, cell, etc

                        except Exception as e:
                            QApplication.restoreOverrideCursor()
                            self.close()
                            self.uc.show_error("ERROR 170519.0705: error while reading " + file + "!\n", e)

                        finally:
                            if features:
                                shapefile = self.debug_directory + "/Flooplain Rim Differences.shp"
                                name = "Flooplain Rim Differences"
                                fields = [
                                    ["cell", "I"],
                                    ["floodplain_elev", "D"],
                                    ["rim_elev", "D"],
                                    ["difference", "D"],
                                    ["new_floodplain_elev", "D"],
                                ]
                                if self.create_points_shapefile(shapefile, name, fields, features):
                                    vlayer = self.iface.addVectorLayer(shapefile, "", "ogr")
                                QApplication.restoreOverrideCursor()

    def populate_elements_cbo(self):

        self.elements_cbo.clear()
        self.elements_cbo.addItem(" ")
        for x in self.errors:
            if self.elements_cbo.findText(x[0].strip()) == -1:
                self.elements_cbo.addItem(x[0].strip())

    #         self.elements_cbo.model().sort(0)

    #         self.uc.clear_bar_messages()
    #         QApplication.restoreOverrideCursor()

    def populate_errors_cbo(self):
        #         QApplication.setOverrideCursor(Qt.WaitCursor)

        singleErrors = []
        for x in self.errors:
            err = int(x[1].strip())
            if err not in singleErrors:
                singleErrors.append(err)

        singleErrors.sort()
        for error in singleErrors:
            self.errors_cbo.addItem(str(error))

    #         self.errors_cbo.clear()
    #         self.errors_cbo.addItem(" ")
    #         for x in self.errors:
    #             if self.errors_cbo.findText(x[1].strip()) == -1:
    #                 self.errors_cbo.addItem(x[1].strip())
    #         self.errors_cbo.model().sort(0)

    #         QApplication.restoreOverrideCursor()

    def codes_cbo_activated(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.loadIssues()
        QApplication.restoreOverrideCursor()

    def loadIssues(self):
        self.description_tblw.setRowCount(0)
        codes = self.issues_codes_cbo.currentText()
        if codes == "Depressed Elements (DEPRESSED_ELEMENTS.OUT)":
            self.uc.bar_info("Depressed Elements (DEPRESSED_ELEMENTS.OUT)", 2)
            codes = "9001"
        elif codes == "Channel <> Floodplain (CHANBANKEL.CHK)":
            self.uc.bar_info("Channel <> Floodplain (CHANBANKEL.CHK)", 2)
            codes = "9002"
        elif codes == "Floodplain <> Storm Drain Rim (FPRIMELEV.OUT)":
            self.uc.bar_info("Floodplain <> Storm Drain Rim (FPRIMELEV.OUT)", 2)
            codes = "9003"
        elif codes == "High Velocities (CHANSTABILITY.OUT)":
            self.uc.bar_info("High Velocities (CHANSTABILITY.OUT)", 2)
            codes = "9004"

        QApplication.setOverrideCursor(Qt.WaitCursor)
        qApp.processEvents()

        first, second = "", ""
        codes = codes.split(" ")
        for item in codes:
            if item != "":
                codes = item
                break
        if codes[0] != "":
            codes = codes.split("-")
            if len(codes) == 1:
                # There only one code.
                first = codes[0]
            else:
                first = codes[0]
                second = codes[1]

            if first.isdigit():
                for item in self.errors:
                    if second == "" and int(item[1]) == int(first):
                        rowPosition = self.description_tblw.rowCount()
                        self.description_tblw.insertRow(rowPosition)
                        itm = QTableWidgetItem()
                        itm.setData(Qt.EditRole, item[0].strip())
                        self.description_tblw.setItem(rowPosition, 0, itm)
                        itm = QTableWidgetItem()
                        itm.setData(Qt.EditRole, item[1].strip())
                        self.description_tblw.setItem(rowPosition, 1, itm)
                        itm = QTableWidgetItem()
                        itm.setData(Qt.EditRole, item[2])
                        self.description_tblw.setItem(rowPosition, 2, itm)
                    elif second != "" and int(item[1]) >= int(first) and int(item[1]) <= int(second):
                        rowPosition = self.description_tblw.rowCount()
                        self.description_tblw.insertRow(rowPosition)
                        itm = QTableWidgetItem()
                        itm.setData(Qt.EditRole, item[0].strip())
                        self.description_tblw.setItem(rowPosition, 0, itm)
                        itm = QTableWidgetItem()
                        itm.setData(Qt.EditRole, item[1].strip())
                        self.description_tblw.setItem(rowPosition, 1, itm)
                        itm = QTableWidgetItem()
                        itm.setData(Qt.EditRole, item[2])
                        self.description_tblw.setItem(rowPosition, 2, itm)
            elif first == "All":
                for item in self.errors:
                    rowPosition = self.description_tblw.rowCount()
                    self.description_tblw.insertRow(rowPosition)
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[0].strip())
                    self.description_tblw.setItem(rowPosition, 0, itm)
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[1].strip())
                    self.description_tblw.setItem(rowPosition, 1, itm)
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[2])
                    self.description_tblw.setItem(rowPosition, 2, itm)

            if self.description_tblw.rowCount() > 0:

                self.description_tblw.selectRow(0)
                cell = self.description_tblw.item(0, 0).text()
                self.find_cell(cell)
            else:
                self.lyrs.clear_rubber()

        self.errors_cbo.setCurrentIndex(0)
        self.elements_cbo.setCurrentIndex(0)
        if self.description_tblw.rowCount() > 0:
            self.description_tblw.selectRow(0)
            cell = self.description_tblw.item(0, 0).text()
            self.find_cell(cell)

        QApplication.restoreOverrideCursor()

    def elements_cbo_activated(self):
        self.description_tblw.setRowCount(0)
        nElems = self.elements_cbo.count()
        if nElems > 0:
            cell = self.elements_cbo.currentText().strip()
            for item in self.errors:
                if item[0].strip() == cell:
                    rowPosition = self.description_tblw.rowCount()
                    self.description_tblw.insertRow(rowPosition)
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[0].strip())
                    self.description_tblw.setItem(rowPosition, 0, itm)
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[1].strip())
                    self.description_tblw.setItem(rowPosition, 1, itm)
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[2])
                    self.description_tblw.setItem(rowPosition, 2, itm)

            self.find_cell(cell)
            self.errors_cbo.setCurrentIndex(0)
            self.issues_codes_cbo.setCurrentIndex(0)

    def errors_cbo_activated(self):
        self.description_tblw.setRowCount(0)
        nElems = self.errors_cbo.count()
        if nElems > 0:
            for item in self.errors:
                if item[1].strip() == self.errors_cbo.currentText().strip():
                    rowPosition = self.description_tblw.rowCount()
                    self.description_tblw.insertRow(rowPosition)
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[0].strip())
                    self.description_tblw.setItem(rowPosition, 0, itm)
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[1].strip())
                    self.description_tblw.setItem(rowPosition, 1, itm)
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[2])
                    self.description_tblw.setItem(rowPosition, 2, itm)
            self.elements_cbo.setCurrentIndex(0)
            self.issues_codes_cbo.setCurrentIndex(0)

    def load_next_combo(self):
        self.previous_grid_issues_btn.setEnabled(True)
        self.elements_cbo.setCurrentIndex(self.elements_cbo.count() - 1)
        last = self.elements_cbo.currentText()
        row = [y[0] for y in self.levee_rows].index(int(last))
        if len(self.levee_rows) > row:
            self.elements_cbo.clear()
            for i in range(row + 1, row + 1 + self.n_levees):
                if i == len(self.levee_rows):
                    self.next_grid_issues_btn.setEnabled(False)
                    break
                self.elements_cbo.addItem(str(self.levee_rows[i][0]))

    def load_previous_combo(self):
        self.next_grid_issues_btn.setEnabled(True)
        self.elements_cbo.setCurrentIndex(0)
        first = self.elements_cbo.currentText()
        row = [y[0] for y in self.levee_rows].index(int(first))
        self.elements_cbo.clear()
        for i in range(row - self.n_levees, row):
            self.elements_cbo.addItem(str(self.levee_rows[i][0]))
        if row - self.n_levees == 0:
            self.previous_grid_issues_btn.setEnabled(False)

    def find_cell_clicked(self):
        cell = self.elements_cbo.currentText()
        self.find_cell(cell)

    def find_cell(self, cell):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            grid = self.lyrs.data["grid"]["qlyr"]
            if grid is not None:
                if grid:
                    if cell != "":
                        cell = int(cell)
                        if len(grid) >= cell and cell > 0:
                            self.lyrs.show_feat_rubber(grid.id(), cell, QColor(Qt.yellow))
                            self.currentCell = next(grid.getFeatures(QgsFeatureRequest(cell)))
                            x, y = self.currentCell.geometry().centroid().asPoint()
                            if (
                                x < self.ext.xMinimum()
                                or x > self.ext.xMaximum()
                                or y < self.ext.yMinimum()
                                or y > self.ext.yMaximum()
                            ):
                                center_canvas(self.iface, x, y)
                                self.update_extent()
                        else:
                            if cell != -999:
                                self.uc.bar_warn("Cell " + str(cell) + " not found.", 2)
                                self.lyrs.clear_rubber()
                            else:
                                self.lyrs.clear_rubber()
                    else:
                        if cell.strip() != "-999" and cell.strip() != "":
                            self.uc.bar_warn("Cell " + str(cell) + " not found.", 2)
                            self.lyrs.clear_rubber()
                        else:
                            self.lyrs.clear_rubber()
        except ValueError:
            self.uc.bar_warn("Cell " + str(cell) + " is not valid.")
            self.lyrs.clear_rubber()
            pass
        finally:
            QApplication.restoreOverrideCursor()

    def description_tblw_cell_clicked(self, row, column):
        cell = self.sed_size_fraction_tblw.item(row, 0).text()
        self.find_cell(cell)

    def zoom_in(self):
        if self.currentCell:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = self.currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, 0.4)
            self.update_extent()
            QApplication.restoreOverrideCursor()

    def zoom_out(self):
        if self.currentCell:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = self.currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, -0.4)
            self.update_extent()
            QApplication.restoreOverrideCursor()

    def update_extent(self):
        self.ext = self.iface.mapCanvas().extent()

    def create_points_shapefile(self, shapefile, name, fields, features):
        try:
            lyr = QgsProject.instance().mapLayersByName(name)

            if lyr:
                QgsProject.instance().removeMapLayers([lyr[0].id()])

            # define fields for feature attributes. A QgsFields object is needed
            f = QgsFields()
            for field in fields:
                f.append(
                    QgsField(
                        field[0],
                        QVariant.Int if field[1] == "I" else QVariant.Double if field[1] == "D" else QVariant.String,
                    )
                )

            mapCanvas = self.iface.mapCanvas()
            my_crs = mapCanvas.mapSettings().destinationCrs()
            QgsVectorFileWriter.deleteShapeFile(shapefile)
            writer = QgsVectorFileWriter(shapefile, "system", f, QgsWkbTypes.Point, my_crs, "ESRI Shapefile")
            if writer.hasError() != QgsVectorFileWriter.NoError:
                self.uc.bar_error("ERROR 201919.0451: Error when creating shapefile: " + shapefile)

            # add features:
            for feat in features:
                attr = []
                fet = QgsFeature()
                fet.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(feat[0]), float(feat[1]))))
                non_coord_feats = []
                for i in range(2, len(fields) + 2):
                    non_coord_feats.append(
                        int(feat[i])
                        if fields[i - 2][1] == "I"
                        else float(feat[i])
                        if fields[i - 2][1] == "D"
                        else feat[i]
                    )

                fet.setAttributes(non_coord_feats)
                writer.addFeature(fet)

            # delete the writer to flush features to disk
            del writer
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 190519.0441: error while creating layer  " + name + "!\n", e)
            return False

    def load_shapefile(self, shapefile, layerName):
        try:
            vlayer = self.iface.addVectorLayer(shapefile, layerName, "ogr")

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 190519.2015: error while loading shapefile\n\n " + shapefile + "!\n", e)
            return False


uiDialog, qtBaseClass = load_ui("issues_files")


class IssuesFiles(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.uc = UserCommunication(iface, "FLO-2D")
        self.gutils = GeoPackageUtils(con, iface)
        self.current_lyr = None
        self.files = []

        self.complementary_files_buttonBox.accepted.connect(self.load_selected_complementary_files)
        self.setFixedSize(self.size())

        self.populate_complementary_files_dialog()

    def populate_complementary_files_dialog(self):
        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")

        if os.path.isfile(last_dir + r"\DEPRESSED_ELEMENTS.OUT"):
            self.depressed_elements_chbox.setChecked(True)
            self.depressed_elements_chbox.setEnabled(True)

        if os.path.isfile(last_dir + r"\CHANBANKEL.CHK"):
            self.chanbankel_chbox.setChecked(True)
            self.chanbankel_chbox.setEnabled(True)

        if os.path.isfile(last_dir + r"\FPRIMELEV.OUT"):
            self.fprimelev_chbox.setChecked(True)
            self.fprimelev_chbox.setEnabled(True)

    def load_selected_complementary_files(self):

        if self.depressed_elements_chbox.isChecked():
            self.files.append("Depressed")

        if self.chanbankel_chbox.isChecked():
            self.files.append("Channels")

        if self.fprimelev_chbox.isChecked():
            self.files.append("Rim")


uiDialog, qtBaseClass = load_ui("conflicts")


class CurrentConflictsDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs, numErrors=1000000, issue1="All", issue2="All"):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.numErrors = numErrors
        self.issue1 = issue1
        self.issue2 = issue2
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None
        self.errors = []
        self.ext = self.iface.mapCanvas().extent()
        self.currentCell = None
        self.debug_directory = ""
        set_icon(self.find_cell_btn, "eye-svgrepo-com.svg")
        set_icon(self.zoom_in_btn, "zoom_in.svg")
        set_icon(self.zoom_out_btn, "zoom_out.svg")
        set_icon(self.copy_btn, "copy.svg")

        self.setup_connection()
        self.component1_cbo.activated.connect(self.component1_cbo_activated)
        self.component2_cbo.activated.connect(self.component2_cbo_activated)
        self.errors_cbo.activated.connect(self.errors_cbo_activated)
        self.elements_cbo.activated.connect(self.elements_cbo_activated)
        self.find_cell_btn.clicked.connect(self.find_cell_clicked)
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        self.description_tblw.cellClicked.connect(self.description_tblw_cell_clicked)
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)

        self.description_tblw.setSortingEnabled(False)
        self.description_tblw.setColumnWidth(2, 450)
        self.description_tblw.resizeRowsToContents()

        self.populate_issues()
        self.populate_elements_cbo()
        self.populate_errors_cbo()
        self.errors_cbo.setCurrentIndex(0)
        self.errors_cbo_activated()

        self.component1_cbo.setCurrentIndex(1)
        self.loadIssuePairs()

        if self.currentCell:
            x, y = self.currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            cell_size = float(self.gutils.get_cont_par("CELLSIZE"))
            zoom_show_n_cells(iface, cell_size, 30)
            self.update_extent()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_issues(self):

        # Inflow conflicts:

        self.conflict4(
            "Inflows", "inflow_cells", "grid_fid", "Inflows", "inflow_cells", "grid_fid", "2 or more inflows"
        )

        self.conflict4(
            "Inflows",
            "inflow_cells",
            "grid_fid",
            "Outflows",
            "outflow_cells",
            "grid_fid",
            "Inflow and outflow in same cell",
        )

        self.conflict4(
            "Inflows",
            "inflow_cells",
            "grid_fid",
            "Reduction Factors",
            "blocked_cells",
            "grid_fid",
            "Inflow and Reduction Factors in same cell (check partial ARF, full ARF, or WRF)",
        )

        self.conflict4(
            "Inflows",
            "inflow_cells",
            "grid_fid",
            "Hydr. Structures",
            "struct",
            "inflonod",
            "Inflow and Hyd. Struct in-cell in same cell",
        )

        self.conflict4(
            "Inflows",
            "inflow_cells",
            "grid_fid",
            "Hydr. Structures",
            "struct",
            "outflonod",
            "Inflow and Hyd. Struct out-cell in same cell",
        )

        self.conflict4(
            "Inflows",
            "inflow_cells",
            "grid_fid",
            "Channels (Left Bank)",
            "chan_elems",
            "fid",
            "Inflow and Channel Left Bank in same cell",
        )

        self.conflict4(
            "Inflows",
            "inflow_cells",
            "grid_fid",
            "Channels (Right Bank)",
            "chan_elems",
            "rbankgrid",
            "Inflow and Channel Right Bank in same cell",
        )

        self.conflict4(
            "Inflows", "inflow_cells", "grid_fid", "Levees", "levee_data", "grid_fid", "Inflow and levee in same cell"
        )

        self.conflict4(
            "Inflows",
            "inflow_cells",
            "grid_fid",
            "Mult. Channels",
            "mult_cells",
            "grid_fid",
            "Inflow and Multiple Channels in same cell",
        )

        self.conflict4(
            "Inflows",
            "inflow_cells",
            "grid_fid",
            "Storm Drain Inlets",
            "swmmflo",
            "swmm_jt",
            "Inflow and Storm Drain Inlet in same cell",
        )

        self.conflict4(
            "Inflows",
            "inflow_cells",
            "grid_fid",
            "Storm Drain Outfalls",
            "swmmoutf",
            "grid_fid",
            "Inflow and Storm Drain Outfall in same cell",
        )

        # Outflow conflicts:
        self.conflict4(
            "Outflows", "outflow_cells", "grid_fid", "Outflows", "outflow_cells", "grid_fid", "2 or more outflows"
        )

        self.conflict4(
            "Outflows",
            "outflow_cells",
            "grid_fid",
            "Reduction Factors",
            "blocked_cells",
            "grid_fid",
            "Outflow and Reduction Factors in same cell (check partial ARF, full ARF, or WRF)",
        )

        self.conflict4(
            "Outflows",
            "outflow_cells",
            "grid_fid",
            "Hydr. Structures",
            "struct",
            "inflonod",
            "Outflow and Hyd. Struct in-cell in same cell",
        )

        self.conflict4(
            "Outflows",
            "outflow_cells",
            "grid_fid",
            "Hydr. Structures",
            "struct",
            "outflonod",
            "Outflow and Hyd. Struct out-cell in same cell",
        )

        self.conflict4(
            "Outflows",
            "outflow_cells",
            "grid_fid",
            "Channels (Left Bank)",
            "chan_elems",
            "fid",
            "Outflow and Channel Left Bank in same cell",
        )

        self.conflict4(
            "Outflows",
            "outflow_cells",
            "grid_fid",
            "Channels (Right Bank)",
            "chan_elems",
            "rbankgrid",
            "Outflow and Channel Right Bank in same cell",
        )

        self.conflict4(
            "Outflows",
            "outflow_cells",
            "grid_fid",
            "Levees",
            "levee_data",
            "grid_fid",
            "Outflow and levee in same cell",
        )

        self.conflict4(
            "Outflows",
            "outflow_cells",
            "grid_fid",
            "Mult. Channels",
            "mult_cells",
            "grid_fid",
            "Outflow and Multiple Channels in same cell",
        )

        self.conflict4(
            "Outflows",
            "outflow_cells",
            "grid_fid",
            "Storm Drain Inlets",
            "swmmflo",
            "swmm_jt",
            "Outflow and Storm Drain Inlet in same cell",
        )

        self.conflict4(
            "Outflows",
            "outflow_cells",
            "grid_fid",
            "Storm Drain Outfalls",
            "swmmoutf",
            "grid_fid",
            "Outflow and Storm Drain Outfall in same cell",
        )

        self.conflict4(
            "Outflows",
            "outflow_cells",
            "grid_fid",
            "Streets",
            "street_seg",
            "igridn",
            "Outflow and Street in same cell",
        )

        # Reduction Factors conflicts:

        self.conflict4(
            "Reduction Factors",
            "blocked_cells",
            "grid_fid",
            "Reduction Factors",
            "blocked_cells",
            "grid_fid",
            "Duplicate Reduction Factors in same cell (check partial ARF, full ARF, or WRF)",
        )

        self.conflict4(
            "Reduction Factors",
            "blocked_cells",
            "grid_fid",
            "Hydr. Structures",
            "struct",
            "inflonod",
            "Reduction Factors and Hyd. Struct in-cell in same cell (not recomended)",
        )

        self.conflict4(
            "Reduction Factors",
            "blocked_cells",
            "grid_fid",
            "Hydr. Structures",
            "struct",
            "outflonod",
            "Reduction Factors and Hyd. Struc out-cell in same cell (not recomended)",
        )

        self.conflict4(
            "Reduction Factors",
            "blocked_cells",
            "grid_fid",
            "Channels (Left Bank)",
            "chan_elems",
            "fid",
            "Reduction Factors and Channel Left Bank in same cell",
        )

        self.conflict4(
            "Reduction Factors",
            "blocked_cells",
            "grid_fid",
            "Channels (Right Bank)",
            "chan_elems",
            "rbankgrid",
            "Reduction Factors and Channel Right Bank in same cell",
        )

        self.conflict4(
            "Reduction Factors",
            "blocked_cells",
            "grid_fid",
            "Levees",
            "levee_data",
            "grid_fid",
            "Reduction Factors and Levees in same cell (not recomended)",
        )

        self.conflict4(
            "Reduction Factors",
            "blocked_cells",
            "grid_fid",
            "Mult. Channels",
            "mult_cells",
            "grid_fid",
            "Reduction Factors and Multiple Channels in same cell (not recomended)",
        )

        self.conflict4(
            "Reduction Factors",
            "blocked_cells",
            "grid_fid",
            "Storm Drain Inlets",
            "swmmflo",
            "swmm_jt",
            "Reduction Factors and Storm Drain Inlet in same cell (not recomended)",
        )

        self.conflict4(
            "Reduction Factors",
            "blocked_cells",
            "grid_fid",
            "Storm Drain Outfalls",
            "swmmoutf",
            "grid_fid",
            "Reduction Factors and Storm Drain Outfall in same cell (not recomended)",
        )

        # Full ARF conflicts:
        # Partial ARF conflicts:
        # WRF conflicts:

        # Hydraulic Structures conflicts:

        self.conflict4(
            "Hydr. Structures",
            "struct",
            "inflonod",
            "Hydr. Structures",
            "struct",
            "inflonod",
            "More than one Hyd. Struct in-cell in same element",
        )

        self.conflict4(
            "Hydr. Structures",
            "struct",
            "outflonod",
            "Hydr. Structures",
            "struct",
            "outflonod",
            "More than one Hyd. Struc out-cell in same element",
        )

        self.conflict4(
            "Hydr. Structures",
            "struct",
            "inflonod",
            "Hydr. Structures",
            "struct",
            "outflonod",
            "Hyd. Struct in-cell and Hyd. Struct out-cell in same element",
        )

        self.conflict4(
            "Hydr. Structures",
            "struct",
            "inflonod",
            "Channels (Right Bank)",
            "chan_elems",
            "rbankgrid",
            "Hyd. Struc in-cell and Channel Right Bank in same cell",
        )

        self.conflict4(
            "Hydr. Structures",
            "struct",
            "outflonod",
            "Channels (Right Bank)",
            "chan_elems",
            "rbankgrid",
            "Hyd. Struc out-cell and Channel Right Bank in same cell",
        )

        self.conflict4(
            "Hydr. Structures",
            "struct",
            "inflonod",
            "Levees",
            "levee_data",
            "grid_fid",
            "Hyd. Struc in-cell and Levee in same element (not recomended)",
        )

        self.conflict4(
            "Hydr. Structures",
            "struct",
            "outflonod",
            "Levees",
            "levee_data",
            "grid_fid",
            "Hyd. Struct out-cell and Levee in same element (not recomended)",
        )

        self.conflict4(
            "Hydr. Structures",
            "struct",
            "inflonod",
            "Mult. Channels",
            "mult_cells",
            "grid_fid",
            "Hyd. Struc in-cell and Multiple Channel in same cell",
        )

        self.conflict4(
            "Hydr. Structures",
            "struct",
            "outflonod",
            "Mult. Channels",
            "mult_cells",
            "grid_fid",
            "Hyd. Struct out-cell and Multiple Channel in same cell",
        )

        self.conflict4(
            "Hydr. Structures",
            "struct",
            "inflonod",
            "Storm Drain Inlets",
            "swmmflo",
            "swmm_jt",
            "Hyd. Struc in-cell and Storm Drain Inlet in same cell",
        )

        self.conflict4(
            "Hydr. Structures",
            "struct",
            "outflonod",
            "Storm Drain Outfalls",
            "swmmoutf",
            "grid_fid",
            "Hyd. Struct out-cell and Storm Drain Outlet in same cell (not recomended)",
        )

        self.conflict4(
            "Hydr. Structures",
            "struct",
            "inflonod",
            "Streets",
            "street_seg",
            "igridn",
            "Hyd. Struc in-cell and Street in same cell",
        )

        self.conflict4(
            "Hydr. Structures",
            "struct",
            "outflonod",
            "Streets",
            "street_seg",
            "igridn",
            "Hyd. Struct out-cell and Streett in same cell",
        )

        # Channels conflicts:

        self.conflict4(
            "Channels (Left Bank)",
            "chan_elems",
            "fid",
            "Channels (Left Bank)",
            "chan_elems",
            "fid",
            "2 or more Channel Left Banks in same cell",
        )

        self.conflict4(
            "Channels (Left Bank)",
            "chan_elems",
            "fid",
            "Channels (Right Bank)",
            "chan_elems",
            "rbankgrid",
            "Channel Left Bank and Channel Right Bank in same cell",
        )

        # TODO: left bank and right bank are in same attribute, this is wrong!!
        self.conflict4(
            "Channels (Right Bank)",
            "chan_elems",
            "rbankgrid",
            "Channels (Right Bank)",
            "chan_elems",
            "rbankgrid",
            "2 or more Channel Right Banks in same cell",
        )

        self.conflict4(
            "Channels (Left Bank)",
            "chan_elems",
            "fid",
            "Levees",
            "levee_data",
            "grid_fid",
            "Channel Left Bank and Levee in same cell",
        )

        self.conflict4(
            "Channels (Right Bank)",
            "chan_elems",
            "rbankgrid",
            "Levees",
            "levee_data",
            "grid_fid",
            "Channel Right Bank and Levee in same cell",
        )

        self.conflict4(
            "Channels (Left Bank)",
            "chan_elems",
            "fid",
            "Mult. Channels",
            "mult_cells",
            "grid_fid",
            "Channel Left Bank and Multiple Channel in same cell",
        )

        self.conflict4(
            "Channels (Right Bank)",
            "chan_elems",
            "rbankgrid",
            "Mult. Channels",
            "mult_cells",
            "grid_fid",
            "Channel Right Bank and Multiple Channel same cell",
        )

        self.conflict4(
            "Channels (Right Bank)",
            "chan_elems",
            "rbankgrid",
            "Storm Drain Inlets",
            "swmmflo",
            "swmm_jt",
            "Channel Right Bank and Storm Drain Inlet same cell",
        )

        self.conflict4(
            "Channels (Right Bank)",
            "chan_elems",
            "rbankgrid",
            "Storm Drain Outfalls",
            "swmmoutf",
            "grid_fid",
            "Channel Right Bank and Storm Drain Outfall same cell",
        )

        self.conflict4(
            "Channels (Left Bank)",
            "chan_elems",
            "fid",
            "Streets",
            "street_seg",
            "igridn",
            "Channel Left Bank and Street in same cell",
        )

        self.conflict4(
            "Channels (Right Bank)",
            "chan_elems",
            "rbankgrid",
            "Streets",
            "street_seg",
            "igridn",
            "Channel Right Bank and Street in same cell",
        )

        # Right bank Channels conflicts:

        # Levee conflicts:

        self.conflict4(
            "Levees",
            "levee_data",
            "grid_fid",
            "Levees",
            "levee_data",
            "grid_fid",
            "2 or more Levees in same cell (review)",
        )

        self.conflict4(
            "Levees",
            "levee_data",
            "grid_fid",
            "Mult. Channels",
            "mult_cells",
            "grid_fid",
            "Levee and Multiple Channels in same cell",
        )

        self.conflict4(
            "Levees",
            "levee_data",
            "grid_fid",
            "Storm Drain Inlets",
            "swmmflo",
            "swmm_jt",
            "Levee and Storm Drain Inlet in same cell",
        )

        self.conflict4(
            "Levees",
            "levee_data",
            "grid_fid",
            "Storm Drain Outfalls",
            "swmmoutf",
            "grid_fid",
            "Levee and Storm Drain Outfall in same cell",
        )

        # Multiple Channels conflicts:

        self.conflict4(
            "Mult. Channels",
            "mult_cells",
            "grid_fid",
            "Mult. Channels",
            "mult_cells",
            "grid_fid",
            "2 or more Multiple Channels in same cell",
        )

        self.conflict4(
            "Mult. Channels",
            "mult_cells",
            "grid_fid",
            "Storm Drain Inlets",
            "swmmflo",
            "swmm_jt",
            "Multiple Channels and Storm Drain Inlet in same cell",
        )

        self.conflict4(
            "Mult. Channels",
            "mult_cells",
            "grid_fid",
            "Storm Drain Outfalls",
            "swmmoutf",
            "grid_fid",
            "Multiple Channels and Storm Drain Outfall in same cell",
        )

        self.conflict4(
            "Mult. Channels",
            "mult_cells",
            "grid_fid",
            "Streets",
            "street_seg",
            "igridn",
            "Multiple Channels and Street in same cell",
        )

        # Storm Drain inlets conflicts:

        self.conflict4(
            "Storm Drain Inlets",
            "swmmflo",
            "swmm_jt",
            "Storm Drain Inlets",
            "swmmflo",
            "swmm_jt",
            "2 or more Storm Drain Inlets in same cell",
        )

        self.conflict4(
            "Storm Drain Inlets",
            "swmmflo",
            "swmm_jt",
            "Storm Drain Outfalls",
            "swmmoutf",
            "grid_fid",
            "Storm Drain Inlet and Storm Drain Outfall in same cell",
        )

        # Storm Drain outfalls conflicts:

        self.conflict4(
            "Storm Drain Outfalls",
            "swmmoutf",
            "grid_fid",
            "Storm Drain Outfalls",
            "swmmoutf",
            "grid_fid",
            "2 or more Storm Drain Outfalls in same cell",
        )

        # Street conflicts:

        self.conflict4(
            "Streets", "street_seg", "igridn", "Streets", "street_seg", "igridn", "2 or more Streets in same cell"
        )

        self.setWindowTitle("Errors and Warnings for: " + self.issue1 + " with " + self.issue2)

        self.create_current_conflicts_layer()

    def create_current_conflicts_layer(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)

        s = QSettings()
        lastDir = s.value("FLO-2D/lastGdsDir", "")
        qApp.processEvents()
        features = []
        for e in self.errors:
            if int(e[0]) > 1:
                pnt = self.gutils.single_centroid(e[0])
                pt = QgsGeometry().fromWkt(pnt).asPoint()
                features.append([pt.x(), pt.y(), e[0], e[3]])

        shapefile = lastDir + "/Current Conflicts.shp"
        name = "Current Conflicts"
        fields = [["X", "I"], ["Y", "I"], ["cell", "I"], ["description", "S"]]
        if self.create_current_conflicts_points_shapefile(shapefile, name, fields, features):
            vlayer = self.iface.addVectorLayer(shapefile, "", "ogr")
        QApplication.restoreOverrideCursor()

    def create_current_conflicts_points_shapefile(self, shapefile, name, fields, features):
        try:
            lyr = QgsProject.instance().mapLayersByName(name)

            if lyr:
                QgsProject.instance().removeMapLayers([lyr[0].id()])

            # define fields for feature attributes. A QgsFields object is needed
            f = QgsFields()
            f.append(QgsField(fields[2][0], QVariant.Int))
            f.append(QgsField(fields[3][0], QVariant.String))

            mapCanvas = self.iface.mapCanvas()
            my_crs = mapCanvas.mapSettings().destinationCrs()
            QgsVectorFileWriter.deleteShapeFile(shapefile)
            writer = QgsVectorFileWriter(shapefile, "system", f, QgsWkbTypes.Point, my_crs, "ESRI Shapefile")
            if writer.hasError() != QgsVectorFileWriter.NoError:
                self.uc.bar_error("ERROR 201919.0451: Error when creating shapefile: " + shapefile)

            # add features:
            for feat in features:
                attr = []
                fet = QgsFeature()
                fet.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(feat[0]), float(feat[1]))))
                non_coord_feats = []
                non_coord_feats.append(feat[2])
                non_coord_feats.append(feat[3])
                fet.setAttributes(non_coord_feats)
                writer.addFeature(fet)

            # delete the writer to flush features to disk
            del writer
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 190519.0442: error while creating layer  " + name + "!\n", e)
            return False

    def get_n_cells(self, table, cell, n):
        sqr = "SELECT {0} FROM {1} ORDER BY {0} LIMIT {2}".format(cell, table, n.text())
        return self.gutils.execute(sqr).fetchall()

    def populate_elements_cbo(self):
        self.elements_cbo.clear()
        self.elements_cbo.addItem(" ")
        for x in self.errors:
            if self.elements_cbo.findText(x[0].strip()) == -1:
                self.elements_cbo.addItem(x[0].strip())
        self.elements_cbo.model().sort(0)

    def populate_errors_cbo(self):
        self.errors_cbo.clear()
        self.errors_cbo.addItem(" ")
        self.errors_cbo.addItem("All")
        for x in self.errors:
            if self.errors_cbo.findText(x[1].strip()) == -1:
                self.errors_cbo.addItem(x[1].strip())
            if self.errors_cbo.findText(x[2].strip()) == -1:
                self.errors_cbo.addItem(x[2].strip())
        self.errors_cbo.model().sort(0)

    def component1_cbo_activated(self):
        self.loadIssuePairs()

    def component2_cbo_activated(self):
        self.loadIssuePairs()

    def loadIssuePairs(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.description_tblw.setRowCount(0)
        comp1 = self.component1_cbo.currentText()
        comp2 = self.component2_cbo.currentText()
        for item in self.errors:
            if (
                (item[1] == comp1 and item[2] == comp2)
                or (item[1] == comp2 and item[2] == comp1)
                or (comp1 == "" and (item[1] == comp2 or item[2] == comp2))
                or (comp2 == "" and (item[1] == comp1 or item[2] == comp1))
                or (comp1 == "All" and comp2 == "All")
                or (comp1 == "All" and comp2 == "")
                or (comp1 == "" and comp2 == "All")
                or (comp1 == "All" and (item[1] == comp2 or item[2] == comp2))
                or (comp2 == "All" and (item[1] == comp1 or item[2] == comp1))
            ):
                rowPosition = self.description_tblw.rowCount()
                self.description_tblw.insertRow(rowPosition)
                itm = QTableWidgetItem()
                itm.setData(Qt.EditRole, item[0].strip())
                self.description_tblw.setItem(rowPosition, 0, itm)
                itm = QTableWidgetItem()
                itm.setData(Qt.EditRole, item[3])
                self.description_tblw.setItem(rowPosition, 2, itm)
            else:
                self.lyrs.clear_rubber()

        self.errors_cbo.setCurrentIndex(0)
        self.elements_cbo.setCurrentIndex(0)
        if self.description_tblw.rowCount() > 0:
            self.description_tblw.selectRow(0)
            cell = self.description_tblw.item(0, 0).text()
            self.find_cell(cell)

        #         self.setWindowTitle("Errors and Warnings for: " + comp1 + " with " + comp2)

        QApplication.restoreOverrideCursor()

    def elements_cbo_activated(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.description_tblw.setRowCount(0)
        nElems = self.elements_cbo.count()
        if nElems > 0:
            cell = self.elements_cbo.currentText().strip()
            for item in self.errors:
                if item[0].strip() == cell:
                    rowPosition = self.description_tblw.rowCount()
                    self.description_tblw.insertRow(rowPosition)
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[0].strip())
                    self.description_tblw.setItem(rowPosition, 0, itm)
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[3])
                    self.description_tblw.setItem(rowPosition, 2, itm)
            self.component1_cbo.setCurrentIndex(0)
            self.component2_cbo.setCurrentIndex(0)
            self.errors_cbo.setCurrentIndex(0)
            self.find_cell(cell)
        QApplication.restoreOverrideCursor()

    def errors_cbo_activated(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.description_tblw.setRowCount(0)
        nElems = self.errors_cbo.count()
        if nElems > 0:
            for item in self.errors:
                if (
                    item[1].strip() == self.errors_cbo.currentText().strip()
                    or item[2].strip() == self.errors_cbo.currentText().strip()
                    or self.errors_cbo.currentText().strip() == "All"
                ):

                    rowPosition = self.description_tblw.rowCount()
                    self.description_tblw.insertRow(rowPosition)
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[0].strip())
                    self.description_tblw.setItem(rowPosition, 0, itm)
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[3])
                    self.description_tblw.setItem(rowPosition, 2, itm)
                else:
                    self.lyrs.clear_rubber()
        self.component1_cbo.setCurrentIndex(0)
        self.component2_cbo.setCurrentIndex(0)
        QApplication.restoreOverrideCursor()

    def find_cell_clicked(self):
        cell = self.elements_cbo.currentText()
        self.find_cell(cell)

    def find_cell(self, cell):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            grid = self.lyrs.data["grid"]["qlyr"]
            if grid is not None:
                if grid:
                    if cell != "":
                        cell = int(cell)
                        if len(grid) >= cell and cell > 0:
                            self.lyrs.show_feat_rubber(grid.id(), cell, QColor(Qt.yellow))
                            self.currentCell = next(grid.getFeatures(QgsFeatureRequest(cell)))
                            x, y = self.currentCell.geometry().centroid().asPoint()
                            if (
                                x < self.ext.xMinimum()
                                or x > self.ext.xMaximum()
                                or y < self.ext.yMinimum()
                                or y > self.ext.yMaximum()
                            ):
                                center_canvas(self.iface, x, y)
                                self.update_extent()
                        else:
                            self.lyrs.clear_rubber()
                    else:
                        self.lyrs.clear_rubber()
        except ValueError:
            self.uc.bar_warn("Cell " + str(cell) + " is not valid.")
            self.lyrs.clear_rubber()
            pass
        finally:
            QApplication.restoreOverrideCursor()

    def description_tblw_cell_clicked(self, row, column):
        cell = self.description_tblw.item(row, 0).text()
        self.find_cell(cell)

    def zoom_in(self):
        if self.currentCell:
            x, y = self.currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, 0.4)
            self.update_extent()

    def zoom_out(self):
        if self.currentCell:
            x, y = self.currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, -0.4)
            self.update_extent()

    def update_extent(self):
        self.ext = self.iface.mapCanvas().extent()

    def copy_to_clipboard(self):
        copy_tablewidget_selection(self.description_tblw)

    def conflict(self, comp1, table1, cell_1, comp2, table2, cell_2, description):
        cells1 = []
        cells2 = []
        repeated = []
        sqr1 = "SELECT {0} FROM {1}".format(cell_1, table1)
        sqr2 = "SELECT {0} FROM {1}".format(cell_2, table2)
        rows1 = self.gutils.execute(sqr1).fetchall()
        rows2 = self.gutils.execute(sqr2).fetchall()
        if not rows1 or not rows2:
            pass
        else:
            for row in rows1:
                cells1.append(row)
            for row in rows2:
                cells2.append(row)
            size1 = len(cells1)
            size2 = len(cells2)

            if comp1 == comp2:
                for i in range(size1):
                    k = i + 1
                    for j in range(k, size1):
                        if cells1[i][0] == cells1[j][0] and cells1[i][0] not in repeated:
                            repeated.append(cells1[i][0])
                            break
            else:
                for i in range(size1):
                    for j in range(size2):
                        if cells1[i][0] == cells2[j][0] and cells1[i][0] not in repeated:
                            repeated.append(cells1[i][0])
                            break
        if repeated:
            for r in repeated:
                self.errors.append([str(r), comp1, comp2, description])

    def conflict2(self, comp1, table1, cell_1, comp2, table2, cell_2, description):

        repeated = []
        rows1 = []
        rows2 = []

        sqr1 = "SELECT {0} FROM {1} ORDER BY {0} LIMIT {2}".format(cell_1, table1, self.numErrors.text())
        sqr2 = "SELECT {0} FROM {1} ORDER BY {0} LIMIT {2}".format(cell_2, table2, self.numErrors.text())

        rows1 = self.gutils.execute(sqr1).fetchall()
        rows2 = self.gutils.execute(sqr2).fetchall()

        size1 = len(rows1)
        size2 = len(rows2)

        if not rows1 or not rows2:
            pass
        else:
            if comp1 == comp2:
                for i in range(size1 - 2):
                    if rows1[i][0] == rows1[i + 1][0]:
                        if rows1[i][0] not in repeated:
                            repeated.append(rows1[i][0])
            else:
                try:
                    k = 0
                    for i in range(size1):
                        while True:
                            if rows2[k][0] < rows1[i][0]:
                                if k < size2 - 1:
                                    k += 1
                                    continue
                                else:
                                    k = 0
                                    break
                            elif rows2[k][0] > rows1[i][0]:
                                break
                            elif rows1[i][0] not in repeated:
                                repeated.append(rows1[i][0])
                            if k < size2 - 1:
                                k += 1
                            else:
                                k = 0
                                break

                except ValueError:
                    pass

        if repeated:
            for r in repeated:
                self.errors.append([str(r), comp1, comp2, description])

    def conflict3(self, comp1, rows1, comp2, rows2, description):

        repeated = []

        size1 = len(rows1)
        size2 = len(rows2)

        if not rows1 or not rows2:
            return 0
        else:
            if comp1 == comp2:
                for i in range(size1 - 2):
                    if rows1[i][0] == rows1[i + 1][0]:
                        if rows1[i][0] not in repeated:
                            repeated.append(rows1[i][0])
            else:
                try:
                    k = 0
                    for i in range(size1):
                        while True:
                            if rows2[k][0] < rows1[i][0]:
                                if k < size2 - 1:
                                    k += 1
                                    continue
                                else:
                                    k = 0
                                    break
                            elif rows2[k][0] > rows1[i][0]:
                                break
                            elif rows1[i][0] not in repeated:
                                repeated.append(rows1[i][0])
                            if k < size2 - 1:
                                k += 1
                            else:
                                k = 0
                                break

                except ValueError:
                    pass

        if repeated:
            for r in repeated:
                self.errors.append([str(r), comp1, comp2, description])
        return len(repeated)

    def conflict4(self, comp1, table1, cell_1, comp2, table2, cell_2, description):

        cond1 = self.issue1 == "All" and self.issue2 == "All"
        cond2 = self.issue1 == "All" and self.issue2 == ""
        cond3 = self.issue1 == "" and self.issue2 == "All"
        cond4 = self.issue1 == "All" and (comp1 == self.issue2 or comp2 == self.issue2)
        cond5 = self.issue2 == "All" and (comp1 == self.issue1 or comp2 == self.issue1)
        cond6 = (comp1 == self.issue1 and comp2 in self.issue2) or (comp2 == self.issue1 and comp1 in self.issue2)

        if cond1 or cond2 or cond3 or cond4 or cond5 or cond6:
            repeated = []

            if table1 == table2 and cell_1 == cell_2:
                sql = """SELECT {0}, COUNT(*) 
                        FROM {1} 
                        GROUP BY {0}
                        HAVING COUNT(*) > 1 ORDER BY {0}
                    """.format(
                    cell_1, table1
                )

            else:
                sql = """SELECT {0} FROM {1} 
                WHERE {0} IN 
                (
                    SELECT {0}
                    FROM {1}
                    INTERSECT
                    SELECT {2}
                    FROM {3}
                ) ORDER BY {0}""".format(
                    cell_1, table1, cell_2, table2
                )

            rows = self.gutils.execute(sql).fetchall()

            if not rows:
                pass
            else:
                size = len(rows)
                for i in range(size):
                    if rows[i][0] not in repeated:
                        repeated.append(rows[i][0])
            if repeated:
                for r in repeated:
                    self.errors.append([str(r), comp1, comp2, description])

    def conflict_inflow_partialARF(self):
        in_cells = []
        ARF_cells = []
        repeated = []
        inf = "SELECT grid_fid FROM inflow_cells"
        ARF = "SELECT grid_fid, arf FROM blocked_cells"
        in_rows = self.gutils.execute(inf).fetchall()
        ARF_rows = self.gutils.execute(ARF).fetchall()
        if not in_rows or not ARF_rows:
            return repeated
        else:
            for row in in_rows:
                in_cells.append(row)
            for row in ARF_rows:
                ARF_cells.append(row)
            in_size = len(in_cells)
            ARF_size = len(ARF_cells)
            for i in range(in_size):
                for j in range(ARF_size):
                    if (
                        in_cells[i][0] == ARF_cells[j][0]
                        and float(ARF_cells[j][1]) < 1.0
                        and in_cells[i][0] not in repeated
                    ):
                        repeated.append(in_cells[i][0])
                        break
            return repeated

    def conflict_outflow_partialARF(self):
        out_cells = []
        ARF_cells = []
        repeated = []
        outf = "SELECT grid_fid FROM outflow_cells"
        ARF = "SELECT grid_fid, arf FROM blocked_cells"
        out_rows = self.gutils.execute(outf).fetchall()
        ARF_rows = self.gutils.execute(ARF).fetchall()
        if not out_rows or not ARF_rows:
            return repeated
        else:
            for row in out_rows:
                out_cells.append(row)
            for row in ARF_rows:
                ARF_cells.append(row)
            in_size = len(out_cells)
            ARF_size = len(ARF_cells)
            for i in range(in_size):
                for j in range(ARF_size):
                    if (
                        out_cells[i][0] == ARF_cells[j][0]
                        and float(ARF_cells[j][1]) < 1.0
                        and out_cells[i][0] not in repeated
                    ):
                        repeated.append(out_cells[i][0])
                        break
            return repeated

    def conflict_outfall_partialARF(self):
        out_cells = []
        ARF_cells = []
        repeated = []
        outf = "SELECT grid_fid FROM swmmoutf"
        ARF = "SELECT grid_fid, arf FROM blocked_cells"
        out_rows = self.gutils.execute(outf).fetchall()
        ARF_rows = self.gutils.execute(ARF).fetchall()
        if not out_rows or not ARF_rows:
            return repeated
        else:
            for row in out_rows:
                out_cells.append(row)
            for row in ARF_rows:
                ARF_cells.append(row)
            in_size = len(out_cells)
            ARF_size = len(ARF_cells)
            for i in range(in_size):
                for j in range(ARF_size):
                    if (
                        out_cells[i][0] == ARF_cells[j][0]
                        and float(ARF_cells[j][1]) < 1.0
                        and out_cells[i][0] not in repeated
                    ):
                        repeated.append(out_cells[i][0])
                        break
            return repeated

    def conflict_inlet_partialARF(self):
        out_cells = []
        ARF_cells = []
        repeated = []
        outf = "SELECT swmm_jt FROM swmmflo"
        ARF = "SELECT grid_fid, arf FROM blocked_cells"
        out_rows = self.gutils.execute(outf).fetchall()
        ARF_rows = self.gutils.execute(ARF).fetchall()
        if not out_rows or not ARF_rows:
            return repeated
        else:
            for row in out_rows:
                out_cells.append(row)
            for row in ARF_rows:
                ARF_cells.append(row)
            in_size = len(out_cells)
            ARF_size = len(ARF_cells)
            for i in range(in_size):
                for j in range(ARF_size):
                    if (
                        out_cells[i][0] == ARF_cells[j][0]
                        and float(ARF_cells[j][1]) < 1.0
                        and out_cells[i][0] not in repeated
                    ):
                        repeated.append(out_cells[i][0])
                        break
            return repeated

    def conflict_outflow_fullARF(self):
        out_cells = []
        ARF_cells = []
        repeated = []
        outf = "SELECT grid_fid FROM outflow_cells"
        ARF = "SELECT grid_fid, arf FROM blocked_cells"
        out_rows = self.gutils.execute(outf).fetchall()
        ARF_rows = self.gutils.execute(ARF).fetchall()
        if not out_rows or not ARF_rows:
            return repeated
        else:
            for row in out_rows:
                out_cells.append(row)
            for row in ARF_rows:
                ARF_cells.append(row)
            in_size = len(out_cells)
            ARF_size = len(ARF_cells)
            for i in range(in_size):
                for j in range(ARF_size):
                    if (
                        out_cells[i][0] == ARF_cells[j][0]
                        and float(ARF_cells[j][1]) == 1.0
                        and out_cells[i][0] not in repeated
                    ):
                        repeated.append(out_cells[i][0])
                        break
            return repeated


uiDialog, qtBaseClass = load_ui("levee_crests")


class LeveeCrestsDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None
        self.levee_crests = []
        self.ext = self.iface.mapCanvas().extent()
        self.currentCell = None
        self.debug_directory = ""
        set_icon(self.find_cell_btn, "eye-svgrepo-com.svg")
        set_icon(self.zoom_in_btn, "zoom_in.svg")
        set_icon(self.zoom_out_btn, "zoom_out.svg")
        set_icon(self.copy_btn, "copy.svg")

        self.setup_connection()

        self.elements_cbo.activated.connect(self.elements_cbo_activated)
        self.find_cell_btn.clicked.connect(self.find_cell_clicked)
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        self.crest_tblw.cellClicked.connect(self.description_tblw_cell_clicked)
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)

        self.crest_tblw.setSortingEnabled(False)
        self.crest_tblw.resizeRowsToContents()

        self.populate_levee_crests()
        self.populate_elements_cbo()
        self.loadLeveeCrests()

        if self.currentCell:
            x, y = self.currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            cell_size = float(self.gutils.get_cont_par("CELLSIZE"))
            zoom_show_n_cells(iface, cell_size, 30)
            self.update_extent()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_levee_crests(self):
        levees = self.gutils.execute(
            "SELECT grid_fid, ldir, levcrest FROM levee_data ORDER BY grid_fid, ldir"
        ).fetchall()
        if not levees:
            pass
        else:
            grid_lyr = self.lyrs.data["grid"]["qlyr"]
            cellsize = float(self.gutils.get_cont_par("CELLSIZE"))

            for i in range(len(levees)):
                cell = levees[i][0]
                dir = levees[i][1]
                crest = levees[i][2]

                elev = self.gutils.grid_value(cell, "elevation")

                adj_cell, adj_elev = get_adjacent_cell_elevation(self.gutils, grid_lyr, cell, dir, cellsize)
                if adj_cell is not None and adj_elev != -999:
                    if crest < elev or crest < adj_cell:
                        self.levee_crests.append([str(i), cell, dir, crest, elev, adj_cell, adj_elev])

        self.setWindowTitle("Levee Crests lower than cell elevations")

        self.create_levee_crests_conflicts_layer()

    def create_levee_crests_conflicts_layer(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)

        s = QSettings()
        lastDir = s.value("FLO-2D/lastGdsDir", "")
        qApp.processEvents()
        features = []
        for e in self.levee_crests:
            pnt = self.gutils.single_centroid(e[1])
            pt = QgsGeometry().fromWkt(pnt).asPoint()
            features.append([pt.x(), pt.y(), e[1], e[2], e[3], e[4], e[5], e[6]])

        shapefile = lastDir + "/Levee Crests Conflicts.shp"
        name = "Levee Crests Conflicts"
        fields = [
            ["X", "I"],
            ["Y", "I"],
            ["Cell", "I"],
            ["Direction", "I"],
            ["Crest Elev", "D"],
            ["Cell Elev", "D"],
            ["Oppos. Cell", "I"],
            ["Oppos. Elev", "D"],
        ]
        if self.create_levee_crests_conflicts_points_shapefile(shapefile, name, fields, features):
            vlayer = self.iface.addVectorLayer(shapefile, "", "ogr")
        QApplication.restoreOverrideCursor()

    def create_levee_crests_conflicts_points_shapefile(self, shapefile, name, fields, features):
        try:
            lyr = QgsProject.instance().mapLayersByName(name)

            if lyr:
                QgsProject.instance().removeMapLayers([lyr[0].id()])

            QgsVectorFileWriter.deleteShapeFile(shapefile)

            # define fields for feature attributes. A QgsFields object is needed
            f = QgsFields()
            f.append(QgsField(fields[2][0], QVariant.Int))
            f.append(QgsField(fields[3][0], QVariant.Int))
            f.append(QgsField(fields[4][0], QVariant.Double))
            f.append(QgsField(fields[5][0], QVariant.Double))
            f.append(QgsField(fields[6][0], QVariant.Int))
            f.append(QgsField(fields[7][0], QVariant.Double))

            mapCanvas = self.iface.mapCanvas()
            my_crs = mapCanvas.mapSettings().destinationCrs()

            writer = QgsVectorFileWriter(shapefile, "system", f, QgsWkbTypes.Point, my_crs, "ESRI Shapefile")

            if writer.hasError() != QgsVectorFileWriter.NoError:
                self.uc.bar_error("ERROR 140619.0922: Error when creating shapefile: " + shapefile)

            # Add features:
            for feat in features:
                attr = []
                fet = QgsFeature()
                fet.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(feat[0]), float(feat[1]))))
                non_coord_feats = []
                non_coord_feats.append(feat[2])
                non_coord_feats.append(feat[3])
                non_coord_feats.append(feat[4])
                non_coord_feats.append(feat[5])
                non_coord_feats.append(feat[6])
                non_coord_feats.append(feat[7])

                fet.setAttributes(non_coord_feats)
                writer.addFeature(fet)

            # delete the writer to flush features to disk
            del writer
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 140619.0923: error while creating layer  " + name + "!\n", e)
            return False

    def get_n_cells(self, table, cell, n):
        sqr = "SELECT {0} FROM {1} ORDER BY {0} LIMIT {2}".format(cell, table, n.text())
        return self.gutils.execute(sqr).fetchall()

    def populate_elements_cbo(self):
        self.elements_cbo.clear()
        self.elements_cbo.addItem("All ")
        for x in self.levee_crests:
            if self.elements_cbo.findText(str(x[1])) == -1:
                self.elements_cbo.addItem(str(x[1]))
        self.elements_cbo.model().sort(1)

    def populate_errors_cbo(self):
        self.errors_cbo.clear()
        self.errors_cbo.addItem(" ")
        self.errors_cbo.addItem("All")
        for x in self.levee_crests:
            if self.errors_cbo.findText(x[1].strip()) == -1:
                self.errors_cbo.addItem(x[1].strip())
            if self.errors_cbo.findText(x[2].strip()) == -1:
                self.errors_cbo.addItem(x[2].strip())
        self.errors_cbo.model().sort(0)

    def loadLeveeCrests(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.crest_tblw.setRowCount(0)

        color1 = Qt.white
        element = -999
        for item in self.levee_crests:

            if item[1] != element:
                if color1 == Qt.yellow:
                    color1 = Qt.white
                    color2 = Qt.lightGray
                else:
                    color1 = Qt.yellow
                    color2 = Qt.darkYellow
                element = item[1]

            rowPosition = self.crest_tblw.rowCount()
            self.crest_tblw.insertRow(rowPosition)

            itm = QTableWidgetItem()
            itm.setBackground(color1)
            itm.setData(Qt.EditRole, item[0].strip())
            self.crest_tblw.setItem(rowPosition, 0, itm)

            itm = QTableWidgetItem()
            itm.setBackground(color1)
            itm.setData(Qt.EditRole, item[1])
            self.crest_tblw.setItem(rowPosition, 0, itm)

            itm = QTableWidgetItem()
            itm.setBackground(color1)
            itm.setData(Qt.EditRole, item[2])
            self.crest_tblw.setItem(rowPosition, 1, itm)

            itm = QTableWidgetItem()
            itm.setBackground(color1)
            itm.setData(Qt.EditRole, item[3])
            self.crest_tblw.setItem(rowPosition, 2, itm)

            itm = QTableWidgetItem()
            itm.setBackground(color1)
            itm.setData(Qt.EditRole, item[4])
            self.crest_tblw.setItem(rowPosition, 3, itm)

            itm = QTableWidgetItem()
            itm.setBackground(color2)
            itm.setData(Qt.EditRole, item[5])
            self.crest_tblw.setItem(rowPosition, 4, itm)

            itm = QTableWidgetItem()
            itm.setBackground(color2)
            itm.setData(Qt.EditRole, item[6])
            self.crest_tblw.setItem(rowPosition, 5, itm)

            self.elements_cbo.setCurrentIndex(0)
            if self.crest_tblw.rowCount() > 0:
                self.crest_tblw.selectRow(0)
                cell = self.crest_tblw.item(0, 0).text()
                self.find_cell(cell)

        QApplication.restoreOverrideCursor()

    def elements_cbo_activated(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.crest_tblw.setRowCount(0)
        nElems = self.elements_cbo.count()
        if nElems > 0:
            cell = self.elements_cbo.currentText().strip()
            if cell == "All":
                self.loadLeveeCrests()
            else:
                for item in self.levee_crests:
                    if str(item[1]) == cell:
                        rowPosition = self.crest_tblw.rowCount()
                        self.crest_tblw.insertRow(rowPosition)

                        itm = QTableWidgetItem()
                        itm.setData(Qt.EditRole, item[0].strip())
                        self.crest_tblw.setItem(rowPosition, 0, itm)

                        itm = QTableWidgetItem()
                        itm.setData(Qt.EditRole, item[1])
                        self.crest_tblw.setItem(rowPosition, 0, itm)

                        itm = QTableWidgetItem()
                        itm.setData(Qt.EditRole, item[2])
                        self.crest_tblw.setItem(rowPosition, 1, itm)

                        itm = QTableWidgetItem()
                        itm.setData(Qt.EditRole, item[3])
                        self.crest_tblw.setItem(rowPosition, 2, itm)

                        itm = QTableWidgetItem()
                        itm.setData(Qt.EditRole, item[4])
                        self.crest_tblw.setItem(rowPosition, 3, itm)

                        itm = QTableWidgetItem()
                        itm.setBackground(Qt.lightGray)
                        itm.setData(Qt.EditRole, item[5])
                        self.crest_tblw.setItem(rowPosition, 4, itm)

                        itm = QTableWidgetItem()
                        itm.setBackground(Qt.lightGray)
                        itm.setData(Qt.EditRole, item[6])
                        self.crest_tblw.setItem(rowPosition, 5, itm)

                self.find_cell(cell)
        QApplication.restoreOverrideCursor()

    def errors_cbo_activated(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.crest_tblw.setRowCount(0)
        nElems = self.errors_cbo.count()
        if nElems > 0:
            for item in self.levee_crests:
                if (
                    item[1].strip() == self.errors_cbo.currentText().strip()
                    or item[2].strip() == self.errors_cbo.currentText().strip()
                    or self.errors_cbo.currentText().strip() == "All"
                ):

                    rowPosition = self.crest_tblw.rowCount()
                    self.crest_tblw.insertRow(rowPosition)
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[0].strip())
                    self.crest_tblw.setItem(rowPosition, 0, itm)
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[3])
                    self.crest_tblw.setItem(rowPosition, 2, itm)
                else:
                    self.lyrs.clear_rubber()
        self.component1_cbo.setCurrentIndex(0)
        self.component2_cbo.setCurrentIndex(0)
        QApplication.restoreOverrideCursor()

    def find_cell_clicked(self):
        cell = self.elements_cbo.currentText()
        self.find_cell(cell)

    def find_cell(self, cell):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            grid = self.lyrs.data["grid"]["qlyr"]
            if grid is not None:
                if grid:
                    if cell != "":
                        cell = int(cell)
                        if len(grid) >= cell and cell > 0:
                            self.lyrs.show_feat_rubber(grid.id(), cell, QColor(Qt.yellow))
                            self.currentCell = next(grid.getFeatures(QgsFeatureRequest(cell)))
                            x, y = self.currentCell.geometry().centroid().asPoint()
                            if (
                                x < self.ext.xMinimum()
                                or x > self.ext.xMaximum()
                                or y < self.ext.yMinimum()
                                or y > self.ext.yMaximum()
                            ):
                                center_canvas(self.iface, x, y)
                                self.update_extent()
                        else:
                            self.lyrs.clear_rubber()
                    else:
                        self.lyrs.clear_rubber()
        except ValueError:
            self.uc.bar_warn("Cell " + str(cell) + " is not valid.")
            self.lyrs.clear_rubber()
            pass
        finally:
            QApplication.restoreOverrideCursor()

    def description_tblw_cell_clicked(self, row, column):
        cell = self.crest_tblw.item(row, 0).text()
        self.find_cell(cell)

    def zoom_in(self):
        if self.currentCell:
            x, y = self.currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, 0.4)
            self.update_extent()

    def zoom_out(self):
        if self.currentCell:
            x, y = self.currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, -0.4)
            self.update_extent()

    def update_extent(self):
        self.ext = self.iface.mapCanvas().extent()

    def copy_to_clipboard(self):
        copy_tablewidget_selection(self.crest_tblw)
