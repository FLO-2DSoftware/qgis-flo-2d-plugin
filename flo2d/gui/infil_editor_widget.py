# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import traceback
from math import isnan
from itertools import chain
from collections import OrderedDict
from qgis.PyQt.QtCore import pyqtSignal, pyqtSlot, Qt, QSettings
from qgis.PyQt.QtWidgets import QCheckBox, QDoubleSpinBox, QInputDialog, QApplication
from qgis.PyQt.QtGui import QStandardItemModel, QStandardItem
from qgis.core import QgsFeatureRequest, QgsWkbTypes
from .ui_utils import load_ui, center_canvas, set_icon, switch_to_selected
from ..utils import m_fdata
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..flo2d_tools.grid_tools import poly2grid, poly2poly_geos
from ..flo2d_tools.infiltration_tools import InfiltrationCalculator

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
        self.schema_green = None
        self.schema_scs = None
        self.schema_horton = None
        self.schema_chan = None
        self.all_schema = []
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
            self.schema_green = self.lyrs.data["infil_areas_green"]["qlyr"]
            self.schema_scs = self.lyrs.data["infil_areas_scs"]["qlyr"]
            self.schema_horton = self.lyrs.data["infil_areas_horton"]["qlyr"]
            self.schema_chan = self.lyrs.data["infil_areas_chan"]["qlyr"]
            self.all_schema += [self.schema_green, self.schema_scs, self.schema_horton, self.schema_chan]
            self.read_global_params()
            self.infil_lyr.editingStopped.connect(self.populate_infiltration)
            self.infil_lyr.selectionChanged.connect(self.switch2selected)
            self.infil_name_cbo.activated.connect(self.infiltration_changed)

    def switch2selected(self):
        switch_to_selected(self.infil_lyr, self.infil_name_cbo)
        self.infiltration_changed()

    def repaint_schema(self):
        for lyr in self.all_schema:
            lyr.triggerRepaint()

    def fill_green_char(self):
        qry = """UPDATE user_infiltration SET green_char = 'F' WHERE green_char NOT IN ('C', 'F');"""
        cur = self.con.cursor()
        cur.execute(qry)
        self.con.commit()
        self.infil_lyr.triggerRepaint()

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
                if not isinstance(obj, (QDoubleSpinBox, QCheckBox)):
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
            return
        if not self.lyrs.enter_edit_mode("user_infiltration"):
            return

    def rename_infil(self):
        if self.iglobal.global_imethod == 0:
            self.uc.bar_warn("Please define global infiltration method first!")
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
            return
        self.infil_name_cbo.setItemText(self.infil_name_cbo.currentIndex(), new_name)
        self.save_infil_edits()

    def revert_infil_lyr_edits(self):
        if self.iglobal.global_imethod == 0:
            self.uc.bar_warn("Please define global infiltration parameters first!")
            return
        user_infil_edited = self.lyrs.rollback_lyrs_edits("user_infiltration")
        if user_infil_edited:
            self.populate_infiltration()

    def delete_cur_infil(self):
        if self.iglobal.global_imethod == 0:
            self.uc.bar_warn("Please define global infiltration method first!")
            return
        if not self.infil_name_cbo.count():
            return
        q = "Are you sure, you want delete the current infiltration?"
        if not self.uc.question(q):
            return
        infil_fid = self.infil_name_cbo.itemData(self.infil_idx)["fid"]
        self.gutils.execute("DELETE FROM user_infiltration WHERE fid = ?;", (infil_fid,))
        self.infil_lyr.triggerRepaint()
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
                if isinstance(obj, QDoubleSpinBox):
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
                if isinstance(obj, QDoubleSpinBox):
                    obj_name = obj.objectName().split("_", 1)[-1]
                    obj.setValue(infil_dict[obj_name])
                else:
                    continue
        self.lyrs.clear_rubber()
        if self.center_chbox.isChecked():
            ifid = infil_dict["fid"]
            self.lyrs.show_feat_rubber(self.infil_lyr.id(), ifid)
            feat = next(self.infil_lyr.getFeatures(QgsFeatureRequest(ifid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def schematize_infiltration(self):
        if self.iglobal.global_imethod == 0:
            self.uc.bar_warn("Please define global infiltration method first!")
            return
        qry_green_areas = """INSERT INTO infil_areas_green (fid, geom, hydc, soils, dtheta, abstrinf, rtimpf, soil_depth) VALUES (?,?,?,?,?,?,?,?);"""
        qry_chan_areas = """INSERT INTO infil_areas_chan (fid, geom, hydconch) VALUES (?,?,?);"""
        qry_scs_areas = """INSERT INTO infil_areas_scs (fid, geom, scsn) VALUES (?,?,?);"""
        qry_horton_areas = """INSERT INTO infil_areas_horton (fid, geom, fhorti, fhortf, deca) VALUES (?,?,?,?,?);"""

        qry_green_cells = """INSERT INTO infil_cells_green (infil_area_fid, grid_fid) VALUES (?,?);"""
        qry_chan_cells = """INSERT INTO infil_chan_elems (infil_area_fid, grid_fid) VALUES (?,?);"""
        qry_scs_cells = """INSERT INTO infil_cells_scs (infil_area_fid, grid_fid) VALUES (?,?);"""
        qry_horton_cells = """INSERT INTO infil_cells_horton (infil_area_fid, grid_fid) VALUES (?,?);"""

        imethod = self.infmethod
        if imethod == 0:
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.gutils.disable_geom_triggers()
            sl = self.slices[imethod]
            columns = self.infil_columns[sl]
            infiltration_grids = list(poly2grid(self.grid_lyr, self.infil_lyr, None, True, False, False, 1, *columns))
            self.gutils.clear_tables(
                "infil_areas_green",
                "infil_areas_scs",
                "infil_areas_horton",
                "infil_areas_chan",
                "infil_cells_green",
                "infil_cells_scs",
                "infil_cells_horton",
                "infil_chan_elems",
            )
            if imethod == 1 or imethod == 3:
                green_area_vals, chan_area_vals, scs_area_vals = [], [], []
                green_cells_vals, chan_cells_vals, scs_cells_vals = [], [], []
                green_fid, chan_fid, scs_fid = 1, 1, 1
                for grid_row in infiltration_grids:
                    row = list(grid_row)
                    gid = row.pop()
                    char = row.pop(0)
                    geom = self.gutils.grid_geom(gid)
                    if char == "F":
                        val = (green_fid, geom) + tuple(row[:6])
                        green_area_vals.append(val)
                        green_cells_vals.append((green_fid, gid))
                        green_fid += 1
                    elif char == "C":
                        val = (chan_fid, geom, row[6])
                        chan_area_vals.append(val)
                        chan_cells_vals.append((chan_fid, gid))
                        chan_fid += 1
                    else:
                        val = (scs_fid, geom, row[7])
                        scs_area_vals.append(val)
                        scs_cells_vals.append((scs_fid, gid))
                        scs_fid += 1
                cur = self.con.cursor()
                cur.executemany(qry_green_areas, green_area_vals)
                cur.executemany(qry_chan_areas, chan_area_vals)
                cur.executemany(qry_scs_areas, scs_area_vals)
                cur.executemany(qry_green_cells, green_cells_vals)
                cur.executemany(qry_chan_cells, chan_cells_vals)
                cur.executemany(qry_scs_cells, scs_cells_vals)
            else:
                if imethod == 2:
                    qry_areas = qry_scs_areas
                    qry_cells = qry_scs_cells
                else:
                    qry_areas = qry_horton_areas
                    qry_cells = qry_horton_cells
                area_vals = []
                cells_vals = []
                for i, grid_row in enumerate(infiltration_grids, 1):
                    row = list(grid_row)
                    gid = row.pop()
                    geom = self.gutils.grid_geom(gid)
                    val = (i, geom) + tuple(row)
                    area_vals.append(val)
                    cells_vals.append((i, gid))
                cur = self.con.cursor()
                cur.executemany(qry_areas, area_vals)
                cur.executemany(qry_cells, cells_vals)
            self.con.commit()
            self.repaint_schema()
            self.gutils.enable_geom_triggers()
            QApplication.restoreOverrideCursor()
            self.uc.bar_info("Schematizing of infiltration finished!")
        except Exception as e:
            self.gutils.enable_geom_triggers()
            self.uc.log_info(traceback.format_exc())
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("Schematizing of infiltration failed! Please check user infiltration layers.")
            self.uc.show_error(
                "ERROR 271118.1638: error schematizing infiltration!."
                + "\n__________________________________________________",
                e,
            )

    def calculate_green_ampt(self):
        dlg = GreenAmptDialog(self.iface, self.lyrs)
        ok = dlg.exec_()
        if not ok:
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            dlg.save_green_ampt_shapefile_fields()
            self.gutils.disable_geom_triggers()
            soil_lyr, land_lyr, fields, vcCheck = dlg.green_ampt_parameters()
            inf_calc = InfiltrationCalculator(self.grid_lyr, self.iface)
            inf_calc.setup_green_ampt(soil_lyr, land_lyr, vcCheck, *fields)
            grid_params = inf_calc.green_ampt_infiltration()

            if grid_params:

                # apply effective impervious area layer
                eff_values = poly2poly_geos(
                    self.grid_lyr,
                    self.eff_lyr,
                    None,
                    "eff"
                )
                try:
                    for gid, values in eff_values:
                        fact = 1-sum((1-row[0]*0.01)*row[-1] for row in values)
                        grid_params[gid]["rtimpf"] *= fact
                except Exception:
                    pass

                self.gutils.clear_tables("infil_areas_green", "infil_cells_green")
                qry_areas = """INSERT INTO infil_areas_green (fid, geom, hydc, soils, dtheta, abstrinf, rtimpf, soil_depth) VALUES (?,?,?,?,?,?,?,?);"""
                qry_cells = """INSERT INTO infil_cells_green (infil_area_fid, grid_fid) VALUES (?,?);"""
                area_values = []
                cells_values = []
                non_intercepted = []
                for i, (gid, params) in enumerate(grid_params.items(), 1):
                    if not "dtheta" in params:
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
                    geom = self.gutils.grid_geom(gid)
                    values = (i, geom) + tuple(round(p, 3) for p in par)
                    area_values.append(values)
                    cells_values.append((i, gid))
                cur = self.con.cursor()
                cur.executemany(qry_areas, area_values)
                cur.executemany(qry_cells, cells_values)
                self.con.commit()
                self.schema_green.triggerRepaint()
                self.gutils.enable_geom_triggers()
                QApplication.restoreOverrideCursor()

                if non_intercepted:
                    no_inter = ""
                    for nope in non_intercepted:
                        no_inter += "\n" + str(nope)
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
            self.gutils.enable_geom_triggers()
            self.uc.log_info(traceback.format_exc())
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 051218.1839: Green-Ampt infiltration failed!. Please check data in your input layers."
                + "\n__________________________________________________",
                e,
            )

    def calculate_scs(self):
        dlg = SCSDialog(self.iface, self.lyrs)
        ok = dlg.exec_()
        if not ok:
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.gutils.disable_geom_triggers()
            inf_calc = InfiltrationCalculator(self.grid_lyr, self.iface)
            if dlg.single_grp.isChecked():
                single_lyr, single_fields = dlg.single_scs_parameters()
                inf_calc.setup_scs_single(single_lyr, *single_fields)
                grid_params = inf_calc.scs_infiltration_single()
            else:
                multi_lyr, multi_fields = dlg.multi_scs_parameters()
                inf_calc.setup_scs_multi(multi_lyr, *multi_fields)
                grid_params = inf_calc.scs_infiltration_multi()
            self.gutils.clear_tables("infil_areas_scs", "infil_cells_scs")
            qry_areas = """INSERT INTO infil_areas_scs (fid, geom, scsn) VALUES (?,?,?);"""
            qry_cells = """INSERT INTO infil_cells_scs (infil_area_fid, grid_fid) VALUES (?,?);"""
            area_values = []
            cells_values = []
            for i, (gid, params) in enumerate(grid_params.items(), 1):
                geom = self.gutils.grid_geom(gid)
                values = (i, geom, round(params["scsn"], 3))
                area_values.append(values)
                cells_values.append((i, gid))
            cur = self.con.cursor()
            cur.executemany(qry_areas, area_values)
            cur.executemany(qry_cells, cells_values)
            self.con.commit()
            self.schema_scs.triggerRepaint()
            self.gutils.enable_geom_triggers()
            QApplication.restoreOverrideCursor()
            self.uc.show_info("Calculating SCS Curve Number parameters finished!")
        except Exception as e:
            self.gutils.enable_geom_triggers()
            self.uc.log_info(traceback.format_exc())
            QApplication.restoreOverrideCursor()
            self.uc.show_warn(
                "WARNING 060319.1724: Calculating SCS Curve Number parameters failed! Please check data in your input layers."
            )


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
                hydcadj, hydcxx, scsnall, abstr1, fhortoni, fhortonf, decaya FROM infil"""

        try:
            infil_glob = self.gutils.execute(qry).fetchone()

            if infil_glob:
                self.spin_abstr.setValue(infil_glob[1] if infil_glob[1] is not None else 0.0)
                self.spin_sati.setValue(infil_glob[2] if infil_glob[2] is not None else 0.7)
                self.spin_satf.setValue(infil_glob[3] if infil_glob[3] is not None else 1.0)
                self.spin_poros.setValue(infil_glob[4] if infil_glob[4] is not None else 0.4)
                self.spin_soild.setValue(infil_glob[5] if infil_glob[5] is not None else 0.0)
                self.cb_infchan.setChecked(infil_glob[6] if infil_glob[6] is not None else 0)
                self.spin_hydcall.setValue(infil_glob[7] if infil_glob[7] is not None else 0.1)
                self.spin_soilall.setValue(infil_glob[8] if infil_glob[8] is not None else 4.3)
                self.spin_hydcadj.setValue(infil_glob[9] if infil_glob[9] is not None else 0.0)
                self.spin_hydcxx.setValue(infil_glob[10] if infil_glob[10] is not None else 0.1)
                self.spin_scsnall.setValue(infil_glob[11] if infil_glob[11] is not None else 99.0)
                self.spin_abstr1.setValue(infil_glob[12] if infil_glob[12] is not None else 0.0)
                self.spin_fhortoni.setValue(infil_glob[13] if infil_glob[13] is not None else 0.0)
                self.spin_fhortonf.setValue(infil_glob[14] if infil_glob[14] is not None else 0.0)
                self.spin_decaya.setValue(infil_glob[15] if infil_glob[15] is not None else 0.0)
            else:
                self.spin_abstr.setValue(0.0)
                self.spin_sati.setValue(0.7)
                self.spin_satf.setValue(1.0)
                self.spin_poros.setValue(0.4)
                self.spin_soild.setValue(0.0)
                self.cb_infchan.setChecked(0)
                self.spin_hydcall.setValue(0.1)
                self.spin_soilall.setValue(4.3)
                self.spin_hydcadj.setValue(0.0)
                self.spin_hydcxx.setValue(0.1)
                self.spin_scsnall.setValue(99.0)
                self.spin_abstr1.setValue(0.0)
                self.spin_fhortoni.setValue(0.0)
                self.spin_fhortonf.setValue(0.0)
                self.spin_decaya.setValue(0.0)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_warn("ERROR 280320.1625: load of infiltration globals failed!")

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
        headers = ["Channel Name", "Channel FID", "Initial hyd. cond.", "Final hyd. cond.", "Max. Soil Depth"]
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
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.soil_combos = [self.xksat_cbo, self.rtimps_cbo, self.soil_depth_cbo]
        self.land_combos = [self.saturation_cbo, self.vc_cbo, self.ia_cbo, self.rtimpl_cbo]
        self.soil_cbo.currentIndexChanged.connect(self.populate_soil_fields)
        self.land_cbo.currentIndexChanged.connect(self.populate_land_fields)

        self.setup_layer_combos()
        self.restore_green_ampt_shapefile_fields()

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
        vcCheck = self.veg_cover_chBox.isChecked()
        return soil_lyr, land_lyr, fields, vcCheck

    def save_green_ampt_shapefile_fields(self):
        s = QSettings()

        s.setValue("ga_soil_layer_name", self.soil_cbo.currentText())
        s.setValue("ga_soil_XKSAT", self.xksat_cbo.currentIndex())
        s.setValue("ga_soil_rtimps", self.rtimps_cbo.currentIndex())
        s.setValue("ga_soil_depth", self.soil_depth_cbo.currentIndex())

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
        self.multi_combos = [self.landsoil_cbo, self.cd_cbo, self.imp_cbo]
        self.single_lyr_cbo.currentIndexChanged.connect(self.populate_single_fields)
        self.multi_lyr_cbo.currentIndexChanged.connect(self.populate_multi_fields)
        self.setup_layer_combos()
        self.single_grp.toggled.connect(self.single_checked)
        self.multi_grp.toggled.connect(self.multi_checked)

    def setup_layer_combos(self):
        """
        Filter layer and fields combo boxes for polygons and connect fields cbo.
        """
        self.single_lyr_cbo.clear()
        self.multi_lyr_cbo.clear()
        try:
            lyrs = self.lyrs.list_group_vlayers()
            for l in lyrs:
                if l.geometryType() == QgsWkbTypes.PolygonGeometry:
                    lyr_name = l.name()
                    self.single_lyr_cbo.addItem(lyr_name, l)
                    self.multi_lyr_cbo.addItem(lyr_name, l)
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

    def multi_checked(self):
        if self.multi_grp.isChecked():
            if self.single_grp.isChecked():
                self.single_grp.setChecked(False)

    def single_scs_parameters(self):
        idx = self.single_lyr_cbo.currentIndex()
        single_lyr = self.single_lyr_cbo.itemData(idx)
        fields = [f.currentText() for f in self.single_combos]
        return single_lyr, fields

    def multi_scs_parameters(self):
        idx = self.multi_lyr_cbo.currentIndex()
        multi_lyr = self.multi_lyr_cbo.itemData(idx)
        fields = [f.currentText() for f in self.multi_combos]
        return multi_lyr, fields
