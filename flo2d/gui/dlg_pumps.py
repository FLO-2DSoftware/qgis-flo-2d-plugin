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

uiDialog, qtBaseClass = load_ui("pumps")


class PumpsDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None

        set_icon(self.find_pump_btn, "eye-svgrepo-com.svg")
        set_icon(self.zoom_in_pump_btn, "zoom_in.svg")
        set_icon(self.zoom_out_pump_btn, "zoom_out.svg")

        self.PumpCurv = None
        self.pumps_data_model = StandardItemModel()
        self.curve_data = None

        self.plot = plot
        self.table = table
        self.tview = table.tview
        self.plot_item_name = None
        self.d1, self.d2 = [[], []]

        self.find_pump_btn.clicked.connect(self.find_pump)
        self.zoom_in_pump_btn.clicked.connect(self.zoom_in_pump)
        self.zoom_out_pump_btn.clicked.connect(self.zoom_out_pump)

        self.pumps_buttonBox.button(QDialogButtonBox.Save).setText("Save to 'Storm Drain Pumps' User Layer")
        self.pump_name_cbo.currentIndexChanged.connect(self.fill_individual_controls_with_current_pump_in_table)

        self.pumps_buttonBox.accepted.connect(self.save_pumps)

        # self.pump_curve_cbo.activated.connect(self.show_pump_curve_table_and_plot)
        self.pump_curve_cbo.currentIndexChanged.connect(self.pump_curve_cbo_currentIndexChanged)

        self.pump_init_status_cbo.currentIndexChanged.connect(self.pump_init_status_cbo_currentIndexChanged)
        self.startup_depth_dbox.valueChanged.connect(self.startup_depth_dbox_valueChanged)
        self.shutoff_depth_dbox.valueChanged.connect(self.shutoff_depth_dbox_valueChanged)

        self.ON_OFF = ("ON", "OFF")

        self.setup_connection()
        self.grid_lyr = self.lyrs.data["grid"]["qlyr"]
        self.pumps_lyr = self.lyrs.data["user_swmm_pumps"]["qlyr"]
        self.populate_pumps()

        self.pumps_tblw.cellClicked.connect(self.pumps_tblw_cell_clicked)
        self.pumps_tblw.verticalHeader().sectionClicked.connect(self.onVerticalSectionClicked)

        self.pumps_data_model.dataChanged.connect(self.save_pump_curve_data)
        self.table.before_paste.connect(self.block_saving)
        self.table.after_paste.connect(self.unblock_saving)
        self.pumps_data_model.itemDataChanged.connect(self.tview.itemDataChangedSlot)

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_pumps(self):
        qry = """SELECT fid,
                        pump_name,
                        pump_inlet, 
                        pump_outlet,
                        pump_curve,
                        pump_init_status,
                        pump_startup_depth,
                        pump_shutoff_depth
                FROM user_swmm_pumps;"""
        wrong_status = 0
        try:
            self.populate_curves()
            rows = self.gutils.execute(qry).fetchall()
            self.pumps_tblw.setRowCount(0)
            for row_number, row_data in enumerate(rows):
                self.pumps_tblw.insertRow(row_number)
                for column, data in enumerate(row_data):
                    item = QTableWidgetItem()
                    item.setData(Qt.DisplayRole, data)  # item gets value of data (as QTableWidgetItem Class)

                    if column == 1:
                        # Fill the list of pump names:
                        self.pump_name_cbo.addItem(data, row_data[0])

                    # Fill all text boxes with data of first feature of query (first element in table user_swmm_pumps):
                    if row_number == 0:
                        if column == 2:
                            self.from_node_txt.setText(str(data))

                        elif column == 3:
                            self.to_node_txt.setText(str(data))

                        elif column == 4:
                            index = self.pump_curve_cbo.findText(data)
                            if index == -1:
                                index = 0
                            self.pump_curve_cbo.setCurrentIndex(index)

                        elif column == 5:
                            if data not in ("ON", "On", "on", "OFF", "Off", "off"):
                                wrong_status += 1
                                data = "OFF"
                                item.setData(Qt.DisplayRole, data)
                            index = self.pump_init_status_cbo.findText(data)
                            if index == -1:
                                index = 0
                            self.pump_init_status_cbo.setCurrentIndex(index)

                        elif column == 6:
                            self.startup_depth_dbox.setValue(data)

                        elif column == 7:
                            self.shutoff_depth_dbox.setValue(data)

                    if column > 0:  # Omit fid number (in column = 0)
                        if column in (1, 2, 3, 4, 5):
                            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                        if column == 5:
                            if data not in ("ON", "On", "on", "OFF", "Off", "off"):
                                wrong_status += 1
                                data = "OFF"
                                item.setData(Qt.DisplayRole, data)
                        self.pumps_tblw.setItem(row_number, column - 1, item)

            self.highlight_pump(self.pump_name_cbo.currentText())
            QApplication.restoreOverrideCursor()
            if wrong_status > 0:
                self.uc.show_info(
                    "WARNING 280222.1910: there were "
                    + str(wrong_status)
                    + " pumps with wrong initial status!\n\n"
                    + "All wrong initial status were changed to 'OFF' in this dialog.\n\n"
                    + "Edit them as wished and then 'Save' to replace the values in the 'Storm Drain Pumps' User layers."
                )
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 251121.0705: assignment of value from pumps users layer failed!.\n",
                e,
            )

    """
    Events for changes in values of widgets: 
    
    """

    def startup_depth_dbox_valueChanged(self):
        self.box_valueChanged(self.startup_depth_dbox, 5)

    def shutoff_depth_dbox_valueChanged(self):
        self.box_valueChanged(self.shutoff_depth_dbox, 6)

    """
    General routines for changes in widgets:
    
    """

    def box_valueChanged(self, widget, col):
        row = self.pump_name_cbo.currentIndex()
        item = QTableWidgetItem()
        item.setData(Qt.EditRole, widget.value())
        if col in (0, 1, 2, 3, 4):
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.pumps_tblw.setItem(row, col, item)

    def checkbox_valueChanged(self, widget, col):
        row = self.pump_name_cbo.currentIndex()
        item = QTableWidgetItem()
        if col in (0, 1, 2, 3, 4):
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.pumps_tblw.setItem(row, col, item)
        self.pumps_tblw.item(row, col).setText("True" if widget.isChecked() else "False")

    def combo_valueChanged(self, widget, col):
        row = self.pump_name_cbo.currentIndex()
        item = QTableWidgetItem()
        data = widget.currentText()
        item.setData(Qt.EditRole, data)
        if col in (0, 1, 2, 3, 4):
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.pumps_tblw.setItem(row, col, item)

    def pump_curve_cbo_currentIndexChanged(self):
        self.combo_valueChanged(self.pump_curve_cbo, 3)
        self.pump_curve_type_lbl.setText("Pump Type:")
        self.pump_curve_description_lbl.setText("Description:")
        name = self.pump_curve_cbo.currentText()
        curve = self.gutils.execute(
            "SELECT pump_curve_type, description FROM swmm_pumps_curve_data WHERE pump_curve_name = ?",
            (name,),
        ).fetchone()
        if curve:
            self.pump_curve_type_lbl.setText("Pump Type: " + curve[0] if curve[0] != None else "")
            self.pump_curve_description_lbl.setText("Description: " + curve[1] if curve[1] != None else "")

    def pump_init_status_cbo_currentIndexChanged(self):
        self.combo_valueChanged(self.pump_init_status_cbo, 4)

    def pumps_tblw_cell_clicked(self, row, column):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            # self.blockSignals(True)
            self.pump_name_cbo.blockSignals(True)
            self.pump_name_cbo.setCurrentIndex(row)
            self.pump_name_cbo.blockSignals(False)

            self.from_node_txt.setText(self.pumps_tblw.item(row, 1).text())
            self.to_node_txt.setText(self.pumps_tblw.item(row, 2).text())

            curve = self.pumps_tblw.item(row, 3).text()
            index = self.pump_curve_cbo.findText(curve)
            if index == -1:
                index = 0
            self.pump_curve_cbo.setCurrentIndex(index)



            status = self.pumps_tblw.item(row, 4).text()
            index = self.pump_init_status_cbo.findText(status)
            if index == -1:
                index = 1 # Select default "OFF".
                self.pumps_tblw.item(row, 4).setText("OFF")
                self.uc.bar_warn("WARNING 261128.0542: pump '" + name  + "' has wrong status '" + status + "'. Changed to default 'OFF'")                
            self.pump_init_status_cbo.setCurrentIndex(index)




            # status = self.pumps_tblw.item(row, 4).text()
            # if status.isdigit():
            #     index = int(status) - 1
            #     index = 1 if index > 1 else 0 if index < 0 else index
            # else:
            #     index = 0 if status == "ON" else 1
            # self.pump_init_status_cbo.setCurrentIndex(index)







            self.startup_depth_dbox.setValue(float_or_zero(self.pumps_tblw.item(row, 5).text()))
            self.shutoff_depth_dbox.setValue(float(self.pumps_tblw.item(row, 6).text()))

            self.highlight_pump(self.pump_name_cbo.currentText())

            QApplication.restoreOverrideCursor()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 261121.0707: assignment of value failed!.\n", e)

    def onVerticalSectionClicked(self, logicalIndex):
        self.pumps_tblw_cell_clicked(logicalIndex, 0)

    def fill_individual_controls_with_current_pump_in_table(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            # highlight row in table:
            row = self.pump_name_cbo.currentIndex()
            self.pumps_tblw.selectRow(row)

            # load controls (text boxes, etc.) with selected row in table:
            item = QTableWidgetItem()

            item = self.pumps_tblw.item(row, 1)
            if item is not None:
                self.from_node_txt.setText(str(item.text()))

            item = self.pumps_tblw.item(row, 2)
            if item is not None:
                self.to_node_txt.setText(str(item.text()))

            item = self.pumps_tblw.item(row, 3)
            if item is not None:
                indx = self.pump_curve_cbo.findText(item.text())
                if indx != -1:
                    self.pump_curve_cbo.setCurrentIndex(indx)
                else:
                    self.uc.bar_warn("WARNING 100222.1811: pump curve not found.")

            item = self.pumps_tblw.item(row, 4)
            if item is not None:
                if item.text() in ("ON", "on", "On", "1"):
                    self.pump_init_status_cbo.setCurrentIndex(0)
                else:
                    self.pump_init_status_cbo.setCurrentIndex(1)

            item = self.pumps_tblw.item(row, 5)
            if item is not None:
                self.startup_depth_dbox.setValue(float(str(item.text())))

            item = self.pumps_tblw.item(row, 6)
            if item is not None:
                self.shutoff_depth_dbox.setValue(float(str(item.text())))

            self.highlight_pump(self.pump_name_cbo.currentText())

            QApplication.restoreOverrideCursor()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 200618.0633: assignment of value failed!.\n", e)

    def find_pump(self):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if self.grid_lyr is not None:
                if self.grid_lyr:
                    pump = self.pump_to_find_le.text()
                    if pump != "":
                        indx = self.pump_name_cbo.findText(pump)
                        if indx != -1:
                            self.pump_name_cbo.setCurrentIndex(indx)
                        else:
                            self.uc.bar_warn("WARNING 091121.0746: pump '" + str(pump) + "' not found.")
                    else:
                        self.uc.bar_warn("WARNING  091121.0747: pump '" + str(pump) + "' not found.")
        except ValueError:
            self.uc.bar_warn("WARNING  091121.0748: pump '" + str(pump) + "' not forund.")
            pass
        finally:
            QApplication.restoreOverrideCursor()

    def highlight_pump(self, pump):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if self.pumps_lyr is not None:
                if pump != "":
                    fid = self.gutils.execute(
                        "SELECT fid FROM user_swmm_pumps WHERE pump_name = ?;", (pump,)
                    ).fetchone()
                    self.lyrs.show_feat_rubber(self.pumps_lyr.id(), fid[0], QColor(Qt.yellow))
                    feat = next(self.pumps_lyr.getFeatures(QgsFeatureRequest(fid[0])))
                    x, y = feat.geometry().centroid().asPoint()
                    self.lyrs.zoom_to_all()
                    center_canvas(self.iface, x, y)
                    zoom(self.iface, 0.45)
                else:
                    self.uc.bar_warn("WARNING 251121.1139: pump '" + str(pump) + "' not found.")
                    self.lyrs.clear_rubber()

            QApplication.restoreOverrideCursor()

        except ValueError:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("WARNING 251121.1134: pump '" + str(pump) + "' is not valid.")
            self.lyrs.clear_rubber()
            pass

    def zoom_in_pump(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        pump = self.pump_name_cbo.currentText()
        fid = self.gutils.execute("SELECT fid FROM user_swmm_pumps WHERE pump_name = ?;", (pump,)).fetchone()
        self.lyrs.show_feat_rubber(self.pumps_lyr.id(), fid[0], QColor(Qt.yellow))
        feat = next(self.pumps_lyr.getFeatures(QgsFeatureRequest(fid[0])))
        x, y = feat.geometry().centroid().asPoint()
        center_canvas(self.iface, x, y)
        zoom(self.iface, 0.4)
        QApplication.restoreOverrideCursor()

    def zoom_out_pump(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        pump = self.pump_name_cbo.currentText()
        fid = self.gutils.execute("SELECT fid FROM user_swmm_pumps WHERE pump_name = ?;", (pump,)).fetchone()
        self.lyrs.show_feat_rubber(self.pumps_lyr.id(), fid[0], QColor(Qt.yellow))
        feat = next(self.pumps_lyr.getFeatures(QgsFeatureRequest(fid[0])))
        x, y = feat.geometry().centroid().asPoint()
        center_canvas(self.iface, x, y)
        zoom(self.iface, -0.4)
        QApplication.restoreOverrideCursor()

    def show_pump_curve_clicked(self):
        self.uc.show_info("Show curve dialog")

    def save_pumps(self):
        """
        Save changes of user_swmm_pumps layer.
        """
        # self.save_attrs()
        update_qry = """
                        UPDATE user_swmm_pumps
                        SET
                           pump_name  = ?,
                           pump_inlet  = ?, 
                           pump_outlet  = ?,
                           pump_curve  = ?,
                           pump_init_status  = ?,
                           pump_startup_depth  = ?,
                           pump_shutoff_depth  = ?                           
                        WHERE fid = ?;"""

        for row in range(0, self.pumps_tblw.rowCount()):
            item = QTableWidgetItem()
            # fid = row + 1
            fid = self.pump_name_cbo.itemData(row)

            item = self.pumps_tblw.item(row, 0)
            if item is not None:
                pump_name = str(item.text())

            item = self.pumps_tblw.item(row, 1)
            if item is not None:
                pump_inlet = str(item.text())

            item = self.pumps_tblw.item(row, 2)
            if item is not None:
                pump_outlet = str(item.text())

            item = self.pumps_tblw.item(row, 3)
            if item is not None:
                pump_curve = str(item.text())

            item = self.pumps_tblw.item(row, 4)
            if item is not None:
                status = str(item.text())
                pump_init_status = status if status in ["ON", "OFF"] else "OFF"

            item = self.pumps_tblw.item(row, 5)
            if item is not None:
                pump_startup_depth = str(item.text())

            item = self.pumps_tblw.item(row, 6)
            if item is not None:
                pump_shutoff_depth = str(item.text())

            self.gutils.execute(
                update_qry,
                (
                    pump_name,
                    pump_inlet,
                    pump_outlet,
                    pump_curve,
                    pump_init_status,
                    pump_startup_depth,
                    pump_shutoff_depth,
                    fid,
                ),
            )

    def block_saving(self):
        try_disconnect(self.pumps_data_model.dataChanged, self.save_pump_curve_data)

    def unblock_saving(self):
        self.pumps_data_model.dataChanged.connect(self.save_pump_curve_data)

    def populate_curves(self):
        self.pump_curve_cbo.clear()
        self.pump_curve_cbo.addItem("*")
        curve = self.gutils.execute("SELECT DISTINCT pump_curve_name FROM swmm_pumps_curve_data")
        for c in curve:
            self.pump_curve_cbo.addItem(c[0])

        # self.pump_curve_cbo.clear()
        # self.pump_curve_cbo.addItem("*")
        # for row in self.PumpCurv.get_pump_curves():
        #     pc_fid, name = [x if x is not None else "" for x in row]
        #     if name != "":
        #         if self.pump_curve_cbo.findText(name) == -1:
        #             self.pump_curve_cbo.addItem(name, pc_fid)

    # def show_pump_curve_table_and_plot(self):
    #     idx = self.pump_curve_cbo.currentIndex()
    #     curve_fid = self.pump_curve_cbo.itemData(idx)
    #     curve_name = self.pump_curve_cbo.currentText()
    #     # if curve_name == "*":
    #     #     return
    #     #
    #
    #     if curve_fid is None:
    #         self.plot.clear()
    #         self.tview.undoStack.clear()
    #         self.tview.setModel(self.pumps_data_model)
    #         self.pumps_data_model.clear()
    #         return
    #
    #     self.curve_data = self.PumpCurv.get_pump_curve_data(curve_name)
    #     if not self.curve_data:
    #         return
    #     self.create_plot(curve_name)
    #     self.tview.undoStack.clear()
    #     self.tview.setModel(self.pumps_data_model)
    #     self.pumps_data_model.clear()
    #     self.pumps_data_model.setHorizontalHeaderLabels(["Depth", "Q"])
    #     self.d1, self.d2 = [[], []]
    #     for row in self.curve_data:
    #         items = [StandardItem("{:.4f}".format(x)) if x is not None else StandardItem("") for x in row]
    #         self.pumps_data_model.appendRow(items)
    #         self.d1.append(row[0] if not row[0] is None else float("NaN"))
    #         self.d2.append(row[1] if not row[1] is None else float("NaN"))
    #     rc = self.pumps_data_model.rowCount()
    #     if rc < 500:
    #         for row in range(rc, 500 + 1):
    #             items = [StandardItem(x) for x in ("",) * 2]
    #             self.pumps_data_model.appendRow(items)
    #     self.tview.horizontalHeader().setStretchLastSection(True)
    #     for col in range(2):
    #         self.tview.setColumnWidth(col, 100)
    #     for i in range(self.pumps_data_model.rowCount()):
    #         self.tview.setRowHeight(i, 20)
    #     self.update_plot()

    def create_plot(self, name):
        self.plot.clear()
        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)
        self.plot.plot.addLegend()
        self.plot_item_name = "Pump Curve:   " + name
        self.plot.add_item(self.plot_item_name, [self.d1, self.d2], col=QColor("#0018d4"))
        self.plot.plot.setTitle("Pump Curve:   " + name)

    def update_plot(self):
        if not self.plot_item_name:
            return
        self.d1, self.d2 = [[], []]
        for i in range(self.pumps_data_model.rowCount()):
            self.d1.append(m_fdata(self.pumps_data_model, i, 0))
            self.d2.append(m_fdata(self.pumps_data_model, i, 1))
        self.plot.update_item(self.plot_item_name, [self.d1, self.d2])

    def save_pump_curve_data(self):
        idx = self.pump_curve_cbo.currentIndex()
        pc_fid = self.pump_curve_cbo.itemData(idx)
        self.update_plot()
        pc_data = []
        for i in range(self.pumps_data_model.rowCount()):
            # save only rows with a number in the first column
            if is_number(m_fdata(self.pumps_data_model, i, 0)) and not isnan(m_fdata(self.pumps_data_model, i, 0)):
                pc_data.append(
                    (
                        pc_fid,
                        m_fdata(self.pumps_data_model, i, 0),
                        m_fdata(self.pumps_data_model, i, 1),
                    )
                )
            else:
                pass
        data_name = self.pump_curve_cbo.currentText()
        self.PumpCurv.set_pump_curve_data(pc_fid, data_name, pc_data)
