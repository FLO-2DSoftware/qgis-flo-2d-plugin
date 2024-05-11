# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import shutil
import traceback
from _ast import Pass
from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from math import floor, isnan, modf
from pathlib import Path

import h5py
import numpy as np
from qgis._core import QgsFeatureRequest
from qgis.core import (
    NULL,
    QgsArrowSymbolLayer,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsFillSymbol,
    QgsGeometry,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPointXY,
    QgsProject,
    QgsSingleSymbolRenderer,
    QgsSymbolLayerRegistry,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
    QgsMessageLog,
    Qgis,
    QgsUnitTypes,
)
from qgis.PyQt import QtCore, QtGui
from qgis.PyQt.QtCore import QSettings, Qt, QTime, QVariant, pyqtSignal, QUrl
from qgis.PyQt.QtGui import QColor, QIcon, QDesktopServices
from qgis.PyQt.QtWidgets import (
    QApplication,
    QCheckBox,
    QRadioButton,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QAction,
    QMenu,
    QToolButton,
    qApp,
    QDialogButtonBox,
)

import pyqtgraph as pg

from .dlg_sd_profile_view import SDProfileView
from ..flo2d_ie.flo2dgeopackage import Flo2dGeoPackage
from ..flo2d_ie.swmm_io import StormDrainProject
from ..flo2d_tools.grid_tools import spatial_index
from ..flo2d_tools.schema2user_tools import remove_features
from ..flo2dobjects import InletRatingTable, PumpCurves
from ..geopackage_utils import GeoPackageUtils
from ..gui.dlg_conduits import ConduitsDialog
from ..gui.dlg_inlets import InletNodesDialog
from ..gui.dlg_storage_units import StorageUnitsDialog
from ..gui.dlg_orifices import OrificesDialog
from ..gui.dlg_outfalls import OutfallNodesDialog
from ..gui.dlg_pumps import PumpsDialog
from ..gui.dlg_stormdrain_shapefile import StormDrainShapefile
from ..gui.dlg_weirs import WeirsDialog
from ..user_communication import ScrollMessageBox, ScrollMessageBox2, UserCommunication,TwoInputsDialog
from ..utils import float_or_zero, int_or_zero, is_number, is_true, m_fdata
from .table_editor_widget import CommandItemEdit, StandardItem, StandardItemModel
from .ui_utils import load_ui, set_icon, try_disconnect, center_canvas
from ..flo2d_ie.flo2d_parser import ParseDAT

uiDialog, qtBaseClass = load_ui("inp_groups")


class INP_GroupsDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.con = con
        self.iface = iface
        self.setupUi(self)
        self.gutils = GeoPackageUtils(con, iface)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.polulate_INP_values()

    def polulate_INP_values(self):
        try:
            today = date.today()
            simul_time = float(self.gutils.get_cont_par("SIMUL"))
            frac, whole = modf(simul_time / 24)
            frac, whole = modf(frac * 24)
            unit = int(self.gutils.get_cont_par("METRIC"))
            # [OPTIONS]:
            self.flow_units_cbo.setCurrentIndex(unit)
            self.start_date.setDate(today)
            self.report_start_date.setDate(today)
            self.end_date.setDate(today + timedelta(hours=simul_time))
            self.end_time.setTime(time(int(whole), int(frac * 60)))

            tout = float(self.gutils.get_cont_par("TOUT"))

            mins, hours = modf(tout)
            hours = int(hours)
            mins = int(mins * 60)

            time_string = timedelta(hours=tout)

            t = QTime(hours, mins)
            self.report_stp_time.setTime(t)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 310818.0824: error populating export storm drain INP dialog."
                + "\n__________________________________________________",
                e,
            )


uiDialog, qtBaseClass = load_ui("storm_drain_editor")


class StormDrainEditorWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.plot = plot
        self.SD_table = table
        self.tview = table.tview
        self.lyrs = lyrs
        self.con = None
        self.gutils = None

        self.system_units = {
            "CMS": ["m", "mps", "cms"],
            "CFS": ["ft", "fps", "cfs"]
             }

        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")

        self.inlet_data_model = StandardItemModel()
        self.tview.setModel(self.inlet_data_model)
        self.pumps_data_model = StandardItemModel()

        # self.rt_tview.setModel(self.inlet_data_model)
        # self.pump_tview.setModel(self.pumps_data_model)

        self.grid_lyr = None
        self.user_swmm_nodes_lyr = None
        self.user_swmm_storage_units_lyr = None
        self.user_swmm_conduits_lyr = None
        self.user_swmm_pumps_lyr = None
        self.swmm_pumps_curve_data_lyr = None
        self.swmm_tidal_curve_lyr = None
        self.swmm_tidal_curve_data_lyr = None
        self.swmm_other_curves_lyr = None
        self.swmm_inflows_lyr = None
        self.swmm_inflow_patterns_lyr = None
        self.swmm_time_series_lyr = None
        self.swmm_time_series_data_lyr = None
        self.control_lyr = None
        self.schema_inlets = None
        self.schema_outlets = None
        self.all_schema = []
        self.swmm_idx = 0
        self.INP_groups = OrderedDict()  # ".INP_groups" will contain all groups [xxxx] in .INP file,
        # ordered as entered.
        self.swmm_columns = [
            "sd_type",
            "intype",
            "swmm_length",
            "swmm_width",
            "swmm_height",
            "swmm_coeff",
            "flapgate",
            "curbheight",
            "max_depth",
            "invert_elev",
            "rt_fid",
            "outf_flo",
        ]

        self.inlet_columns = [
            "intype",
            "swmm_length",
            "swmm_width",
            "swmm_height",
            "swmm_coeff",
            "swmm_feature",
            "flapgate",
            "curbheight",
        ]
        self.outlet_columns = ["swmm_allow_discharge"]

        self.other_curve_types = ["Control", "Diversion", "Rating", "Shape", "Storage"]
        self.all_nodes = None
        self.inletRT = None
        self.plot_item_name = None
        self.inlet_series_data = None
        self.PumpCurv = None
        self.curve_data = None
        self.d1, self.d2, self.d3 = [[], [], []]
        self.auto_assign_msg = ""
        self.no_nodes = ""
        self.inlet_not_found = []
        self.outlet_not_found = []
        self.buffer_distance = 5

        # set_icon(self.create_point_btn, "mActionCapturePoint.svg")
        # set_icon(self.save_changes_btn, "mActionSaveAllEdits.svg")
        # set_icon(self.revert_changes_btn, "mActionUndo.svg")
        # set_icon(self.sd_delete_btn, "mActionDeleteSelected.svg")
        set_icon(self.schema_storm_drain_btn, "schematize_res.svg")
        set_icon(self.sd_help_btn, "help.svg")

        set_icon(self.SD_show_type4_btn, "show_cont_table.svg")
        set_icon(self.SD_add_one_type4_btn, "add_table_data.svg")
        set_icon(self.SD_add_predefined_type4_btn, "mActionOpenFile.svg")
        set_icon(self.SD_remove_type4_btn, "mActionDeleteSelected.svg")
        set_icon(self.SD_rename_type4_btn, "change_name.svg")
        
        set_icon(self.show_pump_table_btn, "show_cont_table.svg")
        set_icon(self.add_pump_curve_btn, "add_table_data.svg")
        set_icon(self.add_predefined_pump_curve_btn, "mActionOpenFile.svg")
        set_icon(self.remove_pump_curve_btn, "mActionDeleteSelected.svg")
        set_icon(self.rename_pump_curve_btn, "change_name.svg")

        # Add submenus to 'Add inlet type 4 data' (SD_add_one_type4_btn) button:
        menu = QMenu()
        action1 = QAction("Add Rating Table", self)
        action1.setStatusTip("Add inlet type 4 rating table")
        action1.setIcon(QIcon(os.path.join(self.plugin_dir, "img/add_table_data.svg")))
        action2 = QAction("Add Culvert Equation", self)
        action1.setStatusTip("Add inlet type 4 Culvert equation")
        action1.setIcon(QIcon(os.path.join(self.plugin_dir, "img/add_table_data.svg"))) 
        menu.addAction(action1)
        menu.addAction(action2)
        menu.triggered.connect(lambda action: self.add_type4_data(action.text()))
        self.SD_add_one_type4_btn.setMenu(menu)
        self.SD_add_one_type4_btn.setPopupMode(QToolButton.InstantPopup)

        self.grid_lyr = self.lyrs.data["grid"]["qlyr"]
        self.user_swmm_nodes_lyr = self.lyrs.data["user_swmm_nodes"]["qlyr"]
        self.user_swmm_storage_units_lyr = self.lyrs.data["user_swmm_storage_units"]["qlyr"]
        self.user_swmm_conduits_lyr = self.lyrs.data["user_swmm_conduits"]["qlyr"]
        self.user_swmm_pumps_lyr = self.lyrs.data["user_swmm_pumps"]["qlyr"]
        self.user_swmm_orifices_lyr = self.lyrs.data["user_swmm_orifices"]["qlyr"]
        self.user_swmm_weirs_lyr = self.lyrs.data["user_swmm_weirs"]["qlyr"]
        self.swmm_pumps_curve_data_lyr = self.lyrs.data["swmm_pumps_curve_data"]["qlyr"]
        self.swmm_tidal_curve_lyr = self.lyrs.data["swmm_tidal_curve"]["qlyr"]
        self.swmm_other_curves_lyr = self.lyrs.data["swmm_other_curves"]["qlyr"]
        self.swmm_tidal_curve_data_lyr = self.lyrs.data["swmm_tidal_curve_data"]["qlyr"]
        self.swmm_inflows_lyr = self.lyrs.data["swmm_inflows"]["qlyr"]
        self.swmm_inflow_patterns_lyr = self.lyrs.data["swmm_inflow_patterns"]["qlyr"]
        self.swmm_time_series_lyr = self.lyrs.data["swmm_time_series"]["qlyr"]
        self.swmm_time_series_data_lyr = self.lyrs.data["swmm_time_series_data"]["qlyr"]
        self.control_lyr = self.lyrs.data["cont"]["qlyr"]
        self.schema_inlets = self.lyrs.data["swmmflo"]["qlyr"]
        self.schema_outlets = self.lyrs.data["swmmoutf"]["qlyr"]
        self.all_schema += [self.schema_inlets, self.schema_outlets]

        self.setup_connection()

        self.inletRT = InletRatingTable(self.con, self.iface)
        self.PumpCurv = PumpCurves(self.con, self.iface)

        self.schema_storm_drain_btn.clicked.connect(self.schematize_swmm)
        self.sd_help_btn.clicked.connect(self.sd_help)

        self.SD_show_type4_btn.clicked.connect(self.SD_show_type4_table_and_plot)
        self.SD_add_predefined_type4_btn.clicked.connect(self.SD_import_type4)
        self.SD_remove_type4_btn.clicked.connect(self.SD_delete_type4)
        self.SD_rename_type4_btn.clicked.connect(self.SD_rename_type4)

        self.show_pump_table_btn.clicked.connect(self.show_pump_curve_table_and_plot)
        self.add_pump_curve_btn.clicked.connect(self.add_one_pump_curve)
        self.add_predefined_pump_curve_btn.clicked.connect(self.SD_import_pump_curves)
        self.remove_pump_curve_btn.clicked.connect(self.delete_pump_curve)
        self.rename_pump_curve_btn.clicked.connect(self.rename_pump_curve)

        self.inlet_data_model.itemDataChanged.connect(self.itemDataChangedSlot)
        self.inlet_data_model.dataChanged.connect(self.save_SD_table_data)

        self.SD_table.before_paste.connect(self.block_saving)
        self.SD_table.after_paste.connect(self.unblock_saving)
        self.SD_table.after_delete.connect(self.save_SD_table_data)

        self.pumps_data_model.itemDataChanged.connect(self.itemDataChangedSlot)
        self.pumps_data_model.dataChanged.connect(self.save_SD_table_data)

        self.pump_curve_type_cbo.currentIndexChanged.connect(self.update_pump_curve_data)
        self.pump_curve_description_le.textChanged.connect(self.update_pump_curve_data)
               
        self.pump_curve_cbo.activated.connect(self.current_cbo_pump_curve_index_changed)
        self.pump_curve_cbo.currentIndexChanged.connect(self.refresh_PC_PlotAndTable)

        self.simulate_stormdrain_chbox.clicked.connect(self.simulate_stormdrain)
        self.import_shapefile_btn.clicked.connect(self.import_hydraulics)

        self.SD_type4_cbo.activated.connect(self.SD_show_type4_table_and_plot)

        self.SD_nodes_components_cbo.currentIndexChanged.connect(self.nodes_component_changed)
        self.SD_links_components_cbo.currentIndexChanged.connect(self.links_component_changed)
        self.auto_assign_link_nodes_btn.clicked.connect(self.auto_assign)
        
        self.populate_type4_combo()
        self.populate_pump_curves_and_data()
        self.show_pump_curve_type_and_description()

        self.populate_profile_plot()
        self.find_profile_btn.clicked.connect(self.show_profile)
        self.start_node_cbo.currentIndexChanged.connect(lambda: self.center_node("Start"))
        self.end_node_cbo.currentIndexChanged.connect(lambda: self.center_node("End"))
        self.center_chbox.clicked.connect(self.clear_sd_rubber)

        swmm = 1 if self.gutils.get_cont_par("SWMM") == "1" else 0
        self.simulate_stormdrain_chbox.setChecked(swmm)

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

            self.control_lyr.editingStopped.connect(self.check_simulate_SD_1)

    def split_INP_into_groups_dictionary_by_tags_to_export(self, inp_file):
        """
        Creates an ordered dictionary INP_groups with all groups in [xxxx] .INP file.

        At the end, INP_groups will be a dictionary of lists of strings, with keys like
            ...
            SUBCATCHMENTS
            SUBAREAS
            INFILTRATION
            JUNCTIONS
            OUTFALLS
            CONDUITS
            etc.

        """
        INP_groups = OrderedDict()  # ".INP_groups" will contain all groups [xxxx] in .INP file,
        # ordered as entered.

        with open(inp_file) as swmm_inp:  # open(file, mode='r',...) defaults to mode 'r' read.
            for chunk in swmm_inp.read().split(
                "["
            ):  #  chunk gets all text (including newlines) until next '[' (may be empty)
                try:
                    key, value = chunk.split("]")  # divide chunk into:
                    # key = name of group (e.g. JUNCTIONS) and
                    # value = rest of text until ']'
                    INP_groups[key] = value.split(
                        "\n"
                    )  # add new item {key, value.split('\n')} to dictionary INP_groups.
                    # E.g.:
                    #   key:
                    #     JUNCTIONS
                    #   value.split('\n') is list of strings:
                    #    I1  4685.00    6.00000    0.00       0.00       0.00
                    #    I2  4684.95    6.00000    0.00       0.00       0.00
                    #    I3  4688.87    6.00000    0.00       0.00       0.00
                except ValueError:
                    continue

            return INP_groups

    def select_this_INP_group(self, INP_groups, chars):
        """Returns the whole .INP group [´chars'xxx]

        ´chars' is the  beginning of the string. Only the first 4 or 5 lower case letters are used in all calls.
        Returns a list of strings of the whole group, one list item for each line of the original .INP file.

        """
        part = None
        if INP_groups is None:
            return part
        else:
            for tag in list(INP_groups.keys()):
                low_tag = tag.lower()
                if low_tag.startswith(chars):
                    part = INP_groups[tag]
                    break
                else:
                    continue
            return (
                part  # List of strings in .INT_groups dictionary item keyed by 'chars' (e.e.´junc', 'cond', 'outf',...)
            )

    def repaint_schema(self):
        for lyr in self.all_schema:
            lyr.triggerRepaint()

    def create_swmm_point(self):
        self.uc.clear_bar_messages()

        if self.gutils.is_table_empty("user_model_boundary"):
            self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
            return
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        if not self.lyrs.enter_edit_mode("user_swmm_nodes"):
            return

    def save_swmm_edits(self):
        self.uc.clear_bar_messages()

        if self.gutils.is_table_empty("user_model_boundary"):
            self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
            return
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        before = self.gutils.count("user_swmm_nodes")
        self.lyrs.save_lyrs_edits("user_swmm_nodes")
        after = self.gutils.count("user_swmm_nodes")

    #         if after > before:
    #             self.swmm_idx = after - 1
    #         elif self.swmm_idx >= 0:
    #             self.save_attrs()
    #         else:
    #             return
    #         self.populate_swmm()

    def revert_swmm_lyr_edits(self):
        user_swmm_nodes_edited = self.lyrs.rollback_lyrs_edits("user_swmm_nodes")
        # if user_swmm_nodes_edited:
        #     self.populate_swmm()

    def delete_cur_swmm(self):
        if not self.swmm_name_cbo.count():
            return
        q = "Are you sure, you want delete the current Storm Drain point?"
        if not self.uc.question(q):
            return
        swmm_fid = self.swmm_name_cbo.itemData(self.swmm_idx)["fid"]
        self.gutils.execute("DELETE FROM user_swmm_nodes WHERE fid = ?;", (swmm_fid,))
        self.swmm_lyr.triggerRepaint()
        # self.populate_swmm()
    
    def sd_help(self):
        QDesktopServices.openUrl(QUrl("https://flo-2dsoftware.github.io/FLO-2D-Documentation/Plugin1000/widgets/storm-drain-editor/index.html"))        

    def save_attrs(self):
        swmm_dict = self.swmm_name_cbo.itemData(self.swmm_idx)
        fid = swmm_dict["fid"]
        name = self.swmm_name_cbo.currentText()
        swmm_dict["name"] = name
        if self.inlet_grp.isChecked():
            swmm_dict["sd_type"] = "I"
            grp = self.inlet_grp
        elif self.outlet_grp.isChecked():
            swmm_dict["sd_type"] = "O"
            grp = self.outlet_grp
        else:
            return
        for obj in self.flatten(grp):
            obj_name = obj.objectName().split("_", 1)[-1]
            if isinstance(obj, QDoubleSpinBox):
                swmm_dict[obj_name] = obj.value()
            elif isinstance(obj, QComboBox):
                val = obj.currentIndex()
                if obj_name == "intype":
                    val += 1
                swmm_dict[obj_name] = val
            elif isinstance(obj, QCheckBox):
                swmm_dict[obj_name] = int(obj.isChecked())
            else:
                continue

        sd_type = swmm_dict["sd_type"]
        intype = swmm_dict["intype"]
        if sd_type in ["I", "i"] and intype != 4:
            if swmm_dict["flapgate"] == 1:
                inlet_type = self.cbo_intype.currentText()
                self.uc.bar_warn("Vertical inlet opening is not allowed for {}!".format(inlet_type))
                return
            swmm_dict["rt_fid"] = None
        elif sd_type in ["I", "i"] and intype == 4:
            swmm_dict["rt_fid"] = self.SD_type4_cbo.itemData(self.SD_type4_cbo.currentIndex())
        else:
            pass

        col_gen = ("{}=?".format(c) for c in list(swmm_dict.keys()))
        col_names = ", ".join(col_gen)
        vals = list(swmm_dict.values()) + [fid]
        update_qry = """UPDATE user_swmm_nodes SET {0} WHERE fid = ?;""".format(col_names)
        self.gutils.execute(update_qry, vals)

    def schematize_swmm(self):
        self.uc.clear_bar_messages()

        # if self.gutils.is_table_empty("user_model_boundary"):
        #     self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
        #     return
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        if self.schematize_inlets_and_outfalls():
            self.uc.show_info(
                "Schematizing Storm Drains finished!\n\n"
                + "The storm drain Inlets, outfalls, and/or rating tables were updated.\n\n"
                + "(Note: The ‘Export data (*.DAT) files’ tool will write the layer attributes into the SWMMFLO.DAT, "
                + " SWMMFLORT.DAT, SWMMOUTF.DAT, SWMMFLODROPBOX.DAT, and SDCLOGGING.DAT files)"
            )

    #             if self.schematize_conduits():
    #                 self.uc.show_info("Schematizing of Storm Drains Conduits finished!\n\n" +
    #                                   "'SD Conduits' layer was created.")

    def schematize_inlets_and_outfalls(self):
        insert_inlet = """
        INSERT INTO swmmflo
        (geom, swmmchar, swmm_jt, swmm_iden, intype, swmm_length, swmm_width, swmm_height, swmm_coeff, swmm_feature, flapgate, curbheight)
        VALUES ((SELECT AsGPB(ST_Centroid(GeomFromGPB(geom))) FROM grid WHERE fid=?),?,?,?,?,?,?,?,?,?,?,?);"""

        insert_outlet = """
        INSERT INTO swmmoutf
        (geom, grid_fid, name, outf_flo)
        VALUES ((SELECT AsGPB(ST_Centroid(GeomFromGPB(geom))) FROM grid WHERE fid=?),?,?,?);"""

        update_rt = "UPDATE swmmflort SET grid_fid = ? WHERE fid = ?;"
        delete_rt = "DELETE FROM swmmflort WHERE fid = ?;"

        try:
            if self.gutils.is_table_empty("user_swmm_nodes"):
                self.uc.show_warn(
                    'User Layer "Storm Drain Nodes" is empty!\n\n'
                    + "Please import components from .INP file or shapefile, or convert from schematized Storm Drains."
                )
                return False

            QApplication.setOverrideCursor(Qt.WaitCursor)

            inlets = []
            outlets = []
            rt_inserts = []
            rt_updates = []
            rt_deletes = []
            user_nodes = self.user_swmm_nodes_lyr.getFeatures()
            for this_user_node in user_nodes:
                geom = this_user_node.geometry()
                if geom is None:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_critical(
                        "ERROR 060319.1831: Schematizing of Storm Drains failed!\n\n"
                        + "Geometry (inlet or outlet) missing.\n\n"
                        + "Please check user Storm Drain Nodes layer."
                    )
                    return False
                point = geom.asPoint()
                grid_fid = self.gutils.grid_on_point(point.x(), point.y())
                sd_type = this_user_node["sd_type"]
                name = this_user_node["name"]
                rt_fid = this_user_node["rt_fid"]
                rt_name = this_user_node["rt_name"]
                if sd_type in ["I", "i", "J"]:
                    # Insert inlet:
                    row = [grid_fid, "D", grid_fid, name] + [this_user_node[col] for col in self.inlet_columns]
                    row[10] = int("1" if is_true(row[9]) else "0")
                    row = [0 if v == NULL else v for v in row]
                    inlets.append(row)

                    # Manage Rating Table:
                #                     intype = this_user_node['intype']
                #                     if intype == 4:
                #                         if rt_name is not None and rt_name != "":
                #                             row = self.gutils.execute("SELECT * WHERE grid_fid = ? AND name = ?;", (grid_fid, rt_name,))
                #                             if not row or row[0] is None or row[1] is None or row[1] == "":
                #                                 # There is no entry for this inlet in rating table. Add it.
                #                                 # See if rating table has an item with the RT name:
                #                                 row = self.gutils.execute("SELECT * FROM swmmflort WHERE name = ?;", (rt_name,))
                #                                 if row:
                #                                    rt_inserts.append([grid_fid, rt_name])
                #
                #
                #
                #
                #
                #                                 rt_inserts.append([grid_fid, rt_name])
                #                     else:
                #                         # See if it in Rating Table. If so, assign NULL to grid_fid but keep reference of RT name to RT data:
                #                         row = self.gutils.execute("SELECT * FROM swmmflort WHERE grid_fid = ? AND name = ?;", (this_user_node['grid'], this_user_node['rt_name'],))
                #                         if row:
                #                             if row[1] == grid_fid:
                #                                 self.gutils.execute("UPDATE swmmflort SET grid_fid = NULL WHERE fid = ?;", (row[0],))

                elif sd_type == "O":
                    outf_flo = 1 if is_true(this_user_node["swmm_allow_discharge"]) else 0
                    #                     outf_flo = 1 if is_true([this_user_node[col] for col in self.outlet_columns]) else 0
                    row = [grid_fid, grid_fid, name, outf_flo]
                    outlets.append(row)
                else:
                    raise ValueError

            msg1, msg2, msg3 = "", "", ""
            if inlets or outlets or rt_updates:
                cur = self.con.cursor()
                if inlets:
                    self.gutils.clear_tables("swmmflo")
                    cur.executemany(insert_inlet, inlets)
                else:
                    msg1 = "No inlets were schematized!\n"

                if outlets:
                    self.gutils.clear_tables("swmmoutf")
                    cur.executemany(insert_outlet, outlets)
                else:
                    msg2 = "No outfalls were schematized!\n"

                #                 if rt_deletes:
                #                     cur.executemany("DELETE FROM swmmflort WHERE grid_fid = ? AND name = ?;", rt_deletes)
                #
                #                 if rt_updates:
                #                     cur.executemany("UPDATE swmmflort SET grid_fid = ? WHERE fid = ?;", rt_updates)
                #
                #                 if rt_inserts:
                #                    cur.executemany("INSERT INTO swmmflort (grid_fid, name);", rt_inserts)
                #                 else:
                #                     msg3 = "No Rating Tables were schematized!\n"

                self.con.commit()
                self.repaint_schema()
                QApplication.restoreOverrideCursor()
                msg = msg1 + msg2 + msg3
                if msg != "":
                    self.uc.show_info(
                        "WARNING 040121.1911: Schematizing Inlets, Outfalls or Rating Tables Storm Drains result:\n\n"
                        + msg
                    )
                if msg1 == "" or msg2 == "" or msg3 == "":
                    return True
                else:
                    return False
            else:
                QApplication.restoreOverrideCursor()
                self.uc.show_info("ERROR 040121.1912: Schematizing Inlets and Outfalls Storm Drains failed!")
                return False

        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 301118..0541: Schematizing Inlets, Outfalls or Rating Tables failed!."
                + "\n__________________________________________________",
                e,
            )
            return False

    def schematize_conduits(self):
        try:
            if self.gutils.is_table_empty("user_swmm_conduits"):
                self.uc.show_warn(
                    'User Layer "Storm Drain Conduits" is empty!\n\n'
                    + "Please import components from .INP file or shapefile, or convert from schematized Storm Drains."
                )
                return False

            QApplication.setOverrideCursor(Qt.WaitCursor)

            s = QSettings()
            lastDir = s.value("FLO-2D/lastGdsDir", "")
            qApp.processEvents()

            shapefile = lastDir + "/SD Conduits.shp"
            name = "SD Conduits"

            lyr = QgsProject.instance().mapLayersByName(name)

            if lyr:
                QgsProject.instance().removeMapLayers([lyr[0].id()])

            QgsVectorFileWriter.deleteShapeFile(shapefile)
            # define fields for feature attributes. A QgsFields object is needed
            fields = QgsFields()
            fields.append(QgsField("name", QVariant.String))
            fields.append(QgsField("inlet", QVariant.String))
            fields.append(QgsField("outlet", QVariant.String))
            fields.append(QgsField("length", QVariant.Double, "double", 10, 4))
            fields.append(QgsField("manning", QVariant.Double, "double", 10, 4))
            fields.append(QgsField("inlet_off", QVariant.Double, "double", 10, 4))
            fields.append(QgsField("outlet_off", QVariant.Double, "double", 10, 4))
            fields.append(QgsField("init_flow", QVariant.Double, "double", 10, 4))
            fields.append(QgsField("max_flow", QVariant.Double, "double", 10, 4))
            fields.append(QgsField("inletLoss", QVariant.Double, "double", 10, 4))
            fields.append(QgsField("outletLoss", QVariant.Double, "double", 10, 4))
            fields.append(QgsField("meanLoss", QVariant.Double, "double", 10, 4))
            fields.append(QgsField("flapLoss", QVariant.Bool))
            fields.append(QgsField("XSshape", QVariant.String))
            fields.append(QgsField("XSMaxDepth", QVariant.Double, "double", 10, 4))
            fields.append(QgsField("XSgeom2", QVariant.Double, "double", 10, 4))
            fields.append(QgsField("XSgeom3", QVariant.Double, "double", 10, 4))
            fields.append(QgsField("XSgeom4", QVariant.Double, "double", 10, 4))
            fields.append(QgsField("XSbarrels", QVariant.Int, "int", 10, 4))

            mapCanvas = self.iface.mapCanvas()
            my_crs = mapCanvas.mapSettings().destinationCrs()

            writer = QgsVectorFileWriter(shapefile, "system", fields, QgsWkbTypes.LineString, my_crs, "ESRI Shapefile")

            if writer.hasError() != QgsVectorFileWriter.NoError:
                QApplication.restoreOverrideCursor()
                self.uc.bar_error("ERROR 220620.1719: error when creating shapefile: " + shapefile)
                return False

            # Add features:
            conduits_lyr = self.lyrs.data["user_swmm_conduits"]["qlyr"]
            conduits_feats = conduits_lyr.getFeatures()
            for feat in conduits_feats:
                line_geom = feat.geometry().asPolyline()
                start = line_geom[0]
                end = line_geom[-1]

                fet = QgsFeature()
                fet.setFields(fields)
                fet.setGeometry(QgsGeometry.fromPolylineXY([start, end]))
                non_coord_feats = []
                non_coord_feats.append(feat[1])
                non_coord_feats.append(feat[2])
                non_coord_feats.append(feat[3])
                non_coord_feats.append(feat[4])
                non_coord_feats.append(feat[5])
                non_coord_feats.append(feat[6])
                non_coord_feats.append(feat[7])
                non_coord_feats.append(feat[8])
                non_coord_feats.append(feat[9])
                non_coord_feats.append(feat[10])
                non_coord_feats.append(feat[11])
                non_coord_feats.append(feat[12])
                non_coord_feats.append(feat[13])
                non_coord_feats.append(feat[14])
                non_coord_feats.append(feat[15])
                non_coord_feats.append(feat[16])
                non_coord_feats.append(feat[17])
                non_coord_feats.append(feat[18])
                non_coord_feats.append(feat[19])

                fet.setAttributes(non_coord_feats)
                writer.addFeature(fet)

            # delete the writer to flush features to disk
            del writer

            vlayer = self.iface.addVectorLayer(shapefile, "", "ogr")
            #             symbol = QgsLineSymbol.createSimple({ 'color': 'red', 'capstyle' : 'arrow', 'line_style': 'solid'})
            #             vlayer.setRenderer(QgsSingleSymbolRenderer(symbol))

            sym = vlayer.renderer().symbol()
            sym_layer = QgsArrowSymbolLayer.create(
                {"arrow_width": "0.05", "arrow_width_at_start": "0.05", "head_length": "0", "head_thickness": "0"}
            )

            sym.changeSymbolLayer(0, sym_layer)

            # show the change
            vlayer.triggerRepaint()
            QApplication.restoreOverrideCursor()
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 220620.1648: error while creating layer " + name + "!\n", e)
            return False

    def simulate_stormdrain(self):
        if self.simulate_stormdrain_chbox.isChecked():
            self.gutils.set_cont_par("SWMM", 1)
        else:
            self.gutils.set_cont_par("SWMM", 0)

    def import_storm_drain_INP_file(self, mode, show_end_message):
        """
        Reads a Storm Water Management Model (SWMM) .INP file.

        Reads an .INP file and creates the "user_swmm_nodes" and "user_swmm_conduits" layers with
        attributes taken from the [COORDINATES], [SUBCATCHMENTS], [JUNCTIONS], [OUTFALLS], [CONDUITS],
        [LOSSES], [XSECTIONS] groups of the .INP file.
        Also includes additional attributes used by the FLO-2D model.

        The following dictionaries from the StormDrainProject class are used:
            self.INP_groups = OrderedDict()    :will contain all groups [xxxx] from .INP file
            self.INP_nodes = {}
            self.INP_conduits = {}

        """
        self.uc.clear_bar_messages()

        # if self.gutils.is_table_empty("user_model_boundary"):
        #     self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
        #     return False

        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return False

        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")
        if mode == "Force import of SWMM.INP":
            swmm_file = last_dir + r"\SWMM.INP"
            if not os.path.isfile(swmm_file):
                return False
        else:
            # Show dialog to import SWMM.INP or cancel its import:
            swmm_file, __ = QFileDialog.getOpenFileName(
                None, "Select SWMM input file to import data", directory=last_dir, filter="(*.inp *.INP*)"
            )
            if not swmm_file:
                return False

        s.setValue("FLO-2D/lastSWMMDir", os.path.dirname(swmm_file))

        n_spaces = "\t\t"
        new_nodes = []
        outside_nodes = ""
        updated_nodes = 0

        new_storages = []
        outside_storages = ""
        updated_storages = 0

        new_conduits = []
        outside_conduits = ""
        updated_conduits = 0

        new_pumps = []
        outside_pumps = ""
        updated_pumps = 0

        new_orifices = []
        outside_orifices = ""
        updated_orifices = 0

        new_weirs = []
        outside_weirs = ""
        updated_weirs = 0

        error_msg = "ERROR 050322.9423: error(s) importing file\n\n" + swmm_file
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            """
            Create an ordered dictionary "storm_drain.INP_groups".

            storm_drain.split_INP_groups_dictionary_by_tags():
            'The dictionary 'INP_groups' will have as key the name of the groups [xxxx] like 'OUTFALLS', 'JUNCTIONS', etc.
            Each element of the dictionary is a list of all the lines following the group name [xxxx] in the .INP file.

            """
            subcatchments = None
            skipped_inlets = 0
            storm_drain = StormDrainProject(self.iface, swmm_file)

            ret = storm_drain.split_INP_groups_dictionary_by_tags()
            if ret == 3:
                # No coordinates in INP file
                QApplication.setOverrideCursor(Qt.ArrowCursor)
                self.uc.show_warn(
                    "WARNING 060319.1729: SWMM input file\n\n " + swmm_file + "\n\n has no coordinates defined!"
                )
                QApplication.restoreOverrideCursor()
                return False
            elif ret == 0:
                return False

            # if self.select_this_INP_group(INP_groups, "coor") > 0: 
            #     QApplication.restoreOverrideCursor()
            #     self.uc.show_warn(
            #         "WARNING 060319.1730: SWMM input file\n\n " + swmm_file + "\n\n has no coordinates defined!"
            #     )
            #     return False                

            # Build Nodes:
            storm_drain.add_JUNCTIONS_to_INP_nodes_dictionary()
            subcatchments = storm_drain.add_SUBCATCHMENTS_to_INP_nodes_dictionary()
            storm_drain.add_OUTFALLS_to_INP_nodes_dictionary() 
                      
            if storm_drain.add_coordinates_INP_nodes_dictionary() == 0:
                QApplication.setOverrideCursor(Qt.ArrowCursor)
                self.uc.show_warn(
                    "WARNING 060319.1730: SWMM input file\n\n " + swmm_file + "\n\n has no coordinates defined!"
                )
                QApplication.restoreOverrideCursor()
                return False
            else:

                if mode == "Force import of SWMM.INP":
                    complete_or_create = "Keep and Complete"
                else:
                    if self.gutils.is_table_empty("user_swmm_nodes"):
                        complete_or_create = "Create New"
                    else:
                        
                        QApplication.setOverrideCursor(Qt.ArrowCursor)
                        complete_or_create = self.import_INP_action()
                        QApplication.restoreOverrideCursor()
                        
                        if complete_or_create == "Cancel":
                            return False

                # Storage units:
                storm_drain.create_INP_storage_dictionary_with_storage()
                storm_drain.add_coordinates_to_INP_storages_dictionary()
                
                # Conduits:
                storm_drain.create_INP_conduits_dictionary_with_conduits()
                storm_drain.add_LOSSES_to_INP_conduits_dictionary()

                # Pumps:
                storm_drain.create_INP_pumps_dictionary_with_pumps()

                # Orifices:
                storm_drain.create_INP_orifices_dictionary_with_orifices()

                # Weirs:
                storm_drain.create_INP_weirs_dictionary_with_weirs()

                storm_drain.add_XSECTIONS_to_INP_orifices_dictionary()
                storm_drain.add_XSECTIONS_to_INP_weirs_dictionary()
                storm_drain.add_XSECTIONS_to_INP_conduits_dictionary()

                # External inflows into table swmm_inflows:
                storm_drain.create_INP_inflows_dictionary_with_inflows()

                remove_features(self.swmm_inflows_lyr)
                try:
                    insert_inflows_sql = """INSERT INTO swmm_inflows 
                                            (   node_name, 
                                                constituent, 
                                                baseline, 
                                                pattern_name, 
                                                time_series_name, 
                                                scale_factor
                                            ) 
                                            VALUES (?, ?, ?, ?, ?, ?);"""
                    for name, values in list(storm_drain.INP_inflows.items()):
                        constituent = values["constituent"].upper() if "constituent" in values else "FLOW"
                        baseline = values["baseline"] if values["baseline"] is not None else 0.0
                        pattern_name = values["pattern_name"] if "pattern_name" in values else "?"
                        time_series_name = values["time_series_name"] if "time_series_name" in values else "?"
                        scale_factor = values["scale_factor"] if values["scale_factor"] is not None else 0.0

                        self.gutils.execute(
                            insert_inflows_sql,
                            (name, constituent, baseline, pattern_name, time_series_name, scale_factor),
                        )

                except Exception as e:
                    QApplication.setOverrideCursor(Qt.ArrowCursor)
                    self.uc.show_error(
                        "ERROR 020219.0812: Reading storm drain inflows from SWMM input data failed!"
                        + "\n__________________________________________________",
                        e,
                    )
                    QApplication.restoreOverrideCursor()
                    
                # Inflows patterns into table swmm_inflow_patterns:
                storm_drain.create_INP_patterns_list_with_patterns()

                remove_features(self.swmm_inflow_patterns_lyr)
                try:
                    description = ""
                    insert_patterns_sql = """INSERT INTO swmm_inflow_patterns
                                            (   pattern_name, 
                                                pattern_description, 
                                                hour, 
                                                multiplier
                                            ) 
                                            VALUES (?, ?, ?, ?);"""
                    i = 0
                    for pattern in storm_drain.INP_patterns:
                        if pattern[2][1] == "HOURLY" :
                            name = pattern[1][1]
                            description = pattern[0][1]
                            for j in range(0, 6):
                                i += 1
                                hour = str(i)
                                multiplier = pattern[j + 3][1]
                                self.gutils.execute(insert_patterns_sql, (name, description, hour, multiplier))
                            if i == 24:
                                i = 0

                except Exception as e:
                    QApplication.setOverrideCursor(Qt.ArrowCursor)
                    self.uc.show_error(
                        "ERROR 280219.1046: Reading storm drain paterns from SWMM input data failed!"
                        + "\n__________________________________________________",
                        e,
                    )
                    QApplication.restoreOverrideCursor()
                # Inflow time series into table swmm_time_series:
                storm_drain.create_INP_time_series_list_with_time_series()

                remove_features(self.swmm_time_series_lyr)
                remove_features(self.swmm_time_series_data_lyr)
                
                try:
                    insert_times_from_file_sql = """INSERT INTO swmm_time_series 
                                            (   time_series_name, 
                                                time_series_description, 
                                                time_series_file,
                                                time_series_data
                                            ) 
                                            VALUES (?, ?, ?, ?);"""

                    insert_times_from_data_sql = """INSERT INTO swmm_time_series_data
                                            (   time_series_name, 
                                                date, 
                                                time,
                                                value
                                            ) 
                                            VALUES (?, ?, ?, ?);"""
                    for time in storm_drain.INP_timeseries:
                        if time[2][1] == "FILE":
                            name = time[1][1]
                            description = time[0][1]
                            file = time[3][1]
                            file2 = file.replace('"', "")
                            self.gutils.execute(insert_times_from_file_sql, (name, description, file2.strip(), "False"))
                        else:
                            # See if time series data reference is already in table:
                            row = self.gutils.execute(
                                "SELECT * FROM swmm_time_series WHERE time_series_name = ?;", (time[1][1],)
                            ).fetchone()
                            if not row:
                                name = time[1][1]
                                description = time[0][1]
                                file = ""
                                file2 = file.replace('"', "")
                                self.gutils.execute(
                                    insert_times_from_file_sql, (name, description, file2.strip(), "True")
                                )

                            description = time[0][1]
                            name = time[1][1]
                            date = time[2][1]
                            tme = time[3][1]
                            value = float_or_zero(time[4][1])
                            self.gutils.execute(insert_times_from_data_sql, (name, date, tme, value))

                except Exception as e:
                    QApplication.setOverrideCursor(Qt.ArrowCursor)
                    self.uc.show_error(
                        "ERROR 290220.1727: Reading storm drain time series from SWMM input data failed!"
                        + "\n__________________________________________________",
                        e,
                    )
                    QApplication.restoreOverrideCursor()

                # Curves into pump, tidal, and other curve tables:
                storm_drain.create_INP_curves_list_with_curves()
                try:
                    insert_pump_curves_sql = """INSERT INTO swmm_pumps_curve_data
                                            (   pump_curve_name, 
                                                pump_curve_type, 
                                                x_value,
                                                y_value,
                                                description
                                            ) 
                                            VALUES (?, ?, ?, ?, ?);"""

                    insert_tidal_curves_sql = """INSERT OR REPLACE INTO swmm_tidal_curve
                                            (   tidal_curve_name, 
                                                tidal_curve_description
                                            ) 
                                            VALUES (?, ?);"""

                    insert_tidal_curves_data_sql = """INSERT INTO swmm_tidal_curve_data
                                            (   tidal_curve_name, 
                                                hour, 
                                                stage
                                            ) 
                                            VALUES (?, ?, ?);"""
                                            
                    insert_other_curves_sql = """INSERT INTO swmm_other_curves
                                            (   name, 
                                                type, 
                                                description,
                                                x_value,
                                                y_value
                                            ) 
                                            VALUES (?, ?, ?, ?, ?);"""                                            

                    remove_features(self.swmm_pumps_curve_data_lyr)
                    remove_features(self.swmm_tidal_curve_lyr)
                    remove_features(self.swmm_tidal_curve_data_lyr)
                    remove_features(self.swmm_other_curves_lyr)
                    
                    for curve in storm_drain.INP_curves:
                        if curve[1][0:4] in ["Pump", "PUMP"]:
                            self.gutils.execute(insert_pump_curves_sql, (curve[0], curve[1], curve[2], curve[3], curve[4]))
                        elif curve[1][0:5].upper() == "TIDAL":
                            self.gutils.execute(insert_tidal_curves_sql, (curve[0], curve[4]))
                            self.gutils.execute(insert_tidal_curves_data_sql, (curve[0], curve[2], curve[3]))
                        else:
                            self.gutils.execute(insert_other_curves_sql, (curve[0], curve[1], curve[4], curve[2], curve[3]))     

                except Exception as e:
                    QApplication.setOverrideCursor(Qt.ArrowCursor)
                    self.uc.show_error(
                        "ERROR 241121.0547: Reading storm drain pump curve data from SWMM input data failed!"
                        + "\n__________________________________________________",
                        e,
                    )
                    QApplication.restoreOverrideCursor()

        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            self.uc.show_error("ERROR 080618.0448: reading SWMM input file failed!", e)
            QApplication.restoreOverrideCursor()
            return False
        finally:
            QApplication.restoreOverrideCursor()            
            
            
        # JUNCTIONS/OUTFALLS: Create User Junctions and Outfalls layers:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            """
            Creates Storm Drain Nodes layer (Users layers).

            Creates "user_swmm_nodes" layer with attributes taken from
            the [COORDINATES], [JUNCTIONS], and [OUTFALLS] groups.

            """

            # Transfer data from "storm_drain.INP_dict" to "user_swmm_nodes" layer:

            replace_user_swmm_nodes_sql = """UPDATE user_swmm_nodes 
                             SET    geom = ?,
                                    junction_invert_elev = ?,
                                    max_depth = ?, 
                                    init_depth = ?,
                                    surcharge_depth = ?, 
                                    ponded_area = ?,
                                    outfall_type = ?, 
                                    outfall_invert_elev = ?, 
                                    tidal_curve = ?, 
                                    time_series = ?,
                                    water_depth = ?,
                                    flapgate = ?, 
                                    swmm_allow_discharge = ?, 
                                    invert_elev_inp = ?, 
                                    max_depth_inp = ?, 
                                    rim_elev_inp = ?, 
                                    rim_elev = ?, 
                                    ge_elev = ?, 
                                    difference = ?                          
                             WHERE name = ?;"""

            new_nodes = []
            updated_nodes = 0
            list_INP_nodes = list(storm_drain.INP_nodes.items())
            for name, values in list_INP_nodes:
                # "INP_nodes dictionary contains attributes names and
                # values taken from the .INP file.
                if subcatchments is not None:
                    if "subcatchment" in values:
                        sd_type = "I"
                    elif "out_type" in values:
                        sd_type = "O"
                    elif name[0] in ["I", "i"]:
                        skipped_inlets += 1
                        continue  # Skip inlets defined by initial "I" or "i". Only consider inlets in [SUBCATCHMENTS]
                    else:
                        sd_type = "J"

                else:
                    if name[0] in ["I", "i"]:
                        if (
                            "junction_invert_elev" in values
                        ):  # if 'junction_invert_elev' is there => it was read from [JUNCTIONS]
                            sd_type = "I"
                        else:
                            continue
                    elif "out_type" in values:
                        sd_type = "O"
                    else:
                        sd_type = "J"

                # Inlets/Junctions:
                junction_invert_elev = (
                    float_or_zero(values["junction_invert_elev"]) if "junction_invert_elev" in values else 0
                )
                max_depth = float_or_zero(values["max_depth"]) if "max_depth" in values else 0
                init_depth = float_or_zero(values["init_depth"]) if "init_depth" in values else 0
                surcharge_depth = float_or_zero(values["surcharge_depth"]) if "surcharge_depth" in values else 0
                ponded_area = float_or_zero(values["ponded_area"]) if "ponded_area" in values else 0

                # Outfalls:
                outfall_type = values["out_type"].upper() if "out_type" in values else "NORMAL"

                outfall_invert_elev = (
                    float_or_zero(values["outfall_invert_elev"]) if "outfall_invert_elev" in values else 0
                )
                time_series = "*"
                tidal_curve = "*"
                if outfall_type == "TIDAL":
                    tidal_curve = values["series"]
                if outfall_type == "TIMESERIES":
                    time_series = values["series"]
                water_depth = values["water_depth"] if "water_depth" in values else 0
                if outfall_type == "FIXED":
                    water_depth = values["series"]

                flapgate = values["tide_gate"] if "tide_gate" in values else "False"
                flapgate = "True" if is_true(flapgate) else "False"
                allow_discharge = values["swmm_allow_discharge"] if "swmm_allow_discharge" in values else "False"
                allow_discharge = "True" if is_true(allow_discharge) else "False"

                rim_elev = junction_invert_elev + max_depth if junction_invert_elev and max_depth else 0

                intype = int(values["intype"]) if "intype" in values else 1

                if not "x" in values or not "y" in values:
                    outside_nodes += n_spaces + name + "\tno coordinates.\n"
                    continue
                
                x = float(values["x"])
                y = float(values["y"])
                grid = self.gutils.grid_on_point(x, y)
                if grid is None:
                    outside_nodes += n_spaces + name + "\toutside domain.\n"

                if grid:
                    elev = self.gutils.grid_value(grid, "elevation")
                else:
                    elev = 0
                elev = elev if elev else 0
                difference = elev - rim_elev if elev and rim_elev else 0

                if complete_or_create == "Create New":
                    geom = QgsGeometry.fromPointXY(QgsPointXY(x, y))
                    fields = self.user_swmm_nodes_lyr.fields()
                    feat = QgsFeature()
                    feat.setFields(fields)
                    feat.setGeometry(geom)
                    feat.setAttribute("grid", grid)
                    feat.setAttribute("sd_type", sd_type)
                    feat.setAttribute("name", name)
                    feat.setAttribute("intype", intype)

                    feat.setAttribute("junction_invert_elev", junction_invert_elev)
                    feat.setAttribute("max_depth", max_depth)
                    feat.setAttribute("init_depth", init_depth)
                    feat.setAttribute("surcharge_depth", surcharge_depth)
                    feat.setAttribute("ponded_area", ponded_area)
                    feat.setAttribute("outfall_type", outfall_type)
                    feat.setAttribute("outfall_invert_elev", outfall_invert_elev)
                    feat.setAttribute("tidal_curve", tidal_curve)
                    feat.setAttribute("time_series", time_series)
                    feat.setAttribute("water_depth", water_depth)
                    feat.setAttribute("flapgate", flapgate)
                    feat.setAttribute("swmm_allow_discharge", allow_discharge)
                    feat.setAttribute("invert_elev_inp", junction_invert_elev)
                    feat.setAttribute("max_depth_inp", max_depth)
                    feat.setAttribute("rim_elev_inp", rim_elev)
                    feat.setAttribute("rim_elev", rim_elev)
                    feat.setAttribute("ge_elev", elev)
                    feat.setAttribute("difference", difference)

                    # The following attributes are not defined in .INP files,
                    # assign them zero as default values:
                    feat.setAttribute("swmm_length", 0)
                    feat.setAttribute("swmm_width", 0)
                    feat.setAttribute("swmm_height", 0)
                    feat.setAttribute("swmm_coeff", 0)
                    feat.setAttribute("swmm_feature", 0)
                    feat.setAttribute("curbheight", 0)
                    feat.setAttribute("swmm_clogging_factor", 0)
                    feat.setAttribute("swmm_time_for_clogging", 0)
                    feat.setAttribute("rt_fid", 0)
                    feat.setAttribute("outf_flo", 0)

                    new_nodes.append(feat)

                else:  # Keep some existing data in user_swmm_nodes (e.g swmm_length, swmm_width, etc.)
                    fid = self.gutils.execute("SELECT fid FROM user_swmm_nodes WHERE name = ?;", (name,)).fetchone()
                    if fid:  # name already in user_swmm_nodes
                        try:
                            fid, wkt_geom = self.gutils.execute(
                                "SELECT fid, ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM user_swmm_nodes WHERE name = ?;",
                                (name,),
                            ).fetchone()
                        except Exception:
                            continue
                        if fid:
                            geom = "POINT({0} {1})".format(x, y)
                            geom = self.gutils.wkt_to_gpb(geom)

                            # xc, yc = [float(i) for i in wkt_geom.strip("POINT()").split()]
                            # geom = "POINT({0} {1})".format(xc, yc)
                            # geom = self.gutils.wkt_to_gpb(geom)

                            self.gutils.execute(
                                replace_user_swmm_nodes_sql,
                                (
                                    geom,
                                    junction_invert_elev,
                                    max_depth,
                                    init_depth,
                                    surcharge_depth,
                                    ponded_area,
                                    outfall_type,
                                    outfall_invert_elev,
                                    tidal_curve,
                                    time_series,
                                    water_depth,
                                    flapgate,
                                    allow_discharge,
                                    junction_invert_elev,
                                    max_depth,
                                    rim_elev,
                                    rim_elev,
                                    elev,
                                    difference,
                                    name,
                                ),
                            )
                            updated_nodes += 1

                    else:  # this name is not in user_swmm_nodes, include it:
                        geom = QgsGeometry.fromPointXY(QgsPointXY(x, y))
                        fields = self.user_swmm_nodes_lyr.fields()
                        feat = QgsFeature()
                        feat.setFields(fields)
                        feat.setGeometry(geom)
                        feat.setAttribute("grid", grid)
                        feat.setAttribute("sd_type", sd_type)
                        feat.setAttribute("name", name)
                        feat.setAttribute("intype", intype)

                        feat.setAttribute("junction_invert_elev", junction_invert_elev)
                        feat.setAttribute("max_depth", max_depth)
                        feat.setAttribute("init_depth", init_depth)
                        feat.setAttribute("surcharge_depth", surcharge_depth)
                        feat.setAttribute("ponded_area", ponded_area)
                        feat.setAttribute("outfall_type", outfall_type)
                        feat.setAttribute("outfall_invert_elev", outfall_invert_elev)
                        feat.setAttribute("tidal_curve", tidal_curve)
                        feat.setAttribute("time_series", time_series)
                        feat.setAttribute("water_depth", water_depth)
                        feat.setAttribute("flapgate", flapgate)
                        feat.setAttribute("swmm_allow_discharge", allow_discharge)
                        feat.setAttribute("invert_elev_inp", junction_invert_elev)
                        feat.setAttribute("max_depth_inp", max_depth)
                        feat.setAttribute("rim_elev_inp", rim_elev)
                        feat.setAttribute("rim_elev", rim_elev)
                        feat.setAttribute("ge_elev", elev)
                        feat.setAttribute("difference", difference)

                        # The following attributes are not defined in .INP files,
                        # assign them zero as default values:
                        feat.setAttribute("swmm_length", 0)
                        feat.setAttribute("swmm_width", 0)
                        feat.setAttribute("swmm_height", 0)
                        feat.setAttribute("swmm_coeff", 0)
                        feat.setAttribute("swmm_feature", 0)
                        feat.setAttribute("curbheight", 0)
                        feat.setAttribute("swmm_clogging_factor", 0)
                        feat.setAttribute("swmm_time_for_clogging", 0)
                        feat.setAttribute("rt_fid", 0)
                        feat.setAttribute("outf_flo", 0)

                        new_nodes.append(feat)
                        updated_nodes += 1

            if complete_or_create == "Create New" and len(new_nodes) != 0:
                remove_features(self.user_swmm_nodes_lyr)
                self.user_swmm_nodes_lyr.startEditing()
                self.user_swmm_nodes_lyr.addFeatures(new_nodes)
                self.user_swmm_nodes_lyr.commitChanges()
                self.user_swmm_nodes_lyr.updateExtents()
                self.user_swmm_nodes_lyr.triggerRepaint()
                self.user_swmm_nodes_lyr.removeSelection()
                
                s = QSettings()
                last_dir = s.value("FLO-2D/lastGdsDir", "")
                # Update drboxarea field by reading SWMMFLODROPBOX.DAT:
                file = last_dir + r"\SWMMFLODROPBOX.DAT"
                if os.path.isfile(file):
                    if os.path.getsize(file) > 0:
                        try: 
                            pd = ParseDAT()
                            par = pd.single_parser(file)
                            for row in par:                    
                                name  = row[0]
                                area = row[2]
                                self.gutils.execute("UPDATE user_swmm_nodes SET drboxarea = ? WHERE name = ?", (area, name))
                        except:
                            self.uc.bar_error("Error while reading SWMMFLODROPBOX.DAT !")                  

                # Update swmm_clogging_factor and  swmm_time_for_clogging fields by reading SDCLOGGING.DAT:
                file = last_dir + r"\SDCLOGGING.DAT"
                if os.path.isfile(file):
                    if os.path.getsize(file) > 0:
                        try: 
                            pd = ParseDAT()
                            par = pd.single_parser(file)
                            for row in par:   
                                name  = row[2]
                                clog_fact = row[3]
                                clog_time = row[4]
                                self.gutils.execute("""UPDATE user_swmm_nodes
                                                       SET swmm_clogging_factor = ?, swmm_time_for_clogging = ?
                                                       WHERE name = ?""", (clog_fact, clog_time, name))                            
                        except:
                            self.uc.bar_error("Error while reading SDCLOGGING.DAT !")                  
                
            else:
                # The option 'Keep existing and complete' already updated values taken from the .INP file.
                # but include new ones:
                if len(new_nodes) != 0:
                    self.user_swmm_nodes_lyr.startEditing()
                    self.user_swmm_nodes_lyr.addFeatures(new_nodes)
                    self.user_swmm_nodes_lyr.commitChanges()
                    self.user_swmm_nodes_lyr.updateExtents()
                    self.user_swmm_nodes_lyr.triggerRepaint()
                    self.user_swmm_nodes_lyr.removeSelection()

        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            self.uc.show_error(
                "ERROR 060319.1610: Creating Storm Drain Nodes layer failed!\n\n"
                + "Please check your SWMM input data.\nAre the nodes coordinates inside the computational domain?",
                e,
            )
            QApplication.restoreOverrideCursor()
            return False
        finally:
            QApplication.restoreOverrideCursor()        

        # STORAGE: Create User Storage layer:
        if complete_or_create == "Create New":
            remove_features(self.user_swmm_storage_units_lyr)
            
        QApplication.setOverrideCursor(Qt.WaitCursor)       
        try:
            """
            Creates Storm Drain Storage Units layer (Users layers).
        
            Creates "user_swmm_storage_units" layer with attributes taken from
            the [COORDINATES] and [STORAGE] groups.
        
            """
        
            # Transfer data from "storm_drain.INP_dict" to "user_swmm_storage_units" layer:
        
            replace_user_swmm_storage_sql = """UPDATE user_swmm_storage_units
                             SET    geom = ?,
                                    "invert_elev" = ?,
                                    "max_depth" = ?,
                                    "init_depth" = ?,
                                    "external_inflow" = ?,
                                    "treatment" = ?,
                                    "ponded_area" = ?,
                                    "evap_factor" = ?,
                                    "infiltration" = ?,
                                    "infil_method" = ?,
                                    "suction_head" = ?,
                                    "conductivity" = ?,
                                    "initial_deficit" = ?,
                                    "storage_curve" = ?,
                                    "coefficient" = ?,
                                    "exponent" = ?,
                                    "constant" = ?,
                                    "curve_name" = ?                             
                             WHERE name = ?;"""
                             
            new_storages = []
            updated_storages = 0
            list_INP_storages = list(storm_drain.INP_storages.items())
            # if list_INP_storages:
            for name, values in list_INP_storages:
                # "INP_storages dictionary contains attributes names and
                # values taken from the .INP file.
                
                invert_elev = float_or_zero(values["invert_elev"]) if "invert_elev" in values else 0
                max_depth = float_or_zero(values["max_depth"]) if "max_depth" in values else 0
                init_depth = float_or_zero(values["init_depth"]) if "init_depth" in values else 0
                external_inflow = int(values["external_inflow"]) if "external_inflow" in values else "False"
                treatment = values["treatment"].upper() if "treatment" in values else "NO"       
                ponded_area = float_or_zero(values["ponded_area"]) if "ponded_area" in values else 0
                evap_factor = float_or_zero(values["evap_factor"]) if "evap_factor" in values else 0
                infiltration = "True" if len(values) in [14, 12] else "False"
                infil_method = values["infil_method"].upper() if "infil_method" in values else "GREEN_AMPT"
                suction_head = float_or_zero(values["suction_head"]) if "suction_head" in values else 0
                conductivity = float_or_zero(values["conductivity"]) if "conductivity" in values else 0
                initial_deficit = float_or_zero(values["initial_deficit"]) if "initial_deficit" in values else 0
                storage_curve = values["storage_curve"].upper() if "storage_curve" in values else "FUNCTIONAL"
                if (storage_curve == "FUNCTIONAL"):
                    coefficient = float_or_zero(values["coefficient"]) if "coefficient" in values else 1000
                    exponent = float_or_zero(values["exponent"]) if "exponent" in values else 0
                    constant = float_or_zero(values["constant"]) if "constant" in values else 0
                else:
                    coefficient = 1000
                    exponent = 0
                    constant = 0    
                curve_name = values["curve_name"] if "curve_name" in values else "*"
    
                if not "x" in values or not "y" in values:
                    outside_nodes += n_spaces + name + "\tno coordinates.\n"
                    continue
                
                x = float(values["x"])
                y = float(values["y"])
                grid = self.gutils.grid_on_point(x, y)
                if grid is None:
                    outside_storages += n_spaces + name + "\toutside domain.\n"
    
                if complete_or_create == "Create New":
                    geom = QgsGeometry.fromPointXY(QgsPointXY(x, y))
                    fields = self.user_swmm_storage_units_lyr.fields()
                    feat = QgsFeature()
                    feat.setFields(fields)
                    feat.setGeometry(geom)
                    feat.setAttribute("grid", grid)
                    feat.setAttribute("name", name)
                    feat.setAttribute("invert_elev", invert_elev)
                    feat.setAttribute("max_depth", max_depth)
                    feat.setAttribute("init_depth", init_depth)
                    feat.setAttribute("external_inflow", external_inflow)
                    feat.setAttribute("treatment", treatment)
                    feat.setAttribute("ponded_area", ponded_area)
                    feat.setAttribute("evap_factor", evap_factor)
                    feat.setAttribute("infiltration", infiltration)
                    feat.setAttribute("infil_method", infil_method)
                    feat.setAttribute("suction_head", suction_head)
                    feat.setAttribute("conductivity", conductivity)
                    feat.setAttribute("initial_deficit", initial_deficit)
                    feat.setAttribute("storage_curve", storage_curve)
                    feat.setAttribute("coefficient", coefficient)
                    feat.setAttribute("exponent", exponent)
                    feat.setAttribute("constant", constant)
                    feat.setAttribute("curve_name", curve_name)
    
                    # The following attributes are not defined in .INP files,
                    # assign them zero as default values:
                    # feat.setAttribute("swmm_length", 0)
                    # feat.setAttribute("swmm_width", 0)
                    # feat.setAttribute("swmm_height", 0)
                    # feat.setAttribute("swmm_coeff", 0)
                    # feat.setAttribute("swmm_feature", 0)
                    # feat.setAttribute("curbheight", 0)
                    # feat.setAttribute("swmm_clogging_factor", 0)
                    # feat.setAttribute("swmm_time_for_clogging", 0)
                    # feat.setAttribute("rt_fid", 0)
                    # feat.setAttribute("outf_flo", 0)
    
                    new_storages.append(feat)
    
                else:  # Keep some existing data in user_swmm_storage_unit.
                    fid = self.gutils.execute("SELECT fid FROM user_swmm_storage_units WHERE name = ?;", (name,)).fetchone()
                    if fid:  # name already in user_swmm_storage_units
                        try:
                            fid, wkt_geom = self.gutils.execute(
                                "SELECT fid, ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM user_swmm_storage_units WHERE name = ?;",
                                (name,),
                            ).fetchone()
                        except Exception:
                            continue
                        if fid:
                            geom = "POINT({0} {1})".format(x, y)
                            geom = self.gutils.wkt_to_gpb(geom)
    
                            self.gutils.execute(
                                replace_user_swmm_storage_sql,
                                (
                                    geom,
                                    invert_elev,
                                    max_depth,
                                    init_depth,
                                    external_inflow,
                                    treatment,                
                                    ponded_area,
                                    evap_factor,
                                    infiltration,
                                    infil_method,
                                    suction_head,
                                    conductivity,
                                    initial_deficit,
                                    storage_curve,
                                    coefficient,
                                    exponent,
                                    constant,
                                    curve_name,
                                    name,
                                ),
                            )
                            updated_storages += 1
    
                    else:  # this name is not in user_swmm_storages, include it:
                        geom = QgsGeometry.fromPointXY(QgsPointXY(x, y))
                        fields = self.user_swmm_storage_units_lyr.fields()
                        feat = QgsFeature()
                        feat.setFields(fields)
                        feat.setGeometry(geom)
                        feat.setAttribute("grid", grid)
                        feat.setAttribute("name", name)
                        feat.setAttribute("invert_elev", invert_elev)
                        feat.setAttribute("max_depth", max_depth)
                        feat.setAttribute("init_depth", init_depth)
                        feat.setAttribute("external_inflow", external_inflow)
                        feat.setAttribute("treatment", treatment)
                        feat.setAttribute("ponded_area", ponded_area)
                        feat.setAttribute("evap_factor", evap_factor)
                        feat.setAttribute("infiltration", infiltration)
                        feat.setAttribute("infil_method", infil_method)
                        feat.setAttribute("suction_head", suction_head)
                        feat.setAttribute("conductivity", conductivity)
                        feat.setAttribute("initial_deficit", initial_deficit)
                        feat.setAttribute("storage_curve", storage_curve)
                        feat.setAttribute("coefficient", coefficient)
                        feat.setAttribute("exponent", exponent)
                        feat.setAttribute("constant", constant)
                        feat.setAttribute("curve_name", curve_name)                        
    
                        new_storages.append(feat)
                        updated_storages += 1
    
            if complete_or_create == "Create New" and len(new_storages) != 0:
                remove_features(self.user_swmm_storage_units_lyr)
                self.user_swmm_storage_units_lyr.startEditing()
                self.user_swmm_storage_units_lyr.addFeatures(new_storages)
                self.user_swmm_storage_units_lyr.commitChanges()
                self.user_swmm_storage_units_lyr.updateExtents()
                self.user_swmm_storage_units_lyr.triggerRepaint()
                self.user_swmm_storage_units_lyr.removeSelection()
            else:
                # The option 'Keep existing and complete' already updated values taken from the .INP file.
                # but include new ones:
                if len(new_storages) != 0:
                    self.user_swmm_storage_units_lyr.startEditing()
                    self.user_swmm_storage_units_lyr.addFeatures(new_storages)
                    self.user_swmm_storage_units_lyr.commitChanges()
                    self.user_swmm_storage_units_lyr.updateExtents()
                    self.user_swmm_storage_units_lyr.triggerRepaint()
                    self.user_swmm_storage_units_lyr.removeSelection()
        
        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            self.uc.show_error(
                "ERROR 300124.1109: Creating Storm Drain Storage Units layer failed!\n\n"
                + "Please check your SWMM input data.\nAre the nodes coordinates inside the computational domain?",
                e,
            )
            QApplication.restoreOverrideCursor()
            return False
        finally:
            QApplication.restoreOverrideCursor()
            
                    
        # Unpack and merge storm_drain.INP_nodes and storm_drain.INP_storages:
        self.all_nodes = {**storm_drain.INP_nodes, **storm_drain.INP_storages} 
                                
        # CONDUITS: Create User Conduits layer:
        conduit_inlets_not_found = ""
        conduit_outlets_not_found = ""
                
        if complete_or_create == "Create New":
            remove_features(self.user_swmm_conduits_lyr)
        
        if storm_drain.INP_conduits:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                """
                Creates Storm Drain Conduits layer (Users layers)
        
                Creates "user_swmm_conduits" layer with attributes taken from
                the [CONDUITS], [LOSSES], and [XSECTIONS] groups.
        
                """
        
                # Transfer data from "storm_drain.INP_dict" to "user_swmm_conduits" layer:
                replace_user_swmm_conduits_sql = """UPDATE user_swmm_conduits
                                 SET   conduit_inlet  = ?,
                                       conduit_outlet  = ?,
                                       conduit_length  = ?,
                                       conduit_manning  = ?,
                                       conduit_inlet_offset  = ?,
                                       conduit_outlet_offset  = ?,
                                       conduit_init_flow  = ?,
                                       conduit_max_flow  = ?,
                                       losses_inlet  = ?,
                                       losses_outlet  = ?,
                                       losses_average  = ?,
                                       losses_flapgate  = ?,
                                       xsections_shape  = ?,
                                       xsections_barrels  = ?,
                                       xsections_max_depth  = ?,
                                       xsections_geom2  = ?,
                                       xsections_geom3  = ?,
                                       xsections_geom4  = ?
                                 WHERE conduit_name = ?;"""
        
                fields = self.user_swmm_conduits_lyr.fields()       
                for name, values in list(storm_drain.INP_conduits.items()):
        
                    conduit_inlet = values["conduit_inlet"] if "conduit_inlet" in values else None
                    conduit_outlet = values["conduit_outlet"] if "conduit_outlet" in values else None
                    conduit_length = float_or_zero(values["conduit_length"]) if "conduit_length" in values else 0
                    conduit_manning = float_or_zero(values["conduit_manning"]) if "conduit_manning" in values else 0
                    conduit_inlet_offset = (
                        float_or_zero(values["conduit_inlet_offset"]) if "conduit_inlet_offset" in values else 0
                    )
                    conduit_outlet_offset = (
                        float_or_zero(values["conduit_outlet_offset"]) if "conduit_outlet_offset" in values else 0
                    )
                    conduit_init_flow = (
                        float_or_zero(values["conduit_init_flow"]) if "conduit_init_flow" in values else 0
                    )
                    conduit_max_flow = float_or_zero(values["conduit_max_flow"]) if "conduit_max_flow" in values else 0
        
                    conduit_losses_inlet = float_or_zero(values["losses_inlet"]) if "losses_inlet" in values else 0
                    conduit_losses_outlet = float_or_zero(values["losses_outlet"]) if "losses_outlet" in values else 0
                    conduit_losses_average = (
                        float_or_zero(values["losses_average"]) if "losses_average" in values else 0
                    )
        
                    conduit_losses_flapgate = values["losses_flapgate"] if "losses_flapgate" in values else "False"
                    conduit_losses_flapgate = "True" if is_true(conduit_losses_flapgate) else "False"
        
                    conduit_xsections_shape = values["xsections_shape"] if "xsections_shape" in values else "CIRCULAR"
                    conduit_xsections_barrels = (
                        float_or_zero(values["xsections_barrels"]) if "xsections_barrels" in values else 0
                    )
                    conduit_xsections_max_depth = (
                        float_or_zero(values["xsections_max_depth"]) if "xsections_max_depth" in values else 0
                    )
                    conduit_xsections_geom2 = (
                        float_or_zero(values["xsections_geom2"]) if "xsections_geom2" in values else 0
                    )
                    conduit_xsections_geom3 = (
                        float_or_zero(values["xsections_geom3"]) if "xsections_geom3" in values else 0
                    )
                    conduit_xsections_geom4 = (
                        float_or_zero(values["xsections_geom4"]) if "xsections_geom4" in values else 0
                    )
        
                    feat = QgsFeature()
                    feat.setFields(fields)

                    if not conduit_inlet in self.all_nodes:
                        conduit_inlets_not_found += "      " +  name + "\n"
                    else:
                        if "x" in self.all_nodes[conduit_inlet] and "x" in self.all_nodes[conduit_inlet]:
                            x1 = float(self.all_nodes[conduit_inlet]["x"])
                            y1 = float(self.all_nodes[conduit_inlet]["y"])                        
                            grid = self.gutils.grid_on_point(x1, y1)
                            if grid is None:
                                if not name in outside_conduits:
                                    outside_conduits += n_spaces + name + "\n"
                        else:
                            if not name in outside_conduits:
                                outside_conduits += n_spaces + name + "\n"                                       
                                    
                    if not conduit_outlet in self.all_nodes:
                        conduit_outlets_not_found += "      " +  name + "\n"
                    else:
                        if "x" in self.all_nodes[conduit_outlet] and "y" in self.all_nodes[conduit_outlet]:
                            x2 = float(self.all_nodes[conduit_outlet]["x"])
                            y2 = float(self.all_nodes[conduit_outlet]["y"])
                            grid = self.gutils.grid_on_point(x2, y2)
                            if grid is None:
                                if not name in outside_conduits:
                                    outside_conduits += n_spaces + name + "\n"
                        else:
                            conduit_outlets_not_found += "      " +  name + "\n" 
                                        
        
                    if conduit_inlet in self.all_nodes and conduit_outlet in self.all_nodes:
                        geom = QgsGeometry.fromPolylineXY([QgsPointXY(x1, y1), QgsPointXY(x2, y2)])
                    else:
                        continue
                    
                    if complete_or_create == "Create New":
                        feat.setGeometry(geom)
            
                        feat.setAttribute("conduit_name", name)
                        feat.setAttribute("conduit_inlet", conduit_inlet)
                        feat.setAttribute("conduit_outlet", conduit_outlet)
                        feat.setAttribute("conduit_length", conduit_length)
                        feat.setAttribute("conduit_manning", conduit_manning)
                        feat.setAttribute("conduit_inlet_offset", conduit_inlet_offset)
                        feat.setAttribute("conduit_outlet_offset", conduit_outlet_offset)
                        feat.setAttribute("conduit_init_flow", conduit_init_flow)
                        feat.setAttribute("conduit_max_flow", conduit_max_flow)
            
                        feat.setAttribute("losses_inlet", conduit_losses_inlet)
                        feat.setAttribute("losses_outlet", conduit_losses_outlet)
                        feat.setAttribute("losses_average", conduit_losses_average)
                        feat.setAttribute("losses_flapgate", conduit_losses_flapgate)
            
                        feat.setAttribute("xsections_shape", conduit_xsections_shape)
                        feat.setAttribute("xsections_barrels", conduit_xsections_barrels)
                        feat.setAttribute("xsections_max_depth", conduit_xsections_max_depth)
                        feat.setAttribute("xsections_geom2", conduit_xsections_geom2)
                        feat.setAttribute("xsections_geom3", conduit_xsections_geom3)
                        feat.setAttribute("xsections_geom4", conduit_xsections_geom4)
            
                        new_conduits.append(feat)
                
                    else:  # Keep some existing data in user_swmm_conduits (e.g swmm_length, swmm_width, etc.)
                        # See if name is in user_swmm_conduits:                     
                        fid = self.gutils.execute("SELECT fid FROM user_swmm_conduits WHERE conduit_name = ?;", (name,)).fetchone()
                        if fid:  # name already in user_swmm_conduits
                                self.gutils.execute(
                                    replace_user_swmm_conduits_sql,
                                    (
                                        conduit_inlet,
                                        conduit_outlet,
                                        conduit_length,
                                        conduit_manning,
                                        conduit_inlet_offset,
                                        conduit_outlet_offset,
                                        conduit_init_flow,
                                        conduit_max_flow,
                                        conduit_losses_inlet,
                                        conduit_losses_outlet,
                                        conduit_losses_average,
                                        conduit_losses_flapgate,
                                        conduit_xsections_shape,
                                        conduit_xsections_barrels,
                                        conduit_xsections_max_depth,
                                        conduit_xsections_geom2,
                                        conduit_xsections_geom3,
                                        conduit_xsections_geom4,            
                                        name,
                                    ),
                                )
                                updated_conduits += 1                        
                        else:                         
                            
                            feat.setGeometry(geom)
                
                            feat.setAttribute("conduit_name", name)
                            feat.setAttribute("conduit_inlet", conduit_inlet)
                            feat.setAttribute("conduit_outlet", conduit_outlet)
                            feat.setAttribute("conduit_length", conduit_length)
                            feat.setAttribute("conduit_manning", conduit_manning)
                            feat.setAttribute("conduit_inlet_offset", conduit_inlet_offset)
                            feat.setAttribute("conduit_outlet_offset", conduit_outlet_offset)
                            feat.setAttribute("conduit_init_flow", conduit_init_flow)
                            feat.setAttribute("conduit_max_flow", conduit_max_flow)
                
                            feat.setAttribute("losses_inlet", conduit_losses_inlet)
                            feat.setAttribute("losses_outlet", conduit_losses_outlet)
                            feat.setAttribute("losses_average", conduit_losses_average)
                            feat.setAttribute("losses_flapgate", conduit_losses_flapgate)
                
                            feat.setAttribute("xsections_shape", conduit_xsections_shape)
                            feat.setAttribute("xsections_barrels", conduit_xsections_barrels)
                            feat.setAttribute("xsections_max_depth", conduit_xsections_max_depth)
                            feat.setAttribute("xsections_geom2", conduit_xsections_geom2)
                            feat.setAttribute("xsections_geom3", conduit_xsections_geom3)
                            feat.setAttribute("xsections_geom4", conduit_xsections_geom4)
                
                            new_conduits.append(feat)
        
                if len(new_conduits) != 0:
                    self.user_swmm_conduits_lyr.startEditing()
                    self.user_swmm_conduits_lyr.addFeatures(new_conduits)
                    self.user_swmm_conduits_lyr.commitChanges()
                    self.user_swmm_conduits_lyr.updateExtents()
                    self.user_swmm_conduits_lyr.triggerRepaint()
                    self.user_swmm_conduits_lyr.removeSelection()
        
            except Exception as e:
                QApplication.setOverrideCursor(Qt.ArrowCursor)
                self.uc.show_error("ERROR 050618.1804: creation of Storm Drain Conduits layer failed!", e)
                QApplication.restoreOverrideCursor()
            finally:
                QApplication.restoreOverrideCursor() 

        # PUMPS: Create User Pumps layer:
        pump_inlets_not_found = ""
        pump_outlets_not_found = ""
        pump_data_missing = ""

        if complete_or_create == "Create New":
            remove_features(self.user_swmm_pumps_lyr)

        if storm_drain.INP_pumps:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                """
                Creates Storm Drain Pumps layer (Users layers)

                Creates "user_swmm_pumps" layer with attributes taken from
                the [PUMPS], and [CURVES] groups.

                """

                replace_user_swmm_pumps_sql = """UPDATE user_swmm_pumps
                                 SET   pump_inlet  = ?,
                                       pump_outlet  = ?,
                                       pump_curve  = ?,
                                       pump_init_status  = ?,
                                       pump_startup_depth  = ?,
                                       pump_shutoff_depth  = ?
                                 WHERE pump_name = ?;"""

                fields = self.user_swmm_pumps_lyr.fields()
                for name, values in list(storm_drain.INP_pumps.items()):
                    
                    if values["pump_shutoff_depth"] == None:
                        pump_data_missing = "\nError(s) in [PUMP] group. Are values missing?"
                        continue
                    
                    pump_inlet = values["pump_inlet"] if "pump_inlet" in values else None
                    pump_outlet = values["pump_outlet"] if "pump_outlet" in values else None
                    pump_curve = values["pump_curve"] if "pump_curve" in values else None
                    pump_init_status = values["pump_init_status"] if "pump_init_status" in values else "OFF"
                    pump_startup_depth = (
                        float_or_zero(values["pump_startup_depth"]) if "pump_startup_depth" in values else 0.0
                    )
                    pump_shutoff_depth = (
                        float_or_zero(values["pump_shutoff_depth"]) if "pump_shutoff_depth" in values else 0.0
                    )

                    feat = QgsFeature()
                    feat.setFields(fields)

                    if not pump_inlet in self.all_nodes:
                        pump_inlets_not_found += "      " + name + "\n"
                    else:
                        if "x" in self.all_nodes[pump_inlet] and "y" in self.all_nodes[pump_inlet]:
                            x1 = float(self.all_nodes[pump_inlet]["x"])
                            y1 = float(self.all_nodes[pump_inlet]["y"])                        
                            grid = self.gutils.grid_on_point(x1, y1)
                            if grid is None:
                                if not name in outside_pumps:
                                    outside_pumps += n_spaces + name + "\n"
                        else:
                            if not name in outside_pumps:
                                outside_pumps += n_spaces + name + "\n"                                        

                    if not pump_outlet in self.all_nodes:
                        pump_outlets_not_found += "      " +  name + "\n"
                    else:
                        if "x" in self.all_nodes[pump_outlet] and "y" in self.all_nodes[pump_outlet]:
                            x2 = float(self.all_nodes[pump_outlet]["x"])
                            y2 = float(self.all_nodes[pump_outlet]["y"])
                            grid = self.gutils.grid_on_point(x2, y2)
                            if grid is None:
                                if not name in outside_pumps:
                                    outside_pumps += n_spaces + name + "\n"
                        else:
                            pump_outlets_not_found += "      " +  name + "\n" 

                    if pump_inlet in self.all_nodes and pump_outlet in self.all_nodes:
                        geom = QgsGeometry.fromPolylineXY([QgsPointXY(x1, y1), QgsPointXY(x2, y2)])
                    else:
                        continue

                    if complete_or_create == "Create New":
                        feat.setGeometry(geom)
                        
                        feat.setAttribute("pump_name", name)
                        feat.setAttribute("pump_inlet", pump_inlet)
                        feat.setAttribute("pump_outlet", pump_outlet)
                        feat.setAttribute("pump_curve", pump_curve)
                        feat.setAttribute("pump_init_status", pump_init_status)
                        feat.setAttribute("pump_startup_depth", pump_startup_depth)
                        feat.setAttribute("pump_shutoff_depth", pump_shutoff_depth)
    
                        new_pumps.append(feat)

                    else:  # Keep some existing data in user_swmm_pumps (e.g pump_curve, etc.)
                        # See if name is in user_swmm_pumps:                     
                        fid = self.gutils.execute("SELECT fid FROM user_swmm_pumps WHERE pump_name = ?;", (name,)).fetchone()
                        if fid:  # name already in user_swmm_pumps
                                self.gutils.execute(
                                    replace_user_swmm_pumps_sql,
                                    ( 
                                        pump_inlet,
                                        pump_outlet,
                                        pump_curve,
                                        pump_init_status,
                                        pump_startup_depth,
                                        pump_shutoff_depth,                                                   
                                        name,
                                    ),
                                )
                                updated_pumps += 1                        
                        else:                         
                            feat.setGeometry(geom)

                            feat.setAttribute("pump_name", name)
                            feat.setAttribute("pump_inlet", pump_inlet)
                            feat.setAttribute("pump_outlet", pump_outlet)
                            feat.setAttribute("pump_curve", pump_curve)
                            feat.setAttribute("pump_init_status", pump_init_status)
                            feat.setAttribute("pump_startup_depth", pump_startup_depth)
                            feat.setAttribute("pump_shutoff_depth", pump_shutoff_depth)
        
                            new_pumps.append(feat)
                        
                if len(new_pumps) != 0:
                    self.user_swmm_pumps_lyr.startEditing()
                    self.user_swmm_pumps_lyr.addFeatures(new_pumps)
                    self.user_swmm_pumps_lyr.commitChanges()
                    self.user_swmm_pumps_lyr.updateExtents()
                    self.user_swmm_pumps_lyr.triggerRepaint()
                    self.user_swmm_pumps_lyr.removeSelection()

            except Exception as e:
                QApplication.setOverrideCursor(Qt.ArrowCursor)
                self.uc.show_error("ERROR 050618.1805: creation of Storm Drain Pumps layer failed!", e)
                QApplication.restoreOverrideCursor()
            finally:
                QApplication.restoreOverrideCursor()

        # ORIFICES: Create User Orifices layer:
        orifice_inlets_not_found = ""
        orifice_outlets_not_found = ""

        if complete_or_create == "Create New":
            remove_features(self.user_swmm_orifices_lyr)

        if storm_drain.INP_orifices:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                """
                Creates Storm Drain Orifices layer (Users layers)

                Creates "user_swmm_orifice" layer with attributes taken from
                the [ORIFICES], and [XSECTIONS] groups.

                """

                replace_user_swmm_orificies_sql = """UPDATE user_swmm_orifices
                                 SET   orifice_inlet  = ?,
                                       orifice_outlet  = ?,
                                       orifice_type  = ?,
                                       orifice_crest_height  = ?,
                                       orifice_disch_coeff  = ?,
                                       orifice_flap_gate  = ?,
                                       orifice_open_close_time  = ?,
                                       orifice_shape  = ?,
                                       orifice_height  = ?,
                                       orifice_width  = ?
                                 WHERE orifice_name = ?;"""
                                 
                fields = self.user_swmm_orifices_lyr.fields()
                for name, values in list(storm_drain.INP_orifices.items()):
                    orifice_inlet = values["ori_inlet"] if "ori_inlet" in values else None
                    orifice_outlet = values["ori_outlet"] if "ori_outlet" in values else None
                    orifice_type = values["ori_type"] if "ori_type" in values else "SIDE"
                    orifice_crest_height = (
                        float_or_zero(values["ori_crest_height"]) if "ori_crest_height" in values else 0.0
                    )
                    orifice_disch_coeff = (
                        float_or_zero(values["ori_disch_coeff"]) if "ori_disch_coeff" in values else 0.0
                    )
                    orifice_flap_gate = values["ori_flap_gate"] if "ori_flap_gate" in values else "NO"
                    orifice_open_close_time = (
                        float_or_zero(values["ori_open_close_time"]) if "ori_open_close_time" in values else 0.0
                    )
                    orifice_shape = values["xsections_shape"] if "xsections_shape" in values else "CIRCULAR"
                    orifice_height = float_or_zero(values["xsections_height"]) if "xsections_height" in values else 0.0
                    orifice_width = float_or_zero(values["xsections_width"]) if "xsections_width" in values else 0.0

                    feat = QgsFeature()
                    feat.setFields(fields)
                    
                    if not orifice_inlet in self.all_nodes:
                        orifice_inlets_not_found += "      " +  name + "\n"
                    else:
                        if "x" in self.all_nodes[orifice_inlet] and "y" in self.all_nodes[orifice_inlet]:
                            x1 = float(self.all_nodes[orifice_inlet]["x"])
                            y1 = float(self.all_nodes[orifice_inlet]["y"])                        
                            grid = self.gutils.grid_on_point(x1, y1)
                            if grid is None:
                                if not name in outside_orifices:
                                    outside_orifices += n_spaces + name + "\n"
                        else:
                            if not name in outside_orifices:
                                outside_orifices += n_spaces + name + "\n"                                        

                    if not orifice_outlet in self.all_nodes:
                        orifice_outlets_not_found += "      " +  name + "\n"
                    else:
                        if "x" in self.all_nodes[orifice_outlet] and "y" in self.all_nodes[orifice_outlet]:
                            x2 = float(self.all_nodes[orifice_outlet]["x"])
                            y2 = float(self.all_nodes[orifice_outlet]["y"])
                            grid = self.gutils.grid_on_point(x2, y2)
                            if grid is None:
                                if not name in outside_orifices:
                                    outside_orifices += n_spaces + name + "\n"
                        else:
                            orifice_outlets_not_found += "      " +  name + "\n" 
                                        
                    if orifice_inlet in self.all_nodes and orifice_outlet in self.all_nodes:
                        geom = QgsGeometry.fromPolylineXY([QgsPointXY(x1, y1), QgsPointXY(x2, y2)])
                    else:
                        continue

                    if complete_or_create == "Create New":
                        feat.setGeometry(geom)
                        
                        feat.setAttribute("orifice_name", name)
                        feat.setAttribute("orifice_inlet", orifice_inlet)
                        feat.setAttribute("orifice_outlet", orifice_outlet)
                        feat.setAttribute("orifice_type", orifice_type)
                        feat.setAttribute("orifice_crest_height", orifice_crest_height)
                        feat.setAttribute("orifice_disch_coeff", orifice_disch_coeff)
                        feat.setAttribute("orifice_flap_gate", orifice_flap_gate)
                        feat.setAttribute("orifice_open_close_time", orifice_open_close_time)
                        feat.setAttribute("orifice_shape", orifice_shape)
                        feat.setAttribute("orifice_height", orifice_height)
                        feat.setAttribute("orifice_width", orifice_width)
    
                        new_orifices.append(feat)
                
                    else:  # Keep some existing data in user_swmm_orifices (e.g orifice_type, orifice_crest_height, etc.)
                        # See if name is in user_swmm_orifices:                     
                        fid = self.gutils.execute("SELECT fid FROM user_swmm_orifices WHERE orifice_name = ?;", (name,)).fetchone()
                        if fid:  # name already in user_swmm_orifices
                                self.gutils.execute(
                                    replace_user_swmm_orificies_sql,
                                    ( 
                                       orifice_inlet,
                                       orifice_outlet,
                                       orifice_type,
                                       orifice_crest_height,
                                       orifice_disch_coeff,
                                       orifice_flap_gate,
                                       orifice_open_close_time,
                                       orifice_shape,
                                       orifice_height,
                                       orifice_width,
                                       name,
                                    ),
                                )
                                updated_orifices += 1                        
                        else:                         
                            feat.setGeometry(geom)

                            feat.setAttribute("orifice_name", name)
                            feat.setAttribute("orifice_inlet", orifice_inlet)
                            feat.setAttribute("orifice_outlet", orifice_outlet)
                            feat.setAttribute("orifice_type", orifice_type)
                            feat.setAttribute("orifice_crest_height", orifice_crest_height)
                            feat.setAttribute("orifice_disch_coeff", orifice_disch_coeff)
                            feat.setAttribute("orifice_flap_gate", orifice_flap_gate)
                            feat.setAttribute("orifice_open_close_time", orifice_open_close_time)
                            feat.setAttribute("orifice_shape", orifice_shape)
                            feat.setAttribute("orifice_height", orifice_height)
                            feat.setAttribute("orifice_width", orifice_width)
        
                            new_orifices.append(feat)

                if len(new_orifices) != 0:
                    self.user_swmm_orifices_lyr.startEditing()
                    self.user_swmm_orifices_lyr.addFeatures(new_orifices)
                    self.user_swmm_orifices_lyr.commitChanges()
                    self.user_swmm_orifices_lyr.updateExtents()
                    self.user_swmm_orifices_lyr.triggerRepaint()
                    self.user_swmm_orifices_lyr.removeSelection()

            except Exception as e:
                QApplication.setOverrideCursor(Qt.ArrowCursor)
                self.uc.show_error("ERROR 310322.0853: creation of Storm Drain Orifices layer failed!", e)
                QApplication.restoreOverrideCursor()
            finally:
                QApplication.restoreOverrideCursor() 

        # WEIRS: Create User Weirs layer:
        weir_inlets_not_found = ""
        weir_outlets_not_found = ""

        if complete_or_create == "Create New":
            remove_features(self.user_swmm_weirs_lyr)

        if storm_drain.INP_weirs:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                """
                Creates Storm Drain Weirs layer (Users layers)

                Creates "user_swmm_weirs" layer with attributes taken from
                the [WEIRS], and [XSECTIONS] groups.

                """
                replace_user_swmm_weirs_sql = """UPDATE user_swmm_weirs
                                 SET   weir_inlet  = ?,
                                       weir_outlet  = ?,
                                       weir_type = ?,
                                       weir_crest_height = ?,
                                       weir_disch_coeff = ?,
                                       weir_flap_gate = ?,
                                       weir_end_contrac = ?,
                                       weir_end_coeff = ?,
                                       weir_shape = ?,
                                       weir_height = ?,
                                       weir_length = ?,
                                       weir_side_slope = ?
                                 WHERE weir_name = ?;"""

                fields = self.user_swmm_weirs_lyr.fields()
                for name, values in list(storm_drain.INP_weirs.items()):

                    weir_inlet = values["weir_inlet"] if "weir_inlet" in values else None
                    weir_outlet = values["weir_outlet"] if "weir_outlet" in values else None
                    weir_type = values["weir_type"] if "weir_type" in values else "TRANSVERSE"
                    weir_crest_height = (
                        float_or_zero(values["weir_crest_height"]) if "weir_crest_height" in values else 0.0
                    )
                    weir_disch_coeff = (
                        float_or_zero(values["weir_disch_coeff"]) if "weir_disch_coeff" in values else 0.0
                    )
                    weir_flap = values["weir_flap_gate"] if "weir_flap_gate" in values else "NO"
                    weir_end_contrac = int_or_zero(values["weir_end_contrac"]) if "weir_end_contrac" in values else 0
                    weir_end_coeff = float_or_zero(values["weir_end_coeff"]) if "weir_end_coeff" in values else 0.0
                    weir_shape = values["xsections_shape"] if "xsections_shape" in values else "RECT_CLOSED"
                    weir_height = float_or_zero(values["xsections_height"]) if "xsections_height" in values else 0.0
                    weir_length = float_or_zero(values["xsections_width"]) if "xsections_width" in values else 0.0
                    weir_side_slope = float_or_zero(values["xsections_geom3"]) if "xsections_geom3" in values else 0.0

                    feat = QgsFeature()
                    feat.setFields(fields)

                    if not weir_inlet in self.all_nodes:
                        weir_inlets_not_found += "      " +  name + "\n"
                    else:
                        if "x" in self.all_nodes[weir_inlet] and "y" in self.all_nodes[weir_inlet]:
                            x1 = float(self.all_nodes[weir_inlet]["x"])
                            y1 = float(self.all_nodes[weir_inlet]["y"])                        
                            grid = self.gutils.grid_on_point(x1, y1)
                            if grid is None:
                                if not name in outside_weirs:
                                    outside_weirs += n_spaces + name + "\n"
                        else:
                            if not name in outside_weirs:
                                outside_weirs += n_spaces + name + "\n"                                        

                    if not weir_outlet in self.all_nodes:
                        weir_outlets_not_found += "      " +  name + "\n"
                    else:
                        if "x" in self.all_nodes[weir_outlet] and "y" in self.all_nodes[weir_outlet]:
                            x2 = float(self.all_nodes[weir_outlet]["x"])
                            y2 = float(self.all_nodes[weir_outlet]["y"])
                            grid = self.gutils.grid_on_point(x2, y2)
                            if grid is None:
                                if not name in outside_weirs:
                                    outside_weirs += n_spaces + name + "\n"
                        else:
                            weir_outlets_not_found += "      " +  name + "\n" 
                                      
                    if weir_inlet in self.all_nodes and weir_outlet in self.all_nodes:
                        geom = QgsGeometry.fromPolylineXY([QgsPointXY(x1, y1), QgsPointXY(x2, y2)])
                    else:
                        continue

                    if complete_or_create == "Create New":
                        feat.setGeometry(geom)
                        
                        feat.setAttribute("weir_name", name)
                        feat.setAttribute("weir_inlet", weir_inlet)
                        feat.setAttribute("weir_outlet", weir_outlet)
                        feat.setAttribute("weir_type", weir_type)
                        feat.setAttribute("weir_crest_height", weir_crest_height)
                        feat.setAttribute("weir_disch_coeff", weir_disch_coeff)
                        feat.setAttribute("weir_flap_gate", weir_flap)
                        feat.setAttribute("weir_end_contrac", weir_end_contrac)
                        feat.setAttribute("weir_end_coeff", weir_end_coeff)
                        feat.setAttribute("weir_shape", weir_shape)
                        feat.setAttribute("weir_height", weir_height)
                        feat.setAttribute("weir_length", weir_length)
                        feat.setAttribute("weir_side_slope", weir_side_slope)
    
                        new_weirs.append(feat)

                    else:  # Keep some existing data in user_swmmm_weirs (e.g weir_crest_height, etc.)
                        # See if name is in user_swmm_weirs:                     
                        fid = self.gutils.execute("SELECT fid FROM user_swmm_weirs WHERE weir_name = ?;", (name,)).fetchone()
                        if fid:  # name already in user_swmm_weirs
                                self.gutils.execute(
                                    replace_user_swmm_weirs_sql,
                                    ( 
                                        weir_inlet,
                                        weir_outlet,
                                        weir_type,
                                        weir_crest_height,
                                        weir_disch_coeff,
                                        weir_flap,
                                        weir_end_contrac,
                                        weir_end_coeff,
                                        weir_shape,
                                        weir_height,
                                        weir_length,
                                        weir_side_slope,                                               
                                        name,
                                    ),
                                )
                                updated_weirs += 1                        
                        else:                         
                            feat.setGeometry(geom)

                            feat.setAttribute("weir_name", name)
                            feat.setAttribute("weir_inlet", weir_inlet)
                            feat.setAttribute("weir_outlet", weir_outlet)
                            feat.setAttribute("weir_type", weir_type)
                            feat.setAttribute("weir_crest_height", weir_crest_height)
                            feat.setAttribute("weir_disch_coeff", weir_disch_coeff)
                            feat.setAttribute("weir_flap_gate", weir_flap)
                            feat.setAttribute("weir_end_contrac", weir_end_contrac)
                            feat.setAttribute("weir_end_coeff", weir_end_coeff)
                            feat.setAttribute("weir_shape", weir_shape)
                            feat.setAttribute("weir_height", weir_height)
                            feat.setAttribute("weir_length", weir_length)
                            feat.setAttribute("weir_side_slope", weir_side_slope)
        
                            new_weirs.append(feat)

                if len(new_weirs) != 0:
                    self.user_swmm_weirs_lyr.startEditing()
                    self.user_swmm_weirs_lyr.addFeatures(new_weirs)
                    self.user_swmm_weirs_lyr.commitChanges()
                    self.user_swmm_weirs_lyr.updateExtents()
                    self.user_swmm_weirs_lyr.triggerRepaint()
                    self.user_swmm_weirs_lyr.removeSelection()

            except Exception as e:
                QApplication.setOverrideCursor(Qt.ArrowCursor)
                self.uc.show_error("ERROR 080422.1115: creation of Storm Drain Weirs layer failed!", e)
                QApplication.restoreOverrideCursor()
            finally:
                QApplication.restoreOverrideCursor() 
                
        if (
            complete_or_create == "Create New"
            and len(new_nodes) == 0
            and len(new_storages) == 0
            and len(new_conduits) == 0
            and len(new_pumps) == 0
            and len(new_orifices) == 0
            and len(new_weirs) == 0
        ):
            error_msg += "\nThere are no nodes or links inside the domain of this project."

        if conduit_inlets_not_found != "":
            error_msg += "\n\nThe following conduits have no inlet defined!\n" + conduit_inlets_not_found

        if conduit_outlets_not_found != "":
            error_msg += "\n\nThe following conduits have no outlet defined!\n" + conduit_outlets_not_found

        if pump_data_missing != "":
            error_msg += "\n" + pump_data_missing

        if pump_inlets_not_found != "":
            error_msg += "\n\nThe following pumps have no inlet defined!\n" + pump_inlets_not_found

        if pump_outlets_not_found != "":
            error_msg += "\n\nThe following pumps have no outlet defined!\n" + pump_outlets_not_found

        if orifice_inlets_not_found != "":
            error_msg += "\n\nThe following orifices have no inlet defined!\n" + orifice_inlets_not_found

        if orifice_outlets_not_found != "":
            error_msg += "\n\nThe following orifices have no outlet defined!\n" + orifice_outlets_not_found

        if weir_inlets_not_found != "":
            error_msg += "\n\nThe following weirs have no inlet defined!\n" + weir_inlets_not_found

        if weir_outlets_not_found != "":
            error_msg += "\n\nThe following weirs have no outlet defined!\n" + weir_outlets_not_found

        if error_msg != "ERROR 050322.9423: error(s) importing file\n\n" + swmm_file:
            self.uc.show_critical(error_msg)

        QApplication.setOverrideCursor(Qt.ArrowCursor)
        if complete_or_create == "Create New":
            self.uc.show_info(
                "Importing Storm Drain data finished!\n\n"
                + "* "
                + str(len(new_nodes))
                + " Nodes (inlets, junctions, and outfalls) were created in the 'Storm Drain Nodes' layer ('User Layers' group), and\n\n"
                + "* "
                + str(len(new_storages))
                + " Storage Units in the 'Storm Drain Storage Units' layer ('User Layers' group), and\n\n"
                + "* "                
                + str(len(new_conduits))
                + " Conduits in the 'Storm Drain Conduits' layer ('User Layers' group), and\n\n"
                + "* "
                + str(len(new_pumps))
                + " Pumps in the 'Storm Drain Pumps' layer ('User Layers' group). \n\n"
                + "* "
                + str(len(new_orifices))
                + " Orifices in the 'Storm Drain Orifices' layer ('User Layers' group). \n\n"
                + "* "
                + str(len(new_weirs))
                + " Weirs in the 'Storm Drain Weirs' layer ('User Layers' group). \n\n"
                "Click the 'Inlets/Junctions', 'Outfalls', 'Conduits', 'Pumps', 'Orifices', and 'Weirs' buttons in the Storm Drain Editor widget to see or edit their attributes.\n\n"
                "NOTE: the 'Schematize Storm Drain Components' button  in the Storm Drain Editor widget will update the 'Storm Drain' layer group, required to "
                "later export the .DAT files used by the FLO-2D model."
            )
        
        elif show_end_message:
            self.uc.show_info(
                "Storm Drain data was updated from file\n"
                + swmm_file
                + "\n\n"
                + "* "
                + str(updated_nodes)
                + " Nodes (inlets, junctions, and outfalls) in the 'Storm Drain Nodes' layer ('User Layers' group) were updated, and\n\n"
                + "* "
                + str(updated_storages)
                + " Storage Units in the 'Storm Drain Storage Units' layer ('User Layers' group) were updated, and\n\n"
                + "* "                
                + str(updated_conduits)
                + " Conduits in the 'Storm Drain Conduits' layer ('User Layers' group) were updated, and\n"
                + "  " + str(len(new_conduits)) + " new conduits created.\n\n"
                + "* "
                + str(updated_pumps)
                + " Pumps in the 'Storm Drain Pumps' layer ('User Layers' group) were updated, and\n"
                + "  " + str(len(new_pumps)) + " new pumps created.\n\n"
                + "* "
                + str(updated_orifices)
                + " Orifices in the 'Storm Drain Orifices' layer ('User Layers' group) were updated, and\n"
                + "  " + str(len(new_orifices)) + " new orifices created.\n\n"
                + "* "                
                + str(updated_weirs)
                + " Weirs in the 'Storm Drain Weirs' layer ('User Layers' group) were updated, and\n"
                + "  " + str(len(new_weirs)) + " new weirs created.\n\n"                
                "Click the 'Inlets/Junctions', 'Outfalls', 'Conduits', 'Pumps', 'Orifices', and 'Weirs' buttons in the Storm Drain Editor widget to see or edit their attributes.\n\n"
                "NOTE: the 'Schematize Storm Drain Components' button  in the Storm Drain Editor widget will update the 'Storm Drain' layer group, required to "
                "later export the .DAT files used by the FLO-2D model."
            )


        node_items = outside_nodes + outside_storages
        if len(node_items) > 0:
            node_items = ("Inlets/Junctions/Outflows:\n"  + outside_nodes if len(outside_nodes) > 0 else  "") + \
                    ("Storage Units:\n" + outside_storages if len(outside_storages) > 0 else "") 
            
            node_items = "WARNING 221220.0336:\nPoints with no coordinates or outside the domain:\n\n" + node_items
            msgBox = QMessageBox()
            msgBox.setIcon(QMessageBox.Warning)
            msgBox.setWindowTitle("Problematic Storm Drain points")
            msgBox.setStandardButtons(QMessageBox.Close)  # Close button instead of OK
            layout = QHBoxLayout()
            label = QLabel(node_items)
            layout.addWidget(label)
            msgBox.layout().addWidget(label)           
            msgBox.exec_()   

        link_items = outside_conduits + outside_pumps + outside_orifices +  outside_weirs 
        if len(link_items) > 0:
            link_items = ("Conduits:\n"  + outside_conduits if len(outside_conduits) > 0 else  "") + \
                    ("Pumps:\n" + outside_pumps if len(outside_pumps) > 0 else "") + \
                    ("Orifices:\n" + outside_orifices if len(outside_orifices) > 0 else "") + \
                    ("Weirs:\n" + outside_weirs  if len(outside_weirs) > 0 else "")  

            link_items = "WARNING 221220.0337:\nThe following links extend outside the domain:\n\n" + link_items                                          
            msgBox = QMessageBox()
            msgBox.setIcon(QMessageBox.Warning)
            msgBox.setWindowTitle("Storm Drain links outside domain")
            msgBox.setStandardButtons(QMessageBox.Close)  # Close button instead of OK
            layout = QHBoxLayout()
            label = QLabel(link_items)
            layout.addWidget(label)
            msgBox.layout().addWidget(label)           
            msgBox.exec_()

        if storm_drain.status_report:
            result2 = ScrollMessageBox2(QMessageBox.Warning, "Storm Drain import status", storm_drain.status_report)
            result2.exec_()
            
        if skipped_inlets != 0:
            self.uc.show_warn("File " + Path(swmm_file).name + " has [SUBCATCHMENTS].\n\n" + 
                              str(skipped_inlets) + " inlets with 'I' or 'i' name prefix were skipped.\n\n"
                              "WARNING: there may be conduits that reference those inlets.")                

        self.populate_pump_curves_combo(False)
        self.pump_curve_cbo.blockSignals(True)
        self.update_pump_curve_data()
        self.pump_curve_cbo.blockSignals(False)
        
        QApplication.restoreOverrideCursor()
        return True

    def import_INP_action(self):
        msg = QMessageBox()
        msg.setWindowTitle("Replace or complete Storm Drain User Data")
        msg.setText(
            "There is already Storm Drain data in the Users Layers.\n\nWould you like to keep it and complete it with data taken from the .INP file?\n\n"
            + "or you prefer to erase it and create new storm drains from the .INP file?\n"
        )

        msg.addButton(QPushButton("Keep existing and complete"), QMessageBox.YesRole)
        msg.addButton(QPushButton("Create new Storm Drains"), QMessageBox.NoRole)
        msg.addButton(QPushButton("Cancel"), QMessageBox.RejectRole)
        msg.setDefaultButton(QMessageBox().Cancel)
        msg.setIcon(QMessageBox.Question)
        ret = msg.exec_()
        if ret == 0:
            return "Keep and Complete"
        elif ret == 1:
            return "Create New"
        else:
            return "Cancel"

    def export_storm_drain_INP_file(self, hdf5_dir=None, hdf5_file=None):
        """
        Writes <name>.INP file
        (<name> exists or is given by user in initial file dialog).

        The following groups are always written with the data of the current project:
            [JUNCTIONS] [OUTFALLS] [CONDUITS] [XSECTIONS] [LOSSES] [COORDINATES]
        All other groups are written from data of .INP file if they exist.
        """

        try:
            self.uc.clear_bar_messages()

            if self.gutils.is_table_empty("user_swmm_nodes"):
                self.uc.show_warn(
                    'User Layer "Storm Drain Nodes" is empty!\n\n'
                    + "Please import components from .INP file or shapefile, or convert from schematized Storm Drains."
                )
                return

            INP_groups = OrderedDict()

            s = QSettings()
            last_dir = s.value("FLO-2D/lastGdsDir", "")
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            if not hdf5_dir and not hdf5_file:
                swmm_dir = QFileDialog.getExistingDirectory(
                    None,
                    "Select directory where SWMM.INP file will be exported",
                    directory=last_dir,
                    options=QFileDialog.ShowDirsOnly,
                )
                QApplication.restoreOverrideCursor()
                if not swmm_dir:
                    return

                swmm_file = swmm_dir + r"\SWMM.INP"
                if os.path.isfile(swmm_file):
                    QApplication.setOverrideCursor(Qt.ArrowCursor)
                    replace = self.uc.question("SWMM.INP already exists.\n\n" + "Would you like to replace it?")
                    QApplication.restoreOverrideCursor()
                    if not replace:
                        return

                if os.path.isfile(swmm_file):
                    # File exist, therefore import groups:
                    INP_groups = self.split_INP_into_groups_dictionary_by_tags_to_export(swmm_file)
                else:
                    # File doen't exists.Create groups.
                    pass

            else:
                swmm_file = hdf5_dir + r"\SWMM.INP"
                if os.path.isfile(swmm_file):
                    os.remove(swmm_file)

            s.setValue("FLO-2D/lastGdsDir", os.path.dirname(swmm_file))
            s.setValue("FLO-2D/lastSWMMDir", os.path.dirname(swmm_file))
            last_dir = s.value("FLO-2D/lastGdsDir", "")

            # Show dialog with [TITLE], [OPTIONS], and [REPORT], with values taken from existing .INP file (if selected),
            # and project units, start date, report start.
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            dlg_INP_groups = INP_GroupsDialog(self.con, self.iface)
            ok = dlg_INP_groups.exec_()
            QApplication.restoreOverrideCursor()
            if ok:
                start_date = NULL
                end_date = NULL
                non_sync_dates = 0

                with open(swmm_file, "w") as swmm_inp_file:
                    no_in_out_conduits = 0
                    no_in_out_pumps = 0
                    no_in_out_orifices = 0
                    no_in_out_weirs = 0

                    # INP TITLE ##################################################
                    items = self.select_this_INP_group(INP_groups, "title")
                    swmm_inp_file.write("[TITLE]")
                    #                     if items is not None:
                    #                         for line in items[1:]:
                    #                             swmm_inp_file.write("\n" + line)
                    #                     else:
                    swmm_inp_file.write("\n" + dlg_INP_groups.titleTextEdit.toPlainText() + "\n")

                    # INP OPTIONS ##################################################
                    items = self.select_this_INP_group(INP_groups, "options")
                    swmm_inp_file.write("\n[OPTIONS]")
                    #                     if items is not None:
                    #                         for line in items[1:]:
                    #                             swmm_inp_file.write("\n" + line)
                    #                     else:
                    #                         swmm_inp_file.write('\n')
                    swmm_inp_file.write("\nFLOW_UNITS           " + dlg_INP_groups.flow_units_cbo.currentText())
                    swmm_inp_file.write("\nINFILTRATION         HORTON")
                    swmm_inp_file.write("\nFLOW_ROUTING         " + dlg_INP_groups.flow_routing_cbo.currentText())
                    start_date = dlg_INP_groups.start_date.date().toString("MM/dd/yyyy")
                    swmm_inp_file.write("\nSTART_DATE           " + start_date)

                    swmm_inp_file.write(
                        "\nSTART_TIME           " + dlg_INP_groups.start_time.time().toString("hh:mm:ss")
                    )
                    swmm_inp_file.write(
                        "\nREPORT_START_DATE    " + dlg_INP_groups.report_start_date.date().toString("MM/dd/yyyy")
                    )
                    swmm_inp_file.write(
                        "\nREPORT_START_TIME    " + dlg_INP_groups.report_start_time.time().toString("hh:mm:ss")
                    )
                    end_date = dlg_INP_groups.end_date.date().toString("MM/dd/yyyy")
                    swmm_inp_file.write("\nEND_DATE             " + end_date)
                    swmm_inp_file.write("\nEND_TIME             " + dlg_INP_groups.end_time.time().toString("hh:mm:ss"))
                    swmm_inp_file.write("\nSWEEP_START          01/01")
                    swmm_inp_file.write("\nSWEEP_END            12/31")
                    swmm_inp_file.write("\nDRY_DAYS             0")
                    swmm_inp_file.write(
                        "\nREPORT_STEP          " + dlg_INP_groups.report_stp_time.time().toString("hh:mm:ss")
                    )
                    swmm_inp_file.write("\nWET_STEP             00:05:00")
                    swmm_inp_file.write("\nDRY_STEP             01:00:00")
                    swmm_inp_file.write("\nROUTING_STEP         00:01:00")
                    swmm_inp_file.write("\nALLOW_PONDING        NO")
                    swmm_inp_file.write("\nINERTIAL_DAMPING     " + dlg_INP_groups.inertial_damping_cbo.currentText())
                    swmm_inp_file.write("\nVARIABLE_STEP        0.75")
                    swmm_inp_file.write("\nLENGTHENING_STEP     0")
                    swmm_inp_file.write("\nMIN_SURFAREA         0")
                    swmm_inp_file.write(
                        "\nNORMAL_FLOW_LIMITED  " + dlg_INP_groups.normal_flow_limited_cbo.currentText()
                    )
                    swmm_inp_file.write("\nSKIP_STEADY_STATE    " + dlg_INP_groups.skip_steady_state_cbo.currentText())
                    if dlg_INP_groups.force_main_equation_cbo.currentIndex() == 0:
                        equation = "H-W"
                    else:
                        equation = "D-W"
                    swmm_inp_file.write("\nFORCE_MAIN_EQUATION  " + equation)
                    swmm_inp_file.write("\nLINK_OFFSETS         " + dlg_INP_groups.link_offsets_cbo.currentText())
                    swmm_inp_file.write("\nMIN_SLOPE            " + str(dlg_INP_groups.min_slop_dbox.value()))

                    # INP JUNCTIONS ##################################################
                    try:
                        SD_junctions_sql = """SELECT name, junction_invert_elev, max_depth, init_depth, surcharge_depth, ponded_area
                                          FROM user_swmm_nodes WHERE sd_type = "I" or sd_type = "i" or sd_type = "J" ORDER BY fid;"""

                        junctions_rows = self.gutils.execute(SD_junctions_sql).fetchall()
                        if not junctions_rows:
                            pass
                        else:
                            swmm_inp_file.write("\n")
                            swmm_inp_file.write("\n[JUNCTIONS]")
                            swmm_inp_file.write("\n;;               Invert     Max.       Init.      Surcharge  Ponded")
                            swmm_inp_file.write("\n;;Name           Elev.      Depth      Depth      Depth      Area")
                            swmm_inp_file.write(
                                "\n;;-------------- ---------- ---------- ---------- ---------- ----------"
                            )

                            line = "\n{0:16} {1:<10.2f} {2:<10.2f} {3:<10.2f} {4:<10.2f} {5:<10.2f}"

                            for row in junctions_rows:
                                row = (
                                    row[0],
                                    0 if row[1] is None else row[1],
                                    0 if row[2] is None else row[2],
                                    0 if row[3] is None else row[3],
                                    0 if row[4] is None else row[4],
                                    0,
                                )
                                swmm_inp_file.write(line.format(*row))
                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 070618.0851: error while exporting [JUNCTIONS] to .INP file!", e)
                        return

                    # INP OUTFALLS ###################################################
                    try:
                        SD_outfalls_sql = """SELECT name, outfall_invert_elev, outfall_type, time_series, tidal_curve, flapgate, water_depth 
                                          FROM user_swmm_nodes  WHERE sd_type = "O"  ORDER BY fid;"""

                        outfalls_rows = self.gutils.execute(SD_outfalls_sql).fetchall()
                        if not outfalls_rows:
                            pass
                        else:
                            swmm_inp_file.write("\n")
                            swmm_inp_file.write("\n[OUTFALLS]")
                            swmm_inp_file.write("\n;;               Invert     Outfall      Stage/Table       Tide")
                            swmm_inp_file.write("\n;;Name           Elev.      Type         Time Series       Gate")
                            swmm_inp_file.write("\n;;-------------- ---------- ------------ ----------------  ----")

                            line = "\n{0:16} {1:<10.2f} {2:<11} {3:<18} {4:<16}"

                            for row in outfalls_rows:
                                lrow = list(row)
                                lrow = [
                                    lrow[0],
                                    0 if lrow[1] is None else lrow[1],
                                    0 if lrow[2] is None else lrow[2],
                                    "   " if lrow[3] is None else lrow[3],
                                    0 if lrow[4] is None else lrow[4],
                                    0 if lrow[5] is None else lrow[5],
                                    0 if lrow[6] is None else lrow[6],
                                ]
                                lrow[3] = "*" if lrow[3] == "..." else "*" if lrow[3] == "" else lrow[3]
                                lrow[4] = "*" if lrow[4] == "..." else "*" if lrow[4] == "" else lrow[4]
                                lrow[2] = lrow[2].upper().strip()
                                if not lrow[2] in ("FIXED", "FREE", "NORMAL", "TIDAL", "TIMESERIES"):
                                    lrow[2] = "NORMAL"
                                lrow[2] = (
                                    "TIDAL"
                                    if lrow[2] == "TIDAL CURVE"
                                    else "TIMESERIES"
                                    if lrow[2] == "TIME SERIES"
                                    else lrow[2]
                                )

                                # Set 3rt. value:
                                if lrow[2] == "FREE" or lrow[2] == "NORMAL":
                                    lrow[3] = "    "
                                elif lrow[2] == "TIMESERIES":
                                    lrow[3] = lrow[3]
                                elif lrow[2] == "TIDAL":
                                    lrow[3] = lrow[4]
                                elif lrow[2] == "FIXED":
                                    lrow[3] = lrow[6]

                                lrow[5] = "YES" if lrow[5] in ("True", "true", "Yes", "yes", "1") else "NO"
                                swmm_inp_file.write(line.format(lrow[0], lrow[1], lrow[2], lrow[3], lrow[5]))

                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 070618.1619: error while exporting [OUTFALLS] to .INP file!", e)
                        return

                    # INP STORAGE ###################################################
                    try:
                        SD_storages_sql = """SELECT name, invert_elev, max_depth, init_depth, storage_curve,
                                                    coefficient, exponent, constant, ponded_area, 
                                                    evap_factor, suction_head, conductivity, initial_deficit, curve_name, infiltration
                                             FROM user_swmm_storage_units;"""

                        storages_rows = self.gutils.execute(SD_storages_sql).fetchall()
                        if not storages_rows:
                            pass
                        else:
                            swmm_inp_file.write("\n")
                            swmm_inp_file.write("\n[STORAGE]")
                            swmm_inp_file.write("\n;;               Invert   Max.     Init.    Storage    Curve                      Ponded   Evap.")
                            swmm_inp_file.write("\n;;Name           Elev.    Depth    Depth    Curve      Params                     Area     Frac.    Infiltration Parameters")
                            swmm_inp_file.write("\n;;-------------- -------- -------- -------- ---------- -------- -------- -------- -------- -------- -----------------------")

                            line_functional_with_infil = "\n{0:16} {1:<8} {2:<8} {3:<8} {4:<10} {5:<8} {6:<8} {7:<8} {8:<8} {9:<8} {10:<8} {11:<8} {12:<8}"
                            line_tabular_with_infil = "\n{0:16} {1:<8} {2:<8} {3:<8} {4:<10} {5:<26} {6:<8} {7:<8} {8:<8} {9:<8} {10:<8}"
                            line_functional_no_infil = "\n{0:16} {1:<8} {2:<8} {3:<8} {4:<10} {5:<8} {6:<8} {7:<8} {8:<8} {9:<8}"
                            line_tabular_no_infil = "\n{0:16} {1:<8} {2:<8} {3:<8} {4:<10} {5:<26} {6:<8} {7:<8}"

                            for row in storages_rows:
                                lrow = list(row)
                                lrow = [
                                    lrow[0],
                                    0 if lrow[1] is None else '%g'%lrow[1],
                                    0 if lrow[2] is None else '%g'%lrow[2],
                                    0 if lrow[3] is None else '%g'%lrow[3],
                                    "FUNCTIONAL" if lrow[4] is None else lrow[4],
                                    0 if lrow[5] is None else '%g'%lrow[5],
                                    0 if lrow[6] is None else '%g'%lrow[6],
                                    0 if lrow[7] is None else '%g'%lrow[7],
                                    0,
                                    0 if lrow[9] is None else '%g'%lrow[9],
                                    0 if lrow[10] is None else '%g'%lrow[10],
                                    0 if lrow[11] is None else '%g'%lrow[11],
                                    0 if lrow[12] is None else '%g'%lrow[12],
                                    lrow[13],
                                    lrow[14]
                                ]
                                if lrow[4] == "FUNCTIONAL": 
                                    if lrow[14]== "True":
                                        swmm_inp_file.write(line_functional_with_infil.format(lrow[0], lrow[1], lrow[2], lrow[3], lrow[4], lrow[5],
                                                                    lrow[6], lrow[7], lrow[8], lrow[9], 
                                                                    lrow[10], lrow[11], lrow[12]))
                                    else:
                                        swmm_inp_file.write(line_functional_no_infil.format(lrow[0], lrow[1], lrow[2], lrow[3], lrow[4], lrow[5],
                                                                    lrow[6], lrow[7], lrow[8], lrow[9]))                                         
                                            
                                else:
                                    if lrow[14]=="True":
                                        swmm_inp_file.write(line_tabular_with_infil.format(lrow[0], lrow[1], lrow[2], lrow[3], lrow[4],
                                                                lrow[13], lrow[8], lrow[9], 
                                                                lrow[10], lrow[11], lrow[12]))
                                    else:    
                                        swmm_inp_file.write(line_tabular_no_infil.format(lrow[0], lrow[1], lrow[2], lrow[3], lrow[4],
                                                                lrow[13], lrow[8], lrow[9]))                                        

                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 160224.0541: error while exporting [STORAGE] to .INP file!", e)
                        return

                    # INP CONDUITS ###################################################

                    try:
                        SD_conduits_sql = """SELECT conduit_name, conduit_inlet, conduit_outlet, conduit_length, conduit_manning, conduit_inlet_offset, 
                                                conduit_outlet_offset, conduit_init_flow, conduit_max_flow 
                                          FROM user_swmm_conduits ORDER BY fid;"""

                        conduits_rows = self.gutils.execute(SD_conduits_sql).fetchall()
                        if not conduits_rows:
                            pass
                        else:
                            swmm_inp_file.write("\n")
                            swmm_inp_file.write("\n[CONDUITS]")
                            swmm_inp_file.write(
                                "\n;;               Inlet            Outlet                      Manning    Inlet      Outlet     Init.      Max."
                            )
                            swmm_inp_file.write(
                                "\n;;Name           Node             Node             Length     N          Offset     Offset     Flow       Flow"
                            )
                            swmm_inp_file.write(
                                "\n;;-------------- ---------------- ---------------- ---------- ---------- ---------- ---------- ---------- ----------"
                            )

                            line = "\n{0:16} {1:<16} {2:<16} {3:<10.2f} {4:<10.3f} {5:<10.2f} {6:<10.2f} {7:<10.2f} {8:<10.2f}"

                            for row in conduits_rows:
                                row = (
                                    row[0],
                                    "?" if row[1] is None or row[1] == "" else row[1],
                                    "?" if row[2] is None or row[2] == "" else row[2],
                                    0 if row[3] is None else row[3],
                                    0 if row[4] is None else row[4],
                                    0 if row[5] is None else row[5],
                                    0 if row[6] is None else row[6],
                                    0 if row[7] is None else row[7],
                                    0 if row[8] is None else row[8],
                                )
                                if row[1] == "?" or row[2] == "?":
                                    no_in_out_conduits += 1
                                swmm_inp_file.write(line.format(*row))
                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 070618.1620: error while exporting [CONDUITS] to .INP file!", e)
                        return

                    # INP PUMPS ###################################################
                    try:
                        SD_pumps_sql = """SELECT pump_name, pump_inlet, pump_outlet, pump_curve, pump_init_status, 
                                            pump_startup_depth, pump_shutoff_depth 
                                            FROM user_swmm_pumps ORDER BY fid;"""

                        pumps_rows = self.gutils.execute(SD_pumps_sql).fetchall()
                        if not pumps_rows:
                            pass
                        else:
                            swmm_inp_file.write("\n")
                            swmm_inp_file.write("\n[PUMPS]")
                            swmm_inp_file.write(
                                "\n;;               Inlet            Outlet           Pump             Init.      Startup    Shutup"
                            )
                            swmm_inp_file.write(
                                "\n;;Name           Node             Node             Curve            Status     Depth      Depth"
                            )
                            swmm_inp_file.write(
                                "\n;;-------------- ---------------- ---------------- ---------------- ---------- ---------- -------"
                            )

                            line = "\n{0:16} {1:<16} {2:<16} {3:<16} {4:<10} {5:<10.2f} {6:<10.2f}"

                            for row in pumps_rows:
                                row = (
                                    row[0],
                                    "?" if row[1] is None or row[1] == "" else row[1],
                                    "?" if row[2] is None or row[2] == "" else row[2],
                                    "*" if row[3] is None else row[3],
                                    "OFF" if row[4] is None else row[4],
                                    0 if row[5] is None else row[5],
                                    0 if row[6] is None else row[6],
                                )
                                if row[1] == "?" or row[2] == "?":
                                    no_in_out_pumps += 1
                                swmm_inp_file.write(line.format(*row))
                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 271121.0515: error while exporting [PUMPS] to .INP file!", e)
                        return

                    # INP ORIFICES ###################################################
                    try:
                        SD_orifices_sql = """SELECT orifice_name, orifice_inlet, orifice_outlet, orifice_type, orifice_crest_height, 
                                            orifice_disch_coeff, orifice_flap_gate, orifice_open_close_time 
                                            FROM user_swmm_orifices ORDER BY fid;"""

                        orifices_rows = self.gutils.execute(SD_orifices_sql).fetchall()
                        if not orifices_rows:
                            pass
                        else:
                            swmm_inp_file.write("\n")
                            swmm_inp_file.write("\n[ORIFICES]")
                            swmm_inp_file.write(
                                "\n;;               Inlet            Outlet           Orifice      Crest      Disch.      Flap      Open/Close"
                            )
                            swmm_inp_file.write(
                                "\n;;Name           Node             Node             Type         Height     Coeff.      Gate      Time"
                            )
                            swmm_inp_file.write(
                                "\n;;-------------- ---------------- ---------------- ------------ ---------- ----------- --------- -----------"
                            )

                            line = "\n{0:16} {1:<16} {2:<16} {3:<12} {4:<10.2f} {5:<11.2f} {6:<9} {7:<9.2f}"

                            for row in orifices_rows:
                                row = (
                                    row[0],
                                    "?" if row[1] is None or row[1] == "" else row[1],
                                    "?" if row[2] is None or row[2] == "" else row[2],
                                    "SIDE" if row[3] is None else row[3],
                                    0 if row[4] is None else row[4],
                                    0 if row[5] is None else row[5],
                                    "NO" if row[6] is None else row[6],
                                    0 if row[7] is None else row[7],
                                )
                                if row[1] == "?" or row[2] == "?":
                                    no_in_out_orifices += 1
                                swmm_inp_file.write(line.format(*row))
                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 310322.1548: error while exporting [ORIFICES] to .INP file!", e)
                        return

                    # INP WEIRS ###################################################
                    try:
                        SD_weirs_sql = """SELECT weir_name, weir_inlet, weir_outlet, weir_type, weir_crest_height, 
                                            weir_disch_coeff, weir_flap_gate, weir_end_contrac, weir_end_coeff 
                                            FROM user_swmm_weirs ORDER BY fid;"""

                        weirs_rows = self.gutils.execute(SD_weirs_sql).fetchall()
                        if not weirs_rows:
                            pass
                        else:
                            swmm_inp_file.write("\n")
                            swmm_inp_file.write("\n[WEIRS]")
                            swmm_inp_file.write(
                                "\n;;               Inlet            Outlet           Weir         Crest      Disch.      Flap      End      End"
                            )
                            swmm_inp_file.write(
                                "\n;;Name           Node             Node             Type         Height     Coeff.      Gate      Con.     Coeff."
                            )
                            swmm_inp_file.write(
                                "\n;;-------------- ---------------- ---------------- ------------ ---------- ----------- --------- -------  ---------"
                            )

                            line = "\n{0:16} {1:<16} {2:<16} {3:<12} {4:<10.2f} {5:<11.2f} {6:<9} {7:<8} {8:<9.2f}"

                            for row in weirs_rows:
                                row = (
                                    row[0],
                                    "?" if row[1] is None or row[1] == "" else row[1],
                                    "?" if row[2] is None or row[2] == "" else row[2],
                                    "TRANSVERSE" if row[3] is None else row[3],
                                    0 if row[4] is None else row[4],
                                    0 if row[5] is None else row[5],
                                    "NO" if row[6] is None else row[6],
                                    "0" if row[7] is None else row[7],
                                    0 if row[8] is None else row[8],
                                )
                                if row[1] == "?" or row[2] == "?":
                                    no_in_out_weirs += 1
                                swmm_inp_file.write(line.format(*row))
                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 090422.0557: error while exporting [WEIRS] to .INP file!", e)
                        return

                    # INP XSECTIONS ###################################################
                    try:
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[XSECTIONS]")
                        swmm_inp_file.write(
                            "\n;;Link           Shape        Geom1      Geom2      Geom3      Geom4      Barrels"
                        )
                        swmm_inp_file.write(
                            "\n;;-------------- ------------ ---------- ---------- ---------- ---------- ----------"
                        )

                        # XSections from user conduits:
                        SD_xsections_1_sql = """SELECT conduit_name, xsections_shape, xsections_max_depth, xsections_geom2, 
                                                xsections_geom3, xsections_geom4, xsections_barrels
                                          FROM user_swmm_conduits ORDER BY fid;"""

                        line = "\n{0:16} {1:<13} {2:<10.2f} {3:<10.2f} {4:<10.3f} {5:<10.2f} {6:<10}"
                        xsections_rows_1 = self.gutils.execute(SD_xsections_1_sql).fetchall()
                        if not xsections_rows_1:
                            pass
                        else:
                            no_xs = 0

                            for row in xsections_rows_1:
                                lrow = list(row)
                                lrow = (
                                    "?" if lrow[0] is None or lrow[0] == "" else lrow[0],
                                    "?" if lrow[1] is None or lrow[0] == "" else lrow[1],
                                    "?" if lrow[2] is None or lrow[0] == "" else lrow[2],
                                    "?" if lrow[3] is None or lrow[0] == "" else lrow[3],
                                    "?" if lrow[4] is None or lrow[0] == "" else lrow[4],
                                    "?" if lrow[5] is None or lrow[0] == "" else lrow[5],
                                    "?" if lrow[6] is None or lrow[0] == "" else lrow[6],
                                )
                                if (
                                    row[0] == "?"
                                    or row[1] == "?"
                                    or row[2] == "?"
                                    or row[3] == "?"
                                    or row[4] == "?"
                                    or row[5] == "?"
                                    or row[6] == "?"
                                ):
                                    no_xs += 1
                                lrow = (
                                    lrow[0],
                                    lrow[1],
                                    0.0 if lrow[2] == "?" else lrow[2],
                                    0.0 if lrow[3] == "?" else lrow[3],
                                    0.0 if lrow[4] == "?" else lrow[4],
                                    0.0 if lrow[5] == "?" else lrow[5],
                                    0.0 if lrow[6] == "?" else lrow[6],
                                )
                                row = tuple(lrow)
                                swmm_inp_file.write(line.format(*row))

                        # XSections from user orifices:
                        SD_xsections_2_sql = """SELECT orifice_name, orifice_shape, orifice_height, orifice_width
                                          FROM user_swmm_orifices ORDER BY fid;"""

                        line = "\n{0:16} {1:<13} {2:<10.2f} {3:<10.2f} {4:<10.2f} {5:<10.2f} {6:<10}"
                        xsections_rows_2 = self.gutils.execute(SD_xsections_2_sql).fetchall()
                        if not xsections_rows_2:
                            pass
                        else:
                            no_xs = 0

                            for row in xsections_rows_2:
                                lrow = list(row)
                                lrow = (
                                    "?" if lrow[0] is None or lrow[0] == "" else lrow[0],
                                    "?" if lrow[1] is None or lrow[0] == "" else lrow[1],
                                    "?" if lrow[2] is None or lrow[0] == "" else lrow[2],
                                    "?" if lrow[3] is None or lrow[0] == "" else lrow[3],
                                    0.0,
                                    0.0,
                                    0,
                                )
                                if row[0] == "?" or row[1] == "?" or row[2] == "?" or row[3] == "?":
                                    no_xs += 1
                                lrow = (
                                    lrow[0],
                                    lrow[1],
                                    0.0 if lrow[2] == "?" else lrow[2],
                                    0.0 if lrow[3] == "?" else 0.0 if lrow[1] == "CIRCULAR" else lrow[3],
                                    0.0,
                                    0.0,
                                    " ",
                                )
                                row = tuple(lrow)
                                swmm_inp_file.write(line.format(*row))

                        # XSections from user weirs:
                        SD_xsections_3_sql = """SELECT weir_name, weir_shape, weir_height, weir_length, weir_side_slope, weir_side_slope
                                          FROM user_swmm_weirs ORDER BY fid;"""

                        line = "\n{0:16} {1:<13} {2:<10.2f} {3:<10.2f} {4:<10.2f} {5:<10.2f} {6:<10}"
                        xsections_rows_3 = self.gutils.execute(SD_xsections_3_sql).fetchall()
                        if not xsections_rows_3:
                            pass
                        else:
                            no_xs = 0

                            for row in xsections_rows_3:
                                lrow = list(row)
                                lrow = (
                                    "?" if lrow[0] is None or lrow[0] == "" else lrow[0],
                                    "?" if lrow[1] is None or lrow[0] == "" else lrow[1],
                                    "?" if lrow[2] is None or lrow[0] == "" else lrow[2],
                                    "?" if lrow[3] is None or lrow[0] == "" else lrow[3],
                                    "?" if lrow[4] is None or lrow[4] == "" else lrow[4],
                                    "?" if lrow[5] is None or lrow[5] == "" else lrow[5],
                                    0,
                                )
                                if row[0] == "?" or row[1] == "?" or row[2] == "?" or row[3] == "?":
                                    no_xs += 1
                                lrow = (
                                    lrow[0],
                                    lrow[1],
                                    0.0 if lrow[2] == "?" else lrow[2],
                                    0.0 if lrow[3] == "?" else 0.0 if lrow[1] == "CIRCULAR" else lrow[3],
                                    0.0 if lrow[4] == "?" else lrow[4],
                                    0.0 if lrow[5] == "?" else lrow[5],
                                    " ",
                                )
                                row = tuple(lrow)
                                swmm_inp_file.write(line.format(*row))

                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 090422.0601: error while exporting [XSECTIONS] to .INP file!", e)
                        return

                    # INP LOSSES ###################################################
                    try:
                        SD_losses_sql = """SELECT conduit_name, losses_inlet, losses_outlet, losses_average, losses_flapgate
                                          FROM user_swmm_conduits ORDER BY fid;"""

                        losses_rows = self.gutils.execute(SD_losses_sql).fetchall()
                        if not losses_rows:
                            pass
                        else:
                            swmm_inp_file.write("\n")
                            swmm_inp_file.write("\n[LOSSES]")
                            swmm_inp_file.write("\n;;Link           Inlet      Outlet     Average    Flap Gate")
                            swmm_inp_file.write("\n;;-------------- ---------- ---------- ---------- ----------")

                            line = "\n{0:16} {1:<10} {2:<10} {3:<10.2f} {4:<10}"

                            for row in losses_rows:
                                lrow = list(row)
                                lrow[4] = "YES" if lrow[4] in ("True", "true", "Yes", "yes", "1") else "NO"
                                swmm_inp_file.write(line.format(*lrow))
                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 070618.1622: error while exporting [LOSSES] to .INP file!", e)
                        return

                    # INP CONTROLS ##################################################
                    items = self.select_this_INP_group(INP_groups, "controls")
                    swmm_inp_file.write("\n\n[CONTROLS]")
                    if items is not None:
                        for line in items[1:]:
                            if line != "":
                                swmm_inp_file.write("\n" + line)
                    else:
                        swmm_inp_file.write("\n")

                    # INP INFLOWS ###################################################
                    try:
                        SD_inflows_sql = """SELECT node_name, constituent, baseline, pattern_name, time_series_name, scale_factor
                                          FROM swmm_inflows ORDER BY fid;"""
                        inflows_rows = self.gutils.execute(SD_inflows_sql).fetchall()
                        if not inflows_rows:
                            pass
                        else:
                            swmm_inp_file.write("\n")
                            swmm_inp_file.write("\n[INFLOWS]")
                            swmm_inp_file.write(
                                "\n;;Node           Constituent      Time Series      Type     Mfactor  Sfactor  Baseline Pattern"
                            )
                            swmm_inp_file.write(
                                "\n;;-------------- ---------------- ---------------- -------- -------- -------- -------- --------"
                            )
                            line = "\n{0:16} {1:<16} {2:<16} {3:<7}  {4:<8} {5:<8.2f} {6:<8.2f} {7:<10}"
                            for row in inflows_rows:
                                lrow = [
                                    row[0],
                                    row[1],
                                    row[4] if row[4] != "" else '""',
                                    row[1],
                                    "1.0",
                                    row[5],
                                    row[2],
                                    row[3] if row[3] is not None else "",
                                ]
                                swmm_inp_file.write(line.format(*lrow))
                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 230220.0751.1622: error while exporting [INFLOWS] to .INP file!", e)
                        return

                    # INP CURVES ###################################################
                    try:
                        # Pumps:
                        SD_pump_curves_sql = """SELECT pump_curve_name, pump_curve_type, x_value, y_value, description
                                          FROM swmm_pumps_curve_data ORDER BY fid;"""
                        pump_curves_rows = self.gutils.execute(SD_pump_curves_sql).fetchall()

                        # Tidal:
                        SD_tidal_curves_data_sql = """SELECT tidal_curve_name, hour, stage
                                          FROM swmm_tidal_curve_data ORDER BY fid;"""
                        tidal_curves_data_rows = self.gutils.execute(SD_tidal_curves_data_sql).fetchall()
                        
                        # Other:
                        SD_other_curves_sql = """SELECT name, type, x_value, y_value, description
                                          FROM swmm_other_curves ORDER BY fid;"""
                        other_curves_rows = self.gutils.execute(SD_other_curves_sql).fetchall()                        
                        
                        if not other_curves_rows and not pump_curves_rows and not tidal_curves_data_rows:
                            pass
                        else:
                            swmm_inp_file.write("\n")
                            swmm_inp_file.write("\n[CURVES]")
                            swmm_inp_file.write("\n;;Name           Type       X-Value    Y-Value")
                            swmm_inp_file.write("\n;;-------------- ---------- ---------- ----------")

                            # Write curves of type 'PumpN' (N being 1,2,3, or 4):
                            line1 = "\n{0:16} {1:<10} {2:<10.2f} {3:<10.2f}"
                            name = ""
                            for row in pump_curves_rows:
                                lrow = list(row)
                                if lrow[0] == name:
                                    lrow[1] = "     "
                                else:
                                    swmm_inp_file.write("\n")
                                    if lrow[4]: 
                                        swmm_inp_file.write("\n;" + lrow[4])
                                    name = lrow[0]
                                swmm_inp_file.write(line1.format(*lrow))

                            # Write curves of type 'Tidal'
                            qry_SD_tidal_curve = """SELECT tidal_curve_description
                                          FROM swmm_tidal_curve WHERE tidal_curve_name = ?;"""
                            line2 = "\n{0:16} {1:<10} {2:<10} {3:<10}"
                            name = ""
                            for row in tidal_curves_data_rows:
                                lrow = [row[0], "Tidal", row[1], row[2]]
                                if lrow[0] == name:
                                    lrow[1] = "     "
                                else:
                                    descr = self.gutils.execute(qry_SD_tidal_curve, (lrow[0],)).fetchone()
                                    swmm_inp_file.write("\n")
                                    if descr[0]:
                                        swmm_inp_file.write("\n;" + descr[0])
                                    name = lrow[0]
                                swmm_inp_file.write(line2.format(*lrow))
                                
                            # Write all other curves in storm_drain.INP_curves:
                            name = ""
                            for row in other_curves_rows:
                                lrow = list(row)
                                if lrow[0] == name:
                                    lrow[1] = "     "
                                else:
                                    swmm_inp_file.write("\n")
                                    if lrow[4]:
                                        swmm_inp_file.write("\n;" + lrow[4])
                                    name = lrow[0]
                                swmm_inp_file.write(line1.format(*lrow))                            

                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error(
                            "ERROR 281121.0453: error while exporting [CURVES] to .INP file!\n"
                            + "Is the name or type of the curve missing in 'Storm Drain Pumps Curve Data' table?",
                            e,
                        )
                        return

                    # INP TIMESERIES ###################################################
                    try:
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[TIMESERIES]")
                        swmm_inp_file.write("\n;;Name           Date       Time       Value     ")
                        swmm_inp_file.write("\n;;-------------- ---------- ---------- ----------")

                        SD_time_series_sql = """SELECT time_series_name, 
                                                            time_series_description, 
                                                            time_series_file,
                                                            time_series_data
                                          FROM swmm_time_series ORDER BY fid;"""

                        SD_time_series_data_sql = """SELECT                                 
                                                            date, 
                                                            time,
                                                            value
                                          FROM swmm_time_series_data WHERE time_series_name = ?;"""

                        line1 = "\n;{0:16}"
                        line2 = "\n{0:16} {1:<10} {2:<50}"
                        line3 = "\n{0:16} {1:<10} {2:<10} {3:<7.4f}"

                        time_series_rows = self.gutils.execute(SD_time_series_sql).fetchall()
                        if not time_series_rows:
                            pass
                        else:
                            for row in time_series_rows:
                                if row[3] == "False":  # Inflow data comes from file:
                                    description = [row[1]]
                                    swmm_inp_file.write(line1.format(*description))
                                    fileName = row[2].strip()
                                    # fileName = os.path.basename(row[2].strip())
                                    file = '"' + fileName + '"'
                                    file = os.path.normpath(file)
                                    lrow2 = [row[0], "FILE", file]
                                    swmm_inp_file.write(line2.format(*lrow2))
                                    swmm_inp_file.write("\n;")
                                else:
                                    # Inflow data given in table 'swmm_time_series_data':
                                    name = row[0]
                                    time_series_data = self.gutils.execute(SD_time_series_data_sql, (name,)).fetchall()
                                    if not time_series_data:
                                        pass
                                    else:
                                        description = [row[1]]
                                        swmm_inp_file.write(line1.format(*description))
                                        for data in time_series_data:
                                            date = data[0] if data[0] is not None else "          "
                                            swmm_inp_file.write(
                                                line3.format(
                                                    name if name is not None else " ",
                                                    date,
                                                    data[1] if data[1] is not None else "00:00",
                                                    data[2] if data[2] is not None else 0.0,
                                                )
                                            )
                                            try:
                                                d0 = datetime.strptime(date, "%m/%d/%Y").date()
                                                start = datetime.strptime(start_date, "%m/%d/%Y").date()
                                                end = datetime.strptime(end_date, "%m/%d/%Y").date()
                                                if d0 < start or d0 > end:
                                                    non_sync_dates += 1
                                            except ValueError:
                                                non_sync_dates += 1
                                        swmm_inp_file.write("\n;")

                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 230220.1005: error while exporting [TIMESERIES] to .INP file!", e)
                        return

                    # INP PATTERNS ###################################################
                    try:
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[PATTERNS]")
                        swmm_inp_file.write("\n;;Name           Type       Multipliers")
                        swmm_inp_file.write("\n;;-------------- ---------- -----------")

                        SD_inflow_patterns_sql = """SELECT pattern_name, pattern_description, hour, multiplier
                                          FROM swmm_inflow_patterns ORDER BY fid;"""

                        line0 = "\n;{0:16}"
                        line1 = "\n{0:16} {1:<10} {2:<10.2f} {3:<10.2f} {4:<10.2f} {5:<10.2f} {6:<10.2f} {6:<10.2f}"
                        pattern_rows = self.gutils.execute(SD_inflow_patterns_sql).fetchall()
                        if not pattern_rows:
                            pass
                        else:
                            i = 1
                            for row in pattern_rows:
                                # First line:
                                if i == 1:  # Beginning of first line:
                                    lrow0 = [row[1]]
                                    swmm_inp_file.write(line0.format(*lrow0))
                                    lrow1 = [row[0], "HOURLY", row[3]]
                                    i += 1
                                elif i < 7:  # Rest of first line:
                                    lrow1.append(row[3])
                                    i += 1
                                elif i == 7:
                                    swmm_inp_file.write(line1.format(*lrow1))
                                    lrow1 = [row[0], "   ", row[3]]
                                    i += 1

                                # Second line
                                elif i > 7 and i < 13:
                                    lrow1.append(row[3])
                                    i += 1
                                elif i == 13:
                                    swmm_inp_file.write(line1.format(*lrow1))
                                    lrow1 = [row[0], "   ", row[3]]
                                    i += 1

                                # Third line:
                                elif i > 13 and i < 19:
                                    lrow1.append(row[3])
                                    i += 1
                                elif i == 19:
                                    swmm_inp_file.write(line1.format(*lrow1))
                                    lrow1 = [row[0], "   ", row[3]]
                                    i += 1

                                # Fourth line:
                                elif i > 19 and i < 24:
                                    lrow1.append(row[3])
                                    i += 1
                                elif i == 24:
                                    swmm_inp_file.write(line1.format(*lrow1))
                                    lrow1 = [row[0], "   ", row[3]]
                                    i = 1

                                    swmm_inp_file.write("\n")

                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 240220.0737: error while exporting [PATTERNS] to .INP file!", e)
                        return

                    # INP REPORT ##################################################
                    items = self.select_this_INP_group(INP_groups, "report")
                    swmm_inp_file.write("\n\n[REPORT]")
                    #                     if items is not None:
                    #                         for line in items[1:]:
                    #                             swmm_inp_file.write("\n" + line)
                    #                     else:
                    #                         swmm_inp_file.write('\n')
                    swmm_inp_file.write("\nINPUT           " + dlg_INP_groups.input_cbo.currentText())
                    swmm_inp_file.write("\nCONTROLS        " + dlg_INP_groups.controls_cbo.currentText())
                    swmm_inp_file.write("\nSUBCATCHMENTS   NONE")
                    swmm_inp_file.write("\nNODES           " + dlg_INP_groups.nodes_cbo.currentText())
                    swmm_inp_file.write("\nLINKS           " + dlg_INP_groups.links_cbo.currentText())

                    # INP COORDINATES ###################################################
                    try:
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[COORDINATES]")
                        swmm_inp_file.write("\n;;Node           X-Coord            Y-Coord ")
                        swmm_inp_file.write("\n;;-------------- ------------------ ------------------")

                        SD_nodes_coords_sql = """SELECT name, ST_AsText(ST_Centroid(GeomFromGPB(geom)))
                                          FROM user_swmm_nodes ORDER BY fid;"""

                        line = "\n{0:16} {1:<18} {2:<18}"
                        coordinates_rows = self.gutils.execute(SD_nodes_coords_sql).fetchall()
                        if not coordinates_rows:
                            pass
                        else:
                            for row in coordinates_rows:
                                x = row[:2][1].strip("POINT()").split()[0]
                                y = row[:2][1].strip("POINT()").split()[1]
                                swmm_inp_file.write(line.format(row[0], x, y))
                                
                        SD_storage_coords_sql = """SELECT name, ST_AsText(ST_Centroid(GeomFromGPB(geom)))
                                          FROM user_swmm_storage_units ORDER BY fid;"""

                        line = "\n{0:16} {1:<18} {2:<18}"
                        coordinates_rows = self.gutils.execute(SD_storage_coords_sql).fetchall()
                        if not coordinates_rows:
                            pass
                        else:
                            for row in coordinates_rows:
                                x = row[:2][1].strip("POINT()").split()[0]
                                y = row[:2][1].strip("POINT()").split()[1]
                                swmm_inp_file.write(line.format(row[0], x, y))                                
                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 070618.1623: error while exporting [COORDINATES] to .INP file!", e)
                        return

                    # FUTURE GROUPS ##################################################
                    future_groups = [
                        "FILES",
                        "RAINGAGES",
                        "HYDROGRAPHS",
                        "PROFILES",
                        "EVAPORATION",
                        "TEMPERATURE",
                        "SUBCATCHMENTS",
                        "SUBAREAS",
                        "INFILTRATION",
                        "AQUIFERS",
                        "GROUNDWATER",
                        "SNOWPACKS",
                        "DIVIDERS",
                        "OUTLETS",
                        "TRANSECTS",
                        "POLLUTANTS",
                        "LANDUSES",
                        "COVERAGES",
                        "BUILDUP",
                        "WASHOFF",
                        "TREATMENT",
                        "DWF",
                        "RDII",
                        "LOADINGS",
                        "TAGS",
                        "MAP",
                    ]

                    for group in future_groups:
                        items = self.select_this_INP_group(INP_groups, group.lower())
                        if items is not None:
                            swmm_inp_file.write("\n\n[" + group + "]")
                            for line in items[1:]:
                                if line != "":
                                    swmm_inp_file.write("\n" + line)

                    file = last_dir + "/SWMM.INI"
                    with open(file, "w") as ini_file:
                        ini_file.write("[SWMM5]")
                        ini_file.write("\nVersion=50022")
                        ini_file.write("\n[Results]")
                        ini_file.write("\nSaved=1")
                        ini_file.write("\nCurrent=1")

                QApplication.setOverrideCursor(Qt.ArrowCursor)
                self.uc.show_info(
                    swmm_file
                    + "\n\nfile saved with:\n\n"
                    + str(len(junctions_rows))
                    + "\t[JUNCTIONS]\n"
                    + str(len(outfalls_rows))
                    + "\t[OUTFALLS]\n"
                    + str(len(storages_rows))
                    + "\t[STORAGE]\n"                    
                    + str(len(conduits_rows))
                    + "\t[CONDUITS]\n"
                    + str(len(pumps_rows))
                    + "\t[PUMPS]\n"
                    + str(len(pump_curves_rows))
                    + "\t[CURVES]\n"                    
                    + str(len(orifices_rows))
                    + "\t[ORIFICES]\n"
                    + str(len(weirs_rows))
                    + "\t[WEIRS]\n"
                    + str(len(xsections_rows_1) + len(xsections_rows_2) + len(xsections_rows_3))
                    + "\t[XSECTIONS]\n"
                    + str(len(losses_rows))
                    + "\t[LOSSES]\n"
                    + str(len(coordinates_rows))
                    + "\t[COORDINATES]\n"
                    + str(len(inflows_rows))
                    + "\t[INFLOWS]\n"
                    + str(len(time_series_rows))
                    + "\t[TIMESERIES]\n"
                    + str(int(len(pattern_rows) / 24))
                    + "\t[PATTERNS]"
                )
                
                warn = ""
                if no_in_out_conduits != 0:
                    warn += (
                        "* "
                        + str(no_in_out_conduits)
                        + " conduits have no inlet and/or outlet!\nThe value '?' was written in [CONDUITS] group.\n\n"
                    )

                if no_in_out_pumps != 0:
                    warn += (
                        "* "
                        + str(no_in_out_pumps)
                        + " pumps have no inlet and/or outlet!\nThe value '?' was written in [PUMPS] group.\n\n"
                    )

                if no_in_out_orifices != 0:
                    warn += (
                        "* "
                        + str(no_in_out_orifices)
                        + " orifices have no inlet and/or outlet!\nThe value '?' was written in [ORIFICES] group.\n\n"
                    )

                if no_in_out_weirs != 0:
                    warn += (
                        "* "
                        + str(no_in_out_weirs)
                        + " weirs have no inlet and/or outlet!\nThe value '?' was written in [WEIRS] group.\n\n"
                    )

                if non_sync_dates > 0:
                    warn += (
                        "* "
                        + str(non_sync_dates)
                        + " time series dates are outside the start and end times of the simulation!\nSee [TIMESERIES] group.\n\n"
                    )

                if warn != "":
                    self.uc.show_warn(
                        "WARNING 090422.0554: SWMM.INP file:\n\n"
                        + warn
                        + "Please review these issues because they will cause errors during their processing."
                    )
                    
                QApplication.restoreOverrideCursor()
                    
        except Exception as e:
            self.uc.show_error("ERROR 160618.0634: couldn't export .INP file!", e)

    def show_outfalls(self):
        """
        Shows outfalls dialog.

        """
        # See if there are inlets:
        if self.gutils.is_table_empty("user_swmm_nodes"):
            self.uc.show_warn(
                'User Layer "Storm Drain Nodes" is empty!\n\n'
                + "Please import components from .INP file or shapefile, or convert from schematized Storm Drains."
            )
            return

        #  See if there are any Outlet nodes:
        qry = """SELECT * FROM user_swmm_nodes WHERE sd_type = 'O';"""
        rows = self.gutils.execute(qry).fetchall()
        if not rows:
            self.uc.bar_warn("No outfalls defined in 'Storm Drain Nodes' User Layer!")
            return

        dlg_outfalls = OutfallNodesDialog(self.iface, self.lyrs)
        dlg_outfalls.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        dlg_outfalls.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        save = dlg_outfalls.exec_()
        if save:
            try:
                dlg_outfalls.save_outfalls()
                self.uc.bar_info(
                    "Outfalls saved to 'Storm Drain-Outfalls' User Layer!\n\n"
                    + "Schematize it from the 'Storm Drain Editor' widget before saving into SWMMOUTF.DAT"
                )
            except Exception:
                self.uc.bar_warn("Could not save outfalls! Please check if they are correct.")
                return

        self.lyrs.clear_rubber()

    def show_inlets(self):
        """
        Shows inlets dialog.

        """
        # See if table is empty:
        if self.gutils.is_table_empty("user_swmm_nodes"):
            self.uc.show_warn(
                'User Layer "Storm Drain Nodes" is empty!\n\n'
                + "Please import components from .INP file or shapefile, or convert from schematized Storm Drains."
            )
            return

        #  See if there are any Inlet nodes:
        qry = """SELECT * FROM user_swmm_nodes WHERE sd_type = 'I' or sd_type = 'J';"""
        rows = self.gutils.execute(qry).fetchall()
        if not rows:
            self.uc.show_info(
                "WARNING 280920.0422: No inlets/junctions defined (of type 'I' or 'J') in 'Storm Drain Nodes' User Layer!"
            )
            return

        dlg_inlets = InletNodesDialog(self.iface, self.plot, self.SD_table, self.lyrs)
        dlg_inlets.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        dlg_inlets.setWindowFlag(Qt.WindowMaximizeButtonHint, True)

        save = dlg_inlets.exec_()
        if save:
            self.uc.show_info(
                "Inlets saved to 'Storm Drain-Inlets' User Layer!\n\n"
                + "Schematize it from the 'Storm Drain Editor' widget before saving into SWMMOUTF.DAT"
            )
            self.populate_type4_combo()

        elif not save:
            pass
        else:
            self.uc.bar_warn("Could not save Inlets! Please check if they are correct.")

        self.lyrs.clear_rubber()

    def show_storage_units(self):
        """
        Shows storage_units_dialog dialog.

        """
        # See if table is empty:
        if self.gutils.is_table_empty("user_swmm_storage_units"):
            self.uc.show_warn(
                'User Layer "Storm Drain Storage Units" is empty!\n\n'
                + "Please import components from .INP file or shapefile, or convert from schematized Storm Drains."
            )
            return

        dlg_storage = StorageUnitsDialog(self.iface, self.plot, self.SD_table, self.lyrs)
        dlg_storage.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        dlg_storage.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        dlg_storage.select_curve_type()
        
        save = dlg_storage.exec_()
        if save:
            self.uc.bar_info("Storage Units saved to 'Storm Drain Storage Units' User Layer.")
        elif not save:
            pass
        else:
            self.uc.bar_warn("Could not save Inlets! Please check if they are correct.")
        
        self.lyrs.clear_rubber()

    def show_conduits(self):
        """
        Shows conduits dialog.

        """
        # See if there are conduits:
        if self.gutils.is_table_empty("user_swmm_conduits"):
            self.uc.show_warn(
                'User Layer "Storm Drain Conduits" is empty!\n\n'
                + "Please import components from .INP file or shapefile, or convert from schematized Storm Drains."
            )
            return

        dlg_conduits = ConduitsDialog(self.iface, self.lyrs)
        dlg_conduits.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        dlg_conduits.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        save = dlg_conduits.exec_()
        if save:
            try:
                dlg_conduits.save_conduits()
                self.uc.bar_info(
                    "Conduits saved to 'Storm Drain-Conduits' User Layer!\n\n"
                    + "Schematize it from the 'Storm Drain Editor' widget before saving into SWMMOUTF.DAT"
                )
            except Exception:
                self.uc.bar_warn("Could not save conduits! Please check if they are correct.")
                return

        self.lyrs.clear_rubber()

    def show_pumps(self):
        """
        Shows pumps dialog.

        """
        # See if there are pumps:
        if self.gutils.is_table_empty("user_swmm_pumps"):
            self.uc.show_warn(
                'User Layer "Storm Drain Pumps" is empty!\n\n'
                + "Please import components from .INP file or shapefile, or convert from schematized Storm Drains."
            )
            return

        dlg_pumps = PumpsDialog(self.iface, self.plot, self.SD_table, self.lyrs)
        dlg_pumps.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        dlg_pumps.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        save = dlg_pumps.exec_()
        if save:
            try:
                dlg_pumps.save_pumps()
                self.uc.bar_info(
                    "Pumps saved to 'Storm Drain-Pumps' User Layer!\n\n"
                    + "Schematize it from the 'Storm Drain Editor' widget before saving into SWMMOUTF.DAT"
                )
            except Exception:
                self.uc.bar_warn("Could not save pumps! Please check if they are correct.")
                return

        self.lyrs.clear_rubber()

    def show_orifices(self):
        """
        Shows orifices dialog.

        """
        # See if there are orifices:
        if self.gutils.is_table_empty("user_swmm_orifices"):
            self.uc.show_warn(
                'User Layer "Storm Drain Orifices" is empty!\n\n'
                + "Please import components from .INP file or shapefile, or convert from schematized Storm Drains."
            )
            return

        dlg_orifices = OrificesDialog(self.iface, self.lyrs)
        dlg_orifices.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        dlg_orifices.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        save = dlg_orifices.exec_()
        if save:
            try:
                dlg_orifices.save_orifices()
                self.uc.bar_info(
                    "Orifices saved to 'Storm Drain Orifices' User Layer!\n\n"
                    + "Schematize it from the 'Storm Drain Editor' widget before saving into SWMMOUTF.DAT"
                )
            except Exception:
                self.uc.bar_warn("Could not save orifices! Please check if they are correct.")
                return

        self.lyrs.clear_rubber()

    def show_weirs(self):
        """
        Shows weirs dialog.

        """
        # See if there are weirs:
        if self.gutils.is_table_empty("user_swmm_weirs"):
            self.uc.show_warn(
                'User Layer "Storm Drain Weirs" is empty!\n\n'
                + "Please import components from .INP file or shapefile, or convert from schematized Storm Drains."
            )
            return

        dlg_weirs = WeirsDialog(self.iface, self.lyrs)
        dlg_weirs.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        dlg_weirs.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        save = dlg_weirs.exec_()
        if save:
            try:
                dlg_weirs.save_weirs()
                self.uc.bar_info(
                    "Weirs saved to 'Storm Drain Weirs' User Layer!\n\n"
                    + "Schematize it from the 'Storm Drain Editor' widget before saving into SWMMOUTF.DAT"
                )
            except Exception:
                self.uc.bar_warn("Could not save weirs! Please check if they are correct.")
                return

        self.lyrs.clear_rubber()

    # def auto_assign_conduit_nodes(self):
    #     self.auto_assign_link_nodes("Conduits", "conduit_inlet", "conduit_outlet")
    #
    # def auto_assign_pump_nodes(self):
    #     self.auto_assign_link_nodes("Pumps", "pump_inlet", "pump_outlet")

    def auto_assign_link_nodes(self, link_name, link_inlet, link_outlet, SD_all_nodes_layer):
        """Auto assign Conduits, Pumps, orifices, or Weirs  (user layer) Inlet and Outlet names
           based on closest (5ft) nodes to their endpoints."""

        no_inlet = ""
        no_outlet = ""
        tabs = "\t\t\t\t"
        layer = (
            self.user_swmm_conduits_lyr
            if link_name == "Conduits"
            else self.user_swmm_pumps_lyr
            if link_name == "Pumps"
            else self.user_swmm_orifices_lyr
            if link_name == "Orifices"
            else self.user_swmm_weirs_lyr
            if link_name == "Weirs"
            else self.user_swmm_conduits_lyr
        )

        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            link_fields = layer.fields()
            link_inlet_fld_idx = link_fields.lookupField(link_inlet)
            link_outlet_fld_idx = link_fields.lookupField(link_outlet)

            nodes_features, nodes_index = spatial_index(SD_all_nodes_layer)
            segments = 5
            link_nodes = {}
            inlet_assignments = 0
            outlet_assignments = 0
            no_in = 0
            no_out = 0
            for feat in layer.getFeatures():
                fid = feat.id()
                geom = feat.geometry()
                geom_poly = geom.asPolyline()
                start_pnt, end_pnt = geom_poly[0], geom_poly[-1]
                start_geom = QgsGeometry.fromPointXY(start_pnt)
                end_geom = QgsGeometry.fromPointXY(end_pnt)
                start_buffer = start_geom.buffer(self.buffer_distance, segments)
                end_buffer = end_geom.buffer(self.buffer_distance, segments)
                start_nodes, end_nodes = [], []

                start_nodes_ids = nodes_index.intersects(start_buffer.boundingBox())
                for node_id in start_nodes_ids:
                    node_feat = nodes_features[node_id]
                    if node_feat.geometry().within(start_buffer):
                        start_nodes.append(node_feat)

                end_nodes_ids = nodes_index.intersects(end_buffer.boundingBox())
                for node_id in end_nodes_ids:
                    node_feat = nodes_features[node_id]
                    if node_feat.geometry().within(end_buffer):
                        end_nodes.append(node_feat)

                start_nodes.sort(key=lambda f: f.geometry().distance(start_geom))
                end_nodes.sort(key=lambda f: f.geometry().distance(end_geom))
                closest_inlet_feat = start_nodes[0] if start_nodes else None
                closest_outlet_feat = end_nodes[0] if end_nodes else None

                if closest_inlet_feat is not None:
                    inlet_name = closest_inlet_feat["name"]
                    inlet_assignments += 1
                else:
                    no_inlet += "{:<10}{:<20}{:<20}{:<20}".format("Inlet: ", feat[2].strip(), feat[1].strip(),
                                                                  link_name.strip()) + "\n"
                    # no_inlet += f"{feat[2].strip():<40}{feat[1].strip():<40}{link_name.strip():<40}\n"
                    # no_inlet += f"{feat[2].ljust(25, '-')}{feat[1].ljust(25, '-')}{link_name.ljust(25, '-')}\n"
                    # no_inlet += feat[2] + tabs + feat[1] + tabs + link_name + "\n"

                    # continue
                    inlet_name = "?"
                    no_in += 1

                if closest_outlet_feat is not None:
                    outlet_name = closest_outlet_feat["name"]
                    outlet_assignments += 1
                else:
                    no_outlet += "{:<10}{:<20}{:<20}{:<20}".format("Outlet: ", feat[3].strip(), feat[1].strip(),
                                                                   link_name.strip()) + "\n"
                    # no_outlet += f"{feat[3].strip():<40}{feat[1].strip():<40}{link_name.strip():<40}\n"
                    # no_outlet += f"{feat[3].ljust(25, '-')}{feat[1].ljust(25, '-')}{link_name.ljust(25, '-')}\n"
                    # no_outlet += feat[3] + tabs + feat[1] + tabs + link_name + "\n"

                    # continue
                    outlet_name = "?"
                    no_out += 1

                link_nodes[fid] = inlet_name, outlet_name

            layer.startEditing()
            for fid, (in_name, out_name) in link_nodes.items():
                layer.changeAttributeValue(fid, link_inlet_fld_idx, in_name)
                layer.changeAttributeValue(fid, link_outlet_fld_idx, out_name)
            layer.commitChanges()
            layer.triggerRepaint()

            QApplication.restoreOverrideCursor()

            msg = "Inlet and Outlet nodes assigned to " + str(len(link_nodes)) + " " + link_name + "!"
            QgsMessageLog.logMessage(msg, level=Qgis.Info, )

            if inlet_assignments > 0:
                self.auto_assign_msg += "✓ " + str(inlet_assignments) + " inlet assignments to " + link_name + "" + "\n"
            if outlet_assignments > 0:
                self.auto_assign_msg += "✓ " + str(
                    outlet_assignments) + " outlet assignments to " + link_name + "" + "\n"
            if no_in > 0:
                self.auto_assign_msg += "x   " + str(no_in) + " inlets not found for " + link_name + "" + "\n"
            if no_out > 0:
                self.auto_assign_msg += "x   " + str(no_out) + " outlets not found for " + link_name + "" + "\n"
            self.auto_assign_msg += "\n"

            hyphens = '-' * 60 + "\n"
            header = "       Inlet/Outlet Name      Link Name           Link Type" + "\n" + \
                     "-----------------------------------------------------------"
            if no_inlet:
                if self.no_nodes == "":
                    self.no_nodes = header
                self.no_nodes += "\n" + no_inlet

                # header = "{:<20}{:<20}{:<20}".format("Inlet Name", "Link Name", "Link Type") + "\n"
                # # header = "Inlet Name" + "\t\t" + "Link Name" + "\t\t" + "Link Type" + "\t\t" + "\n"
                # if self.no_nodes == "":
                #     self.no_nodes = header + hyphens +  no_inlet
                # else:
                #     self.no_nodes += "\n" +  no_inlet
            if no_outlet:
                if self.no_nodes == "":
                    self.no_nodes = header
                self.no_nodes += "\n" + no_outlet

                # header = "{:<20}{:<20}{:<20}".format("Outlet Name", "Link Name", "Link Type") + "\n"
                # # header = "Outlet Name" + "\t\t" + "Link Name" + "\t\t" + "Link Type" + "\t\t" + "\n"
                # if self.no_nodes == "":
                #     self.no_nodes = header + hyphens +  no_outlet
                # else:
                #     self.no_nodes += "\n" +  no_outlet

            # if link_name == "Conduits":
            #
            # elif link_name == "Pumps":
            #
            # elif link_name == "Orifices":
            #
            # elif link_name == "Weirs":

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 210322.0429: Couldn't assign " + link_name + " nodes!", e)

    def SD_import_type4(self):
        """
        Reads one or more rating table files.
        Name of file is the same as a type 4 inlet. Uses file names to associate file with inlet names.
        """
        self.uc.clear_bar_messages()

        if self.gutils.is_table_empty("user_model_boundary"):
            self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
            return
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        if self.gutils.is_table_empty("user_swmm_nodes"):
            self.uc.show_warn(
                'User Layer "Storm Drain Nodes" is empty!\n\n'
                + "Please import components from .INP file or shapefile, or convert from schematized Storm Drains."
            )
            return

        s = QSettings()
        last_dir = s.value("FLO-2D/lastSWMMDir", "")
        rating_files, __ = QFileDialog.getOpenFileNames(
            None,
            "Select files with rating table or Culvert equations data",
            directory=last_dir,
            filter="(*.TXT *.DAT);;(*.TXT);;(*.DAT);;(*.*)",
        )

        if not rating_files:
            return
        s.setValue("FLO-2D/lastSWMMDir", os.path.dirname(rating_files[0]))
        # update lastSWMMDir
        last_dir = s.value("FLO-2D/lastSWMMDir", "")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            errors0 = []
            errors1 = []
            noInlets = []
            lst_no_type4 = []
            str_no_type4 = ""
            warnings = []
            goodRT = 0
            goodCulverts = 0
            culvert_existed = 0
            badCulverts = 0
            already_a_rt = 0
            already_a_culvert = 0
            no_culvert_grids = []
            assignments = {}

            for file in rating_files:
                file_name, file_ext = os.path.splitext(os.path.basename(file))
                file_name = file_name.strip()

                if file_name.upper() == "TYPE4CULVERT":

                    with open(file, "r") as f1:
                        for line in f1:
                            culvert = line.split()
                            if culvert:
                                if len(culvert) == 7:
                                    grid_fid, name, cdiameter, typec, typeen, cubase, multbarrels = culvert
                                    if name:
                                        grid_sql = "SELECT grid FROM user_swmm_nodes WHERE name = ?;"
                                        grid = self.gutils.execute(grid_sql, (name,)).fetchone()
                                        if grid:
                                            exists = self.gutils.execute("SELECT * FROM swmmflo_culvert WHERE name = ?;", (name,)).fetchone()
                                            if exists:
                                                # Remove existing from swmmflo_culvert table:
                                                culvert_existed += 1
                                                self.gutils.execute("DELETE FROM swmmflo_culvert WHERE name = ?;", (name,))
                                            # Insert new Culvert eq:
                                            qry = """INSERT OR REPLACE INTO swmmflo_culvert 
                                                    (grid_fid, name, cdiameter, typec, typeen, cubase, multbarrels) 
                                                    VALUES (?, ?, ?, ?, ?, ?, ?);"""
                                            self.gutils.execute(
                                                qry, (grid[0], name, cdiameter, typec, typeen, cubase, multbarrels)
                                            )

                                            assignments[name] = "C"

                                            # Include Culvert eq. in dropdown list of type 4s:
                                            self.add_type4("CulvertEquation", file_name)
                                            # Assign Culvert name to user_swmm_nodes:
                                            assign_rt_name_sql = (
                                                "UPDATE user_swmm_nodes SET rt_name = ? WHERE name =?;"
                                            )
                                            self.gutils.execute(assign_rt_name_sql, (name, name))

                                            # See if there is a rating table with the same name:
                                            in_rt = self.gutils.execute(
                                                "SELECT * FROM swmmflort WHERE name = ?;", (name,)
                                            ).fetchone()
                                            if in_rt:
                                                # Remove existing rating table:

                                                swmm_fid = self.gutils.execute(
                                                    "SELECT fid FROM swmmflort WHERE name = ?", (name,)
                                                ).fetchone()
                                                self.gutils.execute("DELETE FROM swmmflort WHERE name = ?;", (name,))
                                                # Data in 'swmmflort_data' is deleted with already defined trigger.
                                                # self.gutils.execute("DELETE FROM swmmflort_data WHERE swmm_rt_fid = ?;", (swmm_fid[0],))
                                                # already_a_rt += 1
                                        else:
                                            no_culvert_grids.append((name, name))
                                else:
                                    # badCulverts += 1
                                    pass

                else:
                    err0, err1, err2, t4 = self.check_type4_file(file)
                    if err0 == "" and err1 == "" and err2 == "":

                        goodRT += 1
                        # Include rating table in dropdown list of type 4s:
                        self.add_type4(
                            "RatingTable", file_name
                        )  # Rating table 'file_name' is deleted from 'swmmflort' and its data from 'swmmflort_data' if they exist.
                        # New rating table 'file_name' added to 'swmmflort' (no data included in 'swmmflort_data'!
                        # that will be done further down):.

                        # Read depth and discharge from rating table file and add them to 'swmmflort_data':
                        swmm_fid = self.gutils.execute(
                            "SELECT fid FROM swmmflort WHERE name = ?", (file_name,)
                        ).fetchone()
                        if swmm_fid:
                            swmm_fid = swmm_fid[0]
                            self.gutils.execute("DELETE FROM swmmflort WHERE name = ?;", (file_name,))

                        data_sql = "INSERT INTO swmmflort_data (swmm_rt_fid, depth, q) VALUES (?, ?, ?)"
                        with open(file, "r") as f1:
                            for line in f1:
                                row = line.split()
                                if row:
                                    self.gutils.execute(data_sql, (swmm_fid, row[0], row[1]))

                        # Assign grid number to the just added rating table to 'swmmflort' table:
                        set_grid_sql = "INSERT OR REPLACE INTO swmmflort (grid_fid, name) VALUES (?, ?)"
                        grid_sql = "SELECT grid FROM user_swmm_nodes WHERE name = ?;"
                        grid = self.gutils.execute(grid_sql, (file_name,)).fetchone()[0]
                        if grid:
                            self.gutils.execute(set_grid_sql, (grid, file_name))

                        assignments[file_name] = "R"

                        # Assign rating table name to user_swmm_nodes:
                        assign_rt_name_sql = "UPDATE user_swmm_nodes SET rt_name = ? WHERE name =?;"
                        self.gutils.execute(assign_rt_name_sql, (file_name, file_name))

                        in_culvert = self.gutils.execute(
                            "SELECT * FROM swmmflo_culvert WHERE name = ?;", (file_name,)
                        ).fetchone()
                        if in_culvert:
                            # Remove culvert from swmmflo_culvert:
                            self.gutils.execute("DELETE FROM swmmflo_culvert WHERE name = ?;", (file_name,))
                    else:
                        if err0:
                            errors0.append(err0)
                        if err1:
                            errors1.append(err1)
                        if err2:
                            noInlets.append(err2)

                    if t4:
                        lst_no_type4.append(t4)
                        str_no_type4 += "\n" + t4

            self.SD_type4_cbo.setCurrentIndex(0)
            self.SD_show_type4_table_and_plot()

            txt2 = ""
            answer = True
            if lst_no_type4:
                QApplication.restoreOverrideCursor()
                answer = self.uc.question(
                    str(goodRT)
                    + " imported rating tables were assigned to inlets.\n\n"
                    + "Of those "
                    + str(goodRT)
                    + " inlets, "
                    + str(len(lst_no_type4))
                    + " are not of type 4 (inlet with stage-discharge rating table).\n\n"
                    + "Would you like to change their drain type to 4?"
                )
                if answer:
                    change_type_sql = "UPDATE user_swmm_nodes SET intype = ? WHERE name =?;"
                    for no4 in lst_no_type4:
                        self.gutils.execute(change_type_sql, (4, no4))
                    #                     lst_no_type4  = []
                    #                     str_no_type4 = ""
                    txt2 = (
                        "* " + str(len(lst_no_type4)) + " inlet's drain type changed to type 4 (stage-discharge).\n\n"
                    )
                else:
                    if len(lst_no_type4) > 1:
                        txt2 = (
                            "* "
                            + str(len(lst_no_type4))
                            + " inlet's drain type are not of type 4 (stage-discharge) but have rating table assigned.\n\n"
                        )
                    else:
                        txt2 = (
                            "* "
                            + str(len(lst_no_type4))
                            + " inlet's drain type is not of type 4 (stage-discharge) but has rating table assigned.\n\n"
                        )
                    self.uc.show_warn(
                        "WARNING 121220.1856:\n\n"
                        + "The following inlets were assigned rating tables but are not of type 4 (stage-discharge):\n"
                        + str_no_type4
                    )

            len_errors = len(errors0) + len(errors1)

            if errors0:
                errors0.append("\n")
            if errors1:
                errors1.insert(0,"The following files must have 2 columns in all lines!\n")
                errors1.append("\n")

            warnings = errors0 + errors1

            imported = ""
            # if len_errors + len(noInlets) + goodRT + goodCulverts == 0:
            if not assignments:
                imported = "No rating tables or Culvert equations imported.\n\n"
                # QApplication.restoreOverrideCursor()
                # self.uc.show_info("No rating tables or Culvert equations imported.")
                # return
            else:
                culverts, ratings = 0, 0
                for val in assignments.values():
                    if val == "C":
                        culverts += 1
                    elif val == "R":
                        ratings += 1
                imported = "* "  + str(culverts) + " Culvert Equations imported.\n\n"
                imported += "* " + str(ratings) + " Rating Tables imported.\n\n"


            # Write warnings file Rating Tables Warnings.CHK:
            CHK_file_length = len(assignments) + len(warnings) + len(str_no_type4) + len(noInlets)
            self.uc.log_info(str(last_dir + r"\Rating Tables Warnings.CHK"))
            if CHK_file_length > 0:
                with open(last_dir + r"\Rating Tables Warnings.CHK", "w") as report_file:
                    for key, value in assignments.items():
                        if value == "R":
                            report_file.write("Rating Table in file " + key + ".* assigned to inlet " + key + ".\n")
                        elif value == "C":
                            report_file.write("Culvert Equation from file TYPE4CULVERT.* assigned to inlet " + key + ".\n")

                    if warnings:
                        report_file.write("\n")
                        for w in warnings:
                            report_file.write(w + "\n")

                    if str_no_type4 != "":
                        if answer:
                            report_file.write(
                                "\nThe following inlets were assigned rating tables and its Drain type changed to 4 (stage-discharge):"
                                + str_no_type4
                                + "\n"
                            )
                        else:
                            report_file.write(
                                "\nThe following inlets were assigned rating tables but are not of type 4 (stage-discharge):"
                                + str_no_type4
                                + "\n"
                            )

                    if noInlets:
                        # report_file.write("\n")
                        for no in noInlets:
                            report_file.write(no + "\n")
            else:
                # Delete previous "Rating Tables Warnings.CHK" file if it exists:
                try:
                    if os.path.exists(last_dir + r"\Rating Tables Warnings.CHK"):
                        os.remove(last_dir + r"\Rating Tables Warnings.CHK")
                except OSError:
                    msg = "Couldn't remove existing outdated 'Rating Tables Warnings.CHK file'"
                    self.uc.bar_warn(msg)

            QApplication.restoreOverrideCursor()

            txt1 = " could not be read (maybe wrong format).\n\n"

            txt3 = (
                ""
                if not no_culvert_grids
                else "* "
                + str(len(no_culvert_grids))
                + " Culvert Equations were not read from file TYPE4CULVERT.* (inlet name not found in project).\n\n"
            )

            txt4 = (
                ""
                if already_a_rt == 0
                else "* "
                + str(already_a_rt)
                + " inlets in TYPE4CULVERT.* were already defined with rating tables.\n\n"
            )

            txt5 = (
                ""
                if already_a_culvert == 0
                else "* " + str(already_a_culvert) + " inlets replaced a rating table for a Culvert equation.\n\n"
            )

            txt6 = (
                ""
                if CHK_file_length == 0
                else "See details in file\n\n"
                    + os.path.dirname(rating_files[0])
                    + "/Rating Tables Warnings.CHK"
            )

            self.uc.show_info(
                "INFO 100823.0517:    (" + str(len(rating_files)) + " files selected)\n\n"
                + imported
                + (
                    "* " + str(len(noInlets)) + " rating tables were not read (no inlets with same name as the file name).\n\n"
                    if len(noInlets) > 0
                    else ""
                )
                # + "* "
                # + str(goodRT)
                # + " rating tables were assigned to inlets.\n\n"
                # + "* "
                # + str(goodCulverts)
                # + " Culvert equations were assigned to inlets.\n\n"
                + txt2
                + txt3
                + txt4
                + txt5
                + txt6
            )

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 131120.1846: reading rating tables failed!", e)
            return

    def import_hydraulics(self):
        """
        Shows import shapefile dialog.

        """
        if self.gutils.is_table_empty("user_model_boundary"):
            self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
            return

        point_or_line_layers = False
        layers = self.lyrs.list_group_vlayers()
        for l in layers:
            if l.geometryType() in [QgsWkbTypes.PointGeometry, QgsWkbTypes.LineGeometry]:
                if l.featureCount() > 0:
                    point_or_line_layers = True
                    break
        if not point_or_line_layers:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("There aren't any line or point layers (or they are not visible)!")
            return

        dlg_shapefile = StormDrainShapefile(self.con, self.iface, self.lyrs)
        dlg_shapefile.components_tabWidget.setCurrentPage = 0
        save = dlg_shapefile.exec_()
        if save:
            try:
                if dlg_shapefile.saveSelected:
                    self.uc.bar_info(
                        "Storm drain components (inlets, outfalls, and/or conduits) from hydraulic layers saved."
                    )

            except Exception as e:
                self.uc.bar_error("ERROR while saving storm drain components from hydraulic layers!.")
        # else:
        #     self.uc.bar_warn("Storm drain components not saved!")

    def create_conduit_discharge_table_and_plots(self, intersection=None):
        """
        Create Storm Drain conduit plots.
        """
        self.uc.clear_bar_messages()
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return False

        s = QSettings()
        GDS_dir = s.value("FLO-2D/lastGdsDir", "")
        RPT_file = GDS_dir + r"\swmm.RPT"
        # Check if there is an RPT file on the export folder
        if not os.path.isfile(RPT_file):
            self.uc.bar_warn(
                "No swmm.RPT file found. Please ensure the simulation has completed and verify the project export folder.")
            return

        # Check if the swmm.RPT has data on it
        if os.path.getsize(RPT_file) == 0:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("File  '" + os.path.basename(RPT_file) + "'  is empty!")
            self.uc.bar_warn("WARNING 111123.1744: File  '" + os.path.basename(RPT_file) + "'  is empty!\n" +
                             "Select a valid .RPT file.")
            return

        if intersection:
            with open(RPT_file) as f:
                if not intersection in f.read():
                    self.uc.bar_error("Link " + intersection + " not found in file " + RPT_file)
                    self.uc.bar_warn("WARNING 111123.1742: Link " + intersection + " not found in file\n\n" + RPT_file +
                                     "\n\nSelect a valid .RPT file.")
                    return

        data = OrderedDict()
        # Read RPT file.
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)

            pd = ParseDAT()
            par = pd.single_parser(RPT_file)

            previous = []
            units = "CMS"
            for row in par:
                if "Flow" in row and "Units" in row:
                    units = "CMS" if "CMS" in row else "CFS" if "CFS" in row else "CMS"
                if previous:
                    cell = previous[2]
                    for _ in range(3):
                        next(par)
                if "<<<" in row and "Link" in row:
                    cell = row[2]
                    for _ in range(4):
                        next(par)
                if previous or ("<<<" in row and "Link" in row):
                    previous = []
                    data[cell] = []
                    for row2 in par:
                        if "<<<" in row2 and "Link" in row2:
                            previous = row2
                            break
                        if row2:
                            if len(row2) == 6:
                                data[cell].append(list(row2))
                            else:
                                break

            if data:
                if intersection is False:
                    intersection = next(iter(data.items()))[0]
                if not intersection in data:
                    QApplication.restoreOverrideCursor()
                    self.plot.clear()
                    self.tview.model().setRowCount(0)
                    self.uc.bar_error("Link " + intersection + " not found in file  '" + RPT_file + "'")

                    QApplication.restoreOverrideCursor()
                    self.uc.bar_warn("WARNING 111123.1743: Link " + intersection + " not found in file\n\n" + RPT_file +
                                     "\n\nSelect a valid .RPT file.")
                    return

                node_series = data[intersection]
                I = 1
                day = 0
                previousHour = -1
                RPTtimeSeries = []

                for nextTime in node_series:
                    time = nextTime[1]
                    flow = float(nextTime[2])
                    velocity = float(nextTime[3])
                    depth = float(nextTime[4])
                    percent_full = float(nextTime[5])
                    currentHour, minutes, seconds = time.split(":")
                    currentHour = int(currentHour)
                    minutes = int(minutes) / 60
                    seconds = int(seconds) / 3600
                    if currentHour < previousHour:
                        day = day + 24
                    previousHour = currentHour
                    hour = day + currentHour + minutes + seconds
                    RPTtimeSeries.append([hour, flow, velocity, depth, percent_full])

                # Plot discharge graph:
                self.uc.bar_info("Results for link " + intersection + " from file  '" + RPT_file + "'")

                try:
                    self.plot.clear()
                    timeRPT, flowRPT, velocityRPT, depthRPT, percent_fullRPT = [], [], [], [], []

                    for row in RPTtimeSeries:
                        timeRPT.append(row[0] if not row[0] is None else float("NaN"))
                        flowRPT.append(row[1] if not row[1] is None else float("NaN"))
                        velocityRPT.append(row[2] if not row[2] is None else float("NaN"))
                        depthRPT.append(row[3] if not row[3] is None else float("NaN"))
                        percent_fullRPT.append(row[4] if not row[4] is None else float("NaN"))

                    if self.plot.plot.legend is not None:
                        plot_scene = self.plot.plot.legend.scene()
                        if plot_scene is not None:
                            plot_scene.removeItem(self.plot.plot.legend)

                    self.plot.plot.legend = None
                    self.plot.plot.addLegend()
                    self.plot.plot.setTitle(title="Results for " + intersection)
                    self.plot.plot.setLabel("bottom", text="Time (hours)")
                    self.plot.add_item(f"Flow ({self.system_units[units][2]})", [timeRPT, flowRPT], col=QColor(Qt.darkGreen), sty=Qt.SolidLine)
                    self.plot.add_item(f"Velocity ({self.system_units[units][1]})", [timeRPT, velocityRPT], col=QColor(Qt.red), sty=Qt.SolidLine, hide=True)
                    self.plot.add_item(f"Depth ({self.system_units[units][0]})", [timeRPT, depthRPT], col=QColor(Qt.darkMagenta), sty=Qt.SolidLine, hide=True)
                    self.plot.add_item(f"Percent Full (%)", [timeRPT, percent_fullRPT], col=QColor(Qt.darkGray), sty=Qt.SolidLine, hide=True)

                    # self.plot.plot.setLabel("left", text="Units of measurement: " + units)
                    QApplication.restoreOverrideCursor()

                except:
                    QApplication.restoreOverrideCursor()
                    self.uc.bar_warn("Error while building plot for SD discharge!")
                    return

                try:  # Build table.
                    discharge_data_model = StandardItemModel()
                    self.tview.undoStack.clear()
                    self.tview.setModel(discharge_data_model)
                    discharge_data_model.clear()
                    discharge_data_model.setHorizontalHeaderLabels(["Time (hours)",
                                                                    f"Flow ({self.system_units[units][2]})",
                                                                    f"Velocity ({self.system_units[units][1]})",
                                                                    f"Depth ({self.system_units[units][0]})",
                                                                    f"Percent Full (%)"])
                    for row in RPTtimeSeries:
                        items = [StandardItem("{:.2f}".format(x)) if x is not None else StandardItem("") for x in row]
                        discharge_data_model.appendRow(items)
                    self.tview.horizontalHeader().setStretchLastSection(True)
                    for col in range(3):
                        self.tview.setColumnWidth(col, 100)
                    for i in range(discharge_data_model.rowCount()):
                        self.tview.setRowHeight(i, 20)
                    QApplication.restoreOverrideCursor()
                    return
                except:
                    QApplication.restoreOverrideCursor()
                    self.uc.bar_warn("Error while building table for SD discharge!")
                    return

            else:
                QApplication.restoreOverrideCursor()
                self.uc.bar_error("No time series found in file " + RPT_file + " for node " + intersection)

            QApplication.restoreOverrideCursor()
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.bar_error("Reading .RPT file failed!")
            return False

    def create_SD_discharge_table_and_plots(self, intersection=None):
        """
        Export Storm Drain Discharge plots.
        """
        self.uc.clear_bar_messages()
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return False

        s = QSettings()
        GDS_dir = s.value("FLO-2D/lastGdsDir", "")
        # Check if there is an RPT file on the FLO-2D QSettings
        RPT_file = GDS_dir + r"\swmm.RPT"
        # Check if there is an RPT file on the export folder
        if not os.path.isfile(RPT_file):
            self.uc.bar_warn("No swmm.RPT file found. Please ensure the simulation has completed and verify the project export folder.")
            return

        # Check if the swmm.RPT has data on it
        if os.path.getsize(RPT_file) == 0:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("File  '" + os.path.basename(RPT_file) + "'  is empty!")
            self.uc.bar_warn("WARNING 111123.1744: File  '" + os.path.basename(RPT_file) + "'  is empty!\n" +
                                "Select a valid .RPT file.")
            return

        if intersection:
            with open(RPT_file) as f:
                if not intersection in f.read():
                    self.uc.bar_error("Node " + intersection + " not found in file " + RPT_file)
                    # QApplication.restoreOverrideCursor()
                    self.uc.bar_warn("WARNING 111123.1742: Node " + intersection + " not found in file\n\n" + RPT_file +
                                        "\n\nSelect a valid .RPT file.")
                    return

        data = OrderedDict()
        # Read RPT file.
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)

            pd = ParseDAT()
            par = pd.single_parser(RPT_file)

            previous = []
            units = "CMS"
            for row in par:
                if "Flow" in row and "Units" in row:
                    units = "CMS" if "CMS" in row else "CFS" if "CFS" in row else "CMS"
                if previous:
                    cell = previous[2]
                    for _ in range(3):
                        next(par)
                if "<<<" in row and "Node" in row:
                    cell = row[2]
                    for _ in range(4):
                        next(par)
                if previous or ("<<<" in row and "Node" in row):
                    previous = []
                    data[cell] = []
                    for row2 in par:
                        if "<<<" in row2 and "Node" in row2:
                            previous = row2
                            break
                        if row2:
                            if len(row2) == 6:
                                data[cell].append(list(row2))
                            else:
                                break

            if data:
                if intersection is False:
                    intersection = next(iter(data.items()))[0]
                if not intersection in data:
                    QApplication.restoreOverrideCursor()
                    self.plot.clear()
                    self.tview.model().setRowCount(0)
                    self.uc.bar_error("Node " + intersection + " not found in file  '" + RPT_file + "'")

                    QApplication.restoreOverrideCursor()
                    self.uc.bar_warn("WARNING 111123.1743: Node " + intersection + " not found in file\n\n" + RPT_file +
                                        "\n\nSelect a valid .RPT file.")
                    return

                node_series = data[intersection]
                I = 1
                day = 0
                previousHour = -1
                RPTtimeSeries = []
                inflow_discharge_to_SD = []
                outfall_discharge_to_FLO_2D = []
                SWMMQINtimeSeries = []
                SWMMOUTFINtimeSeries = []

                for nextTime in node_series:
                    time = nextTime[1]
                    inflow = float(nextTime[2])
                    flooding = float(nextTime[3])
                    depth = float(nextTime[4])
                    head = float(nextTime[5])
                    currentHour, minutes, seconds = time.split(":")
                    currentHour = int(currentHour)
                    minutes = int(minutes) / 60
                    seconds = int(seconds) / 3600
                    if currentHour < previousHour:
                        day = day + 24
                    previousHour = currentHour
                    hour = day + currentHour + minutes + seconds
                    RPTtimeSeries.append([hour, inflow, flooding, depth, head])

                # See if there are aditional .DAT files with SD data:
                SWMMQIN_file = GDS_dir + r"\SWMMQIN.OUT"
                if not os.path.isfile(SWMMQIN_file):
                    self.uc.bar_info("There is no SWMMQIN.OUT file")
                else:
                    inflow_discharge_to_SD = self.get_SWMMQIN(SWMMQIN_file)
                    if intersection in inflow_discharge_to_SD:
                        node_series = inflow_discharge_to_SD[intersection]
                        I = 1
                        day = 0
                        previousHour = -1

                        for nextTime in node_series:
                            hour = float(nextTime[0])
                            discharge = float(nextTime[1])
                            return_flow = float(nextTime[2])
                            SWMMQINtimeSeries.append([hour, discharge, return_flow])
                    else:
                        self.uc.bar_info("Node " + intersection + " is not in file SWMMQIN.OUT")

                SWMMOUTFIN_file = GDS_dir + r"\SWMMOUTFIN.OUT"
                if not os.path.isfile(SWMMOUTFIN_file):
                    self.uc.bar_info("There is no SWMMOUTFIN.OUT file")
                else:
                    outfall_discharge_to_FLO_2D = self.get_SWMMOUTFIN(SWMMOUTFIN_file)
                    grid_sql = "SELECT grid FROM user_swmm_nodes WHERE name = ?;"
                    grid = self.gutils.execute(grid_sql,(intersection,)).fetchone()
                    if grid:
                        grid = str(grid[0])
                        if grid in outfall_discharge_to_FLO_2D:
                            node_series = outfall_discharge_to_FLO_2D[grid]
                            I = 1
                            day = 0
                            previousHour = -1

                            for nextTime in node_series:
                                hour = float(nextTime[0])
                                discharge = float(nextTime[1])
                                SWMMOUTFINtimeSeries.append([hour, discharge])
                        else:
                            self.uc.bar_info("Node " + intersection + " is not in file SWMMOUTFIN.OUT")
                    else:
                        self.uc.bar_info("Grid " + grid + " not found in Storm Drain Nodes!")

                # Plot discharge graph:
                self.uc.bar_info("Discharge for node " + intersection + " from file  '" + RPT_file + "'")
                self.show_discharge_table_and_plot(intersection, units, RPTtimeSeries,
                                                   SWMMQINtimeSeries,
                                                   SWMMOUTFINtimeSeries)
            else:
                QApplication.restoreOverrideCursor()
                self.uc.bar_error("No time series found in file " + RPT_file + " for node " + intersection)

            QApplication.restoreOverrideCursor()
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.bar_error("Reading .RPT file failed!")
            return False

    def block_saving(self):
        model = self.tview.model()
        if model == self.inlet_data_model:
            try_disconnect(self.inlet_data_model.dataChanged, self.save_SD_table_data)
        elif model == self.pumps_data_model:
            try_disconnect(self.pumps_data_model.dataChanged, self.save_SD_table_data)

    def unblock_saving(self):
        model = self.tview.model()
        if model == self.inlet_data_model:
            self.inlet_data_model.dataChanged.connect(self.save_SD_table_data)
        elif model == self.pumps_data_model:
            self.pumps_data_model.dataChanged.connect(self.save_SD_table_data)

    def inlet_itemDataChangedSlot(self, item, old_value, new_value, role, save=True):
        """
        Slot used to push changes of existing items onto undoStack.
        """
        if role == Qt.EditRole:
            command = CommandItemEdit(
                self, item, old_value, new_value, "Text changed from '{0}' to '{1}'".format(old_value, new_value)
            )
            self.tview.undoStack.push(command)
            return True

    def pump_itemDataChangedSlot(self, item, old_value, new_value, role, save=True):
        """
        Slot used to push changes of existing items onto undoStack.
        """
        if role == Qt.EditRole:
            command = CommandItemEdit(
                self, item, old_value, new_value, "Text changed from '{0}' to '{1}'".format(old_value, new_value)
            )
            self.tview.undoStack.push(command)
            return True

    def itemDataChangedSlot(self, item, old_value, new_value, role, save=True):
        """
        Slot used to push changes of existing items onto undoStack.
        """
        if role == Qt.EditRole:
            command = CommandItemEdit(
                self, item, old_value, new_value, "Text changed from '{0}' to '{1}'".format(old_value, new_value)
            )
            self.tview.undoStack.push(command)
            return True

    def populate_type4_and_data(self):
        self.populate_type4_combo()
        self.SD_show_type4_table_and_plot()

    def populate_type4_combo(self):
        self.SD_type4_cbo.clear()
        duplicates = ""
        # Load rating tables:
        for row in self.inletRT.get_rating_tables():
            rt_fid, name = [x if x is not None else "" for x in row]
            if name != "":
                if self.SD_type4_cbo.findText(name) == -1:
                    self.SD_type4_cbo.addItem(name, rt_fid)
                else:
                    duplicates += name + "\n"

        # Load Culvert equations:
        culverts = self.gutils.execute(
            "SELECT fid, grid_fid, name, cdiameter, typec, typeen, cubase, multbarrels FROM swmmflo_culvert ORDER BY fid;"
        ).fetchall()
        if culverts:
            for culv in culverts:
                fid, grid_fid, name, cdiameter, typec, typeen, cubase, multbarrels = culv
                if name and name != "":
                    if self.SD_type4_cbo.findText(name) == -1:
                        self.SD_type4_cbo.addItem(name, 9999 + fid)
                    else:
                        duplicates += name + "\n"

    def populate_profile_plot(self):
        """
        Function to populate the nodes on the comboboxes and check for a .RPT file
        """
        self.start_node_cbo.clear()
        self.end_node_cbo.clear()

        nodes_names = self.gutils.execute("SELECT name FROM user_swmm_nodes").fetchall()
        if not nodes_names:
            return

        for name in nodes_names:
            self.start_node_cbo.addItem(name[0])
            self.end_node_cbo.addItem(name[0])

    def show_profile(self):
        """
        Function to show the profile
        """
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            import swmmio
        except ImportError:
            QApplication.restoreOverrideCursor()
            message = "The swmmio library is not found in your python environment. This external library is required to " \
                      "run some processes related to swmm files. More information on: https://swmmio.readthedocs.io/en/v0.6.11/.\n\n" \
                      "Would you like to install it automatically or " \
                      "manually?\n\nSelect automatic if you have admin rights. Otherwise, contact your admin and " \
                      "follow the manual steps."
            title = "External library not found!"
            button1 = "Automatic"
            button2 = "Manual"

            install_options = self.uc.dialog_with_2_customized_buttons(title, message, button1, button2)

            if install_options == QMessageBox.Yes:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                try:
                    import pathlib as pl
                    import subprocess
                    import sys

                    qgis_Path = pl.Path(sys.executable)
                    qgis_python_path = (qgis_Path.parent / "python3.exe").as_posix()

                    subprocess.check_call(
                        [qgis_python_path, "-m", "pip", "install", "--user", "swmmio==0.6.11"]
                    )
                    import swmmio
                    self.uc.bar_info("swmmio successfully installed!")
                    self.uc.log_info("swmmio successfully installed!")
                    QApplication.restoreOverrideCursor()

                except ImportError as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_critical("Error while installing swmmio. Install it manually.")

            # Manual Installation
            elif install_options == QMessageBox.No:
                QApplication.restoreOverrideCursor()
                message = "1. Run OSGeo4W Shell as admin\n" \
                          "2. Type this command: pip install swmmio==0.6.11\n\n" \
                          "Wait the process to finish and rerun this process.\n\n" \
                          "For more information, access https://flo-2d.com/contact/"
                self.uc.show_info(message)
                return
            else:
                return

        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return False

        QApplication.restoreOverrideCursor()
        s = QSettings()
        GDS_dir = s.value("FLO-2D/lastGdsDir", "")
        RPT_file = GDS_dir + r"\swmm.RPT"
        rpt_file = GDS_dir + r"\swmm.rpt"
        INP_file = GDS_dir + r"\SWMM.INP"
        inp_file = GDS_dir + r"\SWMM.inp"
        # Check if there is an RPT and an INP file on the export folder
        if not os.path.isfile(INP_file) or not os.path.isfile(inp_file):
            self.uc.bar_warn(
                "No SWMM.INP file found. Please ensure the simulation has completed and verify the project export "
                "folder.")
            return
        if not os.path.isfile(RPT_file) or not os.path.isfile(rpt_file):
            self.uc.bar_warn(
                "No swmm.RPT file found. Please ensure the simulation has completed and verify the project export "
                "folder.")
            return

        # SWMMIO only read small cap extensions
        if not os.path.isfile(inp_file):
            os.rename(INP_file, INP_file[:-4] + '.inp')

        if not os.path.isfile(rpt_file):
            os.rename(RPT_file, RPT_file[:-4] + '.rpt')

        mymodel = swmmio.Model(inp_file)
        rpt = swmmio.rpt(rpt_file)

        start_node = self.start_node_cbo.currentText()
        end_node = self.end_node_cbo.currentText()

        try:
            path_selection = swmmio.find_network_trace(mymodel, start_node, end_node)
            max_depth = rpt.node_depth_summary.MaxNodeDepth
            ave_depth = rpt.node_depth_summary.AvgDepth
        except:
            self.uc.bar_warn("No path found!")
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        dlg_sd_profile_view = SDProfileView(self.gutils)
        dlg_sd_profile_view.plot_profile(swmmio, mymodel, path_selection, max_depth, ave_depth)
        QApplication.restoreOverrideCursor()
        dlg_sd_profile_view.show()
        while True:
            ok = dlg_sd_profile_view.exec_()
            if ok:
                break
            else:
                return

    def SD_show_type4_table_and_plot(self):
        self.SD_table.after_delete.disconnect()
        self.SD_table.after_delete.connect(self.save_SD_table_data)
    
        self.plot.clear()     
    
        idx = self.SD_type4_cbo.currentIndex()
        fid = self.SD_type4_cbo.itemData(idx)
        name = self.SD_type4_cbo.currentText()
        if fid is None:
            #             self.uc.bar_warn("No table defined!")
            return
    
        in_culvert = self.gutils.execute(
            "SELECT cdiameter, typec, typeen, cubase, multbarrels FROM swmmflo_culvert WHERE name = ?;", (name,)
            ).fetchone() 
    
        if in_culvert:
    
            self.tview.undoStack.clear()
            self.tview.setModel(self.inlet_data_model)
            self.inlet_data_model.clear()
            self.inlet_data_model.setHorizontalHeaderLabels(["CDDIAMETER", "TYPEC", "TYPEEN", "CUBASE", "MULTBARRELS"])
            self.d1, self.d2= [[], []]
    
            items = [StandardItem("{:.4f}".format(x)) if type(x) is float else 
                    StandardItem("{}".format(x)) if type(x) is int else                     
                     StandardItem("") for x in in_culvert]
    
            self.inlet_data_model.appendRow(items)
    
            rc = self.inlet_data_model.rowCount()
            if rc < 500:
                for row in range(rc, 500 + 1):
                    items = [StandardItem(x) for x in ("",) * 2]
                    self.inlet_data_model.appendRow(items)
    
            self.tview.horizontalHeader().setStretchLastSection(True)
            for col in range(2):
                self.tview.setColumnWidth(col, 100)
            for i in range(self.inlet_data_model.rowCount()):
                self.tview.setRowHeight(i, 20)
    
        else:
            self.inlet_series_data = self.inletRT.get_inlet_table_data(fid)
            if not self.inlet_series_data:
                self.tview.undoStack.clear()
                self.tview.setModel(self.inlet_data_model)
                self.inlet_data_model.clear()            
                return
    
            self.create_rt_plot(name)
    
            self.tview.undoStack.clear()
            self.tview.setModel(self.inlet_data_model)
            self.inlet_data_model.clear()
            self.inlet_data_model.setHorizontalHeaderLabels(["Depth", "Q"])
            self.d1, self.d2= [[], []]
    
            for row in self.inlet_series_data:
                items = [StandardItem("{:.4f}".format(x)) if x is not None else StandardItem("") for x in row]
                self.inlet_data_model.appendRow(items)
                self.d1.append(row[0] if not row[0] is None else float("NaN"))
                self.d2.append(row[1] if not row[1] is None else float("NaN"))
    
            rc = self.inlet_data_model.rowCount()
            if rc < 500:
                for row in range(rc, 500 + 1):
                    items = [StandardItem(x) for x in ("",) * 2]
                    self.inlet_data_model.appendRow(items)
    
            self.tview.horizontalHeader().setStretchLastSection(True)
            for col in range(2):
                self.tview.setColumnWidth(col, 100)
            for i in range(self.inlet_data_model.rowCount()):
                self.tview.setRowHeight(i, 20)
    
            self.update_rt_plot()

    def show_discharge_table_and_plot(self, node, units,
                                      RPTseries, 
                                      SWMMQINtimeSeries, 
                                      SWMMOUTFINtimeseries):
        try:
            self.SD_table.after_delete.disconnect()
            self.SD_table.after_delete.connect(self.save_SD_table_data)
            
            grid_sql = "SELECT grid FROM user_swmm_nodes WHERE name = ?;"
            grid = self.gutils.execute(grid_sql,(node,)).fetchone()
            if grid:
                grid = str(grid[0])
            else:
                grid = "?"          

            try: # Build plot.
                self.plot.clear()
                timeRPT, inflowRPT, floodingRPT, depthRPT, headRPT = [], [], [], [], []
                timeInToSD, dischargeInToSD, returnInToSD = [], [], []
                timeOutToFLO, dischargeOutToFLO = [], []
                
                for row in RPTseries:
                    timeRPT.append(row[0] if not row[0] is None else float("NaN"))
                    inflowRPT.append(row[1] if not row[1] is None else float("NaN"))
                    floodingRPT.append(row[2] if not row[2] is None else float("NaN"))
                    depthRPT.append(row[3] if not row[3] is None else float("NaN"))
                    headRPT.append(row[4] if not row[4] is None else float("NaN"))
                
                if SWMMQINtimeSeries:
                    for row in SWMMQINtimeSeries:
                        timeInToSD.append(row[0] if not row[0] is None else float("NaN"))
                        dischargeInToSD.append(row[1] if not row[1] is None else float("NaN"))
                        returnInToSD.append(row[2] if not row[2] is None else float("NaN")) 
                
                if SWMMOUTFINtimeseries:
                    for row in SWMMOUTFINtimeseries:
                        timeOutToFLO.append(row[0] if not row[0] is None else float("NaN"))
                        dischargeOutToFLO.append(row[1] if not row[1] is None else float("NaN"))
                
                if self.plot.plot.legend is not None:
                    plot_scene = self.plot.plot.legend.scene()
                    if plot_scene is not None:
                        plot_scene.removeItem(self.plot.plot.legend)
                
                self.plot.plot.legend = None
                self.plot.plot.addLegend()
                self.plot.plot.setTitle(title="Discharge " + node + " (grid " + grid + ")")
                self.plot.plot.setLabel("bottom", text="Time (hours)")
                self.plot.add_item(f"Total Inflow ({self.system_units[units][2]})", [timeRPT, inflowRPT], col=QColor(Qt.darkGreen), sty=Qt.SolidLine)
                self.plot.add_item(f"Flooding ({self.system_units[units][2]})", [timeRPT, floodingRPT], col=QColor(Qt.red), sty=Qt.SolidLine, hide=True)
                self.plot.add_item(f"Depth ({self.system_units[units][0]})", [timeRPT, depthRPT], col=QColor(Qt.darkMagenta), sty=Qt.SolidLine, hide=True)
                self.plot.add_item(f"Head ({self.system_units[units][0]})", [timeRPT, headRPT], col=QColor(Qt.darkGray), sty=Qt.SolidLine, hide=True)
                
                if SWMMQINtimeSeries:
                    self.plot.add_item(f"Inflow Discharge to Storm Drain ({self.system_units[units][2]})", [timeInToSD, dischargeInToSD], col=QColor(Qt.blue), sty=Qt.SolidLine, hide=True)
                    self.plot.add_item(f"Return Discharge to FLO-2D ({self.system_units[units][2]})", [timeInToSD, returnInToSD], col=QColor(Qt.darkYellow), sty=Qt.SolidLine, hide=True)
                
                if SWMMOUTFINtimeseries:
                    self.plot.add_item(f"Discharge to FLO-2D ({self.system_units[units][2]})", [timeOutToFLO, dischargeOutToFLO], col=QColor(Qt.black), sty=Qt.SolidLine, hide=True)
                
                # self.plot.plot.setLabel("left", text="Discharge (" + units + ")")
                
            except:
                QApplication.restoreOverrideCursor()
                self.uc.bar_warn("Error while building plot for SD discharge!")
                return

            try: # Build table.
                discharge_data_model = StandardItemModel()
                self.tview.undoStack.clear()
                self.tview.setModel(discharge_data_model)
                discharge_data_model.clear()
                discharge_data_model.setHorizontalHeaderLabels(["Time (hours)",
                                                                f"Inflow ({self.system_units[units][2]})",
                                                                f"Flooding ({self.system_units[units][2]})",
                                                                f"Depth ({self.system_units[units][0]})",
                                                                f"Head ({self.system_units[units][0]})"])
                for row in RPTseries:
                    items = [StandardItem("{:.2f}".format(x)) if x is not None else StandardItem("") for x in row]
                    discharge_data_model.appendRow(items)
                self.tview.horizontalHeader().setStretchLastSection(True)
                for col in range(3):
                    self.tview.setColumnWidth(col, 100)
                for i in range(discharge_data_model.rowCount()):
                    self.tview.setRowHeight(i, 20)
                return
            except:
                QApplication.restoreOverrideCursor()
                self.uc.bar_warn("Error while building table for SD discharge!")
                return
            
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("Error while creating discharge plot for node "  + node, e)
            return            

    def get_SWMMQIN(self, SWMMQIN_file):
        data = OrderedDict()            
        try: # Read SWMMQIN_file.      
            pd = ParseDAT()
            par = pd.single_parser(SWMMQIN_file)
            for row in par:
                if "INLET" in row:
                    cell = row[7]
                    inlet =  row[11]
                    next(par)
                    data[inlet] = []   
                    for row2 in par:
                        if len(row2)==3:
                            time = row2[0]
                            discharge = row2[1]
                            return_flow = row2[2]
                            data[inlet].append(row2)
                        elif "INLET" in row2:
                            cell = row2[7]
                            inlet =  row2[11]
                            next(par)
                            data[inlet] = [] 
        except Exception as e:
            self.uc.show_error("Error while reading file\n\n "  + SWMMQIN_file, e)
        finally:
            return data
         
    def get_SWMMOUTFIN(self, SWMMOUTFIN_file):
        data = OrderedDict()            
        try: # Read SWMMOUTFIN_file.      
            pd = ParseDAT()
            par = pd.single_parser(SWMMOUTFIN_file)
            for row in par:
                if "GRID" in row:
                    cell = row[2]
                    # channel_element=  row[5]
                    next(par)
                    data[cell] = []   
                    for row2 in par:
                        if len(row2)==2:
                            time = row2[0]
                            discharge = row2[1]
                            data[cell].append(row2)
                        elif "GRID" in row2:
                            cell = row2[2]
                            # channel_element=  row2[5]
                            next(par)
                            data[cell] = []  
        except Exception as e:
            self.uc.show_error("Error while reading file\n\n "  + SWMMOUTFIN_file, e)
        finally:
            return data  
         
    def check_simulate_SD_1(self):
        qry = """SELECT value FROM cont WHERE name = 'SWMM';"""
        row = self.gutils.execute(qry).fetchone()
        if is_number(row[0]):
            if row[0] == "0":
                self.simulate_stormdrain_chbox.setChecked(False)
            else:
                self.simulate_stormdrain_chbox.setChecked(True)

    def check_type4_file(self, afile):
        file_name, file_ext = os.path.splitext(os.path.basename(afile))
        error0 = ""
        error1 = ""
        noInlet = ""
        no_4Type = ""

        # Is file empty?:
        if not os.path.isfile(afile):
            error0 = "File " + file_name + file_ext + " is being used by another process!"
            return error0, error1, noInlet, no_4Type
        elif os.path.getsize(afile) == 0:
            error0 = "File " + file_name + file_ext + " is empty!"
            return error0, error1, noInlet, no_4Type

        # Check 2 float values in columns:
        try:
            with open(afile, "r") as f:
                for line in f:
                    row = line.split()
                    if row:
                        if len(row) == 2:
                            pass
                        else:
                            error1 = file_name + file_ext 
                            return error0, error1, noInlet, no_4Type
        except UnicodeDecodeError:
            error0 = file_name + file_ext + " is not a text file!"
            return error0, error1, noInlet, no_4Type

        # Check there is an inlet with the same name:
        if file_name.upper() == "TYPE4CULVERT":
            return error0, error1, noInlet, no_4Type
        else:
            user_inlet_qry = """SELECT name, intype FROM user_swmm_nodes WHERE name = ?;"""
            row = self.gutils.execute(user_inlet_qry, (file_name,)).fetchone()
            if not row:
                noInlet = "There isn't an inlet with name " + file_name
            elif row[1] != 4:
                no_4Type = file_name

        return error0, error1, noInlet, no_4Type

    def nodes_component_changed(self):
        idx = self.SD_nodes_components_cbo.currentIndex()
        if idx == 1:
            self.show_inlets()
        elif idx == 2:
            self.show_outfalls()
        elif idx == 3:
            self.show_storage_units()                

        self.SD_nodes_components_cbo.setCurrentIndex(0)

    def links_component_changed(self):
        idx = self.SD_links_components_cbo.currentIndex()
        if idx == 1:
            self.show_conduits()
        elif idx == 2:
            self.show_pumps()
        elif idx == 3:
            self.show_orifices()
        elif idx == 4:
            self.show_weirs()

        self.SD_links_components_cbo.setCurrentIndex(0)

    def auto_assign(self):

        if self.gutils.is_table_empty("user_swmm_conduits") and self.gutils.is_table_empty("user_swmm_pumps") and \
                self.gutils.is_table_empty("user_swmm_orifices") and self.gutils.is_table_empty("user_swmm_weirs"):
            self.uc.show_info("There are no links defined!")
            return

        try:

            layer1 = QgsProject.instance().mapLayersByName('Storm Drain Nodes')[0]
            layer2 = QgsProject.instance().mapLayersByName('Storm Drain Storage Units')[0]
            # Create a new memory layer for point geometries
            SD_all_nodes_layer = QgsVectorLayer("Point", 'SD All Points', 'memory')

            crs = layer1.crs()  # crs is a QgsCoordinateReferenceSystem
            unit = crs.mapUnits()  # unit is a QgsUnitTypes.DistanceUnit

            if QgsProject.instance().crs().mapUnits() == QgsUnitTypes.DistanceMeters:
                distance_units = "mts"
            else:
                distance_units = "feet"

            dialog = TwoInputsDialog("Do you want to overwrite Inlet and Outlet nodes\n" +
                                     "for all links (conduits, pumps, orifices, and weirs)?",
                                     "Find a node located at a distance\nless than this from the link (in " + distance_units + " )",
                                     self.buffer_distance, "", 5)
            if dialog.exec() == QMessageBox.Accepted:
                self.buffer_distance = dialog.first_input.value()
            else:
                return

            # if not self.uc.question("Do you want to overwrite Inlet and Outlet node names\n" +
            #                            "for all conduits, pumps, orifices, and weirs?"):
            #     return

            fields = QgsFields()
            fields.append(QgsField('name', QVariant.String))

            pr = SD_all_nodes_layer.dataProvider()

            pr.addAttributes(fields)
            SD_all_nodes_layer.updateFields()

            # Iterate through features and add point geometries
            for layer in [layer1, layer2]:
                for feature in layer.getFeatures():
                    point_geometry = feature.geometry()
                    new_feature = QgsFeature(fields)
                    new_feature.setGeometry(point_geometry)
                    new_feature['name'] = feature['name']
                    pr.addFeatures([new_feature])

                    # Add the new layer to the map
            QgsProject.instance().addMapLayer(SD_all_nodes_layer)

            self.auto_assign_msg = ""
            self.no_nodes = ""
            self.inlet_not_found = []
            self.outlet_not_found = []
            self.auto_assign_link_nodes("Conduits", "conduit_inlet", "conduit_outlet", SD_all_nodes_layer)
            self.auto_assign_link_nodes("Pumps", "pump_inlet", "pump_outlet", SD_all_nodes_layer)
            self.auto_assign_link_nodes("Orifices", "orifice_inlet", "orifice_outlet", SD_all_nodes_layer)
            self.auto_assign_link_nodes("Weirs", "weir_inlet", "weir_outlet", SD_all_nodes_layer)
            success = ""
            if self.no_nodes != "":
                msg = "The following nodes (inlets or outlets) could not" + "\n" + "be found for the indicated links:\n\n" + self.no_nodes
                result2 = ScrollMessageBox2(QMessageBox.Warning, "Missing inlets and outlets", msg)
                result2.exec_()
            else:
                success = " Success! all inlets and outlets nodes where assigned.\n\n"

            self.uc.show_info("Assignments to Inlet and Outlet nodes:\n\n" + success + self.auto_assign_msg)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.bar_error("ERROR 040524.0706: Auto-assign link nodes failed!")
            return False
        finally:
            # Remove temporary layer:
            QgsProject.instance().removeMapLayer(SD_all_nodes_layer)
            del SD_all_nodes_layer
        
    def SD_add_one_type4(self):
        self.add_single_rtable()

    def add_single_rtable(self, name=None):
        if not self.inletRT:
            return
        newRT = self.inletRT.add_rating_table(name)
        
        self.populate_type4_combo()
        newIdx = self.SD_type4_cbo.findText(newRT)
        if newIdx == -1:
            self.SD_type4_cbo.setCurrentIndex(self.SD_type4_cbo.count() - 1)
        else:
            self.SD_type4_cbo.setCurrentIndex(newIdx)
        self.SD_show_type4_table_and_plot()

    def add_type4(self, condition, name=None):
        newRT = name
        if condition == "RatingTable":
            if not self.inletRT:
                return
            newRT = self.inletRT.add_rating_table(name)
        self.populate_type4_combo()
        newIdx = self.SD_type4_cbo.findText(newRT)
        if newIdx == -1:
            self.SD_type4_cbo.setCurrentIndex(self.SD_type4_cbo.count() - 1)
        else:
            self.SD_type4_cbo.setCurrentIndex(newIdx)

    def add_type4_data(self, what):
        if what == "Add Rating Table":
            self.add_single_rtable()
            
        elif what == "Add Culvert Equation":
            name = None
            qry = "INSERT INTO swmmflo_culvert (name) VALUES (?);"
            rowid = self.gutils.execute(qry, (name,), get_rowid=True)
            name_qry = "UPDATE swmmflo_culvert SET name =  'CulvertEq' || cast(fid as text) WHERE fid = ?;"
            self.gutils.execute(name_qry, (rowid,))
            qry = "UPDATE swmmflo_culvert SET cdiameter = ?, typec = ?, typeen = ?, cubase = ?, multbarrels = ? WHERE fid = ?;"
            self.gutils.execute(qry, (0.0,0,0,0.0,1,rowid))
            
            newCulvert= "Culvert Eq. {}".format(rowid)
            self.populate_type4_combo()
            newIdx = self.SD_type4_cbo.findText(newCulvert)
            if newIdx == -1:
                self.SD_type4_cbo.setCurrentIndex(self.SD_type4_cbo.count() - 1)
            else:
                self.SD_type4_cbo.setCurrentIndex(newIdx) 
            self.SD_show_type4_table_and_plot()
      
        else:
            self.uc.show_warn("ERROR 041203.1542: wrong menu item!") 

    def SD_delete_type4(self):
        if not self.inletRT:
            return
        type4_name = self.SD_type4_cbo.currentText()

        # Delete Rating Table:
        qry = """SELECT grid_fid, name FROM swmmflort WHERE name = ?"""
        rts = self.gutils.execute(qry, (type4_name,))
        for rt in rts:
            grid_fid = rt[0]
            if grid_fid is None or grid_fid == "":
                q = (
                    'WARNING 100319.1024:\n\nRating table "'
                    + type4_name
                    + '" is not assigned to any grid element.\nDo you want to delete it?'
                )
                if not self.uc.question(q):
                    return
                idx = self.SD_type4_cbo.currentIndex()
                rt_fid = self.SD_type4_cbo.itemData(idx)
                self.inletRT.del_rating_table(rt_fid)
            else:
                if self.uc.question(
                    "WARNING 040319.0444:\n\nRating table '"
                    + type4_name
                    + "' is assigned to grid element "
                    + str(grid_fid)
                    + ".\nDo you want to delete it?.\n"
                ):
                    if self.uc.question(
                        "CONFIRM:  Delete rating table '"
                        + type4_name
                        + "' assigned to grid element "
                        + str(grid_fid)
                        + " ?"
                    ):
                        idx = self.SD_type4_cbo.currentIndex()
                        rt_fid = self.SD_type4_cbo.itemData(idx)
                        self.inletRT.del_rating_table(rt_fid)

        # Delete Culvert Equation:
        qry = """SELECT grid_fid, name FROM swmmflo_culvert WHERE name = ?"""
        culvs = self.gutils.execute(qry, (type4_name,))
        for cul in culvs:
            grid_fid = cul[0]
            if grid_fid is None or grid_fid == "":
                q = (
                    'WARNING 250622.0517:\nCulvert equation "'
                    + type4_name
                    + '" is not assigned to any grid element.\nDo you want to delete it?'
                )
                if not self.uc.question(q):
                    return
                idx = self.SD_type4_cbo.currentIndex()
                name = self.SD_type4_cbo.currentText()
                fid = self.SD_type4_cbo.itemData(idx)

                qry = "UPDATE user_swmm_nodes SET rt_fid = ?, rt_name = ? WHERE name = ?;"
                self.gutils.execute(qry, (None, None, name))
                qry = "DELETE FROM swmmflo_culvert WHERE name = ?;"
                self.gutils.execute(qry, (name,))            
                
            else:
                if self.uc.question(
                    "WARNING 250622.9519:\n\nCulvert Equation '"
                    + type4_name
                    + "' is assigned to grid element "
                    + str(grid_fid)
                    + ".\nDo you want to delete it?.\n"
                ):
                    if self.uc.question(
                        "CONFIRM:  Delete Culvert equation table '"
                        + type4_name
                        + "' assigned to grid element "
                        + str(grid_fid)
                        + " ?"
                    ):
                        idx = self.SD_type4_cbo.currentIndex()
                        name = self.SD_type4_cbo.currentText()
                        fid = self.SD_type4_cbo.itemData(idx)
                        qry = "UPDATE user_swmm_nodes SET rt_fid = ?, rt_name = ? WHERE name = ?;"
                        self.gutils.execute(qry, (None, None, name))
                        qry = "DELETE FROM swmmflo_culvert WHERE name = ?;"
                        self.gutils.execute(qry, (name,))

        self.populate_type4_and_data()

        if self.SD_type4_cbo.currentIndex() == -1:
            self.plot.clear()
            if self.plot.plot.legend is not None:
                plot_scene = self.plot.plot.legend.scene()
                if plot_scene is not None:
                    plot_scene.removeItem(self.plot.plot.legend)
            self.plot.plot.addLegend()

            self.tview.undoStack.clear()
            self.tview.setModel(self.inlet_data_model)
            self.inlet_data_model.clear()

    def SD_rename_type4(self):
        if not self.inletRT:
            return
        
        idx = self.SD_type4_cbo.currentIndex()
        rt_fid = self.SD_type4_cbo.itemData(idx)
        name = self.SD_type4_cbo.currentText()   
            
        # Check that the RT or Culvert eq. is not already assigned to an inlet:
        already_a_RT_or_Culvert = self.gutils.execute(
            "SELECT rt_name FROM user_swmm_nodes WHERE name = ?;", (name,)
            ).fetchone()  
        
        if already_a_RT_or_Culvert: 
            # Old name already assigned to inlet as Culvert eq.
            if already_a_RT_or_Culvert[0]:
                if not self.uc.question(
                    "WARNING 201223.0426:\n\nA rating table or Culvert eq. already assigned to inlet "
                    + name
                    + ".\n\nDo you want to rename it?.\n"
                ):
                    return            
    
        new_name, ok = QInputDialog.getText(None, "Change table name", "New name:")
        if not ok or not new_name:
            return
        if not self.SD_type4_cbo.findText(new_name) == -1:
            msg = "WARNING 060319.1735: Type 4 condition with name {} already exists. Please, choose another name or delete it.".format(
                new_name
            )
            self.uc.show_warn(msg)
            return
        
        inlet = self.gutils.execute(
            "SELECT name FROM user_swmm_nodes WHERE name = ?;", (new_name,)
            ).fetchone()        
        
        if not inlet:
            self.uc.show_warn("There is no inlet with name " + new_name)    
            return  
                    
            
        in_culvert = self.gutils.execute(
            "SELECT fid FROM swmmflo_culvert WHERE name = ?;", (name,)
            ).fetchone()  
        
        if in_culvert:         
            qry = "UPDATE swmmflo_culvert SET name=? WHERE name=?;"
            self.gutils.execute(qry,(new_name, name,),)
        else:
            self.inletRT.set_rating_table_data_name(rt_fid, new_name)

        self.gutils.execute("UPDATE user_swmm_nodes SET rt_name=? WHERE name=?;",(new_name, new_name,),)

        self.uc.show_warn("Type 4 condition assigned to inlet " + new_name)
          
        self.populate_type4_combo()
        idx = self.SD_type4_cbo.findText(new_name)
        self.SD_type4_cbo.setCurrentIndex(idx)
        self.SD_show_type4_table_and_plot()

    def save_SD_table_data(self):
        model = self.tview.model()
        if model == self.inlet_data_model:
            self.save_type4_tables_data()
        elif model == self.pumps_data_model:
            self.save_pump_curve_data()

    def save_type4_tables_data(self):
        idx = self.SD_type4_cbo.currentIndex()
        fid = self.SD_type4_cbo.itemData(idx)
        if fid is None:
            #             self.uc.bar_warn("No table defined!")
            return
        name = self.SD_type4_cbo.currentText()
        
        in_culvert = self.gutils.execute(
            "SELECT cdiameter, typec, typeen, cubase, multbarrels FROM swmmflo_culvert WHERE name = ?;", (name,)
            ).fetchone() 
        
        if in_culvert:         
            
            sql = "UPDATE swmmflo_culvert SET cdiameter=?, typec=?, typeen=?, cubase=?, multbarrels=? WHERE name = ?;"
            
            cdiameter = self.inlet_data_model.data(self.inlet_data_model.index(0.0, 0), Qt.DisplayRole)
            typec = self.inlet_data_model.data(self.inlet_data_model.index(0, 1), Qt.DisplayRole)
            typeen = self.inlet_data_model.data(self.inlet_data_model.index(0, 2), Qt.DisplayRole)
            cubase = self.inlet_data_model.data(self.inlet_data_model.index(0.0, 3), Qt.DisplayRole)
            multbarrels = self.inlet_data_model.data(self.inlet_data_model.index(0, 4), Qt.DisplayRole)
            
            self.gutils.execute(sql , (cdiameter ,typec ,typeen ,cubase ,multbarrels, name))
            
        else:
        
            self.update_rt_plot()
            rt_data = []
            for i in range(self.inlet_data_model.rowCount()):
                # save only rows with a number in the first column
                if is_number(m_fdata(self.inlet_data_model, i, 0)) and not isnan(m_fdata(self.inlet_data_model, i, 0)):
                    rt_data.append((fid, m_fdata(self.inlet_data_model, i, 0), m_fdata(self.inlet_data_model, i, 1)))
                else:
                    pass
            self.inletRT.set_rating_table_data(fid, name, rt_data)
            self.update_rt_plot()

    def create_rt_plot(self, name):
        self.plot.clear()
        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)
        self.plot.plot.addLegend()
        
        self.plot.plot.setTitle("Rating Table:   " + name)
        self.plot_item_name = "Rating Table:   " + name
        self.plot.add_item(self.plot_item_name, [self.d1, self.d2], col=QColor("#0018d4"))

     
    def update_rt_plot(self):
        if not self.plot_item_name:
            return
        self.d1, self.d2 = [[], []]
        for i in range(self.inlet_data_model.rowCount()):
            self.d1.append(m_fdata(self.inlet_data_model, i, 0))
            self.d2.append(m_fdata(self.inlet_data_model, i, 1))
        self.plot.update_item(self.plot_item_name, [self.d1, self.d2])


    def update_discharge_plot(self):
        # if not self.plot_item_name:
        #     return
        self.d1, self.d2, self.d3  = [[], [], []]
        for i in range(self.inlet_data_model.rowCount()):
            self.d1.append(m_fdata(self.inlet_data_model, i, 0))
            self.d2.append(m_fdata(self.inlet_data_model, i, 1))
            self.d3.append(m_fdata(self.inlet_data_model, i, 2))
        self.plot.update_item("Inflow", [self.d1, self.d2])
        self.plot.update_item("Flooding", [self.d1, self.d3])

    # PUMPS:

    def populate_pump_curves_and_data(self):
        self.populate_pump_curves_combo(True)
        self.show_pump_curve_table_and_plot()

    def populate_pump_curves_combo(self, block=True):
        self.pump_curve_cbo.blockSignals(block)
        self.pump_curve_cbo.clear()
        duplicates = ""
        for row in self.PumpCurv.get_pump_curves():
            if row:
                pc_fid, name = [x if x is not None else "" for x in row]
                if name != "":
                    if self.pump_curve_cbo.findText(name) == -1:
                        self.pump_curve_cbo.addItem(name, pc_fid)
                    else:
                        duplicates += name + "\n"
        self.pump_curve_cbo.blockSignals(not block)

    def current_cbo_pump_curve_index_changed(self, idx=0):
        if not self.pump_curve_cbo.count():
            return
        fid = self.pump_curve_cbo.currentData()
        if fid is None:
            fid = -1

        self.show_pump_curve_table_and_plot()

    def show_pump_curve_table_and_plot(self):
        self.SD_table.after_delete.disconnect()
        self.SD_table.after_delete.connect(self.save_SD_table_data)

        idx = self.pump_curve_cbo.currentIndex()
        curve_fid = self.pump_curve_cbo.itemData(idx)
        curve_name = self.pump_curve_cbo.currentText()
        if curve_fid is None:
            #             self.uc.bar_warn("No curve table defined!")
            return

        self.curve_data = self.PumpCurv.get_pump_curve_data(curve_name)
        if not self.curve_data:
            return
        self.create_pump_plot(curve_name)
        self.tview.undoStack.clear()
        self.tview.setModel(self.pumps_data_model)
        self.pumps_data_model.clear()
        currentPump = self.pump_curve_type_cbo.currentText()
        if currentPump == "Pump1":
            x = "Volume"
            y = "Flow"
        elif currentPump == "Pump2" or currentPump == "Pump4":
            x = "Depth"
            y = "Flow"
        elif currentPump == "Pump3":
            x = "Head"
            y = "Flow"
        else:
            x = "X"
            y = "Y"
        self.pumps_data_model.setHorizontalHeaderLabels([x, y])
        self.d1, self.d2 = [[], []]
        for row in self.curve_data:
            items = [StandardItem("{:.4f}".format(xx)) if xx is not None else StandardItem("") for xx in row]
            self.pumps_data_model.appendRow(items)
            self.d1.append(row[0] if not row[0] is None else float("NaN"))
            self.d2.append(row[1] if not row[1] is None else float("NaN"))
        rc = self.pumps_data_model.rowCount()
        if rc < 500:
            for row in range(rc, 500 + 1):
                items = [StandardItem(x) for x in ("",) * 2]
                self.pumps_data_model.appendRow(items)
        self.tview.horizontalHeader().setStretchLastSection(True)
        for col in range(2):
            self.tview.setColumnWidth(col, 100)
        for i in range(self.pumps_data_model.rowCount()):
            self.tview.setRowHeight(i, 20)
        self.update_pump_plot()

    def create_pump_plot(self, name):
        self.plot.clear()
        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)
        self.plot.plot.addLegend()

        self.plot_item_name = "Pump Curve:   " + name
        self.plot.plot.setTitle("Pump Curve:   " + name)
        self.plot.add_item(self.plot_item_name, [self.d1, self.d2], col=QColor("#0018d4"))

    def update_pump_plot(self):
        if not self.plot_item_name:
            return
        self.d1, self.d2 = [[], []]
        for i in range(self.pumps_data_model.rowCount()):
            self.d1.append(m_fdata(self.pumps_data_model, i, 0))
            self.d2.append(m_fdata(self.pumps_data_model, i, 1))
        self.plot.update_item(self.plot_item_name, [self.d1, self.d2])

    def add_one_pump_curve(self):
        self.add_single_pump_curve()

    def add_single_pump_curve(self, name=None):
        if not self.PumpCurv:
            return
        newPC = self.PumpCurv.add_pump_curve(name)
        self.populate_pump_curves_combo(True)
        newIdx = self.pump_curve_cbo.findText(newPC)
        if newIdx == -1:
            self.pump_curve_cbo.setCurrentIndex(self.pump_curve_cbo.count() - 1)
        else:
            self.pump_curve_cbo.setCurrentIndex(newIdx)
            self.show_pump_curve_table_and_plot()

    def delete_pump_curve(self):
        if not self.PumpCurv:
            return

        pc_name = self.pump_curve_cbo.currentText()
        if pc_name == "*":
            return
        self.PumpCurv.del_pump_curve(pc_name)
        self.populate_pump_curves_combo(False)

        if self.pump_curve_cbo.currentIndex() == -1:
            self.plot.clear()
            if self.plot.plot.legend is not None:
                plot_scene = self.plot.plot.legend.scene()
                if plot_scene is not None:
                    plot_scene.removeItem(self.plot.plot.legend)
            self.plot.plot.addLegend()

            self.tview.undoStack.clear()
            self.tview.setModel(self.pumps_data_model)
            self.pumps_data_model.clear()

        self.show_pump_curve_table_and_plot()

    def refresh_PC_PlotAndTable(self):
        # idx = self.pump_curve_cbo.currentIndex()
        self.show_pump_curve_type_and_description()

    def rename_pump_curve(self):
        if not self.PumpCurv:
            return
        new_name, ok = QInputDialog.getText(None, "Change curve name", "New name:")
        if not ok or not new_name:
            return
        if len(new_name.split()) > 1:
            self.uc.show_warn("Do not use spaces in the new name!")
            return
        if not self.pump_curve_cbo.findText(new_name) == -1:
            msg = "WARNING 200222.0512: Pump curve with name {} already exists in the database. Please, choose another name.".format(
                new_name
            )
            self.uc.show_warn(msg)
            return
        name = self.pump_curve_cbo.currentText()
        self.PumpCurv.set_pump_curve_name(name, new_name)

        self.populate_pump_curves_combo(True)
        idx = self.pump_curve_cbo.findText(new_name)
        self.pump_curve_cbo.setCurrentIndex(idx)
        self.show_pump_curve_table_and_plot()

    def save_pump_curve_data(self):
        idx = self.pump_curve_cbo.currentIndex()
        pc_fid = self.pump_curve_cbo.itemData(idx)
        data_name = self.pump_curve_cbo.currentText()
        self.update_pump_plot()
        pc_data = []
        for i in range(self.pumps_data_model.rowCount()):
            # save only rows with a number in the first column
            if is_number(m_fdata(self.pumps_data_model, i, 0)) and not isnan(m_fdata(self.pumps_data_model, i, 0)):
                pc_data.append((data_name, m_fdata(self.pumps_data_model, i, 0), m_fdata(self.pumps_data_model, i, 1)))
            else:
                pass

        self.PumpCurv.set_pump_curve_data(data_name, pc_data)

        curve = self.pump_curve_cbo.currentText()
        ptype = "Pump" + self.pump_curve_type_cbo.currentText()[4]
        desc = self.pump_curve_description_le.text()
        self.gutils.execute(
            "UPDATE swmm_pumps_curve_data SET pump_curve_type = ?, description = ? WHERE pump_curve_name = ?",
            (ptype, desc, curve),
        )

    def update_pump_curve_data(self):
        curve = self.pump_curve_cbo.currentText()
        ptype = "Pump" + self.pump_curve_type_cbo.currentText()[4]
        desc = self.pump_curve_description_le.text()
        self.gutils.execute(
            "UPDATE swmm_pumps_curve_data SET pump_curve_type = ?, description = ? WHERE pump_curve_name = ?",
            (ptype, desc, curve),
        )
        self.show_pump_curve_table_and_plot()

    def show_pump_curve_type_and_description(self):
        if self.pump_curve_cbo.count():
            curve = self.pump_curve_cbo.currentText()
            if curve:
                typ, desc = self.gutils.execute(
                    "SELECT pump_curve_type, description FROM swmm_pumps_curve_data WHERE pump_curve_name = ?", (curve,)
                ).fetchone()
                if not typ:
                    typ = "Pump1"
                ind = self.pump_curve_type_cbo.findText(typ)
                if ind != -1:
                    self.pump_curve_type_cbo.setCurrentIndex(ind)
                self.pump_curve_description_le.setText(desc)

    def SD_import_pump_curves(self):
        """
        Reads one or more pump curve table files.
        """
        self.uc.clear_bar_messages()

        if self.gutils.is_table_empty("user_model_boundary"):
            self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
            return
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        s = QSettings()
        last_dir = s.value("FLO-2D/lastSWMMDir", "")
        curve_files, __ = QFileDialog.getOpenFileNames(
            None,
            "Select pump curve files",
            directory=last_dir,
            filter="(*.TXT *.DAT);;(*.TXT);;(*.DAT);;(*.*)",
        )

        if not curve_files:
            return
        s.setValue("FLO-2D/lastSWMMDir", os.path.dirname(curve_files[0]))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            del_sql = "DELETE FROM swmm_pumps_curve_data WHERE pump_curve_name = ?"
            data_sql = "INSERT INTO swmm_pumps_curve_data (pump_curve_name, pump_curve_type, description, x_value, y_value) VALUES (?, ?, ?, ?, ?)"

            read = 0
            no_files = ""
            for cf in curve_files:
                filename = os.path.splitext(os.path.basename(cf))[0]

                # Delete pump curve if it already exists:
                self.gutils.execute(del_sql, (filename,))

                with open(cf, "r") as f1:
                    read += 1
                    for line in f1:
                        row = line.split()
                        if row:
                            if not len(row) == 2:
                                no_files += os.path.basename(cf) + "\n"
                                read -= 1
                                break
                            try:
                                r0 = float(row[0])
                                r1 = float(row[1])
                            except ValueError:
                                no_files += os.path.basename(cf) + "\n"
                                read -= 1
                                break
                            self.gutils.execute(data_sql, (filename, "Pump1", "imported", r0, r1))

            self.populate_pump_curves_and_data()
            QApplication.restoreOverrideCursor()
            msg = str(read) + "  pump curve files imported. "
            if no_files:
                msg = (
                    msg
                    + "\n\n ..but the following files could not be imported.\n(Ensure that files have rows with pair of values):\n\n"
                    + no_files
                )
            self.uc.show_info(msg)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 180322.0925: reading pump curve files failed!", e)
            return

    def center_node(self, node_type):
        """
        Function to center the node
        """
        if self.center_chbox.isChecked():
            if node_type == "Start":
                node_name = self.start_node_cbo.currentText()
            if node_type == "End":
                node_name = self.end_node_cbo.currentText()
            request = QgsFeatureRequest().setFilterExpression(f'"name" = \'{node_name}\'')
            feats = list(self.user_swmm_nodes_lyr.getFeatures(request))
            if feats:
                feat = feats[0]
                self.lyrs.show_feat_rubber(self.user_swmm_nodes_lyr.id(), request)
                x, y = feat.geometry().centroid().asPoint()
                center_canvas(self.iface, x, y)

    def clear_sd_rubber(self):
        """
        Function to clear the stormm drain rubber
        """
        self.lyrs.clear_rubber()

    def update_profile_cbos(self, node_type, name):
        """
        Function to update the start and end node for the profile plot
        """
        if node_type == "Start":
            index = self.start_node_cbo.findText(name)
            if index != -1:
                self.uc.log_info(str(index))
                self.start_node_cbo.setCurrentIndex(index)
        if node_type == "End":
            index = self.end_node_cbo.findText(name)
            if index != -1:
                self.end_node_cbo.setCurrentIndex(index)
