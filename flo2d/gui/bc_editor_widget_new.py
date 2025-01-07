# -*- coding: utf-8 -*-
from math import isnan

from PyQt5.QtCore import QSettings, QUrl
from PyQt5.QtGui import QColor, QDesktopServices
from PyQt5.QtWidgets import QInputDialog, QApplication, QFileDialog
from qgis._core import QgsProject, QgsFeatureRequest, QgsFeature, QgsGeometry, QgsPointXY
from qgis._gui import QgsRubberBand

from .table_editor_widget import StandardItem, StandardItemModel, CommandItemEdit
# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

from .ui_utils import load_ui, center_canvas, try_disconnect
from ..flo2dobjects import Inflow, Outflow
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication

from ..utils import is_number, m_fdata, set_BC_Border

from ..flo2d_tools.grid_tools import get_adjacent_cell

from qgis.PyQt.QtCore import Qt

import traceback

from ..flo2d_ie.flo2d_parser import ParseDAT

import processing

uiDialog, qtBaseClass = load_ui("bc_editor_new")


class BCEditorWidgetNew(qtBaseClass, uiDialog):
    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.uc = UserCommunication(iface, "FLO-2D")
        self.setupUi(self)

        self.lyrs = lyrs
        self.project = QgsProject.instance()
        self.bc_table = table
        self.bc_data_model = StandardItemModel()
        self.bc_data_model.clear()
        self.plot = plot
        self.plot.clear()
        self.table_dock = table
        self.bc_tview = table.tview
        self.bc_tview.setModel(self.bc_data_model)
        self.con = None
        self.gutils = None
        self.inflow = None
        self.outflow = None
        self.setup_connection()
        self.define_outflow_types()
        self.populate_outflow_type_cbo()
        self.populate_hydrograph_cbo()
        self.rb_tidal = []

        # Variable to catch the outflow or inflow changes
        self.bc_type = ""

        self.user_bc_tables = ["user_bc_points", "user_bc_lines", "user_bc_polygons"]

        self.bc_points_lyr = self.lyrs.data["user_bc_points"]["qlyr"]
        self.bc_lines_lyr = self.lyrs.data["user_bc_lines"]["qlyr"]
        self.bc_polygons_lyr = self.lyrs.data["user_bc_polygons"]["qlyr"]

        # inflow plot data variables
        self.t, self.d, self.m = [[], [], []]
        self.ot, self.od, self.om = [[], [], []]
        # outflow plot data variables
        self.d1, self.d2 = [[], []]

        # Connections
        self.inflow_grpbox.toggled.connect(self.add_shapes)
        self.outflow_grpbox.toggled.connect(self.add_shapes)
        self.bc_help_btn.clicked.connect(self.bc_help)

        # Inflow
        self.inflow_bc_name_cbo.activated.connect(
            self.inflow_changed)
        self.create_inflow_point_bc_btn.clicked.connect(
            lambda: self.create_bc("user_bc_points", "inflow", self.create_inflow_point_bc_btn))
        self.create_inflow_line_bc_btn.clicked.connect(
            lambda: self.create_bc("user_bc_lines", "inflow", self.create_inflow_line_bc_btn))
        self.rollback_inflow_btn.clicked.connect(
            lambda: self.cancel_bc_lyrs_edits("inflow"))
        self.open_inflow_btn.clicked.connect(
            lambda: self.open_data("inflow"))
        self.delete_schem_inflow_bc_btn.clicked.connect(
            lambda: self.delete_schematized_data("inflow"))
        self.add_inflow_data_btn.clicked.connect(
            lambda: self.add_data("inflow"))
        self.change_inflow_bc_name_btn.clicked.connect(
            lambda: self.change_bc_name(self.inflow_bc_name_cbo, "inflow"))
        self.delete_inflow_bc_btn.clicked.connect(
            lambda: self.delete_bc(self.inflow_bc_name_cbo, "inflow"))
        self.inflow_bc_center_btn.clicked.connect(
            self.inflow_bc_center)
        self.ifc_fplain_radio.clicked.connect(
            lambda: self.inflow_bc_changed(self.inflow_bc_name_cbo))
        self.ifc_chan_radio.clicked.connect(
            lambda: self.inflow_bc_changed(self.inflow_bc_name_cbo))
        self.inflow_type_cbo.activated.connect(
            lambda: self.inflow_bc_changed(self.inflow_bc_name_cbo))
        self.inflow_tseries_cbo.activated.connect(
            self.inflow_data_changed)
        self.change_inflow_data_name_btn.clicked.connect(
            lambda: self.change_bc_data_name(self.inflow_tseries_cbo, "inflow"))
        self.delete_inflow_ts_btn.clicked.connect(
            lambda: self.delete_ts_data(self.inflow_tseries_cbo, "inflow"))

        # Outflow
        self.outflow_bc_name_cbo.activated.connect(
            self.outflow_changed)
        self.create_outflow_point_bc_btn.clicked.connect(
            lambda: self.create_bc("user_bc_points", "outflow", self.create_outflow_point_bc_btn))
        self.create_outflow_line_bc_btn.clicked.connect(
            lambda: self.create_bc("user_bc_lines", "outflow", self.create_outflow_line_bc_btn))
        self.create_outflow_polygon_bc_btn.clicked.connect(
            lambda: self.create_bc("user_bc_polygons", "outflow", self.create_outflow_polygon_bc_btn))
        self.rollback_outflow_btn.clicked.connect(
            lambda: self.cancel_bc_lyrs_edits("outflow"))
        self.open_outflow_btn.clicked.connect(
            lambda: self.open_data("outflow"))
        self.create_all_border_outflow_bc_btn.clicked.connect(
            self.create_all_border_outflow_bc)
        self.delete_schem_outflow_bc_btn.clicked.connect(
            lambda: self.delete_schematized_data("outflow"))
        self.change_outflow_data_name_btn.clicked.connect(
            lambda: self.change_bc_data_name(self.outflow_data_cbo, "outflow"))
        self.add_outflow_data_btn.clicked.connect(
            lambda: self.add_data("outflow"))
        self.change_outflow_bc_name_btn.clicked.connect(
            lambda: self.change_bc_name(self.outflow_bc_name_cbo, "outflow"))
        self.delete_outflow_ts_btn.clicked.connect(
            lambda: self.delete_ts_data(self.outflow_data_cbo, "outflow"))
        self.delete_outflow_bc_btn.clicked.connect(
            lambda: self.delete_bc(self.outflow_bc_name_cbo, "outflow"))
        self.outflow_bc_center_btn.clicked.connect(
            self.outflow_bc_center)
        self.outflow_type_cbo.activated.connect(
            self.outflow_type_changed)
        self.outflow_hydro_cbo.activated.connect(
            self.outflow_hydrograph_changed)
        self.outflow_data_cbo.activated.connect(
            self.outflow_data_changed)

        self.schem_inflow_bc_btn.clicked.connect(self.schematize_inflow_bc)
        self.schem_outflow_bc_btn.clicked.connect(self.schematize_outflow_bc)

        # SIGNALS
        self.bc_points_lyr.featureAdded.connect(self.feature_added)
        self.bc_lines_lyr.featureAdded.connect(self.feature_added)
        self.bc_polygons_lyr.featureAdded.connect(self.feature_added)

        self.bc_table.before_paste.connect(self.block_saving)
        self.bc_table.after_paste.connect(self.unblock_saving)
        self.bc_table.after_delete.connect(self.save_bc_data)
        self.bc_data_model.dataChanged.connect(self.save_bc_data)
        self.bc_data_model.itemDataChanged.connect(self.itemDataChangedSlot)

        (
            out_deleted,
            time_stage_1,
            time_stage_2,
            border,
        ) = self.select_outflows_according_to_type()

        for layer in self.user_bc_tables:
            for feature in self.lyrs.data[layer]["qlyr"].getFeatures():
                type_value = feature['type']
                if type_value == 'inflow':
                    self.inflow_grpbox.setChecked(True)
                elif type_value == 'outflow':
                    self.outflow_grpbox.setChecked(True)

        if not self.inflow_bc_name_cbo.count():
            self.no_bc_disable("inflow")
        if not self.outflow_bc_name_cbo.count():
            self.no_bc_disable("outflow")

    def setup_connection(self):
        """
        Function to set up connection
        """
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
            interval = self.gutils.get_cont_par("IHOURDAILY")
            if interval is None:
                interval = 0
            else:
                interval = int(interval)
            self.inflow_interval_ckbx.setChecked(interval)
            self.inflow_interval_ckbx.stateChanged.connect(self.set_interval)

    def block_saving(self):
        try_disconnect(self.bc_data_model.dataChanged, self.save_bc_data)

    def unblock_saving(self):
        self.bc_data_model.dataChanged.connect(self.save_bc_data)

    def set_interval(self):
        state = str(int(self.inflow_interval_ckbx.isChecked()))
        self.gutils.set_cont_par("IHOURDAILY", state)

    def add_shapes(self):
        """
        Function to add the BC shapes
        """
        if self.inflow_grpbox.isChecked() or self.outflow_grpbox.isChecked():
            self.gutils.enable_geom_triggers()
            self.populate_inflows()
            self.populate_outflows()

    def bc_help(self):
        QDesktopServices.openUrl(QUrl("https://flo-2dsoftware.github.io/FLO-2D-Documentation/Plugin1000/widgets/boundary-condition-editor/index.html"))        

    def feature_added(self):
        """
        Function to only populate the bcs when editing is finished
        """
        self.gutils.fill_empty_inflow_names()
        self.gutils.fill_empty_outflow_names()

        self.populate_bcs(show_last_edited=True)

        self.repaint_bcs()

    def save_changes(self):
        """
        Function to save inflow changes
        """
        if not self.gutils or not self.lyrs.any_lyr_in_edit(*self.user_bc_tables):
            return
        self.delete_imported_bcs()
        # try to save user bc layers (geometry additions/changes)
        user_bc_edited = self.lyrs.save_lyrs_edits(*self.user_bc_tables)
        # if user bc layers were edited
        if user_bc_edited:
            # Update inflow or outflow names:
            self.gutils.fill_empty_inflow_names()
            self.gutils.fill_empty_outflow_names()

            # populate widgets and show last edited bc
            self.populate_bcs(show_last_edited=True)
        self.repaint_bcs()
        self.uncheck_btns()

    def discard_changes(self):
        """
        Function to discard changes in a layer in edit mode
        """
        for layer in self.user_bc_tables:
            if self.lyrs.data[layer]["qlyr"].isEditable():
                self.lyrs.data[layer]["qlyr"].rollBack()

    def delete_imported_bcs(self):
        """
        Function to delete imported inflow bcs
        """
        if self.inflow_grpbox.isChecked():
            self.gutils.delete_all_imported_inflows()
        if self.outflow_grpbox.isChecked():
            self.gutils.delete_all_imported_outflows()

    def repaint_bcs(self):
        """
        Function to repaint the bcs
        """
        self.lyrs.lyrs_to_repaint = [
            self.lyrs.data["all_schem_bc"]["qlyr"],
            self.lyrs.data["user_bc_points"]["qlyr"],
            self.lyrs.data["user_bc_lines"]["qlyr"],
            self.lyrs.data["user_bc_polygons"]["qlyr"],
        ]
        self.lyrs.repaint_layers()

    def create_bc(self, table, type, btn):
        """
        Function to create the bcs
        """
        self.gutils.enable_geom_triggers()

        self.inflow_bc_center_btn.setChecked(False)
        self.outflow_bc_center_btn.setChecked(False)

        self.bc_type = type
        if self.lyrs.any_lyr_in_edit(*self.user_bc_tables):
            self.uc.bar_info(f"{type.capitalize()} Boundary Condition(s) saved!")
            self.uc.log_info(f"{type.capitalize()} Boundary Condition(s) saved!")
            self.save_changes()
            self.uncheck_btns()
            return

        btn.setCheckable(True)
        btn.setChecked(True)

        if not self.lyrs.enter_edit_mode(table, {"type": type}):
            return

    def uncheck_btns(self):
        """
        Function to uncheck the checked buttons
        """
        self.create_inflow_point_bc_btn.setChecked(False)
        self.create_inflow_line_bc_btn.setChecked(False)
        self.create_outflow_point_bc_btn.setChecked(False)
        self.create_outflow_line_bc_btn.setChecked(False)
        self.create_outflow_polygon_bc_btn.setChecked(False)

    def populate_bcs(self, bc_fid=None, show_last_edited=False, widget_setup=False):
        """
        Function to populate data into the
        """
        self.lyrs.clear_rubber()
        if self.inflow_grpbox.isChecked():
            self.populate_inflows(
                inflow_fid=bc_fid,
                show_last_edited=show_last_edited,
                widget_setup=widget_setup,
            )
        if self.outflow_grpbox.isChecked():
            self.populate_outflows(
                outflow_fid=bc_fid,
                show_last_edited=show_last_edited,
                widget_setup=widget_setup,
            )

    def get_user_bc_lyr_for_geomtype(self, geom_type):
        table_name = "user_bc_{}s".format(geom_type)
        return self.lyrs.data[table_name]["qlyr"]

    def highlight_time_stage_cells(self, time_stage_1, time_stage_2):
        if not self.gutils.is_table_empty("outflow_cells"):
            for rb in self.rb_tidal:
                self.canvas.scene().removeItem(rb)
                del rb

            grid = self.lyrs.data["grid"]["qlyr"]
            lyr = self.lyrs.get_layer_tree_item(grid.id()).layer()
            gt = lyr.geometryType()

            if time_stage_1:
                for cell in time_stage_1:
                    rb = QgsRubberBand(self.canvas, gt)
                    rb.setColor(QColor(Qt.cyan))
                    fill_color = QColor(Qt.yellow)
                    fill_color.setAlpha(0)
                    rb.setFillColor(fill_color)
                    rb.setWidth(2)
                    try:
                        feat = next(lyr.getFeatures(QgsFeatureRequest(cell)))
                    except StopIteration:
                        return
                    rb.setToGeometry(feat.geometry(), lyr)
                    self.rb_tidal.append(rb)

            if time_stage_2:
                for cell in time_stage_2:
                    rb = QgsRubberBand(self.canvas, gt)
                    rb.setColor(QColor(Qt.red))
                    fill_color = QColor(Qt.red)
                    fill_color.setAlpha(0)
                    rb.setFillColor(fill_color)
                    rb.setWidth(2)
                    try:
                        feat = next(lyr.getFeatures(QgsFeatureRequest(cell)))
                    except StopIteration:
                        return
                    rb.setToGeometry(feat.geometry(), lyr)
                    self.rb_tidal.append(rb)

    def change_bc_data_name(self, cb, type):
        """
        Function to change the name of the BC Time Series
        """
        new_name, ok = QInputDialog.getText(None, "Change data name", "New name:")
        if not ok or not new_name:
            return
        self.bc_type = type
        # inflow
        if type == "inflow":
            if not cb.findText(new_name) == -1:
                msg = f"WARNING 060319.1620: Time series with name {new_name} " \
                      f"already exists in the database. Please, choose another name."
                self.uc.show_warn(msg)
                return
            self.inflow.set_time_series_data_name(new_name)
            self.populate_inflows(inflow_fid=self.inflow.fid)
        # outflow
        if type == "outflow":
            if not cb.findText(new_name) == -1:
                msg = f"WARNING 060319.1621: Data series with name {new_name} " \
                      f"already exists in the database. Please, choose another name."
                self.uc.show_warn(msg)
                return
            self.outflow.set_data_name(new_name)
            self.populate_outflows(outflow_fid=self.outflow.fid)

    # INFLOWS
    def populate_inflows(self, inflow_fid=None, show_last_edited=False, widget_setup=False):
        """
        Read inflow and inflow_time_series tables, populate proper combo boxes.
        """
        self.reset_inflow_gui()
        all_inflows = self.gutils.get_inflows_list()
        if not all_inflows and not widget_setup:
            return
        cur_name_idx = 0
        inflows_skipped = 0
        for i, row in enumerate(all_inflows):
            row = [x if x is not None else "" for x in row]
            fid, name, geom_type, ts_fid = row
            if not geom_type:
                inflows_skipped += 1
                continue
            if not name:
                name = "Inflow {}".format(fid)
            self.inflow_bc_name_cbo.addItem(name, [fid, ts_fid])
            if inflow_fid and fid == inflow_fid:
                cur_name_idx = i - inflows_skipped
        if not self.inflow_bc_name_cbo.count():
            if not widget_setup:
                self.uc.bar_info("There is no inflow defined in the database...")
                self.uc.log_info("There is no inflow defined in the database...")
            return
        if show_last_edited:
            cur_name_idx = i - inflows_skipped
        self.in_fid, self.ts_fid = self.inflow_bc_name_cbo.itemData(cur_name_idx)
        self.inflow = Inflow(self.in_fid, self.iface.f2d["con"], self.iface)
        self.inflow.get_row()
        self.inflow_bc_name_cbo.setCurrentIndex(cur_name_idx)
        self.inflow_changed()

        if self.inflow_bc_name_cbo.count():
            self.inflow_name_label.setDisabled(False)
            self.inflow_bc_name_cbo.setDisabled(False)
            self.change_inflow_bc_name_btn.setDisabled(False)
            self.delete_inflow_bc_btn.setDisabled(False)
            self.inflow_bc_center_btn.setDisabled(False)
            self.inflow_type_label.setDisabled(False)
            self.inflow_type_cbo.setDisabled(False)
            self.ifc_fplain_radio.setDisabled(False)
            self.ifc_chan_radio.setDisabled(False)
            self.inflow_tseries_label.setDisabled(False)
            self.inflow_tseries_cbo.setDisabled(False)
            self.add_inflow_data_btn.setDisabled(False)
            self.change_inflow_data_name_btn.setDisabled(False)
            self.delete_inflow_ts_btn.setDisabled(False)
            self.inflow_interval_ckbx.setDisabled(False)
            self.schematize_inflow_label.setDisabled(False)
            self.schem_inflow_bc_btn.setDisabled(False)

    def inflow_changed(self):
        self.bc_type = "inflow"
        bc_idx = self.inflow_bc_name_cbo.currentIndex()
        cur_data = self.inflow_bc_name_cbo.itemData(bc_idx)
        if cur_data:
            self.in_fid, self.ts_fid = cur_data
        else:
            return
        self.inflow = Inflow(self.in_fid, self.iface.f2d["con"], self.iface)
        self.inflow.get_row()
        if not is_number(self.ts_fid) or self.ts_fid == -1:
            self.ts_fid = 0
        else:
            self.ts_fid = int(self.ts_fid)
        self.inflow_tseries_cbo.setCurrentIndex(self.ts_fid)

        if self.inflow.ident == "F":
            self.ifc_fplain_radio.setChecked(1)
            self.ifc_chan_radio.setChecked(0)
        elif self.inflow.ident == "C":
            self.ifc_fplain_radio.setChecked(0)
            self.ifc_chan_radio.setChecked(1)
        else:
            self.ifc_fplain_radio.setChecked(0)
            self.ifc_chan_radio.setChecked(0)
        if not self.inflow.inoutfc == "":
            self.inflow_type_cbo.setCurrentIndex(self.inflow.inoutfc)
        else:
            self.inflow_type_cbo.setCurrentIndex(0)
        if not self.inflow.geom_type:
            return
        self.bc_lyr = self.get_user_bc_lyr_for_geomtype(self.inflow.geom_type)
        self.show_inflow_rb()
        if self.inflow_bc_center_btn.isChecked():
            feat = next(self.bc_lyr.getFeatures(QgsFeatureRequest(self.inflow.bc_fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
        self.populate_inflow_data_cbo()

    def populate_inflow_data_cbo(self):
        """
        Read and set inflow properties.
        """
        self.time_series = self.inflow.get_time_series()
        if not self.time_series:
            self.uc.bar_warn("No data series for this inflow.")
            return
        self.inflow_tseries_cbo.clear()
        cur_idx = 0
        for i, row in enumerate(self.time_series):
            row = [x if x is not None else "" for x in row]
            ts_fid, ts_name = row
            if not ts_name:
                ts_name = "Time Series {}".format(ts_fid)
            self.inflow_tseries_cbo.addItem(ts_name, str(ts_fid))
            # if ts_fid == self.inflow.time_series_fid:
            #     cur_idx = i
            #     self.uc.log_info(str(cur_idx))
        # self.inflow.time_series_fid = self.inflow_tseries_cbo.itemData(cur_idx)
        if isinstance(self.inflow.time_series_fid, int):
            index = self.inflow.time_series_fid - 1
            self.inflow_tseries_cbo.setCurrentIndex(index)
        # Sometimes it is an empty string, then set it to the first time series
        else:
            self.inflow_tseries_cbo.setCurrentIndex(0)
        self.inflow_data_changed()

    def inflow_data_changed(self):
        """
        Get current time series data, populate data table and create plot.
        """
        self.bc_type = "inflow"

        self.bc_table.after_delete.disconnect()
        self.bc_table.after_delete.connect(self.save_bc_data)

        cur_ts_idx = self.inflow_tseries_cbo.currentIndex()
        cur_ts_fid = self.inflow_tseries_cbo.itemData(cur_ts_idx)
        self.create_inflow_plot()

        self.bc_tview.undoStack.clear()
        self.bc_tview.setModel(self.bc_data_model)
        self.inflow.time_series_fid = cur_ts_fid

        self.infow_tseries_data = self.inflow.get_time_series_data()
        self.bc_data_model.clear()
        self.bc_data_model.setHorizontalHeaderLabels(["Time", "Discharge", "Mud"])
        self.ot, self.od, self.om = [[], [], []]
        if not self.infow_tseries_data:
            self.uc.bar_warn("No time series data defined for that inflow.")
            return
        for row in self.infow_tseries_data:
            items = [StandardItem(str(x)) if x is not None else StandardItem("") for x in row]
            self.bc_data_model.appendRow(items)
            self.ot.append(row[0] if not row[0] is None else float("NaN"))
            self.od.append(row[1] if not row[1] is None else float("NaN"))
            self.om.append(row[2] if not row[2] is None else float("NaN"))
        rc = self.bc_data_model.rowCount()

        if rc < 500:
            for row in range(rc, 500 + 1):
                items = [StandardItem(x) for x in ("",) * 3]
                self.bc_data_model.appendRow(items)

        self.bc_tview.resizeColumnsToContents()

        for i in range(self.bc_data_model.rowCount()):
            self.bc_tview.setRowHeight(i, 20)

        self.bc_tview.horizontalHeader().setStretchLastSection(True)

        for i in range(3):
            self.bc_tview.setColumnWidth(i, 90)

        self.save_inflow()
        self.create_inflow_plot()

    def show_inflow_rb(self):
        self.lyrs.show_feat_rubber(self.bc_lyr.id(), self.inflow.bc_fid)

    def reset_inflow_gui(self):
        """
        Function to reset the inflow gui
        """
        self.inflow_bc_name_cbo.clear()
        self.inflow_tseries_cbo.clear()
        self.bc_data_model.clear()
        self.plot.clear()

    def inflow_bc_center(self):
        """
        Function to check the inflow eye button
        """
        self.bc_type = "inflow"
        if self.inflow_bc_center_btn.isChecked():
            self.inflow_bc_center_btn.setChecked(True)
            return
        else:
            self.inflow_bc_center_btn.setChecked(False)
            return

    def create_inflow_plot(self):
        """
        Create initial plot.
        """
        self.plot.clear()
        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)
        self.plot.plot.addLegend()

        self.plot.add_item(
            "Original Discharge",
            [self.ot, self.od],
            col=QColor("#7dc3ff"),
            sty=Qt.DotLine,
        )
        self.plot.add_item("Current Discharge", [self.ot, self.od], col=QColor("#0018d4"))
        self.plot.add_item("Original Mud", [self.ot, self.om], col=QColor("#cd904b"), sty=Qt.DotLine)
        self.plot.add_item("Current Mud", [self.ot, self.om], col=QColor("#884800"))

    def save_inflow(self):
        """
        Get inflow and time series data from table view and save them to gpkg.
        """
        new_name = self.inflow_bc_name_cbo.currentText()
        # check if the name was changed
        if not self.inflow.name == new_name:
            if new_name in self.gutils.get_inflow_names():
                msg = "WARNING 060319.1622: Inflow with name {} already exists in the database. Please, choose another name.".format(
                    self.inflow.name
                )
                self.uc.show_warn(msg)
                return False
            else:
                self.inflow.name = new_name
        # save current inflow parameters
        self.inflow.set_row()
        self.save_inflow_data()

    def save_inflow_data(self):
        ts_data = []
        for i in range(self.bc_data_model.rowCount()):
            # save only rows with a number in the first column
            if is_number(m_fdata(self.bc_data_model, i, 0)) and not isnan(m_fdata(self.bc_data_model, i, 0)):
                ts_data.append(
                    (
                        self.inflow.time_series_fid,
                        m_fdata(self.bc_data_model, i, 0),
                        m_fdata(self.bc_data_model, i, 1),
                        m_fdata(self.bc_data_model, i, 2),
                    )
                )
            else:
                pass
        data_name = self.inflow_tseries_cbo.currentText()
        self.inflow.set_time_series_data(data_name, ts_data)
        self.update_inflow_plot()

    def update_inflow_plot(self):
        """
        When time series data for plot change, update the plot.
        """
        self.t, self.d, self.m = [[], [], []]
        for i in range(self.bc_data_model.rowCount()):
            self.t.append(m_fdata(self.bc_data_model, i, 0))
            self.d.append(m_fdata(self.bc_data_model, i, 1))
            self.m.append(m_fdata(self.bc_data_model, i, 2))
        try:
            self.plot.update_item("Current Discharge", [self.t, self.d])
            self.plot.update_item("Current Mud", [self.t, self.m])
        except:
            pass
        self.plot.auto_range()

    def change_bc_name(self, cb, type):
        """
        Function to change the inflow name
        """
        self.bc_type = type
        if not cb.count():
            if type == "inflow":
                self.no_bc_disable("inflow")
            if type == "outflow":
                self.no_bc_disable("outflow")
            return
        new_name, ok = QInputDialog.getText(None, "Change name", "New name:")
        if not ok or not new_name:
            return
        if not cb.findText(new_name) == -1:
            msg = f"WARNING 060319.1619: Boundary condition with name {new_name} already exists in the database. Please, choose another name."
            self.uc.show_warn(msg)
            return
        # inflow
        if type == "inflow":
            self.inflow.name = new_name
            self.inflow.set_row()
            self.populate_inflows(inflow_fid=self.inflow.fid)
        # outflow
        if type == "outflow":
            self.outflow.name = new_name
            self.outflow.set_row()
            self.populate_outflows(outflow_fid=self.outflow.fid)

    def delete_bc(self, cb, type):
        """
        Delete the current boundary condition from user layer and schematic tables.
        """
        if not cb.count():
            return
        q = "Are you sure, you want delete the current BC?"
        if not self.uc.question(q):
            return
        fid = None
        bc_idx = cb.currentIndex()
        cur_data = cb.itemData(bc_idx)
        if cur_data:
            fid = cur_data[0]
        else:
            return
        self.bc_type = type
        if fid and type == "inflow":
            self.inflow.del_row()
        elif fid and type == "outflow":
            self.outflow.del_row()
        else:
            pass
        self.repaint_bcs()
        # try to set current bc to the last before the deleted one
        try:
            self.populate_bcs(bc_fid=fid - 1)
        except Exception as e:
            self.populate_bcs()

        if not cb.count():
            if type == "inflow":
                self.no_bc_disable("inflow")
            if type == "outflow":
                self.no_bc_disable("outflow")

    def delete_ts_data(self, cb, type):
        """
        Function to delete/clear the time series
        """
        q = "Are you sure, you want delete the current Time Series?"
        if not self.uc.question(q):
            return
        self.bc_type = type
        if type == "inflow":
            inflow_bc_idx = cb.currentIndex() + 1
            qry = f"""
                    DELETE FROM inflow_time_series_data
                    WHERE series_fid = {inflow_bc_idx};
                   """
            self.gutils.execute(qry)
            qry = f"""
                    DELETE FROM inflow_time_series
                    WHERE fid = {inflow_bc_idx};
                   """
            self.gutils.execute(qry)
            self.populate_inflow_data_cbo()
            self.inflow_data_changed()
        if type == "outflow":
            outflow_bc_idx = self.outflow.get_cur_data_fid()
            if self.outflow.typ in [5, 6, 7, 8]:
                qry = f"""
                        DELETE FROM outflow_time_series_data
                        WHERE series_fid = {outflow_bc_idx};
                       """
                self.gutils.execute(qry)
                qry = f"""
                        DELETE FROM outflow_time_series
                        WHERE fid = {outflow_bc_idx};
                       """
                self.gutils.execute(qry)
            if self.outflow.typ == 9:
                qry = f"""
                        DELETE FROM qh_params_data
                        WHERE params_fid = {outflow_bc_idx};
                       """
                self.gutils.execute(qry)
                qry = f"""
                        DELETE FROM qh_params
                        WHERE fid = {outflow_bc_idx};
                       """
                self.gutils.execute(qry)
            if self.outflow.typ == 10:
                qry = f"""
                        DELETE FROM qh_table_data
                        WHERE table_fid = {outflow_bc_idx};
                       """
                self.gutils.execute(qry)
                qry = f"""
                        DELETE FROM qh_table
                        WHERE fid = {outflow_bc_idx};
                       """
                self.gutils.execute(qry)

            self.populate_outflow_data_cbo()
            self.outflow_data_changed()

            # # delete data and rename to Time Series 1
            # if cb.count() == 1:
            #     self.outflow.get_cur_data_fid()
            #     QgsMessageLog.logMessage(str(self.outflow.get_cur_data_fid()))
            # # delete everything
            # else:
            #     self.outflow.get_cur_data_fid()
            #     QgsMessageLog.logMessage(str(self.outflow.get_cur_data_fid()))

    def open_data(self, type):
        """
        Function to open the INFLOW.DAT and OUTFLOW.DAT
        """
        self.bc_type = type
        if type == "inflow":
            s = QSettings()
            last_dir = s.value("FLO-2D/lastGpkgDir", "")
            inflow_dat_path, __ = QFileDialog.getOpenFileName(
                None,
                "Select INFLOW.DAT with data to import",
                directory=last_dir,
                filter="INFLOW.DAT",
            )
            if not inflow_dat_path:
                return

            parser = ParseDAT()
            head, inf, res = parser.parse_inflow(inflow_dat_path)

            if head is not None:

                current_bc_cells = []

                current_bc_cells_sql = """SELECT * FROM inflow_cells"""
                bc_cells = self.gutils.execute(current_bc_cells_sql).fetchall()
                for cell in bc_cells:
                    current_bc_cells.append(str(cell[2]))

                insert_inflow_sql = [
                    """INSERT INTO inflow (name, time_series_fid, ident, inoutfc, geom_type, bc_fid) VALUES""",
                    6]
                insert_cells_sql = [
                    """INSERT INTO inflow_cells (inflow_fid, grid_fid, area_factor) VALUES""",
                    3]
                insert_ts_sql = [
                    """INSERT INTO inflow_time_series (fid, name) VALUES""",
                    2]
                insert_tsd_sql = [
                    """INSERT OR REPLACE INTO inflow_time_series_data (series_fid, time, value, value2) VALUES""",
                    4]

                update_all_schem_sql = []

                current_inflow_fid = self.gutils.execute("""SELECT MAX(fid) FROM inflow;""").fetchone()[0]
                if current_inflow_fid is not None:
                    current_inflow_fid = int(current_inflow_fid) + 1
                else:
                    current_inflow_fid = 1

                current_ts_fid = self.gutils.execute("""SELECT MAX(fid) FROM inflow_time_series;""").fetchone()[0]
                if current_ts_fid is not None:
                    current_ts_fid = int(current_ts_fid) + 1
                else:
                    current_ts_fid = 1

                bc_fid = self.gutils.execute(f"SELECT MAX(fid) FROM user_bc_points").fetchone()[0]
                if bc_fid is None:
                    bc_fid = 1
                else:
                    bc_fid = int(bc_fid) + 1

                new_bc_cells = []
                batch_updates = []

                for i, gid in enumerate(inf, 1):
                    row = inf[gid]["row"]
                    # insert
                    if gid not in current_bc_cells:
                        insert_inflow_sql += [(f'Inflow Cell {gid}', current_ts_fid, row[0], row[1], 'point', bc_fid)]
                        insert_cells_sql += [(current_inflow_fid, gid, 1)]
                        new_bc_cells.append(gid)
                        if inf[gid]["time_series"]:
                            insert_ts_sql += [(current_ts_fid, "Time series " + str(current_ts_fid))]
                            for n in inf[gid]["time_series"]:
                                insert_tsd_sql += [(current_ts_fid,) + tuple(n[1:])]
                            current_ts_fid += 1
                        current_inflow_fid += 1
                        update_all_schem_sql.append(
                            f"UPDATE all_schem_bc SET tab_bc_fid = {bc_fid} WHERE grid_fid = '{gid}'")
                        bc_fid += 1

                    # update
                    else:
                        # get the inflow fid
                        inflow_fid = self.gutils.execute(
                            f"SELECT inflow_fid FROM inflow_cells WHERE grid_fid = '{gid}'").fetchone()[0]

                        # UPDATE INFLOW
                        self.gutils.execute(
                            f"""UPDATE inflow SET 
                             ident = '{row[0][0]}',
                             inoutfc = '{row[1]}'
                             WHERE fid = {inflow_fid}"""
                        )

                        if inf[gid]["time_series"]:
                            time_series_fid = self.gutils.execute(
                                f"SELECT time_series_fid FROM inflow WHERE fid = '{inflow_fid}'").fetchone()[0]
                            n_ts_fids = self.gutils.execute(
                                f"SELECT fid FROM inflow_time_series_data WHERE series_fid = {time_series_fid}").fetchall()
                            for n in zip(n_ts_fids, inf[gid]["time_series"]):
                                if n[1][3]:
                                    batch_updates.append((time_series_fid, n[1][1], n[1][2], n[1][3], n[0][0]))
                                else:
                                    batch_updates.append((time_series_fid, n[1][1], n[1][2], n[0][0]))

                if len(batch_updates[0]) == 4:
                    self.gutils.execute_many(f"""UPDATE inflow_time_series_data SET
                                         series_fid = ?,
                                         time = ?,
                                         value = ?
                                         WHERE fid = ?""", batch_updates)
                else:
                    self.gutils.execute_many(f"""UPDATE inflow_time_series_data SET
                                         series_fid = ?,
                                         time = ?,
                                         value = ?,
                                         value2 = ?,
                                         WHERE fid = ?""", batch_updates)
                self.gutils.batch_execute(insert_ts_sql, insert_inflow_sql, insert_cells_sql, insert_tsd_sql)

                if len(update_all_schem_sql) > 0:
                    for qry in update_all_schem_sql:
                        self.gutils.execute(qry)

                schem_bc = self.lyrs.data['all_schem_bc']["qlyr"]
                user_bc = self.lyrs.data['user_bc_points']["qlyr"]

                new_features = []
                for feature in schem_bc.getFeatures():
                    if feature['type'] == "inflow" and str(feature['grid_fid']) not in current_bc_cells:
                        geometry = feature.geometry()
                        centroid = geometry.centroid().asPoint()
                        centroid_point = QgsPointXY(centroid.x(), centroid.y())
                        points_feature = QgsFeature(user_bc.fields())
                        points_feature.setAttribute('fid', feature['tab_bc_fid'])
                        points_feature.setAttribute('type', feature['type'])
                        points_feature.setGeometry(QgsGeometry.fromPointXY(centroid_point))
                        existing_features = [f for f in user_bc.getFeatures() if
                                             f.geometry().equals(points_feature.geometry())]
                        if not existing_features:
                            new_features.append(points_feature)
                user_bc.dataProvider().addFeatures(new_features)
                user_bc.updateExtents()
                user_bc.triggerRepaint()

                self.populate_inflows()

                self.uc.bar_info("Importing INFLOW.DAT completed!")
                self.uc.log_info("Importing INFLOW.DAT completed!")

        if type == "outflow":
            s = QSettings()
            last_dir = s.value("FLO-2D/lastGpkgDir", "")
            outflow_dat_path, __ = QFileDialog.getOpenFileName(
                None,
                "Select OUTFLOW.DAT with data to import",
                directory=last_dir,
                filter="OUTFLOW.DAT",
            )
            if not outflow_dat_path:
                return

            parser = ParseDAT()
            data = parser.parse_outflow(outflow_dat_path)

            if data is not None:

                current_bc_cells = []

                current_bc_cells_sql = """SELECT * FROM outflow_cells"""
                bc_cells = self.gutils.execute(current_bc_cells_sql).fetchall()
                for cell in bc_cells:
                    current_bc_cells.append(str(cell[2]))

                outflow_sql = [
                    """INSERT INTO outflow (fid, chan_out, fp_out, hydro_out, chan_tser_fid, chan_qhpar_fid,
                                                    chan_qhtab_fid, fp_tser_fid, geom_type, bc_fid) VALUES""",
                    10,
                ]

                cells_sql = ["""INSERT INTO outflow_cells (outflow_fid, grid_fid, geom_type, area_factor) VALUES""", 4]

                qh_params_sql = ["""INSERT INTO qh_params (fid) VALUES""", 1]

                qh_params_data_sql = [
                    """INSERT INTO qh_params_data (params_fid, hmax, coef, exponent) VALUES""",
                    4,
                ]

                qh_tab_sql = ["""INSERT INTO qh_table (fid) VALUES""", 1]

                qh_tab_data_sql = [
                    """INSERT INTO qh_table_data (table_fid, depth, q) VALUES""",
                    3,
                ]

                ts_sql = ["""INSERT INTO outflow_time_series (fid) VALUES""", 1]

                ts_data_sql = [
                    """INSERT INTO outflow_time_series_data (series_fid, time, value) VALUES""",
                    3,
                ]

                qh_params_fid = 0
                qh_tab_fid = self.gutils.execute("""SELECT MAX(fid) FROM qh_table;""").fetchone()[0]
                ts_fid = self.gutils.execute("""SELECT MAX(fid) FROM outflow_time_series;""").fetchone()[0]
                outflow_cells_fid = self.gutils.execute("""SELECT MAX(outflow_fid) FROM outflow_cells;""").fetchone()[0]
                outflow_fid = self.gutils.execute("""SELECT MAX(fid) FROM outflow_cells;""").fetchone()[0]
                bc_fid = self.gutils.execute(f"SELECT MAX(fid) FROM user_bc_points").fetchone()[0]
                if bc_fid is None:
                    bc_fid = 1
                else:
                    bc_fid = int(bc_fid) + 1

                if qh_tab_fid is not None:
                    qh_tab_fid = int(qh_tab_fid)
                else:
                    qh_tab_fid = 1

                if ts_fid is not None:
                    ts_fid = int(ts_fid)
                else:
                    ts_fid = 1

                if outflow_cells_fid is not None:
                    outflow_cells_fid = int(outflow_cells_fid) + 1
                else:
                    outflow_cells_fid = 1

                if outflow_fid is not None:
                    outflow_fid = int(outflow_fid) + 1
                else:
                    outflow_fid = 1

                update_all_schem_sql = []

                for gid, values in data.items():
                    chan_out = values["K"]
                    fp_out = values["O"]
                    hydro_out = values["hydro_out"]
                    chan_tser_fid, chan_qhpar_fid, chan_qhtab_fid, fp_tser_fid = [0] * 4
                    # Insert the outflow BC's
                    if str(gid) not in current_bc_cells:
                        if values["qh_params"]:
                            qh_params_fid += 1
                            chan_qhpar_fid = qh_params_fid
                            qh_params_sql += [(qh_params_fid,)]
                            for row in values["qh_params"]:
                                qh_params_data_sql += [(qh_params_fid,) + tuple(row)]
                        if values["qh_data"]:
                            qh_tab_fid += 1
                            chan_qhtab_fid = qh_tab_fid
                            qh_tab_sql += [(qh_tab_fid,)]
                            for row in values["qh_data"]:
                                qh_tab_data_sql += [(qh_tab_fid,) + tuple(row)]
                        if values["time_series"]:
                            ts_fid += 1
                            if values["N"] == 1:
                                fp_tser_fid = ts_fid
                            elif values["N"] == 2:
                                chan_tser_fid = ts_fid
                            else:
                                pass
                            ts_sql += [(ts_fid,)]
                            for row in values["time_series"]:
                                ts_data_sql += [(ts_fid,) + tuple(row)]

                        outflow_sql += [
                            (
                                outflow_fid,
                                chan_out,
                                fp_out,
                                hydro_out,
                                chan_tser_fid,
                                chan_qhpar_fid,
                                chan_qhtab_fid,
                                fp_tser_fid,
                                'point',
                                bc_fid,
                            )
                        ]

                        cells_sql += [(outflow_cells_fid, gid, 'point', 1)]

                        outflow_cells_fid += 1
                        outflow_fid += 1
                        update_all_schem_sql.append(
                            f"UPDATE all_schem_bc SET tab_bc_fid = {bc_fid} WHERE grid_fid = '{gid}'")
                        bc_fid += 1

                    # Update the outflow BC's
                    else:
                        # get the outflow fid
                        outflow = self.gutils.execute(
                            f"SELECT outflow_fid, geom_type, fid FROM outflow_cells WHERE grid_fid = '{gid}'").fetchone()

                        outflow_fid = outflow[0]
                        geom_type = outflow[1]

                        bc_fid = self.gutils.execute(
                            f"SELECT bc_fid FROM outflow WHERE fid = '{outflow_fid}'").fetchone()[0]

                        if geom_type != 'point':
                            outflow_fid = self.gutils.execute("""
                                        SELECT MAX(fid) FROM outflow;""").fetchone()[0] + 1
                            self.gutils.execute(f"""UPDATE outflow_cells SET
                                                geom_type = 'point',
                                                outflow_fid = '{outflow_fid}'
                                                WHERE grid_fid = '{gid}'""")
                            self.gutils.execute(f"""INSERT INTO outflow 
                                                    (chan_out, fp_out, hydro_out, chan_tser_fid, chan_qhpar_fid,
                                                    chan_qhtab_fid, fp_tser_fid, geom_type, bc_fid) VALUES
                                                    (0,0,0,0,0,0,0,'point', {bc_fid})""")
                            current_bc_cells.remove(gid)
                        if values["time_series"]:
                            # Floodplain
                            if values["N"] == 1:
                                fp_tser_fid = self.gutils.execute(
                                    f"SELECT fp_tser_fid FROM outflow WHERE fid = '{outflow_fid}'").fetchone()[0]
                                if fp_tser_fid is None or fp_tser_fid == 0:
                                    fp_tser_fid = self.gutils.execute("""
                                        SELECT MAX(series_fid) FROM outflow_time_series_data;""").fetchone()[0] + 1
                                    self.gutils.execute(f"""
                                    INSERT INTO outflow_time_series (fid) VALUES ('{fp_tser_fid}')""")
                                    for row in values["time_series"]:
                                        self.gutils.execute(f"""
                                            INSERT INTO outflow_time_series_data 
                                            (series_fid, time, value) VALUES 
                                            ('{fp_tser_fid}','{row[0]}' ,'{row[1]}')""")
                                    chan_tser_fid, chan_qhpar_fid, chan_qhtab_fid = [0] * 3
                                else:
                                    self.gutils.execute(
                                        f"DELETE FROM outflow_time_series_data WHERE series_fid = {fp_tser_fid}")
                                    for row in values["time_series"]:
                                        self.gutils.execute(f"""
                                            INSERT INTO outflow_time_series_data 
                                            (series_fid, time, value) VALUES 
                                            ('{fp_tser_fid}','{row[0]}' ,'{row[1]}')""")
                            # Channel
                            elif values["N"] == 2:
                                chan_tser_fid = self.gutils.execute(
                                    f"SELECT chan_tser_fid FROM outflow WHERE fid = '{outflow_fid}'").fetchone()[0]
                                if chan_tser_fid is None or chan_tser_fid == 0:
                                    chan_tser_fid = self.gutils.execute("""
                                        SELECT MAX(series_fid) FROM outflow_time_series_data;""").fetchone()[0]
                                    self.gutils.execute(f"""
                                                INSERT INTO outflow_time_series (fid) VALUES ('{chan_tser_fid}')""")
                                    for row in values["time_series"]:
                                        self.gutils.execute(f"""
                                                INSERT INTO outflow_time_series_data 
                                                (series_fid, time, value) VALUES 
                                                ('{chan_tser_fid}','{row[0]}' ,'{row[1]}')""")
                                    chan_qhpar_fid, chan_qhtab_fid, fp_tser_fid = [0] * 3
                                else:
                                    self.gutils.execute(
                                        f"DELETE FROM outflow_time_series_data WHERE series_fid = {chan_tser_fid}")
                                    for row in values["time_series"]:
                                        self.gutils.execute(f"""
                                                INSERT INTO outflow_time_series_data 
                                                (series_fid, time, value) VALUES 
                                                ('{chan_tser_fid}','{row[0]}' ,'{row[1]}')""")
                            else:
                                pass

                        if values["qh_data"]:
                            qh_tab_fid = self.gutils.execute(
                                f"SELECT chan_qhtab_fid FROM outflow WHERE fid = '{outflow_fid}'").fetchone()[0]
                            if qh_tab_fid == '' or qh_tab_fid == 0:
                                qh_tab_data_fid = self.gutils.execute("""
                                    SELECT MAX(table_fid) FROM qh_table_data;""").fetchone()[0]
                                if qh_tab_data_fid is None:
                                    qh_tab_fid = 1
                                else:
                                    qh_tab_fid = int(qh_tab_data_fid) + 1
                                self.gutils.execute(f"""
                                    INSERT INTO qh_table (fid) VALUES ({qh_tab_fid})""")
                                for row in values["qh_data"]:
                                    self.gutils.execute(f"""
                                    INSERT INTO qh_table_data 
                                    (table_fid, depth, q) VALUES 
                                    ('{qh_tab_fid}','{row[0]}' ,'{row[1]}')""")
                                chan_tser_fid, chan_qhpar_fid, fp_tser_fid = [0] * 3
                            else:
                                self.gutils.execute(
                                    f"DELETE FROM qh_table_data WHERE table_fid = '{qh_tab_fid}'")
                                for row in values["qh_data"]:
                                    self.gutils.execute(f"""
                                    INSERT INTO qh_table_data 
                                    (table_fid, depth, q) VALUES 
                                    ('{qh_tab_fid}','{row[0]}' ,'{row[1]}')""")
                            chan_qhtab_fid = qh_tab_fid

                        if values["qh_params"]:
                            qh_params_fid = self.gutils.execute(
                                f"SELECT chan_qhpar_fid FROM outflow WHERE fid = '{outflow_fid}'").fetchone()[0]
                            if qh_params_fid == '' or qh_params_fid == 0:
                                qh_params_data_fid = self.gutils.execute("""
                                    SELECT MAX(params_fid) FROM qh_params_data;""").fetchone()[0]
                                if qh_params_data_fid is None:
                                    qh_params_fid = 1
                                else:
                                    qh_params_fid = int(qh_params_data_fid) + 1
                                self.gutils.execute(f"""
                                    INSERT INTO qh_params (fid) VALUES ({qh_params_fid})""")
                                for row in values["qh_params"]:
                                    self.gutils.execute(f"""
                                    INSERT INTO qh_params_data 
                                    (params_fid, hmax, coef, exponent) VALUES 
                                    ('{qh_params_fid}','{row[0]}' ,'{row[1]}', '{row[2]}')""")
                                chan_tser_fid, chan_qhtab_fid, fp_tser_fid = [0] * 3
                            else:
                                self.gutils.execute(
                                    f"DELETE FROM qh_params_data WHERE params_fid = '{qh_params_fid}'")
                                for row in values["qh_params"]:
                                    self.gutils.execute(f"""
                                        INSERT INTO qh_params_data 
                                        (params_fid, hmax, coef, exponent) VALUES 
                                        ('{qh_params_fid}','{row[0]}' ,'{row[1]}', '{row[2]}')""")
                            chan_qhpar_fid = qh_params_fid

                        self.gutils.execute(
                            f"""UPDATE outflow SET
                                     chan_out = '{chan_out}',
                                     fp_out = '{fp_out}',
                                     hydro_out = '{hydro_out}',
                                     chan_tser_fid = '{chan_tser_fid}',
                                     chan_qhpar_fid = '{chan_qhpar_fid}',
                                     chan_qhtab_fid = '{chan_qhtab_fid}',
                                     fp_tser_fid = '{fp_tser_fid}',
                                     geom_type = 'point',
                                     bc_fid = {bc_fid}
                                     WHERE fid = {outflow_fid}"""
                        )

                self.gutils.batch_execute(
                    outflow_sql,
                    cells_sql,
                    qh_params_sql,
                    qh_params_data_sql,
                    qh_tab_sql,
                    qh_tab_data_sql,
                    ts_sql,
                    ts_data_sql,
                )

                self.gutils.execute("""UPDATE outflow
                                        SET chan_out = COALESCE(chan_out, 0),
                                            fp_out = COALESCE(fp_out, 0),
                                            hydro_out = COALESCE(hydro_out, 0),
                                            chan_tser_fid = COALESCE(chan_tser_fid, 0),
                                            chan_qhpar_fid = COALESCE(chan_qhpar_fid, 0),
                                            chan_qhtab_fid = COALESCE(chan_qhtab_fid, 0),
                                            fp_tser_fid = COALESCE(fp_tser_fid, 0);""")

                type_qry = f"""UPDATE outflow SET type = (CASE
                                            WHEN (fp_out > 0 AND chan_out = 0 AND fp_tser_fid = 0) THEN 1
                                            WHEN (fp_out = 0 AND chan_out > 0 AND chan_tser_fid = 0 AND
                                                  chan_qhpar_fid = 0 AND chan_qhtab_fid = 0) THEN 2
                                            WHEN (fp_out > 0 AND chan_out > 0) THEN 3
                                            WHEN (hydro_out > 0) THEN 4
                                            WHEN (fp_out = 0 AND fp_tser_fid > 0) THEN 5
                                            WHEN (chan_out = 0 AND chan_tser_fid > 0) THEN 6
                                            WHEN (fp_out > 0 AND fp_tser_fid > 0) THEN 7
                                            WHEN (chan_out > 0 AND chan_tser_fid > 0) THEN 8
                                            WHEN (chan_qhpar_fid > 0) THEN 9 
                                            WHEN (chan_qhtab_fid > 0) THEN 10
                                            ELSE 0
                                            END);"""

                self.gutils.execute(type_qry)
                # update series and tables names
                # outflow_name_qry = """UPDATE outflow SET name = 'Outflow ' ||  cast(fid as text) WHERE name IS NULL;"""
                outflow_name_qry = """
                                   UPDATE outflow
                                   SET name = 'Outflow ' || CAST(outflow_cells.grid_fid AS TEXT)
                                   FROM outflow_cells
                                   WHERE outflow.name IS NULL
                                   AND outflow.fid = outflow_cells.outflow_fid
                                   """
                self.gutils.execute(outflow_name_qry)
                ts_name_qry = """UPDATE outflow_time_series SET name = 'Time series ' ||  cast(fid as text);"""
                self.gutils.execute(ts_name_qry)
                qhpar_name_qry = """UPDATE qh_params SET name = 'Q(h) parameters ' ||  cast(fid as text);"""
                self.gutils.execute(qhpar_name_qry)
                qhtab_name_qry = """UPDATE qh_table SET name = 'Q(h) table ' ||  cast(fid as text);"""
                self.gutils.execute(qhtab_name_qry)

                if len(update_all_schem_sql) > 0:
                    for qry in update_all_schem_sql:
                        self.gutils.execute(qry)

                schem_bc = self.lyrs.data['all_schem_bc']["qlyr"]
                user_bc = self.lyrs.data['user_bc_points']["qlyr"]

                new_features = []
                for feature in schem_bc.getFeatures():
                    if feature['type'] == "outflow" and str(feature['grid_fid']) not in current_bc_cells:
                        geometry = feature.geometry()
                        centroid = geometry.centroid().asPoint()
                        centroid_point = QgsPointXY(centroid.x(), centroid.y())
                        points_feature = QgsFeature(user_bc.fields())
                        points_feature.setAttribute('fid', feature['tab_bc_fid'])
                        points_feature.setAttribute('type', feature['type'])
                        points_feature.setGeometry(QgsGeometry.fromPointXY(centroid_point))
                        existing_features = [f for f in user_bc.getFeatures() if
                                             f.geometry().equals(points_feature.geometry())]
                        if not existing_features:
                            new_features.append(points_feature)
                user_bc.dataProvider().addFeatures(new_features)
                user_bc.updateExtents()
                user_bc.triggerRepaint()

                self.gutils.execute("DELETE FROM outflow WHERE type = 0;")

                self.populate_outflows()

                self.uc.bar_info("Importing OUTFLOW.DAT completed!")
                self.uc.log_info("Importing OUTFLOW.DAT completed!")

        else:
            pass

    def add_data(self, type):
        if not self.gutils:
            return
        self.bc_type = type
        self.bc_data_model.clear()
        self.plot.clear()
        if type == "inflow":
            if not self.inflow:
                return
            if not self.inflow.time_series_fid:
                return
            self.inflow.add_time_series()
            self.populate_inflow_data_cbo()
        elif type == "outflow":
            if not self.outflow:
                return
            self.outflow.add_data()
            self.populate_outflow_data_cbo()
        else:
            pass

    def schematize_inflow_bc(self):
        """
        Function to schematize the inflow boundary conditions
        """
        # Code to test the performance
        # start_time = time.time()

        exist_user_bc = self.gutils.execute("SELECT * FROM all_user_bc WHERE type = 'inflow';").fetchone()
        if not exist_user_bc:
            self.uc.bar_warn("There are no inflow User Boundary Conditions (points, lines, or polygons) defined.")
        if not self.gutils.is_table_empty("all_schem_bc"):
            if not self.uc.question(
                    "There are some boundary conditions grid cells defined already.\n\n Overwrite them?"
            ):
                return

        self.bc_type = "inflow"
        QApplication.setOverrideCursor(Qt.WaitCursor)

        in_inserted = self.schematize_inflows()

        self.lyrs.lyrs_to_repaint = [self.lyrs.data["all_schem_bc"]["qlyr"]]
        self.lyrs.repaint_layers()

        QApplication.restoreOverrideCursor()
        m = str(in_inserted) + " inflows boundary conditions schematized!"
        self.uc.bar_info(m)
        self.uc.log_info(m)

        # QgsMessageLog.logMessage(f"Time taken to schematize: {round(time.time() - start_time, 2)} seconds")

    def schematize_outflow_bc(self):
        """
        Function to schematize the outflow boundary conditions
        """
        # Code to test the performance
        # start_time = time.time()

        exist_user_bc = self.gutils.execute("SELECT * FROM all_user_bc WHERE type = 'outflow';").fetchone()
        if not exist_user_bc:
            self.uc.bar_warn("There are no outflow User Boundary Conditions (points, lines, or polygons) defined.")
        if not self.gutils.is_table_empty("all_schem_bc"):
            if not self.uc.question(
                    "There are some boundary conditions grid cells defined already.\n\n Overwrite them?"
            ):
                return

        self.bc_type = "outflow"
        QApplication.setOverrideCursor(Qt.WaitCursor)

        out_inserted = self.schematize_outflows()

        (
            out_deleted,
            time_stage_1,
            time_stage_2,
            border,
        ) = self.select_outflows_according_to_type()
        self.highlight_time_stage_cells(time_stage_1, time_stage_2)

        if time_stage_1:
            set_BC_Border(border)

        self.lyrs.lyrs_to_repaint = [self.lyrs.data["all_schem_bc"]["qlyr"]]
        self.lyrs.repaint_layers()

        QApplication.restoreOverrideCursor()
        m = str(out_inserted - out_deleted)+ " outflows boundary conditions schematized!"
        self.uc.bar_info(m)
        self.uc.log_info(m)

    def schematize_bc(self):

        in_inserted, out_inserted, out_deleted = 0, 0, 0
        border = []
        exist_user_bc = self.gutils.execute("SELECT * FROM all_user_bc;").fetchone()
        if not exist_user_bc:
            self.uc.bar_warn("There are no User Boundary Conditions (points, lines, or polygons) defined.")
        if not self.gutils.is_table_empty("all_schem_bc"):
            if not self.uc.question(
                    "There are some boundary conditions grid cells defined already.\n\n Overwrite them?"
            ):
                return

        QApplication.setOverrideCursor(Qt.WaitCursor)

        out_inserted = self.schematize_outflows()
        in_inserted = self.schematize_inflows()

        (
            out_deleted,
            time_stage_1,
            time_stage_2,
            border,
        ) = self.select_outflows_according_to_type()
        self.highlight_time_stage_cells(time_stage_1, time_stage_2)

        if time_stage_1:
            set_BC_Border(border)

        self.lyrs.lyrs_to_repaint = [self.lyrs.data["all_schem_bc"]["qlyr"]]
        self.lyrs.repaint_layers()

        QApplication.restoreOverrideCursor()
        m = str(in_inserted) + " inflows and " + str(out_inserted - out_deleted) + "outflows boundary conditions " \
                                                                                   "schematized!"
        self.uc.bar_info(m)
        self.uc.log_info(m)

    def schematize_outflows(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.gutils.execute("DELETE FROM outflow_cells;")

            for geom_type in ['point', 'line', 'polygon']:
                ins_qry = f"""INSERT INTO outflow_cells (outflow_fid, grid_fid, geom_type)
                            SELECT outflow.fid as outflow_fid, g.fid as grid_fid, abc.geom_type
                            FROM
                                grid AS g
                            JOIN
                                all_user_bc AS abc ON ST_Intersects(CastAutomagic(g.geom), CastAutomagic(abc.geom))
                            JOIN
                                outflow ON abc.bc_fid = outflow.bc_fid
                            WHERE
                                abc.type = 'outflow' AND
                                abc.geom_type = '{geom_type}' AND
                                outflow.geom_type = '{geom_type}';"""
                inserted = self.gutils.execute(ins_qry)

            # outflow_cells = self.gutils.execute("SELECT * FROM outflow_cells ORDER BY fid;").fetchall()
            # # Fix outflow_cells:
            # for oc in outflow_cells:
            #     outflow_fid = oc[1]
            #     grid = oc[2]
            #     geom_type = oc[3]
            #     fid = self.gutils.execute(
            #         "SELECT fid FROM outflow WHERE geom_type = ? AND bc_fid = ?;",
            #         (
            #             geom_type,
            #             outflow_fid
            #         ),
            #     ).fetchone()
            #     if fid:
            #         self.gutils.execute(
            #             "UPDATE outflow_cells SET area_factor = ? WHERE fid = ?;",
            #             (1, oc[0]),
            #         )
            #     else:
            #         tab_bc_fid = self.gutils.execute(
            #             "SELECT tab_bc_fid FROM all_schem_bc WHERE grid_fid = ?;",
            #             (grid,),
            #         ).fetchone()
            #         if tab_bc_fid:
            #             self.gutils.execute(
            #                 "UPDATE outflow_cells SET outflow_fid = ? WHERE geom_type = ?;",
            #                 (tab_bc_fid[0], geom_type),
            #             )

            self.gutils.execute(f"""
                                UPDATE outflow
                                SET chan_out = COALESCE(chan_out, 0),
                                fp_out = COALESCE(fp_out, 0),
                                hydro_out = COALESCE(hydro_out, 0),
                                chan_tser_fid = COALESCE(chan_tser_fid, 0),
                                chan_qhpar_fid = COALESCE(chan_qhpar_fid, 0),
                                chan_qhtab_fid = COALESCE(chan_qhtab_fid, 0),
                                fp_tser_fid = COALESCE(fp_tser_fid, 0)
            """)

            QApplication.restoreOverrideCursor()
            return inserted.rowcount
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 180319.1434: Schematizing of outflows aborted!\n", e)
            self.uc.log_info(traceback.format_exc())
            return 0

    def schematize_inflows(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            del_qry = "DELETE FROM inflow_cells;"
            ins_qry = """INSERT INTO inflow_cells (inflow_fid, grid_fid)
                         SELECT 
                             inflow.fid AS inflow_fid, 
                             g.fid AS grid_fid
                         FROM
                             grid AS g
                         JOIN
                             all_user_bc AS abc 
                             ON (
                                 (abc.geom_type = 'point' AND ST_Intersects(CastAutomagic(g.geom), CastAutomagic(abc.geom))) OR 
                                 (abc.geom_type = 'line' AND ST_Crosses(CastAutomagic(g.geom), CastAutomagic(abc.geom)))
                             )
                         JOIN
                             inflow 
                             ON abc.bc_fid = inflow.bc_fid
                         WHERE
                             abc.type = 'inflow' 
                             AND abc.geom_type = inflow.geom_type;"""
            self.gutils.execute(del_qry)

            inserted = self.gutils.execute(ins_qry)
            QApplication.restoreOverrideCursor()
            return inserted.rowcount

        except Exception:
            QApplication.restoreOverrideCursor()
            self.uc.show_warn("WARNING 180319.1431: Schematizing of inflow aborted!")
            self.uc.log_info(traceback.format_exc())
            return 0

    def select_outflows_according_to_type(self):
        no_outflow, time_stage_1, time_stage_2, border = [], [], [], []
        try:
            cell_side = self.gutils.get_cont_par("CELLSIZE")
            if cell_side:
                cell_size = float(cell_side)
                if not self.gutils.is_table_empty("outflow_cells"):
                    grid_lyr = self.lyrs.data["grid"]["qlyr"]
                    cells = self.gutils.execute("SELECT grid_fid, outflow_fid, geom_type FROM outflow_cells").fetchall()
                    if cells:
                        for cell in cells:
                            grid_fid, outflow_fid, geom_type = cell
                            if geom_type == "polygon":
                                row = self.gutils.execute(
                                    "SELECT type FROM outflow WHERE geom_type = ? AND fid = ?;",
                                    (
                                        geom_type,
                                        outflow_fid,
                                    ),
                                ).fetchone()

                                if row:
                                    if row[0] == 0:  # Outflow type selected as 'No Outflow'. Tag it to remove it,
                                        no_outflow.append(grid_fid)
                                    elif row[0] in [0, 1, 4, 5, 7]:

                                        currentCell = next(grid_lyr.getFeatures(QgsFeatureRequest(grid_fid)))
                                        xx, yy = currentCell.geometry().centroid().asPoint()

                                        # North cell:
                                        y = yy + cell_size
                                        x = xx
                                        n_grid = self.gutils.grid_on_point(x, y)

                                        # NorthEast cell
                                        y = yy + cell_size
                                        x = xx + cell_size
                                        ne_grid = self.gutils.grid_on_point(x, y)

                                        # East cell:
                                        y = yy
                                        x = xx + cell_size
                                        e_grid = self.gutils.grid_on_point(x, y)

                                        # SouthEast cell:
                                        y = yy - cell_size
                                        x = xx + cell_size
                                        se_grid = self.gutils.grid_on_point(x, y)

                                        # South cell:
                                        y = yy - cell_size
                                        x = xx
                                        s_grid = self.gutils.grid_on_point(x, y)

                                        # SouthWest cell:
                                        y = yy - cell_size
                                        x = xx - cell_size
                                        sw_grid = self.gutils.grid_on_point(x, y)

                                        # West cell:
                                        y = yy
                                        x = xx - cell_size
                                        w_grid = self.gutils.grid_on_point(x, y)

                                        # NorthWest cell:
                                        y = yy + cell_size
                                        x = xx - cell_size
                                        nw_grid = self.gutils.grid_on_point(x, y)

                                        a = nw_grid is None and n_grid and w_grid
                                        b = sw_grid is None and w_grid and s_grid
                                        c = se_grid is None and e_grid and s_grid
                                        d = ne_grid is None and n_grid and e_grid

                                        if a or b or c or d:
                                            # It is a diagonal cell, remove it:
                                            no_outflow.append(grid_fid)
                                        else:  # Find adjacent inner cells:
                                            if all([n_grid, ne_grid, e_grid, se_grid, s_grid, sw_grid, w_grid,
                                                    nw_grid]):
                                                no_outflow.append(grid_fid)
                                            else:
                                                border.append(grid_fid)

                                                if row[0] == 5:  # Time stage => select adjacent inner cells
                                                    this = None
                                                    if w_grid and e_grid and s_grid:
                                                        this = s_grid
                                                    elif n_grid and s_grid and w_grid:
                                                        this = w_grid
                                                    elif w_grid and e_grid and n_grid:
                                                        this = n_grid
                                                    elif n_grid and s_grid and e_grid:
                                                        this = e_grid

                                                    if this is not None:
                                                        if this not in time_stage_1:
                                                            time_stage_1.append(this)

                                                    if False:
                                                        pass
                                                    elif w_grid and not e_grid and s_grid:
                                                        this = s_grid
                                                    elif n_grid and not s_grid and w_grid:
                                                        this = w_grid
                                                    elif w_grid and not e_grid and n_grid and ne_grid:
                                                        this = n_grid
                                                    elif n_grid and not s_grid and e_grid:
                                                        this = e_grid
                                                    elif not n_grid and not w_grid and e_grid:
                                                        this = e_grid

                                                    if this is not None:
                                                        if this not in time_stage_1 + time_stage_2:
                                                            adj_cell = get_adjacent_cell(
                                                                self.gutils,
                                                                grid_lyr,
                                                                this,
                                                                "N",
                                                                cell_size,
                                                            )
                                                            if adj_cell is not None:
                                                                adj_cell = get_adjacent_cell(
                                                                    self.gutils,
                                                                    grid_lyr,
                                                                    this,
                                                                    "E",
                                                                    cell_size,
                                                                )
                                                                if adj_cell is not None:
                                                                    adj_cell = get_adjacent_cell(
                                                                        self.gutils,
                                                                        grid_lyr,
                                                                        this,
                                                                        "S",
                                                                        cell_size,
                                                                    )
                                                                    if adj_cell is not None:
                                                                        adj_cell = get_adjacent_cell(
                                                                            self.gutils,
                                                                            grid_lyr,
                                                                            this,
                                                                            "W",
                                                                            cell_size,
                                                                        )
                                                                        if adj_cell is not None:
                                                                            time_stage_2.append(this)

                            elif geom_type == "line" or geom_type == "point":
                                rows = self.gutils.execute(
                                    "SELECT type FROM outflow WHERE geom_type = ? AND bc_fid = ?;",
                                    (
                                        geom_type,
                                        outflow_fid,
                                    ),
                                ).fetchall()
                                if rows:
                                    for row in rows:
                                        if row[0] == 0:  # No outflow
                                            no_outflow.append(grid_fid)

                        if no_outflow:
                            if time_stage_1:
                                for cell in time_stage_1:
                                    if cell in no_outflow:
                                        no_outflow.remove(cell)

                            if time_stage_2:
                                for cell in time_stage_2:
                                    if cell in no_outflow:
                                        no_outflow.remove(cell)

                            for cell in no_outflow:
                                self.gutils.execute(
                                    "DELETE FROM outflow_cells WHERE grid_fid = ?;",
                                    (cell,),
                                )

                return (
                    len(no_outflow),
                    list(set(time_stage_1 + time_stage_2)),
                    [],
                    border,
                )

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 280522.0729: error selecting outflows according to type!!"
                + "\n__________________________________________________",
                e,
            )
        finally:
            return len(no_outflow), list(set(time_stage_1 + time_stage_2)), [], border

    def inflow_bc_changed(self, cb):
        """
        Function to save changes on the floodplain/channel and on inflow type
        """
        self.bc_type = "inflow"
        if cb.count():
            if self.ifc_fplain_radio.isChecked():
                self.inflow.ident = "F"
            else:
                self.inflow.ident = "C"
            self.inflow.inoutfc = self.inflow_type_cbo.currentIndex()
            self.save_inflow()
        else:
            self.inflow_name_label.setDisabled(True)
            self.inflow_bc_name_cbo.setDisabled(True)
            self.change_inflow_bc_name_btn.setDisabled(True)
            self.delete_inflow_bc_btn.setDisabled(True)
            self.inflow_bc_center_btn.setDisabled(True)
            self.inflow_type_label.setDisabled(True)
            self.inflow_type_cbo.setDisabled(True)
            self.ifc_fplain_radio.setDisabled(True)
            self.ifc_chan_radio.setDisabled(True)
            self.inflow_tseries_label.setDisabled(True)
            self.inflow_tseries_cbo.setDisabled(True)
            self.add_inflow_data_btn.setDisabled(True)
            self.change_inflow_data_name_btn.setDisabled(True)
            self.delete_inflow_ts_btn.setDisabled(True)
            self.inflow_interval_ckbx.setDisabled(True)
            self.schematize_inflow_label.setDisabled(True)
            self.schem_inflow_bc_btn.setDisabled(True)

    def outflow_bc_center(self):
        """
        Function to check the outflow eye button
        """
        self.bc_type = "outflow"
        if self.outflow_bc_center_btn.isChecked():
            self.outflow_bc_center_btn.setChecked(True)
            return
        else:
            self.outflow_bc_center_btn.setChecked(False)
            return

    def populate_outflows(self, outflow_fid=None, show_last_edited=False, widget_setup=False):
        """
        Read outflow table, populate the cbo and set proper outflow.
        """
        self.reset_outflow_gui()
        all_outflows = self.gutils.get_outflows_list()
        if not all_outflows and not widget_setup:
            return
        cur_out_idx = 0
        outflows_skipped = 0
        for i, row in enumerate(all_outflows):
            row = [x if x is not None else "" for x in row]
            fid, name, typ, geom_type = row
            if not geom_type:
                outflows_skipped += 1
                continue
            if not name:
                name = "Outflow {}".format(fid)
            self.outflow_bc_name_cbo.addItem(name, [fid, typ, geom_type])
            if fid == outflow_fid:
                cur_out_idx = i - outflows_skipped

        if not self.outflow_bc_name_cbo.count():
            if not widget_setup:
                self.uc.bar_info("There is no outflow defined in the database...")
                self.uc.log_info("There is no outflow defined in the database...")
            return
        if show_last_edited:
            cur_out_idx = i - outflows_skipped
        self.out_fid, self.type_fid, self.geom_type = self.outflow_bc_name_cbo.itemData(cur_out_idx)
        self.outflow = Outflow(self.out_fid, self.iface.f2d["con"], self.iface)
        self.outflow.get_row()

        if not self.outflow.geom_type:
            return
        self.bc_lyr = self.get_user_bc_lyr_for_geomtype(self.outflow.geom_type)
        self.show_outflow_rb()
        if self.outflow.hydro_out:
            self.outflow_hydro_cbo.setCurrentIndex(self.outflow.hydro_out)
        self.outflow_bc_name_cbo.setCurrentIndex(cur_out_idx)
        self.outflow_changed()

        if self.outflow_bc_name_cbo.count():
            self.outflow_name_label.setDisabled(False)
            self.outflow_bc_name_cbo.setDisabled(False)
            self.change_outflow_bc_name_btn.setDisabled(False)
            self.delete_outflow_bc_btn.setDisabled(False)
            self.outflow_bc_center_btn.setDisabled(False)
            self.outflow_type_label.setDisabled(False)
            self.outflow_type_cbo.setDisabled(False)
            self.schematize_outflow_label.setDisabled(False)
            self.schem_outflow_bc_btn.setDisabled(False)
            if self.outflow_type_cbo.currentIndex() == 0 or self.outflow_type_cbo.currentIndex() == 1:
                self.outflow_hydro_label.setDisabled(True)
                self.outflow_hydro_cbo.setDisabled(True)
                self.outflow_data_label.setDisabled(True)
                self.outflow_data_cbo.setDisabled(True)
                self.add_outflow_data_btn.setDisabled(True)
                self.change_outflow_data_name_btn.setDisabled(True)
                self.delete_outflow_ts_btn.setDisabled(True)

    def reset_outflow_gui(self):
        """
        Function to reset the outflow gui
        """
        self.outflow_bc_name_cbo.clear()
        self.outflow_data_cbo.clear()
        self.outflow_type_cbo.setCurrentIndex(0)
        self.outflow_hydro_cbo.setCurrentIndex(0)
        self.outflow_hydro_cbo.setDisabled(True)
        self.outflow_data_cbo.setDisabled(True)
        self.change_outflow_data_name_btn.setDisabled(True)
        self.add_outflow_data_btn.setDisabled(True)
        self.delete_outflow_ts_btn.setDisabled(True)
        self.bc_data_model.clear()
        self.plot.clear()

    def show_outflow_rb(self):
        """
        Function to show the outflow rubberband
        """
        self.lyrs.show_feat_rubber(self.bc_lyr.id(), self.outflow.bc_fid)

    def show_editor(self, user_bc_table=None, bc_fid=None):
        if user_bc_table:
            qry = f"""SELECT
                        type
                    FROM
                        {user_bc_table}
                    WHERE
                        fid = {bc_fid}"""

            typ = self.gutils.execute(qry).fetchone()[0]
            self.populate_bcs(bc_fid)
            if typ == "inflow":
                self.populate_inflow_data_cbo()
            if typ == "outflow":
                self.populate_outflow_data_cbo()

    def outflow_changed(self):
        self.bc_type = "outflow"
        self.enable_outflow_types()
        bc_idx = self.outflow_bc_name_cbo.currentIndex()
        cur_data = self.outflow_bc_name_cbo.itemData(bc_idx)
        self.bc_tview.undoStack.clear()
        self.bc_tview.setModel(self.bc_data_model)
        self.bc_data_model.clear()
        self.plot.clear()
        if cur_data:
            self.out_fid, self.type_fid, self.geom_type = cur_data
        else:
            return
        self.outflow = Outflow(self.out_fid, self.iface.f2d["con"], self.iface)
        self.outflow.get_row()
        if not is_number(self.outflow.typ):
            self.type_fid = 0
        else:
            self.type_fid = int(self.outflow.typ)
        if not self.outflow.geom_type:
            return
        self.bc_lyr = self.get_user_bc_lyr_for_geomtype(self.outflow.geom_type)
        self.show_outflow_rb()
        if self.outflow_bc_center_btn.isChecked():
            feat = next(self.bc_lyr.getFeatures(QgsFeatureRequest(self.outflow.bc_fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
        self.outflow_type_cbo.setCurrentIndex(self.type_fid)
        self.outflow_type_changed()
        if self.geom_type == "polygon":
            self.disable_outflow_types()

    def enable_outflow_types(self):
        for idx in range(0, self.outflow_type_cbo.count()):
            self.outflow_type_cbo.model().item(idx).setEnabled(True)

    def outflow_type_changed(self):
        self.bc_type = "outflow"
        self.bc_data_model.clear()
        typ_idx = self.outflow_type_cbo.currentIndex()
        self.set_outflow_widgets(typ_idx)
        self.outflow.set_type_data(typ_idx)
        self.outflow.set_row()
        self.populate_outflow_data_cbo()

    def set_outflow_widgets(self, outflow_type):
        self.outflow_data_cbo.clear()
        self.outflow_data_cbo.setDisabled(True)
        self.outflow_data_label.setDisabled(True)
        self.add_outflow_data_btn.setDisabled(True)
        self.change_outflow_data_name_btn.setDisabled(True)
        self.delete_outflow_ts_btn.setDisabled(True)
        if not outflow_type == 4:
            self.outflow_hydro_cbo.setCurrentIndex(0)
            self.outflow_hydro_cbo.setDisabled(True)
            self.outflow_hydro_label.setDisabled(True)
        self.bc_data_model.clear()
        self.plot.clear()
        if outflow_type == -1:
            outflow_type = 0
        out_par = self.outflow_types[outflow_type]
        for wid in out_par["wids"]:
            wid.setEnabled(True)
        self.outflow_tab_head = out_par["tab_head"]

    def define_outflow_types(self):
        self.outflow_types = {
            0: {"name": "No outflow", "wids": [], "data_label": "", "tab_head": None},
            1: {
                "name": "Floodplain outflow (no hydrograph)",
                "wids": [],
                "data_label": "",
                "tab_head": None,
            },
            2: {
                "name": "Channel outflow (no hydrograph)",
                "wids": [],
                "data_label": "",
                "tab_head": None,
            },
            3: {
                "name": "Floodplain and channel outflow (no hydrograph)",
                "wids": [],
                "data_label": "",
                "tab_head": None,
            },
            4: {
                "name": "Outflow with hydrograph",
                "wids": [self.outflow_hydro_cbo],
                "data_label": "",
                "tab_head": None,
            },
            5: {
                "name": "Time-stage for floodplain",
                "wids": [
                    self.outflow_data_cbo,
                    self.change_outflow_data_name_btn,
                    self.add_outflow_data_btn,
                    self.plot,
                ],
                "data_label": "Time series",
                "tab_head": ["Time", "Stage"],
            },
            6: {
                "name": "Time-stage for channel",
                "wids": [
                    self.outflow_data_cbo,
                    self.change_outflow_data_name_btn,
                    self.add_outflow_data_btn,
                    self.plot,
                ],
                "data_label": "Time series",
                "tab_head": ["Time", "Stage"],
            },
            7: {
                "name": "Time-stage for floodplain and free floodplain and channel",
                "wids": [
                    self.outflow_data_cbo,
                    self.change_outflow_data_name_btn,
                    self.add_outflow_data_btn,
                    self.plot,
                ],
                "data_label": "Time series",
                "tab_head": ["Time", "Stage"],
            },
            8: {
                "name": "Time-stage for channel and free floodplain and channel",
                "wids": [
                    self.outflow_data_cbo,
                    self.change_outflow_data_name_btn,
                    self.add_outflow_data_btn,
                    self.plot,
                ],
                "data_label": "Time series",
                "tab_head": ["Time", "Stage"],
            },
            9: {
                "name": "Channel Depth-Discharge Power Regression (Q(h)) params)",
                "wids": [self.outflow_data_cbo, self.change_outflow_data_name_btn, self.add_outflow_data_btn, ],
                "data_label": "Q(h) parameters",
                "tab_head": ["Hmax", "Coef", "Exponent"],
            },
            # 10: {
            #     "name": "Channel depth-discharge (Q(h) parameters)",
            #     "wids": [self.outflow_data_cbo, self.change_outflow_data_name_btn, self.add_outflow_data_btn, ],
            #     "data_label": "Q(h) parameters",
            #     "tab_head": ["Hmax", "Coef", "Exponent"],
            # },
            10: {
                "name": "Channel depth-discharge (Q(h) table)",
                "wids": [
                    self.outflow_data_cbo,
                    self.change_outflow_data_name_btn,
                    self.add_outflow_data_btn,
                    self.plot,
                ],
                "data_label": "Q(h) table",
                "tab_head": ["Depth", "Discharge"],
            },
        }

    def populate_outflow_data_cbo(self):
        self.series = None
        if self.outflow.typ == 4:
            self.outflow_hydro_label.setDisabled(False)
            if self.outflow.hydro_out:
                self.outflow_hydro_cbo.setCurrentIndex(self.outflow.hydro_out)
            else:
                self.outflow_hydro_cbo.setCurrentIndex(1)
                self.outflow_hydrograph_changed()
            return
        elif self.outflow.typ > 4:
            self.create_outflow_plot()
            self.series = self.outflow.get_data_fid_name()
        else:
            return
        if not self.series:
            self.uc.bar_warn("No data series for this type of outflow.")
            return
        self.outflow_data_cbo.clear()
        self.outflow_data_cbo.setEnabled(True)
        self.outflow_data_label.setDisabled(False)
        self.delete_outflow_ts_btn.setDisabled(False)
        cur_idx = 0
        for i, row in enumerate(self.series):
            row = [x if x is not None else "" for x in row]
            s_fid, name = row
            if not name:
                name = self.outflow.get_new_data_name(s_fid)
            self.outflow_data_cbo.addItem(name, s_fid)
            if s_fid == self.outflow.get_cur_data_fid():
                cur_idx = i
        data_fid = self.outflow_data_cbo.itemData(cur_idx)
        self.outflow.set_new_data_fid(data_fid)
        self.outflow_data_cbo.setCurrentIndex(cur_idx)
        self.outflow_data_changed()

    def outflow_data_changed(self):
        self.bc_type = "outflow"
        self.outflow.get_cur_data_fid()
        out_nr = self.outflow_data_cbo.count()
        if not out_nr:
            return
        data_idx = self.outflow_data_cbo.currentIndex()
        data_fid = self.outflow_data_cbo.itemData(data_idx)
        self.outflow.set_new_data_fid(data_fid)
        self.create_outflow_plot()
        self.bc_tview.undoStack.clear()
        self.bc_tview.setModel(self.bc_data_model)
        head = self.outflow_tab_head
        series_data = self.outflow.get_data()
        self.d1, self.d2 = [[], []]
        self.bc_data_model.clear()
        self.bc_data_model.setHorizontalHeaderLabels(head)
        for row in series_data:
            items = [StandardItem(str(x)) if x is not None else StandardItem("") for x in row]
            self.d1.append(row[0] if not row[0] is None else float("NaN"))
            self.d2.append(row[1] if not row[1] is None else float("NaN"))
            self.bc_data_model.appendRow(items)
        rc = self.bc_data_model.rowCount()
        if rc < 500:
            for row in range(rc, 500 + 1):
                items = [StandardItem(x) for x in ("",) * self.bc_data_model.columnCount()]
                self.bc_data_model.appendRow(items)
        self.bc_tview.setEnabled(True)
        cols = len(head)
        for col in range(cols):
            self.bc_tview.setColumnWidth(col, int(230 / cols))
        self.bc_tview.horizontalHeader().setStretchLastSection(True)
        for i in range(self.bc_data_model.rowCount()):
            self.bc_tview.setRowHeight(i, 20)
        self.outflow.set_row()
        self.update_outflow_plot()

    def update_outflow_plot(self):
        """
        When time series data for plot change, update the plot.
        """
        if not self.plot_item_name:
            return
        self.d1, self.d2 = [[], []]
        for i in range(self.bc_data_model.rowCount()):
            self.d1.append(m_fdata(self.bc_data_model, i, 0))
            self.d2.append(m_fdata(self.bc_data_model, i, 1))
        self.plot.update_item(self.plot_item_name, [self.d1, self.d2])
        self.plot.auto_range()

    def populate_outflow_type_cbo(self):
        """
        Populate outflow types cbo and set current type.
        """
        self.outflow_type_cbo.clear()
        type_name = "{}. {}"
        for typnr in sorted(self.outflow_types.keys()):
            outflow_type = type_name.format(typnr, self.outflow_types[typnr]["name"]).strip()
            self.outflow_type_cbo.addItem(outflow_type, typnr)

    def populate_hydrograph_cbo(self):
        self.outflow_hydro_cbo.clear()
        self.outflow_hydro_cbo.addItem("", 0)
        for i in range(1, 10):
            h_name = "O{}".format(i)
            self.outflow_hydro_cbo.addItem(h_name, i)

    def outflow_hydrograph_changed(self):
        self.bc_type = "outflow"
        self.outflow.hydro_out = self.outflow_hydro_cbo.currentIndex()
        self.outflow.set_row()

    def create_outflow_plot(self):
        """
        Create initial plot for the current outflow type.
        """
        self.plot.clear()
        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)
        self.plot.plot.addLegend()

        self.plot_item_name = None
        if self.outflow.typ in [5, 6, 7, 8]:
            self.plot_item_name = "Time"
        elif self.outflow.typ == 9:
            self.plot_item_name = "Q(h) parameters"
        elif self.outflow.typ == 10:
            self.plot_item_name = "Q(h) table"
        else:
            pass
        self.plot.add_item(self.plot_item_name, [self.d1, self.d2], col=QColor("#0018d4"))

    def no_bc_disable(self, type):
        """
        Disable elements when there is no BC
        """
        self.bc_type = type
        if type == "inflow":
            self.inflow_name_label.setDisabled(True)
            self.inflow_bc_name_cbo.setDisabled(True)
            self.change_inflow_bc_name_btn.setDisabled(True)
            self.delete_inflow_bc_btn.setDisabled(True)
            self.inflow_bc_center_btn.setDisabled(True)
            self.inflow_type_label.setDisabled(True)
            self.inflow_type_cbo.setDisabled(True)
            self.ifc_fplain_radio.setDisabled(True)
            self.ifc_chan_radio.setDisabled(True)
            self.inflow_tseries_label.setDisabled(True)
            self.inflow_tseries_cbo.setDisabled(True)
            self.add_inflow_data_btn.setDisabled(True)
            self.change_inflow_data_name_btn.setDisabled(True)
            self.delete_inflow_ts_btn.setDisabled(True)
            self.inflow_interval_ckbx.setDisabled(True)
            self.schematize_inflow_label.setDisabled(True)
            self.schem_inflow_bc_btn.setDisabled(True)
        if type == "outflow":
            self.outflow_name_label.setDisabled(True)
            self.outflow_bc_name_cbo.setDisabled(True)
            self.change_outflow_bc_name_btn.setDisabled(True)
            self.delete_outflow_bc_btn.setDisabled(True)
            self.outflow_bc_center_btn.setDisabled(True)
            self.outflow_type_label.setDisabled(True)
            self.outflow_type_cbo.setDisabled(True)
            self.outflow_hydro_label.setDisabled(True)
            self.outflow_hydro_cbo.setDisabled(True)
            self.outflow_data_label.setDisabled(True)
            self.outflow_data_cbo.setDisabled(True)
            self.add_outflow_data_btn.setDisabled(True)
            self.change_outflow_data_name_btn.setDisabled(True)
            self.delete_outflow_ts_btn.setDisabled(True)
            self.schematize_outflow_label.setDisabled(True)
            self.schem_outflow_bc_btn.setDisabled(True)

    def disable_outflow_types(self):
        for idx in [2, 3, 6, 8, 9, 10]:
            self.outflow_type_cbo.model().item(idx).setEnabled(False)

    def delete_all_inflow_data(self):
        """
        Function to delete all inflow data in the geopackage
        """
        sql_commands = [
            "DELETE FROM user_bc_points",
            "DELETE FROM user_bc_lines",
            "DELETE FROM user_bc_polygons",
            "DELETE FROM all_schem_bc",
            "DELETE FROM inflow",
            "DELETE FROM inflow_cells",
            "DELETE FROM inflow_time_series",
            "DELETE FROM inflow_time_series_data",
        ]

        for sql in sql_commands:
            self.gutils.execute(sql)

    def itemDataChangedSlot(self, item, oldValue, newValue, role, save=True):
        """
        Slot used to push changes of existing items onto undoStack.
        """
        if role == Qt.EditRole:
            command = CommandItemEdit(
                self,
                item,
                oldValue,
                newValue,
                "Text changed from '{0}' to '{1}'".format(oldValue, newValue),
            )
            self.bc_tview.undoStack.push(command)
            return True

    def create_plot(self):
        """
        Create initial plot.
        """
        if self.bc_type == "inflow":
            self.create_inflow_plot()
        if self.bc_type == "outflow":
            self.create_outflow_plot()

    def update_plot(self):
        """
        When data model data change, update the plot.
        """
        if self.bc_type == "inflow":
            self.update_inflow_plot()
        if self.bc_type == "outflow":
            self.update_outflow_plot()

    def save_bc_data(self):
        """
        Save the boundary condition data.
        """
        self.update_plot()

        if self.bc_type == "inflow":
            self.save_inflow_data()

        if self.bc_type == "outflow":
            self.save_outflow_data()

    def cancel_bc_lyrs_edits(self, type):
        """
        Function to rollback
        """
        # if user bc layers are edited
        if not self.gutils:
            return
        self.bc_type = type
        user_bc_edited = self.lyrs.rollback_lyrs_edits(*self.user_bc_tables)
        if user_bc_edited:
            self.populate_bcs()
        if type == "inflow":
            self.create_inflow_point_bc_btn.setChecked(False)
            self.create_inflow_line_bc_btn.setChecked(False)
            try:
                self.populate_bcs(self.inflow.fid)
            except AttributeError:
                self.populate_bcs()
        if type == "outflow":
            self.create_outflow_point_bc_btn.setChecked(False)
            self.create_outflow_line_bc_btn.setChecked(False)
            self.create_outflow_polygon_bc_btn.setChecked(False)
            try:
                self.populate_bcs(self.outflow.fid)
            except AttributeError:
                self.populate_bcs()

        self.uc.bar_info("Boundary Conditions edits rolled back!")
        self.uc.log_info("Boundary Conditions edits rolled back!")

    def delete_schematized_data(self, type):
        """
        Function to delete the schematized data
        """
        exist_user_bc = self.gutils.execute(f"SELECT * FROM all_schem_bc WHERE type = '{type}';").fetchone()
        if not exist_user_bc:
            self.uc.bar_info(f"There are no schematized {type} Boundary Conditions.")
            self.uc.log_info(f"There are no schematized {type} Boundary Conditions.")
            return

        msg = f"Are you sure? This will delete all {type} schematized data."
        if not self.uc.question(msg):
            return
        else:
            self.bc_type = type
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                if type == "inflow":
                    self.gutils.execute(f"DELETE FROM all_schem_bc WHERE type = 'inflow'")
                    self.gutils.execute(f"DELETE FROM inflow_cells")

                if type == "outflow":
                    self.gutils.execute(f"DELETE FROM all_schem_bc WHERE type = 'outflow'")
                    self.gutils.execute(f"DELETE FROM outflow_cells")

            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error(
                    "ERROR:"
                    + "\n__________________________________________________",
                    e,
                )

            schem_bc = self.lyrs.data['all_schem_bc']["qlyr"]
            schem_bc.triggerRepaint()
            QApplication.restoreOverrideCursor()
            self.uc.bar_info(f"Schematized {type} deleted.")
            self.uc.log_info(f"Schematized {type} deleted.")

    def create_all_border_outflow_bc(self):
        """
        Function to create outflow bc into the whole outside grid cells
        """
        self.gutils.enable_geom_triggers()

        msg = "This boundary method applies a normal depth boundary to every grid element on the outer edge " \
              "of the computational domain. Please review the grid element elevation modification that happens " \
              "when this method applied. \n\n" \
              "Would you like to proceed?"
        if not self.uc.question(msg):
            return

        self.bc_type = "outflow"
        QApplication.setOverrideCursor(Qt.WaitCursor)

        try:
            grid = self.lyrs.data["grid"]["qlyr"]

            dissolved_grid = processing.run("native:dissolve",
                                            {'INPUT': grid,
                                             'FIELD': [],
                                             'SEPARATE_DISJOINT': False,
                                             'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

            cell_size = float(self.gutils.get_cont_par("CELLSIZE"))
            buffer = processing.run("native:buffer",
                                    {'INPUT': dissolved_grid,
                                     'DISTANCE': (-cell_size / 2),
                                     'SEGMENTS': 1,
                                     'END_CAP_STYLE': 0,
                                     'JOIN_STYLE': 0,
                                     'MITER_LIMIT': 2,
                                     'DISSOLVE': False,
                                     'SEPARATE_DISJOINT': False,
                                     'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

            lines = processing.run("native:polygonstolines", {
                'INPUT': buffer,
                'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

            user_bc_lines = self.lyrs.data["user_bc_lines"]["qlyr"]
            features = []
            for feature in lines.getFeatures():
                temp_feature = QgsFeature()
                temp_feature.setFields(user_bc_lines.fields())
                temp_feature['type'] = 'outflow'
                temp_feature.setGeometry(feature.geometry())
                features.append(temp_feature)
            user_bc_lines.startEditing()
            data_provider = user_bc_lines.dataProvider()
            data_provider.addFeatures(features)
            user_bc_lines.commitChanges()

            idx = self.gutils.execute(
                """SELECT MAX(fid) FROM user_bc_lines WHERE type = 'outflow';""").fetchone()[0]

            self.gutils.execute(
                f"UPDATE outflow SET name = 'Whole Boundary Cells' WHERE geom_type = 'line' AND bc_fid = {idx};")

            self.populate_outflows()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR:"
                + "\n__________________________________________________",
                e,
            )

        QApplication.restoreOverrideCursor()

    def save_outflow_data(self):
        data = []
        for i in range(self.bc_data_model.rowCount()):
            # save only rows with a number in the first column
            if is_number(m_fdata(self.bc_data_model, i, 0)) and not isnan(m_fdata(self.bc_data_model, i, 0)):
                data.append([m_fdata(self.bc_data_model, i, j) for j in range(self.bc_data_model.columnCount())])
            else:
                pass
        data_name = self.outflow_data_cbo.currentText()
        typ_idx = self.outflow_type_cbo.currentIndex()
        if typ_idx in [5,6,7,8]:
            self.outflow.set_time_series_data(data_name, data)
        elif typ_idx in [9]:
            self.outflow.set_qh_params_data(data_name, data)
        elif typ_idx in [10]:
            self.outflow.set_qh_table_data(data_name, data)
        else:
            pass

        self.update_outflow_plot()

