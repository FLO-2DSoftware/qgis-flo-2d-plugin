# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.PyQt.QtWidgets import QInputDialog
from qgis.core import QgsFeatureRequest
from .ui_utils import load_ui, center_canvas, set_icon
from ..flo2dobjects import Reservoir
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..utils import is_number

uiDialog, qtBaseClass = load_ui('ic_editor')


class ICEditorWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.con = None
        self.gutils = None
        self.uc = UserCommunication(iface, 'FLO-2D')

        # set button icons
        set_icon(self.add_user_res_btn, 'add_reservoir.svg')
        set_icon(self.save_changes_btn, 'mActionSaveAllEdits.svg')
        set_icon(self.revert_changes_btn, 'mActionUndo.svg')
        set_icon(self.delete_res_btn, 'mActionDeleteSelected.svg')
        set_icon(self.schem_res_btn, 'schematize_res.svg')
        set_icon(self.rename_res_btn, 'change_name.svg')

        # connections
        self.add_user_res_btn.clicked.connect(self.create_user_res)
        self.save_changes_btn.clicked.connect(self.save_res_lyr_edits)
        self.revert_changes_btn.clicked.connect(self.revert_res_lyr_edits)
        self.delete_res_btn.clicked.connect(self.delete_cur_res)
        self.schem_res_btn.clicked.connect(self.schematize_res)
        self.rename_res_btn.clicked.connect(self.rename_res)
        self.res_cbo.activated.connect(self.cur_res_changed)
        self.res_ini_sbox.editingFinished.connect(self.save_res)
        self.chan_seg_cbo.activated.connect(self.cur_seg_changed)
        self.seg_ini_sbox.editingFinished.connect(self.save_chan_seg)

    def populate_cbos(self, fid=None, show_last_edited=False):
        if not self.iface.f2d['con']:
            return
        self.res_lyr = self.lyrs.data['user_reservoirs']['qlyr']
        self.chan_lyr = self.lyrs.data['chan']['qlyr']
        self.res_cbo.clear()
        self.chan_seg_cbo.clear()
        self.gutils = GeoPackageUtils(self.iface.f2d['con'], self.iface)
        res_qry = '''SELECT fid, name FROM user_reservoirs ORDER BY name COLLATE NOCASE'''
        rows = self.gutils.execute(res_qry).fetchall()
        max_fid = self.gutils.get_max('user_reservoirs')
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
        seg_qry = '''SELECT fid, name FROM chan ORDER BY name COLLATE NOCASE'''
        rows = self.gutils.execute(seg_qry).fetchall()
        for i, row in enumerate(rows):
            self.chan_seg_cbo.addItem(row[1], row[0])

    def cur_res_changed(self, cur_idx):
        wsel = -1.
        self.res_fid = self.res_cbo.itemData(self.res_cbo.currentIndex())
        self.reservoir = Reservoir(self.res_fid, self.iface.f2d['con'], self.iface)
        self.reservoir.get_row()
        if is_number(self.reservoir.wsel):
            wsel = float(self.reservoir.wsel)
        self.res_ini_sbox.setValue(wsel)
        self.show_res_rb()
        if self.center_res_chbox.isChecked():
            feat = next(self.res_lyr.getFeatures(QgsFeatureRequest(self.reservoir.fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def cur_seg_changed(self, cur_idx):
        depini = -1.
        self.seg_fid = self.chan_seg_cbo.itemData(self.chan_seg_cbo.currentIndex())
        qry = 'SELECT depinitial FROM chan WHERE fid = ?;'
        di = self.gutils.execute(qry, (self.seg_fid, )).fetchone()
        if di and is_number(di[0]):
            depini = float(di[0])
        self.seg_ini_sbox.setValue(depini)
        self.show_chan_rb()
        if self.center_seg_chbox.isChecked():
            feat = next(self.chan_lyr.getFeatures(QgsFeatureRequest(self.seg_fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def show_res_rb(self):
        if not self.reservoir.fid:
            return
        self.lyrs.show_feat_rubber(self.res_lyr.id(), self.reservoir.fid)

    def show_chan_rb(self):
        if not self.seg_fid:
            return
        self.lyrs.show_feat_rubber(self.chan_lyr.id(), self.seg_fid)

    def create_user_res(self):
        self.lyrs.enter_edit_mode('user_reservoirs')

    def save_res_lyr_edits(self):
        if not self.gutils or not self.lyrs.any_lyr_in_edit('user_reservoirs'):
            return
        self.gutils.delete_imported_reservoirs()
        # try to save user bc layers (geometry additions/changes)
        user_res_edited = self.lyrs.save_lyrs_edits('user_reservoirs')
        # if user reservoirs layer was edited
        if user_res_edited:
            self.gutils.fill_empty_reservoir_names()
            # populate widgets and show last edited reservoir
            self.populate_cbos(show_last_edited=True)

    def rename_res(self):
        if not self.res_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, 'Change name', 'New name:')
        if not ok or not new_name:
            return
        if not self.res_cbo.findText(new_name) == -1:
            msg = 'Reservoir with name {} already exists in the database. Please, choose another name.'.format(
                new_name)
            self.uc.show_warn(msg)
            return
        self.reservoir.name = new_name
        self.save_res()

    def repaint_reservoirs(self):
        self.lyrs.lyrs_to_repaint = [
            self.lyrs.data['reservoirs']['qlyr']
        ]
        self.lyrs.repaint_layers()

    def revert_res_lyr_edits(self):
        user_res_edited = self.lyrs.rollback_lyrs_edits('user_reservoirs')
        if user_res_edited:
            self.populate_cbos()

    def delete_cur_res(self):
        if not self.res_cbo.count():
            return
        q = 'Are you sure, you want delete the current reservoir?'
        if not self.uc.question(q):
            return
        self.reservoir.del_row()
        self.repaint_reservoirs()
        self.populate_cbos()

    def schematize_res(self):
        del_qry = 'DELETE FROM reservoirs;'
        ins_qry = '''INSERT INTO reservoirs (user_res_fid, grid_fid, geom)
                    SELECT
                        ur.fid, g.fid, g.geom
                    FROM
                        grid AS g, user_reservoirs AS ur
                    WHERE
                        ST_Intersects(CastAutomagic(g.geom), CastAutomagic(ur.geom));'''
        self.gutils.execute(del_qry)
        self.gutils.execute(ins_qry)
        self.repaint_reservoirs()

    def save_res(self):
        self.reservoir.wsel = self.res_ini_sbox.value()
        self.reservoir.set_row()
        self.populate_cbos(fid=self.reservoir.fid)

    def save_chan_seg(self):
        fid = self.chan_seg_cbo.itemData(self.chan_seg_cbo.currentIndex())
        dini = self.seg_ini_sbox.value()
        qry = 'UPDATE chan SET depinitial = ? WHERE fid = ?;'
        if fid > 0:
            self.gutils.execute(qry, (dini, fid, ))

    def save_seg_init_depth(self):
        pass
