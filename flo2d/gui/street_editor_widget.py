# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import traceback

from qgis.core import QgsFeatureRequest
from qgis.PyQt.QtWidgets import QInputDialog

from ..flo2d_tools.schematic_tools import schematize_streets
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from .ui_utils import center_canvas, load_ui, set_icon, switch_to_selected

uiDialog, qtBaseClass = load_ui("street_editor")
uiDialog_pop, qtBaseClass_pop = load_ui("street_global")


class StreetGeneral(uiDialog_pop, qtBaseClass_pop):
    def __init__(self, iface, lyrs):
        qtBaseClass_pop.__init__(self)
        uiDialog_pop.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")


class StreetEditorWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None
        self.street_lyr = None
        self.street_idx = 0

        # Icons:
        set_icon(self.create_street, "mActionCaptureLine.svg")
        set_icon(self.save_changes_btn, "mActionSaveAllEdits.svg")
        set_icon(self.schema_streets, "schematize_streets.svg")
        set_icon(self.revert_changes_btn, "mActionUndo.svg")
        set_icon(self.delete_street_btn, "mActionDeleteSelected.svg")
        set_icon(self.change_street_name_btn, "change_name.svg")

        # Connections:
        self.create_street.clicked.connect(self.create_street_line)
        self.global_params.clicked.connect(self.set_general_params)
        self.save_changes_btn.clicked.connect(self.save_street_edits)
        self.revert_changes_btn.clicked.connect(self.revert_edits)
        self.delete_street_btn.clicked.connect(self.delete_street)
        self.schema_streets.clicked.connect(self.schematize_street_lines)
        self.change_street_name_btn.clicked.connect(self.change_street_name)
        self.street_name_cbo.activated.connect(self.street_changed)

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
            self.street_lyr = self.lyrs.data["user_streets"]["qlyr"]
            self.street_lyr.editingStopped.connect(self.populate_streets)
            self.street_lyr.selectionChanged.connect(self.switch2selected)

    def switch2selected(self):
        switch_to_selected(self.street_lyr, self.street_name_cbo)
        self.street_changed()

    def populate_streets(self):
        self.street_name_cbo.clear()
        qry = """SELECT fid, name, n_value, elevation, curb_height, street_width FROM user_streets ORDER BY fid;"""
        for street in self.gutils.execute(qry):
            name = street[1]
            self.street_name_cbo.addItem(name, street)
        self.street_name_cbo.setCurrentIndex(self.street_idx)
        self.street_changed()

    def street_changed(self):
        self.street_idx = self.street_name_cbo.currentIndex()
        cur_data = self.street_name_cbo.itemData(self.street_idx)
        if cur_data:
            fid, name, n_value, elevation, curb_height, street_width = cur_data
            self.spin_n.setValue(n_value)
            self.spin_e.setValue(elevation)
            self.spin_h.setValue(curb_height)
            self.spin_w.setValue(street_width)
        else:
            return
        self.lyrs.clear_rubber()
        if self.street_center_chbox.isChecked():
            self.lyrs.show_feat_rubber(self.street_lyr.id(), fid)
            feat = next(self.street_lyr.getFeatures(QgsFeatureRequest(fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def create_street_line(self):
        if not self.lyrs.enter_edit_mode("user_streets"):
            return

    def save_street_edits(self):
        """
        Save changes of user street layer.
        """
        before = self.gutils.count("user_streets")
        self.lyrs.save_lyrs_edits("user_streets")
        after = self.gutils.count("user_streets")
        if after > before:
            self.street_idx = after - 1
        elif self.street_idx >= 0:
            self.save_attrs()
        else:
            return
        self.populate_streets()

    def revert_edits(self):
        self.lyrs.rollback_lyrs_edits("user_streets")
        self.populate_streets()

    def save_attrs(self):
        update_qry = """
        UPDATE user_streets
        SET
            name = ?,
            n_value = ?,
            elevation = ?,
            curb_height = ?,
            street_width = ?
        WHERE fid = ?;"""
        fid = self.street_name_cbo.itemData(self.street_idx)[0]
        name = self.street_name_cbo.currentText()
        n = self.spin_n.value()
        elev = self.spin_e.value()
        curb = self.spin_h.value()
        width = self.spin_w.value()
        self.gutils.execute(update_qry, (name, n, elev, curb, width, fid))

    def delete_street(self):
        """
        Delete the current street from user layer.
        """
        if not self.street_name_cbo.count():
            return
        q = "Are you sure, you want delete the current street line?"
        if not self.uc.question(q):
            return
        cur_data = self.street_name_cbo.itemData(self.street_idx)
        if cur_data:
            fid = cur_data[0]
        else:
            return
        del_qry = "DELETE FROM user_streets WHERE fid = ?;"
        self.gutils.execute(del_qry, (fid,))
        self.street_lyr.triggerRepaint()
        if self.street_idx > 0:
            self.street_idx -= 1
        self.populate_streets()

    def schematize_street_lines(self):
        if not self.lyrs.save_edits_and_proceed("Street Lines"):
            return
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return
        if self.gutils.is_table_empty("user_streets"):
            self.uc.bar_warn("There are not any user streets to schematize! Please digitize them before running tool.")
            return
        cell_size = float(self.gutils.get_cont_par("CELLSIZE"))
        try:
            schematize_streets(self.gutils, self.street_lyr, cell_size)
            streets_schem = self.street_lyr = self.lyrs.data["street_seg"]["qlyr"]
            if streets_schem:
                streets_schem.triggerRepaint()
            self.uc.show_info("Streets schematized!")
        except Exception as e:
            self.uc.show_warn("WARNING 060319.1736: Schematizing of streets aborted! Please check Street Lines layer.")
            self.uc.log_info(traceback.format_exc())

    def change_street_name(self):
        new_name, ok = QInputDialog.getText(None, "Change street name", "New name:")
        if not ok or not new_name:
            return
        self.street_name_cbo.setItemText(self.street_idx, new_name)

    def set_general_params(self):
        qry = """SELECT strfno, strman, depx, widst, istrflo FROM street_general;"""
        gen = self.gutils.execute(qry).fetchone()
        street_general = StreetGeneral(self.iface, self.lyrs)
        if gen is not None:
            froude, n, curb, width, i2s = gen
            street_general.global_froude.setValue(froude)
            street_general.global_n.setValue(n)
            street_general.global_curb.setValue(curb)
            street_general.global_width.setValue(width)
            if i2s == 1:
                street_general.inflow_to_street.setChecked(True)
            else:
                street_general.inflow_to_street.setChecked(False)
        ok = street_general.exec_()
        if ok:
            self.gutils.clear_tables("street_general")
            update_qry = """INSERT INTO street_general (strfno, strman, depx, widst, istrflo) VALUES (?,?,?,?,?);"""
            froude = street_general.global_froude.value()
            n = street_general.global_n.value()
            curb = street_general.global_curb.value()
            width = street_general.global_width.value()
            i2s = 1 if street_general.inflow_to_street.isChecked() else 0
            self.gutils.execute(update_qry, (froude, n, curb, width, i2s))
        else:
            return
