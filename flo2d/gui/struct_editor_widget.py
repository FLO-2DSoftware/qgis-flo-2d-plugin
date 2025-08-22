# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import math
import os
import re
from collections import OrderedDict
from math import isnan

from PyQt5.QtGui import QDesktopServices
from qgis._gui import QgsDockWidget
from qgis.core import QgsFeatureRequest
from qgis.PyQt.QtCore import (
    QSettings,
    Qt,
)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QApplication, QFileDialog, QInputDialog
from PyQt5.QtCore import QUrl

from .dlg_check_report import GenericCheckReportDialog
from ..flo2dobjects import Structure
from ..geopackage_utils import GeoPackageUtils
from ..gui.dlg_bridges import BridgesDialog
from ..misc.project_review_utils import hydrostruct_dataframe_from_hdf5_scenarios, SCENARIO_COLOURS, SCENARIO_STYLES
from ..user_communication import UserCommunication
from ..utils import is_number, m_fdata
from .table_editor_widget import StandardItem, StandardItemModel
from .ui_utils import center_canvas, load_ui, set_icon, try_disconnect

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

        self.system_units = {
            "CMS": ["m", "mps", "cms"],
            "CFS": ["ft", "fps", "cfs"]
             }

        self.inletRT = None
        self.plot = plot
        self.plot_item_name = None
        self.table = table
        self.tview = table.tview
        self.data_model = StandardItemModel()
        self.tview.setModel(self.data_model)
        self.struct_data = None
        self.d1, self.d2 = [[], []]

        self.rating = [
            "Rating curve",
            "Rating table",
            "Culvert equation",
            "Bridge routine",
        ]
        # set button icons
        set_icon(self.create_struct_btn, "mActionCaptureLine.svg")
        set_icon(self.save_changes_btn, "mActionSaveAllEdits.svg")
        set_icon(self.revert_changes_btn, "mActionUndo.svg")
        set_icon(self.delete_struct_btn, "mActionDeleteSelected.svg")
        set_icon(self.schem_struct_btn, "schematize_struct.svg")
        set_icon(self.change_struct_name_btn, "change_name.svg")

        # layers
        self.user_struct_lyr = self.lyrs.data["user_struct"]["qlyr"]
        self.struct_lyr = self.lyrs.data["struct"]["qlyr"]

        # connections
        self.data_model.dataChanged.connect(self.save_data)
        self.create_struct_btn.clicked.connect(self.create_struct)
        self.save_changes_btn.clicked.connect(self.save_struct_lyrs_edits)
        self.user_struct_lyr.afterCommitChanges.connect(self.save_struct_lyrs_edits)
        self.revert_changes_btn.clicked.connect(self.cancel_struct_lyrs_edits)
        self.delete_struct_btn.clicked.connect(self.delete_struct)
        self.schem_struct_btn.clicked.connect(self.schematize_struct)
        self.structures_help_btn.clicked.connect(self.structures_help)
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
        if self.center_btn.isChecked():
            try:
                feat = next(self.user_struct_lyr.getFeatures(QgsFeatureRequest(self.struct.fid)))
                x, y = feat.geometry().centroid().asPoint()
                center_canvas(self.iface, x, y)
            except:
                pass   

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
            self.gutils.execute(
                "UPDATE struct SET ifporchan = ? WHERE structname =?;",
                (idx, self.struct.name),
            )
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
            self.gutils.execute(
                "UPDATE struct SET icurvtable = ? WHERE structname =?;",
                (idx, self.struct.name),
            )
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
            self.gutils.execute(
                "UPDATE struct SET inoutcont = ? WHERE structname =?;",
                (idx, self.struct.name),
            )
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
        """
        Function to schematize the Hydraulic Structures
        """
        if not self.gutils.execute("SELECT * FROM user_struct;").fetchone():
            self.uc.bar_info("WARNING 040220.0728: there are no user structures to schematize!")
            self.uc.log_info("WARNING 040220.0728: there are no user structures to schematize!")
            return

        qry = "SELECT * FROM struct WHERE geom IS NOT NULL;"
        exist_struct = self.gutils.execute(qry).fetchone()
        if exist_struct:
            if not self.uc.question("There are some schematized structures created already. Overwrite them?"):
                return

        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)

            del_qry = "DELETE FROM struct WHERE fid NOT IN (SELECT fid FROM user_struct);"
            self.gutils.execute(del_qry)

            batch_updates = []
            for feat in self.user_struct_lyr.getFeatures():
                line_geom = feat.geometry().asPolyline()
                fid = feat["fid"]
                start = line_geom[0]
                end = line_geom[-1]
                inflonod = self.gutils.grid_on_point(start.x(), start.y())
                outflonod = self.gutils.grid_on_point(end.x(), end.y())
                batch_updates.append((inflonod, outflonod, fid))

            self.gutils.execute_many("UPDATE struct SET inflonod = ?, outflonod = ? WHERE fid = ?;", batch_updates)

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

            QApplication.restoreOverrideCursor()
            if structs:

                # Set Structures on the Control Parameters
                self.gutils.set_cont_par("IHYDRSTRUCT", 1)

                # Return False there are some errors
                if self.check_structures():
                    self.uc.bar_info("Schematizing Hydraulic Structures finished with errors. Check the report!")
                    self.uc.log_info("Schematizing Hydraulic Structures finished with errors. Check the report!")

                # Return True there are no errors
                else:
                    self.uc.log_info(
                        "Schematizing Hydraulic Structures finished! The Hydraulic Structure switch is now enabled.\n\n"
                        + str(len(structs)) + " structures were updated in the Hydraulic Structures table."
                    )
                    self.uc.bar_info(
                        "Schematizing Hydraulic Structures finished! The Hydraulic Structure switch is now enabled."
                    )
            else:
                self.uc.bar_error("WARNING 151203.0646: Error during Hydraulic Structures schematization!")
                self.uc.log_info("WARNING 151203.0646: Error during Hydraulic Structures schematization!")

        except Exception as e:
            self.uc.bar_error("WARNING 151203.0646: Error during Hydraulic Structures schematization!")
            self.uc.log_info("WARNING 151203.0646: Error during Hydraulic Structures schematization!.")

    def check_structures(self):
        """
        Function to check the structures and create a report
        """
        same_inlet_outlet = []
        same_inlets = []
        same_outlets = []
        short_struct = []

        cellsize = float(self.gutils.get_cont_par("CELLSIZE"))
        min_dist = math.sqrt(cellsize ** 2 + cellsize ** 2)

        for feat in self.struct_lyr.getFeatures():
            inlet_grid = feat["inflonod"]
            outlet_grid = feat["outflonod"]

            # Error 1 - Inlet and outlet on the same cell
            if inlet_grid == outlet_grid:
                if inlet_grid not in same_inlet_outlet:
                    same_inlet_outlet.append(inlet_grid)

            # Error 2 - One or more inlets in the same cell
            n_inlets = self.gutils.execute(f"SELECT COUNT(inflonod) FROM struct WHERE inflonod = '{inlet_grid}'").fetchone()[0]
            if n_inlets > 1:
                if inlet_grid not in same_inlets:
                    same_inlets.append(inlet_grid)

            # Error 3 - One or more outlets in the same cell
            n_outlets = self.gutils.execute(f"SELECT COUNT(outflonod) FROM struct WHERE outflonod = '{outlet_grid}'").fetchone()[0]
            if n_outlets > 1:
                if outlet_grid not in same_outlets:
                    same_outlets.append(outlet_grid)

            # Error 4 - Inlet and outlet too close
            ifporchan = feat["ifporchan"]
            # It's ok to have an inlet and outline in adjacent cells if they are channel to channel.
            if ifporchan != 1:
                # Distance between the inlet and outlet must be greater than sqrt(cellsize^2 + cellsize^2)
                struct_geom = feat.geometry()
                struct_len = struct_geom.length()
                if struct_len != 0 and struct_len <= min_dist:
                    short_struct.append(inlet_grid)

        msg = ""

        if len(same_inlet_outlet) > 0:
            msg += "ERROR: STRUCTURE INLET AND OUTLET ON THE SAME GRID CELL.  " \
                   f"GRID ELEMENTS(S): \n{'-'.join(map(str, same_inlet_outlet))}\n\n"

        if len(same_inlets) > 0:
            msg += "ERROR: TWO OR MORE STRUCTURES SHARING THE SAME INLET CELL.  " \
                   f"GRID ELEMENTS(S): \n{'-'.join(map(str, same_inlets))}\n\n"

        if len(same_outlets) > 0:
            msg += "ERROR: TWO OR MORE STRUCTURES SHARING THE SAME OUTLET CELL.  " \
                   f"GRID ELEMENTS(S): \n{'-'.join(map(str, same_outlets))}\n\n"

        if len(short_struct) > 0:
            msg += "ERROR: STRUCTURE INLET AND OUTLET SEPARATED BY LESS THAN ONE CELL.  " \
                   f"GRID ELEMENTS(S): \n{'-'.join(map(str, short_struct))}\n\n"

        for widget in QApplication.instance().allWidgets():
            if isinstance(widget, QgsDockWidget):
                if widget.windowTitle() == "FLO-2D Hydraulic Structures Check Report":
                    widget.close()

        if msg != "":
            self.uc.log_info(msg)
            dlg_structures_report = GenericCheckReportDialog(self.iface, self.lyrs, self.gutils)
            plot_dock = QgsDockWidget()
            plot_dock.setWindowTitle("FLO-2D Hydraulic Structures Check Report")
            plot_dock.setWidget(dlg_structures_report)
            self.iface.addDockWidget(Qt.BottomDockWidgetArea, plot_dock)
            dlg_structures_report.report_te.insertPlainText(msg)

            grid_errors = list(set(
                str(item) for sublist in
                [same_inlet_outlet, same_inlets, same_outlets, short_struct]
                for item in sublist))

            dlg_structures_report.error_grids_cbo.addItems(grid_errors)
            dlg_structures_report.show()
            while True:
                ok = dlg_structures_report.exec_()
                if ok:
                    break
                else:
                    return
        else:
            return False

    def structures_help(self):
        QDesktopServices.openUrl(QUrl("https://flo-2dsoftware.github.io/FLO-2D-Documentation/Plugin1000/widgets/hydraulic-structure-editor/Hydraulic%20Structure%20Editor.html"))        

    def clear_structs_data_widgets(self):
        self.storm_drain_cap_sbox.clear()
        self.ref_head_elev_sbox.clear()
        self.culvert_len_sbox.clear()
        self.culvert_width_sbox.clear()
        self.data_model.clear()

    def populate_rating_cbo(self):
        self.rating_cbo.clear()
        self.rating_types = OrderedDict(
            [
                (0, "Rating curve"),
                (1, "Rating table"),
                (2, "Culvert equation"),
                (3, "Bridge routine"),
            ]
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
                        "SELECT fid, icurvtable FROM struct WHERE structname  = ?",
                        (file_name,),
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
                                    "UPDATE struct SET icurvtable = ? WHERE structname =?;",
                                    (1, file_name),
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
                    self.struct_changed()
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
            "UPDATE struct SET headrefel = ? WHERE structname =?;",
            (self.struct.headrefel, self.struct.name),
        )
        # self.struct.set_row()

    def save_culvert_len(self):
        if not self.struct_cbo.count():
            return
        self.struct.clength = self.culvert_len_sbox.value()
        self.gutils.execute(
            "UPDATE struct SET clength = ? WHERE structname =?;",
            (self.struct.clength, self.struct.name),
        )
        # self.struct.set_row()

    def save_culvert_width(self):
        if not self.struct_cbo.count():
            return
        self.struct.cdiameter = self.culvert_width_sbox.value()
        self.gutils.execute(
            "UPDATE struct SET cdiameter = ? WHERE structname =?;",
            (self.struct.cdiameter, self.struct.name),
        )
        # self.struct.set_row()

    def define_data_table_head(self):
        self.tab_heads = {
            0: [
                "HDEPEXC",
                "COEFQ",
                "EXPQ",
                "COEFA",
                "EXPA",
                "REPDEP",
                "RQCOEF",
                "RQEXP",
                "RACOEF",
                "RAEXP",
            ],
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
        if not self.gutils:
            return
        # ask user if overwrite imported structures, if any
        # if not self.gutils.delete_all_imported_structs():
        #     self.cancel_struct_lyrs_edits()
        #     return
        # try to save user layer (geometry additions/changes)
        self.lyrs.save_lyrs_edits("user_struct")
        # populate widgets and show last edited struct
        self.gutils.copy_new_struct_from_user_lyr()
        self.gutils.fill_empty_struct_names()
        self.populate_structs(show_last_edited=True)
        self.repaint_structs()

    def repaint_structs(self):
        self.lyrs.lyrs_to_repaint = [
            self.lyrs.data["user_struct"]["qlyr"],
            self.lyrs.data["struct"]["qlyr"],
        ]
        self.lyrs.repaint_layers()

    def show_bridge(self):
        """
        Shows bridge dialog.

        """
        if not self.struct_cbo.count():
            self.uc.bar_warn("There are no structures defined!")
            self.uc.log_info("There are no structures defined!")
            return
        dlg_bridge = BridgesDialog(self.iface, self.lyrs, self.struct_cbo.currentText())
        dlg_bridge.setWindowTitle("Bridge Variables for structure '" + self.struct_cbo.currentText() + "'")
        save = dlg_bridge.exec_()
        if save:
            if dlg_bridge.save_bridge_variables():
                self.uc.show_info("Bridge variables saved for '" + self.struct_cbo.currentText() + "'")
            else:
                self.uc.bar_warn("Could not save bridge variables!")
                self.uc.log_info("Could not save bridge variables!")

    def show_hydrograph(self, table, fid):
        """
        Function to load the structure hydrograph data from HYDROSTRUCT.OUT
        """
        self.uc.clear_bar_messages()
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            self.uc.log_info("There is no grid! Please create it before running tool.")
            return False

        units = "CMS" if self.gutils.get_cont_par("METRIC") == "1" else "CFS"

        # Get structure name from FID because the HYDROSTRUCT.OUT structure number is not always the same as the FID
        struct_name = self.gutils.execute(
            "SELECT structname FROM struct WHERE fid = ?;",
            (fid,),
        ).fetchone()

        if struct_name:
            struct_name = struct_name[0]
        else:
            self.uc.bar_warn("No Hydraulic Structure found!")
            self.uc.log_info("No Hydraulic Structure found!")
            return False

        s = QSettings()

        processed_results_file = s.value("FLO-2D/processed_results", "")
        if os.path.exists(processed_results_file):
            # try:

            dict_df = hydrostruct_dataframe_from_hdf5_scenarios(processed_results_file, struct_name)
            self.uc.log_info(str(dict_df))

            # Clear the plots
            self.plot.clear()
            if self.plot.plot.legend is not None:
                plot_scene = self.plot.plot.legend.scene()
                if plot_scene is not None:
                    plot_scene.removeItem(self.plot.plot.legend)

            # Set up legend and plot title
            self.plot.plot.legend = None
            self.plot.plot.addLegend(offset=(0, 30))
            self.plot.plot.setTitle(title=f"Hydraulic Structure: {struct_name}")
            self.plot.plot.setLabel("bottom", text="Time (hrs)")
            self.plot.plot.setLabel("left", text="")

            # Create a new data model for the table view.
            data_model = StandardItemModel()
            self.tview.undoStack.clear()
            self.tview.setModel(data_model)
            data_model.clear()
            headers = ["Time (hours)"]

            for i, (key, value) in enumerate(dict_df.items(), start=0):
                self.plot.add_item(f"Inflow ({self.system_units[units][2]})", [value['Time'], value['Inflow']],
                                   col=SCENARIO_COLOURS[i], sty=SCENARIO_STYLES[0])
                self.plot.add_item(f"Outflow ({self.system_units[units][2]})", [value['Time'], value['Outflow']],
                                   col=SCENARIO_COLOURS[i], sty=SCENARIO_STYLES[1], hide=True)

                headers.extend([
                    f"{key} - Inflow ({self.system_units[units][2]})",
                    f"{key} - Outflow ({self.system_units[units][2]})",
                ])
                data_model.setHorizontalHeaderLabels(headers)

                for row_idx, row in enumerate(value):
                    if i == 0:
                        data_model.setItem(row_idx, 0,
                                           StandardItem("{:.2f}".format(row[0]) if row[0] is not None else ""))
                    data_model.setItem(row_idx, 1 + i * 2,
                                       StandardItem("{:.2f}".format(row[1]) if row[1] is not None else ""))
                    data_model.setItem(row_idx, 2 + i * 2,
                                       StandardItem("{:.2f}".format(row[2]) if row[2] is not None else ""))

            # except:
            #     QApplication.restoreOverrideCursor()
            #     self.uc.bar_warn("Error while creating the plots!")
            #     self.uc.log_info("Error while creating the plots!")
            #     return
        else:
            HYDROSTRUCT_file = s.value("FLO-2D/lastHYDROSTRUCTFile", "")
            GDS_dir = s.value("FLO-2D/lastGdsDir", "")
            # Check if there is an HYDROSTRUCT.OUT file on the FLO-2D QSettings
            if not os.path.isfile(HYDROSTRUCT_file):
                HYDROSTRUCT_file = GDS_dir + r"/HYDROSTRUCT.OUT"
                # Check if there is an HYDROSTRUCT.OUT file on the export folder
                if not os.path.isfile(HYDROSTRUCT_file):
                    self.uc.bar_warn(
                        "No HYDROSTRUCT.OUT file found. Please ensure the simulation has completed and verify the project export folder.")
                    self.uc.log_info(
                        "No HYDROSTRUCT.OUT file found. Please ensure the simulation has completed and verify the project export folder.")
                    return
            # Check if the HYDROSTRUCT.OUT has data on it
            if os.path.getsize(HYDROSTRUCT_file) == 0:
                QApplication.restoreOverrideCursor()
                self.uc.bar_warn("File  '" + os.path.basename(HYDROSTRUCT_file) + "'  is empty!")
                self.uc.log_info("File  '" + os.path.basename(HYDROSTRUCT_file) + "'  is empty!")
                return

            with open(HYDROSTRUCT_file, "r") as myfile:
                time_list = []
                discharge_list = []
                pattern = r"THE MAXIMUM DISCHARGE FOR:\s+(\S+)\s+STRUCTURE\s+NO\.\s+(\d+)\s+IS:"
                structure_name = None
                while True:
                    try:
                        line = next(myfile)
                        match = re.search(pattern, line)
                        if match:
                            matched_structure_name = match.group(1)
                            if matched_structure_name == struct_name:
                                structure_name = matched_structure_name
                                line = next(myfile)
                                while True:
                                    line = next(myfile)
                                    if not line.strip():  # If the line is empty, exit the loop
                                        break
                                    line = line.split()
                                    time_list.append(float(line[0]))
                                    discharge_list.append(float(line[1]))
                                break
                    except StopIteration:
                        break

            self.plot.clear()
            if self.plot.plot.legend is not None:
                plot_scene = self.plot.plot.legend.scene()
                if plot_scene is not None:
                    plot_scene.removeItem(self.plot.plot.legend)

            self.plot.plot.legend = None
            self.plot.plot.addLegend(offset=(0, 30))
            self.plot.plot.setTitle(title=f"Hydraulic Structure: {structure_name}")
            self.plot.plot.setLabel("bottom", text="Time (hrs)")
            self.plot.plot.setLabel("left", text="")
            self.plot.add_item(f"Discharge ({self.system_units[units][2]})", [time_list, discharge_list], col=QColor(Qt.darkYellow), sty=Qt.SolidLine)

            try:  # Build table.
                discharge_data_model = StandardItemModel()
                self.tview.undoStack.clear()
                self.tview.setModel(discharge_data_model)
                discharge_data_model.clear()
                headers = ["Time (hours)", f"Discharge ({self.system_units[units][2]})"]
                discharge_data_model.setHorizontalHeaderLabels(headers)

                data = zip(time_list, discharge_list)
                for row, (time, discharge) in enumerate(data):
                    time_item = StandardItem("{:.2f}".format(time)) if time is not None else StandardItem("")
                    discharge_item = StandardItem("{:.2f}".format(discharge)) if discharge is not None else StandardItem("")
                    discharge_data_model.setItem(row, 0, time_item)
                    discharge_data_model.setItem(row, 1, discharge_item)

                self.tview.horizontalHeader().setStretchLastSection(True)
                for col in range(3):
                    self.tview.setColumnWidth(col, 100)
                for i in range(discharge_data_model.rowCount()):
                    self.tview.setRowHeight(i, 20)
            except:
                QApplication.restoreOverrideCursor()
                self.uc.bar_warn("Error while building table for hydraulic structure discharge!")
                self.uc.log_info("Error while building table for hydraulic structure discharge!")
                return

        # use_prs = s.value("FLO-2D/use_prs", "")
        # if use_prs:
        #     scenario1 = s.value("FLO-2D/scenario1") + r"/HYDROSTRUCT.OUT" if s.value("FLO-2D/scenario1") != "" else None
        #     scenario2 = s.value("FLO-2D/scenario2") + r"/HYDROSTRUCT.OUT" if s.value("FLO-2D/scenario2") != "" else None
        #     scenario3 = s.value("FLO-2D/scenario3") + r"/HYDROSTRUCT.OUT" if s.value("FLO-2D/scenario3") != "" else None
        #     scenario4 = s.value("FLO-2D/scenario4") + r"/HYDROSTRUCT.OUT" if s.value("FLO-2D/scenario4") != "" else None
        #     scenario5 = s.value("FLO-2D/scenario5") + r"/HYDROSTRUCT.OUT" if s.value("FLO-2D/scenario5") != "" else None
        #     scenarios = [scenario1, scenario2, scenario3, scenario4, scenario5]
        #     j = 1
        #     for scenario in scenarios:
        #         if scenario:
        #             with open(scenario, "r") as myfile:
        #                 time_list = []
        #                 discharge_list = []
        #                 pattern = r'THE MAXIMUM DISCHARGE FOR:\s+(\w+)\s+STRUCTURE\sNO.\s+(\d+)\s+IS:'
        #                 structure_name = None
        #                 while True:
        #                     try:
        #                         line = next(myfile)
        #                         match = re.search(pattern, line)
        #                         if match:
        #                             matched_structure_name = match.group(1)
        #                             matched_structure_number = int(match.group(2))
        #                             if matched_structure_number == fid:
        #                                 structure_name = matched_structure_name
        #                                 line = next(myfile)
        #                                 while True:
        #                                     line = next(myfile)
        #                                     if not line.strip():  # If the line is empty, exit the loop
        #                                         break
        #                                     line = line.split()
        #                                     time_list.append(float(line[0]))
        #                                     discharge_list.append(float(line[1]))
        #                                 break
        #                     except StopIteration:
        #                         break
        #
        #             if j == 1:
        #                 color = Qt.yellow
        #             if j == 2:
        #                 color = Qt.darkGreen
        #             if j == 3:
        #                 color = Qt.green
        #             if j == 4:
        #                 color = Qt.darkBlue
        #             if j == 5:
        #                 color = Qt.blue
        #             self.plot.add_item(f"Discharge ({self.system_units[units][2]}) - Scenario {j}", [time_list, discharge_list],
        #                                col=QColor(color), sty=Qt.SolidLine)
        #
        #             headers.extend([f"Discharge ({self.system_units[units][2]}) - Scenario {j}"])
        #             discharge_data_model.setHorizontalHeaderLabels(headers)
        #
        #             new_column_index = discharge_data_model.columnCount() - 1
        #             data = zip(time_list, discharge_list)
        #             for row, (_, discharge) in enumerate(data):
        #                 discharge_item = StandardItem(
        #                     "{:.2f}".format(discharge)) if discharge is not None else StandardItem("")
        #                 discharge_data_model.setItem(row, new_column_index, discharge_item)
        #
        #
        #         j += 1

