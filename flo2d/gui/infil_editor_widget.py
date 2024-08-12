# -*- coding: utf-8 -*-
# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import traceback
from collections import OrderedDict
from itertools import chain
from math import isnan

from PyQt5.QtCore import QVariant, QUrl
from PyQt5.QtWidgets import QFileDialog
from qgis._core import QgsField, QgsVectorLayer, QgsRasterLayer, QgsProcessing, QgsLayerTreeRegistryBridge, \
    QgsLayerTreeLayer, QgsMapLayer, QgsVectorFileWriter
from qgis.core import QgsFeatureRequest, QgsWkbTypes, QgsProject
from qgis.PyQt.QtCore import QSettings, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QDesktopServices
from qgis.PyQt.QtGui import QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import (QApplication, QCheckBox, QDoubleSpinBox,
                                 QInputDialog, QSpinBox, QProgressDialog,
                                 QMessageBox)

from ..flo2d_tools.grid_tools import poly2grid, poly2poly_geos
from ..flo2d_tools.infiltration_tools import InfiltrationCalculator
from ..geopackage_utils import GeoPackageUtils

from ..user_communication import UserCommunication
from ..utils import m_fdata
from .ui_utils import center_canvas, load_ui, set_icon, switch_to_selected

from ..misc.ssurgo_soils import SsurgoSoil
from ..misc import osm_landuse

import processing
import os

uiDialog, qtBaseClass = load_ui("infil_editor")


class InfilEditorWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None
        self.grid_lyr = None
        self.infil_lyr = None
        self.eff_lyr = None
        self.infil_idx = 0
        self.iglobal = InfilGlobal(self.iface, self.lyrs)
        self.infmethod = self.iglobal.global_imethod
        self.groups = set()
        self.params = [
            "infmethod",
            "abstr",
            "sati",
            "satf",
            "poros",
            "soild",
            "infchan",
            "hydcall",
            "soilall",
            "hydcadj",
            "hydcxx",
            "scsnall",
            "abstr1",
            "fhortoni",
            "fhortonf",
            "decaya",
            "fhortonia"
        ]
        self.infil_columns = [
            "green_char",
            "hydc",
            "soils",
            "dtheta",
            "abstrinf",
            "rtimpf",
            "soil_depth",
            "hydconch",
            "scsn",
            "fhorti",
            "fhortf",
            "deca",
            "fhortia"
        ]
        self.imethod_groups = {
            1: {self.iglobal.green_grp},
            2: {self.iglobal.scs_grp},
            3: {self.iglobal.green_grp, self.iglobal.scs_grp},
            4: {self.iglobal.horton_grp},
        }

        self.single_groups = {
            1: {self.single_green_grp},
            2: {self.single_scs_grp},
            3: {self.single_green_grp, self.single_scs_grp},
            4: {self.single_horton_grp},
        }
        self.slices = {1: slice(0, 8), 2: slice(8, 9), 3: slice(0, 9), 4: slice(9, 12)}
        set_icon(self.create_polygon_btn, "mActionCapturePolygon.svg")
        set_icon(self.save_changes_btn, "mActionSaveAllEdits.svg")
        set_icon(self.schema_btn, "schematize_res.svg")
        set_icon(self.revert_changes_btn, "mActionUndo.svg")
        set_icon(self.delete_btn, "mActionDeleteSelected.svg")
        set_icon(self.change_name_btn, "change_name.svg")
        self.create_polygon_btn.clicked.connect(self.create_infil_polygon)
        self.save_changes_btn.clicked.connect(self.save_infil_edits)
        self.revert_changes_btn.clicked.connect(self.revert_infil_lyr_edits)
        self.delete_btn.clicked.connect(self.delete_cur_infil)
        self.change_name_btn.clicked.connect(self.rename_infil)
        self.schema_btn.clicked.connect(self.schematize_infiltration)
        self.infiltration_help_btn.clicked.connect(self.infiltration_help)
        self.global_params.clicked.connect(self.show_global_params)
        self.iglobal.global_changed.connect(self.show_groups)
        self.fplain_grp.toggled.connect(self.floodplain_checked)
        self.chan_grp.toggled.connect(self.channel_checked)
        self.green_ampt_btn.clicked.connect(self.calculate_green_ampt)
        self.scs_btn.clicked.connect(self.calculate_scs)

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
            self.grid_lyr = self.lyrs.data["grid"]["qlyr"]
            self.infil_lyr = self.lyrs.data["user_infiltration"]["qlyr"]
            self.eff_lyr = self.lyrs.data["user_effective_impervious_area"]["qlyr"]
            self.read_global_params()
            self.infil_lyr.editingStopped.connect(self.populate_infiltration)
            self.infil_lyr.selectionChanged.connect(self.switch2selected)
            self.infil_name_cbo.activated.connect(self.infiltration_changed)

    def switch2selected(self):
        switch_to_selected(self.infil_lyr, self.infil_name_cbo)
        self.infiltration_changed()

    def fill_green_char(self):
        qry = """UPDATE user_infiltration SET green_char = 'F' WHERE green_char NOT IN ('C', 'F');"""
        cur = self.con.cursor()
        cur.execute(qry)
        self.con.commit()

    def show_global_params(self):
        self.iglobal.populate_infilglobals()

        ok = self.iglobal.exec_()
        if ok:
            self.iglobal.save_imethod()
            self.write_global_params()
        else:
            self.read_global_params()

    @pyqtSlot(int)
    def show_groups(self, imethod):
        if imethod == 0:
            self.single_green_grp.setHidden(True)
            self.single_scs_grp.setHidden(True)
            self.single_horton_grp.setHidden(True)
        elif imethod == 1:
            self.single_green_grp.setHidden(False)
            self.single_scs_grp.setHidden(True)
            self.single_horton_grp.setHidden(True)
            self.fill_green_char()
        elif imethod == 2:
            self.single_green_grp.setHidden(True)
            self.single_scs_grp.setHidden(False)
            self.single_horton_grp.setHidden(True)
        elif imethod == 3:
            self.single_green_grp.setHidden(False)
            self.single_scs_grp.setHidden(False)
            self.single_horton_grp.setHidden(True)
        elif imethod == 4:
            self.single_green_grp.setHidden(True)
            self.single_scs_grp.setHidden(True)
            self.single_horton_grp.setHidden(False)

        self.infmethod = imethod
        self.populate_infiltration()

    def read_global_params(self):
        try:
            qry = """SELECT {} FROM infil;""".format(",".join(self.params))
            glob = self.gutils.execute(qry).fetchone()
            if glob is None:
                self.show_groups(0)
                return
            row = OrderedDict(list(zip(self.params, glob)))
            try:
                method = row["infmethod"]
                self.groups = self.imethod_groups[method]
            except KeyError:
                self.groups = set()
            for grp in self.groups:
                grp.setChecked(True)
                for obj in grp.children():
                    if not isinstance(obj, (QDoubleSpinBox, QCheckBox)):
                        continue
                    obj_name = obj.objectName()
                    name = obj_name.split("_", 1)[-1]
                    val = row[name]
                    if val is None:
                        continue
                    if isinstance(obj, QCheckBox):
                        obj.setChecked(bool(val))
                    else:
                        obj.setValue(val)
            self.iglobal.save_imethod()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 110618.1818: Could not read infiltration global parameters!", e)

    def write_global_params(self):
        qry = """INSERT INTO infil ({0}) VALUES ({1});"""
        method = self.iglobal.global_imethod
        names = ["infmethod"]
        vals = [method]
        try:
            self.groups = self.imethod_groups[method]
        except KeyError:
            self.groups = set()
        for grp in self.groups:
            for obj in grp.children():
                if not isinstance(obj, (QSpinBox, QDoubleSpinBox, QCheckBox)):
                    continue
                obj_name = obj.objectName()
                name = obj_name.split("_", 1)[-1]
                if isinstance(obj, QCheckBox):
                    val = int(obj.isChecked())
                    obj.setChecked(bool(val))
                else:
                    val = obj.value()
                    obj.setValue(val)
                names.append(name)
                vals.append(val)
        self.gutils.clear_tables("infil")
        names_str = ", ".join(names)
        vals_str = ", ".join(["?"] * len(vals))
        qry = qry.format(names_str, vals_str)
        self.gutils.execute(qry, vals)

    def floodplain_checked(self):
        if self.fplain_grp.isChecked():
            if self.chan_grp.isChecked():
                self.chan_grp.setChecked(False)

    def channel_checked(self):
        if self.chan_grp.isChecked():
            if self.fplain_grp.isChecked():
                self.fplain_grp.setChecked(False)

    def create_infil_polygon(self):
        if self.iglobal.global_imethod == 0:
            self.uc.bar_warn("Please define global infiltration method first!")
            self.uc.log_info("Please define global infiltration method first!")
            return
        if not self.lyrs.enter_edit_mode("user_infiltration"):
            return

    def rename_infil(self):
        if self.iglobal.global_imethod == 0:
            self.uc.bar_warn("Please define global infiltration method first!")
            self.uc.log_info("Please define global infiltration method first!")
            return
        if not self.infil_name_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, "Change name", "New name:")
        if not ok or not new_name:
            return
        if not self.infil_name_cbo.findText(new_name) == -1:
            msg = "WARNING 060319.1723: Infiltration with name {} already exists in the database. Please, choose another name."
            msg = msg.format(new_name)
            self.uc.show_warn(msg)
            self.uc.log_info(msg)
            return
        self.infil_name_cbo.setItemText(self.infil_name_cbo.currentIndex(), new_name)
        self.save_infil_edits()

    def revert_infil_lyr_edits(self):
        if self.iglobal.global_imethod == 0:
            self.uc.bar_warn("Please define global infiltration parameters first!")
            self.uc.log_info("Please define global infiltration parameters first!")
            return
        user_infil_edited = self.lyrs.rollback_lyrs_edits("user_infiltration")
        if user_infil_edited:
            self.populate_infiltration()

    def delete_cur_infil(self):
        if self.iglobal.global_imethod == 0:
            self.uc.bar_warn("Please define global infiltration method first!")
            self.uc.log_info("Please define global infiltration method first!")
            return
        if not self.infil_name_cbo.count():
            return
        q = "Are you sure, you want delete the current infiltration?"
        if not self.uc.question(q):
            return
        infil_fid = self.infil_name_cbo.itemData(self.infil_idx)["fid"]
        self.gutils.execute("DELETE FROM user_infiltration WHERE fid = ?;", (infil_fid,))
        self.populate_infiltration()

    def save_infil_edits(self):
        before = self.gutils.count("user_infiltration")
        self.lyrs.save_lyrs_edits("user_infiltration")
        after = self.gutils.count("user_infiltration")
        if after > before:
            self.infil_idx = after - 1
        elif self.infil_idx >= 0:
            self.save_attrs()
        else:
            return
        self.populate_infiltration()

    def save_attrs(self):
        if self.iglobal.global_imethod == 0:
            self.uc.bar_warn("Please define global infiltration method first!")
            self.uc.log_info("Please define global infiltration method first!")
            return
        infil_dict = self.infil_name_cbo.itemData(self.infil_idx)
        fid = infil_dict["fid"]
        name = self.infil_name_cbo.currentText()

        for grp in self.single_groups[self.infmethod]:
            grp_name = grp.objectName()
            if grp_name == "single_green_grp":
                if self.fplain_grp.isChecked():
                    infil_dict["green_char"] = "F"
                    grp = self.fplain_grp
                elif self.chan_grp.isChecked():
                    infil_dict["green_char"] = "C"
                    grp = self.chan_grp
                else:
                    if self.infmethod == 3:
                        infil_dict["green_char"] = ""
                    else:
                        infil_dict["green_char"] = "F"
                        grp = self.fplain_grp
            for obj in grp.children():
                obj_name = obj.objectName().split("_", 1)[-1]
                if isinstance(obj, QDoubleSpinBox) or isinstance(obj, QSpinBox):
                    infil_dict[obj_name] = obj.value()
                else:
                    continue

        col_gen = ("{}=?".format(c) for c in list(infil_dict.keys())[1:])
        col_names = ", ".join(col_gen)
        vals = [name] + list(infil_dict.values())[2:] + [fid]
        update_qry = """UPDATE user_infiltration SET {0} WHERE fid = ?;""".format(col_names)
        self.gutils.execute(update_qry, vals)

    def populate_infiltration(self):
        self.infil_name_cbo.clear()
        imethod = self.infmethod
        if imethod == 0:
            return
        sl = self.slices[imethod]
        columns = self.infil_columns[sl]
        qry = """SELECT fid, name, {0} FROM user_infiltration ORDER BY fid;"""
        qry = qry.format(", ".join(columns))
        columns = ["fid", "name"] + columns
        rows = self.gutils.execute(qry).fetchall()
        for row in rows:
            infil_dict = OrderedDict(list(zip(columns, row)))
            name = infil_dict["name"]
            self.infil_name_cbo.addItem(name, infil_dict)
        self.infil_name_cbo.setCurrentIndex(self.infil_idx)
        self.infiltration_changed()

    def infiltration_changed(self):
        imethod = self.infmethod
        self.infil_idx = self.infil_name_cbo.currentIndex()
        infil_dict = self.infil_name_cbo.itemData(self.infil_idx)
        if not infil_dict:
            return
        for grp in self.single_groups[imethod]:
            grp_name = grp.objectName()
            if grp_name == "single_green_grp":
                green_char = infil_dict["green_char"]
                if green_char == "F":
                    self.fplain_grp.setChecked(True)
                    grp = self.fplain_grp
                elif green_char == "C":
                    self.chan_grp.setChecked(True)
                    grp = self.chan_grp
                else:
                    if imethod == 3:
                        self.fplain_grp.setChecked(False)
                        self.chan_grp.setChecked(False)
                    else:
                        self.fplain_grp.setChecked(True)
                        grp = self.fplain_grp
            for obj in grp.children():
                if isinstance(obj, QDoubleSpinBox) or isinstance(obj, QSpinBox):
                    obj_name = obj.objectName().split("_", 1)[-1]
                    obj.setValue(infil_dict[obj_name])
                else:
                    continue
        self.lyrs.clear_rubber()
        if self.infil_center_btn.isChecked():
            ifid = infil_dict["fid"]
            self.lyrs.show_feat_rubber(self.infil_lyr.id(), ifid)
            feat = next(self.infil_lyr.getFeatures(QgsFeatureRequest(ifid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def schematize_infiltration(self):
        if self.iglobal.global_imethod == 0:
            self.uc.bar_warn("Please define global infiltration method first!")
            self.uc.log_info("Please define global infiltration method first!")
            return
        qry_green = """INSERT INTO infil_cells_green (grid_fid, hydc, soils, dtheta, abstrinf, rtimpf, soil_depth) VALUES (?,?,?,?,?,?,?);"""
        qry_chan = """INSERT INTO infil_chan_elems (grid_fid, hydconch) VALUES (?,?);"""
        qry_scs = """INSERT INTO infil_cells_scs (grid_fid, scsn) VALUES (?,?);"""
        qry_horton = """INSERT INTO infil_cells_horton (grid_fid, fhorti, fhortf, deca) VALUES (?,?,?,?);"""

        imethod = self.infmethod
        if imethod == 0:
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.gutils.disable_geom_triggers()
            sl = self.slices[imethod]
            columns = self.infil_columns[sl]
            cellSize = float(self.gutils.get_cont_par("CELLSIZE"))
            infiltration_grids = list(
                poly2grid(cellSize, self.grid_lyr, self.infil_lyr, None, True, False, False, 1, *columns))
            self.gutils.clear_tables(
                "infil_cells_green",
                "infil_cells_scs",
                "infil_cells_horton",
                "infil_chan_elems",
            )
            if imethod == 1 or imethod == 3:
                green_vals, chan_area_vals, scs_vals, chan_vals = [], [], [], []
                chan_fid, scs_fid = 1, 1
                for grid_row in infiltration_grids:
                    row = list(grid_row)
                    gid = row.pop()
                    char = row.pop(0)
                    geom = self.gutils.grid_geom(gid)
                    if char == "F":
                        val = (gid,) + tuple(row[:6])
                        green_vals.append(val)
                    elif char == "C":
                        val = (gid, row[6])
                        chan_vals.append(val)
                        chan_fid += 1
                    else:
                        val = (gid, row[7])
                        scs_vals.append(val)
                        scs_fid += 1
                cur = self.con.cursor()
                cur.executemany(qry_green, green_vals)
                cur.executemany(qry_chan, chan_vals)
                cur.executemany(qry_scs, scs_vals)
            else:
                if imethod == 2:
                    qry_cells = qry_scs
                else:
                    qry_cells = qry_horton
                cells_vals = []
                for i, grid_row in enumerate(infiltration_grids, 1):
                    row = list(grid_row)
                    gid = row.pop()
                    val = (gid,) + tuple(row)
                    cells_vals.append(val)
                cur = self.con.cursor()
                cur.executemany(qry_cells, cells_vals)
            self.con.commit()
            self.gutils.enable_geom_triggers()
            QApplication.restoreOverrideCursor()
            self.uc.bar_info("Schematizing of infiltration finished!")
            self.uc.log_info("Schematizing of infiltration finished!")
        except Exception as e:
            self.gutils.enable_geom_triggers()
            self.uc.log_info(traceback.format_exc())
            QApplication.restoreOverrideCursor()
            self.uc.bar_error("Schematizing of infiltration failed! Please check user infiltration layers.")
            self.uc.log_info("Schematizing of infiltration failed! Please check user infiltration layers.")
            self.uc.show_error(
                "ERROR 271118.1638: error schematizing infiltration!."
                + "\n__________________________________________________",
                e,
            )

    def infiltration_help(self):
        QDesktopServices.openUrl(QUrl("https://flo-2dsoftware.github.io/FLO-2D-Documentation/Plugin1000/widgets/infiltration-editor/index.html"))        

    def calculate_green_ampt(self):
        dlg = GreenAmptDialog(self.iface, self.lyrs)
        ok = dlg.exec_()
        if not ok:
            return
        try:
            dlg.save_green_ampt_shapefile_fields()
            self.gutils.disable_geom_triggers()
            (
                soil_lyr,
                land_lyr,
                fields,
                vc_check,
                log_area_average,
            ) = dlg.green_ampt_parameters()

            inf_calc = InfiltrationCalculator(self.grid_lyr, self.iface, self.gutils)
            inf_calc.setup_green_ampt(soil_lyr, land_lyr, vc_check, log_area_average, *fields)
            grid_params = inf_calc.green_ampt_infiltration()

            if grid_params:
                # apply effective impervious area layer
                if self.eff_lyr is not None:
                    eff_values = poly2poly_geos(self.grid_lyr, self.eff_lyr, None, "eff")
                    try:
                        for gid, values in eff_values:
                            fact = 1 - sum((1 - row[0] * 0.01) * row[-1] for row in values)
                            grid_params[gid]["rtimpf"] *= fact
                    except Exception:
                        pass

                self.gutils.clear_tables("infil_cells_green")
                qry_cells = """INSERT INTO infil_cells_green (grid_fid, hydc, soils, dtheta, abstrinf, rtimpf, soil_depth) VALUES (?,?,?,?,?,?,?);"""
                cells_values = []
                non_intercepted = []
                for i, (gid, params) in enumerate(grid_params.items(), 1):
                    if "dtheta" not in params:
                        non_intercepted.append(gid)
                        params["dtheta"] = 0.3
                        params["abstrinf"] = 0.1
                    par = (
                        params["hydc"],
                        params["soils"],
                        params["dtheta"],
                        params["abstrinf"],
                        params["rtimpf"],
                        params["soil_depth"],
                    )
                    values = (gid,) + tuple(round(p, 3) for p in par)
                    cells_values.append(values)
                cur = self.con.cursor()
                cur.executemany(qry_cells, cells_values)
                self.con.commit()
                self.gutils.enable_geom_triggers()
                QApplication.restoreOverrideCursor()

                if non_intercepted:
                    no_inter = ""
                    for nope in non_intercepted:
                        no_inter += "\n" + str(nope)
                    QApplication.restoreOverrideCursor()
                    self.uc.show_info(
                        "WARNING 150119.0354: Calculating Green-Ampt parameters finished, but \n"
                        + str(len(non_intercepted))
                        + " cells didn´t intercept the land use shapefile.\n"
                        + "Default values were assigned for the infiltration.\n"
                        + no_inter
                    )
                else:
                    self.uc.show_info("Calculating Green-Ampt parameters finished!")

            else:
                QApplication.restoreOverrideCursor()
                self.uc.show_critical(
                    "ERROR 061218.1839: Green-Ampt infiltration failed!. Please check data in your input layers."
                )

        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_error(
                "ERROR 051218.1839: Green-Ampt infiltration failed!. Please check data in your input layers."
                + "\n__________________________________________________",
                e,
            )
        finally:
            self.gutils.enable_geom_triggers()
            QApplication.restoreOverrideCursor()

    def calculate_scs(self):
        dlg = SCSDialog(self.iface, self.lyrs)
        ok = dlg.exec_()
        if not ok:
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.gutils.disable_geom_triggers()
            inf_calc = InfiltrationCalculator(self.grid_lyr, self.iface, self.gutils)
            if dlg.single_grp.isChecked():
                single_lyr, single_fields = dlg.single_scs_parameters()
                inf_calc.setup_scs_single(single_lyr, *single_fields)
                grid_params = inf_calc.scs_infiltration_single()
            elif dlg.raster_grp.isChecked():
                raster_lyr, algorithm, nodatavalue, fillnodata, multithread = dlg.raster_scs_parameters()
                inf_calc.setup_scs_raster(raster_lyr, algorithm, nodatavalue, fillnodata, multithread)
                grid_params = inf_calc.scs_infiltration_raster()
            else:
                multi_lyr, multi_fields = dlg.multi_scs_parameters()
                inf_calc.setup_scs_multi(multi_lyr, *multi_fields)
                grid_params = inf_calc.scs_infiltration_multi()
            self.gutils.clear_tables("infil_cells_scs")
            qry = """INSERT INTO infil_cells_scs (grid_fid, scsn) VALUES (?,?);"""
            values = []
            for i, (gid, params) in enumerate(grid_params.items(), 1):
                val = (gid, params["scsn"])
                values.append(val)
            cur = self.con.cursor()
            cur.executemany(qry, values)
            self.con.commit()
            self.gutils.enable_geom_triggers()
            QApplication.restoreOverrideCursor()
            self.uc.show_info("Calculating SCS Curve Number parameters finished!")
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            QApplication.restoreOverrideCursor()
            self.uc.show_warn(
                "WARNING 060319.1724: Calculating SCS Curve Number parameters failed! Please check data in your input layers."
            )

        finally:
            self.gutils.enable_geom_triggers()


uiDialog_glob, qtBaseClass_glob = load_ui("infil_global")


class InfilGlobal(uiDialog_glob, qtBaseClass_glob):
    global_changed = pyqtSignal(int)

    def __init__(self, iface, lyrs):
        qtBaseClass_glob.__init__(self)
        uiDialog_glob.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.con = self.iface.f2d["con"]
        self.gutils = GeoPackageUtils(self.con, self.iface)
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.chan_dlg = ChannelDialog(self.iface, self.lyrs)
        self.global_imethod = 0
        self.current_imethod = 0
        self.green_grp.toggled.connect(self.green_checked)
        self.scs_grp.toggled.connect(self.scs_checked)
        self.horton_grp.toggled.connect(self.horton_checked)
        self.cb_infchan.stateChanged.connect(self.infchan_changed)
        self.chan_btn.clicked.connect(self.show_channel_dialog)

        self.populate_infilglobals()

    def populate_infilglobals(self):
        qry = """SELECT infmethod, abstr, sati, satf, poros, soild, infchan, hydcall, soilall,
                hydcadj, hydcxx, scsnall, abstr1, fhortoni, fhortonf, decaya, fhortonia FROM infil"""

        try:
            infil_glob = self.gutils.execute(qry).fetchone()

            if infil_glob:
                self.spin_abstr.setValue(infil_glob[1] if infil_glob[1] is not None else 0.0)
                self.spin_sati.setValue(infil_glob[2] if infil_glob[2] is not None else 0.7)
                self.spin_satf.setValue(infil_glob[3] if infil_glob[3] is not None else 1.0)
                self.spin_poros.setValue(infil_glob[4] if infil_glob[4] is not None else 0.0)
                self.spin_soild.setValue(infil_glob[5] if infil_glob[5] is not None else 10.0)
                self.cb_infchan.setChecked(infil_glob[6] if infil_glob[6] is not None else 0)
                self.spin_hydcall.setValue(infil_glob[7] if infil_glob[7] is not None else 0.1)
                self.spin_soilall.setValue(infil_glob[8] if infil_glob[8] is not None else 4.3)
                self.spin_hydcadj.setValue(infil_glob[9] if infil_glob[9] is not None else 0.0)
                self.spin_hydcxx.setValue(infil_glob[10] if infil_glob[10] is not None else 0.1)
                self.spin_scsnall.setValue(int(infil_glob[11]) if infil_glob[11] is not None else 99)
                self.spin_abstr1.setValue(infil_glob[12] if infil_glob[12] is not None else 0.0)
                self.spin_fhortoni.setValue(infil_glob[13] if infil_glob[13] is not None else 0.0)
                self.spin_fhortonf.setValue(infil_glob[14] if infil_glob[14] is not None else 0.0)
                self.spin_decaya.setValue(infil_glob[15] if infil_glob[15] is not None else 0.0)
                self.spin_fhortonia.setValue(infil_glob[16] if infil_glob[16] is not None else 0.0)
            else:
                self.spin_abstr.setValue(0.0)
                self.spin_sati.setValue(0.7)
                self.spin_satf.setValue(1.0)
                self.spin_poros.setValue(0.0)
                self.spin_soild.setValue(10.0)
                self.cb_infchan.setChecked(0)
                self.spin_hydcall.setValue(0.1)
                self.spin_soilall.setValue(4.3)
                self.spin_hydcadj.setValue(0.0)
                self.spin_hydcxx.setValue(0.1)
                self.spin_scsnall.setValue(99)
                self.spin_abstr1.setValue(0.0)
                self.spin_fhortoni.setValue(0.0)
                self.spin_fhortonf.setValue(0.0)
                self.spin_decaya.setValue(0.0)
                self.spin_fhortonia.setValue(0.0)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_warn("ERROR 280320.1625: load of infiltration globals failed!")
            self.uc.log_info("ERROR 280320.1625: load of infiltration globals failed!")

    def show_channel_dialog(self):
        hydcxx = self.spin_hydcxx.value()
        self.chan_dlg.set_chan_model(hydcxx)
        ok = self.chan_dlg.exec_()
        if not ok:
            return
        self.chan_dlg.save_channel_params()

    def save_imethod(self):
        self.global_imethod = self.current_imethod
        self.global_changed.emit(self.global_imethod)

    def green_checked(self):
        if self.green_grp.isChecked():
            if self.horton_grp.isChecked():
                self.horton_grp.setChecked(False)
            if self.scs_grp.isChecked():
                self.current_imethod = 3
            else:
                self.current_imethod = 1
        else:
            if self.scs_grp.isChecked():
                self.current_imethod = 2
            else:
                self.current_imethod = 0

    def scs_checked(self):
        if self.scs_grp.isChecked():
            if self.horton_grp.isChecked():
                self.horton_grp.setChecked(False)
            if self.green_grp.isChecked():
                self.current_imethod = 3
            else:
                self.current_imethod = 2
        else:
            if self.green_grp.isChecked():
                self.current_imethod = 1
            else:
                self.current_imethod = 0

    def horton_checked(self):
        if self.horton_grp.isChecked():
            if self.green_grp.isChecked():
                self.green_grp.setChecked(False)
            if self.scs_grp.isChecked():
                self.scs_grp.setChecked(False)
            self.current_imethod = 4
        else:
            self.current_imethod = 0

    def infchan_changed(self):
        if self.cb_infchan.isChecked():
            self.label_hydcxx.setEnabled(True)
            self.spin_hydcxx.setEnabled(True)
            self.chan_btn.setEnabled(True)
        else:
            self.label_hydcxx.setDisabled(True)
            self.spin_hydcxx.setDisabled(True)
            self.chan_btn.setDisabled(True)


uiDialog_chan, qtBaseClass_chan = load_ui("infil_chan")


class ChannelDialog(uiDialog_chan, qtBaseClass_chan):
    def __init__(self, iface, lyrs):
        qtBaseClass_chan.__init__(self)
        uiDialog_chan.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.con = self.iface.f2d["con"]
        self.gutils = GeoPackageUtils(self.con, self.iface)
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        model = QStandardItemModel()
        self.tview.setModel(model)

    def set_chan_model(self, hydcxx):
        str_hydcxx = str(hydcxx)
        qry = """
        SELECT c.name, c.fid, i.hydcx, i.hydcxfinal, i.soildepthcx
        FROM chan AS c
        LEFT OUTER JOIN infil_chan_seg AS i
        ON c.fid = i.chan_seg_fid;"""
        headers = [
            "Channel Name",
            "Channel FID",
            "Initial hyd. cond.",
            "Final hyd. cond.",
            "Max. Soil Depth",
        ]
        tab_data = self.con.execute(qry).fetchall()
        model = QStandardItemModel()
        for i, head in enumerate(headers):
            model.setHorizontalHeaderItem(i, QStandardItem(head))
        for row in tab_data:
            model_row = []
            for i, col in enumerate(row):
                if col is None:
                    str_col = str_hydcxx if i == 2 else ""
                else:
                    str_col = str(col)
                item = QStandardItem(str_col)
                if i < 2:
                    item.setEditable(False)
                model_row.append(item)
            model.appendRow(model_row)
        self.tview.setModel(model)

    def save_channel_params(self):
        qry = "INSERT INTO infil_chan_seg (chan_seg_fid, hydcx, hydcxfinal, soildepthcx) VALUES (?,?,?,?);"
        data_model = self.tview.model()
        data_rows = []
        for i in range(data_model.rowCount()):
            row = [m_fdata(data_model, i, j) for j in range(1, 5)]
            row = ["" if isnan(r) else r for r in row]
            data_rows.append(row)
        if data_rows:
            self.gutils.clear_tables("infil_chan_seg")
            cur = self.con.cursor()
            cur.executemany(qry, data_rows)
            self.con.commit()


uiDialog_green, qtBaseClass_green = load_ui("infil_green_ampt")


class GreenAmptDialog(uiDialog_green, qtBaseClass_green):
    def __init__(self, iface, lyrs):
        qtBaseClass_green.__init__(self)
        uiDialog_green.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.grid_lyr = self.lyrs.data["grid"]["qlyr"]
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.rb_NRCS = self.rb_NRCS
        self.soil_combos = [
            self.xksat_cbo,
            self.rtimps_cbo,
            self.soil_depth_cbo,
            self.dthetan_cbo,
            self.dthetad_cbo,
            self.psif_cbo,
        ]
        self.land_combos = [
            self.saturation_cbo,
            self.vc_cbo,
            self.ia_cbo,
            self.rtimpl_cbo,
        ]

        self.soil_cbo.currentIndexChanged.connect(self.populate_soil_fields)
        self.land_cbo.currentIndexChanged.connect(self.populate_land_fields)

        self.setup_layer_combos()
        self.restore_green_ampt_shapefile_fields()

        self.calculateJE_btn.clicked.connect(self.calculate_ssurgo)
        self.lu_osm_btn.clicked.connect(self.calculate_osm)

    def setup_layer_combos(self):
        """
        Filter layer and fields combo boxes for polygons and connect fields cbo.
        """
        self.soil_cbo.clear()
        self.land_cbo.clear()
        try:
            lyrs = self.lyrs.list_group_vlayers()
            for l in lyrs:
                if l.geometryType() == QgsWkbTypes.PolygonGeometry:
                    l.reload()
                    if l.featureCount() > 0:
                        lyr_name = l.name()
                        self.soil_cbo.addItem(lyr_name, l)
                        self.land_cbo.addItem(lyr_name, l)
        except Exception as e:
            pass

        s = QSettings()
        previous = "" if s.value("ga_soil_layer_name") is None else s.value("ga_soil_layer_name")
        idx = self.soil_cbo.findText(previous)
        if idx != -1:
            self.soil_cbo.setCurrentIndex(idx)

        previous = "" if s.value("ga_land_layer_name") is None else s.value("ga_land_layer_name")
        idx = self.land_cbo.findText(previous)
        if idx != -1:
            self.land_cbo.setCurrentIndex(idx)

    def populate_soil_fields(self, idx):
        lyr = self.soil_cbo.itemData(idx)
        fields = [f.name() for f in lyr.fields()]

        for c in self.soil_combos:
            c.clear()
            c.addItems(fields)

    def populate_land_fields(self, idx):
        lyr = self.land_cbo.itemData(idx)
        fields = [f.name() for f in lyr.fields()]
        for c in self.land_combos:
            c.clear()
            c.addItems(fields)

    def green_ampt_parameters(self):
        sidx = self.soil_cbo.currentIndex()
        soil_lyr = self.soil_cbo.itemData(sidx)
        lidx = self.land_cbo.currentIndex()
        land_lyr = self.land_cbo.itemData(lidx)
        fields = [f.currentText() for f in chain(self.soil_combos, self.land_combos)]
        vc_check = self.veg_cover_chbox.isChecked()
        log_area_average = self.log_area_average_chbox.isChecked()
        return soil_lyr, land_lyr, fields, vc_check, log_area_average

    def save_green_ampt_shapefile_fields(self):
        s = QSettings()

        s.setValue("ga_soil_layer_name", self.soil_cbo.currentText())
        s.setValue("ga_soil_XKSAT", self.xksat_cbo.currentIndex())
        s.setValue("ga_soil_rtimps", self.rtimps_cbo.currentIndex())
        s.setValue("ga_soil_depth", self.soil_depth_cbo.currentIndex())
        s.setValue("ga_soil_DTHETAn", self.dthetan_cbo.currentIndex())
        s.setValue("ga_soil_DTHETAd", self.dthetad_cbo.currentIndex())
        s.setValue("ga_soil_PSIF", self.psif_cbo.currentIndex())

        s.setValue("ga_land_layer_name", self.land_cbo.currentText())
        s.setValue("ga_land_saturation", self.saturation_cbo.currentIndex())
        s.setValue("ga_land_vc", self.vc_cbo.currentIndex())
        s.setValue("ga_land_ia", self.ia_cbo.currentIndex())
        s.setValue("ga_land_rtimpl", self.rtimpl_cbo.currentIndex())

    def restore_green_ampt_shapefile_fields(self):
        s = QSettings()

        name = "" if s.value("ga_soil_layer_name") is None else s.value("ga_soil_layer_name")
        if name == self.soil_cbo.currentText():
            val = int(-1 if s.value("ga_soil_XKSAT") is None else s.value("ga_soil_XKSAT"))
            self.xksat_cbo.setCurrentIndex(val)

            val = int(-1 if s.value("ga_soil_rtimps") is None else s.value("ga_soil_rtimps"))
            self.rtimps_cbo.setCurrentIndex(val)

            val = int(-1 if s.value("ga_soil_depth") is None else s.value("ga_soil_depth"))
            self.soil_depth_cbo.setCurrentIndex(val)

            val = int(-1 if s.value("ga_soil_DTHETAn") is None else s.value("ga_soil_DTHETAn"))
            self.dthetan_cbo.setCurrentIndex(val)

            val = int(-1 if s.value("ga_soil_DTHETAd") is None else s.value("ga_soil_DTHETAd"))
            self.dthetad_cbo.setCurrentIndex(val)

            val = int(-1 if s.value("ga_soil_PSIF") is None else s.value("ga_soil_PSIF"))
            self.psif_cbo.setCurrentIndex(val)

        name = "" if s.value("ga_land_layer_name") is None else s.value("ga_land_layer_name")
        if name == self.land_cbo.currentText():
            val = int(-1 if s.value("ga_land_saturation") is None else s.value("ga_land_saturation"))
            self.saturation_cbo.setCurrentIndex(val)

            val = int(-1 if s.value("ga_land_vc") is None else s.value("ga_land_vc"))
            self.vc_cbo.setCurrentIndex(val)

            val = int(-1 if s.value("ga_land_ia") is None else s.value("ga_land_ia"))
            self.ia_cbo.setCurrentIndex(val)

            val = int(-1 if s.value("ga_land_rtimpl") is None else s.value("ga_land_rtimpl"))
            self.rtimpl_cbo.setCurrentIndex(val)

    def calculate_ssurgo(self):

        # Verify if the user would like to save the intermediate calculation layers
        saveLayers = False
        answer = QMessageBox.question(self.iface.mainWindow(), 'NRCS G&A parameters',
                                      'Save intermediate calculation layers into the geopackage?', QMessageBox.Yes,
                                      QMessageBox.No)
        if answer == QMessageBox.Yes:
            saveLayers = True

        try:
            # Create the progress Dialog
            pd = QProgressDialog("Setting up...", None, 0, 7)
            pd.setWindowTitle("NRCS soil survey database")
            pd.setModal(True)
            pd.forceShow()
            pd.setValue(0)

            ssurgoSoil = SsurgoSoil(self.grid_lyr, self.iface)

            # 1. Set up the ssurgo
            ssurgoSoil.setup_ssurgo(saveLayers)

            # 2. Download Chorizon data
            pd.setLabelText("Downloading chorizon data...")
            ssurgoSoil.downloadChorizon()
            pd.setValue(1)

            # 3. Download Cfrags data
            pd.setLabelText("Downloading chfrags data...")
            ssurgoSoil.downloadChfrags()
            pd.setValue(2)

            # 4. Download Component data
            pd.setLabelText("Downloading component data...")
            ssurgoSoil.downloadComp()
            pd.setValue(3)

            # 5. Join the Tables
            pd.setLabelText("Combining the layers...")
            ssurgoSoil.combineSsurgoLayers()
            pd.setValue(4)

            # 6. Calculate the G&A parameters
            pd.setLabelText("Calculating G&A parameters...")
            ssurgoSoil.calculateGAparameters()
            pd.setValue(5)

            # 7. Fill empty polygons
            pd.setLabelText("Post processing data...")
            ssurgoSoil.postProcess()
            pd.setValue(6)

            # 8. Add to the G&A table
            pd.setLabelText("Writing parameters to G&A table...")
            ssurgo_lyr = ssurgoSoil.soil_lyr()
            self.soil_cbo.insertItem(0, ssurgo_lyr.name(), ssurgo_lyr)
            self.soil_cbo.setCurrentIndex(0)
            self.xksat_cbo.setCurrentIndex(2)
            self.rtimps_cbo.setCurrentIndex(3)
            self.soil_depth_cbo.setCurrentIndex(4)
            self.dthetan_cbo.setCurrentIndex(7)
            self.dthetad_cbo.setCurrentIndex(6)
            self.psif_cbo.setCurrentIndex(5)

            pd.setValue(7)
            pd.close()

            QApplication.restoreOverrideCursor()

        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_error(
                "ERROR: Green-Ampt SSURGO infiltration parameters failed!."
                + "\n__________________________________________________",
                e,
            )

    def calculate_osm(self):

        # Verify if the user would like to save the intermediate calculation layers
        saveLayers = False
        layers = []
        temp_layers = []
        answer = QMessageBox.question(self.iface.mainWindow(), 'OSM land use',
                                      'Save intermediate calculation layers into the geopackage?',
                                      QMessageBox.Yes,
                                      QMessageBox.No)
        if answer == QMessageBox.Yes:
            saveLayers = True

        # Create the progress Dialog
        pd = QProgressDialog("Getting OSM data...", None, 0, 11)
        pd.setWindowTitle("OSM land use")
        pd.setModal(True)
        pd.forceShow()
        pd.setValue(0)

        con = self.iface.f2d["con"]
        if con is not None:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

        try:

            # OSM data
            urlWithParams = 'type=xyz&url=http://a.tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png&zmax=16&zmin=16'
            rlayer = QgsRasterLayer(urlWithParams, 'OpenStreetMap', 'wms')
            # Check if the layer is valid
            if rlayer.isValid():

                # Add it to the canvas because it will export the layer based on the canva's extent
                root_group = QgsProject.instance().layerTreeRoot()
                insertion_point = QgsLayerTreeRegistryBridge.InsertionPoint(root_group, 0)
                QgsProject.instance().layerTreeRegistryBridge().setLayerInsertionPoint(insertion_point)

                QgsProject.instance().addMapLayer(rlayer)

                parameters = {
                    "INPUT": rlayer,
                    "EXTENT": self.grid_lyr.extent(),  # Provide the extent parameter
                    'TILE_SIZE': 64,
                    'MAP_UNITS_PER_PIXEL': 10,
                    "OUTPUT": 'TEMPORARY_OUTPUT'
                }
                proc_output = processing.run("native:rasterize", parameters)

                finalRaster = QgsRasterLayer(proc_output['OUTPUT'], "OSM")
                QgsProject.instance().removeMapLayer(rlayer)
                QgsProject.instance().addMapLayer(finalRaster)
                layers.append(finalRaster)

                # RASTER CALCULATOR starts here
                osm = osm_landuse.OSMLanduse(self.iface)

                # Medium Density Residential
                pd.setLabelText("Finding residential areas...")
                pd.setValue(1)

                residential_1 = QgsRasterLayer(osm.raster_calculator(finalRaster, 224, 223, 223), "RES1")
                QgsProject.instance().addMapLayer(residential_1)
                temp_layers.append(residential_1)
                residential_2 = QgsRasterLayer(osm.raster_calculator(finalRaster, 242, 239, 233), "RES2")
                QgsProject.instance().addMapLayer(residential_2)
                temp_layers.append(residential_2)
                residential_3 = QgsRasterLayer(osm.raster_calculator(finalRaster, 226, 212, 212), "RES3")
                QgsProject.instance().addMapLayer(residential_3)
                temp_layers.append(residential_3)
                school = QgsRasterLayer(osm.raster_calculator(finalRaster, 255, 255, 229), "SCHO")
                QgsProject.instance().addMapLayer(school)
                temp_layers.append(school)
                church = QgsRasterLayer(osm.raster_calculator(finalRaster, 208, 208, 208), "CHUR")
                QgsProject.instance().addMapLayer(church)
                temp_layers.append(church)

                mdr = QgsRasterLayer(osm.landuse_calculator(residential_1,
                                                            [
                                                                residential_1.name(),
                                                                residential_2.name(),
                                                                residential_3.name(),
                                                                school.name(),
                                                                church.name()]
                                                            , 1), "MDR")
                QgsProject.instance().addMapLayer(mdr)
                layers.append(mdr)

                # Commercial
                pd.setLabelText("Finding commercial areas...")
                pd.setValue(2)

                commercial_1 = QgsRasterLayer(osm.raster_calculator(finalRaster, 242, 218, 217), "COM1")
                QgsProject.instance().addMapLayer(commercial_1)
                temp_layers.append(commercial_1)
                commercial_2 = QgsRasterLayer(osm.raster_calculator(finalRaster, 255, 214, 209), "COM2")
                QgsProject.instance().addMapLayer(commercial_2)
                temp_layers.append(commercial_2)
                commercial_3 = QgsRasterLayer(osm.raster_calculator(finalRaster, 243, 227, 221), "COM3")
                QgsProject.instance().addMapLayer(commercial_3)
                temp_layers.append(commercial_3)
                commercial_4 = QgsRasterLayer(osm.raster_calculator(finalRaster, 235, 209, 205), "COM4")
                QgsProject.instance().addMapLayer(commercial_4)
                temp_layers.append(commercial_4)
                commercial_5 = QgsRasterLayer(osm.raster_calculator(finalRaster, 236, 199, 196), "COM5")
                QgsProject.instance().addMapLayer(commercial_5)
                temp_layers.append(commercial_5)

                c = QgsRasterLayer(osm.landuse_calculator(commercial_1,
                                                          [commercial_1.name(),
                                                           commercial_2.name(),
                                                           commercial_3.name(),
                                                           commercial_4.name(),
                                                           commercial_5.name()],
                                                          2), "C")
                QgsProject.instance().addMapLayer(c)
                layers.append(c)

                # Lawns/Parks/Cemeteries
                pd.setLabelText("Finding green areas...")
                pd.setValue(3)

                park = QgsRasterLayer(osm.raster_calculator(finalRaster, 200, 250, 204), "PARK")
                QgsProject.instance().addMapLayer(park)
                temp_layers.append(park)
                green_area_1 = QgsRasterLayer(osm.raster_calculator(finalRaster, 174, 223, 163), "GRE1")
                QgsProject.instance().addMapLayer(green_area_1)
                temp_layers.append(green_area_1)
                green_area_2 = QgsRasterLayer(osm.raster_calculator(finalRaster, 205, 235, 176), "GRE2")
                QgsProject.instance().addMapLayer(green_area_2)
                temp_layers.append(green_area_2)
                green_area_3 = QgsRasterLayer(osm.raster_calculator(finalRaster, 170, 224, 203), "GRE3")
                QgsProject.instance().addMapLayer(green_area_3)
                temp_layers.append(green_area_3)
                green_area_4 = QgsRasterLayer(osm.raster_calculator(finalRaster, 222, 246, 192), "GRE4")
                QgsProject.instance().addMapLayer(green_area_4)
                temp_layers.append(green_area_4)
                green_area_5 = QgsRasterLayer(osm.raster_calculator(finalRaster, 223, 252, 226), "GRE5")
                QgsProject.instance().addMapLayer(green_area_5)
                temp_layers.append(green_area_5)
                green_area_6 = QgsRasterLayer(osm.raster_calculator(finalRaster, 170, 203, 175), "GRE6")
                QgsProject.instance().addMapLayer(green_area_6)
                temp_layers.append(green_area_6)
                green_area_7 = QgsRasterLayer(osm.raster_calculator(finalRaster, 222, 252, 225), "GRE7")
                QgsProject.instance().addMapLayer(green_area_7)
                temp_layers.append(green_area_7)
                green_area_8 = QgsRasterLayer(osm.raster_calculator(finalRaster, 200, 215, 171), "GRE8")
                QgsProject.instance().addMapLayer(green_area_8)
                temp_layers.append(green_area_8)
                green_area_9 = QgsRasterLayer(osm.raster_calculator(finalRaster, 173, 209, 158), "GRE9")
                QgsProject.instance().addMapLayer(green_area_9)
                temp_layers.append(green_area_9)
                green_area_10 = QgsRasterLayer(osm.raster_calculator(finalRaster, 214, 217, 159), "GRE10")
                QgsProject.instance().addMapLayer(green_area_10)
                temp_layers.append(green_area_10)
                green_area_11 = QgsRasterLayer(osm.raster_calculator(finalRaster, 224, 233, 184), "GRE11")
                QgsProject.instance().addMapLayer(green_area_11)
                temp_layers.append(green_area_11)
                green_area_12 = QgsRasterLayer(osm.raster_calculator(finalRaster, 204, 236, 194), "GRE12")
                QgsProject.instance().addMapLayer(green_area_12)
                temp_layers.append(green_area_12)
                green_area_13 = QgsRasterLayer(osm.raster_calculator(finalRaster, 177, 212, 193), "GRE13")
                QgsProject.instance().addMapLayer(green_area_13)
                temp_layers.append(green_area_13)
                green_area_14 = QgsRasterLayer(osm.raster_calculator(finalRaster, 179, 198, 153), "GRE14")
                QgsProject.instance().addMapLayer(green_area_14)
                temp_layers.append(green_area_14)

                lpc = QgsRasterLayer(osm.landuse_calculator(park,
                                                            [park.name(),
                                                             green_area_1.name(),
                                                             green_area_2.name(),
                                                             green_area_3.name(),
                                                             green_area_4.name(),
                                                             green_area_5.name(),
                                                             green_area_6.name(),
                                                             green_area_7.name(),
                                                             green_area_8.name(),
                                                             green_area_9.name(),
                                                             green_area_10.name(),
                                                             green_area_11.name(),
                                                             green_area_12.name(),
                                                             green_area_13.name()],
                                                            3), "LPC")
                QgsProject.instance().addMapLayer(lpc)
                layers.append(lpc)

                # Water
                pd.setLabelText("Finding water...")
                pd.setValue(4)

                water = QgsRasterLayer(osm.raster_calculator(finalRaster, 170, 211, 223), "WAT1")
                QgsProject.instance().addMapLayer(water)
                temp_layers.append(water)
                water_2 = QgsRasterLayer(osm.raster_calculator(finalRaster, 177, 200, 211), "WAT2")
                QgsProject.instance().addMapLayer(water_2)
                temp_layers.append(water_2)

                watr = QgsRasterLayer(osm.landuse_calculator(water,
                                                             [water.name(),
                                                              water_2.name(),
                                                              ],
                                                             4), "WATR")
                QgsProject.instance().addMapLayer(watr)
                layers.append(watr)

                # Agricultural
                pd.setLabelText("Finding agricultural...")
                pd.setValue(5)

                agricultural = QgsRasterLayer(osm.raster_calculator(finalRaster, 238, 240, 213), "AGRI")
                QgsProject.instance().addMapLayer(agricultural)
                temp_layers.append(agricultural)

                ag = QgsRasterLayer(osm.landuse_calculator(agricultural,
                                                           [agricultural.name(),
                                                            ],
                                                           5), "AG")
                QgsProject.instance().addMapLayer(ag)
                layers.append(ag)

                # Undeveloped Desert Rangeland
                pd.setLabelText("Finding undeveloped areas...")
                pd.setValue(6)

                undeveloped_1 = QgsRasterLayer(osm.raster_calculator(finalRaster, 199, 199, 180), "UND1")
                QgsProject.instance().addMapLayer(undeveloped_1)
                temp_layers.append(undeveloped_1)
                undeveloped_2 = QgsRasterLayer(osm.raster_calculator(finalRaster, 234, 220, 215), "UND2")
                QgsProject.instance().addMapLayer(undeveloped_2)
                temp_layers.append(undeveloped_2)
                undeveloped_3 = QgsRasterLayer(osm.raster_calculator(finalRaster, 203, 190, 173), "UND3")
                QgsProject.instance().addMapLayer(undeveloped_3)
                temp_layers.append(undeveloped_3)

                ndr = QgsRasterLayer(osm.landuse_calculator(undeveloped_1,
                                                            [undeveloped_1.name(),
                                                             undeveloped_2.name(),
                                                             undeveloped_3.name(),
                                                             ],
                                                            6), "NDR")
                QgsProject.instance().addMapLayer(ndr)
                layers.append(ndr)

                # Desert Landscaping
                pd.setLabelText("Finding desert areas...")
                pd.setValue(7)

                desert_1 = QgsRasterLayer(osm.raster_calculator(finalRaster, 245, 233, 198), "DES1")
                QgsProject.instance().addMapLayer(desert_1)
                temp_layers.append(desert_1)
                desert_2 = QgsRasterLayer(osm.raster_calculator(finalRaster, 238, 229, 220), "DES2")
                QgsProject.instance().addMapLayer(desert_2)
                temp_layers.append(desert_2)
                desert_3 = QgsRasterLayer(osm.raster_calculator(finalRaster, 245, 221, 189), "DES3")
                QgsProject.instance().addMapLayer(desert_3)
                temp_layers.append(desert_3)

                dl = QgsRasterLayer(osm.landuse_calculator(desert_1,
                                                           [desert_1.name(),
                                                            desert_2.name(),
                                                            desert_3.name()
                                                            ],
                                                           7), "DL")
                QgsProject.instance().addMapLayer(dl)
                layers.append(dl)

                # Industrial
                pd.setLabelText("Finding industrial areas...")
                pd.setValue(8)

                industrial_1 = QgsRasterLayer(osm.raster_calculator(finalRaster, 197, 195, 195), "IND1")
                QgsProject.instance().addMapLayer(industrial_1)
                temp_layers.append(industrial_1)
                industrial_2 = QgsRasterLayer(osm.raster_calculator(finalRaster, 235, 219, 232), "IND2")
                QgsProject.instance().addMapLayer(industrial_2)
                temp_layers.append(industrial_2)
                industrial_3 = QgsRasterLayer(osm.raster_calculator(finalRaster, 226, 203, 222), "IND3")
                QgsProject.instance().addMapLayer(industrial_3)
                temp_layers.append(industrial_3)
                industrial_4 = QgsRasterLayer(osm.raster_calculator(finalRaster, 245, 220, 186), "IND4")
                QgsProject.instance().addMapLayer(industrial_4)
                temp_layers.append(industrial_4)
                industrial_5 = QgsRasterLayer(osm.raster_calculator(finalRaster, 245, 220, 186), "IND5")
                QgsProject.instance().addMapLayer(industrial_5)
                temp_layers.append(industrial_5)
                industrial_6 = QgsRasterLayer(osm.raster_calculator(finalRaster, 201, 186, 186), "IND6")
                QgsProject.instance().addMapLayer(industrial_6)
                temp_layers.append(industrial_6)
                industrial_7 = QgsRasterLayer(osm.raster_calculator(finalRaster, 228, 194, 211), "IND7")
                QgsProject.instance().addMapLayer(industrial_7)
                temp_layers.append(industrial_7)

                i = QgsRasterLayer(osm.landuse_calculator(industrial_1,
                                                          [industrial_1.name(),
                                                           industrial_2.name(),
                                                           industrial_3.name(),
                                                           industrial_4.name(),
                                                           industrial_5.name(),
                                                           industrial_6.name(),
                                                           industrial_7.name()
                                                           ],
                                                          8), "I")
                QgsProject.instance().addMapLayer(i)
                layers.append(i)

                # Land cover raster
                pd.setLabelText("Creating land cover map...")
                pd.setValue(9)

                land_cover = QgsRasterLayer(osm.landuse_rasterizor(lpc,
                                                                   [mdr.name(),
                                                                    c.name(),
                                                                    lpc.name(),
                                                                    watr.name(),
                                                                    ag.name(),
                                                                    ndr.name(),
                                                                    dl.name(),
                                                                    i.name()]),
                                            "land_use")
                QgsProject.instance().addMapLayer(land_cover)
                layers.append(land_cover)

                # Land cover vector
                pd.setLabelText("Vectorizing land cover map...")
                pd.setValue(10)
                land_cover_vector = osm.landuse_vectorizor(land_cover, self.grid_lyr)
                land_cover_vector.setName("landuse_layer")

                # adding the fields
                layer_provider = land_cover_vector.dataProvider()
                layer_provider.addAttributes([QgsField("landuse_category", QVariant.String)])
                layer_provider.addAttributes([QgsField("InitAbs", QVariant.Double)])
                layer_provider.addAttributes([QgsField("RTIMP", QVariant.Double)])
                layer_provider.addAttributes([QgsField("VegCov", QVariant.Double)])
                layer_provider.addAttributes([QgsField("Sat", QVariant.String)])
                land_cover_vector.updateFields()

                # Check model's unit
                if self.gutils.get_cont_par("METRIC") == "1":
                    unit_conversion = 25.4  # mm
                else:
                    unit_conversion = 1  # inches

                # Updating attributes
                land_cover_vector.startEditing()
                for feature in land_cover_vector.getFeatures():
                    if feature['DN'] == 0:
                        feature['landuse_category'] = "Pavement and Rooftops"
                        feature['InitAbs'] = 0.05 * unit_conversion
                        feature['RTIMP'] = 98
                        feature['VegCov'] = 0
                        feature['Sat'] = "normal"
                    if feature['DN'] == 1:
                        feature['landuse_category'] = "Medium density residential"
                        feature['InitAbs'] = 0.25 * unit_conversion
                        feature['RTIMP'] = 30
                        feature['VegCov'] = 50
                        feature['Sat'] = "dry"
                    if feature['DN'] == 2:
                        feature['landuse_category'] = "Commercial"
                        feature['InitAbs'] = 0.1 * unit_conversion
                        feature['RTIMP'] = 80
                        feature['VegCov'] = 75
                        feature['Sat'] = "normal"
                    if feature['DN'] == 3:
                        feature['landuse_category'] = "Lawns/Parks/Cemeteries"
                        feature['InitAbs'] = 0.2 * unit_conversion
                        feature['RTIMP'] = 0  # assumed
                        feature['VegCov'] = 80
                        feature['Sat'] = "normal"
                    if feature['DN'] == 4:  # DOUBLE CHECK
                        feature['landuse_category'] = "Water"
                        feature['InitAbs'] = 0
                        feature['RTIMP'] = 0
                        feature['VegCov'] = 0
                        feature['Sat'] = "normal"
                    if feature['DN'] == 5:
                        feature['landuse_category'] = "Agricultural"
                        feature['InitAbs'] = 0.5 * unit_conversion
                        feature['RTIMP'] = 0
                        feature['VegCov'] = 85
                        feature['Sat'] = "normal"
                    if feature['DN'] == 6:
                        feature['landuse_category'] = "Undeveloped Desert Rangeland"
                        feature['InitAbs'] = 0.35 * unit_conversion
                        feature['RTIMP'] = 0  # assumed
                        feature['VegCov'] = 0  # assumed
                        feature['Sat'] = "normal"
                    if feature['DN'] == 7:
                        feature['landuse_category'] = "Desert Landscaping"
                        feature['InitAbs'] = 0.1 * unit_conversion
                        feature['RTIMP'] = 95
                        feature['VegCov'] = 30
                        feature['Sat'] = "normal"
                    if feature['DN'] == 8:
                        feature['landuse_category'] = "Industrial"
                        feature['InitAbs'] = 0.15 * unit_conversion
                        feature['RTIMP'] = 55
                        feature['VegCov'] = 60
                        feature['Sat'] = "normal"

                    land_cover_vector.updateFeature(feature)

                land_cover_vector.commitChanges()

                QgsProject.instance().addMapLayer(land_cover_vector)
                layers.append(land_cover_vector)

                for layer in temp_layers:
                    QgsProject.instance().removeMapLayer(layer)

                if not saveLayers:
                    for layer in layers:
                        if layer != land_cover_vector:
                            QgsProject.instance().removeMapLayer(layer)
                else:
                    gpkg_path = self.gutils.get_gpkg_path()

                    flo2d_name = f"FLO-2D_{self.gutils.get_metadata_par('PROJ_NAME')}"
                    group_name = "OSM Generator"
                    flo2d_grp = root_group.findGroup(flo2d_name)
                    if flo2d_grp.findGroup(group_name):
                        group = flo2d_grp.findGroup(group_name)
                    else:
                        group = flo2d_grp.insertGroup(-1, group_name)

                    for layer in layers:
                        # Check if it is vector or raster
                        if layer.type() == QgsMapLayer.VectorLayer and layer.isSpatial():
                            # Save to gpkg
                            options = QgsVectorFileWriter.SaveVectorOptions()
                            options.driverName = "GPKG"
                            options.includeZ = True
                            options.overrideGeometryType = layer.wkbType()
                            options.layerName = layer.name()
                            options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
                            QgsVectorFileWriter.writeAsVectorFormatV3(
                                layer,
                                gpkg_path,
                                QgsProject.instance().transformContext(),
                                options)
                            # Add back to the project
                            gpkg_uri = f"{gpkg_path}|layername={layer.name()}"
                            gpkg_layer = QgsVectorLayer(gpkg_uri, layer.name(), "ogr")
                            QgsProject.instance().addMapLayer(gpkg_layer, False)
                            gpkg_layer.setRenderer(layer.renderer().clone())
                            gpkg_layer.triggerRepaint()
                            group.insertLayer(0, gpkg_layer)
                            if layer.name() == "landuse_layer":
                                land_cover_vector = gpkg_layer
                            layer = QgsProject.instance().mapLayersByName(gpkg_layer.name())[0]
                            myLayerNode = root_group.findLayer(layer.id())
                            myLayerNode.setExpanded(False)

                            # Delete layer that is not in the gpkg
                            QgsProject.instance().removeMapLayer(layer)

                        elif layer.type() == QgsMapLayer.RasterLayer:
                            # Save to gpkg
                            layer_name = layer.name().replace(" ", "_")
                            if layer.name() != "OSM":
                                params = {'INPUT': f'{layer.dataProvider().dataSourceUri()}',
                                          'TARGET_CRS': None,
                                          'NODATA': None,
                                          'COPY_SUBDATASETS': False,
                                          'OPTIONS': '',
                                          'EXTRA': f'-co APPEND_SUBDATASET=YES -co RASTER_TABLE={layer_name} -ot Float32',
                                          'DATA_TYPE': 0,
                                          'OUTPUT': f'{gpkg_path}'}
                            else:
                                params = {'INPUT': f'{layer.dataProvider().dataSourceUri()}',
                                          'TARGET_CRS': None,
                                          'NODATA': None,
                                          'COPY_SUBDATASETS': False,
                                          'OPTIONS': '',
                                          'EXTRA': f'-co APPEND_SUBDATASET=YES -co RASTER_TABLE={layer_name} -ot Byte',
                                          'DATA_TYPE': 0,
                                          'OUTPUT': f'{gpkg_path}'}

                            processing.run("gdal:translate", params)

                            gpkg_uri = f"GPKG:{gpkg_path}:{layer_name}"
                            gpkg_layer = QgsRasterLayer(gpkg_uri, layer_name, "gdal")
                            QgsProject.instance().addMapLayer(gpkg_layer, False)
                            gpkg_layer.setRenderer(layer.renderer().clone())
                            gpkg_layer.triggerRepaint()
                            group.insertLayer(0, gpkg_layer)
                            # Delete layer that is not in the gpkg
                            QgsProject.instance().removeMapLayer(layer)

                            layer = QgsProject.instance().mapLayersByName(gpkg_layer.name())[0]
                            myLayerNode = root_group.findLayer(layer.id())
                            myLayerNode.setExpanded(False)

                self.land_cbo.insertItem(0, land_cover_vector.name(), land_cover_vector)
                self.land_cbo.setCurrentIndex(0)
                self.saturation_cbo.setCurrentIndex(6)
                self.vc_cbo.setCurrentIndex(5)
                self.ia_cbo.setCurrentIndex(3)
                self.rtimpl_cbo.setCurrentIndex(4)
                self.iface.mapCanvas().refresh()

                pd.setValue(11)
                pd.close()

        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_error(
                "ERROR: Green-Ampt OSM parameters failed!."
                + "\n__________________________________________________",
                e,
            )

        return


uiDialog_scs, qtBaseClass_scs = load_ui("infil_scs")


class SCSDialog(uiDialog_scs, qtBaseClass_scs):
    def __init__(self, iface, lyrs):
        qtBaseClass_scs.__init__(self)
        uiDialog_scs.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")

        self.single_combos = [self.cn_cbo]
        self.single_lyr_cbo.currentIndexChanged.connect(self.populate_single_fields)
        self.single_grp.toggled.connect(self.single_checked)

        self.raster_combos = [self.raster_lyr_cbo, self.resamp_cbo]
        self.raster_grp.toggled.connect(self.raster_checked)
        self.browse_btn.clicked.connect(self.browse_raster)
        self.populate_alg_cbo()
        self.src_nodata = -9999
        self.grid = None

        self.multi_combos = [self.landsoil_cbo, self.cd_cbo, self.imp_cbo]
        self.multi_lyr_cbo.currentIndexChanged.connect(self.populate_multi_fields)
        self.multi_grp.toggled.connect(self.multi_checked)
        self.setup_layer_combos()

    def setup_layer_combos(self):
        """
        Filter layer and fields combo boxes for polygons and rasters and connect fields cbo.
        """
        self.single_lyr_cbo.clear()
        self.raster_lyr_cbo.clear()
        self.multi_lyr_cbo.clear()
        try:
            lyrs = self.lyrs.list_group_vlayers()
            for l in lyrs:
                if l.geometryType() == QgsWkbTypes.PolygonGeometry:
                    l.reload()
                    if l.featureCount() > 0:
                        lyr_name = l.name()
                        self.single_lyr_cbo.addItem(lyr_name, l)
                        self.multi_lyr_cbo.addItem(lyr_name, l)
            rasters = self.lyrs.list_group_rlayers()
            for r in rasters:
                self.raster_lyr_cbo.addItem(r.name(), r.dataProvider().dataSourceUri())
        except Exception as e:
            pass

    def populate_single_fields(self, idx):
        lyr = self.single_lyr_cbo.itemData(idx)
        fields = [f.name() for f in lyr.fields()]
        for c in self.single_combos:
            c.clear()
            c.addItems(fields)

    def populate_multi_fields(self, idx):
        lyr = self.multi_lyr_cbo.itemData(idx)
        fields = [f.name() for f in lyr.fields()]
        for c in self.multi_combos:
            c.clear()
            c.addItems(fields)

    def single_checked(self):
        if self.single_grp.isChecked():
            if self.multi_grp.isChecked():
                self.multi_grp.setChecked(False)
            if self.raster_grp.isChecked():
                self.raster_grp.setChecked(False)

    def raster_checked(self):
        if self.raster_grp.isChecked():
            if self.multi_grp.isChecked():
                self.multi_grp.setChecked(False)
            if self.single_grp.isChecked():
                self.single_grp.setChecked(False)

    def multi_checked(self):
        if self.multi_grp.isChecked():
            if self.single_grp.isChecked():
                self.single_grp.setChecked(False)
            if self.raster_grp.isChecked():
                self.raster_grp.setChecked(False)

    def single_scs_parameters(self):
        idx = self.single_lyr_cbo.currentIndex()
        single_lyr = self.single_lyr_cbo.itemData(idx)
        fields = [f.currentText() for f in self.single_combos]
        return single_lyr, fields

    def raster_scs_parameters(self):
        idx = self.raster_lyr_cbo.currentIndex()
        raster_lyr = self.raster_lyr_cbo.itemData(idx)
        idx_algo = self.resamp_cbo.currentIndex()
        algorithm = self.resamp_cbo.itemData(idx_algo)
        nodatavalue = self.nodata_value.text()
        fillnodata = self.fillNoDataChBox.isChecked()
        multithread = self.multiThreadChBox.isChecked()
        return raster_lyr, algorithm, nodatavalue, fillnodata, multithread

    def multi_scs_parameters(self):
        idx = self.multi_lyr_cbo.currentIndex()
        multi_lyr = self.multi_lyr_cbo.itemData(idx)
        fields = [f.currentText() for f in self.multi_combos]
        return multi_lyr, fields

    def populate_alg_cbo(self):
        """
        Populate resample algorithm combobox.
        """
        met = {
            "near": "Nearest neighbour",
            "bilinear": "Bilinear",
            "cubic": "Cubic",
            "cubicspline": "Cubic spline",
            "lanczos": "Lanczos",
            "average": "Average of all non-NODATA pixels",
            "mode": "Mode - Select the value which appears most often",
            "max": "Maximum value from all non-NODATA pixels",
            "min": "Minimum value from all non-NODATA pixels",
            "med": "Median value of all non-NODATA pixels",
            "q1": "q1 - First quartile value of all non-NODATA",
            "q3": "q1 - Third quartile value of all non-NODATA",
        }
        for m in sorted(met.keys()):
            self.resamp_cbo.addItem(met[m], m)
            self.resamp_cbo.setCurrentIndex(0)

    def browse_raster(self):
        """
        Users pick a source raster not loaded into project.
        """
        s = QSettings()
        last_elev_raster_dir = s.value("FLO-2D/lastScsRasterDir", "")
        self.src, __ = QFileDialog.getOpenFileName(None, "Choose SCS Curve Number raster...",
                                                   directory=last_elev_raster_dir)
        if not self.src:
            return
        s.setValue("FLO-2D/lastScsRasterDir", os.path.dirname(self.src))
        if self.raster_lyr_cbo.findData(self.src) == -1:
            bname = os.path.basename(self.src)
            self.raster_lyr_cbo.addItem(bname, self.src)
            self.raster_lyr_cbo.setCurrentIndex(len(self.raster_lyr_cbo) - 1)
