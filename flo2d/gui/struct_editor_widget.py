# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import sys, os
import csv
import io
from math import isnan
from qgis.PyQt.QtWidgets import QInputDialog, QApplication, QFileDialog, QTableView
from qgis.PyQt.QtCore import (
    Qt,
    QSettings,
    QMimeData,
    QUrl,
    QItemSelection,
    QItemSelectionModel,
    QPersistentModelIndex,
    pyqtSignal,
)
from qgis.core import QgsFeatureRequest, QgsApplication
from collections import OrderedDict
from PyQt5.QtWidgets import QApplication
from PyQt5 import QtGui
from PyQt5.QtGui import QClipboard
from qgis.PyQt import QtGui
from qgis.PyQt.QtGui import QColor

from .ui_utils import load_ui, center_canvas, set_icon, try_disconnect
from ..geopackage_utils import GeoPackageUtils
from ..flo2dobjects import Structure
from ..user_communication import UserCommunication
from ..utils import m_fdata, is_number
from .table_editor_widget import StandardItemModel, StandardItem
from ..gui.dlg_bridges import BridgesDialog
from _ast import Or

uiDialog, qtBaseClass = load_ui("struct_editor")


class StructEditorWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        #         self.twidget = table
        self.lyrs = lyrs
        self.setupUi(self)
        self.populate_rating_cbo()
        self.uc = UserCommunication(iface, "FLO-2D")
        self.struct = None
        self.gutils = None
        self.define_data_table_head()

        self.inletRT = None
        self.plot = plot
        self.plot_item_name = None
        self.table = table
        self.tview = table.tview
        self.data_model = StandardItemModel()
        self.tview.setModel(self.data_model)
        self.struct_data = None
        self.d1, self.d2 = [[], []]

        self.rating = ["Rating curve", "Rating table", "Culvert equation", "Bridge routine"]
        # set button icons
        set_icon(self.create_struct_btn, "mActionCaptureLine.svg")
        set_icon(self.save_changes_btn, "mActionSaveAllEdits.svg")
        set_icon(self.revert_changes_btn, "mActionUndo.svg")
        set_icon(self.delete_struct_btn, "mActionDeleteSelected.svg")
        set_icon(self.schem_struct_btn, "schematize_struct.svg")
        set_icon(self.change_struct_name_btn, "change_name.svg")

        # connections
        self.data_model.dataChanged.connect(self.save_data)
        self.create_struct_btn.clicked.connect(self.create_struct)
        self.save_changes_btn.clicked.connect(self.save_struct_lyrs_edits)
        self.revert_changes_btn.clicked.connect(self.cancel_struct_lyrs_edits)
        self.delete_struct_btn.clicked.connect(self.delete_struct)
        self.schem_struct_btn.clicked.connect(self.schematize_struct)
        self.struct_cbo.activated.connect(self.struct_changed)
        self.type_cbo.activated.connect(self.type_changed)
        self.rating_cbo.activated.connect(self.rating_changed)
        self.twater_effect_cbo.activated.connect(self.twater_changed)
        self.change_struct_name_btn.clicked.connect(self.change_struct_name)
        self.storm_drain_cap_sbox.editingFinished.connect(self.save_stormdrain_capacity)
        self.stormdrain_chbox.stateChanged.connect(self.clear_stormdrain_data)
        self.ref_head_elev_sbox.editingFinished.connect(self.save_head_ref_elev)
        self.culvert_len_sbox.editingFinished.connect(self.save_culvert_len)
        self.culvert_width_sbox.editingFinished.connect(self.save_culvert_width)
        self.bridge_variables_btn.clicked.connect(self.show_bridge)
        self.import_rating_table_btn.clicked.connect(self.import_struct_table)

        self.table.before_paste.connect(self.block_saving)
        self.table.after_paste.connect(self.unblock_saving)
        self.table.after_delete.connect(self.save_data)

    def populate_structs(self, struct_fid=None, show_last_edited=False):
        if not self.iface.f2d["con"]:
            return
        self.struct_cbo.clear()
        self.lyrs.clear_rubber()
        self.struct_lyr = self.lyrs.data["struct"]["qlyr"]
        self.user_struct_lyr = self.lyrs.data["user_struct"]["qlyr"]
        self.gutils = GeoPackageUtils(self.iface.f2d["con"], self.iface)
        all_structs = self.gutils.get_structs_list()
        cur_name_idx = 0
        for i, row in enumerate(all_structs):
            row = [x if x is not None else "" for x in row]
            fid, name, typ, notes = row
            if not name:
                name = "Structure {}".format(fid)
            self.struct_cbo.addItem(name, fid)
            if fid == struct_fid:
                cur_name_idx = i
        if not self.struct_cbo.count():
            return
        if show_last_edited:
            cur_name_idx = i
        self.struct_cbo.setCurrentIndex(cur_name_idx)
        self.struct_changed()

    def block_saving(self):
        try_disconnect(self.data_model.dataChanged, self.save_data)

    def unblock_saving(self):
        self.data_model.dataChanged.connect(self.save_data)

    def struct_changed(self):
        self.table.after_delete.disconnect()
        self.table.after_delete.connect(self.save_data)

        cur_struct_idx = self.struct_cbo.currentIndex()
        sdata = self.struct_cbo.itemData(cur_struct_idx)
        if sdata:
            fid = sdata
        else:
            return

        self.clear_structs_data_widgets()
        self.data_model.clear()
        self.struct = Structure(fid, self.iface.f2d["con"], self.iface)
        self.struct.get_row()
        self.show_struct_rb()
        if self.center_chbox.isChecked():
            feat = next(self.user_struct_lyr.getFeatures(QgsFeatureRequest(self.struct.fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

        self.type_changed(None)
        self.rating_changed(None)
        self.twater_changed(None)
        self.set_stormdrain()
        if is_number(self.struct.headrefel):
            self.ref_head_elev_sbox.setValue(self.struct.headrefel)
        if is_number(self.struct.clength):
            self.culvert_len_sbox.setValue(self.struct.clength)
        if is_number(self.struct.cdiameter):
            self.culvert_width_sbox.setValue(self.struct.cdiameter)

        # self.struct_cbo.setCurrentIndex(fid)
        self.show_table_data()

    def type_changed(self, idx):
        if not self.struct:
            return
        if idx is None:
            idx = self.struct.ifporchan
            if is_number(idx):
                self.type_cbo.setCurrentIndex(idx)
            else:
                self.type_cbo.setCurrentIndex(0)
        else:
            self.struct.ifporchan = idx
            self.gutils.execute("UPDATE struct SET ifporchan = ? WHERE structname =?;", (idx, self.struct.name))
            # self.struct.set_row()

    def rating_changed(self, idx):
        if not self.struct:
            return
        if idx is None:
            idx = self.struct.icurvtable
            if is_number(idx):
                self.rating_cbo.setCurrentIndex(idx)
            else:
                self.rating_cbo.setCurrentIndex(0)
        else:
            self.struct.icurvtable = idx
            self.gutils.execute("UPDATE struct SET icurvtable = ? WHERE structname =?;", (idx, self.struct.name))
            # self.struct.set_row()
        self.show_table_data()
        self.bridge_variables_btn.setVisible(self.rating_cbo.currentIndex() == 3)  # Bridge routine

    #         self.import_rating_table_btn.setVisible(self.rating_cbo.currentIndex() == 1)

    def twater_changed(self, idx):
        if not self.struct:
            return
        if idx is None:
            idx = self.struct.inoutcont
            if is_number(idx):
                self.twater_effect_cbo.setCurrentIndex(idx)
            else:
                self.twater_effect_cbo.setCurrentIndex(0)
        else:
            self.struct.inoutcont = idx
            self.gutils.execute("UPDATE struct SET inoutcont = ? WHERE structname =?;", (idx, self.struct.name))
            # self.struct.set_row()

    def set_stormdrain(self):
        sd = self.struct.get_stormdrain()
        if sd:
            self.stormdrain_chbox.setChecked(True)
            self.storm_drain_cap_sbox.setValue(sd)
        else:
            self.stormdrain_chbox.setChecked(False)

    def clear_stormdrain_data(self):
        if not self.struct:
            return
        if not self.stormdrain_chbox.isChecked():
            self.storm_drain_cap_sbox.clear()
            self.struct.clear_stormdrain_data()
            self.storm_drain_cap_sbox.setEnabled(False)
        else:
            self.storm_drain_cap_sbox.setEnabled(True)

    def schematize_struct(self):
        if not self.gutils.execute("SELECT * FROM user_struct;").fetchone():
            self.uc.show_warn("WARNING 040220.0728: there are no user structures to schematize!")
            return

        qry = "SELECT * FROM struct WHERE geom IS NOT NULL;"
        exist_struct = self.gutils.execute(qry).fetchone()
        if exist_struct:
            if not self.uc.question("There are some schematized structures created already. Overwrite them?"):
                return

        del_qry = "DELETE FROM struct WHERE fid NOT IN (SELECT fid FROM user_struct);"
        self.gutils.execute(del_qry)
        upd_cells_qry = """UPDATE struct SET
            inflonod = (
                SELECT g.fid FROM
                    grid AS g,
                    user_struct AS us
                WHERE
                    ST_Intersects(ST_StartPoint(GeomFromGPB(us.geom)), GeomFromGPB(g.geom)) AND
                    us.fid = struct.fid
                LIMIT 1
            ),
            outflonod = (
                SELECT g.fid FROM
                    grid AS g,
                    user_struct AS us
                WHERE
                    ST_Intersects(ST_EndPoint(GeomFromGPB(us.geom)), GeomFromGPB(g.geom)) AND
                    us.fid = struct.fid
                LIMIT 1);"""
        self.gutils.execute(upd_cells_qry)

        upd_stormdrains_qry = """UPDATE storm_drains SET
                    istormdout = (
                        SELECT outflonod FROM
                            struct
                        WHERE
                            storm_drains.struct_fid = struct.fid
                        LIMIT 1
                    );"""
        self.gutils.execute(upd_stormdrains_qry)

        qry = "SELECT fid, inflonod, outflonod FROM struct;"
        structs = self.gutils.execute(qry).fetchall()
        for struct in structs:
            fid, inflo, outflo = struct
            geom = self.gutils.build_linestring([inflo, outflo])
            upd_geom_qry = """UPDATE struct SET geom = ? WHERE fid = ?;"""
            self.gutils.execute(
                upd_geom_qry,
                (
                    geom,
                    fid,
                ),
            )
        self.lyrs.lyrs_to_repaint = [self.lyrs.data["struct"]["qlyr"]]
        self.lyrs.repaint_layers()

    def clear_structs_data_widgets(self):
        self.storm_drain_cap_sbox.clear()
        self.ref_head_elev_sbox.clear()
        self.culvert_len_sbox.clear()
        self.culvert_width_sbox.clear()
        self.data_model.clear()

    def populate_rating_cbo(self):
        self.rating_cbo.clear()
        self.rating_types = OrderedDict(
            [(0, "Rating curve"), (1, "Rating table"), (2, "Culvert equation"), (3, "Bridge routine")]
        )
        for typ, name in self.rating_types.items():
            self.rating_cbo.addItem(name, typ)

    def import_struct_table(self):
        try:
            self.uc.show_info("Only files with the same name of the existing structures will be loaded.")
            tables_in = ""
            tables_out = ""
            s = QSettings()
            last_dir = s.value("FLO-2D/ImportStructTable", "")

            rating_files, __ = QFileDialog.getOpenFileNames(
                None,
                "Select rating table files",
                directory=last_dir,
                filter="(*.TXT *.DAT);;(*.TXT);;(*.DAT);;(*.*)",
            )

            if not rating_files:
                return

            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                s.setValue("FLO-2D/ImportStructTable", os.path.dirname(rating_files[0]))
                for file in rating_files:
                    file_name, file_ext = os.path.splitext(os.path.basename(file))

                    # See if there is structure with same name of file:
                    row = self.gutils.execute(
                        "SELECT fid, icurvtable FROM struct WHERE structname  = ?", (file_name,)
                    ).fetchone()

                    if row:
                        tables_in += file_name + "\n"
                        # There is an structure with name 'file_name':
                        struct_fid, icurvtable = row[0], row[1]
                        # If there is a rating table for this structure delete it:
                        self.gutils.execute("DELETE FROM rat_table WHERE struct_fid = ?;", (row[0],))

                        # Insert new rating table and assign it to this structure:
                        with open(file, "r") as f1:
                            for line in f1:
                                row = line.split()
                                if row:
                                    self.gutils.execute(
                                        "INSERT INTO rat_table (struct_fid, hdepth, qtable) VALUES (?, ?, ?)",
                                        (struct_fid, row[0], row[1]),
                                    )
                        if icurvtable != 1:
                            # The structure is not of type 'rating table'.
                            QApplication.restoreOverrideCursor()
                            answer = self.uc.question(
                                "Structure '"
                                + file_name
                                + "' is not of rating type 'rating table'.\n\n"
                                + "Would you like to change its type to 'rating table' (icurvtable = 1)?"
                            )
                            if answer:
                                self.gutils.execute(
                                    "UPDATE struct SET icurvtable = ? WHERE structname =?;", (1, file_name)
                                )
                                self.rating_cbo.setCurrentIndex(1)

                            QApplication.setOverrideCursor(Qt.WaitCursor)
                    else:
                        # There is no structure with name 'file_name'.
                        tables_out += file_name + "\n"
                        pass

                QApplication.restoreOverrideCursor()
                txt = ""
                if tables_in != "":
                    txt = "The following files were loaded:\n" + tables_in
                if tables_out != "":
                    txt += "The following files were not loaded:\n" + tables_out
                if txt != "":
                    self.uc.show_info(txt)

            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error("ERROR 111120.1019: importing structures rating tables failed!\n", e)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 111120.1020: importing structures rating tables failed!\n", e)

    def change_struct_name(self):
        if not self.struct_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, "Change name", "New name (no spaces, max 15 characters):")
        if not ok or not new_name:
            return
        if not self.struct_cbo.findText(new_name) == -1:
            msg = "WARNING 060319.1737: Structure with name {} already exists in the database. Please, choose another name.".format(
                new_name
            )
            self.uc.show_warn(msg)
            return
        self.struct.name = new_name.replace(" ", "_")[:15]
        self.struct.set_row()
        self.populate_structs(struct_fid=self.struct.fid)

    def save_stormdrain_capacity(self):
        if not self.struct_cbo.count():
            return
        cap = self.storm_drain_cap_sbox.value()
        self.struct.set_stormdrain_capacity(cap)

    def save_head_ref_elev(self):
        if not self.struct_cbo.count():
            return
        self.struct.headrefel = self.ref_head_elev_sbox.value()
        self.gutils.execute(
            "UPDATE struct SET headrefel = ? WHERE structname =?;", (self.struct.headrefel, self.struct.name)
        )
        # self.struct.set_row()

    def save_culvert_len(self):
        if not self.struct_cbo.count():
            return
        self.struct.clength = self.culvert_len_sbox.value()
        self.gutils.execute(
            "UPDATE struct SET clength = ? WHERE structname =?;", (self.struct.clength, self.struct.name)
        )
        # self.struct.set_row()

    def save_culvert_width(self):
        if not self.struct_cbo.count():
            return
        self.struct.cdiameter = self.culvert_width_sbox.value()
        self.gutils.execute(
            "UPDATE struct SET cdiameter = ? WHERE structname =?;", (self.struct.cdiameter, self.struct.name)
        )
        # self.struct.set_row()

    def define_data_table_head(self):
        self.tab_heads = {
            0: ["HDEPEXC", "COEFQ", "EXPQ", "COEFA", "EXPA", "REPDEP", "RQCOEF", "RQEXP", "RACOEF", "RAEXP"],
            1: ["HDEPTH", "QTABLE", "ATABLE"],
            2: ["TYPEC", "TYPEEN", "CULVERTN", "KE", "CUBASE", "MULTBARRELS"],
            3: ["XUP", "YUP", "YB"],
        }
        self.tab_tips = {
            0: [
                "Maximum depth that a hydraulic structure rating curve is valid",
                "Discharge rating curve coefficients as a power function of the headwater depth.",
                "Hydraulic structure discharge exponent",
                "Flow area rating curve coefficient (long culvert routine)",
                "Flow area exponent (long culvert routine)",
                "Flow depth that if exceeded will invoke the replacement structure rating curve parameters",
                "Structure rating curve discharge replacement coefficients",
                "Structure rating curve discharge replacement exponents",
                "Flow area rating curve replacement coefficient (long culvert routine)",
                "Flow area replacement exponent (long culvert routine)",
            ],
            1: [
                "Headwater depth for the structure headwater depth-discharge rating table",
                "Hydraulic structure discharges for the headwater depths",
                "hydraulic structure flow area for each headwater depth",
            ],
            2: [
                "Culvert switch, either 1 or 2. Set TYPEC=1 for a box culvert and TYPEC=2 for a pipe culvert",
                "Culvert switch. Set TYPEEN(I) for entrance type 1, 2, or 3.",
                "Culvert Manning’s roughness coefficient",
                "Culvert entrance loss coefficient",
                "Flow width of box culvert for TYPEC=1. For a circular culvert, CUBASE=0",
            ],
        }

    def show_table_data(self):
        try:
            self.table.after_delete.disconnect()
            self.table.after_delete.connect(self.save_data)

            self.plot.clear()
            if self.plot.plot.legend is not None:
                plot_scene = self.plot.plot.legend.scene()
                if plot_scene is not None:
                    plot_scene.removeItem(self.plot.plot.legend)
            self.plot.plot.addLegend()
            self.plot.plot.setTitle("")

            if not self.struct:
                return
            else:
                self.struct_data = self.struct.get_table_data()
                if not self.struct_data:
                    return

            rating = self.rating_cbo.currentIndex()
            struct_name = ""

            idx = self.struct_cbo.currentIndex()
            struct_fid = self.struct_cbo.itemData(idx)
            struct_name = self.struct_cbo.currentText()
            if struct_fid is None:
                return
            # if rating in [1, 3]:  # Rating Table  or Bridge XS
            #     idx = self.struct_cbo.currentIndex()
            #     struct_fid = self.struct_cbo.itemData(idx)
            #     struct_name = self.struct_cbo.currentText()
            #     if struct_fid is None:
            #         return

            self.tview.undoStack.clear()
            self.tview.setModel(self.data_model)
            self.data_model.clear()
            self.data_model.setHorizontalHeaderLabels(self.tab_heads[self.struct.icurvtable])
            self.d1, self.d2 = [[], []]

            if self.struct.icurvtable == "":
                self.struct.icurvtable = 0
            tab_col_nr = len(self.tab_heads[self.struct.icurvtable])
            for row in self.struct_data:
                items = [StandardItem("{:.4f}".format(x)) if x is not None else StandardItem("") for x in row]
                self.data_model.appendRow(items)

                if row:
                    self.d1.append(row[0] if not row[0] is None else float("NaN"))
                    self.d2.append(row[1] if not row[1] is None else float("NaN"))
                else:
                    self.d1.append(float("NaN"))
                    self.d2.append(float("NaN"))
                # if rating in [1, 3]:  # Rating Table or Bridge XS
                #     if row:
                #         self.d1.append(row[0] if not row[0] is None else float("NaN"))
                #         self.d2.append(row[1] if not row[1] is None else float("NaN"))
                #     else:
                #         self.d1.append(float("NaN"))
                #         self.d2.append(float("NaN"))

            rc = self.data_model.rowCount()
            if rc < 10:
                for row in range(rc, 10 + 1):
                    items = [StandardItem(x) for x in ("",) * tab_col_nr]
                    self.data_model.appendRow(items)

            self.tview.horizontalHeader().setStretchLastSection(True)
            self.tview.resizeColumnsToContents()
            for i in range(self.data_model.rowCount()):
                self.tview.setRowHeight(i, 20)

            if rating in [1, 3]:  # Rating Table or Bridge XS
                self.create_plot(rating, struct_name)
                self.update_plot()
            else:
                self.plot.clear()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 211222.1017: something went wrong when plotting table!\n", e)

    def create_plot(self, rating, name):
        self.plot.clear()
        if rating in [1, 3]:
            if self.plot.plot.legend is not None:
                plot_scene = self.plot.plot.legend.scene()
                if plot_scene is not None:
                    plot_scene.removeItem(self.plot.plot.legend)
            self.plot.plot.addLegend()
            prefix = "Rating Table:   " if rating == 1 else "Bridge XS Table:   " if rating == 3 else ""
            self.plot_item_name = prefix + name
            self.plot.add_item(self.plot_item_name, [self.d1, self.d2], col=QColor("#0018d4"))
            self.plot.plot.setTitle(prefix + name)

    def update_plot(self):
        if not self.plot_item_name:
            return
        self.d1, self.d2 = [[], []]
        for i in range(self.data_model.rowCount()):
            self.d1.append(m_fdata(self.data_model, i, 0))
            self.d2.append(m_fdata(self.data_model, i, 1))
        self.plot.update_item(self.plot_item_name, [self.d1, self.d2])

    def save_data(self):
        data = []
        for i in range(self.data_model.rowCount()):
            # save only rows with a number in the first column
            if is_number(m_fdata(self.data_model, i, 0)) and not isnan(m_fdata(self.data_model, i, 0)):
                data.append([m_fdata(self.data_model, i, j) for j in range(self.data_model.columnCount())])
        self.struct.set_table_data(data)
        rating = self.rating_cbo.currentIndex()
        if rating in [1, 3]:  # Rating Table or Bridge XS
            self.update_plot()

    def show_struct_rb(self):
        self.lyrs.show_feat_rubber(self.user_struct_lyr.id(), self.struct.fid)

    def delete_struct(self):
        if not self.struct_cbo.count() or not self.struct.fid:
            return
        q = "Are you sure, you want delete the current structure?"
        if not self.uc.question(q):
            return
        old_fid = self.struct.fid
        self.struct.del_row()
        self.clear_structs_data_widgets()
        self.repaint_structs()
        # try to set current struct to the last before the deleted one
        try:
            self.populate_structs(struct_fid=old_fid - 1)
        except Exception as e:
            self.populate_structs()

    def create_struct(self):
        if not self.lyrs.enter_edit_mode("user_struct"):
            return
        # self.struct_frame.setDisabled(True)

    def cancel_struct_lyrs_edits(self):
        user_lyr_edited = self.lyrs.rollback_lyrs_edits("user_struct")
        if user_lyr_edited:
            try:
                self.populate_structs(self.struct.fid)
            except AttributeError:
                self.populate_structs()
        # self.struct_frame.setEnabled(True)

    def save_struct_lyrs_edits(self):
        """
        Save changes of user layer.
        """
        if not self.gutils or not self.lyrs.any_lyr_in_edit("user_struct"):
            return
        # ask user if overwrite imported structures, if any
        if not self.gutils.delete_all_imported_structs():
            self.cancel_struct_lyrs_edits()
            return
        # try to save user layer (geometry additions/changes)
        user_lyr_edited = self.lyrs.save_lyrs_edits("user_struct")
        # if user layer was edited
        if user_lyr_edited:
            # self.struct_frame.setEnabled(True)
            # populate widgets and show last edited struct
            self.gutils.copy_new_struct_from_user_lyr()
            self.gutils.fill_empty_struct_names()
            self.populate_structs(show_last_edited=True)
        self.repaint_structs()

    def repaint_structs(self):
        self.lyrs.lyrs_to_repaint = [self.lyrs.data["user_struct"]["qlyr"], self.lyrs.data["struct"]["qlyr"]]
        self.lyrs.repaint_layers()

    def show_bridge(self):
        """
        Shows bridge dialog.

        """
        if not self.struct_cbo.count():
            self.uc.bar_warn("There are no structures defined!")
            return
        dlg_bridge = BridgesDialog(self.iface, self.lyrs, self.struct_cbo.currentText())
        dlg_bridge.setWindowTitle("Bridge Variables for structure '" + self.struct_cbo.currentText() + "'")
        save = dlg_bridge.exec_()
        if save:
            if dlg_bridge.save_bridge_variables():
                self.uc.show_info("Bridge variables saved for '" + self.struct_cbo.currentText() + "'")
            else:
                self.uc.bar_warn("Could not save bridge variables!")
