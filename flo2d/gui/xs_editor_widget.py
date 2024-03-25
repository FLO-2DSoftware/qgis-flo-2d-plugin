# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import shutil
import subprocess
import processing
import sys
import traceback
from collections import OrderedDict
from math import isnan

from PyQt5.QtWidgets import QProgressDialog
from qgis._core import QgsMessageLog, QgsProcessingFeatureSourceDefinition, QgsUnitTypes
from qgis._gui import QgsDockWidget
from qgis.core import (
    NULL,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsMapLayerProxyModel,
    QgsPointXY,
    QgsProject,
    QgsWkbTypes,
)
from qgis.gui import QgsMapLayerComboBox
from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtGui import QColor, QStandardItem
from qgis.PyQt.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QStyledItemDelegate,
    QTableWidgetItem,
)

from .dlg_channel_check_report import ChannelCheckReportDialog
from ..flo2d_ie.flo2d_parser import ParseDAT
from ..flo2d_ie.flo2dgeopackage import Flo2dGeoPackage
from ..flo2d_tools.flopro_tools import (
    ChannelNInterpolatorExecutor,
    ChanRightBankExecutor,
    XSECInterpolatorExecutor,
)
from ..flo2d_tools.grid_tools import adjacent_grids
from ..flo2d_tools.schematic_tools import ChannelsSchematizer, Confluences
from ..flo2dobjects import ChannelSegment, UserCrossSection
from ..geopackage_utils import GeoPackageUtils
from ..gui.dlg_flopro import ExternalProgramFLO2D
from ..gui.dlg_tributaries import TributariesDialog
from ..gui.dlg_xsec_interpolation import XSecInterpolationDialog
from ..user_communication import UserCommunication
from ..utils import is_number, m_fdata
from .plot_widget import PlotWidget
from .table_editor_widget import CommandItemEdit, StandardItem, StandardItemModel
from .ui_utils import (
    center_canvas,
    load_ui,
    set_icon,
    switch_to_selected,
    try_disconnect,
)

# uiDialog, qtBaseClass = load_ui("schematized_channels_info")
#
#
# class ShematizedChannelsInfo(qtBaseClass, uiDialog):
#     def __init__(self, iface):
#         qtBaseClass.__init__(self)
#         uiDialog.__init__(self)
#         self.iface = iface
#         self.uc = UserCommunication(iface, "FLO-2D")
#         self.setupUi(self)
#         self.con = self.iface.f2d["con"]
#         self.gutils = GeoPackageUtils(self.con, self.iface)
#         self.schematized_summary_tblw.horizontalHeader().setStretchLastSection(True)
#         self.populate_schematized_dialog()
#
#     def populate_schematized_dialog(self):
#         try:
#             qry_chan_names = """SELECT name FROM user_left_bank"""
#             chan_names = self.gutils.execute(qry_chan_names).fetchall()
#
#             qry_count_xs = """SELECT COUNT(seg_fid) FROM chan_elems GROUP BY seg_fid;"""
#             total_xs = self.gutils.execute(qry_count_xs).fetchall()
#
#             qry_interpolated = """SELECT COUNT(interpolated) FROM chan_elems WHERE interpolated = 1 GROUP BY seg_fid;"""
#             interpolated_xs = self.gutils.execute(qry_interpolated).fetchall()
#
#             self.schematized_summary_tblw.setRowCount(0)
#             for row_number, name in enumerate(chan_names):
#                 self.schematized_summary_tblw.insertRow(row_number)
#                 item = QTableWidgetItem()
#                 if interpolated_xs:
#                     if row_number <= len(interpolated_xs) - 1:
#                         n_interpolated_xs = interpolated_xs[row_number][0]
#                     else:
#                         n_interpolated_xs = 0
#                 else:
#                     n_interpolated_xs = 0
#                 #                 n_interpolated_xs = interpolated_xs[row_number][0] if interpolated_xs else 0
#                 original_xs = total_xs[row_number][0] - n_interpolated_xs
#                 item.setData(Qt.DisplayRole, name[0] + " (" + str(original_xs) + " xsecs)")
#                 self.schematized_summary_tblw.setItem(row_number, 0, item)
#                 item = QTableWidgetItem()
#                 item.setData(Qt.DisplayRole, total_xs[row_number][0])
#                 self.schematized_summary_tblw.setItem(row_number, 1, item)
#                 item = QTableWidgetItem()
#                 item.setData(
#                     Qt.DisplayRole,
#                     str(total_xs[row_number][0]) + " (" + str(n_interpolated_xs) + " interpolated)",
#                 )
#                 self.schematized_summary_tblw.setItem(row_number, 2, item)
#         except Exception as e:
#             QApplication.restoreOverrideCursor()
#             self.uc.show_error("ERROR 130718.0831: schematized dialog failed to show!", e)
#             return


uiDialog, qtBaseClass = load_ui("xs_editor")

ChannelRole = Qt.UserRole + 1


class CrossSectionDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super(CrossSectionDelegate, self).initStyleOption(option, index)
        a = index.data(ChannelRole)
        if index.data(ChannelRole):
            option.font.setBold(True)
            option.font.setItalic(True)


class XsecEditorWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.f2g = None
        self.chan_seg = None
        self.iface = iface
        self.plot = plot
        self.xs_table = table
        self.tview = table.tview
        self.lyrs = lyrs
        self.con = None
        self.gutils = None

        self.system_units = {
            "CMS": ["m", "mps", "cms", "sq. m", "Pa"],
            "CFS": ["ft", "fps", "cfs", "sq. ft", "lb/sq. ft"]
        }

        self.user_xs_lyr = None
        self.xs = None
        self.cur_xs_fid = None
        self.project_dir = ""
        self.exe_dir = ""
        self.uc = UserCommunication(iface, "FLO-2D")

        self.parser = ParseDAT()

        self.setupUi(self)
        delegate = CrossSectionDelegate(self.xs_cbo)
        self.xs_cbo.setItemDelegate(delegate)
        self.populate_xsec_type_cbo()
        self.xi, self.yi = [[], []]
        #         self.create_plot()
        self.xs_data_model = StandardItemModel()
        self.tview.setModel(self.xs_data_model)
        # Connections:

        # Buttons connections:
        self.digitize_btn.clicked.connect(self.digitize_xsec)
        self.save_xs_changes_btn.clicked.connect(self.save_user_xsections_lyr_edits)
        self.revert_changes_btn.clicked.connect(self.cancel_user_lyr_edits)
        self.delete_btn.clicked.connect(self.delete_xs)
        self.delete_user_btn.clicked.connect(self.delete_user_data)
        self.delete_schema_btn.clicked.connect(self.delete_schematize_data)
        self.schematize_xs_btn.clicked.connect(self.schematize_channels)
        self.check_schematized_channel_btn.clicked.connect(self.check_schematized_channel)
        self.interpolate_channel_elevation_btn.clicked.connect(self.interpolate_channel_elevation)
        self.confluences_btn.clicked.connect(self.create_confluences)
        self.delete_confluences_btn.clicked.connect(self.delete_confluences)
        self.interpolate_channel_n_btn.clicked.connect(self.interpolate_channel_n)
        self.rename_xs_btn.clicked.connect(self.change_xs_name)
        self.sample_elevation_current_natural_btn.clicked.connect(self.sample_elevation_current_natural_cross_sections)
        self.sample_elevation_all_natural_btn.clicked.connect(self.sample_elevation_all_natural_cross_sections)
        self.sample_elevation_current_R_T_V_btn.clicked.connect(self.sample_bank_elevation_current_RTV_cross_sections)
        self.sample_elevation_all_R_T_V_btn.clicked.connect(self.sample_bank_elevation_all_RTV_cross_sections)

        # More connections:
        self.xs_cbo.activated.connect(self.current_cbo_xsec_index_changed)
        self.xs_type_cbo.activated.connect(self.cur_xsec_type_changed)
        self.n_sbox.valueChanged.connect(self.save_n)
        self.xs_data_model.dataChanged.connect(self.save_xs_data)
        self.xs_table.before_paste.connect(self.block_saving)
        self.xs_table.after_paste.connect(self.unblock_saving)
        self.xs_table.after_delete.connect(self.save_xs_data)

        self.raster_combobox = QgsMapLayerComboBox()
        self.raster_combobox.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.raster_combobox.setEnabled(self.raster_radio_btn.isChecked())
        self.source_raster_layout.addWidget(self.raster_combobox)
        self.raster_radio_btn.toggled.connect(self.raster_combobox.setEnabled)
        self.raster_radio_btn.toggled.connect(self.update_sample_elevation_btn)
        self.update_sample_elevation_btn(self.raster_radio_btn.isChecked())

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
            self.user_xs_lyr = self.lyrs.data["user_xsections"]["qlyr"]
            self.user_xs_lyr.editingStopped.connect(self.populate_xsec_cbo)
            self.user_xs_lyr.selectionChanged.connect(self.switch2selected)

    def update_sample_elevation_btn(self, is_checked):
        if self.xs is not None:
            row = self.xs.get_row()
            chan_x_row = self.xs.get_chan_x_row()
            typ = row["type"]
            self.sample_elevation_current_natural_btn.setEnabled(is_checked and typ == "N")
        self.sample_elevation_all_natural_btn.setEnabled(is_checked)

    def block_saving(self):
        try_disconnect(self.xs_data_model.dataChanged, self.save_xs_data)

    def unblock_saving(self):
        self.xs_data_model.dataChanged.connect(self.save_xs_data)

    def switch2selected(self):
        switch_to_selected(self.user_xs_lyr, self.xs_cbo, use_fid=True)
        current_fid = self.xs_cbo.currentData()
        self.current_xsec_changed(current_fid)

    def interp_bed_and_banks(self):
        qry = "SELECT fid FROM chan;"
        fids = self.gutils.execute(qry).fetchall()
        for fid in fids:
            seg = ChannelSegment(int(fid[0]), self.con, self.iface)
            res, msg = seg.interpolate_bed()
            if not res:
                self.uc.log_info(msg)
                self.uc.show_warn("WARNING 060319.1740: " + msg)
                return False
        return True

    def populate_xsec_type_cbo(self):
        """
        Get current xsection data, populate all relevant fields of the dialog and create xsection plot.
        """
        self.xs_type_cbo.clear()
        self.xs_types = OrderedDict()

        self.xs_types["R"] = {"name": "Rectangular", "cbo_idx": 0}
        self.xs_types["N"] = {"name": "Natural", "cbo_idx": 1}
        self.xs_types["T"] = {"name": "Trapezoidal", "cbo_idx": 2}
        self.xs_types["V"] = {"name": "Variable Area", "cbo_idx": 3}
        for typ, data in self.xs_types.items():
            self.xs_type_cbo.addItem(data["name"], typ)

    def setup_plot(self):
        self.plotWidget = PlotWidget()
        self.plotLayout.addWidget(self.plotWidget)

    def populate_xsec_cbo(self, fid=None, show_last_edited=False):
        """
        Populate xsection combo.
        """
        self.xs_cbo.clear()
        self.xs_type_cbo.setCurrentIndex(1)
        qry = "SELECT fid, name FROM user_xsections ORDER BY fid COLLATE NOCASE;"
        user_xs_rows = self.gutils.execute(qry).fetchall()

        if not user_xs_rows:
            self.xs_data_model.clear()
            self.tview.setModel(self.xs_data_model)
            self.plot.clear()
            return

        qry = "SELECT seg_fid, nr_in_seg, user_xs_fid FROM chan_elems WHERE interpolated = 0;"
        schematized_cross_section = self.gutils.execute(qry).fetchall()
        schematized_channel_dict = dict()
        user_xs_dict = dict()
        # Construct channel dict
        for i, row in enumerate(schematized_cross_section):
            row = [x if x is not None else "" for x in row]
            seg_fid, nr_in_seg, user_xs_fid = row
            user_xs_dict[user_xs_fid] = seg_fid
            if seg_fid in schematized_channel_dict:
                schematized_channel_dict[seg_fid].append((user_xs_fid, nr_in_seg))
            else:
                schematized_channel_dict[seg_fid] = [(user_xs_fid, nr_in_seg)]

        # Order the cross section in each channel
        for channel, lst in schematized_channel_dict.items():
            schematized_channel_dict[channel] = sorted(lst, key=lambda tup: tup[1])

        qry = "SELECT fid, name FROM user_left_bank;"
        channel_names = self.gutils.execute(qry).fetchall()
        channel_names_dict = dict()
        for i, row in enumerate(channel_names):
            row = [x if x is not None else "" for x in row]
            seg_fid, name = row
            channel_names_dict[seg_fid] = name

        # search for not schematized cross section and construct name cross section dict
        non_schematized_xs = []
        xs_name_dict = dict()
        for i, row in enumerate(user_xs_rows):
            row = [x if x is not None else "" for x in row]
            row_fid, name = row
            if row_fid not in user_xs_dict:
                non_schematized_xs.append(row_fid)
            xs_name_dict[row_fid] = name

        if len(non_schematized_xs) > 0 or len(schematized_channel_dict) > 0:
            cur_idx = 1  # Pointer to selected item in combo. See below. Depending on call of method,
            # it could be the first, the last, or a given one.
        else:
            cur_idx = 0

        # ... and populate combo box, start with non schematized cross section
        if len(non_schematized_xs) > 0:
            self.xs_cbo.addItem("Non Schematized")
            row_index = self.xs_cbo.model().rowCount() - 1
            flags = self.xs_cbo.model().item(row_index).flags()
            self.xs_cbo.model().item(row_index).setFlags(flags & ~Qt.ItemIsSelectable)
            self.xs_cbo.model().item(row_index).setData(True, ChannelRole)
            for xs_fid in non_schematized_xs:
                name = xs_name_dict[xs_fid]
                self.xs_cbo.addItem(name, str(xs_fid))
                row_index = self.xs_cbo.model().rowCount() - 1
                self.xs_cbo.model().item(row_index).setData(False, ChannelRole)

                if fid:
                    if xs_fid == int(fid):
                        cur_idx = row_index

        for channel, cross_sections in schematized_channel_dict.items():
            channel_name = channel_names_dict[channel]
            self.xs_cbo.addItem(channel_name)
            row_index = self.xs_cbo.model().rowCount() - 1
            flags = self.xs_cbo.model().item(row_index).flags()
            self.xs_cbo.model().item(row_index).setFlags(flags & ~Qt.ItemIsSelectable)
            self.xs_cbo.model().item(row_index).setData(True, ChannelRole)
            for tup in cross_sections:
                xs_fid = tup[0]
                if xs_fid in xs_name_dict:
                    name = xs_name_dict[xs_fid]
                else:
                    continue
                self.xs_cbo.addItem(name, str(xs_fid))
                row_index = self.xs_cbo.model().rowCount() - 1
                self.xs_cbo.model().item(row_index).setData(False, ChannelRole)

                if fid:
                    if xs_fid == int(fid):
                        cur_idx = row_index

        if show_last_edited:
            cur_idx = i

        self.xs_cbo.setCurrentIndex(cur_idx)
        self.enable_widgets(False)
        if self.xs_cbo.count():
            self.enable_widgets()
            self.current_xsec_changed(self.xs_cbo.currentData())

    def digitize_xsec(self, i):
        def_attr_exp = self.lyrs.data["user_xsections"]["attrs_defaults"]
        if not self.lyrs.enter_edit_mode("user_xsections", def_attr_exp):
            return
        self.enable_widgets(False)

    def enable_widgets(self, enable=True):
        self.xs_cbo.setEnabled(enable)
        self.rename_xs_btn.setEnabled(enable)
        self.xs_type_cbo.setEnabled(enable)
        self.xs_center_btn.setEnabled(enable)
        self.n_sbox.setEnabled(enable)

    def cancel_user_lyr_edits(self, i):
        user_lyr_edited = self.lyrs.rollback_lyrs_edits("user_xsections")
        if user_lyr_edited:
            self.populate_xsec_cbo()

    def save_user_xsections_lyr_edits(self, i):
        if not self.gutils or not self.lyrs.any_lyr_in_edit("user_xsections"):
            return
        # try to save user bc layers (geometry additions/changes)
        user_lyr_edited = self.lyrs.save_lyrs_edits(
            "user_xsections"
        )  # Saves all user cross sections created in this opportunity into 'user_xsections'.
        # if user bc layers were edited
        # self.enable_widgets()
        if user_lyr_edited:
            self.gutils.fill_empty_user_xsec_names()  # Sometimes (to be determined) the 'name' column of 'user_xsections' is not assigned. This does.
            self.gutils.set_def_n()  # Assigns the default manning (from global MANNING) or 0.035 (at the time of writing this comment)
            self.populate_xsec_cbo(show_last_edited=True)
            # for i in range(self.xs_cbo.count()):
            #     self.current_xsec_changed(i)

    def repaint_xs(self):
        self.lyrs.lyrs_to_repaint = [self.lyrs.data["user_xsections"]["qlyr"]]
        self.lyrs.repaint_layers()

    def current_cbo_xsec_index_changed(self, idx=0):
        if not self.xs_cbo.count():
            return
        fid = self.xs_cbo.currentData()
        if fid is None:
            fid = -1

        self.xs_table.after_delete.disconnect()
        self.xs_table.after_delete.connect(self.save_xs_data)

        self.current_xsec_changed(fid)

    def current_xsec_changed(self, fid=-1):
        """
        User changed current xsection in the xsections list.
        Populate xsection data fields and update the plot.
        """
        if not self.xs_cbo.count():
            return

        if fid is None or fid == -1:
            fid = self.xs_cbo.itemData(0)

        channel_names = self.gutils.execute("SELECT name FROM user_left_bank").fetchall()
        channel_names_list = [item[0] for item in channel_names]

        if self.xs_cbo.currentText() in channel_names_list or self.xs_cbo.currentText() == "Non Schematized":
            return

        self.xs = UserCrossSection(fid, self.con, self.iface)
        row = self.xs.get_row()
        self.lyrs.clear_rubber()
        if self.xs_center_btn.isChecked():
            self.lyrs.show_feat_rubber(self.user_xs_lyr.id(), int(fid))
            feat = next(self.user_xs_lyr.getFeatures(QgsFeatureRequest(int(self.xs.fid))))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
        typ = row["type"]
        fcn = float(row["fcn"]) if is_number(row["fcn"]) else float(self.gutils.get_cont_par("MANNING"))
        self.xs_type_cbo.setCurrentIndex(self.xs_types[typ]["cbo_idx"])
        self.n_sbox.setValue(fcn)

        self.update_table()
        self.create_plot()
        self.update_plot()

        self.sample_elevation_current_R_T_V_btn.setEnabled(typ == "R" or typ == "T" or typ == "V")
        self.sample_elevation_current_natural_btn.setEnabled(typ == "N" and self.raster_radio_btn.isChecked())

    def update_table(self):
        row = self.xs.get_row()
        chan_x_row = self.xs.get_chan_x_row()
        typ = row["type"]
        if typ == "N":
            xy = self.xs.get_chan_natural_data()
            self.xs_table.connect_delete(True)
        else:
            xy = None
            self.xs_table.connect_delete(False)  # disable data or row delete function if table editor
        self.xs_data_model.clear()
        self.tview.undoStack.clear()

        if not xy:
            self.plot.clear()
            self.xs_data_model.setHorizontalHeaderLabels(["Value"])
            for val in chan_x_row.values():
                item = StandardItem(str(val))
                self.xs_data_model.appendRow(item)
            self.xs_data_model.setVerticalHeaderLabels(list(chan_x_row.keys()))
            self.xs_data_model.removeRows(0, 2)  # excluding fid and user_xs_fid values
            self.tview.setModel(self.xs_data_model)
        else:
            self.xs_data_model.setHorizontalHeaderLabels(["Station", "Elevation"])
            for i, pt in enumerate(xy):
                x, y = pt
                xi = StandardItem(str(x))
                yi = StandardItem(str(y))
                self.xs_data_model.appendRow([xi, yi])
            self.tview.setModel(self.xs_data_model)
            rc = self.xs_data_model.rowCount()
            if rc < 500:
                for row in range(rc, 500 + 1):
                    items = [StandardItem(x) for x in ("",) * 2]
                    self.xs_data_model.appendRow(items)
        for i in range(self.xs_data_model.rowCount()):
            self.tview.setRowHeight(i, 20)
        self.tview.horizontalHeader().setStretchLastSection(True)
        for i in range(2):
            self.tview.setColumnWidth(i, 100)

    def cur_xsec_type_changed(self, idx):
        if not self.xs_cbo.count():
            return
        typ = self.xs_type_cbo.itemData(idx)
        self.xs.set_type(typ)
        xs_cbo_fid = self.xs_cbo.currentData()
        self.current_xsec_changed(xs_cbo_fid)

    def create_plot(self):
        """
        Create initial plot.
        """
        self.plot.clear()
        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)
        self.plot.plot.addLegend()

        self.plot.add_item("Cross-section", [[], []], col=QColor("#0018d4"))
        self.plot.plot.setTitle(title="Cross Section - {}".format(self.xs_cbo.currentText()))
        self.plot.plot.setLabel("bottom", text="Station")
        self.plot.plot.setLabel("left", text="Elevation")

    def update_plot(self):
        """
        When time series data for plot change, update the plot.
        """
        xs_type = self.xs_type_cbo.currentText()
        if xs_type == "Natural":
            self._create_natural_xy()
        elif xs_type == "Rectangular":
            self._create_rectangular_xy()
        elif xs_type == "Trapezoidal":
            self._create_trapezoidal_xy()
        self.plot.update_item("Cross-section", [self.xi, self.yi])

    def _create_rectangular_xy(self):
        data = []
        for i in range(self.xs_data_model.rowCount()):
            data.append(m_fdata(self.xs_data_model, i, 0))
        bankell, bankelr, fcw, fcd = data
        x0, y0 = [0, bankell]
        x1, y1 = [0, min(bankell - fcd, bankelr - fcd)]
        x2, y2 = [fcw, min(bankell - fcd, bankelr - fcd)]
        x3, y3 = [fcw, bankelr]
        self.xi = [x0, x1, x2, x3]
        self.yi = [y0, y1, y2, y3]

    def _create_trapezoidal_xy(self):
        data = []
        for i in range(self.xs_data_model.rowCount()):
            data.append(m_fdata(self.xs_data_model, i, 0))
        bankell, bankelr, fcw, fcd, zl, zr = data
        x0, y0 = [0, bankell]
        x1, y1 = [x0 + zl * fcd, min(bankell - fcd, bankelr - fcd)]
        x2, y2 = [x1 + fcw, min(bankell - fcd, bankelr - fcd)]
        x3, y3 = [x2 + ((bankelr - bankell + fcd) * zr * 1.0), bankelr]
        self.xi = [x0, x1, x2, x3]
        self.yi = [y0, y1, y2, y3]

    # def _create_rectangular_xy(self):
    # data = []
    # for i in range(self.xs_data_model.rowCount()):
    # data.append(m_fdata(self.xs_data_model, i, 0))
    # bankell, bankelr, fcw, fcd = data
    # x0, y0 = [0, bankell]
    # x1, y1 = [0, bankell - fcd]
    # x2, y2 = [fcw, bankell - fcd]
    # x3, y3 = [fcw, bankelr]
    # self.xi = [x0, x1, x2, x3]
    # self.yi = [y0, y1, y2, y3]
    #
    # def _create_trapezoidal_xy(self):
    # data = []
    # for i in range(self.xs_data_model.rowCount()):
    # data.append(m_fdata(self.xs_data_model, i, 0))
    # bankell, bankelr, fcw, fcd, zl, zr = data
    # x0, y0 = [0, bankell]
    # x1, y1 = [x0 + zl * fcd, bankell - fcd]
    # x2, y2 = [x1 + fcw, bankell - fcd]
    # x3, y3 = [x2 + ((bankelr - bankell + fcd) * zr * 1.0), bankelr]
    # self.xi = [x0, x1, x2, x3]
    # self.yi = [y0, y1, y2, y3]

    def _create_natural_xy(self):
        self.xi, self.yi = [[], []]
        for i in range(self.xs_data_model.rowCount()):
            x = m_fdata(self.xs_data_model, i, 0)
            y = m_fdata(self.xs_data_model, i, 1)
            if not isnan(x) and not isnan(y):
                self.xi.append(x)
                self.yi.append(y)

    def save_n(self, n_val):
        if not self.xs_cbo.count():
            return
        self.xs.set_n(n_val)

    def change_xs_name(self, i):
        if not self.xs_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, "Change name", "New name:")
        if not ok or not new_name:
            return
        if not self.xs_cbo.findText(new_name) == -1:
            msg = "WARNING 060319.1741: Boundary condition with name {} already exists in the database. Please, choose another name.".format(
                new_name
            )
            self.uc.show_warn(msg)
            return
        self.xs.name = new_name
        self.xs.set_name()
        self.populate_xsec_cbo(fid=self.xs.fid)

    def save_xs_data(self):
        if self.xs.type == "N":
            xiyi = []
            for i in range(self.xs_data_model.rowCount()):
                # save only rows with a number in the first column
                if is_number(m_fdata(self.xs_data_model, i, 0)) and not isnan(m_fdata(self.xs_data_model, i, 0)):
                    xiyi.append(
                        (
                            self.xs.fid,
                            m_fdata(self.xs_data_model, i, 0),
                            m_fdata(self.xs_data_model, i, 1),
                        )
                    )
            self.xs.set_chan_natural_data(xiyi)
            self.update_plot()
        else:
            # parametric xsection
            data = []
            for i in range(self.xs_data_model.rowCount()):
                data.append((m_fdata(self.xs_data_model, i, 0)))
            self.xs.set_chan_data(data)
            self.update_plot()

    def delete_xs(self, i):
        """
        Delete the current cross-section from user layer.
        """
        if not self.xs_cbo.count():
            return
        q = "Are you sure, you want to delete current cross-section?"
        if not self.uc.question(q):
            return
        fid = None
        xs_idx = self.xs_cbo.currentIndex()
        cur_data = self.xs_cbo.itemData(xs_idx)
        if cur_data:
            fid = int(cur_data)
        else:
            return
        qry = """DELETE FROM user_xsections WHERE fid = ?;"""
        self.gutils.execute(qry, (fid,))

        # try to set current xs to the last before the deleted one
        try:
            self.populate_xsec_cbo(fid=fid - 1)
        except Exception as e:
            self.populate_xsec_cbo()
        self.repaint_xs()

    def delete_user_data(self):
        """
        Function to delete the user channel data
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return
        else:
            if self.uc.question("Are you sure you want to delete all user channel data?"):
                self.gutils.clear_tables(
                    "user_chan_r",
                    "user_chan_v",
                    "user_chan_t",
                    "user_chan_n",
                    "user_xsec_n_data",
                    "user_noexchange_chan_areas",
                )
                self.uc.bar_info("User Channel Data deleted!")
                current_fid = self.xs_cbo.currentData()
                self.current_xsec_changed(current_fid)
                self.populate_xsec_cbo()
            return

    def delete_schematize_data(self):
        """
        Function to delete the schematized channel data
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return
        if self.gutils.is_table_empty("chan"):
            self.uc.bar_info("There are no schematized channel data. ")
            return
        else:
            if self.uc.question("Are you sure you want to delete all schematized channel data?"):
                self.gutils.clear_tables(
                    "chan",
                    "rbank",
                    "chan_elems",
                    "chan_r",
                    "chan_v",
                    "chan_t",
                    "chan_n",
                    "chan_confluences",
                    "xsec_n_data",
                    "noexchange_chan_cells",
                    "chan_wsel",
                    "chan_elems_interp"
                )
                self.uc.bar_info("Schematized Cross Sections deleted!")
                chan_schem = self.lyrs.data["chan"]["qlyr"]
                chan_elems = self.lyrs.data["chan_elems"]["qlyr"]
                rbank = self.lyrs.data["rbank"]["qlyr"]
                confluences = self.lyrs.data["chan_confluences"]["qlyr"]
                self.lyrs.lyrs_to_repaint = [chan_schem, chan_elems, rbank, confluences]
                self.lyrs.repaint_layers()
                current_fid = self.xs_cbo.currentData()
                self.current_xsec_changed(current_fid)
                self.populate_xsec_cbo()
            return

    def schematize_channels(self):
        """
        Function to schematize the channels
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return
        if self.gutils.is_table_empty("user_left_bank"):
            if not self.gutils.is_table_empty("chan"):
                if not self.uc.question(
                        "There are no user left bank lines.\n\n"
                        + "But there are schematized left banks and cross sections.\n"
                        + "Would you like to delete them?"
                ):
                    return
                else:
                    if self.uc.question("Are you sure you want to delete all channel data?"):
                        self.gutils.clear_tables(
                            "chan",
                            "rbank",
                            "chan_elems",
                            "chan_r",
                            "chan_v",
                            "chan_t",
                            "chan_n",
                            "chan_confluences",
                            "xsec_n_data",
                            "noexchange_chan_cells",
                            "chan_wsel",
                            "chan_elems_interp"
                        )
                    return
            else:
                self.uc.bar_warn("There are no User Left Bank lines! Please digitize them before running the tool.")
                return
        if self.gutils.is_table_empty("user_xsections"):
            self.uc.bar_warn("There are no User Cross Sections! Please digitize them before running the tool.")
            return
        if not self.gutils.is_table_empty("chan"):
            if not self.uc.question(
                    "There are already Schematized Channel Segments (Left Banks) and Cross Sections. Overwrite them?"
            ):
                return

        # Get an instance of the ChannelsSchematizer class:
        cs = ChannelsSchematizer(self.con, self.iface, self.lyrs)

        # Create the Schematized Left Bank (Channel Segments), joining cells intersecting
        # the User Left Bank Line, with arrows from one cell centroid to the next:
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            cs.create_schematized_channels()
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(traceback.format_exc())
            self.uc.show_error(
                "ERROR 060319.1611: Schematizing left bank lines failed !\n"
                "Please check your User Layers.\n\n"
                "Check that:\n\n"
                "   * For each User Left Bank line, the first cross section is\n"
                "     defined starting in the first grid cell.\n\n"
                "   * Each User Left Bank line has at least 2 cross sections\n"
                "     crossing it.\n\n"
                "   * All cross sections associated to a User Left Bank line\n"
                "     intersects (crossover) it."
                "\n_________________________________________________",
                e,
            )
            return
        QApplication.restoreOverrideCursor()

        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            cs.copy_features_from_user_channel_layer_to_schematized_channel_layer()
            cs.copy_features_from_user_xsections_layer_to_schematized_xsections_layer()

            self.gutils.create_xs_type_n_r_t_v_tables()

            cs.copy_user_xs_data_to_schem()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn(
                "WARNING 060319.1743: Schematizing failed while processing attributes! "
                "Please check your User Layers."
            )
            return
        QApplication.restoreOverrideCursor()

        if not self.gutils.is_table_empty("chan_elems"):
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                cs.make_distance_table()
            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.log_info(traceback.format_exc())
                self.uc.show_warn(
                    "WARNING 060319.1744: Schematizing failed while preparing interpolation table!\n\n"
                    "Please check your User Layers."
                )
                return
            QApplication.restoreOverrideCursor()
        else:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn(
                "WARNING 060319.1745: Schematizing failed while preparing interpolation table!\n\n"
                "Schematic Channel Cross Sections layer is empty!"
            )
            return

        chan_schem = self.lyrs.data["chan"]["qlyr"]
        chan_elems = self.lyrs.data["chan_elems"]["qlyr"]
        rbank = self.lyrs.data["rbank"]["qlyr"]
        confluences = self.lyrs.data["chan_confluences"]["qlyr"]
        self.lyrs.lyrs_to_repaint = [chan_schem, chan_elems, rbank, confluences]
        self.lyrs.repaint_layers()
        current_fid = self.xs_cbo.currentData()
        self.current_xsec_changed(current_fid)

        self.log_schematized_info()

        self.populate_xsec_cbo()

    def check_schematized_channel(self):
        """
        Function to check the schematized channel. FLO-2D Engine does that, but this tries to remove the necessity
        of a FLO-2D Engine run to check the schematized channel data.
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return
        if self.gutils.is_table_empty("chan"):
            self.uc.bar_warn("There is no schematized data! Please schematize the channel data before running tool.")
            return

        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)

            msg = ""

            # Add relevant data to the channel dict
            # Channel dict: {'left_grid': ['right_grid', topw, distt, xdistshort, xdistlong, xlen, arf_left, arf_right}
            channel_dict = {}

            # Calculate the Channel Top Width
            left_bank_grids_r = self.gutils.execute("SELECT elem_fid, fcw FROM chan_r").fetchall()
            # left_bank_grids_v = self.gutils.execute("SELECT elem_fid, nxsecnum FROM chan_n").fetchall() # TODO variable area
            left_bank_grids_t = self.gutils.execute("SELECT elem_fid, fcw FROM chan_t").fetchall()
            left_bank_grids_n = self.gutils.execute("SELECT elem_fid, nxsecnum FROM chan_n").fetchall()
            cell_size = int(float(self.gutils.get_cont_par("CELLSIZE")))  # Assuming that it is the SIDE on JIM's code

            for data in left_bank_grids_n + left_bank_grids_r + left_bank_grids_t:
                left_bank_grid = data[0]
                arf_left = self.gutils.execute(f"SELECT arf FROM blocked_cells WHERE grid_fid = '{left_bank_grid}'").fetchone()
                if not arf_left:
                    arf_left = 0
                else:
                    arf_left = arf_left[0]
                chan_elems = self.gutils.execute(f"SELECT rbankgrid, xlen FROM chan_elems WHERE fid = '{left_bank_grid}'").fetchone()
                right_bank_grid = chan_elems[0]
                arf_right = self.gutils.execute(f"SELECT arf FROM blocked_cells WHERE grid_fid = '{right_bank_grid}'").fetchone()
                if not arf_right:
                    arf_right = 0
                else:
                    arf_right = arf_right[0]
                xlen = chan_elems[1]

                lb_centroid = self.gutils.single_centroid(left_bank_grid)
                rb_centroid = self.gutils.single_centroid(right_bank_grid)
                lb_x = QgsGeometry().fromWkt(lb_centroid).asPoint().x()
                lb_y = QgsGeometry().fromWkt(lb_centroid).asPoint().y()
                rb_x = QgsGeometry().fromWkt(rb_centroid).asPoint().x()
                rb_y = QgsGeometry().fromWkt(rb_centroid).asPoint().y()

                xcaddist = lb_x - rb_x
                ycaddist = lb_y - rb_y

                xdistt = (xcaddist ** 2 + ycaddist ** 2) ** 0.5

                if data in left_bank_grids_n:
                    nxsecnum = data[1]
                    topw = self.gutils.execute(
                        f"SELECT (MAX(xi) - MIN(xi)) FROM xsec_n_data WHERE chan_n_nxsecnum = '{nxsecnum}'").fetchone()[0]
                else:
                    topw = data[1]

                if xcaddist < 1 or ycaddist < 1:
                    xdistshort = xdistt + cell_size
                    xdistlong = xdistt - cell_size * 1.10
                else:
                    xdistshort = xdistt + cell_size * 1.41412
                    xdistlong = xdistt - cell_size * 1.41412 * 1.10
                channel_dict[left_bank_grid] = [right_bank_grid, topw, xdistt, xdistshort, xdistlong, xlen, arf_left, arf_right]

            pd = QProgressDialog("Checking potential width errors", None, 0, len(channel_dict))
            pd.setWindowTitle("Checking Channel Data...")
            pd.setModal(True)
            pd.forceShow()
            pd.setValue(0)
            i = 0

            # 1 CHANNEL WIDTH ERROR
            close_elements = []
            area_elements = []
            for left_grid, data in channel_dict.items():

                topw = data[1]
                xdistt = data[2]
                xdistshort = data[3]
                xdistlong = data[4]
                xlen = data[5]
                arf_left = data[6]
                arf_right = data[7]

                acf = topw * xlen

                # 1.1 Cross-section is wider than the distance between two left and right bank elements

                # Distance is shorter than the top width
                if xdistshort < topw:
                    close_elements.append(left_grid)

                # Distance is longer than the top width
                if (topw > 2 * xdistt) and (xdistlong > topw):
                    close_elements.append(left_grid)

                # 1.2 Area on the bank elements is less than 5% - JIM's code translated to python

                # Floodplain surface area needs to be larger for the left bank element
                arealft = xdistshort * xlen - acf
                if arealft < 0:
                    area_elements.append(left_grid)

                # Available area is less than 5% of the floodplain surface
                apf_left = arealft * 0.5 * arf_left

                areapercent = apf_left / (cell_size * cell_size)
                if (areapercent < 0.05) and (arf_left > 0.999):
                    if left_grid not in area_elements: area_elements.append(left_grid)

                # Check storage on the left bank floodplain area
                if (areapercent < 0.05) and (arf_left < 0.999):
                    apf_left = arealft * 0.5
                    areapercent = apf_left / (cell_size * cell_size)
                    if areapercent < 0.05:
                        if left_grid not in area_elements: area_elements.append(left_grid)

                # Check storage on the right bank floodplain area
                if (areapercent < 0.05) and (arf_right > 0.999):
                    if left_grid not in area_elements: area_elements.append(left_grid)

                # Check storage on the right bank floodplain area
                if (areapercent < 0.05) and (arf_right < 0.999):
                    apf_right = arealft * 0.5
                    areapercent = apf_right / (cell_size * cell_size)
                    if areapercent < 0.05:
                        if left_grid not in area_elements: area_elements.append(left_grid)

                i += 1
                pd.setValue(i)

            # 2 RIGHT BANK ERROR

            # 2.1 Right bank is inside the two bank lines

            # 3 BOUNDARY CONDITION ERRORS

            # 3.1 Outflow last cross-section must be lower than adjacent upstream neighbor by 0.1 ft
            # Verify if there is Channel Outflow BC (outflow table)
            pd = QProgressDialog("Checking potential outflow boundary conditions errors", None, 0, len(channel_dict))
            pd.setValue(0)
            i = 0
            error_outflow_bc_grid = []
            outflow_bc_channel_grid_elements = self.gutils.execute(r"SELECT grid_fid FROM outflow_cells JOIN outflow ON "
                                                                   r"outflow_cells.outflow_fid = outflow.fid WHERE "
                                                                   r"outflow.chan_out = '1'").fetchall()

            for bc in outflow_bc_channel_grid_elements:
                bc_grid = bc[0]
                # Get the Channel Outflow Grid Element (chan_* table) TODO: Do this for all types of cross sections
                nxsecnum = self.gutils.execute(f"SELECT nxsecnum FROM chan_n WHERE elem_fid = '{bc_grid}'").fetchone()
                if nxsecnum:
                    # Get the xc number
                    xc = nxsecnum[0]
                    # Get the downstream xc number
                    upstream_xc = xc - 1
                    # Compare the minimum elevations (xsec_n_data table)
                    xc_min_elev = \
                        self.gutils.execute(f"SELECT MIN(yi) FROM xsec_n_data WHERE chan_n_nxsecnum = '{xc}'").fetchone()[0]
                    upstream_xc_min_elev = self.gutils.execute(
                        f"SELECT MIN(yi) FROM xsec_n_data WHERE chan_n_nxsecnum = '{upstream_xc}'").fetchone()[0]

                    if self.gutils.get_cont_par("METRIC") == "1":
                        outflow_elev_threshold = 0.03
                    elif self.gutils.get_cont_par("METRIC") == "0":
                        outflow_elev_threshold = 0.1

                    if float(upstream_xc_min_elev) - float(xc_min_elev) < outflow_elev_threshold:
                        error_outflow_bc_grid.append(bc_grid)

                i += 1
                pd.setValue(i)

            # 3.2 Upstream inflow boundary must be positive slope in the downstream direction
            # Verify if there is Channel Inflow BC (inflow table)
            pd = QProgressDialog("Checking potential outflow boundary conditions errors", None, 0, len(channel_dict))
            pd.setValue(0)
            i = 0

            error_inflow_bc_grid = []
            inflow_bc_channel_grid_elements = self.gutils.execute(
                r"SELECT grid_fid FROM inflow_cells JOIN inflow ON inflow_cells.inflow_fid = "
                r"inflow.fid WHERE inflow.ident = 'C'").fetchall()
            for bc in inflow_bc_channel_grid_elements:
                bc_grid = bc[0]
                # Get the Channel Inflow Grid Element (chan_* table) TODO: Do this for all types of cross sections
                nxsecnum = self.gutils.execute(f"SELECT nxsecnum FROM chan_n WHERE elem_fid = '{bc_grid}'").fetchone()
                if nxsecnum:
                    # Get the xc number
                    xc = nxsecnum[0]
                    # Get the downstream xc number
                    downstream_xc = xc + 1
                    # Compare the minimum elevations (xsec_n_data table)
                    xc_min_elev = \
                        self.gutils.execute(f"SELECT MIN(yi) FROM xsec_n_data WHERE chan_n_nxsecnum = '{xc}'").fetchone()[0]
                    downstream_xc_min_elev = self.gutils.execute(
                        f"SELECT MIN(yi) FROM xsec_n_data WHERE chan_n_nxsecnum = '{downstream_xc}'").fetchone()[0]
                    if downstream_xc_min_elev >= xc_min_elev:
                        error_inflow_bc_grid.append(bc_grid)

                i += 1
                pd.setValue(i)

            if len(close_elements) > 0:
                msg += "CHANNEL RIGHT BANK ELEMENTS NEED SOME ADJUSTMENT DUE TO THE CHANNEL WIDTH.  " \
                       "SET THE RIGHT BANK EITHER CLOSER OR FARTHER AWAY FROM THE LEFT BANK ELEMENT. " \
                       f"GRID ELEMENTS(S): \n{'-'.join(map(str, close_elements))}\n\n"

            if len(area_elements) > 0:
                msg += "THE REMAINING FLOODPLAIN SURFACE AREA ON THE CHANNEL BANK ELEMENTS NEEDS TO BE LARGER FOR LEFT BANK ELEMENT. " \
                       f"GRID ELEMENTS(S): \n{'-'.join(map(str, area_elements))}\n\n"

            if len(error_outflow_bc_grid) > 0:
                msg += "ERROR: CHANNEL OUTFLOW CROSS SECTION MUST BE LOWER THAN ADJACENT UPSTREAM NEIGHBOR BY 0.1. " \
                       f"GRID ELEMENTS(S): \n{'-'.join(map(str, error_outflow_bc_grid))}\n\n"

            if len(error_inflow_bc_grid) > 0:
                msg += "ERROR: THE FOLLOWING CHANNEL INFLOW NODES HAVE AN ADVERSE (NEGATIVE BED SLOPE) OR ABSOLUTELY FLAT BED " \
                       "SLOPE (ZERO SLOPE) TO THE NEXT DOWNSTREAM CHANNEL ELEMENT: \n(EITHER RAISE THE INFLOW NODE BED " \
                       "ELEVATION OR LOWER THE DOWNSTREAM CHANNEL ELEMENT BED ELEVATION). " \
                       f"GRID ELEMENTS(S): \n{'-'.join(map(str, error_inflow_bc_grid))}\n\n"

            pd.close()
            QApplication.restoreOverrideCursor()

            for widget in QApplication.instance().allWidgets():
                if isinstance(widget, QgsDockWidget):
                    if widget.windowTitle() == "FLO-2D Channel Check Report":
                        widget.close()

            if msg != "":
                dlg_channel_report = ChannelCheckReportDialog(self.iface, self.lyrs, self.gutils)
                plot_dock = QgsDockWidget()
                plot_dock.setWindowTitle("FLO-2D Channel Check Report")
                plot_dock.setWidget(dlg_channel_report)
                self.iface.addDockWidget(Qt.BottomDockWidgetArea, plot_dock)
                dlg_channel_report.report_te.insertPlainText(msg)

                grid_errors = list(set(
                    str(item) for sublist in [close_elements, area_elements, error_outflow_bc_grid, error_inflow_bc_grid]
                    for item in sublist))
                dlg_channel_report.error_grids_cbo.addItems(grid_errors)
                dlg_channel_report.show()
                while True:
                    ok = dlg_channel_report.exec_()
                    if ok:
                        break
                    else:
                        return

                self.uc.log_info(msg)
            else:
                self.uc.show_info("The schematized channel has passed all required checks!")

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(repr(e))
            self.uc.show_error("Channel Check Error!", e)

    def log_schematized_info(self):
        """
        Function to log the schematized info
        """
        qry_chan_names = """SELECT name FROM user_left_bank"""

        chan_names = self.gutils.execute(qry_chan_names).fetchall()

        qry_count_xs = """SELECT COUNT(seg_fid) FROM chan_elems GROUP BY seg_fid;"""
        total_xs = self.gutils.execute(qry_count_xs).fetchall()

        qry_interpolated = """SELECT COUNT(interpolated) FROM chan_elems WHERE interpolated = 1 GROUP BY seg_fid;"""
        interpolated_xs = self.gutils.execute(qry_interpolated).fetchall()

        for row_number, name in enumerate(chan_names):
            if interpolated_xs:
                if row_number <= len(interpolated_xs) - 1:
                    n_interpolated_xs = interpolated_xs[row_number][0]
                else:
                    n_interpolated_xs = 0
            else:
                n_interpolated_xs = 0
            original_xs = total_xs[row_number][0] - n_interpolated_xs
            log_msg = f"Interpolation of {name[0]}: {total_xs[row_number][0]} ({original_xs} xsecs & {n_interpolated_xs} interpolated)"
            self.uc.log_info(log_msg)

    def schematize_right_banks(self):
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return
        if self.gutils.is_table_empty("user_right_bank"):
            self.uc.bar_warn("There are no User Right Bank lines! Please digitize them before running the tool.")
            return

        # Get an instance of the ChannelsSchematizer class:
        cs = ChannelsSchematizer(self.con, self.iface, self.lyrs)

        # Create the Schematized Right Bank, joining cells intersecting
        # the User Right Bank Line, with arrows from one cell centroid to the next:
        try:
            cs.create_schematized_rbank_lines_from_user_rbanks_banks()

            if self.uc.question("Would you like to join left banks with right banks?"):
                # chan_schem = self.lyrs.data['chan']['qlyr']
                # rbank_schem = self.lyrs.data['rbank']['qlyr']

                pairs = [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7)]
                for xs_seg_fid, right_bank_fid in pairs:
                    self.reassign_xs_rightbanks_grid_id_from_schematized_rbanks(xs_seg_fid, right_bank_fid)

            self.gutils.create_schematized_rbank_lines_from_xs_tips()
            rbank = self.lyrs.data["rbank"]["qlyr"]
            rbank.updateExtents()
            rbank.triggerRepaint()
            rbank.removeSelection()

        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_error("ERROR 280718.1054: Schematizing right bank lines failed !", e)
            return

        rbank = self.lyrs.data["rbank"]["qlyr"]
        self.lyrs.lyrs_to_repaint = [rbank]
        self.lyrs.repaint_layers()

    def interpolate_channel_elevation(self):
        """
        Function to interpolate channel elevation
        """
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            xs_survey = self.save_chan_dot_dat_with_zero_natural_cross_sections()
            if xs_survey:
                if self.save_xsec_dot_dat_with_only_user_cross_sections():
                    if self.save_CHANBANK():
                        rtrn = -2
                        while rtrn == -2:
                            rtrn = self.run_INTERPOLATE()
                            if rtrn == 0:
                                s = QSettings()
                                last_dir = s.value("FLO-2D/lastGdsDir", "") + "/temp/"
                                fname = last_dir + "\\CONT.DAT"
                                if not fname:
                                    return
                                self.parser.scan_project_dir(fname)
                                self.import_chan(temp=last_dir)
                                zero, few = self.import_xsec()
                                m = "Elevation Cross Section Interpolated!"
                                if zero > 0:
                                    m += "\n\nWARNING: There are " + str(zero) + " cross sections with no stations."
                                if few > 0:
                                    m += (
                                            "\n\nWARNING: There are "
                                            + str(few)
                                            + " cross sections with less than 6 stations."
                                    )
                                if zero > 0 or few > 0:
                                    m += "\n\nIncrement the number of stations in the problematic cross sections."

                                shutil.rmtree(last_dir)
                                if m != "Elevation Cross Section Interpolated!":
                                    self.uc.bar_warn(m)
                                else:
                                    self.uc.bar_info(m)
                                self.uc.log_info(m)
            QApplication.restoreOverrideCursor()
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(repr(e))
            self.uc.show_error("Interpolate Channel Elevation Error!", e)

    def save_channel_DAT_and_XSEC_files(self):
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return
        if self.gutils.is_table_empty("chan"):
            self.uc.bar_warn("There are no Schematized Channel Segments (Left Banks) to export.")
            return
        if self.gutils.is_table_empty("chan_elems"):
            self.uc.bar_warn("There are no Schematized Channel Cross Sections to export.")
            return
        if self.gutils.is_table_empty("user_xsections"):
            self.uc.show_warn("WARNING 060319.1746: There are no user cross sections defined.")
            return

        xs_survey = self.save_chan_dot_dat_with_zero_natural_cross_sections()
        if xs_survey:
            if self.save_xsec_dot_dat_with_only_user_cross_sections():
                if self.save_CHANBANK():
                    QApplication.restoreOverrideCursor()
                    self.uc.show_info("Files CHAN.DAT, XSEC.DAT, and CHANBANK.DAT saved.")
                    rtrn = -2
                    while rtrn == -2:
                        rtrn = self.run_INTERPOLATE(xs_survey)
                        if rtrn == 0:
                            s = QSettings()
                            outdir = s.value("FLO-2D/lastGdsDir", "")

                            msg = QMessageBox()

                            q = "Cross sections interpolation performed!.\n"
                            q += "(in Directory: " + outdir + ")\n\n"
                            q += "CHAN.DAT and XSEC.DAT updated with the interpolated cross section data.\n\n"
                            q += "Now select:\n\n"
                            q += "      Import CHAN.DAT, CHANBANK.DAT, and XSEC.DAT files.\n\n"
                            q += "      or\n\n"
                            q += "      Run CHANRIGHTBANK.EXE to identify right bank cells.\n"
                            q += "      (It requires the CHAN.DAT, XSEC.DAT, and TOPO.DAT files).\n"
                            msg.setWindowTitle("Interpolation Performed")
                            msg.setText(q)
                            #                     msg.setStandardButtons(
                            #                         QMessageBox().Ok | QMessageBox().Cancel)
                            msg.addButton(
                                QPushButton("Import CHAN.DAT, CHANBANK.DAT, and XSEC.DAT files"),
                                QMessageBox.YesRole,
                            )
                            msg.addButton(QPushButton("Run CHANRIGHTBANK.EXE"), QMessageBox.NoRole)
                            msg.addButton(QPushButton("Cancel"), QMessageBox.RejectRole)
                            msg.setDefaultButton(QMessageBox().Cancel)
                            msg.setIcon(QMessageBox.Question)
                            ret = msg.exec_()
                            if ret == 0:
                                s = QSettings()
                                last_dir = s.value("FLO-2D/lastGdsDir", "")
                                fname = last_dir + "\\CONT.DAT"
                                if not fname:
                                    return
                                self.parser.scan_project_dir(fname)
                                self.import_chan()
                                zero, few = self.import_xsec()
                                m = "Interpolation completed! Check log for more information."
                                if zero > 0:
                                    m += "\n\nWARNING: There are " + str(zero) + " cross sections with no stations."
                                if few > 0:
                                    m += (
                                            "\n\nWARNING: There are "
                                            + str(few)
                                            + " cross sections with less than 6 stations."
                                    )
                                if zero > 0 or few > 0:
                                    m += "\n\nIncrement the number of stations in the problematic cross sections."
                                if m != "Interpolation completed! Check log for more information.":
                                    self.uc.bar_warn(m)
                                else:
                                    self.uc.bar_info(m)
                            if ret == 1:
                                self.uc.show_warn("WARNING 060319.1747: CHANRIGHTBANK.EXE execution is disabled!")
                            #                         self.run_CHANRIGHTBANK()
                            if ret == 2:
                                pass

        QApplication.restoreOverrideCursor()

    def import_chan(self, temp=False):
        s = QSettings()
        if temp:
            last_dir = s.value("FLO-2D/lastGdsDir", "") + "/temp/"
            if not os.path.isfile(last_dir + "\\CHAN.DAT"):
                self.uc.show_warn("WARNING 060319.1748: Can't import channels!.\nCHAN.DAT doesn't exist.")
                return
        else:
            last_dir = s.value("FLO-2D/lastGdsDir", "")
            if not os.path.isfile(last_dir + "\\CHAN.DAT"):
                self.uc.show_warn("WARNING 060319.1748: Can't import channels!.\nCHAN.DAT doesn't exist.")
                return

        cont_file = last_dir + "\\CHAN.DAT"

        chan_sql = [
            """INSERT INTO chan (geom, depinitial, froudc, roughadj, isedn) VALUES""",
            5,
        ]
        chan_elems_sql = [
            """INSERT INTO chan_elems (geom, fid, seg_fid, nr_in_seg, rbankgrid, fcn, xlen, type) VALUES""",
            8,
        ]
        chan_r_sql = [
            """INSERT INTO chan_r (elem_fid, bankell, bankelr, fcw, fcd) VALUES""",
            5,
        ]
        chan_v_sql = [
            """INSERT INTO chan_v (elem_fid, bankell, bankelr, fcd, a1, a2, b1, b2, c1, c2,
                                                 excdep, a11, a22, b11, b22, c11, c22) VALUES""",
            17,
        ]
        chan_t_sql = [
            """INSERT INTO chan_t (elem_fid, bankell, bankelr, fcw, fcd, zl, zr) VALUES""",
            7,
        ]
        chan_n_sql = ["""INSERT INTO chan_n (elem_fid, nxsecnum, xsecname) VALUES""", 3]
        chan_wsel_sql = [
            """INSERT INTO chan_wsel (istart, wselstart, iend, wselend) VALUES""",
            4,
        ]
        chan_conf_sql = [
            """INSERT INTO chan_confluences (geom, conf_fid, type, chan_elem_fid) VALUES""",
            4,
        ]
        chan_e_sql = ["""INSERT INTO user_noexchange_chan_areas (geom) VALUES""", 1]
        elems_e_sql = [
            """INSERT INTO noexchange_chan_cells (area_fid, grid_fid) VALUES""",
            2,
        ]

        sqls = {
            "R": [chan_r_sql, 4, 7],
            "V": [chan_v_sql, 4, 6],
            "T": [chan_t_sql, 4, 7],
            "N": [chan_n_sql, 2, 3],
        }

        #             try:
        self.gutils.clear_tables(
            "chan",
            "chan_elems",
            "chan_r",
            "chan_v",
            "chan_t",
            "chan_n",
            "chan_confluences",
            "user_noexchange_chan_areas",
            "noexchange_chan_cells",
            "chan_wsel",
        )

        segments, wsel, confluence, noexchange = self.parser.parse_chan()
        for i, seg in enumerate(segments, 1):
            xs = seg[-1]  # Last element from segment. [-1] means count from right, last from right.
            gids = []
            for ii, row in enumerate(xs, 1):  # Adds counter ii to iterable.
                char = row[0]  # " R", "V", "T", or "N"
                gid = row[1]  # Grid element number (no matter what 'char' is).
                rbank = row[-1]
                geom = (
                    self.gutils.build_linestring([gid, rbank])
                    if int(rbank) > 0
                    else self.gutils.build_linestring([gid, gid])
                )
                sql, fcn_idx, xlen_idx = sqls[char]
                xlen = row.pop(xlen_idx)
                fcn = row.pop(fcn_idx)
                params = row[1:-1]
                gids.append(gid)
                chan_elems_sql += [(geom, gid, i, ii, rbank, fcn, xlen, char)]
                sql += [tuple(params)]
            options = seg[:-1]
            geom = self.gutils.build_linestring(gids)
            chan_sql += [(geom,) + tuple(options)]

        for row in wsel:
            chan_wsel_sql += [tuple(row)]

        for i, row in enumerate(confluence, 1):
            gid1, gid2 = row[1], row[2]
            cells = self.grid_centroids([gid1, gid2], buffers=True)

            geom1, geom2 = cells[gid1], cells[gid2]
            chan_conf_sql += [(geom1, i, 0, gid1)]
            chan_conf_sql += [(geom2, i, 1, gid2)]

        for i, row in enumerate(noexchange, 1):
            gid = row[-1]
            geom = self.grid_centroids([gid])[0]
            chan_e_sql += [(self.build_buffer(geom, self.buffer),)]
            elems_e_sql += [(i, gid)]

        self.gutils.batch_execute(
            chan_sql,
            chan_elems_sql,
            chan_r_sql,
            chan_v_sql,
            chan_t_sql,
            chan_n_sql,
            chan_conf_sql,
            chan_e_sql,
            elems_e_sql,
            chan_wsel_sql,
        )
        qry = """UPDATE chan SET name = 'Channel ' ||  cast(fid as text);"""
        self.gutils.execute(qry)

    #
    #             except Exception:
    #                 self.uc.log_info(traceback.format_exc())
    #                 self.uc.show_warn('Import channels failed!. Check CHAN.DAT and CHANBANK.DAT files.')
    #                 #self.uc.show_warn('Import channels failed!.\nMaybe the number of left bank and right bank cells are different.')

    def import_xsec(self):
        xsec_sql = ["""INSERT INTO xsec_n_data (chan_n_nxsecnum, xi, yi) VALUES""", 3]
        zero = 0
        few = 0
        self.gutils.clear_tables("xsec_n_data")
        data = self.parser.parse_xsec()
        for key in list(data.keys()):
            xsec_no, xsec_name = key
            nodes = data[key]
            if len(nodes) == 0:
                zero += 1
            elif len(nodes) < 6:
                #                 few +=
                few += 1
            for row in nodes:
                xsec_sql += [(xsec_no,) + tuple(row)]

        self.gutils.batch_execute(xsec_sql)
        return zero, few

    def save_chan_dot_dat_with_zero_natural_cross_sections(self):
        # check if there are any channels defined
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if self.gutils.is_table_empty("chan"):
                QApplication.restoreOverrideCursor()
                return []

            chan_sql = """SELECT fid, depinitial, froudc, roughadj, isedn FROM chan ORDER BY fid;"""
            chan_elems_sql = """SELECT fid, rbankgrid, fcn, xlen, type, user_xs_fid FROM chan_elems WHERE seg_fid = ? ORDER BY nr_in_seg;"""

            chan_r_sql = """SELECT elem_fid, bankell, bankelr, fcw, fcd FROM chan_r WHERE elem_fid = ?;"""
            chan_v_sql = """SELECT elem_fid, bankell, bankelr, fcd, a1, a2, b1, b2, c1, c2,
                                   excdep, a11, a22, b11, b22, c11, c22 FROM chan_v WHERE elem_fid = ?;"""
            chan_t_sql = """SELECT elem_fid, bankell, bankelr, fcw, fcd, zl, zr FROM chan_t WHERE elem_fid = ?;"""
            chan_n_sql = """SELECT elem_fid, nxsecnum FROM chan_n WHERE elem_fid = ?;"""

            chan_wsel_sql = """SELECT istart, wselstart, iend, wselend FROM chan_wsel ORDER BY fid;"""
            chan_conf_sql = """SELECT chan_elem_fid FROM chan_confluences ORDER BY fid;"""
            chan_e_sql = """SELECT grid_fid FROM noexchange_chan_cells ORDER BY fid;"""

            segment = "   {0:.2f}   {1:.2f}   {2:.2f}   {3}\n"
            chan_r = "R" + "  {}" * 7 + "\n"
            chan_v = "V" + "  {}" * 19 + "\n"
            chan_t = "T" + "  {}" * 9 + "\n"
            chan_n = "N" + "  {}" * 4 + "\n"
            chanbank = " {0: <10} {1}\n"
            wsel = "{0} {1:.2f}\n"
            conf = " C {0}  {1}\n"
            chan_e = " E {0}\n"

            sqls = {
                "R": [chan_r_sql, chan_r, 3, 6],
                "V": [chan_v_sql, chan_v, 3, 5],
                "T": [chan_t_sql, chan_t, 3, 6],
                "N": [chan_n_sql, chan_n, 1, 2],
            }

            chan_rows = self.gutils.execute(chan_sql).fetchall()
            if not chan_rows:
                QApplication.restoreOverrideCursor()
                return []
            else:
                pass

            qry = "SELECT user_xs_fid, nxsecnum FROM user_chan_n;"
            natural_channel_section_number = self.gutils.execute(qry).fetchall()
            if len(natural_channel_section_number) <= 1:
                QApplication.restoreOverrideCursor()
                self.uc.bar_warn("ERROR: There is insufficient user cross-sections to interpolate. Check User Cross "
                                 "Sections table.")
                return []

            natural_channel_section_number_dict = dict()
            for i, row in enumerate(natural_channel_section_number):
                row = [x if x is not None else "" for x in row]
                user_xs_fid, nxsecum = row
                natural_channel_section_number_dict[user_xs_fid] = nxsecum

            s = QSettings()
            last_dir = s.value("FLO-2D/lastGdsDir", "")
            # Create a temporary directory on the export folder
            outdir = last_dir + "/temp/"
            if not os.path.exists(outdir):
                os.mkdir(outdir)

            QApplication.restoreOverrideCursor()
            if outdir:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                chan = os.path.join(outdir, "CHAN.DAT")
                if os.path.isfile(chan):
                    os.remove(chan)
                try:
                    with open(chan, "w") as c:
                        surveyed = 0
                        non_surveyed = 0

                        ISED = self.gutils.get_cont_par("ISED")

                        for row in chan_rows:
                            row = [x if x is not None else "0" for x in row]
                            fid = row[0]
                            if ISED == "0":
                                row[4] = ""
                            c.write(
                                segment.format(*row[1:5])
                            )  # Writes depinitial, froudc, roughadj, isedn from 'chan' table (schematic layer).
                            # A single line for each channel segment. The next lines will be the grid elements of
                            # this channel segment.
                            previous_xs = -999

                            for elems in self.gutils.execute(
                                    chan_elems_sql, (fid,)
                            ):  # each 'elems' is a list [(fid, rbankgrid, fcn, xlen, type)] from
                                # 'chan_elems' table (the cross sections in the schematic layer),
                                #  that has the 'fid' value indicated (the channel segment id).

                                elems = [
                                    x if x is not None else "" for x in elems
                                ]  # If 'elems' has a None in any of above values of list, replace it by ''
                                (
                                    eid,
                                    rbank,
                                    fcn,
                                    xlen,
                                    typ,
                                    usr_xs_fid,
                                ) = elems  # Separates values of list into individual variables.
                                sql, line, fcn_idx, xlen_idx = sqls[
                                    typ
                                ]  # depending on 'typ' (R,V,T, or N) select sql (the SQLite SELECT statement to execute),
                                # line (format to write), fcn_idx (?), and xlen_idx (?)
                                res = [
                                    x if x is not None else "" for x in self.gutils.execute(sql, (eid,)).fetchone()
                                ]  # 'res' is a list of values depending on 'typ' (R,V,T, or N).

                                if typ == "N":
                                    res.insert(
                                        1, fcn
                                    )  # Add 'fcn' (coming from table Â´chan_elems' (cross sections) to 'res' list) in position 'fcn_idx'.
                                    res.insert(
                                        2, xlen
                                    )  # Add Â´xlen' (coming from table Â´chan_elems' (cross sections) to 'res' list in position 'xlen_idx'.
                                    if usr_xs_fid == previous_xs:
                                        res.insert(3, 0)
                                        non_surveyed += 1
                                    else:
                                        res.insert(
                                            3,
                                            natural_channel_section_number_dict[usr_xs_fid],
                                        )
                                        surveyed += 1
                                        previous_xs = usr_xs_fid
                                else:
                                    res.insert(
                                        fcn_idx, fcn
                                    )  # Add 'fcn' (coming from table Â´chan_elems' (cross sections) to 'res' list) in position 'fcn_idx'.
                                    res.insert(
                                        xlen_idx, xlen
                                    )  # Add Â´xlen' (coming from table Â´chan_elems' (cross sections) to 'res' list in position 'xlen_idx'.

                                c.write(line.format(*res))

                        for row in self.gutils.execute(chan_wsel_sql):
                            c.write(wsel.format(*row[:2]))
                            c.write(wsel.format(*row[2:]))

                        pairs = []
                        for row in self.gutils.execute(chan_conf_sql):
                            chan_elem = row[0]
                            if not pairs:
                                pairs.append(chan_elem)
                            else:
                                pairs.append(chan_elem)
                                c.write(conf.format(*pairs))
                                del pairs[:]

                        for row in self.gutils.execute(chan_e_sql):
                            c.write(chan_e.format(row[0]))

                    QApplication.restoreOverrideCursor()
                    return [surveyed, non_surveyed]

                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 190521.1733: couln't export CHAN.DAT and/or XSEC.DAT !", e)
                    return []

            else:
                QApplication.restoreOverrideCursor()
                return []

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(repr(e))
            return []

    def save_xsec_dot_dat_with_only_user_cross_sections(self):
        chan_n_sql = """SELECT user_xs_fid, nxsecnum, xsecname FROM user_chan_n ORDER BY nxsecnum;"""
        xsec_sql = """SELECT xi, yi FROM user_xsec_n_data WHERE chan_n_nxsecnum = ? ORDER BY fid;"""

        user_xsections_sql = """SELECT fid, name FROM user_xsections ORDER BY fid;"""

        xsec_line = """X     {0}  {1}\n"""
        pkt_line = """ {0:<10} {1: >10}\n"""
        nr = "{0:.2f}"

        chan_n = self.gutils.execute(chan_n_sql).fetchall()
        if not chan_n:
            self.uc.show_warn(
                "WARNING 230319.0645: There are no user cross sections of type n defined!\n\n"
                + "XSEC.DAT was not saved!"
            )
            return False
        else:
            pass

        user_xsections = self.gutils.execute(user_xsections_sql).fetchall()
        if not user_xsections:
            self.uc.show_warn(
                "WARNING 230319.0646: There are no user cross sections defined!\n\n" + "XSEC.DAT was not saved!"
            )
            return False
        else:
            pass

        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")
        # Create a temporary directory on the export folder
        outdir = last_dir + "/temp/"
        if not os.path.exists(outdir):
            os.mkdir(outdir)

        if outdir:
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                xsec = os.path.join(outdir, "XSEC.DAT")
                with open(xsec, "w") as x:
                    for fid, nxsecnum, name in chan_n:
                        x.write(xsec_line.format(nxsecnum, name))
                        for xi, yi in self.gutils.execute(xsec_sql, (fid,)):
                            x.write(pkt_line.format(nr.format(xi), nr.format(yi)))
                QApplication.restoreOverrideCursor()
                return True
            except Exception as e:
                QApplication.restoreOverrideCursor()
                return False
        else:
            return False

    def save_CHANBANK(self):
        try:
            line = " {0: <10} {1}\n"
            rbanks = self.gutils.execute("SELECT fid, rbankgrid FROM chan_elems;").fetchall()
            if rbanks:
                s = QSettings()
                last_dir = s.value("FLO-2D/lastGdsDir", "")
                # Create a temporary directory on the export folder
                outdir = last_dir + "/temp/"
                if not os.path.exists(outdir):
                    os.mkdir(outdir)
                if outdir:
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    chanbank = os.path.join(outdir, "CHANBANK.DAT")
                    with open(chanbank, "w") as cb:
                        for rb in rbanks:
                            cb.write(line.format(rb[0], rb[1]))
                    QApplication.restoreOverrideCursor()
                    return True
        except Exception as e:
            self.uc.log_info(repr(e))
            self.uc.show_error("ERROR 260521.1207: Couldn't export CHANBANK.DAT!", e)
            return False

    def run_INTERPOLATE(self):
        if sys.platform != "win32":
            self.uc.bar_warn("Could not run interpolation under current operation system!")
            return -1
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            s = QSettings()
            self.project_dir = s.value("FLO-2D/lastGdsDir", "") + "/temp/"
            self.exe_dir = s.value("FLO-2D/last_flopro", "")

            if os.path.isfile(self.exe_dir + "\\INTERPOLATE.EXE"):
                interpolate = XSECInterpolatorExecutor(self.exe_dir, self.project_dir)
                return_code = interpolate.run()
                QApplication.restoreOverrideCursor()
                if return_code != 0:
                    self.uc.show_warn(
                        "WARNING 280119.0631 : Cross sections interpolation failed!\n\n"
                        "Interpolation program finished with return code " + str(return_code) + "."
                                                                                                "\n\nCheck content and format of CHAN.DAT and XSEC.DAT files."
                                                                                                "\n\n For natural cross sections:"
                                                                                                "\n\n      - Cross section numbers sequence in CHAN.DAT must be consecutive."
                                                                                                "\n\n      - Total number of cross sections in CHAN.DAT and XSEC.DAT must be equal."
                                                                                                "\n\n      - Each cross section must have at least 6 station pairs (distance, elevation)."
                                                                                                "\n              (use the Cross Sections Editor widget to define the"
                                                                                                "\n               cross sections stations, and then schematize them)"
                    )

                return return_code
            else:
                QApplication.restoreOverrideCursor()
                self.uc.show_warn("WARNING 060319.1750: Program INTERPOLATE.EXE is not in directory\n\n" + self.exe_dir)
                return -2
        except Exception as e:
            self.uc.log_info(repr(e))
            self.uc.bar_error("ERROR 280318.0528: Cross sections interpolation failed!")
            return -1

    def run_CHANRIGHTBANK(self):
        if sys.platform != "win32":
            self.uc.bar_warn("Could not run CHANRIGHTBANK.EXE under current operation system!")
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if os.path.isfile(self.exe_dir + "\\CHANRIGHTBANK.EXE"):
                chanrightbank = ChanRightBankExecutor(self.exe_dir, self.project_dir)
                return_code = chanrightbank.run()
                if return_code != 0:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_warn(
                        "WARNING 060319.1751: Right bank cells selection failed!\n\n"
                        + "Program finished with return code "
                        + str(return_code)
                        + "."
                        + "\n\nCheck content and format of CHAN.DAT, XSEC.DAT, and TOPO.DAT files."
                        + "\n\nHave you assigned elevations to cells?"
                    )
                else:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_warn(
                        "WARNING 060319.1752: Right bank cells calculated!\n\n"
                        + "CHANBANK.DAT written as pairs (left bank cell, right bank cell)\n"
                        + "in directory\n\n"
                        + self.project_dir
                    )
            else:
                QApplication.restoreOverrideCursor()
                self.uc.show_warn(
                    "WARNING 060319.1753: Program CHANRIGHTBANK.EXE is not in directory!.\n\n" + self.exe_dir
                )
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(repr(e))
            self.uc.bar_warn("CHANRIGHTBANK.EXE failed!")

    def interpolate_xs_values(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        if not self.interp_bed_and_banks():
            QApplication.restoreOverrideCursor()
            self.uc.show_warn(
                "WARNING 060319.1756: Interpolation of cross-sections values failed! " "Please check your User Layers."
            )
            return
        else:
            current_fid = self.xs_cbo.currentData()
            self.current_xsec_changed(current_fid)
            QApplication.restoreOverrideCursor()
            self.uc.bar_info("Interpolation of cross-sections values finished!")

    def interpolate_xs_values_externally(self):
        os.chdir("C:/Users/Juan Jose Rodriguez/Desktop/XSEC Interpolated")
        subprocess.call("INTERPOLATE.EXE")

    def reassign_rightbanks_from_CHANBANK_file(self):
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return
        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")
        chanbank_file, __ = QFileDialog.getOpenFileName(
            None,
            "Select CHANBANK.DAT file to read",
            directory=last_dir,
            filter="CHANBANK.DAT",
        )
        if not chanbank_file:
            return

        s.setValue("FLO-2D/lastGdsDir", os.path.dirname(chanbank_file))

        try:
            new_feats = []
            xs_lyr = self.lyrs.data["chan_elems"]["qlyr"]

            # Create a dictionary of pairs (left bank cell, right bank cell) read from CHANBANK.DAT file:
            pd = ParseDAT()
            pairs = {left: right for left, right in pd.single_parser(chanbank_file)}

            # Create a list of features taken from cham_elems layer (schematized cross sections), modifying their geometry
            # by changing the point of the coordinates of the right bank cell:
            for f in xs_lyr.getFeatures():
                xs_feat = QgsFeature()
                # Copy the next complete feature of chan_elems layer.
                xs_feat = f
                left = str(f["fid"])

                # Only change the geometry of the right bank cell (if it is not null or zero):
                if left in pairs:
                    right = pairs.get(left)
                    if int(right) > 0 and right is not None and int(left) > 0 and left is not None:
                        pnt0 = self.gutils.single_centroid(left)
                        qgsPoint0 = QgsGeometry().fromWkt(pnt0).asPoint()
                        pnt1 = self.gutils.single_centroid(right)
                        qgsPoint1 = QgsGeometry().fromWkt(pnt1).asPoint()
                        new_xs = QgsGeometry.fromPolylineXY([qgsPoint0, qgsPoint1])

                        xs_feat.setGeometry(new_xs)
                        xs_feat.setAttribute("rbankgrid", right)

                new_feats.append(xs_feat)

            # Replace all features of chan_elems with the new calculated features:
            xs_lyr.startEditing()
            for feat in xs_lyr.getFeatures():
                xs_lyr.deleteFeature(feat.id())
            for feat in new_feats:
                xs_lyr.addFeature(feat)
            xs_lyr.commitChanges()
            xs_lyr.updateExtents()
            xs_lyr.triggerRepaint()
            xs_lyr.removeSelection()

            self.gutils.create_schematized_rbank_lines_from_xs_tips()
            rbank = self.lyrs.data["rbank"]["qlyr"]
            rbank.updateExtents()
            rbank.triggerRepaint()
            rbank.removeSelection()

        except Exception as e:
            self.uc.show_error(
                "ERROR 260618.0416: couln't read CHANBANK.DAT or reassign right bank coordinates !",
                e,
            )

    def show_channel(self, fid):
        """
        Function to show the channel schematized data
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        units = "CMS" if self.gutils.get_cont_par("METRIC") == "1" else "CFS"

        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)

        self.chan_seg = ChannelSegment(fid, self.iface.f2d["con"], self.iface)
        self.chan_seg.get_row()  # Assigns to self.chan_seg all field values of the selected schematized channel:
        # 'name', 'depinitial',  'froudc',  'roughadj', 'isedn', 'notes', 'user_lbank_fid', 'rank'
        if not self.chan_seg.get_profiles():
            return
        self.plot.clear()
        sta, lb, rb, bed = [], [], [], []

        ordered_dict = self.chan_seg.profiles.items()

        for item in ordered_dict:
            key = str(item[0])

        for st, data in ordered_dict:
            sta.append(data["station"])
            lb.append(data["lbank_elev"])
            rb.append(data["rbank_elev"])
            bed.append(data["bed_elev"])

        self.plot.plot.legend = None
        self.plot.plot.addLegend(offset=(0, 30))
        self.plot.plot.setTitle(title=f"Channel Profile - {fid}")
        self.plot.plot.setLabel("bottom", text="Channel length")
        self.plot.plot.setLabel("left", text="")
        self.plot.add_item("Bed elevation", [sta, bed], col=QColor(Qt.black), sty=Qt.SolidLine)
        self.plot.add_item("Left bank", [sta, lb], col=QColor(Qt.darkGreen), sty=Qt.SolidLine)
        self.plot.add_item("Right bank", [sta, rb], col=QColor(Qt.darkYellow), sty=Qt.SolidLine)

        try:  # Build table.
            data_model = StandardItemModel()
            self.tview.undoStack.clear()
            self.tview.setModel(data_model)
            data_model.clear()
            data_model.setHorizontalHeaderLabels([f"Station ({self.system_units[units][0]})",
                                                  f"Bed elevation ({self.system_units[units][0]})",
                                                  f"Left bank ({self.system_units[units][0]})",
                                                  f"Right bank ({self.system_units[units][0]})",
                                                 ])

            data = zip(sta, bed, lb, rb)
            for station, bed_elev, left_bank, right_bank in data:
                station_item = StandardItem("{:.2f}".format(station)) if station is not None else StandardItem("")
                bed_item = StandardItem("{:.2f}".format(bed_elev)) if bed_elev is not None else StandardItem("")
                left_bank_item = StandardItem("{:.2f}".format(left_bank)) if left_bank is not None else StandardItem("")
                right_bank_item = StandardItem("{:.2f}".format(right_bank)) if right_bank is not None else StandardItem(
                    "")
                data_model.appendRow([station_item,
                                      bed_item,
                                      left_bank_item,
                                      right_bank_item,
                                      ])

            self.tview.horizontalHeader().setStretchLastSection(True)
            for col in range(3):
                self.tview.setColumnWidth(col, 100)
            for i in range(data_model.rowCount()):
                self.tview.setRowHeight(i, 20)
            return
        except:
            self.uc.bar_warn("Error while building table for channel!")
            return

    def show_channel_peaks(self, table, fid):
        """
        Function to show the channel peaks
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        units = "CMS" if self.gutils.get_cont_par("METRIC") == "1" else "CFS"

        s = QSettings()
        HYCHAN_file = s.value("FLO-2D/lastHYCHANFile", "")
        GDS_dir = s.value("FLO-2D/lastGdsDir", "")
        # Check if there is an HYCHAN.OUT file on the FLO-2D QSettings
        if not os.path.isfile(HYCHAN_file):
            HYCHAN_file = GDS_dir + r"/HYCHAN.OUT"
            # Check if there is an HYCHAN.OUT file on the export folder
            if not os.path.isfile(HYCHAN_file):
                self.uc.bar_warn(
                    "No HYCHAN.OUT file found. Please ensure the simulation has completed and verify the project export folder.")
                return
        # Check if the HYCHAN.OUT has data on it
        if os.path.getsize(HYCHAN_file) == 0:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("File  '" + os.path.basename(HYCHAN_file) + "'  is empty!")
            return

        # Read HYCHAN.OUT and create a dictionary of grid: [max_water_elev, peak_discharge].
        peaks_dict = {}
        peaks_list = []
        with open(HYCHAN_file, "r") as myfile:
            while True:
                try:
                    velocity_list = []
                    froude_list = []
                    flow_area_list = []
                    w_perimeter_list = []
                    hyd_radius_list = []
                    top_width_list = []
                    width_depth_list = []
                    energy_slope_list = []
                    shear_stress_list = []
                    surf_area_list = []
                    line = next(myfile)
                    if "CHANNEL HYDROGRAPH FOR ELEMENT NO:" in line:
                        grid = line.split()[-1]
                        line = next(myfile)
                        line = next(myfile)
                        peak_discharge = line.split(f"MAXIMUM DISCHARGE ({units}) =")[1].split()[0]
                        line = next(myfile)
                        max_water_elev = line.split("MAXIMUM STAGE = ")[1].split()[0]
                        for _ in range(4):
                            line = next(myfile)
                        while True:
                            line = next(myfile)
                            if not line.strip():  # If the line is empty, exit the loop
                                break
                            line = line.split()
                            velocity_list.append(float(line[3]))
                            froude_list.append(float(line[5]))
                            flow_area_list.append(float(line[6]))
                            w_perimeter_list.append(float(line[7]))
                            hyd_radius_list.append(float(line[8]))
                            top_width_list.append(float(line[9]))
                            width_depth_list.append(float(line[10]))
                            energy_slope_list.append(float(line[11]))
                            shear_stress_list.append(float(line[12]))
                            surf_area_list.append(float(line[13]))
                        max_velocity = max(velocity_list)
                        max_froude = max(froude_list)
                        max_flow_area = max(flow_area_list)
                        max_w_perimeter = max(w_perimeter_list)
                        max_hyd_radius = max(hyd_radius_list)
                        max_top_width = max(top_width_list)
                        max_width_depth = max(width_depth_list)
                        max_energy_slope = max(energy_slope_list)
                        max_shear_stress = max(shear_stress_list)
                        max_surf_area = max(surf_area_list)

                        peaks_dict[grid] = [max_water_elev,
                                            peak_discharge,
                                            max_velocity,
                                            max_froude,
                                            max_flow_area,
                                            max_w_perimeter,
                                            max_hyd_radius,
                                            max_top_width,
                                            max_width_depth,
                                            max_energy_slope,
                                            max_shear_stress,
                                            max_surf_area,
                                            ]
                        peaks_list.append((grid,
                                           max_water_elev,
                                           peak_discharge,
                                           max_velocity,
                                           max_froude,
                                           max_flow_area,
                                           max_w_perimeter,
                                           max_hyd_radius,
                                           max_top_width,
                                           max_width_depth,
                                           max_energy_slope,
                                           max_shear_stress,
                                           max_surf_area,
                                           ))
                    else:
                        pass
                except StopIteration:
                    break

        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)

        self.chan_seg = ChannelSegment(fid, self.iface.f2d["con"], self.iface)
        self.chan_seg.get_row()  # Assigns to self.chan_seg all field values of the selected schematized channel:
        # 'name', 'depinitial',  'froudc',  'roughadj', 'isedn', 'notes', 'user_lbank_fid', 'rank'
        if not self.chan_seg.get_profiles():
            return
        self.plot.clear()
        sta, lb, rb, bed = [], [], [], []
        max_water_elev = []
        peak_discharge = []
        max_velocity = []
        max_froude = []
        max_flow_area = []
        max_w_perimeter = []
        max_hyd_radius = []
        max_top_width = []
        max_width_depth = []
        max_energy_slope = []
        max_shear_stress = []
        max_surf_area = []

        ordered_dict = self.chan_seg.profiles.items()

        for item in ordered_dict:
            key = str(item[0])
            if key in peaks_dict:
                item[1].update({'max_water_elev': float(peaks_dict[key][0]),
                                'peak_discharge': float(peaks_dict[key][1]),
                                'max_velocity': float(peaks_dict[key][2]),
                                'max_froude': float(peaks_dict[key][3]),
                                'max_flow_area': float(peaks_dict[key][4]),
                                'max_w_perimeter': float(peaks_dict[key][5]),
                                'max_hyd_radius': float(peaks_dict[key][6]),
                                'max_top_width': float(peaks_dict[key][7]),
                                'max_width_depth': float(peaks_dict[key][8]),
                                'max_energy_slope': float(peaks_dict[key][9]),
                                'max_shear_stress': float(peaks_dict[key][10]),
                                'max_surf_area': float(peaks_dict[key][11])}
                               )

        for st, data in ordered_dict:
            if "max_water_elev" in data.keys():
                sta.append(data["station"])
                lb.append(data["lbank_elev"])
                rb.append(data["rbank_elev"])
                bed.append(data["bed_elev"])
                max_water_elev.append(data["max_water_elev"])
                peak_discharge.append(data["peak_discharge"])
                max_velocity.append(data["max_velocity"])
                max_froude.append(data["max_froude"])
                max_flow_area.append(data["max_flow_area"])
                max_w_perimeter.append(data["max_w_perimeter"])
                max_hyd_radius.append(data["max_hyd_radius"])
                max_top_width.append(data["max_top_width"])
                max_width_depth.append(data["max_width_depth"])
                max_energy_slope.append(data["max_energy_slope"])
                max_shear_stress.append(data["max_shear_stress"])
                max_surf_area.append(data["max_surf_area"])

        self.plot.plot.legend = None
        self.plot.plot.addLegend(offset=(0, 30))
        self.plot.plot.setTitle(title=f"Channel Profile - {fid}")
        self.plot.plot.setLabel("bottom", text="Channel length")
        self.plot.plot.setLabel("left", text="")
        self.plot.add_item(f"Bed elevation ({self.system_units[units][0]})", [sta, bed], col=QColor(Qt.black), sty=Qt.SolidLine)
        self.plot.add_item(f"Left bank ({self.system_units[units][0]})", [sta, lb], col=QColor(Qt.darkGreen), sty=Qt.SolidLine)
        self.plot.add_item(f"Right bank ({self.system_units[units][0]})", [sta, rb], col=QColor(Qt.darkYellow), sty=Qt.SolidLine)
        self.plot.add_item(f"Max. Water ({self.system_units[units][0]})", [sta, max_water_elev], col=QColor(Qt.blue), sty=Qt.SolidLine, hide=True)
        self.plot.add_item(f"Velocity ({self.system_units[units][1]})", [sta, max_velocity], col=QColor(Qt.green), sty=Qt.SolidLine, hide=True)
        self.plot.add_item(f"Froude", [sta, max_froude], col=QColor(Qt.gray), sty=Qt.SolidLine, hide=True)
        self.plot.add_item(f"Flow area ({self.system_units[units][3]})", [sta, max_flow_area], col=QColor(Qt.red), sty=Qt.SolidLine, hide=True)
        self.plot.add_item(f"Wetted perimeter ({self.system_units[units][0]})", [sta, max_w_perimeter], col=QColor(Qt.yellow), sty=Qt.SolidLine, hide=True)
        self.plot.add_item(f"Hydraulic radius ({self.system_units[units][0]})", [sta, max_hyd_radius], col=QColor(Qt.darkBlue), sty=Qt.SolidLine, hide=True)
        self.plot.add_item(f"Top width ({self.system_units[units][0]})", [sta, max_top_width], col=QColor(Qt.darkRed), sty=Qt.SolidLine, hide=True)
        self.plot.add_item(f"Width/Depth", [sta, max_width_depth], col=QColor(Qt.darkCyan), sty=Qt.SolidLine, hide=True)
        self.plot.add_item(f"Energy slope", [sta, max_energy_slope], col=QColor(Qt.magenta), sty=Qt.SolidLine, hide=True)
        self.plot.add_item(f"Shear stress ({self.system_units[units][4]})", [sta, max_shear_stress], col=QColor(Qt.darkYellow), hide=True)
        self.plot.add_item(f"Surface area ({self.system_units[units][3]})", [sta, max_surf_area], col=QColor(Qt.darkMagenta), hide=True)

        try:  # Build table.
            data_model = StandardItemModel()
            self.tview.undoStack.clear()
            self.tview.setModel(data_model)
            data_model.clear()
            data_model.setHorizontalHeaderLabels([f"Station ({self.system_units[units][0]})",
                                                  f"Bed elevation ({self.system_units[units][0]})",
                                                  f"Left bank ({self.system_units[units][0]})",
                                                  f"Right bank ({self.system_units[units][0]})",
                                                  f"Max. Water ({self.system_units[units][0]})",
                                                  f"Velocity ({self.system_units[units][1]})",
                                                  f"Froude",
                                                  f"Flow area ({self.system_units[units][3]})",
                                                  f"Wetted perimeter ({self.system_units[units][0]})",
                                                  f"Hydraulic radius ({self.system_units[units][0]})",
                                                  f"Top width ({self.system_units[units][0]})",
                                                  f"Width/Depth",
                                                  f"Energy slope",
                                                  f"Shear stress ({self.system_units[units][4]})",
                                                  f"Surface area ({self.system_units[units][3]})"])

            data = zip(sta, bed, lb, rb, max_water_elev, max_velocity, max_froude, max_flow_area, max_w_perimeter, max_hyd_radius, max_top_width, max_width_depth,
                       max_energy_slope, max_shear_stress, max_surf_area)
            for station, bed_elev, left_bank, right_bank, mw, vel, fr, fa, wp, hr, tw, wd, es, ss, sa in data:
                station_item = StandardItem("{:.2f}".format(station)) if station is not None else StandardItem("")
                bed_item = StandardItem("{:.2f}".format(bed_elev)) if bed_elev is not None else StandardItem("")
                left_bank_item = StandardItem("{:.2f}".format(left_bank)) if left_bank is not None else StandardItem("")
                right_bank_item = StandardItem("{:.2f}".format(right_bank)) if right_bank is not None else StandardItem(
                    "")
                max_water_item = StandardItem("{:.2f}".format(mw)) if mw is not None else StandardItem("")
                velocity_item = StandardItem("{:.2f}".format(vel)) if vel is not None else StandardItem("")
                froude_item = StandardItem("{:.2f}".format(fr)) if fr is not None else StandardItem("")
                flow_area_item = StandardItem("{:.2f}".format(fa)) if fa is not None else StandardItem("")
                wet_perim_item = StandardItem("{:.2f}".format(wp)) if wp is not None else StandardItem("")
                h_radius_item = StandardItem("{:.2f}".format(hr)) if hr is not None else StandardItem("")
                top_width_item = StandardItem("{:.2f}".format(tw)) if tw is not None else StandardItem("")
                widthdepth_item = StandardItem("{:.2f}".format(wd)) if wd is not None else StandardItem("")
                ener_slo_item = StandardItem("{:.2f}".format(es)) if es is not None else StandardItem("")
                shearstress_item = StandardItem("{:.2f}".format(ss)) if ss is not None else StandardItem("")
                surfacearea_item = StandardItem("{:.2f}".format(sa)) if sa is not None else StandardItem("")
                data_model.appendRow([station_item,
                                      bed_item,
                                      left_bank_item,
                                      right_bank_item,
                                      max_water_item,
                                      velocity_item,
                                      froude_item,
                                      flow_area_item,
                                      wet_perim_item,
                                      h_radius_item,
                                      top_width_item,
                                      widthdepth_item,
                                      ener_slo_item,
                                      shearstress_item,
                                      surfacearea_item,
                                      ])

            self.tview.horizontalHeader().setStretchLastSection(True)
            for col in range(3):
                self.tview.setColumnWidth(col, 100)
            for i in range(data_model.rowCount()):
                self.tview.setRowHeight(i, 20)
            return
        except:
            self.uc.bar_warn("Error while building table for channel!")
            return

    def show_hydrograph(self, table, fid):
        """
        Function to load the hydrograph data from HYCHAN.OUT
        """
        self.uc.clear_bar_messages()
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return False

        units = "CMS" if self.gutils.get_cont_par("METRIC") == "1" else "CFS"

        s = QSettings()
        HYCHAN_file = s.value("FLO-2D/lastHYCHANFile", "")
        GDS_dir = s.value("FLO-2D/lastGdsDir", "")
        # Check if there is an HYCHAN.OUT file on the FLO-2D QSettings
        if not os.path.isfile(HYCHAN_file):
            HYCHAN_file = GDS_dir + r"/HYCHAN.OUT"
            # Check if there is an HYCHAN.OUT file on the export folder
            if not os.path.isfile(HYCHAN_file):
                self.uc.bar_warn(
                    "No HYCHAN.OUT file found. Please ensure the simulation has completed and verify the project export folder.")
                return
        # Check if the HYCHAN.OUT has data on it
        if os.path.getsize(HYCHAN_file) == 0:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("File  '" + os.path.basename(HYCHAN_file) + "'  is empty!")
            return

        xc_fid = str(self.gutils.execute(f"SELECT fid FROM chan_elems WHERE id = '{fid}'").fetchone()[0])
        with open(HYCHAN_file, "r") as myfile:
            time_list = []
            thalweg_list = []
            discharge_list = []
            velocity_list = []
            froude_list = []
            flow_area_list = []
            w_perimeter_list = []
            hyd_radius_list = []
            top_width_list = []
            width_depth_list = []
            energy_slope_list = []
            shear_stress_list = []
            surf_area_list = []
            while True:
                line = next(myfile)
                if "CHANNEL HYDROGRAPH FOR ELEMENT NO:" in line and line.split()[-1] == xc_fid:
                    for _ in range(7):
                        line = next(myfile)
                    while True:
                        line = next(myfile)
                        if not line.strip():  # If the line is empty, exit the loop
                            break
                        line = line.split()
                        time_list.append(float(line[0]))
                        thalweg_list.append(float(line[2]))
                        velocity_list.append(float(line[3]))
                        discharge_list.append(float(line[4]))
                        froude_list.append(float(line[5]))
                        flow_area_list.append(float(line[6]))
                        w_perimeter_list.append(float(line[7]))
                        hyd_radius_list.append(float(line[8]))
                        top_width_list.append(float(line[9]))
                        width_depth_list.append(float(line[10]))
                        energy_slope_list.append(float(line[11]))
                        shear_stress_list.append(float(line[12]))
                        surf_area_list.append(float(line[13]))
                    break

        self.plot.clear()
        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)

        self.plot.plot.legend = None
        self.plot.plot.addLegend(offset=(0, 30))
        self.plot.plot.setTitle(title=f"Cross Section - {xc_fid}")
        self.plot.plot.setLabel("bottom", text="Time (hrs)")
        self.plot.plot.setLabel("left", text="")
        self.plot.add_item(f"Discharge ({self.system_units[units][2]})", [time_list, discharge_list],
                           col=QColor(Qt.darkYellow), sty=Qt.SolidLine)
        self.plot.add_item(f"Thalweg depth ({self.system_units[units][0]})", [time_list, thalweg_list],
                           col=QColor(Qt.black), sty=Qt.SolidLine,
                           hide=True)
        self.plot.add_item(f"Velocity ({self.system_units[units][1]})", [time_list, velocity_list],
                           col=QColor(Qt.darkGreen), sty=Qt.SolidLine,
                           hide=True)
        self.plot.add_item(f"Froude", [time_list, froude_list], col=QColor(Qt.blue), sty=Qt.SolidLine, hide=True)
        self.plot.add_item(f"Flow area ({self.system_units[units][3]})", [time_list, flow_area_list],
                           col=QColor(Qt.red), sty=Qt.SolidLine,
                           hide=True)
        self.plot.add_item(f"Wetted perimeter ({self.system_units[units][0]})", [time_list, w_perimeter_list],
                           col=QColor(Qt.yellow),
                           sty=Qt.SolidLine, hide=True)
        self.plot.add_item(f"Hydraulic radius ({self.system_units[units][0]})", [time_list, hyd_radius_list],
                           col=QColor(Qt.darkBlue),
                           sty=Qt.SolidLine, hide=True)
        self.plot.add_item(f"Top width ({self.system_units[units][0]})", [time_list, top_width_list],
                           col=QColor(Qt.darkRed), sty=Qt.SolidLine,
                           hide=True)
        self.plot.add_item(f"Width/Depth", [time_list, width_depth_list], col=QColor(Qt.darkCyan), sty=Qt.SolidLine,
                           hide=True)
        self.plot.add_item(f"Energy slope", [time_list, energy_slope_list], col=QColor(Qt.magenta), sty=Qt.SolidLine,
                           hide=True)
        self.plot.add_item(f"Shear stress ({self.system_units[units][4]})", [time_list, shear_stress_list],
                           col=QColor(Qt.darkYellow),
                           hide=True)
        self.plot.add_item(f"Surface Area ({self.system_units[units][3]})", [time_list, surf_area_list],
                           col=QColor(Qt.darkMagenta), hide=True)

        try:  # Build table.
            data_model = StandardItemModel()
            self.tview.undoStack.clear()
            self.tview.setModel(data_model)
            data_model.clear()
            data_model.setHorizontalHeaderLabels(["Time (hours)",
                                                  f"Thalweg depth ({self.system_units[units][0]})",
                                                  f"Velocity ({self.system_units[units][1]})",
                                                  f"Discharge ({self.system_units[units][2]})",
                                                  f"Froude",
                                                  f"Flow area ({self.system_units[units][2]})",
                                                  f"Wetted perimeter ({self.system_units[units][0]})",
                                                  f"Hydraulic radius ({self.system_units[units][0]})",
                                                  f"Top width ({self.system_units[units][0]})",
                                                  f"Width/Depth",
                                                  f"Energy slope",
                                                  f"Shear stress ({self.system_units[units][4]})",
                                                  f"Surface Area ({self.system_units[units][3]})",
                                                  ])

            data = zip(time_list,
                       thalweg_list,
                       velocity_list,
                       discharge_list,
                       froude_list,
                       flow_area_list,
                       w_perimeter_list,
                       hyd_radius_list,
                       top_width_list,
                       width_depth_list,
                       energy_slope_list,
                       shear_stress_list,
                       surf_area_list)

            for time, thalweg, velocity, discharge, froude, flow_area, w_perimeter, hyd_radius, top_width, width_depth, energy_slope, shear_stress, surf_area in data:
                time_item = StandardItem("{:.2f}".format(time)) if time is not None else StandardItem("")
                thalweg_item = StandardItem("{:.2f}".format(thalweg)) if thalweg is not None else StandardItem("")
                velocity_item = StandardItem("{:.2f}".format(velocity)) if velocity is not None else StandardItem("")
                discharge_item = StandardItem("{:.2f}".format(discharge)) if discharge is not None else StandardItem("")
                froude_item = StandardItem("{:.2f}".format(froude)) if froude is not None else StandardItem("")
                flow_area_item = StandardItem("{:.2f}".format(flow_area)) if flow_area is not None else StandardItem("")
                w_perimeter_item = StandardItem("{:.2f}".format(w_perimeter)) if w_perimeter is not None else StandardItem("")
                hyd_radius_item = StandardItem("{:.2f}".format(hyd_radius)) if hyd_radius is not None else StandardItem("")
                top_width_item = StandardItem("{:.2f}".format(top_width)) if top_width is not None else StandardItem("")
                width_depth_item = StandardItem("{:.2f}".format(width_depth)) if width_depth is not None else StandardItem("")
                energy_slope_item = StandardItem("{:.2f}".format(energy_slope)) if energy_slope is not None else StandardItem("")
                shear_stress_item = StandardItem("{:.2f}".format(shear_stress)) if shear_stress is not None else StandardItem("")
                surf_area_item = StandardItem("{:.2f}".format(surf_area)) if surf_area is not None else StandardItem("")


                data_model.appendRow([time_item,
                                      thalweg_item,
                                      velocity_item,
                                      discharge_item,
                                      froude_item,
                                      flow_area_item,
                                      w_perimeter_item,
                                      hyd_radius_item,
                                      top_width_item,
                                      width_depth_item,
                                      energy_slope_item,
                                      shear_stress_item,
                                      surf_area_item])

            self.tview.horizontalHeader().setStretchLastSection(True)
            for col in range(3):
                self.tview.setColumnWidth(col, 100)
            for i in range(data_model.rowCount()):
                self.tview.setRowHeight(i, 20)
            return
        except:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("Error while building table for hydraulic structure discharge!")
            return

    def reassign_xs_rightbanks_grid_id_from_schematized_rbanks(self, xs_seg_fid, right_bank_fid):
        """Takes all schematized left bank cross sections (from 'cham_elems' layer) identified by 'xs_seg_fid', and
        changes
        1) their end point to a centroid (see below) of the schematized right bank identified by 'right_bank_fid'and,
        2) their ´rbank´ field (a cell number) to the schematized right bank identified by 'right_bank_fid'.

        Centroids belong to the points of a polyline defined by the ´right_bank_fid' feature. They are taken in order using
        an iterator, from the first to the last.

        """
        try:
            new_feats = []
            xs_lyr = self.lyrs.data["chan_elems"]["qlyr"]
            rbank = self.lyrs.data["rbank"]["qlyr"]
            rbank_feats = iter(rbank.getFeatures())

            while True:
                # Find if there is a schematized right bank with 'fid' equal to 'right_bank_fid'.
                # Otherwise do nothing, and return.
                r = next(rbank_feats, None)
                if r is None:
                    return
                elif r["fid"] == right_bank_fid:
                    break

            r_poly = (
                r.geometry().asPolyline()
            )  # Polyline of schematized right bank identified by right_bank_fid: list of pairs (x,y) of its points.
            r_points = iter(r_poly)

            # Create a list of features taken from cham_elems layer (schematized cross sections), modifying their geometry
            # by changing the point of the coordinates of the right bank cell:
            for xs_f in xs_lyr.getFeatures():
                if not xs_f["seg_fid"] == xs_seg_fid:
                    continue
                # xs_f is the next schematized cross section (a single line) identified by xs_seg_fid (from cham_elems layer):
                # All xs with id xs_seg_fid belong to the same left bank.
                xs_feat = QgsFeature()
                xs_feat = xs_f  # Copy schematized polyline with id xs_seg_fid.
                left = str(xs_f["fid"])  # Cell number of start of this xs.
                pnt0 = self.gutils.single_centroid(left)  # Center point of cell 'left'.
                qgsPoint0 = QgsGeometry().fromWkt(pnt0).asPoint()
                qgsPoint1 = next(r_points, None)  # Get next point of schematized right bank 'right_bank_fid'.
                if qgsPoint1 is None:
                    break
                else:
                    right = self.gutils.grid_on_point(
                        qgsPoint1.x(), qgsPoint1.y()
                    )  # Get cell number of next schematized right bank cell.
                    new_xs = QgsGeometry.fromPolylineXY(
                        [qgsPoint0, qgsPoint1]
                    )  # Define line  between left bank and right bank.
                    xs_feat.setGeometry(new_xs)  # Assign new line geometry to current xs.
                    xs_feat.setAttribute("rbankgrid", right)  # Assign new cell id for right bank cell of current xs.

                    new_feats.append(xs_feat)

            # Replace all features of chan_elems with the new calculated features:
            xs_lyr.startEditing()
            for feat in xs_lyr.getFeatures():
                if feat["seg_fid"] == xs_seg_fid:
                    xs_lyr.deleteFeature(feat.id())
            for feat in new_feats:
                xs_lyr.addFeature(feat)
            xs_lyr.commitChanges()
            xs_lyr.updateExtents()
            xs_lyr.triggerRepaint()
            xs_lyr.removeSelection()

            # self.gutils.create_schematized_rbank_lines_from_xs_tips()
            # rbank.updateExtents()
            # rbank.triggerRepaint()
            # rbank.removeSelection()

        except Exception as e:
            self.uc.show_error("ERROR 240718.0359: Couldn't join left and right banks!", e)

    def interpolate_channel_n(self):
        if sys.platform != "win32":
            self.uc.bar_warn("Could not run 'CHAN N-VALUE INTERPOLATOR.EXE' under current operation system!")
            return
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        # dlg = ExternalProgramFLO2D(self.iface, "Run interpolation of channel n-values")
        # dlg.debug_run_btn.setVisible(False)
        # dlg.exec_folder_lbl.setText("FLO-2D Folder (of interpolation executable)")
        # ok = dlg.exec_()
        # if not ok:
        #     return
        s = QSettings()
        flo2d_dir = s.value("FLO-2D/last_flopro", "")
        project_dir = s.value("FLO-2D/lastGdsDir", "")
        outdir = project_dir + "/temp/"
        self.f2g = Flo2dGeoPackage(self.con, self.iface)
        if not os.path.exists(outdir):
            os.mkdir(outdir)
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            # Export CONT, TOPO, CHAN and XSEC to temp folder
            self.f2g.export_cont_toler_dat(outdir)
            self.f2g.export_mannings_n_topo_dat(outdir)
            self.f2g.export_chan(outdir)
            self.f2g.export_xsec(outdir)

            # Run the interpolator
            channelNInterpolator = ChannelNInterpolatorExecutor(flo2d_dir, outdir)
            return_code = channelNInterpolator.run()

            if return_code == 0:
                QApplication.restoreOverrideCursor()

                # Import back
                for root, dirs, files in os.walk(outdir):
                    if "fort.4" in files:
                        fort_path = os.path.join(root, "fort.4")
                        chanfile = os.path.join(outdir, "CHAN.DAT")

                        # If CHAN.DAT already exists, remove it
                        if os.path.exists(chanfile):
                            os.remove(chanfile)

                        # Rename fort.4 to CHAN.DAT
                        os.rename(fort_path, chanfile)
                        break  # Found "fort.4" and renamed it, no need to continue searching

                self.import_chan(temp=outdir)

                # Delete the temp folder
                shutil.rmtree(outdir)

                self.uc.bar_info("Channel n-values interpolated into CHAN.DAT file!\n\n")

            elif return_code == -999:
                QApplication.restoreOverrideCursor()
                self.uc.show_warn(
                    "WARNING 060319.1758: Interpolation of channel n-values could not be performed!\n\n"
                    + "File\n\n"
                    + os.path.join(project_dir, "CHAN.DAT\n\n")
                    + "doesn't exist."
                )
            else:
                QApplication.restoreOverrideCursor()
                self.uc.show_warn(
                    "WARNING 060319.1759: Interpolation of channel n-values failed!\n\n"
                    + "Program finished with return code "
                    + str(return_code)
                    + "."
                    + "\n\nCheck content and format of file\n\n"
                    + os.path.join(project_dir, "CHAN.DAT")
                )

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(repr(e))
            self.uc.show_error(
                "ERROR 060319.1631: Interpolation of channel n-values failed!\n"
                "\n_________________________________________________",
                e,
            )

    def schematize_confluences(self):
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("WARNING 060319.1801: There is no grid! Please create it before running tool.")
            return
        if self.gutils.is_table_empty("user_left_bank"):
            self.uc.bar_warn(
                "WARNING 060319.1802: There are no any user left bank lines! Please digitize them before running the tool."
            )
            return
        if self.gutils.is_table_empty("user_xsections"):
            self.uc.bar_warn(
                "WARNING 060319.1803: There are no any user cross sections! Please digitize them before running the tool."
            )
            return
        try:
            conf = Confluences(self.con, self.iface, self.lyrs)
            conf.calculate_confluences()
            chan_schem = self.lyrs.data["chan"]["qlyr"]
            chan_elems = self.lyrs.data["chan_elems"]["qlyr"]
            rbank = self.lyrs.data["rbank"]["qlyr"]
            confluences = self.lyrs.data["chan_confluences"]["qlyr"]
            self.lyrs.lyrs_to_repaint = [chan_schem, chan_elems, rbank, confluences]
            self.lyrs.repaint_layers()
            self.uc.show_info("Confluences schematized!")
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn("WARNING 060319.1804: Schematizing aborted! Please check your 1D User Layers.")

    def create_confluences(self):
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("WARNING 160821.0930: There is no grid! Please create it before running tool.")
            return
        if self.gutils.is_table_empty("chan_elems"):
            self.uc.bar_warn("WARNING 160821.0931: There are no schematized channel cross sections.")
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            grid_lyr = self.lyrs.data["grid"]["qlyr"]
            cell_size = float(self.gutils.get_cont_par("CELLSIZE"))
            xs_lyr = self.lyrs.data["chan_elems"]["qlyr"]
            xs = xs_lyr.getFeatures()
            segments = {}
            for feat in xs:
                segments[feat["seg_fid"]] = [feat["fid"]]
            lastCellInSegments = segments.items()
            confluences = dict(segments)
            for key, last in lastCellInSegments:
                # Find adjacent cells to 'last' cell in others segments:
                lastCell = next(grid_lyr.getFeatures(QgsFeatureRequest(last)))
                (
                    n_grid,
                    ne_grid,
                    e_grid,
                    se_grid,
                    s_grid,
                    sw_grid,
                    w_grid,
                    nw_grid,
                ) = adjacent_grids(self.gutils, lastCell, cell_size)
                if n_grid:
                    lst = list(segments[key])
                    lst.append(n_grid)
                    segments[key] = lst
                    pass
                if ne_grid:
                    lst = list(segments[key])
                    lst.append(ne_grid)
                    segments[key] = lst
                    pass
                if e_grid:
                    lst = list(segments[key])
                    lst.append(e_grid)
                    segments[key] = lst
                    pass
                if se_grid:
                    lst = list(segments[key])
                    lst.append(se_grid)
                    segments[key] = lst
                    pass
                if s_grid:
                    lst = list(segments[key])
                    lst.append(s_grid)
                    segments[key] = lst
                    pass
                if sw_grid:
                    lst = list(segments[key])
                    lst.append(sw_grid)
                    segments[key] = lst
                    pass
                if w_grid:
                    lst = list(segments[key])
                    lst.append(w_grid)
                    segments[key] = lst
                    pass
                if nw_grid:
                    lst = list(segments[key])
                    lst.append(nw_grid)
                    segments[key] = lst
                    pass

            for key, values in segments.items():
                xs2 = xs_lyr.getFeatures()
                for f in xs2:
                    if f["seg_fid"] != key:
                        if f["fid"] in values[1:]:
                            lst = list(confluences[key])
                            if f["fid"] not in lst:
                                lst.append(f["fid"])
                                confluences[key] = lst
                        if f["rbankgrid"] in values[1:]:
                            lst = list(confluences[key])
                            if f["rbankgrid"] not in lst:
                                lst.append(f["rbankgrid"])
                                confluences[key] = lst
            QApplication.restoreOverrideCursor()

            dlg_tributaries = TributariesDialog(self.iface, self.lyrs, confluences)
            save = dlg_tributaries.exec_()
            if save:
                dlg_tributaries.save()

            dlg_tributaries.clear_confluences_rubber()

            self.lyrs.data["chan_confluences"]["qlyr"].triggerRepaint()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(traceback.format_exc())
            self.uc.show_error("ERROR 160921.0937: Creation of confluences aborted!\n,", e)

    def delete_confluences(self):
        """
        Function to delete confluences
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("WARNING 160821.0930: There is no grid! Please create it before running tool.")
            return
        if self.gutils.is_table_empty("chan_elems"):
            self.uc.bar_warn("WARNING 160821.0931: There are no schematized channel cross sections.")
            return

        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.gutils.clear_tables("chan_confluences")
            self.lyrs.data["chan_confluences"]["qlyr"].triggerRepaint()
            self.uc.bar_info("Confluences deleted!")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(repr(e))
            self.uc.show_error("Delete Confluences Error!", e)

    def effective_user_cross_section(self, fid, name):
        """Return the cross section split between banks"""

        user_xs_lyr = self.lyrs.data["user_xsections"]["qlyr"]
        try:
            feat = next(user_xs_lyr.getFeatures(QgsFeatureRequest(fid)))
        except StopIteration:
            self.uc.show_warn("WARNING 060319.XXX: Cross section " + str(name) + " has not geometry.")
            return

        # split the cross section between banks lines
        xs_geometry = feat.geometry()
        user_left_bank_layer = self.lyrs.data["user_left_bank"]["qlyr"]
        left_bank_intersect = False
        for left_bank_feature in user_left_bank_layer.getFeatures():
            if left_bank_feature.geometry().intersects(xs_geometry):
                left_bank_intersect = True
                break

        if not left_bank_intersect:
            self.uc.show_warn(
                "WARNING 060319.XXX: Cross section " + str(name) + " does not intersect with any left bank"
            )
            return

        intersects = xs_geometry.intersection(left_bank_feature.geometry())
        if intersects.wkbType == QgsWkbTypes.MultiPoint:
            multi_point = intersects.asMultiPoint()
            intersect_point = multi_point[0]
        else:
            intersect_point = intersects.asPoint()

        (
            dist,
            left_intersect_point,
            left_after_vertex_index,
            side,
        ) = xs_geometry.closestSegmentWithContext(QgsPointXY(intersect_point))

        user_right_bank_layer = self.lyrs.data["user_right_bank"]["qlyr"]
        right_bank_intersect = False
        for right_bank_feature in user_right_bank_layer.getFeatures():
            if right_bank_feature.geometry().intersects(xs_geometry):
                right_bank_intersect = True
                break

        xs_polyline = xs_geometry.asPolyline()
        right_after_vertex_index = len(xs_polyline) - 1

        if right_bank_intersect:
            intersects = xs_geometry.intersection(right_bank_feature.geometry())
            if intersects.wkbType == QgsWkbTypes.MultiPoint:
                multi_point = intersects.asMultiPoint()
                intersect_point = multi_point[0]
            else:
                intersect_point = intersects.asPoint()

            (
                dist,
                right_intersect_point,
                right_after_vertex_index,
                side,
            ) = xs_geometry.closestSegmentWithContext(QgsPointXY(intersect_point))

            last_vertex = right_intersect_point
        else:
            last_vertex = xs_polyline[-1]

        xs_effective_cross_section = [left_intersect_point]
        for i in range(left_after_vertex_index, right_after_vertex_index):
            xs_effective_cross_section.append(xs_polyline[i])
        xs_effective_cross_section.append(last_vertex)

        return xs_effective_cross_section

    def sample_bank_elevation_all_RTV_cross_sections(self):
        if not self.uc.question(
                "After this action, all bank elevations from cross sections R, T and V will be lost.\n"
                "Do you want to proceed?"
        ):
            return

        request = QgsFeatureRequest()
        features = self.user_xs_lyr.getFeatures(request)
        while True:
            try:
                feat = next(features)
                self.sample_bank_elevation_cross_section(feat.attribute("fid"))
            except StopIteration:
                return

    def sample_bank_elevation_current_RTV_cross_sections(self):
        if not self.uc.question(
                "After this action, bank elevations from current cross sections will be lost.\n" "Do you want to proceed?"
        ):
            return

        fid = int(self.xs_cbo.currentData())
        self.sample_bank_elevation_cross_section(fid)

    def sample_bank_elevation_cross_section(self, fid):
        xs = UserCrossSection(fid, self.con, self.iface)
        xs.get_row()
        if xs.type == "N":
            return

        effective_cross_section = self.effective_user_cross_section(xs.fid, xs.name)

        if self.raster_radio_btn.isChecked():
            raster_layer = self.raster_combobox.currentLayer()
            if raster_layer is None:
                return
            transform = QgsCoordinateTransform(self.user_xs_lyr.crs(), raster_layer.crs(), QgsProject.instance())
            xs.sample_bank_elevation_from_raster_layer(raster_layer, effective_cross_section, transform)
        else:
            grid_layer = self.lyrs.data["grid"]["qlyr"]
            xs.sample_bank_elevation_from_grid(effective_cross_section, grid_layer)

        self.update_table()
        self.create_plot()
        self.update_plot()

    def sample_elevation_all_natural_cross_sections(self):
        if not self.uc.question(
                "After this action, all current natural cross section profiles will be lost.\n" "Do you want to proceed?"
        ):
            return
        request = QgsFeatureRequest()
        request.setFilterExpression("\"type\"='N'")
        features = self.user_xs_lyr.getFeatures(request)
        while True:
            try:
                feat = next(features)
                self.sample_elevation_natural_cross_section(feat.attribute("fid"))
            except StopIteration:
                return

    def sample_elevation_current_natural_cross_sections(self):
        if not self.uc.question(
                "After this action, current natural cross section profile will be lost.\n" "Do you want to proceed?"
        ):
            return
        fid = int(self.xs_cbo.currentData())
        self.sample_elevation_natural_cross_section(fid)

    def sample_elevation_natural_cross_section(self, fid):
        raster_layer = self.raster_combobox.currentLayer()

        if raster_layer is None:
            return

        xs = UserCrossSection(fid, self.con, self.iface)
        xs.get_row()
        if xs.type != "N":
            return

        transform = QgsCoordinateTransform(self.user_xs_lyr.crs(), raster_layer.crs(), QgsProject.instance())
        xs.sample_elevation_from_raster_layer(
            raster_layer, self.effective_user_cross_section(xs.fid, xs.name), transform
        )
        self.update_table()
        self.create_plot()
        self.update_plot()
