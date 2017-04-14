# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
from collections import OrderedDict
from PyQt4.QtCore import pyqtSignal, pyqtSlot
from PyQt4.QtGui import QIcon, QCheckBox, QDoubleSpinBox, QInputDialog
from qgis.core import QgsFeatureRequest
from ui_utils import load_ui, center_canvas
from flo2d.geopackage_utils import GeoPackageUtils, connection_required
from flo2d.user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui('infil_editor')
uiDialog_pop, qtBaseClass_pop = load_ui('infil_global')


class InfilGlobal(uiDialog_pop, qtBaseClass_pop):

    global_changed = pyqtSignal(int)

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.global_imethod = 0
        self.current_imethod = 0
        self.green_grp.toggled.connect(self.green_checked)
        self.scs_grp.toggled.connect(self.scs_checked)
        self.horton_grp.toggled.connect(self.horton_checked)
        self.cb_infchan.stateChanged.connect(self.infchan_changed)

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


class InfilEditorWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = None
        self.gutils = None
        self.infil_lyr = None
        self.infil_idx = 0
        self.iglobal = InfilGlobal(self.iface, self.lyrs)
        self.infmethod = self.iglobal.global_imethod
        self.groups = set()
        self.params = [
            'infmethod', 'abstr', 'sati', 'satf', 'poros', 'soild', 'infchan', 'hydcall', 'soilall', 'hydcadj',
            'hydcxx', 'scsnall', 'abstr1', 'fhortoni', 'fhortonf', 'decaya'
        ]
        self.infil_columns = [
            'green_char', 'hydc', 'soils', 'dtheta', 'abstrinf', 'rtimpf', 'soil_depth', 'hydconch', 'scsn', 'fhorti',
            'fhortf', 'deca'
        ]
        self.imethod_groups = {
            1: {self.iglobal.green_grp},
            2: {self.iglobal.scs_grp},
            3: {self.iglobal.green_grp, self.iglobal.scs_grp},
            4: {self.iglobal.horton_grp}
        }
        self.imethod_groups = {
            1: {self.iglobal.green_grp},
            2: {self.iglobal.scs_grp},
            3: {self.iglobal.green_grp, self.iglobal.scs_grp},
            4: {self.iglobal.horton_grp}
        }
        self.single_groups = {
            1: {self.single_green_grp},
            2: {self.single_scs_grp},
            3: {self.single_green_grp, self.single_scs_grp},
            4: {self.single_horton_grp}
        }
        self.slices = {
            1: slice(0, 8),
            2: slice(8, 9),
            3: slice(0, 9),
            4: slice(9, 12)
        }
        self.set_icon(self.create_polygon_btn, 'mActionCapturePolygon.svg')
        self.set_icon(self.save_changes_btn, 'mActionSaveAllEdits.svg')
        self.set_icon(self.schema_btn, 'schematize_res.svg')
        self.set_icon(self.revert_changes_btn, 'mActionUndo.svg')
        self.set_icon(self.delete_btn, 'mActionDeleteSelected.svg')
        self.set_icon(self.change_name_btn, 'change_name.svg')
        self.create_polygon_btn.clicked.connect(lambda: self.create_infil_polygon())
        self.save_changes_btn.clicked.connect(lambda: self.save_infil_edits())
        self.revert_changes_btn.clicked.connect(lambda: self.revert_infil_lyr_edits())
        self.delete_btn.clicked.connect(lambda: self.delete_cur_infil())
        self.change_name_btn.clicked.connect(lambda: self.rename_infil())
        self.global_params.clicked.connect(lambda: self.show_global_params())
        self.iglobal.global_changed.connect(self.show_groups)
        self.fplain_grp.toggled.connect(self.floodplain_checked)
        self.chan_grp.toggled.connect(self.channel_checked)

    @staticmethod
    def set_icon(btn, icon_file):
        idir = os.path.join(os.path.dirname(__file__), '..\\img')
        btn.setIcon(QIcon(os.path.join(idir, icon_file)))

    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
            self.read_global_params()
            self.infil_lyr = self.lyrs.data['user_infiltration']['qlyr']
            self.infil_lyr.editingStopped.connect(self.populate_infiltration)
            self.infil_name_cbo.activated.connect(self.infiltration_changed)

    @connection_required
    def create_infil_polygon(self):
        if not self.lyrs.enter_edit_mode('user_infiltration'):
            return

    @connection_required
    def rename_infil(self):
        if not self.infil_name_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, 'Change name', 'New name:')
        if not ok or not new_name:
            return
        if not self.infil_name_cbo.findText(new_name) == -1:
            msg = 'Infiltration with name {} already exists in the database. Please, choose another name.'
            msg = msg.format(new_name)
            self.uc.show_warn(msg)
            return
        self.infil_name_cbo.setItemText(self.infil_name_cbo.currentIndex(), new_name)
        self.save_infil_edits()

    @connection_required
    def revert_infil_lyr_edits(self):
        user_infil_edited = self.lyrs.rollback_lyrs_edits('user_infiltration')
        if user_infil_edited:
            self.populate_infiltration()

    @connection_required
    def delete_cur_infil(self):
        if not self.infil_name_cbo.count():
            return
        q = 'Are you sure, you want delete the current infiltration?'
        if not self.uc.question(q):
            return
        infil_fid = self.infil_name_cbo.itemData(self.infil_idx)['fid']
        self.gutils.execute('DELETE FROM user_infiltration WHERE fid = ?;', (infil_fid,))
        self.infil_lyr.triggerRepaint()
        self.populate_infiltration()

    @connection_required
    def save_infil_edits(self):
        before = self.gutils.count('user_infiltration')
        self.lyrs.save_lyrs_edits('user_infiltration')
        after = self.gutils.count('user_infiltration')
        if after > before:
            self.infil_idx = after - 1
        elif self.infil_idx >= 0:
            self.save_attrs()
        else:
            return
        self.populate_infiltration()

    def save_attrs(self):
        infil_dict = self.infil_name_cbo.itemData(self.infil_idx)
        fid = infil_dict['fid']
        name = self.infil_name_cbo.currentText()

        for grp in self.single_groups[self.infmethod]:
            grp_name = grp.objectName()
            if grp_name == 'single_green_grp':
                if self.fplain_grp.isChecked():
                    infil_dict['green_char'] = 'F'
                    grp = self.fplain_grp
                elif self.chan_grp.isChecked():
                    infil_dict['green_char'] = 'C'
                    grp = self.chan_grp
            for obj in grp.children():
                obj_name = obj.objectName().split('_', 1)[-1]
                if isinstance(obj, QDoubleSpinBox):
                    infil_dict[obj_name] = obj.value()
                else:
                    continue

        col_gen = ('{}=?'.format(c) for c in infil_dict.keys()[1:])
        col_names = ', '.join(col_gen)
        vals = [name] + infil_dict.values()[2:] + [fid]
        update_qry = '''UPDATE user_infiltration SET {0} WHERE fid = ?;'''.format(col_names)
        self.gutils.execute(update_qry, vals)

    @connection_required
    def show_global_params(self):
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

    def populate_infiltration(self):
        self.infil_name_cbo.clear()
        imethod = self.infmethod
        if imethod == 0:
            return
        sl = self.slices[imethod]
        columns = self.infil_columns[sl]
        qry = '''SELECT fid, name, {0} FROM user_infiltration ORDER BY fid;'''
        qry = qry.format(' ,'.join(columns))
        columns = ['fid', 'name'] + columns
        rows = self.gutils.execute(qry)
        for row in rows:
            infil_dict = OrderedDict(zip(columns, row))
            name = infil_dict['name']
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
            if grp_name == 'single_green_grp':
                green_char = infil_dict['green_char']
                grp = self.fplain_grp if green_char == 'F' else self.chan_grp
                grp.setChecked(True)
            for obj in grp.children():
                if isinstance(obj, QDoubleSpinBox):
                    obj_name = obj.objectName().split('_', 1)[-1]
                    obj.setValue(infil_dict[obj_name])
                else:
                    continue

        if self.center_chbox.isChecked():
            feat = self.infil_lyr.getFeatures(QgsFeatureRequest(infil_dict['fid'])).next()
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    @connection_required
    def read_global_params(self):
        qry = '''SELECT {} FROM infil;'''.format(','.join(self.params))
        glob = self.gutils.execute(qry).fetchone()
        if glob is None:
            self.show_groups()
            return
        row = OrderedDict(zip(self.params, glob))
        try:
            method = row['infmethod']
            self.groups = self.imethod_groups[method]
        except KeyError:
            self.groups = set()
        for grp in self.groups:
            grp.setChecked(True)
            for obj in grp.children():
                if not isinstance(obj, (QDoubleSpinBox, QCheckBox)):
                    continue
                obj_name = obj.objectName()
                name = obj_name.split('_', 1)[-1]
                val = row[name]
                if isinstance(obj, QCheckBox):
                    obj.setChecked(bool(val))
                else:
                    obj.setValue(val)
        self.iglobal.save_imethod()

    @connection_required
    def write_global_params(self):
        qry = '''INSERT INTO infil ({0}) VALUES ({1});'''
        method = self.iglobal.global_imethod
        names = ['infmethod']
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
                name = obj_name.split('_', 1)[-1]
                if isinstance(obj, QCheckBox):
                    val = int(obj.isChecked())
                    obj.setChecked(bool(val))
                else:
                    val = obj.value()
                    obj.setValue(val)
                names.append(name)
                vals.append(val)
        self.gutils.clear_tables('infil')
        names_str = ', '.join(names)
        vals_str = ', '.join(['?'] * len(vals))
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
