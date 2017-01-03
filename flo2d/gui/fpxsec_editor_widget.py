# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt4.QtGui import QIcon, QInputDialog
from qgis.core import QgsFeatureRequest
from .utils import load_ui, center_canvas
from ..geopackage_utils import GeoPackageUtils, connection_required
from ..schematic_tools import FloodplainXS
from ..user_communication import UserCommunication

import os


uiDialog, qtBaseClass = load_ui('fpxsec_editor')


class FPXsecEditorWidget(qtBaseClass, uiDialog):

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
        self.set_icon(self.add_user_fpxs_btn, 'add_fpxs.svg')
        self.set_icon(self.save_changes_btn, 'mActionSaveAllEdits.svg')
        self.set_icon(self.revert_changes_btn, 'mActionUndo.svg')
        self.set_icon(self.delete_fpxs_btn, 'mActionDeleteSelected.svg')
        self.set_icon(self.schem_fpxs_btn, 'schematize_fpxs.svg')
        self.set_icon(self.rename_fpxs_btn, 'change_name.svg')
        idir = os.path.join(os.path.dirname(__file__), '..\\img')
        for i in range(8):
            icon_file = 'arrow_{}.svg'.format(i+1)
            self.flow_dir_cbo.setItemIcon(i, QIcon(os.path.join(idir, icon_file)))

        # connections
        self.add_user_fpxs_btn.clicked.connect(self.create_user_fpxs)
        self.save_changes_btn.clicked.connect(self.save_fpxs_lyr_edits)
        self.revert_changes_btn.clicked.connect(self.revert_fpxs_lyr_edits)
        self.delete_fpxs_btn.clicked.connect(self.delete_cur_fpxs)
        self.schem_fpxs_btn.clicked.connect(self.schematize_fpxs)
        self.rename_fpxs_btn.clicked.connect(self.rename_fpxs)
        self.fpxs_cbo.activated.connect(self.cur_fpxs_changed)
        self.flow_dir_cbo.activated.connect(self.save_fpxs)
        self.report_chbox.stateChanged.connect(self.set_report)

    @staticmethod
    def set_icon(btn, icon_file):
        idir = os.path.join(os.path.dirname(__file__), '..\\img')
        btn.setIcon(QIcon(os.path.join(idir, icon_file)))

    def populate_cbos(self, fid=None, show_last_edited=False):
        if not self.iface.f2d['con']:
            return
        self.fpxsec_lyr = self.lyrs.data['user_fpxsec']['qlyr']
        self.fpxs_cbo.clear()
        self.gutils = GeoPackageUtils(self.iface.f2d['con'], self.iface)
        qry = '''SELECT fid, name, iflo FROM user_fpxsec ORDER BY name COLLATE NOCASE'''
        rows = self.gutils.execute(qry).fetchall()
        max_fid = self.gutils.get_max('user_fpxsec')
        cur_idx = 0
        for i, row in enumerate(rows):
            self.fpxs_cbo.addItem(row[1], row)
            if fid and row[0] == fid:
                cur_idx = i
            elif show_last_edited and row[0] == max_fid:
                cur_idx = i
        self.fpxs_cbo.setCurrentIndex(cur_idx)
        self.cur_fpxs_changed(cur_idx)
        self.set_report()

    def cur_fpxs_changed(self, cur_idx):
        row = self.fpxs_cbo.itemData(self.fpxs_cbo.currentIndex())
        if row is None:
            return
        self.fpxs_fid = row[0]
        row_flo = row[-1]
        flow_idx = row_flo - 1 if row_flo is not None else 0
        self.flow_dir_cbo.setCurrentIndex(flow_idx)
        if self.center_fpxs_chbox.isChecked():
            feat = self.fpxsec_lyr.getFeatures(QgsFeatureRequest(self.fpxs_fid)).next()
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def show_fpxs_rb(self):
        if not self.fpxs_fid:
            return
        self.lyrs.show_feat_rubber(self.fpxsec_lyr, self.fpxs_fid)

    def create_user_fpxs(self):
        self.lyrs.enter_edit_mode('user_fpxsec')

    def save_fpxs_lyr_edits(self):
        if not self.gutils or not self.lyrs.any_lyr_in_edit('user_fpxsec'):
            return
        user_fpxs_edited = self.lyrs.save_lyrs_edits('user_fpxsec')
        if user_fpxs_edited:
            self.populate_cbos(show_last_edited=True)

    @connection_required
    def rename_fpxs(self):
        if not self.fpxs_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, 'Change name', 'New name:')
        if not ok or not new_name:
            return
        if not self.fpxs_cbo.findText(new_name) == -1:
            msg = 'Floodplain cross-sections with name {} already exists in the database. Please, choose another name.'
            msg = msg.format(new_name)
            self.uc.show_warn(msg)
            return
        self.fpxs_cbo.setItemText(self.fpxs_cbo.currentIndex(), new_name)
        self.save_fpxs()

    @connection_required
    def revert_fpxs_lyr_edits(self):
        user_fpxs_edited = self.lyrs.rollback_lyrs_edits('user_fpxsec')
        if user_fpxs_edited:
            self.populate_cbos()

    @connection_required
    def delete_cur_fpxs(self):
        if not self.fpxs_cbo.count():
            return
        q = 'Are you sure, you want delete the current floodplain cross-section?'
        if not self.uc.question(q):
            return
        self.gutils.execute('DELETE FROM user_fpxsec WHERE fid = ?;', (self.fpxs_fid,))
        self.fpxsec_lyr.triggerRepaint()
        self.populate_cbos()

    @connection_required
    def save_fpxs(self):
        row = self.fpxs_cbo.itemData(self.fpxs_cbo.currentIndex())
        fid = row[0]
        name = self.fpxs_cbo.currentText()
        iflo = self.flow_dir_cbo.currentText()
        qry = 'UPDATE user_fpxsec SET name = ?, iflo = ? WHERE fid = ?;'
        if fid > 0:
            self.gutils.execute(qry, (name, iflo, fid,))

    @connection_required
    def schematize_fpxs(self):
        self.con = self.iface.f2d['con']
        if not self.con:
            return
        fpxs = FloodplainXS(self.con, self.iface, self.lyrs)
        fpxs.schematize_floodplain_xs()

    @connection_required
    def set_report(self):
        if self.report_chbox.isChecked():
            self.gutils.set_cont_par('NXPRT', '1')
        else:
            self.gutils.set_cont_par('NXPRT', '0')
