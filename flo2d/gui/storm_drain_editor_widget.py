# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import traceback
from collections import OrderedDict
from qgis.PyQt.QtCore import QSettings, Qt, QVariant, QTime
from qgis.PyQt.QtWidgets import (
    QApplication,
    QComboBox,
    QCheckBox,
    QDoubleSpinBox,
    QInputDialog,
    QFileDialog,
    qApp,
    QDialog,
    QMessageBox,
    QSpacerItem,
    QSizePolicy,
    QPushButton,
)
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    NULL,
    QgsProject,
    QgsVectorFileWriter,
    QgsFields,
    QgsField,
    QgsWkbTypes,
    QgsSymbolLayerRegistry,
    QgsMarkerSymbol,
    QgsLineSymbol,
    QgsSingleSymbolRenderer,
    QgsArrowSymbolLayer,
    QgsVectorLayer,
    QgsFillSymbol,
)
from .ui_utils import load_ui, try_disconnect, set_icon
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..flo2d_ie.swmm_io import StormDrainProject
from ..flo2d_tools.schema2user_tools import remove_features
from ..flo2d_tools.grid_tools import spatial_index
from ..flo2dobjects import InletRatingTable
from ..utils import is_number, m_fdata, is_true
from .table_editor_widget import StandardItemModel, StandardItem, CommandItemEdit
from math import isnan, modf, floor
from datetime import date, time, timedelta, datetime
from ..gui.dlg_outfalls import OutfallNodesDialog
from ..gui.dlg_inlets import InletNodesDialog
from ..gui.dlg_conduits import ConduitsDialog
from ..gui.dlg_stormdrain_shapefile import StormDrainShapefile
from _ast import Pass

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
        self.lyrs = lyrs
        self.tables = table
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.gutils = None
        self.grid_lyr = None
        self.user_swmm_nodes_lyr = None
        self.user_swmm_conduits_lyr = None
        self.swmm_inflows_lyr = None
        self.swmm_inflow_patterns_lyr = None
        self.swmm_inflows_time_series_lyr = None
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

        self.inletRT = None
        self.plot = plot
        self.plot_item_name = None
        self.table = table
        self.tview = table.tview
        self.inlet_data_model = StandardItemModel()
        self.inlet_series_data = None

        self.d1, self.d2 = [[], []]

        set_icon(self.create_point_btn, "mActionCapturePoint.svg")
        set_icon(self.save_changes_btn, "mActionSaveAllEdits.svg")
        set_icon(self.revert_changes_btn, "mActionUndo.svg")
        set_icon(self.delete_btn, "mActionDeleteSelected.svg")
        set_icon(self.schema_storm_drain_btn, "schematize_res.svg")

        set_icon(self.show_table_btn, "show_cont_table.svg")
        set_icon(self.add_one_rtable_btn, "add_bc_data.svg")
        set_icon(self.remove_rtable_btn, "mActionDeleteSelected.svg")
        set_icon(self.rename_rtable_btn, "change_name.svg")

        self.create_point_btn.clicked.connect(self.create_swmm_point)
        self.save_changes_btn.clicked.connect(self.save_swmm_edits)
        self.revert_changes_btn.clicked.connect(self.revert_swmm_lyr_edits)
        self.delete_btn.clicked.connect(self.delete_cur_swmm)
        self.schema_storm_drain_btn.clicked.connect(self.schematize_swmm)

        self.show_table_btn.clicked.connect(self.populate_rtables_data)
        self.remove_rtable_btn.clicked.connect(self.delete_rtables)
        self.add_one_rtable_btn.clicked.connect(self.add_one_rt)
        self.rename_rtable_btn.clicked.connect(self.rename_rtables)

        # self.change_name_btn.clicked.connect(self.rename_swmm)
        #
        # self.recalculate_btn.clicked.connect(self.recalculate_max_depth)
        # self.inlet_grp.toggled.connect(self.inlet_checked)
        # self.outlet_grp.toggled.connect(self.outlet_checked)
        #
        self.inlet_data_model.dataChanged.connect(self.save_rtables_data)
        self.table.before_paste.connect(self.block_saving)
        self.table.after_paste.connect(self.unblock_saving)
        self.inlet_data_model.itemDataChanged.connect(self.itemDataChangedSlot)

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

            self.inletRT = InletRatingTable(self.con, self.iface)
            self.grid_lyr = self.lyrs.data["grid"]["qlyr"]
            self.user_swmm_nodes_lyr = self.lyrs.data["user_swmm_nodes"]["qlyr"]
            self.user_swmm_conduits_lyr = self.lyrs.data["user_swmm_conduits"]["qlyr"]
            self.swmm_inflows_lyr = self.lyrs.data["swmm_inflows"]["qlyr"]
            self.swmm_inflow_patterns_lyr = self.lyrs.data["swmm_inflow_patterns"]["qlyr"]
            self.swmm_inflows_time_series_lyr = self.lyrs.data["swmm_inflow_time_series"]["qlyr"]
            self.control_lyr = self.lyrs.data["cont"]["qlyr"]
            self.schema_inlets = self.lyrs.data["swmmflo"]["qlyr"]
            self.schema_outlets = self.lyrs.data["swmmoutf"]["qlyr"]
            self.all_schema += [self.schema_inlets, self.schema_outlets]

            self.simulate_stormdrain_chbox.clicked.connect(self.simulate_stormdrain)
            self.import_shapefile_btn.clicked.connect(self.import_hydraulics)
            self.import_inp_btn.clicked.connect(self.import_storm_drain_INP_file)
            self.export_inp_btn.clicked.connect(self.export_storm_drain_INP_file)
            self.outfalls_btn.clicked.connect(self.show_outfalls)
            self.inlets_btn.clicked.connect(self.show_inlets)
            self.conduits_btn.clicked.connect(self.show_conduits)
            self.assign_conduits_nodes_btn.clicked.connect(self.auto_assign_conduits_nodes)
            self.control_lyr.editingStopped.connect(self.check_simulate_SD_1)
            self.import_rating_table_btn.clicked.connect(self.SD_import_rating_table)

            self.check_simulate_SD_1()

            self.populate_rtables()
            self.populate_rtables_data()
            self.SD_rating_table_cbo.activated.connect(self.populate_rtables_data)
            self.SD_rating_table_cbo.currentIndexChanged.connect(self.refresh_SD_PlotAndTable)

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
        if sd_type == "I" and intype != 4:
            if swmm_dict["flapgate"] == 1:
                inlet_type = self.cbo_intype.currentText()
                self.uc.bar_warn("Vertical inlet opening is not allowed for {}!".format(inlet_type))
                return
            swmm_dict["rt_fid"] = None
        elif sd_type == "I" and intype == 4:
            swmm_dict["rt_fid"] = self.SD_rating_table_cbo.itemData(self.SD_rating_table_cbo.currentIndex())
        else:
            pass

        col_gen = ("{}=?".format(c) for c in list(swmm_dict.keys()))
        col_names = ", ".join(col_gen)
        vals = list(swmm_dict.values()) + [fid]
        update_qry = """UPDATE user_swmm_nodes SET {0} WHERE fid = ?;""".format(col_names)
        self.gutils.execute(update_qry, vals)

    def schematize_swmm(self):
        self.uc.clear_bar_messages()

        if self.gutils.is_table_empty("user_model_boundary"):
            self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
            return
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        if self.schematize_inlets_and_outfalls():
            self.uc.show_info(
                "Schematizing of Storm Drains Inlets and Outfalls finished!\n\n"
                + "The 'Storm Drain Inlets', 'Storm Drain Outfalls' and/or Rating Tables layers were updated.\n\n"
                + "(NOTE: the 'Export GDS files' tool will write those layer attributes into the SWMMFLO.DAT and SWMMOUTF.DAT files)"
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
                if sd_type == "I" or sd_type == "J":
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

    def import_storm_drain_INP_file(self):
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

        if self.gutils.is_table_empty("user_model_boundary"):
            self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
            return
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        s = QSettings()
        #         last_dir = s.value('FLO-2D/lastGpkgDir', '')
        last_dir = s.value("FLO-2D/lastSWMMDir", "")
        swmm_file, __ = QFileDialog.getOpenFileName(
            None, "Select SWMM input file to import data", directory=last_dir, filter="(*.inp *.INP*)"
        )
        if not swmm_file:
            return
        s.setValue("FLO-2D/lastSWMMDir", os.path.dirname(swmm_file))

        QApplication.setOverrideCursor(Qt.WaitCursor)
        outside_nodes = ""
        outside_conduits = ""
        try:
            """
            Create an ordered dictionary "storm_drain.INP_groups".

            storm_drain.split_INP_groups_dictionary_by_tags():
            'The dictionary 'INP_groups' will have as key the name of the groups [xxxx] like 'OUTFALLS', 'JUNCTIONS', etc.
            Each element of the dictionary is a list of all the lines following the group name [xxxx] in the .INP file.

            """
            subcatchments = None
            storm_drain = StormDrainProject(self.iface, swmm_file)

            ret = storm_drain.split_INP_groups_dictionary_by_tags()
            if ret == 3:
                # No coordinates in INP file
                QApplication.restoreOverrideCursor()
                self.uc.show_warn(
                    "WARNING 060319.1729: SWMM input file\n\n " + swmm_file + "\n\n has no coordinates defined!"
                )
                return
            elif ret == 0:
                return

            # Build Nodes:
            if storm_drain.create_INP_nodes_dictionary_with_coordinates() == 0:
                QApplication.restoreOverrideCursor()
                self.uc.show_warn(
                    "WARNING 060319.1730: SWMM input file\n\n " + swmm_file + "\n\n has no coordinates defined!"
                )
                return
            else:
                QApplication.restoreOverrideCursor()
                if not self.gutils.is_table_empty("user_swmm_nodes"):
                    complete_or_create = self.import_INP_action()
                    if complete_or_create == "Cancel":
                        return
                else:
                    complete_or_create = "Create New"

                QApplication.setOverrideCursor(Qt.WaitCursor)
                subcatchments = storm_drain.add_SUBCATCHMENTS_to_INP_nodes_dictionary()
                storm_drain.add_OUTFALLS_to_INP_nodes_dictionary()
                storm_drain.add_JUNCTIONS_to_INP_nodes_dictionary()

                # Conduits:
                storm_drain.create_INP_conduits_dictionary_with_conduits()

                storm_drain.add_LOSSES_to_INP_conduits_dictionary()
                storm_drain.add_XSECTIONS_to_INP_conduits_dictionary()

                # External inflows into table swmm_inflows:
                storm_drain.create_INP_inflows_dictionary_with_inflows()
                try:
                    if complete_or_create == "Create New":
                        remove_features(self.swmm_inflows_lyr)
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
                        constituent = values["constituent"].upper() if "cosntituent" in values else "FLOW"
                        baseline = values["baseline"] if values["baseline"] is not None else 0.0
                        pattern_name = values["pattern_name"] if "pattern_name" in values else "?"
                        time_series_name = values["time_series_name"] if "time_series_name" in values else "?"
                        scale_factor = values["scale_factor"] if values["scale_factor"] is not None else 0.0

                        self.gutils.execute(
                            insert_inflows_sql,
                            (name, constituent, baseline, pattern_name, time_series_name, scale_factor),
                        )

                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error(
                        "ERROR 020219.0812: Reading storm drain inflows from SWMM input data failed!"
                        + "\n__________________________________________________",
                        e,
                    )

                # Inflows patterns into table swmm_inflow_patterns:
                storm_drain.create_INP_patterns_list_with_patterns()
                try:
                    description = ""
                    if complete_or_create == "Create New":
                        remove_features(self.swmm_inflow_patterns_lyr)
                    insert_patterns_sql = """INSERT INTO swmm_inflow_patterns
                                            (   pattern_name, 
                                                pattern_description, 
                                                hour, 
                                                multiplier
                                            ) 
                                            VALUES (?, ?, ?, ?);"""
                    i = 0
                    for pattern in storm_drain.INP_patterns:

                        if pattern[2][1] == "HOURLY":
                            name = pattern[1][1]
                            description = pattern[0][1]
                            for j in range(1, 7):
                                i += 1
                                hour = str(i)
                                multiplier = pattern[j + 2][1]
                                self.gutils.execute(insert_patterns_sql, (name, description, hour, multiplier))
                            if i == 24:
                                i = 0

                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error(
                        "ERROR 280219.1046: Reading storm drain paterns from SWMM input data failed!"
                        + "\n__________________________________________________",
                        e,
                    )

                # Inflow time series into table swmm_time_series:
                storm_drain.create_INP_time_series_list_with_time_series()
                try:
                    if complete_or_create == "Create New":
                        remove_features(self.swmm_inflows_time_series_lyr)
                    insert_times_sql = """INSERT INTO swmm_inflow_time_series 
                                            (   time_series_name, 
                                                time_series_description, 
                                                time_series_file
                                            ) 
                                            VALUES (?, ?, ?);"""
                    for time in storm_drain.INP_timeseries:
                        name = time[1][1]
                        description = time[0][1]
                        description2 = description.replace('"', "")
                        file = time[3][1]
                        file2 = file.replace('"', "")
                        self.gutils.execute(insert_times_sql, (name, description, file2.strip()))

                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error(
                        "ERROR 290220.1727: Reading storm drain time series from SWMM input data failed!"
                        + "\n__________________________________________________",
                        e,
                    )

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 080618.0448: reading SWMM input file failed!", e)
            return

        try:
            """
            Creates Storm Drain Nodes layer (Users layers).

            Creates "user_swmm_nodes" layer with attributes taken from
            the [COORDINATES], [JUNCTIONS], and [OUTFALLS] groups.

            """

            # Transfer data from "storm_drain.INP_dict" to "user_swmm_user" layer:

            replace_user_swmm_nodes_sql = """UPDATE user_swmm_nodes 
                             SET    junction_invert_elev = ?,
                                    max_depth = ?, 
                                    init_depth = ?,
                                    surcharge_depth = ?, 
                                    ponded_area = ?,
                                    outfall_type = ?, 
                                    outfall_invert_elev = ?, 
                                    tidal_curve = ?, 
                                    time_series = ?,
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
            for name, values in list(
                storm_drain.INP_nodes.items()
            ):  # "INP_nodes dictionary contains attributes names and
                # values taken from the .INP file.
                if subcatchments is not None:
                    if "subcatchment" in values:
                        sd_type = "I"
                    elif "out_type" in values:
                        sd_type = "O"
                    elif name[0] == "I":
                        continue  # Only consider inlets in [SUBCATCHMENTS]
                    else:
                        sd_type = "J"

                else:
                    if name[0] == "I":
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
                junction_invert_elev = float(values["junction_invert_elev"]) if "junction_invert_elev" in values else 0
                max_depth = float(values["max_depth"]) if "max_depth" in values else 0
                init_depth = float(values["init_depth"]) if "init_depth" in values else 0
                surcharge_depth = float(values["surcharge_depth"]) if "surcharge_depth" in values else 0
                ponded_area = float(values["ponded_area"]) if "ponded_area" in values else 0
                # Outfalls:
                if name[0] == "O":
                    XXXX = 0
                outfall_type = values["out_type"].upper() if "out_type" in values else "NORMAL"
                outfall_invert_elev = float(values["outfall_invert_elev"]) if "outfall_invert_elev" in values else 0
                tidal_curve = values["tidal_curve"] if "tidal_curve" in values else "..."
                time_series = values["time_series"] if "time_series" in values else "..."

                flapgate = values["tide_gate"] if "tide_gate" in values else "False"
                flapgate = "True" if is_true(flapgate) else "False"
                allow_discharge = values["swmm_allow_discharge"] if "swmm_allow_discharge" in values else "False"
                allow_discharge = "True" if is_true(allow_discharge) else "False"

                rim_elev = junction_invert_elev + max_depth if junction_invert_elev and max_depth else 0

                intype = int(values["intype"]) if "intype" in values else 1

                x = float(values["x"])
                y = float(values["y"])
                grid = self.gutils.grid_on_point(x, y)
                if grid is None:
                    outside_nodes += name + "\n"
                    continue

                elev = self.gutils.grid_value(grid, "elevation")
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
                    feat.setAttribute("flapgate", flapgate)
                    feat.setAttribute("swmm_allow_discharge", allow_discharge)
                    feat.setAttribute("invert_elev_inp", junction_invert_elev)
                    feat.setAttribute("max_depth_inp", max_depth)
                    feat.setAttribute("rim_elev_inp", rim_elev)
                    feat.setAttribute("rim_elev", rim_elev)
                    feat.setAttribute("ge_elev", elev)
                    feat.setAttribute("difference", difference)

                    feat.setAttribute("swmm_length", 0)
                    feat.setAttribute("swmm_width", 0)
                    feat.setAttribute("swmm_height", 0)
                    feat.setAttribute("swmm_coeff", 0)
                    feat.setAttribute("swmm_feature", 0)
                    feat.setAttribute("curbheight", 0)
                    feat.setAttribute("swmm_clogging_factor", 0)
                    feat.setAttribute("swmm_time_for_clogging", 0)
                    feat.setAttribute("water_depth", 0)
                    feat.setAttribute("rt_fid", 0)
                    feat.setAttribute("outf_flo", 0)

                    new_nodes.append(feat)

                else:
                    existing_node = self.gutils.execute(
                        "SELECT fid FROM user_swmm_nodes WHERE name = ?;", (name,)
                    ).fetchone()
                    if existing_node:
                        self.gutils.execute(
                            replace_user_swmm_nodes_sql,
                            (
                                junction_invert_elev,
                                max_depth,
                                init_depth,
                                surcharge_depth,
                                ponded_area,
                                outfall_type,
                                outfall_invert_elev,
                                tidal_curve,
                                time_series,
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

            if complete_or_create == "Create New" and len(new_nodes) != 0:
                remove_features(self.user_swmm_nodes_lyr)
                self.user_swmm_nodes_lyr.startEditing()
                self.user_swmm_nodes_lyr.addFeatures(new_nodes)
                self.user_swmm_nodes_lyr.commitChanges()
                self.user_swmm_nodes_lyr.updateExtents()
                self.user_swmm_nodes_lyr.triggerRepaint()
                self.user_swmm_nodes_lyr.removeSelection()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 060319.1610: Creating Storm Drain Nodes layer failed!\n\n"
                + "Please check your SWMM input data.\nAre the nodes coordinates inside the computational domain?",
                e,
            )
            return

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
            new_conduits = []
            updated_conduits = 0
            conduit_inlets_not_found = ""
            conduit_outlets_not_found = ""

            for name, values in list(storm_drain.INP_conduits.items()):

                go_go = True

                conduit_inlet = values["conduit_inlet"] if "conduit_inlet" in values else None
                conduit_outlet = values["conduit_outlet"] if "conduit_outlet" in values else None
                conduit_length = float(values["conduit_length"]) if "conduit_length" in values else 0
                conduit_manning = float(values["conduit_manning"]) if "conduit_manning" in values else 0
                conduit_inlet_offset = float(values["conduit_inlet_offset"]) if "conduit_inlet_offset" in values else 0
                conduit_outlet_offset = (
                    float(values["conduit_outlet_offset"]) if "conduit_outlet_offset" in values else 0
                )
                conduit_init_flow = float(values["conduit_init_flow"]) if "conduit_init_flow" in values else 0
                conduit_max_flow = float(values["conduit_max_flow"]) if "conduit_max_flow" in values else 0

                conduit_losses_inlet = float(values["losses_inlet"]) if "losses_inlet" in values else 0
                conduit_losses_outlet = float(values["losses_outlet"]) if "losses_outlet" in values else 0
                conduit_losses_average = float(values["losses_average"]) if "losses_average" in values else 0

                conduit_losses_flapgate = values["losses_flapgate"] if "losses_flapgate" in values else "False"
                conduit_losses_flapgate = "True" if is_true(conduit_losses_flapgate) else "False"

                conduit_xsections_shape = values["xsections_shape"] if "xsections_shape" in values else "CIRCULAR"
                conduit_xsections_barrels = float(values["xsections_barrels"]) if "xsections_barrels" in values else 0
                conduit_xsections_max_depth = (
                    float(values["xsections_max_depth"]) if "xsections_max_depth" in values else 0
                )
                conduit_xsections_geom2 = float(values["xsections_geom2"]) if "xsections_geom2" in values else 0
                conduit_xsections_geom3 = float(values["xsections_geom3"]) if "xsections_geom3" in values else 0
                conduit_xsections_geom4 = float(values["xsections_geom4"]) if "xsections_geom4" in values else 0

                feat = QgsFeature()
                feat.setFields(fields)

                if not conduit_inlet in storm_drain.INP_nodes:
                    conduit_inlets_not_found += conduit_inlet + " \t(for conduit " + name + ")\n"
                    go_go = False
                if not conduit_outlet in storm_drain.INP_nodes:
                    conduit_outlets_not_found += conduit_outlet + " \t(for conduit " + name + ")\n"
                    go_go = False

                if not go_go:
                    continue

                x1 = float(storm_drain.INP_nodes[conduit_inlet]["x"])
                y1 = float(storm_drain.INP_nodes[conduit_inlet]["y"])
                x2 = float(storm_drain.INP_nodes[conduit_outlet]["x"])
                y2 = float(storm_drain.INP_nodes[conduit_outlet]["y"])

                grid = self.gutils.grid_on_point(x1, y1)
                if grid is None:
                    outside_conduits += name + "\n"
                    continue

                grid = self.gutils.grid_on_point(x2, y2)
                if grid is None:
                    outside_conduits += name + "\n"
                    continue

                # NOTE: for now ALWAYS read all inlets   !!!:
                #                 if complete_or_create == "Create New":

                geom = QgsGeometry.fromPolylineXY([QgsPointXY(x1, y1), QgsPointXY(x2, y2)])
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
                updated_conduits += 1

            #                 else:
            #                     existing_conduit = self.gutils.execute("SELECT fid FROM user_swmm_conduits WHERE conduit_name = ?;", (name,)).fetchone()
            #                     if existing_conduit:
            #                         self.gutils.execute(replace_user_swmm_conduits_sql, (conduit_inlet, conduit_outlet, conduit_length, conduit_manning,
            #                                                                              conduit_inlet_offset, conduit_outlet_offset, conduit_init_flow, conduit_max_flow,
            #                                                                              conduit_losses_inlet, conduit_losses_outlet, conduit_losses_average, conduit_losses_flapgate,
            #                                                                              conduit_xsections_shape, conduit_xsections_barrels, conduit_xsections_max_depth,
            #                                                                              conduit_xsections_geom2, conduit_xsections_geom3, conduit_xsections_geom4,
            #                                                                              name))
            #                         updated_conduits += 1

            #             if complete_or_create == "Create New" and len(new_conduits) != 0:
            if len(new_conduits) != 0:
                remove_features(self.user_swmm_conduits_lyr)
                self.user_swmm_conduits_lyr.startEditing()
                self.user_swmm_conduits_lyr.addFeatures(new_conduits)
                self.user_swmm_conduits_lyr.commitChanges()
                self.user_swmm_conduits_lyr.updateExtents()
                self.user_swmm_conduits_lyr.triggerRepaint()
                self.user_swmm_conduits_lyr.removeSelection()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 050618.1804: creation of Storm Drain Conduits layer failed!", e)

        QApplication.restoreOverrideCursor()

        if complete_or_create == "Create New" and len(new_nodes) == 0 and len(new_conduits) == 0:
            self.uc.show_info(
                "WARNING 261220.1631:\n\nFile "
                + swmm_file
                + "\n\ndoes not have nodes or conduits inside the domain of this project."
            )
        else:
            if conduit_inlets_not_found != "":
                self.uc.show_warn(
                    "WARNING 060319.1732: The following conduit inlets were not found!\n\n" + conduit_inlets_not_found
                )

            if conduit_outlets_not_found != "":
                self.uc.show_warn(
                    "WARNING 060319.1733: The following conduit outlets were not found!\n\n" + conduit_outlets_not_found
                )

            if complete_or_create == "Create New":
                self.uc.show_info(
                    "Importing Storm Drain data finished!\n\n"
                    + "* "
                    + str(len(new_nodes))
                    + " nodes (inlets, junctions, and outfalls) were created in the 'Storm Drain Nodes' layer ('User Layers' group), and\n\n"
                    + "* "
                    + str(len(new_conduits))
                    + " conduits in the 'Storm Drain Conduits' layer ('User Layers' group). \n\n"
                    "Click the 'Inlets/Junctions', 'Outfalls', and 'Conduits' buttons in the Storm Drain Editor widget to see or edit their attributes.\n\n"
                    "NOTE: the 'Schematize Storm Drain Components' button  in the Storm Drain Editor widget will update the 'Storm Drain' layer group, required to "
                    "later export the .DAT files used by the FLO-2D model."
                )
            else:
                self.uc.show_info(
                    "Storm Drain data was updated from file\n"
                    + swmm_file
                    + "\n\n"
                    + "* "
                    + str(updated_nodes)
                    + " Nodes (inlets, junctions, and outfalls) in the 'Storm Drain Nodes' layer ('User Layers' group) were updated, and\n\n"
                    + "* "
                    + str(updated_conduits)
                    + " Conduits in the 'Storm Drain Conduits' layer ('User Layers' group) were updated. \n\n"
                    "Click the 'Inlets/Junctions', 'Outfalls', and 'Conduits' buttons in the Storm Drain Editor widget to see or edit their attributes.\n\n"
                    "NOTE: the 'Schematize Storm Drain Components' button  in the Storm Drain Editor widget will update the 'Storm Drain' layer group, required to "
                    "later export the .DAT files used by the FLO-2D model."
                )
            if outside_nodes != "":
                msgBox = QMessageBox()
                msgBox.setIcon(QMessageBox.Warning)
                msgBox.setWindowTitle("Storm Drain points outside domain")
                msgBox.setText("WARNING 221220.0336:")
                msgBox.setInformativeText("The following Storm Drain points are outside the domain:")
                msgBox.setDetailedText(outside_nodes)
                msgBox.setStandardButtons(QMessageBox.Ok)
                msgBox.exec_()

            if outside_conduits != "":
                msgBox = QMessageBox()
                msgBox.setIcon(QMessageBox.Warning)
                msgBox.setWindowTitle("Storm Drain conduits outside domain")
                msgBox.setText("WARNING 221220.0337:")
                msgBox.setInformativeText("The following Conduits are outside the domain:")
                msgBox.setDetailedText(outside_conduits)
                msgBox.setStandardButtons(QMessageBox.Ok)
                msgBox.exec_()

    def import_INP_action(self):
        msg = QMessageBox()
        msg.setWindowTitle("Complete or replace Storm Drain User Data")
        msg.setText(
            "There is already Storm Drain data in the Users Layers.\n\nWould you like to keep it and complete it with data taken from the .INP file?\n\n"
            + "or you prefer to erase it and create new storm drains from the .INP file?\n"
        )
        msg.addButton(QPushButton("Keep existing and Complete "), QMessageBox.YesRole)
        msg.addButton(QPushButton("Create new storm drains"), QMessageBox.NoRole)
        msg.addButton(QPushButton("Cancel"), QMessageBox.RejectRole)
        msg.setDefaultButton(QMessageBox().Cancel)
        msg.setIcon(QMessageBox.Question)
        ret = msg.exec_()
        if ret == 0:
            #             self.uc.show_warn("Keep and Complete")
            return "Keep and Complete"
        elif ret == 1:
            #             self.uc.show_warn("Create New")
            return "Create New"
        else:
            #             self.uc.show_warn("Cancel")
            return "Cancel"

    def export_storm_drain_INP_file(self):
        """
        Writes <name>.INP file
        (<name> exists or is given by user in initial file dialog).

        The following groups are are always written with the data of the current project:
            [JUNCTIONS] [OUTFALLS] [CONDUITS] [XSECTIONS] [LOSSES] [COORDINATES]
        All other groups are written from data of .INP file if they exists.
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
            last_dir = s.value("FLO-2D/lastSWMMDir", "")
            swmm_file, __ = QFileDialog.getSaveFileName(
                None, "Select SWMM input file to update", directory=last_dir, filter="(*.inp *.INP*)"
            )

            if not swmm_file:
                return

            s.setValue("FLO-2D/lastSWMMDir", os.path.dirname(swmm_file))
            last_dir = s.value("FLO-2D/lastSWMMDir", "")

            if os.path.isfile(swmm_file):
                # File exist, therefore import groups:
                INP_groups = self.split_INP_into_groups_dictionary_by_tags_to_export(swmm_file)
            else:
                # File doen't exists.Create groups.
                pass

            # Show dialog with [TITLE], [OPTIONS], and [REPORT], with values taken from existing .INP file (if selected),
            # and project units, start date, report start.
            dlg_INP_groups = INP_GroupsDialog(self.con, self.iface)
            ok = dlg_INP_groups.exec_()
            if ok:

                with open(swmm_file, "w") as swmm_inp_file:
                    no_in_out_conduits = 0
                    # TITLE ##################################################
                    items = self.select_this_INP_group(INP_groups, "title")
                    swmm_inp_file.write("[TITLE]")
                    #                     if items is not None:
                    #                         for line in items[1:]:
                    #                             swmm_inp_file.write("\n" + line)
                    #                     else:
                    swmm_inp_file.write("\n" + dlg_INP_groups.titleTextEdit.toPlainText() + "\n")

                    # OPTIONS ##################################################
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
                    swmm_inp_file.write(
                        "\nSTART_DATE           " + dlg_INP_groups.start_date.date().toString("MM/dd/yyyy")
                    )
                    swmm_inp_file.write(
                        "\nSTART_TIME           " + dlg_INP_groups.start_time.time().toString("hh:mm:ss")
                    )
                    swmm_inp_file.write(
                        "\nREPORT_START_DATE    " + dlg_INP_groups.report_start_date.date().toString("MM/dd/yyyy")
                    )
                    swmm_inp_file.write(
                        "\nREPORT_START_TIME    " + dlg_INP_groups.report_start_time.time().toString("hh:mm:ss")
                    )
                    swmm_inp_file.write(
                        "\nEND_DATE             " + dlg_INP_groups.end_date.date().toString("MM/dd/yyyy")
                    )
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

                    # JUNCTIONS ##################################################
                    try:
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[JUNCTIONS]")
                        swmm_inp_file.write("\n;;               Invert     Max.       Init.      Surcharge  Ponded")
                        swmm_inp_file.write("\n;;Name           Elev.      Depth      Depth      Depth      Area")
                        swmm_inp_file.write("\n;;-------------- ---------- ---------- ---------- ---------- ----------")

                        SD_junctions_sql = """SELECT name, junction_invert_elev, max_depth, init_depth, surcharge_depth, ponded_area
                                          FROM user_swmm_nodes WHERE sd_type = "I" or sd_type = "J" ORDER BY fid;"""
                        line = "\n{0:16} {1:<10.2f} {2:<10.2f} {3:<10.2f} {4:<10.2f} {5:<10.2f}"
                        junctions_rows = self.gutils.execute(SD_junctions_sql).fetchall()
                        if not junctions_rows:
                            pass
                        else:
                            for row in junctions_rows:
                                row = (
                                    row[0],
                                    0 if row[1] is None else row[1],
                                    0 if row[2] is None else row[2],
                                    0 if row[3] is None else row[3],
                                    0 if row[4] is None else row[4],
                                    0 if row[5] is None else row[5],
                                )
                                swmm_inp_file.write(line.format(*row))
                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 070618.0851: error while exporting [JUNCTIONS] to .INP file!", e)
                        return

                    # OUTFALLS ###################################################
                    try:
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[OUTFALLS]")
                        swmm_inp_file.write("\n;;               Invert     Outfall      Stage/Table       Tide")
                        swmm_inp_file.write("\n;;Name           Elev.      Type         Time Series       Gate")
                        swmm_inp_file.write("\n;;-------------- ---------- ------------ ----------------  ----")

                        SD_outfalls_sql = """SELECT name, outfall_invert_elev, outfall_type, time_series, tidal_curve, flapgate 
                                          FROM user_swmm_nodes  WHERE sd_type = "O"  ORDER BY fid;"""

                        line = "\n{0:16} {1:<10.2f} {2:<11} {3:<18} {4:<16}"
                        outfalls_rows = self.gutils.execute(SD_outfalls_sql).fetchall()
                        if not outfalls_rows:
                            pass
                        else:
                            for row in outfalls_rows:
                                lrow = list(row)
                                lrow = [
                                    lrow[0],
                                    0 if lrow[1] is None else lrow[1],
                                    0 if lrow[2] is None else lrow[2],
                                    "   " if lrow[3] is None else lrow[3],
                                    0 if lrow[4] is None else lrow[4],
                                    0 if lrow[5] is None else lrow[5],
                                ]
                                lrow[3] = "   " if lrow[3] == "..." else lrow[3]
                                lrow[4] = "   " if lrow[4] == "..." else lrow[4]
                                lrow[2] = lrow[2].upper()
                                if not lrow[2] in ("FIXED", "FREE", "NORMAL", "TIDAL CURVE", "TIME SERIES"):
                                    lrow[2] = "NORMAL"
                                if lrow[2] == "TIME SERIES":
                                    lrow[3] = lrow[4]
                                lrow[5] = "YES" if lrow[5] in ("True", "true", "Yes", "yes", "1") else "NO"
                                swmm_inp_file.write(line.format(lrow[0], lrow[1], lrow[2], lrow[3], lrow[5]))
                    #                                 row = (row[0], 0 if row[1] is None else row[1], 0 if row[2] is None else row[2],
                    #                                        "   "  if row[3] is None else row[3] , 0 if row[4] is None else row[4])

                    #                                 swmm_inp_file.write(line.format(*row))
                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 070618.1619: error while exporting [OUTFALLS] to .INP file!", e)
                        return

                    # CONDUITS ###################################################

                    try:
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

                        SD_conduits_sql = """SELECT conduit_name, conduit_inlet, conduit_outlet, conduit_length, conduit_manning, conduit_inlet_offset, 
                                                conduit_outlet_offset, conduit_init_flow, conduit_max_flow 
                                          FROM user_swmm_conduits ORDER BY fid;"""

                        line = (
                            "\n{0:16} {1:<16} {2:<16} {3:<10.2f} {4:<10.3f} {5:<10.2f} {6:<10.2f} {7:<10.2f} {8:<10.2f}"
                        )
                        conduits_rows = self.gutils.execute(SD_conduits_sql).fetchall()
                        if not conduits_rows:
                            pass
                        else:
                            for row in conduits_rows:
                                row = (
                                    row[0],
                                    "?" if row[1] is None else row[1],
                                    "?" if row[2] is None else row[2],
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

                    # XSECTIONS ###################################################
                    try:
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[XSECTIONS]")
                        swmm_inp_file.write(
                            "\n;;Link           Shape        Geom1      Geom2      Geom3      Geom4      Barrels"
                        )
                        swmm_inp_file.write(
                            "\n;;-------------- ------------ ---------- ---------- ---------- ---------- ----------"
                        )

                        SD_xsections_sql = """SELECT conduit_name, xsections_shape, xsections_max_depth, xsections_geom2, xsections_geom3, xsections_geom4, xsections_barrels
                                          FROM user_swmm_conduits ORDER BY fid;"""

                        line = "\n{0:16} {1:<13} {2:<10.2f} {3:<10.2f} {4:<10.3f} {5:<10.2f} {6:<10}"
                        xsections_rows = self.gutils.execute(SD_xsections_sql).fetchall()
                        if not xsections_rows:
                            pass
                        else:
                            no_xs = 0

                            for row in xsections_rows:
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

                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 070618.1621: error while exporting [XSECTIONS] to .INP file!", e)
                        return

                    # LOSSES ###################################################
                    try:
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[LOSSES]")
                        swmm_inp_file.write("\n;;Link           Inlet      Outlet     Average    Flap Gate")
                        swmm_inp_file.write("\n;;-------------- ---------- ---------- ---------- ----------")

                        SD_losses_sql = """SELECT conduit_name, losses_inlet, losses_outlet, losses_average, losses_flapgate
                                          FROM user_swmm_conduits ORDER BY fid;"""

                        line = "\n{0:16} {1:<10} {2:<10} {3:<10.2f} {4:<10}"
                        losses_rows = self.gutils.execute(SD_losses_sql).fetchall()
                        if not losses_rows:
                            pass
                        else:
                            for row in losses_rows:
                                lrow = list(row)
                                lrow[4] = "YES" if lrow[4] in ("True", "true", "Yes", "yes", "1") else "NO"
                                swmm_inp_file.write(line.format(*lrow))
                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 070618.1622: error while exporting [LOSSES] to .INP file!", e)
                        return

                    # REPORT ##################################################
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

                    # COORDINATES ###################################################
                    try:
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[COORDINATES]")
                        swmm_inp_file.write("\n;;Node           X-Coord            Y-Coord ")
                        swmm_inp_file.write("\n;;-------------- ------------------ ------------------")

                        SD_coordinates_sql = """SELECT name, ST_AsText(ST_Centroid(GeomFromGPB(geom)))
                                          FROM user_swmm_nodes ORDER BY fid;"""

                        line = "\n{0:16} {1:<18} {2:<18}"
                        coordinates_rows = self.gutils.execute(SD_coordinates_sql).fetchall()
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

                    # INFLOWS ###################################################
                    try:
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[INFLOWS]")
                        swmm_inp_file.write(
                            "\n;;                                                 Param    Units    Scale    Baseline Baseline"
                        )
                        swmm_inp_file.write(
                            "\n;;Node           Parameter        Time Series      Type     Factor   Factor   Value    Pattern "
                        )
                        swmm_inp_file.write(
                            "\n;;-------------- ---------------- ---------------- -------- -------- -------- -------- --------"
                        )

                        SD_inflows_sql = """SELECT node_name, constituent, baseline, pattern_name, time_series_name, scale_factor
                                          FROM swmm_inflows ORDER BY fid;"""

                        line = "\n{0:16} {1:<16} {2:<16} {3:<7}  {4:<8} {5:<8.2f} {6:<8.2f} {7:<10}"
                        inflows_rows = self.gutils.execute(SD_inflows_sql).fetchall()
                        if not inflows_rows:
                            pass
                        else:
                            for row in inflows_rows:
                                lrow = [
                                    row[0],
                                    row[1],
                                    row[4] if row[3] is not None else "?",
                                    row[1],
                                    "1.0",
                                    row[5],
                                    row[2],
                                    row[3] if row[3] is not None else "?",
                                ]
                                swmm_inp_file.write(line.format(*lrow))
                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 230220.0751.1622: error while exporting [INFLOWS] to .INP file!", e)
                        return

                    # TIMESERIES ###################################################
                    try:
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[TIMESERIES]")
                        swmm_inp_file.write("\n;;Name           Date       Time       Value     ")
                        swmm_inp_file.write("\n;;-------------- ---------- ---------- ----------")

                        SD_inflow_time_series_sql = """SELECT time_series_name, time_series_description, time_series_file
                                          FROM swmm_inflow_time_series ORDER BY fid;"""

                        line1 = "\n;{0:16}"
                        line2 = "\n{0:16} {1:<10} {2:<50}"
                        time_series_rows = self.gutils.execute(SD_inflow_time_series_sql).fetchall()
                        if not time_series_rows:
                            pass
                        else:
                            for row in time_series_rows:
                                lrow1 = [row[1]]
                                swmm_inp_file.write(line1.format(*lrow1))
                                fileName = os.path.basename(row[2].strip())
                                file = '"' + last_dir + "/" + fileName + '"'
                                lrow2 = [row[0], "FILE", file]
                                swmm_inp_file.write(line2.format(*lrow2))
                                swmm_inp_file.write("\n")
                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 230220.1005: error while exporting [TIMESERIES] to .INP file!", e)
                        return

                    # PATTERNS ###################################################
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

                    # CONTROLS ##################################################
                    items = self.select_this_INP_group(INP_groups, "controls")
                    swmm_inp_file.write("\n\n[CONTROLS]")
                    if items is not None:
                        for line in items[1:]:
                            if line != "":
                                swmm_inp_file.write("\n" + line)
                    else:
                        swmm_inp_file.write("\n")

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
                        "STORAGE",
                        "PUMPS",
                        "ORIFICES",
                        "WEIRS",
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
                        "CURVES",
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

                self.uc.show_info(
                    swmm_file
                    + "\n\nfile saved with:\n\n"
                    + str(len(junctions_rows))
                    + "\t[JUNCTIONS]\n"
                    + str(len(outfalls_rows))
                    + "\t[OUTFALLS]\n"
                    + str(len(conduits_rows))
                    + "\t[CONDUITS]\n"
                    + str(len(xsections_rows))
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
                if no_in_out_conduits != 0:
                    self.uc.show_warn(
                        "WARNING 060319.1734: "
                        + str(no_in_out_conduits)
                        + " conduits have no inlet and/or outlet! The value '?' was assigned to them.\n"
                        + "Please review them because it will cause errors during their processing.\n"
                    )
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
            except Exception as e:
                self.uc.bar_warn("Could not save outfalls! Please check if they are correct.")
                return

    def show_inlets(self):
        """
        Shows inlets dialog.

        """
        # See if table is empy:
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

        dlg_inlets = InletNodesDialog(self.iface, self.plot, self.table, self.lyrs)
        dlg_inlets.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        dlg_inlets.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        save = dlg_inlets.exec_()
        if save:
            self.uc.show_info(
                "Inlets saved to 'Storm Drain-Inlets' User Layer!\n\n"
                + "Schematize it from the 'Storm Drain Editor' widget before saving into SWMMOUTF.DAT"
            )
            self.populate_rtables()

        elif not save:
            pass
        else:
            self.uc.bar_warn("Could not save Inlets! Please check if they are correct.")

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
            except Exception as e:
                self.uc.bar_warn("Could not save conduits! Please check if they are correct.")
                return

    def auto_assign_conduits_nodes(self):
        """Auto assign Conduits (user layer) Inlet and Outlet names based on closest (5ft) nodes to their endpoints."""
        proceed = self.uc.question("Do you want to overwrite Conduits Inlet and Outlet nodes names?")
        if not proceed:
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            conduit_fields = self.user_swmm_conduits_lyr.fields()
            conduit_inlet_fld_idx = conduit_fields.lookupField("conduit_inlet")
            conduit_outlet_fld_idx = conduit_fields.lookupField("conduit_outlet")
            nodes_features, nodes_index = spatial_index(self.user_swmm_nodes_lyr)
            buffer_distance, segments = 5.0, 5
            conduit_nodes = {}
            for feat in self.user_swmm_conduits_lyr.getFeatures():
                fid = feat.id()
                geom = feat.geometry()
                geom_poly = geom.asPolyline()
                start_pnt, end_pnt = geom_poly[0], geom_poly[-1]
                start_geom = QgsGeometry.fromPointXY(start_pnt)
                end_geom = QgsGeometry.fromPointXY(end_pnt)
                start_buffer = start_geom.buffer(buffer_distance, segments)
                end_buffer = end_geom.buffer(buffer_distance, segments)
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
                else:
                    inlet_name = None
                if closest_outlet_feat is not None:
                    outlet_name = closest_outlet_feat["name"]
                else:
                    outlet_name = None
                conduit_nodes[fid] = inlet_name, outlet_name

            self.user_swmm_conduits_lyr.startEditing()
            for fid, (inlet_name, outlet_name) in conduit_nodes.items():
                self.user_swmm_conduits_lyr.changeAttributeValue(fid, conduit_inlet_fld_idx, inlet_name)
                self.user_swmm_conduits_lyr.changeAttributeValue(fid, conduit_outlet_fld_idx, outlet_name)
            self.user_swmm_conduits_lyr.commitChanges()
            self.user_swmm_conduits_lyr.triggerRepaint()
            QApplication.restoreOverrideCursor()
            self.uc.show_info(
                "Inlet and Outlet node names successfully assigned for the {len(conduit_nodes)} Conduits!"
            )
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR: Couldn't assign Conduits nodes!", e)

    def SD_import_rating_table(self):
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
            "Select rating table files input file to import data",
            directory=last_dir,
            filter="(*.TXT *.DAT);;(*.TXT);;(*.DAT);;(*.*)",
        )

        if not rating_files:
            return
        s.setValue("FLO-2D/lastSWMMDir", os.path.dirname(rating_files[0]))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            errors0 = []
            errors1 = []
            noInlets = []
            lst_no_type4 = []
            str_no_type4 = ""
            warnings = []
            accepted_files = []
            goodRT = 0
            for file in rating_files:
                err0, err1, err2, t4 = self.check_RT_file(file)
                if err0 == "" and err1 == "" and err2 == "":
                    goodRT += 1
                    file_name, file_ext = os.path.splitext(os.path.basename(file))

                    self.add_rtable(
                        file_name
                    )  # Rating table 'file_name' is deleted from 'swmmflort' and its data from 'swmmflort_data' if they exist.
                    # New rating table 'file_name' added to 'swmmflort' (no data included in 'swmmflort_data'! That will be done next:).

                    # Read depth and discharge from rating table file and add them to 'swmmflort_data':
                    swmm_fid = self.gutils.execute("SELECT fid FROM swmmflort WHERE name = ?", (file_name,)).fetchone()[
                        0
                    ]
                    data_sql = "INSERT INTO swmmflort_data (swmm_rt_fid, depth, q) VALUES (?, ?, ?)"
                    with open(file, "r") as f1:
                        for line in f1:
                            row = line.split()
                            if row:
                                self.gutils.execute(data_sql, (swmm_fid, row[0], row[1]))

                    # Assign grid number to the just added rating table to 'swmmflort' table:
                    grid_sql = "SELECT grid FROM user_swmm_nodes WHERE name = ?;"
                    set_grid_sql = "UPDATE swmmflort SET grid_fid = ? WHERE name = ?;"
                    grid = self.gutils.execute(grid_sql, (file_name,)).fetchone()[0]
                    self.gutils.execute(set_grid_sql, (grid, file_name))

                    # Assign rating table name to user_swmm_nodes:
                    assign_rt_name_sql = "UPDATE user_swmm_nodes SET rt_name = ? WHERE name =?;"

                    #                     raise Exception("NOTE3: update rt_fid")

                    self.gutils.execute(assign_rt_name_sql, (file_name, file_name))

                    accepted_files.append(
                        file_name + file_ext + " rating table was assigned to inlet with identical name"
                    )
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

            txt2 = ""
            answer = True
            if lst_no_type4:
                QApplication.restoreOverrideCursor()
                answer = self.uc.question(
                    str(goodRT)
                    + " imported rating tables were assigned to inlets with identical name.\n\n"
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
                        + "The following inlets were assigned rating tables but are not of type 4 (stage-discharge):\n\n"
                        + str_no_type4
                    )

            len_errors = len(errors0) + len(errors1)

            if errors0:
                errors0.append("\n")
            if errors1:
                errors1.append("\n")
            #             if noInlets:
            #                 noInlets.append("\n")

            warnings = errors0 + errors1

            if len_errors + len(noInlets) + goodRT > 0:
                with open(last_dir + "\Rating Tables Warnings.CHK", "w") as error_file:
                    for w in warnings:
                        error_file.write(w + "\n")

                    for accepted in accepted_files:
                        error_file.write(accepted + "\n")

                    if str_no_type4 != "":
                        if answer:
                            error_file.write(
                                "\nThe following inlets were assigned rating tables and its Drain type changed to 4 (stage-discharge):"
                                + str_no_type4
                                + "\n"
                            )
                        else:
                            error_file.write(
                                "\nThe following inlets were assigned rating tables but are not of type 4 (stage-discharge):"
                                + str_no_type4
                                + "\n"
                            )

                    if noInlets:
                        error_file.write("\n")
                        for no in noInlets:
                            error_file.write(no + "\n")

                QApplication.restoreOverrideCursor()

                txt1 = " could not be read (maybe wrong format).\n\n"

                self.uc.show_info(
                    "INFO 181120.1629:\n\n"
                    + "* "
                    + str(len(rating_files))
                    + " files selected"
                    + (", of which " + str(len_errors) + txt1 if len_errors > 0 else ".\n\n")
                    + (
                        "* " + str(len(noInlets)) + " rating tables were not read (no inlets with identical name).\n\n"
                        if len(noInlets) > 0
                        else ""
                    )
                    + "* "
                    + str(goodRT)
                    + " rating tables were assigned to inlets with identical name.\n\n"
                    + txt2
                    + "See details in file\n\n"
                    + os.path.dirname(rating_files[0])
                    + "/Rating Tables Warnings.CHK"
                )

        #                 if len(noInlets)> 0:
        #                     QApplication.restoreOverrideCursor()
        #                     self.uc.show_info( (str(len(noInlets)) if len(noInlets) > 0 else "No" ) + "rating tables were not assigned to inlets with identical name.")

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 131120.1846: reading rating tables failed!", e)
            return

    def import_hydraulics(self):
        """
        Shows import shapefile dialog.

        """
        # # See if there are inlets:
        # if self.gutils.is_table_empty('user_swmm_conduits'):
        #     self.uc.bar_warn('User Layer "Storm Drain Conduits" is empty!.')
        #     return
        # self.uc.clear_bar_messages()
        #
        # if self.gutils.is_table_empty('user_model_boundary'):
        #     self.uc.bar_warn('There is no computational domain! Please digitize it before running tool.')
        #     return
        # if self.gutils.is_table_empty('grid'):
        #     self.uc.bar_warn('There is no grid! Please create it before running tool.')
        #     return

        dlg_shapefile = StormDrainShapefile(self.con, self.iface, self.lyrs, self.tables)
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

    def block_saving(self):
        try_disconnect(self.inlet_data_model.dataChanged, self.save_rtables_data)

    def unblock_saving(self):
        self.inlet_data_model.dataChanged.connect(self.save_rtables_data)

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

    def populate_rtables_and_data(self):
        self.populate_rtables()
        self.populate_rtables_data()

    def populate_rtables(self):
        self.SD_rating_table_cbo.clear()
        duplicates = ""
        for row in self.inletRT.get_rating_tables():
            rt_fid, name = [x if x is not None else "" for x in row]
            if name != "":
                if self.SD_rating_table_cbo.findText(name) == -1:
                    self.SD_rating_table_cbo.addItem(name, rt_fid)
                else:
                    duplicates += name + "\n"

    #         if duplicates:
    #             self.uc.show_warn("WARNING 301220.0436:\n\nThe following rating tables are duplicated\n\n" + duplicates)

    def populate_rtables_data(self):
        idx = self.SD_rating_table_cbo.currentIndex()
        rt_fid = self.SD_rating_table_cbo.itemData(idx)
        rt_name = self.SD_rating_table_cbo.currentText()
        if rt_fid is None:
            #             self.uc.bar_warn("No rating table defined!")
            return

        self.inlet_series_data = self.inletRT.get_rating_tables_data(rt_fid)
        if not self.inlet_series_data:
            return
        self.create_plot(rt_name)
        self.tview.undoStack.clear()
        self.tview.setModel(self.inlet_data_model)
        self.inlet_data_model.clear()
        self.inlet_data_model.setHorizontalHeaderLabels(["Depth", "Q"])
        self.d1, self.d2 = [[], []]
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
        self.update_plot()

    def check_simulate_SD_1(self):
        qry = """SELECT value FROM cont WHERE name = 'SWMM';"""
        row = self.gutils.execute(qry).fetchone()
        if is_number(row[0]):
            if row[0] == "0":
                self.simulate_stormdrain_chbox.setChecked(False)
            else:
                self.simulate_stormdrain_chbox.setChecked(True)

    def check_RT_file(self, file):
        file_name, file_ext = os.path.splitext(os.path.basename(file))
        assigned = ""
        error0 = ""
        error1 = ""
        noInlet = ""
        no_4Type = ""

        # Is file empty?:
        if not os.path.isfile(file):
            error0 = "File " + file_name + file_ext + " is being used by another process!"
            return error0, error1, noInlet, no_4Type
        elif os.path.getsize(file) == 0:
            error0 = "File " + file_name + file_ext + " is empty!"
            return error0, error1, noInlet, no_4Type

        # Check 2 float values in columns:
        try:
            with open(file, "r") as f:
                for line in f:
                    row = line.split()
                    if row:
                        if len(row) != 2:
                            error1 = "File " + file_name + file_ext + " must have 2 columns in all lines!"
                            return error0, error1, noInlet, no_4Type
        except UnicodeDecodeError:
            error0 = "File " + file_name + file_ext + " is not a text file!"
            return error0, error1, noInlet, no_4Type

        # Check there is an inlet with the same name:
        user_inlet_qry = """SELECT name, intype FROM user_swmm_nodes WHERE name = ?;"""
        row = self.gutils.execute(user_inlet_qry, (file_name,)).fetchone()
        if not row:
            noInlet = "There isn't an inlet with name " + file_name
        elif row[1] != 4:
            no_4Type = file_name

        return error0, error1, noInlet, no_4Type

    def add_one_rt(self):
        self.add_single_rtable()

    def add_single_rtable(self, name=None):
        if not self.inletRT:
            return
        newRT = self.inletRT.add_rating_table(name)
        self.populate_rtables()
        newIdx = self.SD_rating_table_cbo.findText(newRT)
        if newIdx == -1:
            self.SD_rating_table_cbo.setCurrentIndex(self.SD_rating_table_cbo.count() - 1)
        else:
            self.SD_rating_table_cbo.setCurrentIndex(newIdx)
            self.populate_rtables_data()

    def add_rtable(self, name=None):
        if not self.inletRT:
            return
        newRT = self.inletRT.add_rating_table(name)
        self.populate_rtables()
        newIdx = self.SD_rating_table_cbo.findText(newRT)
        if newIdx == -1:
            self.SD_rating_table_cbo.setCurrentIndex(self.SD_rating_table_cbo.count() - 1)
        else:
            self.SD_rating_table_cbo.setCurrentIndex(newIdx)

    def refresh_SD_PlotAndTable(self):
        idx = self.SD_rating_table_cbo.currentIndex()

    def delete_rtables(self):
        if not self.inletRT:
            return
        rt_name = self.SD_rating_table_cbo.currentText()
        qry = """SELECT grid_fid, name FROM swmmflort WHERE name = ?"""
        rts = self.gutils.execute(qry, (rt_name,))
        for rt in rts:
            grid_fid = rt[0]
            if grid_fid is None or grid_fid == "":
                q = (
                    'WARNING 100319.1024:\n\nRating table "'
                    + rt_name
                    + '" is not assigned to any grid element.\nDo you want to delete it?'
                )
                if not self.uc.question(q):
                    return
                idx = self.SD_rating_table_cbo.currentIndex()
                rt_fid = self.SD_rating_table_cbo.itemData(idx)
                self.inletRT.del_rating_table(rt_fid)
                self.populate_rtables()
            else:
                if self.uc.question(
                    "WARNING 040319.0444:\n\nRating table '"
                    + rt_name
                    + "' is assigned to grid element "
                    + str(grid_fid)
                    + ".\nDo you want to delete it?.\n"
                ):
                    if self.uc.question(
                        "CONFIRM:  Delete rating table '"
                        + rt_name
                        + "' assigned to grid element "
                        + str(grid_fid)
                        + " ?"
                    ):
                        idx = self.SD_rating_table_cbo.currentIndex()
                        rt_fid = self.SD_rating_table_cbo.itemData(idx)
                        self.inletRT.del_rating_table(rt_fid)
                        self.populate_rtables()

    def rename_rtables(self):
        if not self.inletRT:
            return
        new_name, ok = QInputDialog.getText(None, "Change rating table name", "New name:")
        if not ok or not new_name:
            return
        if not self.SD_rating_table_cbo.findText(new_name) == -1:
            msg = "WARNING 060319.1735: Rating table with name {} already exists in the database. Please, choose another name.".format(
                new_name
            )
            self.uc.show_warn(msg)
            return
        idx = self.SD_rating_table_cbo.currentIndex()
        rt_fid = self.SD_rating_table_cbo.itemData(idx)
        self.inletRT.set_rating_table_data_name(rt_fid, new_name)
        self.populate_rtables()

    def save_rtables_data(self):
        idx = self.SD_rating_table_cbo.currentIndex()
        rt_fid = self.SD_rating_table_cbo.itemData(idx)
        self.update_plot()
        rt_data = []

        for i in range(self.inlet_data_model.rowCount()):
            # save only rows with a number in the first column
            if is_number(m_fdata(self.inlet_data_model, i, 0)) and not isnan(m_fdata(self.inlet_data_model, i, 0)):
                rt_data.append((rt_fid, m_fdata(self.inlet_data_model, i, 0), m_fdata(self.inlet_data_model, i, 1)))
            else:
                pass
        data_name = self.SD_rating_table_cbo.currentText()
        self.inletRT.set_rating_table_data(rt_fid, data_name, rt_data)

    def create_plot(self, name):
        self.plot.clear()
        if self.plot.plot.legend is not None:
            self.plot.plot.legend.scene().removeItem(self.plot.plot.legend)
        self.plot.plot.addLegend()
        self.plot_item_name = "Rating Table:   " + name
        self.plot.add_item(self.plot_item_name, [self.d1, self.d2], col=QColor("#0018d4"))
        self.plot.plot.setTitle("Rating Table   " + name)

    def update_plot(self):
        if not self.plot_item_name:
            return
        self.d1, self.d2 = [[], []]
        for i in range(self.inlet_data_model.rowCount()):
            self.d1.append(m_fdata(self.inlet_data_model, i, 0))
            self.d2.append(m_fdata(self.inlet_data_model, i, 1))
        self.plot.update_item(self.plot_item_name, [self.d1, self.d2])
