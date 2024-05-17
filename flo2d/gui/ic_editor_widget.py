# -*- coding: utf-8 -*-
import csv

from PyQt5.QtCore import QVariant
from PyQt5.QtWidgets import QFileDialog, QProgressDialog, QApplication
from qgis._core import QgsVectorLayer, QgsProject, QgsField, QgsExpression, QgsExpressionContext, \
    QgsExpressionContextUtils, QgsWkbTypes
# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import processing

from qgis.core import QgsFeatureRequest
from qgis.PyQt.QtWidgets import QInputDialog
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices
from ..flo2dobjects import Reservoir, Tailings, TailingsReservoir, ChannelSegment
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..utils import is_number
from .ui_utils import center_canvas, load_ui, set_icon

uiDialog, qtBaseClass = load_ui("ic_editor")


class ICEditorWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.con = None
        self.gutils = None
        self.uc = UserCommunication(iface, "FLO-2D")
        self.gutils = GeoPackageUtils(self.iface.f2d["con"], self.iface)

        self.res_lyr = self.lyrs.data["user_reservoirs"]["qlyr"]
        self.chan_lyr = self.lyrs.data["chan"]["qlyr"]
        self.tal_lyr = self.lyrs.data["user_tailings"]["qlyr"]
        self.tal_res_lyr = self.lyrs.data["user_tailing_reservoirs"]["qlyr"]
        self.cont_table = self.lyrs.data["cont"]["qlyr"]

        # connections Reservoir
        self.add_user_res_btn.clicked.connect(self.create_user_res)
        self.revert_res_changes_btn.clicked.connect(self.revert_res_lyr_edits)
        self.schem_res_btn.clicked.connect(self.schematize_res)
        self.delete_schem_res_btn.clicked.connect(self.delete_schematize_res)
        self.rename_res_btn.clicked.connect(self.rename_res)
        self.delete_res_btn.clicked.connect(self.delete_cur_res)
        self.clear_res_rb_btn.clicked.connect(self.lyrs.clear_rubber)
        self.res_cbo.activated.connect(self.cur_res_changed)
        self.res_ini_sbox.editingFinished.connect(self.save_res)
        self.res_n_sbox.editingFinished.connect(self.save_res)

        # connections Channels
        self.chan_seg_cbo.activated.connect(self.cur_seg_changed)
        self.seg_ini_sbox.editingFinished.connect(self.save_chan_seg)
        self.rename_seg_btn.clicked.connect(self.rename_chan)
        self.delete_seg_btn.clicked.connect(self.delete_chan)
        self.clear_chan_rb_btn.clicked.connect(self.lyrs.clear_rubber)

        # connections Tailings
        self.add_point_tailings_btn.clicked.connect(self.create_point_tailings)
        self.add_tailings_btn.clicked.connect(self.create_tailings)
        self.revert_tal_changes_btn.clicked.connect(self.revert_tal_lyr_edits)
        self.delete_tailings_btn.clicked.connect(self.delete_tailings)
        self.delete_schem_tal_btn.clicked.connect(self.delete_schematize_tal)
        self.schem_tal_btn.clicked.connect(self.schematize_tal)
        # tailing res
        self.tailing_res_cbo.activated.connect(self.cur_tal_res_changed)
        self.rename_tal_res_btn.clicked.connect(self.rename_tal_res)
        self.delete_tal_res_btn.clicked.connect(self.delete_tailings_res)
        self.clear_tal_res_rb_btn.clicked.connect(self.lyrs.clear_rubber)
        self.tal_res_elev_sb.editingFinished.connect(self.save_tal_res)
        self.wse_tal_res_sb.editingFinished.connect(self.save_tal_res)
        self.tal_n_sbox.editingFinished.connect(self.save_tal_res)

        # tailing stack
        self.tailings_cbo.activated.connect(self.cur_tal_changed)
        self.rename_tal_btn.clicked.connect(self.rename_tal)
        self.clear_tal_rb_btn.clicked.connect(self.lyrs.clear_rubber)
        self.tailings_elev_sb.editingFinished.connect(self.save_tal)
        self.wse_sb.editingFinished.connect(self.save_tal)
        self.concentration_sb.editingFinished.connect(self.save_tal)

    def populate_cbos(self, fid=None, show_last_edited=False):

        if not self.iface.f2d["con"]:
            return

        mud_switch = self.gutils.get_cont_par("MUD")
        sed_switch = self.gutils.get_cont_par("ISED")
        # none
        if mud_switch == '0' and sed_switch == '0':
            self.reservoir_grp.setHidden(False)
            self.tailings_grp.setHidden(True)
        # Mud/debris
        if mud_switch == '1' and sed_switch == '0':
            self.reservoir_grp.setHidden(True)
            self.tailings_grp.setHidden(False)
            self.wse_tal_res_sb.setValue(0)
            self.wse_tal_res_sb.setEnabled(False)
            self.wse_sb.setEnabled(False)
            self.wse_sb.setValue(0)
        # Sediment Transport
        if mud_switch == '0' and sed_switch == '1':
            self.reservoir_grp.setHidden(False)
            self.tailings_grp.setHidden(True)
            self.wse_tal_res_sb.setEnabled(False)
            self.wse_tal_res_sb.setValue(0)
            self.wse_sb.setEnabled(False)
            self.wse_sb.setValue(0)
        # two-phase
        if mud_switch == '2' and sed_switch == '0':
            self.reservoir_grp.setHidden(False)
            self.tailings_grp.setHidden(False)
            self.wse_tal_res_sb.setEnabled(True)
            self.wse_sb.setEnabled(True)

        # reservoir
        self.res_cbo.clear()
        res_qry = """SELECT fid, name FROM user_reservoirs ORDER BY name COLLATE NOCASE"""
        rows = self.gutils.execute(res_qry).fetchall()
        max_fid = self.gutils.get_max("user_reservoirs")
        cur_res_idx = 0
        for i, row in enumerate(rows):
            self.res_cbo.addItem(row[1], row[0])
            if fid and row[0] == fid:
                cur_res_idx = i
            elif show_last_edited and row[0] == max_fid:
                cur_res_idx = i
        self.res_cbo.setCurrentIndex(cur_res_idx)
        self.cur_res_changed(cur_res_idx)
        # channel
        self.chan_seg_cbo.clear()
        seg_qry = """SELECT fid, name, depinitial FROM chan ORDER BY name COLLATE NOCASE"""
        rows = self.gutils.execute(seg_qry).fetchall()
        for i, row in enumerate(rows):
            self.chan_seg_cbo.addItem(row[1], row[0])
        self.cur_seg_changed(cur_res_idx)
        # tailings
        self.tailings_cbo.clear()
        tal_qry = """SELECT fid, name FROM user_tailings ORDER BY name COLLATE NOCASE"""
        rows_tal = self.gutils.execute(tal_qry).fetchall()
        for i, row in enumerate(rows_tal):
            self.tailings_cbo.addItem(row[1], row[0])
        self.cur_tal_changed(cur_res_idx)
        self.tailing_res_cbo.clear()
        tal_res_qry = """SELECT fid, name FROM user_tailing_reservoirs ORDER BY name COLLATE NOCASE"""
        rows_tal_res = self.gutils.execute(tal_res_qry).fetchall()
        for i, row in enumerate(rows_tal_res):
            self.tailing_res_cbo.addItem(row[1], row[0])
        self.cur_tal_res_changed(cur_res_idx)

        self.check_cbos()
        self.lyrs.clear_rubber()

    def cur_res_changed(self, cur_idx):
        if not self.res_cbo.count():
            self.res_ini_sbox.setValue(0)
            return
        wsel = 0
        n_value = 0.25
        self.res_fid = self.res_cbo.itemData(self.res_cbo.currentIndex())
        self.reservoir = Reservoir(self.res_fid, self.iface.f2d["con"], self.iface)
        self.reservoir.get_row()
        if is_number(self.reservoir.wsel):
            wsel = float(self.reservoir.wsel)
        if is_number(self.reservoir.n_value):
            n_value = float(self.reservoir.n_value)
        self.res_ini_sbox.setValue(wsel)
        self.res_n_sbox.setValue(n_value)
        self.show_res_rb()
        if self.center_res_btn.isChecked():
            feat = next(self.res_lyr.getFeatures(QgsFeatureRequest(self.reservoir.fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def cur_seg_changed(self, cur_idx):
        if not self.chan_seg_cbo.count():
            self.seg_ini_sbox.setValue(0)
            return
        depini = 0
        self.seg_fid = self.chan_seg_cbo.itemData(self.chan_seg_cbo.currentIndex())
        self.chan_seg = ChannelSegment(self.seg_fid, self.iface.f2d["con"], self.iface)
        self.chan_seg.get_row()
        if is_number(self.chan_seg.depinitial):
            depini = float(self.chan_seg.depinitial)
        self.seg_ini_sbox.setValue(depini)
        self.show_chan_rb()
        if self.center_seg_btn.isChecked():
            feat = next(self.chan_lyr.getFeatures(QgsFeatureRequest(self.seg_fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def cur_tal_changed(self, cur_idx):
        if not self.tailings_cbo.count():
            self.tailings_elev_sb.setValue(0)
            self.wse_sb.setValue(0)
            self.concentration_sb.setValue(0)
            return
        tailings_surf_elev = 0
        water_surf_elev = 0
        concentration = 0
        self.tal_fid = self.tailings_cbo.itemData(self.tailings_cbo.currentIndex())
        self.tailings = Tailings(self.tal_fid, self.iface.f2d["con"], self.iface)
        self.tailings.get_row()
        if is_number(self.tailings.tailings_surf_elev):
            tailings_surf_elev = float(self.tailings.tailings_surf_elev)
        if is_number(self.tailings.water_surf_elev):
            water_surf_elev = float(self.tailings.water_surf_elev)
        if is_number(self.tailings.concentration):
            concentration = float(self.tailings.concentration)
        self.tailings_elev_sb.setValue(tailings_surf_elev)
        self.wse_sb.setValue(water_surf_elev)
        self.concentration_sb.setValue(concentration)
        self.show_tal_rb()

        if self.center_res_chbox.isChecked():
            feat = next(self.tal_lyr.getFeatures(QgsFeatureRequest(self.tailings.fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def cur_tal_res_changed(self, cur_idx):
        if not self.tailing_res_cbo.count():
            self.tal_res_elev_sb.setValue(0)
            self.wse_tal_res_sb.setValue(0)
            return
        tailings_surf_elev = 0
        water_surf_elev = 0
        n_value = 0.25
        self.tal_res_fid = self.tailing_res_cbo.itemData(self.tailing_res_cbo.currentIndex())
        self.tailings_reservoir = TailingsReservoir(self.tal_res_fid, self.iface.f2d["con"], self.iface)
        self.tailings_reservoir.get_row()
        if is_number(self.tailings_reservoir.wsel):
            water_surf_elev = float(self.tailings_reservoir.wsel)
        if is_number(self.tailings_reservoir.tailings):
            tailings_surf_elev = float(self.tailings_reservoir.tailings)
        if is_number(self.tailings_reservoir.n_value):
            n_value = float(self.tailings_reservoir.n_value)
        self.tal_res_elev_sb.setValue(tailings_surf_elev)
        self.wse_tal_res_sb.setValue(water_surf_elev)
        self.tal_n_sbox.setValue(n_value)
        self.show_tal_res_rb()

        if self.center_tal_res_chbox.isChecked():
            feat = next(self.tal_lyr.getFeatures(QgsFeatureRequest(self.tailings_reservoir.fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def show_res_rb(self):
        if not self.reservoir.fid:
            return
        self.lyrs.show_feat_rubber(self.res_lyr.id(), self.reservoir.fid)

    def show_tal_rb(self):
        if not self.tailings.fid:
            return
        self.lyrs.show_feat_rubber(self.tal_lyr.id(), self.tailings.fid)

    def show_tal_res_rb(self):
        if not self.tailings_reservoir.fid:
            return
        self.lyrs.show_feat_rubber(self.tal_res_lyr.id(), self.tailings_reservoir.fid)

    def show_chan_rb(self):
        if not self.seg_fid:
            return
        self.lyrs.show_feat_rubber(self.chan_lyr.id(), self.seg_fid)

    def create_user_res(self):

        if self.lyrs.any_lyr_in_edit('user_reservoirs'):
            self.uc.bar_info(f"Reservoir saved!")
            self.uc.log_info(f"Reservoir saved!")
            self.lyrs.save_lyrs_edits('user_reservoirs')
            self.add_user_res_btn.setChecked(False)
            self.gutils.fill_empty_reservoir_names()
            self.populate_cbos()
            return
        else:
            self.lyrs.enter_edit_mode("user_reservoirs")

    def save_res_lyr_edits(self):
        if not self.gutils or not self.lyrs.any_lyr_in_edit("user_reservoirs"):
            return
        self.gutils.delete_imported_reservoirs()
        # try to save user bc layers (geometry additions/changes)
        user_res_edited = self.lyrs.save_lyrs_edits("user_reservoirs")
        # if user reservoirs layer was edited
        if user_res_edited:
            self.gutils.fill_empty_reservoir_names()
            # populate widgets and show last edited reservoir
            self.populate_cbos(show_last_edited=True)

    def rename_res(self):
        if not self.res_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, "Change name", "New name:")
        if not ok or not new_name:
            return
        if not self.res_cbo.findText(new_name) == -1:
            msg = "WARNING 060319.1722: Reservoir with name {} already exists in the database. Please, choose another name.".format(
                new_name
            )
            self.uc.show_warn(msg)
            return
        self.reservoir.name = new_name
        self.save_res()

    def rename_chan(self):
        if not self.chan_seg_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, "Change name", "New name:")
        if not ok or not new_name:
            return
        if not self.chan_seg_cbo.findText(new_name) == -1:
            msg = "WARNING 060319.1722: Channel with name {} already exists in the database. Please, choose another name.".format(
                new_name
            )
            self.uc.show_warn(msg)
            return
        self.chan_seg.name = new_name
        self.save_chan_seg()

    def rename_tal(self):
        if not self.tailings_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, "Change name", "New name:")
        if not ok or not new_name:
            return
        if not self.tailings_cbo.findText(new_name) == -1:
            msg = "WARNING 060319.1722: Tailings with name {} already exists in the database. Please, choose another name.".format(
                new_name
            )
            self.uc.show_warn(msg)
            return
        self.tailings.name = new_name
        self.save_tal()

    def rename_tal_res(self):
        """
        Function to rename tailing reservoir
        """
        if not self.tailing_res_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, "Change name", "New name:")
        if not ok or not new_name:
            return
        if not self.tailing_res_cbo.findText(new_name) == -1:
            msg = "WARNING 060319.1722: Tailings with name {} already exists in the database. Please, choose another name.".format(
                new_name
            )
            self.uc.show_warn(msg)
            return
        self.tailings_reservoir.name = new_name
        self.save_tal_res()

    def repaint_reservoirs(self):
        self.lyrs.lyrs_to_repaint = [
            self.lyrs.data["reservoirs"]["qlyr"],
            self.lyrs.data["user_reservoirs"]["qlyr"],
        ]
        self.lyrs.repaint_layers()

    def repaint_chan_seg(self):
        self.lyrs.lyrs_to_repaint = [
            self.lyrs.data["chan"]["qlyr"],
            self.lyrs.data["chan_elems"]["qlyr"],
            self.lyrs.data["rbank"]["qlyr"]
        ]
        self.lyrs.repaint_layers()

    def repaint_tailings(self):
        self.lyrs.lyrs_to_repaint = [
            self.lyrs.data["user_tailings"]["qlyr"],
            self.lyrs.data["tailing_cells"]["qlyr"],
        ]
        self.lyrs.repaint_layers()

    def repaint_tailings_res(self):
        self.lyrs.lyrs_to_repaint = [
            self.lyrs.data["user_tailing_reservoirs"]["qlyr"],
            self.lyrs.data["tailing_reservoirs"]["qlyr"],
        ]
        self.lyrs.repaint_layers()

    def revert_res_lyr_edits(self):
        user_res_edited = self.lyrs.rollback_lyrs_edits("user_reservoirs")
        if user_res_edited:
            self.add_user_res_btn.setChecked(False)
            self.populate_cbos()

    def revert_tal_lyr_edits(self):
        user_tal_edited = self.lyrs.rollback_lyrs_edits("user_tailings")
        if user_tal_edited:
            self.add_tailings_btn.setChecked(False)
            self.populate_cbos()

    def delete_cur_res(self):
        if not self.res_cbo.count():
            return
        q = "Are you sure you want delete the current reservoir?"
        if not self.uc.question(q):
            return
        self.reservoir.del_row()
        self.repaint_reservoirs()
        self.lyrs.clear_rubber()
        self.populate_cbos()
        
    def delete_schematize_res(self):
        """
        Function to delete the schematic data related to reservoirs
        """
        user_rsvs = self.gutils.execute("SELECT Count(*) FROM reservoirs").fetchone()[0]
        if user_rsvs > 0:
            self.gutils.execute("DELETE FROM reservoirs;")
            self.repaint_reservoirs()
            self.lyrs.clear_rubber()
            self.uc.bar_info(f"{user_rsvs} schematized reservoirs deleted!")
            self.uc.log_info(f"{user_rsvs} schematized reservoirs deleted!")

    def delete_schematize_tal(self):
        """
        Function to delete the schematic data related to tailings
        """
        user_tal = self.gutils.execute("SELECT Count(*) FROM tailing_cells").fetchone()[0]
        if user_tal > 0:
            self.gutils.execute("DELETE FROM tailing_cells;")
            self.repaint_tailings()
            self.lyrs.clear_rubber()
            self.uc.bar_info(f"{user_tal} schematized tailings deleted!")
            self.uc.log_info(f"{user_tal} schematized tailings deleted!")

        user_tal_res = self.gutils.execute("SELECT Count(*) FROM tailing_reservoirs").fetchone()[0]
        if user_tal_res > 0:
            self.gutils.execute("DELETE FROM tailing_reservoirs;")
            self.repaint_tailings_res()
            self.lyrs.clear_rubber()
            self.uc.bar_info(f"{user_tal_res} schematized tailings deleted!")
            self.uc.log_info(f"{user_tal_res} schematized tailings deleted!")
            
    def help_res(self):
        QDesktopServices.openUrl(QUrl("https://flo-2dsoftware.github.io/FLO-2D-Documentation/Plugin1000/widgets/initial-condition-editor/Initial%20Condition%20Editor.html#"))        

    def schematize_res(self):
        user_rsvs = self.gutils.execute("SELECT Count(*) FROM user_reservoirs").fetchone()[0]
        if user_rsvs > 0:
            ins_qry = """INSERT INTO reservoirs (user_res_fid, name, grid_fid, wsel, n_value, geom)
                        SELECT
                            ur.fid, ur.name, g.fid, ur.wsel, ur.n_value, g.geom
                        FROM
                            grid AS g, user_reservoirs AS ur
                        WHERE
                            ST_Intersects(CastAutomagic(g.geom), CastAutomagic(ur.geom));"""

            self.gutils.execute("DELETE FROM reservoirs;")
            self.gutils.execute(ins_qry)
            self.repaint_reservoirs()
            self.uc.bar_info(str(user_rsvs) + " user reservoirs schematized!")
            self.uc.log_info(str(user_rsvs) + " user reservoirs schematized!")
        else:
            sch_rsvs = self.gutils.execute("SELECT Count(*) FROM reservoirs").fetchone()[0]
            if sch_rsvs > 0:
                if self.uc.question(
                        "There aren't any user reservoirs."
                        + "\nBut there are "
                        + str(sch_rsvs)
                        + " schematic reservoirs."
                        + "\n\nDo you want to delete them?"
                ):
                    self.gutils.execute("DELETE FROM reservoirs;")
                    self.repaint_reservoirs()
            else:
                self.uc.bar_warn("There aren't any user reservoirs!")

    def schematize_tal(self):
        """
        Function to schematize the tailings
        """
        self.mud = self.gutils.get_cont_par("MUD")
        self.ised = self.gutils.get_cont_par("ISED")
        if self.mud == '0' and self.ised == '0':
            self.uc.bar_error("Mudflow / Sediment Transport disabled. Schematize Tailings failed!")
            self.uc.log_info("Mudflow / Sediment Transport disabled. Schematize Tailings failed!")
            return

        user_tal = self.gutils.execute("SELECT Count(*) FROM user_tailings").fetchone()[0]
        if not user_tal:
            user_tal = 0
        user_tal_res = self.gutils.execute("SELECT Count(*) FROM user_tailing_reservoirs").fetchone()[0]
        if not user_tal_res:
            user_tal_res = 0
        if user_tal > 0 or user_tal_res > 0:
            if user_tal > 0:
                tailings = self.gutils.execute("SELECT fid, tailings_surf_elev, water_surf_elev FROM user_tailings")
                for tailing in tailings:
                    if tailing[2] != 0 and tailing[1] > tailing[2]:
                        self.uc.bar_error("Tailing depth greater than water depth! Schematize Tailings failed!")
                        self.uc.log_info("Tailing depth greater than water depth! Schematize Tailings failed!")
                        return

                ins_qry = """INSERT INTO tailing_cells (user_tal_fid, name, grid, tailings_surf_elev, water_surf_elev, concentration, geom)
                            SELECT
                                ut.fid,
                                ut.name,
                                g.fid,
                                ROUND(
                                    CASE
                                        WHEN (ut.tailings_surf_elev - g.elevation) < 0 THEN 0
                                        ELSE (ut.tailings_surf_elev - g.elevation)
                                    END,
                                    2 
                                ) AS adjusted_tal_elev,
                                ROUND(
                                    CASE
                                        WHEN (ut.water_surf_elev - g.elevation) > 0 THEN 
                                            CASE
                                                WHEN (ut.tailings_surf_elev - g.elevation) > 0 THEN (ut.water_surf_elev - ut.tailings_surf_elev)
                                                ELSE (ut.water_surf_elev - g.elevation)
                                            END
                                        ELSE 0
                                    END,
                                    2 
                                ) AS adjusted_water_elev,
                                ut.concentration,
                                g.geom
                            FROM
                                grid AS g,
                                user_tailings AS ut
                            WHERE
                                ST_Intersects(CastAutomagic(g.geom), CastAutomagic(ut.geom));
                            """

                self.gutils.execute("DELETE FROM tailing_cells;")
                self.gutils.execute(ins_qry)
                self.repaint_tailings()

            if user_tal_res > 0:
                tailings_res = self.gutils.execute("SELECT fid, wsel, tailings FROM user_tailing_reservoirs")
                for tailing_res in tailings_res:
                    if tailing_res[1] != 0 and tailing_res[2] > tailing_res[1]:
                        self.uc.bar_error("Tailing depth greater than water depth! Schematize Tailings failed!")
                        self.uc.log_info("Tailing depth greater than water depth! Schematize Tailings failed!")
                        return

                ins_qry = """
                            INSERT INTO tailing_reservoirs (user_tal_res_fid, name, grid_fid, wsel, tailings, geom)
                             SELECT
                                utr.fid,
                                utr.name,
                                g.fid,
                                utr.wsel,
                                utr.tailings,
                                g.geom
                            FROM
                                grid AS g,
                                user_tailing_reservoirs AS utr
                            WHERE
                                ST_Intersects(CastAutomagic(g.geom), CastAutomagic(utr.geom));
                            
                          """

                self.gutils.execute("DELETE FROM tailing_reservoirs;")
                self.gutils.execute(ins_qry)
                self.repaint_tailings_res()
            self.uc.bar_info(str(user_tal + user_tal_res) + " user tailing reservoirs schematized!")
            self.uc.log_info(str(user_tal + user_tal_res) + " user tailing reservoirs schematized!")

        else:
            sch_tal = self.gutils.execute("SELECT Count(*) FROM tailing_cells").fetchone()[0]
            if not sch_tal:
                sch_tal = 0
            sch_tal_res = self.gutils.execute("SELECT Count(*) FROM tailing_reservoirs").fetchone()[0]
            if not sch_tal_res:
                sch_tal_res = 0
            if sch_tal > 0 or sch_tal_res > 0:
                if self.uc.question(
                        "There aren't any user tailings."
                        + "\nBut there are "
                        + str(sch_tal + sch_tal_res)
                        + " schematic tailings."
                        + "\n\nDo you want to delete them?"
                ):
                    self.gutils.execute("DELETE FROM tailing_cells;")
                    self.gutils.execute("DELETE FROM tailing_reservoirs;")
                    self.repaint_tailings()
                    self.repaint_tailings_res()
            else:
                self.uc.bar_warn("There aren't any user tailings!")
                self.uc.log_info("There aren't any user tailings!")

    def save_res(self):
        self.reservoir.wsel = self.res_ini_sbox.value()
        self.reservoir.n_value = self.res_n_sbox.value()
        self.reservoir.set_row()
        self.populate_cbos(fid=self.reservoir.fid)

    def save_tal(self):
        self.tailings.tailings_surf_elev = self.tailings_elev_sb.value()
        self.tailings.water_surf_elev = self.wse_sb.value()
        self.tailings.concentration = self.concentration_sb.value()
        self.tailings.set_row()
        self.populate_cbos(fid=self.tailings.fid)

    def save_tal_res(self):
        self.tailings_reservoir.tailings = self.tal_res_elev_sb.value()
        self.tailings_reservoir.wsel = self.wse_tal_res_sb.value()
        self.tailings_reservoir.n_value = self.tal_n_sbox.value()
        self.tailings_reservoir.set_row()
        self.populate_cbos(fid=self.tailings_reservoir.fid)

    def save_chan_seg(self):
        self.chan_seg.depinitial = self.seg_ini_sbox.value()
        self.chan_seg.set_row()
        self.populate_cbos(fid=self.chan_seg.fid)

    def save_seg_init_depth(self):
        pass

    def create_point_tailings(self):
        """
        Function to create tailing reservoirs
        """
        if self.lyrs.any_lyr_in_edit('user_tailing_reservoirs'):
            self.uc.bar_info(f"Tailings saved!")
            self.uc.log_info(f"Tailings saved!")
            self.lyrs.save_lyrs_edits('user_tailing_reservoirs')
            self.add_point_tailings_btn.setChecked(False)
            self.gutils.fill_empty_point_tailings_names()
            self.populate_cbos()
            return
        else:
            self.lyrs.enter_edit_mode("user_tailing_reservoirs")

    def create_tailings(self):
        """
        Start editing tailings
        """
        if self.lyrs.any_lyr_in_edit('user_tailings'):
            self.uc.bar_info(f"Tailings saved!")
            self.uc.log_info(f"Tailings saved!")
            self.lyrs.save_lyrs_edits('user_tailings')
            self.add_tailings_btn.setChecked(False)
            self.gutils.fill_empty_tailings_names()
            self.populate_cbos()
            return
        else:
            self.lyrs.enter_edit_mode("user_tailings")

    def save_tailings_edits(self):
        """
        Save the tailings shapefile
        """
        self.tal_lyr.commitChanges()
        self.tailings_cbo.clear()
        self.tailings_cbo.addItem(self.tal_lyr.name(), self.tal_lyr.dataProvider().dataSourceUri())

        # enable the elevations
        self.tailings_elev_sb.setEnabled(True)
        self.wse_sb.setEnabled(True)
        self.export_tailings_btn.setEnabled(True)
        self.concentration_sb.setEnabled(True)
        self.label_3.setEnabled(True)
        self.label_4.setEnabled(True)
        self.label_5.setEnabled(True)

    def delete_chan(self):
        """
        Delete schematized channel
        """
        if not self.chan_seg_cbo.count():
            return
        q = "Are you sure you want delete the current schematized channel?"
        if not self.uc.question(q):
            return
        self.chan_seg.del_row()
        self.repaint_chan_seg()
        self.lyrs.clear_rubber()
        self.populate_cbos()

    def delete_tailings(self):
        """
        Delete tailings
        """
        if not self.tailings_cbo.count():
            return
        q = "Are you sure you want delete the current tailings?"
        if not self.uc.question(q):
            return
        self.tailings.del_row()
        self.repaint_tailings()
        self.lyrs.clear_rubber()
        self.populate_cbos()

    def delete_tailings_res(self):
        """
        Function to delete tailings reservoirs
        """
        if not self.tailing_res_cbo.count():
            return
        q = "Are you sure you want delete the current tailings?"
        if not self.uc.question(q):
            return
        self.tailings_reservoir.del_row()
        self.repaint_tailings_res()
        self.lyrs.clear_rubber()
        self.populate_cbos()

    def check_cbos(self):
        """
        Function to adjust the cbos based on the simulation type
        """
        self.tailings_stack_grp.setEnabled(True)
        self.tailings_res_grp.setEnabled(True)
        self.water_res_grp.setEnabled(True)
        self.add_tailings_btn.setEnabled(True)
        self.add_point_tailings_btn.setEnabled(True)
        self.add_user_res_btn.setEnabled(True)

        # Block tailings stacks (TAILINGS_*.DAT) if reservoirs are assigned (INFLOW.DAT).
        if self.res_cbo.count() != 0 or self.tailing_res_cbo.count() != 0:
            self.tailings_stack_grp.setEnabled(False)
            self.add_tailings_btn.setEnabled(False)
            self.tailings_res_grp.setEnabled(True)
            self.water_res_grp.setEnabled(True)
            self.add_user_res_btn.setEnabled(True)

        # Block reservoirs (INFLOW.DAT) if tailings (TAILINGS_*.DAT) are assigned.
        if self.tailings_cbo.count() != 0:
            self.tailings_stack_grp.setEnabled(True)
            self.tailings_res_grp.setEnabled(False)
            self.add_point_tailings_btn.setEnabled(False)
            self.water_res_grp.setEnabled(False)
            self.add_user_res_btn.setEnabled(False)


