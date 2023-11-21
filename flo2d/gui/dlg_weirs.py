# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from math import isnan

from qgis.core import QgsFeatureRequest
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QInputDialog,
    QTableWidgetItem,
)

from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..utils import is_number, is_true, m_fdata, float_or_zero
from .table_editor_widget import StandardItem, StandardItemModel
from .ui_utils import center_canvas, load_ui, set_icon, try_disconnect, zoom

uiDialog, qtBaseClass = load_ui("weirs")


class WeirsDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None

        set_icon(self.find_weir_btn, "eye-svgrepo-com.svg")
        set_icon(self.zoom_in_weir_btn, "zoom_in.svg")
        set_icon(self.zoom_out_weir_btn, "zoom_out.svg")

        self.find_weir_btn.clicked.connect(self.find_weir)
        self.zoom_in_weir_btn.clicked.connect(self.zoom_in_weir)
        self.zoom_out_weir_btn.clicked.connect(self.zoom_out_weir)

        self.weirs_buttonBox.button(QDialogButtonBox.Save).setText("Save to 'Storm Drain weirs' User Layer")
        self.weir_name_cbo.currentIndexChanged.connect(self.fill_individual_controls_with_current_weir_in_table)

        self.weirs_buttonBox.accepted.connect(self.save_weirs)

        self.weir_type_cbo.currentIndexChanged.connect(self.weir_type_cbo_currentIndexChanged)
        self.weir_crest_height_dbox.valueChanged.connect(self.weir_crest_height_dbox_valueChanged)
        self.weir_discharge_coeff_dbox.valueChanged.connect(self.weir_discharge_coeff_dbox_valueChanged)
        self.weir_flap_gate_cbo.currentIndexChanged.connect(self.weir_flap_gate_cbo_currentIndexChanged)
        self.weir_end_contrac_cbo.currentIndexChanged.connect(self.weir_end_contrac_cbo_currentIndexChanged)
        self.weir_end_coeff_dbox.valueChanged.connect(self.weir_end_coeff_dbox_valueChanged)
        self.weir_shape_cbo.currentIndexChanged.connect(self.weir_shape_cbo_currentIndexChanged)
        self.weir_height_dbox.valueChanged.connect(self.weir_height_dbox_valueChanged)
        self.weir_length_dbox.valueChanged.connect(self.weir_length_dbox_valueChanged)
        self.weir_side_slope_dbox.valueChanged.connect(self.weir_side_slope_dbox_valueChanged)

        self.shape = ("TRIANGULAR", "TRAPEZOIDAL", "RECT_CLOSED")

        self.setup_connection()
        self.grid_lyr = self.lyrs.data["grid"]["qlyr"]
        self.weirs_lyr = self.lyrs.data["user_swmm_weirs"]["qlyr"]
        self.populate_weirs()

        self.weirs_tblw.cellClicked.connect(self.weirs_tblw_cell_clicked)
        self.weirs_tblw.verticalHeader().sectionClicked.connect(self.onVerticalSectionClicked)

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_weirs(self):
        qry = """SELECT fid,
                        weir_name,
                        weir_inlet, 
                        weir_outlet,
                        weir_type,
                        weir_crest_height,
                        weir_disch_coeff,
                        weir_flap_gate,
                        weir_end_contrac,
                        weir_end_coeff,
                        weir_side_slope,
                        weir_shape,
                        weir_height,
                        weir_length
                FROM user_swmm_weirs;"""
        wrong_status = 0
        try:
            rows = self.gutils.execute(qry).fetchall()
            self.weirs_tblw.setRowCount(0)
            for row_number, row_data in enumerate(rows):
                self.weirs_tblw.insertRow(row_number)
                for column, data in enumerate(row_data):
                    # if data is not None:
                        item = QTableWidgetItem()
                        item.setData(Qt.DisplayRole, data)  # item gets value of data (as QTableWidgetItem Class)

                        if column == 1:
                            # Fill the list of weirs names:
                            self.weir_name_cbo.addItem(data, row_data[0])
                        if row_number == 0:
                            if column == 2:
                                self.weir_from_node_txt.setText(str(data))

                            elif column == 3:
                                self.weir_to_node_txt.setText(str(data))

                            elif column == 4:
                                if data.upper() not in (
                                    "TRANSVERSE",
                                    "SIDEFLOW",
                                    "V-NOTCH",
                                    "TRAPEZOIDAL",
                                ):
                                    wrong_status += 1
                                    data = "TRANSVERSE"
                                    item.setData(Qt.DisplayRole, data)
                                index = self.weir_type_cbo.findText(data)
                                if index == -1:
                                    index = 0
                                self.weir_type_cbo.setCurrentIndex(index)

                            elif column == 5:
                                self.weir_crest_height_dbox.setValue(float_or_zero(data))

                            elif column == 6:
                                self.weir_discharge_coeff_dbox.setValue(float_or_zero(data))

                            elif column == 7:
                                if data.upper() not in ("YES", "NO"):
                                    wrong_status += 1
                                    data = 1
                                    item.setData(Qt.DisplayRole, data)
                                index = self.weir_flap_gate_cbo.findText(str(data))
                                if index == -1:
                                    index = 0
                                self.weir_flap_gate_cbo.setCurrentIndex(index)

                            elif column == 8:
                                if data not in ("0", "1", "2"):
                                    wrong_status += 1
                                    data = 1
                                    item.setData(Qt.DisplayRole, data)
                                index = self.weir_end_contrac_cbo.findText(str(data))
                                if index == -1:
                                    index = 0
                                self.weir_end_contrac_cbo.setCurrentIndex(index)

                            elif column == 9:
                                self.weir_end_coeff_dbox.setValue(float_or_zero(data))

                            elif column == 10:
                                self.weir_side_slope_dbox.setValue(float_or_zero(data))

                            elif column == 11:
                                if data.upper() not in self.shape:
                                    wrong_status += 1
                                    data = "RECT_CLOSE"
                                    item.setData(Qt.DisplayRole, data)
                                index = self.weir_shape_cbo.findText(data)
                                if index == -1:
                                    index = 0
                                self.weir_shape_cbo.setCurrentIndex(index)

                            elif column == 12:
                                self.weir_height_dbox.setValue(float_or_zero(data))

                            elif column == 13:
                                self.weir_length_dbox.setValue(float_or_zero(data))

                        if column > 0:  # Omit fid number (in column = 0)
                            if column in (1, 2, 3, 4, 7, 9):
                                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

                            self.weirs_tblw.setItem(row_number, column - 1, item)
                    # else:
                    #     wrong_status += 1

            self.highlight_weir(self.weir_name_cbo.currentText())
            QApplication.restoreOverrideCursor()
            if wrong_status > 0:
                self.uc.show_info(
                    "WARNING 070422.0531: there are some weirs with wrong type, shape, or flap gate!\n\n"
                    + "All wrong values were changed to their defaults.\n\n"
                    + "Edit them as wished and then 'Save' to replace the values in the 'Storm Drain weirs' User layers."
                )
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 070422.0730: assignment of value from weirs users layer failed!.\n",
                e,
            )

    def weir_type_cbo_currentIndexChanged(self):
        self.combo_valueChanged(self.weir_type_cbo, 3)

    def weir_crest_height_dbox_valueChanged(self):
        self.box_valueChanged(self.weir_crest_height_dbox, 4)

    def weir_discharge_coeff_dbox_valueChanged(self):
        self.box_valueChanged(self.weir_discharge_coeff_dbox, 5)

    def weir_flap_gate_cbo_currentIndexChanged(self):
        self.combo_valueChanged(self.weir_flap_gate_cbo, 6)

    def weir_end_contrac_cbo_currentIndexChanged(self):
        self.combo_valueChanged(self.weir_end_contrac_cbo, 7)

    def weir_end_coeff_dbox_valueChanged(self):
        self.box_valueChanged(self.weir_end_coeff_dbox, 8)

    def weir_side_slope_dbox_valueChanged(self):
        self.box_valueChanged(self.weir_side_slope_dbox, 9)

    def weir_shape_cbo_currentIndexChanged(self):
        self.combo_valueChanged(self.weir_shape_cbo, 10)

    def weir_height_dbox_valueChanged(self):
        self.box_valueChanged(self.weir_height_dbox, 11)

    def weir_length_dbox_valueChanged(self):
        self.box_valueChanged(self.weir_length_dbox, 12)

    def box_valueChanged(self, widget, col):
        row = self.weir_name_cbo.currentIndex()
        item = QTableWidgetItem()
        item.setData(Qt.EditRole, widget.value())
        # if col in (1, 2, 3, 4, 7, 9):
        #     item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.weirs_tblw.setItem(row, col, item)

    def combo_valueChanged(self, widget, col):
        row = self.weir_name_cbo.currentIndex()
        item = QTableWidgetItem()
        data = widget.currentText()
        item.setData(Qt.EditRole, data)
        if col in (3, 6, 8):
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.weirs_tblw.setItem(row, col, item)

    def weirs_tblw_cell_clicked(self, row, column):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.weir_name_cbo.blockSignals(True)
            self.weir_name_cbo.setCurrentIndex(row)
            self.weir_name_cbo.blockSignals(False)

            self.weir_from_node_txt.setText(self.weirs_tblw.item(row, 1).text())
            self.weir_to_node_txt.setText(self.weirs_tblw.item(row, 2).text())

            typ = self.weirs_tblw.item(row, 3).text()
            index = self.weir_type_cbo.findText(typ)
            if index == -1:
                index = 0
            else:
                self.weir_type_cbo.setCurrentIndex(index)

            self.weir_crest_height_dbox.setValue(float(self.weirs_tblw.item(row, 4).text()))
            self.weir_discharge_coeff_dbox.setValue(float(self.weirs_tblw.item(row, 5).text()))

            flap = self.weirs_tblw.item(row, 6).text()
            index = self.weir_flap_gate_cbo.findText(flap)
            if index == -1:
                index = 0
            else:
                self.weir_flap_gate_cbo.setCurrentIndex(index)
            contr = self.weirs_tblw.item(row, 7).text()
            index = self.weir_end_contrac_cbo.findText(contr)
            if index == -1:
                index = 0
            else:
                self.weir_end_contrac_cbo.setCurrentIndex(index)

            self.weir_end_coeff_dbox.setValue(float(self.weirs_tblw.item(row, 8).text()))

            self.weir_side_slope_dbox.setValue(float(self.weirs_tblw.item(row, 9).text()))

            shape = self.weirs_tblw.item(row, 10).text()
            index = self.weir_shape_cbo.findText(shape)
            if index == -1:
                index = 0
            else:
                self.weir_shape_cbo.setCurrentIndex(index)

            self.weir_height_dbox.setValue(float(self.weirs_tblw.item(row, 11).text()))
            self.weir_length_dbox.setValue(float(self.weirs_tblw.item(row, 12).text()))

            self.highlight_weir(self.weir_name_cbo.currentText())

            QApplication.restoreOverrideCursor()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 090422.1101: assignment of value failed!.\n", e)

    def onVerticalSectionClicked(self, logicalIndex):
        self.weirs_tblw_cell_clicked(logicalIndex, 0)

    def fill_individual_controls_with_current_weir_in_table(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            # highlight row in table:
            row = self.weir_name_cbo.currentIndex()
            self.weirs_tblw.selectRow(row)

            # load controls (text boxes, etc.) with selected row in table:
            item = QTableWidgetItem()

            item = self.weirs_tblw.item(row, 1)
            if item is not None:
                self.weir_from_node_txt.setText(str(item.text()))

            item = self.weirs_tblw.item(row, 2)
            if item is not None:
                self.weir_to_node_txt.setText(str(item.text()))

            item = self.weirs_tblw.item(row, 3)
            if item is not None:
                indx = self.weir_type_cbo.findText(item.text())
                if indx != -1:
                    self.weir_type_cbo.setCurrentIndex(indx)
                else:
                    self.uc.bar_warn("WARNING 070422.0839: weir type curve not found.")

            item = self.weirs_tblw.item(row, 4)
            if item is not None:
                self.weir_crest_height_dbox.setValue(float(str(item.text())))

            item = self.weirs_tblw.item(row, 5)
            if item is not None:
                self.weir_discharge_coeff_dbox.setValue(float(str(item.text())))

            item = self.weirs_tblw.item(row, 6)
            if item is not None:
                if item.text() in ("YES", "yes", "Yes", "0"):
                    self.weir_flap_gate_cbo.setCurrentIndex(0)
                else:
                    self.weir_flap_gate_cbo.setCurrentIndex(1)

            item = self.weirs_tblw.item(row, 7)
            if item is not None:
                self.weir_open_close_time_dbox.setValue(float(str(item.text())))

            item = self.weirs_tblw.item(row, 8)
            if item is not None:
                if item.text() in ("CIRCULAR", "circular", "Circular", "0"):
                    self.weir_shape_cbo.setCurrentIndex(0)
                else:
                    self.weir_shape_cbo.setCurrentIndex(1)

            item = self.weirs_tblw.item(row, 9)
            if item is not None:
                self.weir_height_dbox.setValue(float(str(item.text())))

            item = self.weirs_tblw.item(row, 10)
            if item is not None:
                self.weir_width_dbox.setValue(float(str(item.text())))

            self.highlight_weir(self.weir_name_cbo.currentText())

            QApplication.restoreOverrideCursor()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 200618.0632: assignment of value failed!.\n", e)

    def find_weir(self):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if self.grid_lyr is not None:
                if self.grid_lyr:
                    weir = self.weir_to_find_le.text()
                    if weir != "":
                        indx = self.weir_name_cbo.findText(weir)
                        if indx != -1:
                            self.weir_name_cbo.setCurrentIndex(indx)
                        else:
                            self.uc.bar_warn("WARNING 070422.0836: weir '" + str(weir) + "' not found.")
                    else:
                        self.uc.bar_warn("WARNING  070422.0734: weir '" + str(weir) + "' not found.")
        except ValueError:
            self.uc.bar_warn("WARNING  070422.0735: weir '" + str(weir) + "' not found.")
            pass
        finally:
            QApplication.restoreOverrideCursor()

    def highlight_weir(self, weir):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if self.weirs_lyr is not None:
                if weir != "":
                    fid = self.gutils.execute(
                        "SELECT fid FROM user_swmm_weirs WHERE weir_name = ?;", (weir,)
                    ).fetchone()
                    self.lyrs.show_feat_rubber(self.weirs_lyr.id(), fid[0], QColor(Qt.yellow))
                    feat = next(self.weirs_lyr.getFeatures(QgsFeatureRequest(fid[0])))
                    x, y = feat.geometry().centroid().asPoint()
                    self.lyrs.zoom_to_all()
                    center_canvas(self.iface, x, y)
                    zoom(self.iface, 0.45)
                else:
                    self.uc.bar_warn("WARNING 070422.0760: weir '" + str(weir) + "' not found.")
                    self.lyrs.clear_rubber()
            QApplication.restoreOverrideCursor()

        except ValueError:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("WARNING 070422.0761: weir '" + str(weir) + "' is not valid.")
            self.lyrs.clear_rubber()
            pass

    def zoom_in_weir(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        weir = self.weir_name_cbo.currentText()
        fid = self.gutils.execute("SELECT fid FROM user_swmm_weirs WHERE weir_name = ?;", (weir,)).fetchone()
        self.lyrs.show_feat_rubber(self.weirs_lyr.id(), fid[0], QColor(Qt.yellow))
        feat = next(self.weirs_lyr.getFeatures(QgsFeatureRequest(fid[0])))
        x, y = feat.geometry().centroid().asPoint()
        center_canvas(self.iface, x, y)
        zoom(self.iface, 0.4)
        QApplication.restoreOverrideCursor()

    def zoom_out_weir(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        weir = self.weir_name_cbo.currentText()
        fid = self.gutils.execute("SELECT fid FROM user_swmm_weirs WHERE weir_name = ?;", (weir,)).fetchone()
        self.lyrs.show_feat_rubber(self.weirs_lyr.id(), fid[0], QColor(Qt.yellow))
        feat = next(self.weirs_lyr.getFeatures(QgsFeatureRequest(fid[0])))
        x, y = feat.geometry().centroid().asPoint()
        center_canvas(self.iface, x, y)
        zoom(self.iface, -0.4)
        QApplication.restoreOverrideCursor()

    def save_weirs(self):
        """
        Save changes of user_swmm_weirs layer.
        """
        update_qry = """
                        UPDATE user_swmm_weirs
                        SET
                            weir_name = ?,
                            weir_inlet = ?, 
                            weir_outlet = ?,
                            weir_type = ?,
                            weir_crest_height = ?,
                            weir_disch_coeff = ?,
                            weir_flap_gate = ?,
                            weir_end_contrac = ?,
                            weir_end_coeff = ?,
                            weir_side_slope = ?,
                            weir_shape = ?,
                            weir_height = ?,
                            weir_length = ?                                               
                        WHERE fid = ?;"""

        for row in range(0, self.weirs_tblw.rowCount()):
            item = QTableWidgetItem()
            fid = self.weir_name_cbo.itemData(row)

            item = self.weirs_tblw.item(row, 0)
            if item is not None:
                weir_name = str(item.text())

            item = self.weirs_tblw.item(row, 1)
            if item is not None:
                weir_inlet = str(item.text())

            item = self.weirs_tblw.item(row, 2)
            if item is not None:
                weir_outlet = str(item.text())

            item = self.weirs_tblw.item(row, 3)
            if item is not None:
                typ = str(item.text())
                weir_type = typ if typ.upper() in ["TRANSVERSE", "SIDEFLOW", "V-NOTCH", "TRAPEZOIDAL"] else "TRANSVERSE"
            else:
                weir_type ="TRANSVERSE"
                
            item = self.weirs_tblw.item(row, 4)
            if item is not None:
                weir_crest_height = str(item.text())

            item = self.weirs_tblw.item(row, 5)
            if item is not None:
                weir_disch_coeff = str(item.text())

            item = self.weirs_tblw.item(row, 6)
            if item is not None:
                gate = str(item.text())
                weir_flap_gate = gate if gate.upper() in ["YES", "NO"] else "YES"
            
            item = self.weirs_tblw.item(row, 7)
            if item is not None:
                end = str(item.text())
                weir_end_contrac = end if end in ["0", "1", "2"] else "0"

            item = self.weirs_tblw.item(row, 8)
            if item is not None:
                weir_end_coeff = str(item.text())

            item = self.weirs_tblw.item(row, 9)
            if item is not None:
                weir_side_slope = str(item.text())

            item = self.weirs_tblw.item(row, 10)
            if item is not None:
                shape = str(item.text())
                weir_shape = shape if shape in self.shape else "RECT_CLOSED"

            item = self.weirs_tblw.item(row, 11)
            if item is not None:
                weir_height = str(item.text())

            item = self.weirs_tblw.item(row, 12)
            if item is not None:
                weir_width = str(item.text())

            self.gutils.execute(
                update_qry,
                (
                    weir_name,
                    weir_inlet,
                    weir_outlet,
                    weir_type,
                    weir_crest_height,
                    weir_disch_coeff,
                    weir_flap_gate,
                    weir_end_contrac,
                    weir_end_coeff,
                    weir_side_slope,
                    weir_shape,
                    weir_height,
                    weir_width,
                    fid,
                ),
            )
