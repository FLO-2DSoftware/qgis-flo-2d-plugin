# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import datetime
import os
from random import randrange

from PyQt5 import QtCore
from qgis.core import QgsFeatureRequest
from qgis.PyQt.QtCore import (
    NULL,
    QDate,
    QDateTime,
    QRegExp,
    QSettings,
    Qt,
    QTime,
    pyqtSignal,
)
from qgis.PyQt.QtGui import QColor, QRegExpValidator, QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QFileDialog,
    QHeaderView,
    QInputDialog,
    QLineEdit,
    QStyledItemDelegate,
    QTableWidgetItem,
)

from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..utils import (
    FloatDelegate,
    HourDelegate,
    NumericDelegate,
    NumericDelegate2,
    TimeSeriesDelegate,
    copy_tablewidget_selection,
    float_or_zero,
    int_or_zero,
    is_number,
    is_true,
)
from .ui_utils import center_canvas, load_ui, set_icon, zoom

uiDialog, qtBaseClass = load_ui("outfalls")


class OutfallNodesDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None
        self.block = False

        set_icon(self.find_outfall_cell_btn, "eye-svgrepo-com.svg")
        set_icon(self.zoom_in_outfall_btn, "zoom_in.svg")
        set_icon(self.zoom_out_outfall_btn, "zoom_out.svg")
        set_icon(self.open_tidal_curve_btn, "open_dialog.svg")
        set_icon(self.open_time_series_btn, "open_dialog.svg")

        self.outfalls_tuple = ("FIXED", "FREE", "NORMAL", "TIDAL", "TIMESERIES")

        self.setup_connection()

        self.outfalls_buttonBox.button(QDialogButtonBox.Save).setText("Save to 'Storm Drain Nodes-Outfalls' User Layer")
        self.outfall_cbo.currentIndexChanged.connect(self.fill_individual_controls_with_current_outfall_in_table)
        self.outfalls_buttonBox.accepted.connect(self.save_outfalls)

        self.find_outfall_cell_btn.clicked.connect(self.find_outfall)
        self.zoom_in_outfall_btn.clicked.connect(self.zoom_in_outfall_cell)
        self.zoom_out_outfall_btn.clicked.connect(self.zoom_out_outfall_cell)

        # Connections from individual controls to particular cell in outfalls_tblw table widget:
        # self.grid_element.valueChanged.connect(self.grid_element_valueChanged)
        self.invert_elevation_dbox.valueChanged.connect(self.invert_elevation_dbox_valueChanged)
        self.flap_gate_chbox.stateChanged.connect(self.flap_gate_chbox_stateChanged)
        self.allow_discharge_chbox.stateChanged.connect(self.allow_discharge_chbox_stateChanged)
        self.outfall_type_cbo.currentIndexChanged.connect(self.out_fall_type_cbo_currentIndexChanged)
        self.water_depth_dbox.valueChanged.connect(self.water_depth_dbox_valueChanged)
        self.tidal_curve_cbo.currentIndexChanged.connect(self.tidal_curve_cbo_currentIndexChanged)
        self.time_series_cbo.currentIndexChanged.connect(self.time_series_cbo_currentIndexChanged)

        self.open_tidal_curve_btn.clicked.connect(self.open_tidal_curve)
        self.open_time_series_btn.clicked.connect(self.open_time_series)
        #
        # self.set_header()

        self.grid_lyr = self.lyrs.data["grid"]["qlyr"]
        self.grid_count = self.gutils.count("grid", field="fid")

        self.outfalls_tblw.cellClicked.connect(self.outfalls_tblw_cell_clicked)
        self.outfalls_tblw.verticalHeader().sectionClicked.connect(self.onVerticalSectionClicked)

        self.populate_outfalls()

    def set_header(self):
        self.outfalls_tblw.setHorizontalHeaderLabels(
            [
                "Name",  # INP
                "Node",  # FLO-2D
                "Invert Elev.",  # INP
                "Flap Gate",  # INP #FLO-2D
                "Allow Discharge" "Outfall Type",  # FLO-2D  # INP
                "Water Depth",  #
                "Tidal Curve",  # IN P
                "Time Series",
            ]
        )  # INP

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    # def invert_connect(self):
    #     self.uc.show_info('Connection!')
    #
    # def grid_element_valueChanged(self):
    #     self.box_valueChanged(self.grid_element, 1)

    def populate_outfalls(self):
        try:
            qry = """SELECT fid,
                            name, 
                            grid, 
                            outfall_invert_elev,
                            flapgate, 
                            swmm_allow_discharge,
                            outfall_type, 
                            water_depth,
                            tidal_curve, 
                            time_series              
                    FROM user_swmm_nodes WHERE sd_type = 'O';"""

            rows = self.gutils.execute(qry).fetchall()  # rows is a list of tuples.
            if not rows:
                QApplication.restoreOverrideCursor()
                self.uc.show_info("WARNING 121121.0421: No outfalls in 'Storm Drain Nodes' User Layer!")
                return

            self.block = True

            # Fill list of time series names:
            time_names_sql = "SELECT DISTINCT time_series_name FROM swmm_time_series GROUP BY time_series_name"
            names = self.gutils.execute(time_names_sql).fetchall()
            if names:
                for name in names:
                    self.time_series_cbo.addItem(name[0].strip())
            self.time_series_cbo.addItem("")

            # Fill list of tidal curves names:
            tidal_names_sql = "SELECT DISTINCT tidal_curve_name FROM swmm_tidal_curve GROUP BY tidal_curve_name"
            names = self.gutils.execute(tidal_names_sql).fetchall()
            if names:
                for name in names:
                    self.tidal_curve_cbo.addItem(name[0].strip())
            self.tidal_curve_cbo.addItem("")

            # Fill table:
            self.outfalls_tblw.setRowCount(0)
            for row_number, row_data in enumerate(
                rows
            ):  # In each iteration gets a tuple, for example:  0, ('fid'12, 'name''OUT3', 2581, 'False', 'False' 0,0,0, '', '')
                self.outfalls_tblw.insertRow(row_number)
                for col_number, data in enumerate(
                    row_data
                ):  # For each iteration gets, for example: first iteration:  0, 12. 2nd. iteration 1, 'OUT3', etc
                    if col_number == 6 and data not in self.outfalls_tuple:
                        data = "NORMAL"
                    item = QTableWidgetItem()
                    item.setData(
                        Qt.DisplayRole, data if data is not None else 0
                    )  # item gets value of data (as QTableWidgetItem Class)

                    # Fill the list of outfall names:
                    if (
                        col_number == 1
                    ):  # We need 2nd. col_number: 'OUT3' in the example above, and its fid from row_data[0]
                        self.outfall_cbo.addItem(data, row_data[0])

                    # Fill all text boxes with data of first feature of query (first element in table user_swmm_nodes):
                    if row_number == 0:
                        data = 0 if data is None else data
                        if col_number == 2:
                            self.grid_element_txt.setText(str(data))
                        elif col_number == 3:
                            self.invert_elevation_dbox.setValue(data if data is not None else 0)
                        elif col_number == 4:
                            self.flap_gate_chbox.setChecked(True if is_true(data) else False)
                        elif col_number == 5:
                            self.allow_discharge_chbox.setChecked(True if is_true(data) else False)
                        elif col_number == 6:
                            data = str(data).upper()
                            if data in self.outfalls_tuple:
                                index = self.outfalls_tuple.index(data)
                            else:
                                index = 0
                            self.outfall_type_cbo.setCurrentIndex(index)
                            data = self.outfall_type_cbo.currentText()
                            if not data in (
                                "FIXED",
                                "FREE",
                                "NORMAL",
                                "TIDAL",
                                "TIMESERIES",
                            ):
                                data = "NORMAL"
                            item.setData(Qt.DisplayRole, data)
                        elif col_number == 7:
                            self.water_depth_dbox.setValue(data if data is not None else 0)
                        elif col_number == 8:
                            txt = "*" if data == "..." else str(data) if not type(data) == str else data
                            idx = self.tidal_curve_cbo.findText(txt)
                            self.tidal_curve_cbo.setCurrentIndex(idx)
                        elif col_number == 9:
                            txt = "*" if data == "..." else str(data) if not type(data) == str else data
                            idx = self.time_series_cbo.findText(txt)
                            self.time_series_cbo.setCurrentIndex(idx)

                    if col_number > 0:  # For this row disable some elements and omit fid number
                        if col_number in (1, 2, 4, 5, 6, 8, 9):
                            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                        self.outfalls_tblw.setItem(row_number, col_number - 1, item)

            self.outfall_cbo.model().sort(0)

            self.outfalls_tblw.sortItems(0, Qt.AscendingOrder)
            self.outfalls_tblw.selectRow(0)

            self.block = False
            self.out_fall_type_cbo_currentIndexChanged()
            self.outfall_cbo.setCurrentIndex(0)
            self.highlight_outfall_cell(self.grid_element_txt.text())

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 100618.0846: error while loading outfalls components!", e)

    def onVerticalSectionClicked(self, logicalIndex):
        self.outfalls_tblw_cell_clicked(logicalIndex, 0)

    def invert_elevation_dbox_valueChanged(self):
        self.box_valueChanged(self.invert_elevation_dbox, 2)

    def flap_gate_chbox_stateChanged(self):
        self.checkbox_valueChanged(self.flap_gate_chbox, 3)

    def allow_discharge_chbox_stateChanged(self):
        self.checkbox_valueChanged(self.allow_discharge_chbox, 4)

    def out_fall_type_cbo_currentIndexChanged(self):
        try:
            self.combo_valueChanged(self.outfall_type_cbo, 5)

            self.disableTypes()

            idx = self.outfall_type_cbo.currentIndex()

            if idx == 0:
                self.water_depth_dbox.setEnabled(True)
                self.label_5.setEnabled(True)
                self.water_depth_dbox.setVisible(True)
                self.label_5.setVisible(True)

            elif idx == 3:
                self.tidal_curve_cbo.setEnabled(True)
                self.label_7.setEnabled(True)
                self.open_tidal_curve_btn.setEnabled(True)
                self.tidal_curve_cbo.setVisible(True)
                self.label_7.setVisible(True)
                self.open_tidal_curve_btn.setVisible(True)

                row = self.outfalls_tblw.currentRow()
                # row = row if row != -1 else 0
                item = self.outfalls_tblw.item(row, 7)
                # if item is not None:
                tidal_curve = str(item.text()) if item is not None else ""
                idx = self.tidal_curve_cbo.findText(tidal_curve)
                if idx != -1:
                    self.tidal_curve_cbo.setCurrentIndex(idx)
                else:
                    pass
                    # self.uc.bar_warn("WARNING 221222.0625: time series " + time_series + " not found.")

            elif idx == 4:
                self.time_series_cbo.setEnabled(True)
                self.label_8.setEnabled(True)
                self.open_time_series_btn.setEnabled(True)
                self.time_series_cbo.setVisible(True)
                self.label_8.setVisible(True)
                self.open_time_series_btn.setVisible(True)

                row = self.outfalls_tblw.currentRow()
                # row = row if row != -1 else 0
                item = self.outfalls_tblw.item(row, 8)
                # if item is not None:
                time_series = str(item.text()) if item is not None else ""
                idx = self.time_series_cbo.findText(time_series)
                if idx != -1:
                    self.time_series_cbo.setCurrentIndex(idx)
                else:
                    pass
                    # self.uc.bar_warn("WARNING 221222.0625: time series " + time_series + " not found.")
        except:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("WARNING 241222.0840: outfall type not found!")

    def disableTypes(self):
        self.water_depth_dbox.setEnabled(False)
        self.label_5.setEnabled(False)
        self.water_depth_dbox.setVisible(False)
        self.label_5.setVisible(False)

        self.tidal_curve_cbo.setEnabled(False)
        self.label_7.setEnabled(False)
        self.tidal_curve_cbo.setVisible(False)
        self.label_7.setVisible(False)
        self.open_tidal_curve_btn.setEnabled(False)
        self.open_tidal_curve_btn.setVisible(False)

        self.time_series_cbo.setEnabled(False)
        self.label_8.setEnabled(False)
        self.time_series_cbo.setVisible(False)
        self.label_8.setVisible(False)
        self.open_time_series_btn.setEnabled(False)
        self.open_time_series_btn.setVisible(False)

    def water_depth_dbox_valueChanged(self):
        self.box_valueChanged(self.water_depth_dbox, 6)

    def tidal_curve_cbo_currentIndexChanged(self):
        self.combo_valueChanged(self.tidal_curve_cbo, 7)

    def time_series_cbo_currentIndexChanged(self):
        self.combo_valueChanged(self.time_series_cbo, 8)

    def open_tidal_curve(self):
        tidal_curve_name = self.tidal_curve_cbo.currentText()
        dlg = OutfallTidalCurveDialog(self.iface, tidal_curve_name)
        while True:
            ok = dlg.exec_()
            if ok:
                if dlg.values_ok:
                    dlg.save_curve()
                    tidal_curve_name = dlg.get_curve_name()
                    if tidal_curve_name != "":
                        # Reload tidal curve list and select the one saved:
                        time_curve_names_sql = (
                            "SELECT DISTINCT tidal_curve_name FROM swmm_tidal_curve GROUP BY tidal_curve_name"
                        )
                        names = self.gutils.execute(time_curve_names_sql).fetchall()
                        if names:
                            self.tidal_curve_cbo.clear()
                            for name in names:
                                self.tidal_curve_cbo.addItem(name[0])
                            self.tidal_curve_cbo.addItem("")

                            idx = self.tidal_curve_cbo.findText(tidal_curve_name)
                            self.tidal_curve_cbo.setCurrentIndex(idx)

                        # self.uc.bar_info("Storm Drain external tidal curve saved for inlet " + "?????")
                        break
                    else:
                        break
            else:
                break

    def open_time_series(self):
        time_series_name = self.time_series_cbo.currentText()
        dlg = OutfallTimeSeriesDialog(self.iface, time_series_name)
        while True:
            save = dlg.exec_()
            if save:
                if dlg.values_ok:
                    dlg.save_time_series()
                    time_series_name = dlg.get_name()
                    if time_series_name != "":
                        # Reload time series list and select the one saved:
                        time_series_names_sql = (
                            "SELECT DISTINCT time_series_name FROM swmm_time_series GROUP BY time_series_name"
                        )
                        names = self.gutils.execute(time_series_names_sql).fetchall()
                        if names:
                            self.time_series_cbo.clear()
                            for name in names:
                                self.time_series_cbo.addItem(name[0])
                            self.time_series_cbo.addItem("")

                            idx = self.time_series_cbo.findText(time_series_name)
                            self.time_series_cbo.setCurrentIndex(idx)

                        # self.uc.bar_info("Storm Drain external time series saved for inlet " + "?????")
                        break
                    else:
                        break
            else:
                break

    def box_valueChanged(self, widget, col):
        # if not self.block:
        #     row = self.outfall_cbo.currentIndex()
        #     item = QTableWidgetItem()
        #     item.setData(Qt.EditRole, widget.value())
        #     self.outfalls_tblw.setItem(row, col, item)

        if not self.block:
            outfall = self.outfall_cbo.currentText()
            row = 0
            for i in range(1, self.outfalls_tblw.rowCount() - 1):
                name = self.outfalls_tblw.item(i, 0).text()
                if name == outfall:
                    row = i
                    break
            item = QTableWidgetItem()
            item.setData(Qt.EditRole, widget.value())
            if col in (0, 1, 3, 4, 5, 7, 8):
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.outfalls_tblw.setItem(row, col, item)

    def checkbox_valueChanged(self, widget, col):
        row = self.outfall_cbo.currentIndex()
        item = QTableWidgetItem()
        if col in (0, 1, 3, 4, 5, 7, 8):
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.outfalls_tblw.setItem(row, col, item)
        self.outfalls_tblw.item(row, col).setText("True" if widget.isChecked() else "False")

    def combo_valueChanged(self, widget, col):
        row = self.outfall_cbo.currentIndex()
        item = QTableWidgetItem()
        data = widget.currentText()
        item.setData(Qt.EditRole, data)
        if col in (0, 1, 3, 4, 5, 7, 8):
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.outfalls_tblw.setItem(row, col, item)

    def outfalls_tblw_cell_clicked(self, row, column):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.outfall_cbo.blockSignals(True)

            name = self.outfalls_tblw.item(row, 0).text()
            idx = self.outfall_cbo.findText(name)
            self.outfall_cbo.setCurrentIndex(idx)

            self.outfall_cbo.blockSignals(False)

            self.block = True

            self.grid_element_txt.setText(self.outfalls_tblw.item(row, 1).text())
            self.invert_elevation_dbox.setValue(float_or_zero(self.outfalls_tblw.item(row, 2)))
            self.flap_gate_chbox.setChecked(True if is_true(self.outfalls_tblw.item(row, 3).text()) else False)
            self.allow_discharge_chbox.setChecked(True if is_true(self.outfalls_tblw.item(row, 4).text()) else False)
            # Set index of outfall_type_cbo (a combo) depending of text contents:
            item = self.outfalls_tblw.item(row, 5)
            if item is not None:
                itemTxt = item.text().upper().strip()
                # itemTxt = "TIDAL CURVE" if itemTxt == "TIDAL" else "TIME SERIES" if itemTxt == "TIME" else itemTxt
                if itemTxt not in self.outfalls_tuple:
                    itemTxt = "NORMAL"
                index = self.outfall_type_cbo.findText(itemTxt)
                index = 4 if index > 4 else 0 if index < 0 else index
                self.outfall_type_cbo.setCurrentIndex(index)
                item = QTableWidgetItem()
                item.setData(Qt.EditRole, self.outfall_type_cbo.currentText())
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.outfalls_tblw.setItem(row, 5, item)

                self.out_fall_type_cbo_currentIndexChanged()

            self.water_depth_dbox.setValue(float_or_zero(self.outfalls_tblw.item(row, 6)))

            self.block = False

            self.highlight_outfall_cell(self.grid_element_txt.text())

            QApplication.restoreOverrideCursor()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 210618.1702: error assigning outfall values!", e)

    def fill_individual_controls_with_current_outfall_in_table(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        if not self.block:
            # Highlight row in table:
            row = self.outfall_cbo.currentIndex()
            self.outfalls_tblw.selectRow(row)

            # Load controls (text boxes, etc.) with selected row in table:
            item = QTableWidgetItem()

            item = self.outfalls_tblw.item(row, 1)
            if item is not None:
                self.grid_element_txt.setText(str(item.text()))

            self.invert_elevation_dbox.setValue(float_or_zero(self.outfalls_tblw.item(row, 2)))

            item = self.outfalls_tblw.item(row, 3)
            if item is not None:
                self.flap_gate_chbox.setChecked(True if is_true(item.text()) else False)

            #                                             True if item.text() == 'true' or item.text() == 'True' or item.text() == '1'
            #                                             or item.text() == 'Yes' or item.text() == 'yes' else False)

            item = self.outfalls_tblw.item(row, 4)
            if item is not None:
                self.allow_discharge_chbox.setChecked(True if is_true(item.text()) else False)

            #                                             True if item.text() == 'true' or item.text() == 'True' or item.text() == '1' else False)

            item = self.outfalls_tblw.item(row, 5)
            if item is not None:
                itemTxt = item.text().upper()
                if itemTxt in self.outfalls_tuple:
                    index = self.outfall_type_cbo.findText(itemTxt)
                else:
                    if itemTxt == "":
                        index = 0
                    else:
                        if is_number(itemTxt):
                            index = itemTxt
                        else:
                            index = 0
                index = 4 if index > 4 else 0 if index < 0 else index
                self.outfall_type_cbo.setCurrentIndex(index)
                item = QTableWidgetItem()
                item.setData(Qt.EditRole, self.outfall_type_cbo.currentText())
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.outfalls_tblw.setItem(row, 5, item)

            self.water_depth_dbox.setValue(float_or_zero(self.outfalls_tblw.item(row, 6)))

            self.highlight_outfall_cell(self.grid_element_txt.text())

        QApplication.restoreOverrideCursor()

    def find_outfall(self):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if self.grid_lyr is not None:
                if self.grid_lyr:
                    outfall = self.outfall_to_find_le.text()
                    if outfall != "":
                        indx = self.outfall_cbo.findText(outfall)
                        if indx != -1:
                            self.outfall_cbo.setCurrentIndex(indx)
                        else:
                            self.uc.bar_warn("WARNING 121121.0746: outfall " + str(outfall) + " not found.")
                    else:
                        self.uc.bar_warn("WARNING  121121.0747: outfall " + str(outfall) + " not found.")
        except ValueError:
            self.uc.bar_warn("WARNING  121121.0748: outfall " + str(outfall) + " is not a levee cell.")
            pass
        finally:
            QApplication.restoreOverrideCursor()

    def highlight_outfall_cell(self, cell):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if self.grid_lyr is not None:
                if cell != "":
                    cell = int(cell)
                    if self.grid_count >= cell and cell > 0:
                        self.lyrs.show_feat_rubber(self.grid_lyr.id(), cell, QColor(Qt.yellow))
                        feat = next(self.grid_lyr.getFeatures(QgsFeatureRequest(cell)))
                        x, y = feat.geometry().centroid().asPoint()
                        self.lyrs.zoom_to_all()
                        center_canvas(self.iface, x, y)
                        zoom(self.iface, 0.45)

                    else:
                        self.uc.bar_warn("WARNING 121121.1140: Cell " + str(cell) + " not found.")
                        self.lyrs.clear_rubber()
                else:
                    self.uc.bar_warn("WARNING 121121.1139: Cell " + str(cell) + " not found.")
                    self.lyrs.clear_rubber()

            QApplication.restoreOverrideCursor()

        except ValueError:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("WARNING 121121.1134: Cell " + str(cell) + "is not valid.")
            self.lyrs.clear_rubber()
            pass

    def zoom_in_outfall_cell(self):
        self.currentCell = next(self.grid_lyr.getFeatures(QgsFeatureRequest(int(self.grid_element_txt.text()))))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        x, y = self.currentCell.geometry().centroid().asPoint()
        center_canvas(self.iface, x, y)
        zoom(self.iface, 0.4)
        # self.update_extent()
        QApplication.restoreOverrideCursor()

    def zoom_out_outfall_cell(self):
        self.currentCell = next(self.grid_lyr.getFeatures(QgsFeatureRequest(int(self.grid_element_txt.text()))))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        x, y = self.currentCell.geometry().centroid().asPoint()
        center_canvas(self.iface, x, y)
        zoom(self.iface, -0.4)
        # self.update_extent()
        QApplication.restoreOverrideCursor()

    def save_outfalls(self):
        """
        Save changes of user_swmm_nodes layer.
        """
        # self.save_attrs()
        update_qry = """
                        UPDATE user_swmm_nodes
                        SET
                            name = ?, 
                            grid = ?, 
                            outfall_invert_elev = ?,
                            flapgate = ?, 
                            swmm_allow_discharge = ?,
                            outfall_type = ?,
                            water_depth = ?,
                            tidal_curve = ?,
                            time_series = ?
                        WHERE fid = ?;"""

        for row in range(0, self.outfalls_tblw.rowCount()):
            item = QTableWidgetItem()

            fid = self.outfall_cbo.itemData(row)

            item = self.outfalls_tblw.item(row, 0)
            if item is not None:
                name = str(item.text())

            item = self.outfalls_tblw.item(row, 1)
            if item is not None:
                grid = str(item.text())

            item = self.outfalls_tblw.item(row, 2)
            if item is not None:
                invert_elev = str(item.text())

            item = self.outfalls_tblw.item(row, 3)
            if item is not None:
                flapgate = str(True if is_true(item.text()) else False)

            item = self.outfalls_tblw.item(row, 4)
            if item is not None:
                allow_discharge = str(True if is_true(item.text()) else False)

            item = self.outfalls_tblw.item(row, 5)
            if item is not None:
                outfall_type = str(item.text())
                if not outfall_type in (
                    "FIXED",
                    "FREE",
                    "NORMAL",
                    "TIDAL",
                    "TIMESERIES",
                ):
                    outfall_type = "NORMAL"

            item = self.outfalls_tblw.item(row, 6)
            if item is not None:
                water_depth = str(item.text())

            item = self.outfalls_tblw.item(row, 7)
            # if item is not None:
            tidal_curve = str(item.text()) if item is not None else ""

            item = self.outfalls_tblw.item(row, 8)
            # if item is not None:
            time_series = str(item.text()) if item is not None else ""

            self.gutils.execute(
                update_qry,
                (
                    name,
                    grid,
                    invert_elev,
                    flapgate,
                    allow_discharge,
                    outfall_type,
                    water_depth,
                    tidal_curve,
                    time_series,
                    fid,
                ),
            )


uiDialog, qtBaseClass = load_ui("storm_drain_outfall_time_series")
class OutfallTimeSeriesDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, time_series_name):
        qtBaseClass.__init__(self)

        uiDialog.__init__(self)
        self.iface = iface
        self.time_series_name = time_series_name
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None

        self.values_ok = False
        self.loading = True
        set_icon(self.add_time_data_btn, "add.svg")
        set_icon(self.delete_time_data_btn, "remove.svg")

        self.setup_connection()

        delegate = TimeSeriesDelegate(self.outfall_time_series_tblw)
        self.outfall_time_series_tblw.setItemDelegate(delegate)

        self.time_series_buttonBox.accepted.connect(self.is_ok_to_save)
        self.select_time_series_btn.clicked.connect(self.select_time_series_file)
        self.outfall_time_series_tblw.itemChanged.connect(self.ts_tblw_changed)
        self.add_time_data_btn.clicked.connect(self.add_time)
        self.delete_time_data_btn.clicked.connect(self.delete_time)

        self.populate_time_series_dialog()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_time_series_dialog(self):
        self.loading = True
        if self.time_series_name == "":
            self.use_table_radio.setChecked(True)
            pass
        else:
            series_sql = "SELECT * FROM swmm_time_series WHERE time_series_name = ?;"
            row = self.gutils.execute(series_sql, (self.time_series_name,)).fetchone()
            if row:
                self.name_le.setText(row[1])
                self.description_le.setText(row[2])
                self.file_le.setText(row[3])
                external = True if is_true(row[4]) else False

                if external:
                    self.use_table_radio.setChecked(True)
                    self.external_radio.setChecked(False)
                else:
                    self.external_radio.setChecked(True)
                    self.use_table_radio.setChecked(False)

                data_qry = """SELECT
                                date, 
                                time, 
                                value
                        FROM swmm_time_series_data WHERE time_series_name = ? ORDER BY date, time"""
                rows = self.gutils.execute(data_qry, (self.time_series_name,)).fetchall()
                if rows:
                    self.outfall_time_series_tblw.setRowCount(0)
                    for row_number, row_data in enumerate(rows):
                        self.outfall_time_series_tblw.insertRow(row_number)
                        for col, data in enumerate(row_data):
                            if col == 0:
                                if data:
                                    try:
                                        a, b, c = data.split("/")
                                        if len(a) < 2:
                                            a = "0" * (2 - len(a)) + a
                                        if len(b) < 2:
                                            b = "0" * (2 - len(b)) + b
                                        if len(c) < 4:
                                            c = "0" * (4 - len(c)) + c
                                        data = a + "/" + b + "/" + c
                                    except:
                                        data = "00/00/0000"
                                else:
                                    data = "00/00/0000"
                            if col == 1:
                                if data:
                                    try:
                                        a, b = data.split(":")
                                        if len(a) == 1:
                                            a = "0" + a
                                        data = a + ":" + b
                                    except:
                                        data = "00:00"    
                                else:
                                    data = "00:00"   
                            if col == 2:
                                data = str(data)
                            item = QTableWidgetItem()
                            item.setData(Qt.DisplayRole, data)
                            self.outfall_time_series_tblw.setItem(row_number, col, item)

                    # self.outfall_time_series_tblw.sortItems(0, Qt.AscendingOrder)
            else:
                self.name_le.setText(self.time_series_name)
                self.external_radio.setChecked(True)
                self.use_table_radio.setChecked(False)

        QApplication.restoreOverrideCursor()
        self.loading = False

    def select_time_series_file(self):
        self.uc.clear_bar_messages()

        s = QSettings()
        last_dir = s.value("FLO-2D/lastSWMMDir", "")
        time_series_file, __ = QFileDialog.getOpenFileName(None, "Select time series data file", directory=last_dir)
        if not time_series_file:
            return
        s.setValue("FLO-2D/lastSWMMDir", os.path.dirname(time_series_file))
        self.file_le.setText(os.path.normpath(time_series_file))
        # For future use
        try:
            pass
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 140220.0807: reading time series data file failed!", e)
            return

    def is_ok_to_save(self):
        if self.name_le.text() == "":
            self.uc.bar_warn("Time Series name required!", 2)
            self.time_series_name = ""
            self.values_ok = False

        elif " " in self.name_le.text():
            self.uc.bar_warn("Time Series name with spaces not allowed!", 2)
            self.time_series_name = ""
            self.values_ok = False

        elif self.description_le.text() == "":
            self.uc.bar_warn("Time Series description required!", 2)
            self.values_ok = False

        elif self.use_table_radio.isChecked() and self.outfall_time_series_tblw.rowCount() == 0:
            self.uc.bar_warn("Time Series table can't be empty!", 2)
            self.values_ok = False

        elif self.external_radio.isChecked() and self.file_le.text() == "":
            self.uc.bar_warn("Data file name required!", 2)
            self.values_ok = False
        else:
            self.values_ok = True

    def save_time_series(self):
        delete_sql = "DELETE FROM swmm_time_series WHERE time_series_name = ?"
        self.gutils.execute(delete_sql, (self.name_le.text(),))
        insert_sql = "INSERT INTO swmm_time_series (time_series_name, time_series_description, time_series_file, time_series_data) VALUES (?, ?, ?, ?);"
        self.gutils.execute(
            insert_sql,
            (
                self.name_le.text(),
                self.description_le.text(),
                self.file_le.text(),
                "True" if self.use_table_radio.isChecked() else "False",
            ),
        )

        delete_data_sql = "DELETE FROM swmm_time_series_data WHERE time_series_name = ?"
        self.gutils.execute(delete_data_sql, (self.name_le.text(),))

        insert_data_sql = [
            """INSERT INTO swmm_time_series_data (time_series_name, date, time, value) VALUES""",
            4,
        ]
        for row in range(0, self.outfall_time_series_tblw.rowCount()):
            date = self.outfall_time_series_tblw.item(row, 0)
            if date:
                date = date.text()

            time = self.outfall_time_series_tblw.item(row, 1)
            if time:
                time = time.text()

            value = self.outfall_time_series_tblw.item(row, 2)
            if value:
                value = value.text()

            insert_data_sql += [(self.name_le.text(), date, time, value)]
        self.gutils.batch_execute(insert_data_sql)

        self.uc.bar_info("Inflow time series " + self.name_le.text() + " saved.", 2)
        self.time_series_name = self.name_le.text()
        self.close()

    def get_name(self):
        return self.time_series_name

    def outfall_time_series_tblw(self):
        self.uc.show_info("Clicked")

    def time_series_model_changed(self, i, j):
        self.uc.show_info("Changed")

    def ts_tblw_changed(self, Qitem):
        if not self.loading:
            text = Qitem.text()
            if "/" in text:
                a, b, c = text.split("/")
                if len(a) < 2:
                    a = "0" * (2 - len(a)) + a
                if len(b) < 2:
                    b = "0" * (2 - len(b)) + b
                if len(c) < 4:
                    c = "0" * (4 - len(c)) + c
                text = a + "/" + b + "/" + c
            if ":" in text:
                a, b = text.split(":")
                if len(a) == 1:
                    a = "0" + a
                text = a + ":" + b
            Qitem.setText(text)

    def add_time(self):
        self.outfall_time_series_tblw.insertRow(self.outfall_time_series_tblw.rowCount())
        row_number = self.outfall_time_series_tblw.rowCount() - 1

        item = QTableWidgetItem()
        d = QDate.currentDate()
        d = str(d.month()) + "/" + str(d.day()) + "/" + str(d.year())
        item.setData(Qt.DisplayRole, d)
        self.outfall_time_series_tblw.setItem(row_number, 0, item)

        item = QTableWidgetItem()
        t = QTime.currentTime()
        t = str(t.hour()) + ":" + str(t.minute())
        item.setData(Qt.DisplayRole, t)
        self.outfall_time_series_tblw.setItem(row_number, 1, item)

        item = QTableWidgetItem()
        item.setData(Qt.DisplayRole, "0.0")
        self.outfall_time_series_tblw.setItem(row_number, 2, item)

        self.outfall_time_series_tblw.selectRow(row_number)
        self.outfall_time_series_tblw.setFocus()

    def delete_time(self):
        self.outfall_time_series_tblw.removeRow(self.outfall_time_series_tblw.currentRow())
        self.outfall_time_series_tblw.selectRow(0)
        self.outfall_time_series_tblw.setFocus()

class TidalHourDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = super(TidalHourDelegate, self).createEditor(parent, option, index)
        if index.column() == 0:
            if isinstance(editor, QLineEdit):
                reg_ex = QRegExp("^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")
                validator = QRegExpValidator(reg_ex, editor)
                editor.setValidator(validator)
        return editor

uiDialog, qtBaseClass = load_ui("xy_curve_editor")
class CurveEditorDialog(qtBaseClass, uiDialog):
    before_paste = pyqtSignal()
    after_paste = pyqtSignal()
    after_delete = pyqtSignal()

    def __init__(self, iface, curve_name):
        qtBaseClass.__init__(self)

        uiDialog.__init__(self)
        self.iface = iface
        self.curve_name = curve_name
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None

        self.values_ok = False
        self.loading = True
        set_icon(self.add_data_btn, "add.svg")
        set_icon(self.delete_data_btn, "remove.svg")

        self.setup_connection()

        self.curve_tblw.setItemDelegate(FloatDelegate(3, self.curve_tblw))

        self.curve_buttonBox.accepted.connect(self.is_ok_to_save_curve)
        self.curve_tblw.itemChanged.connect(self.otc_tblw_changed)
        self.add_data_btn.clicked.connect(self.add_curve)
        self.delete_data_btn.clicked.connect(self.delete_data)
        self.load_curve_btn.clicked.connect(self.load_curve_file)
        self.save_curve_btn.clicked.connect(self.save_curve_file)
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        self.paste_btn.clicked.connect(self.paste_from_clipboard)

        self.populate_curve_dialog()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_curve_dialog(self):
        # Empty polymorphic method to be overwritten by a child derived class.
        pass
    
    def is_ok_to_save_curve(self):
        if self.name_le.text() == "" or self.name_le.text() == "...":
            self.uc.bar_warn("Curve name required!", 2)
            self.curve_name = ""
            self.values_ok = False
    
        elif " " in self.name_le.text():
            self.uc.bar_warn("Curve Name with spaces not allowed!", 2)
            self.curve_name = ""
            self.values_ok = False
    
        elif self.description_le.text() == "":
            self.uc.bar_warn("Curve description required!", 2)
            self.values_ok = False
    
        elif self.curve_tblw.rowCount() == 0:
            self.uc.bar_warn("Curve table can't be empty!", 2)
            self.values_ok = False
    
        else:
            self.values_ok = True

    def save_curve(self):
        # Empty polymorphic method to be overwritten by a child derived class.
        pass

    def get_curve_name(self):
        return self.curve_name

    def otc_tblw_changed(self, Qitem):
        try:
            text = float(Qitem.text())
            Qitem.setText(str(text))
        except ValueError:
            Qitem.setText("0.0")

    def add_curve(self):
        self.curve_tblw.insertRow(self.curve_tblw.rowCount())
        row_number = self.curve_tblw.rowCount() - 1

        item = QTableWidgetItem()
        item.setData(Qt.DisplayRole, "0.0")
        self.curve_tblw.setItem(row_number, 0, item)

        item = QTableWidgetItem()
        item.setData(Qt.DisplayRole, "0.0")
        self.curve_tblw.setItem(row_number, 1, item)

        self.curve_tblw.selectRow(row_number)
        self.curve_tblw.setFocus()

    def delete_data(self):
        self.curve_tblw.removeRow(self.curve_tblw.currentRow())
        self.curve_tblw.selectRow(0)
        self.curve_tblw.setFocus()

    def load_curve_file(self):
        self.uc.clear_bar_messages()

        s = QSettings()
        last_dir = s.value("FLO-2D/lastSWMMDir", "")
        curve_file, __ = QFileDialog.getOpenFileName(
            None,
            "Select file with curve data to load",
            directory=last_dir,
            filter="Text files (*.txt *.TXT*);;All files(*.*)",
        )
        if not curve_file:
            return
        s.setValue("FLO-2D/lastSWMMDir", os.path.dirname(curve_file))

        QApplication.setOverrideCursor(Qt.WaitCursor)
        # Load file into table:
        try:
            with open(curve_file, "r") as f1:
                lines = f1.readlines()
            if len(lines) > 0:
                self.curve_tblw.setRowCount(0)
                j = -1
                for i in range(1, len(lines)):
                    if i == 1:
                        desc = lines[i]
                    else:
                        if lines[i].strip() != "":
                            nxt = lines[i].split()
                            if len(nxt) == 2:
                                j += 1
                                self.curve_tblw.insertRow(j)
                                x, y = nxt[0], nxt[1]
                                self.curve_tblw.setItem(j, 0, QTableWidgetItem(x))
                                self.curve_tblw.setItem(j, 1, QTableWidgetItem(y))
                            else:
                                self.uc.bar_warn("Wrong data in line " + str(j + 4) + " of curve file!")
                        else:
                            self.uc.bar_warn("Wrong data in line " + str(j + 4) + " of curve file!")
                self.description_le.setText(desc)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 090422.0435: importing curve file failed!.\n", e)

        QApplication.restoreOverrideCursor()

    def save_curve_file(self):
        self.uc.clear_bar_messages()

        if self.curve_tblw.rowCount() == 0:
            self.uc.bar_warn("Curve table is empty. There is nothing to save!", 2)
            return
        elif self.description_le.text() == "":
            self.uc.bar_warn("Curve description required!", 2)
            return

        s = QSettings()
        last_dir = s.value("FLO-2D/lastSWMMDir", "")

        curve_file, __ = QFileDialog.getSaveFileName(
            None,
            "Save curve table as file...",
            directory=last_dir,
            filter="Text files (*.txt *.TXT*);;All files(*.*)",
        )

        if not curve_file:
            return

        s.setValue("FLO-2D/lastSWMMDir", os.path.dirname(curve_file))

        QApplication.setOverrideCursor(Qt.WaitCursor)
        with open(curve_file, "w") as tfile:
            tfile.write("EPASWMM Curve Data")
            tfile.write("\n" + self.description_le.text())

            for row in range(0, self.curve_tblw.rowCount()):
                hour = self.curve_tblw.item(row, 0)
                if hour:
                    hour = hour.text()
                else:
                    hour = "0.0"
                stage = self.curve_tblw.item(row, 1)
                if stage:
                    stage = stage.text()
                else:
                    stage = "0.0"
                tfile.write("\n" + hour + "    " + stage)

        QApplication.restoreOverrideCursor()
        self.uc.bar_info("Curve data saved as " + tidal_file, 4)

    def copy_to_clipboard(self):
        copy_tablewidget_selection(self.curve_tblw)

    def paste_from_clipboard(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.before_paste.emit()

        paste_str = QApplication.clipboard().text()
        rows = paste_str.split("\n")
        num_rows = len(rows) - 1
        if num_rows > 0:
            num_cols = rows[0].count("\t") + 1
            if num_cols > 2:
                self.uc.bar_info("Too many columns (" + str(num_cols) + ") to paste!")
            elif num_cols < 2:
                self.uc.bar_info("Two columns needed. Only (" + str(num_cols) + ") given!")
            else:
                for row in rows:
                    if row:
                        data = row.split()
                        j = self.curve_tblw.rowCount()
                        self.curve_tblw.insertRow(j)
                        hour, stage = data[0], data[1]
                        self.curve_tblw.setItem(j, 0, QTableWidgetItem(hour))
                        self.curve_tblw.setItem(j, 1, QTableWidgetItem(stage))
                self.curve_tblw.selectRow(self.curve_tblw.rowCount() - 1)
                self.curve_tblw.setFocus()
        else:
            self.uc.bar_info("No complete rows with two columns to paste!")

        self.after_paste.emit()
        QApplication.restoreOverrideCursor()
        
class OutfallTidalCurveDialog(CurveEditorDialog):    
    def populate_curve_dialog(self):
        self.loading = True
        if self.curve_name == "":
            pass
        else:
            self.setWindowTitle("Outfall Tidal Curve Editor")
            self.label_2.setText("Tidal Curve Name")
            self.curve_tblw.setHorizontalHeaderLabels(["Hour", "Stage"])       
            tidal_sql = "SELECT * FROM swmm_tidal_curve WHERE tidal_curve_name = ?"
            row = self.gutils.execute(tidal_sql, (self.curve_name,)).fetchone()
            if row:
                self.name_le.setText(row[1])
                self.description_le.setText(row[2])

                data_qry = """SELECT
                                hour, 
                                stage
                        FROM swmm_tidal_curve_data WHERE tidal_curve_name = ? ORDER BY hour;"""
                rows = self.gutils.execute(data_qry, (self.curve_name,)).fetchall()
                if rows:
                    # Convert items of first column to float to sort them in ascending order:
                    rws = []
                    for row in rows:
                        rws.append([float(row[0]), row[1]])
                    rws.sort()
                    # Restore items of first column to string:
                    rows = []
                    for row in rws:
                        rows.append([str(row[0]), row[1]])

                    self.curve_tblw.setRowCount(0)

                    for row_number, row_data in enumerate(rows):
                        self.curve_tblw.insertRow(row_number)
                        for cell, data in enumerate(row_data):
                            # if cell == 0:
                            #     if ":" in data:
                            #         a, b = data.split(":")
                            #         b = float(b)/60
                            #         data = float(a) + b
                            #     else:
                            #         data = float(data)
                            self.curve_tblw.setItem(row_number, cell, QTableWidgetItem(str(data)))

            else:
                self.name_le.setText(self.curve_name)

        QApplication.restoreOverrideCursor()
        self.loading = False   
        
    def save_curve(self):
        delete_sql = "DELETE FROM swmm_tidal_curve WHERE tidal_curve_name = ?"
        self.gutils.execute(delete_sql, (self.name_le.text(),))
        insert_sql = "INSERT INTO swmm_tidal_curve (tidal_curve_name, tidal_curve_description) VALUES (?, ?);"
        self.gutils.execute(
            insert_sql,
            (self.name_le.text(), self.description_le.text()),
        )

        delete_data_sql = "DELETE FROM swmm_tidal_curve_data WHERE tidal_curve_name = ?"
        self.gutils.execute(delete_data_sql, (self.name_le.text(),))

        insert_data_sql = [
            """INSERT INTO swmm_tidal_curve_data (tidal_curve_name, hour, stage) VALUES""",
            3,
        ]
        for row in range(0, self.curve_tblw.rowCount()):
            hour = self.curve_tblw.item(row, 0)
            if hour:
                hour = hour.text()

            stage = self.curve_tblw.item(row, 1)
            if stage:
                stage = stage.text()

            insert_data_sql += [(self.name_le.text(), hour, stage)]
        self.gutils.batch_execute(insert_data_sql)

        self.uc.bar_info("Curve " + self.name_le.text() + " saved.", 2)
        self.curve_name = self.name_le.text()
        self.close()        
        
class StorageUnitTabularCurveDialog(CurveEditorDialog):    
    def populate_curve_dialog(self):
        self.loading = True
        if self.curve_name == "":
            pass
        else:
            self.setWindowTitle("Storage Unit Tabular Curve Editor")
            self.label_2.setText("Tabular Curve Name")
            self.curve_tblw.setHorizontalHeaderLabels(["Depth", "Area"])       
            curve_sql = "SELECT * FROM swmm_other_curves WHERE name = ? AND type = 'Storage'"
            row = self.gutils.execute(curve_sql, (self.curve_name,)).fetchone()
            if row:
                self.name_le.setText(row[1])
                self.description_le.setText(row[3])

                data_qry = """SELECT
                                x_value, 
                                y_value
                        FROM swmm_other_curves WHERE name = ? and type = 'Storage' ORDER BY x_value;"""
                rows = self.gutils.execute(data_qry, (self.curve_name,)).fetchall()
                if rows:
                    # Convert items of first column to float to sort them in ascending order:
                    rws = []
                    for row in rows:
                        rws.append([float(row[0]), row[1]])
                    rws.sort()
                    # Restore items of first column to string:
                    rows = []
                    for row in rws:
                        rows.append([str(row[0]), row[1]])

                    self.curve_tblw.setRowCount(0)

                    for row_number, row_data in enumerate(rows):
                        self.curve_tblw.insertRow(row_number)
                        for cell, data in enumerate(row_data):
                            self.curve_tblw.setItem(row_number, cell, QTableWidgetItem(str(data)))
            else:
                self.name_le.setText(self.curve_name)

        QApplication.restoreOverrideCursor()
        self.loading = False   
        
    def save_curve(self):
        delete_data_sql = "DELETE FROM swmm_other_curves WHERE name = ? and type = 'Storage'"
        self.gutils.execute(delete_data_sql, (self.name_le.text(),))

        insert_data_sql = [
            """INSERT INTO swmm_other_curves (name, type,  description, x_value, y_value) VALUES""",
            5,
        ]
        for row in range(0, self.curve_tblw.rowCount()):
            x = self.curve_tblw.item(row, 0)
            if x:
                x = x.text()

            y = self.curve_tblw.item(row, 1)
            if y:
                y = y.text()

            insert_data_sql += [(self.name_le.text(), 'Storage',  self.description_le.text(), x, y)]
        self.gutils.batch_execute(insert_data_sql)

        self.uc.bar_info("Curve " + self.name_le.text() + " saved.", 2)
        self.curve_name = self.name_le.text()
        self.close()  