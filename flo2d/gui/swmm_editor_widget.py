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
from PyQt4.QtCore import QSettings, pyqtSignal, pyqtSlot, Qt
from PyQt4.QtGui import QApplication, QIcon, QComboBox, QCheckBox, QDoubleSpinBox, QInputDialog, QFileDialog, QStandardItemModel, QStandardItem
from qgis.core import QgsFeature,  QgsGeometry, QgsPoint, QgsFeatureRequest
from ui_utils import load_ui, center_canvas
from flo2d.geopackage_utils import GeoPackageUtils, connection_required
from flo2d.user_communication import UserCommunication
from flo2d.flo2d_ie.swmm_import import StormDrainProject
from flo2d.flo2d_tools.schematic_conversion import remove_features

uiDialog, qtBaseClass = load_ui('swmm_editor')


class SWMMEditorWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = None
        self.gutils = None
        self.grid_lyr = None
        self.swmm_lyr = None
        self.schema_inlets = None
        self.schema_outlets = None
        self.all_schema = []
        self.swmm_idx = 0

        self.swmm_columns = [
            'sd_type', 'intype', 'swmm_length', 'swmm_width', 'swmm_height', 'swmm_coeff', 'flapgate', 'curbheight',
            'outf_flo'
        ]

        self.set_icon(self.create_point_btn, 'mActionCapturePoint.svg')
        self.set_icon(self.save_changes_btn, 'mActionSaveAllEdits.svg')
        self.set_icon(self.schema_btn, 'schematize_res.svg')
        self.set_icon(self.revert_changes_btn, 'mActionUndo.svg')
        self.set_icon(self.delete_btn, 'mActionDeleteSelected.svg')
        self.set_icon(self.change_name_btn, 'change_name.svg')

        self.create_point_btn.clicked.connect(lambda: self.create_swmm_point())
        self.save_changes_btn.clicked.connect(lambda: self.save_swmm_edits())
        self.revert_changes_btn.clicked.connect(lambda: self.revert_swmm_lyr_edits())
        self.delete_btn.clicked.connect(lambda: self.delete_cur_swmm())
        self.change_name_btn.clicked.connect(lambda: self.rename_swmm())
        self.schema_btn.clicked.connect(lambda: self.schematize_swmm())
        self.import_inp.clicked.connect(lambda: self.import_swmm_input())
        self.inlet_grp.toggled.connect(self.inlet_checked)
        self.outlet_grp.toggled.connect(self.outlet_checked)

    def inlet_checked(self):
        if self.inlet_grp.isChecked():
            if self.outlet_grp.isChecked():
                self.outlet_grp.setChecked(False)

    def outlet_checked(self):
        if self.outlet_grp.isChecked():
            if self.inlet_grp.isChecked():
                self.inlet_grp.setChecked(False)

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
            self.grid_lyr = self.lyrs.data['grid']['qlyr']
            self.swmm_lyr = self.lyrs.data['user_swmm']['qlyr']
            self.schema_inlets = self.lyrs.data['swmmflo']['qlyr']
            self.schema_outlets = self.lyrs.data['swmmoutf']['qlyr']
            self.all_schema += [self.schema_inlets, self.schema_outlets]
            self.swmm_lyr.editingStopped.connect(self.populate_swmm)
            self.swmm_name_cbo.activated.connect(self.swmm_changed)
            self.populate_swmm()

    def repaint_schema(self):
        for lyr in self.all_schema:
            lyr.triggerRepaint()

    @connection_required
    def create_swmm_point(self):
        if not self.lyrs.enter_edit_mode('user_swmm'):
            return

    @connection_required
    def save_swmm_edits(self):
        before = self.gutils.count('user_swmm')
        self.lyrs.save_lyrs_edits('user_swmm')
        after = self.gutils.count('user_swmm')
        if after > before:
            self.swmm_idx = after - 1
        elif self.swmm_idx >= 0:
            self.save_attrs()
        else:
            return
        self.populate_swmm()

    @connection_required
    def revert_swmm_lyr_edits(self):
        user_swmm_edited = self.lyrs.rollback_lyrs_edits('user_swmm')
        if user_swmm_edited:
            self.populate_swmm()

    @connection_required
    def delete_cur_swmm(self):
        if not self.swmm_name_cbo.count():
            return
        q = 'Are you sure, you want delete the current Storm Drain point?'
        if not self.uc.question(q):
            return
        swmm_fid = self.swmm_name_cbo.itemData(self.swmm_idx)['fid']
        self.gutils.execute('DELETE FROM user_swmm WHERE fid = ?;', (swmm_fid,))
        self.swmm_lyr.triggerRepaint()
        self.populate_swmm()

    @connection_required
    def rename_swmm(self):
        if not self.swmm_name_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, 'Change name', 'New name:')
        if not ok or not new_name:
            return
        if not self.swmm_name_cbo.findText(new_name) == -1:
            msg = 'Storm Drain point with name {} already exists in the database. Please, choose another name.'
            msg = msg.format(new_name)
            self.uc.show_warn(msg)
            return
        self.swmm_name_cbo.setItemText(self.swmm_name_cbo.currentIndex(), new_name)
        self.save_swmm_edits()

    def populate_swmm(self):
        self.swmm_name_cbo.clear()
        columns = self.swmm_columns[:]
        qry = '''SELECT fid, name, {0} FROM user_swmm ORDER BY fid;'''
        qry = qry.format(', '.join(columns))
        columns = ['fid', 'name'] + columns
        rows = self.gutils.execute(qry).fetchall()
        for row in rows:
            swmm_dict = OrderedDict(zip(columns, row))
            name = swmm_dict['name']
            self.swmm_name_cbo.addItem(name, swmm_dict)
        self.swmm_name_cbo.setCurrentIndex(self.swmm_idx)
        self.swmm_changed()

    def swmm_changed(self):
        self.swmm_idx = self.swmm_name_cbo.currentIndex()
        swmm_dict = self.swmm_name_cbo.itemData(self.swmm_idx)
        if not swmm_dict:
            return
        sd_type = swmm_dict['sd_type']
        if sd_type == 'I':
            self.inlet_grp.setChecked(True)
            grp = self.inlet_grp
        elif sd_type == 'O':
            self.outlet_grp.setChecked(True)
            grp = self.outlet_grp
        else:
            return
        for obj in grp.children():
            if isinstance(obj, QDoubleSpinBox):
                obj_name = obj.objectName().split('_', 1)[-1]
                val = swmm_dict[obj_name]
                obj.setValue(val)
            elif isinstance(obj, QComboBox):
                obj_name = obj.objectName().split('_', 1)[-1]
                val = swmm_dict[obj_name]
                obj.setCurrentIndex(val)
            elif isinstance(obj, QCheckBox):
                obj_name = obj.objectName().split('_', 1)[-1]
                val = swmm_dict[obj_name]
                obj.setChecked(val)
            else:
                continue
        self.lyrs.clear_rubber()
        if self.center_chbox.isChecked():
            sfid = swmm_dict['fid']
            self.lyrs.show_feat_rubber(self.swmm_lyr.id(), sfid)
            feat = self.swmm_lyr.getFeatures(QgsFeatureRequest(sfid)).next()
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def save_attrs(self):
        swmm_dict = self.swmm_name_cbo.itemData(self.swmm_idx)
        fid = swmm_dict['fid']
        name = self.swmm_name_cbo.currentText()
        swmm_dict['name'] = name
        if self.inlet_grp.isChecked():
            swmm_dict['sd_type'] = 'I'
            grp = self.inlet_grp
        elif self.outlet_grp.isChecked():
            swmm_dict['sd_type'] = 'O'
            grp = self.outlet_grp
        else:
            return
        for obj in grp.children():
            obj_name = obj.objectName().split('_', 1)[-1]
            if isinstance(obj, QDoubleSpinBox):
                swmm_dict[obj_name] = obj.value()
            elif isinstance(obj, QComboBox):
                swmm_dict[obj_name] = obj.currentIndex()
            elif isinstance(obj, QCheckBox):
                swmm_dict[obj_name] = int(obj.isChecked())
            else:
                continue

        col_gen = ('{}=?'.format(c) for c in swmm_dict.keys())
        col_names = ', '.join(col_gen)
        vals = swmm_dict.values() + [fid]
        update_qry = '''UPDATE user_swmm SET {0} WHERE fid = ?;'''.format(col_names)
        self.gutils.execute(update_qry, vals)

    def schematize_swmm(self):
        qry_inlet = '''
        INSERT INTO swmmflo
        (geom, swmmchar, swmm_jt, swmm_iden, intype, swmm_length, swmm_width, swmm_height, swmm_coeff, flapgate, curbheight)
        VALUES ((SELECT AsGPB(ST_Centroid(GeomFromGPB(geom))) FROM grid WHERE fid=?),?,?,?,?,?,?,?,?,?,?);'''
        qry_outlet = '''
        INSERT INTO swmmoutf
        (geom, grid_fid, name, outf_flo)
        VALUES ((SELECT AsGPB(ST_Centroid(GeomFromGPB(geom))) FROM grid WHERE fid=?),?,?,?);'''
        inlet_columns = self.swmm_columns[1:-1]
        outlet_columns = self.swmm_columns[-1:]
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            inlets = []
            outlets = []
            for feat in self.swmm_lyr.getFeatures():
                geom = feat.geometry()
                point = geom.asPoint()
                grid_fid = self.gutils.grid_on_point(point.x(), point.y())
                sd_type = feat['sd_type']
                name = feat['name']
                if sd_type == 'I':
                    char = 'N' if feat['intype'] == 4 else 'D'
                    row = [grid_fid, char, grid_fid, name] + [feat[col] for col in inlet_columns]
                    inlets.append(row)
                elif sd_type == 'O':
                    row = [grid_fid, grid_fid, name] + [feat[col] for col in outlet_columns]
                    outlets.append(row)
                else:
                    raise ValueError
            self.gutils.clear_tables('swmmflo', 'swmmoutf')
            cur = self.con.cursor()
            cur.executemany(qry_inlet, inlets)
            cur.executemany(qry_outlet, outlets)
            self.con.commit()
            self.repaint_schema()
            QApplication.restoreOverrideCursor()
            self.uc.bar_info('Schematizing of Storm Drains finished!')
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn('Schematizing of Storm Drains failed! Please check user Storm Drains Points layer.')

    def import_swmm_input(self):
        s = QSettings()
        last_dir = s.value('FLO-2D/lastSWMMDir', '')
        swmm_file = QFileDialog.getOpenFileName(
            None,
            'Select SWMM input file to import data',
            directory=last_dir,
            filter='(*.inp *.INP*)')
        if not swmm_file:
            return
        s.setValue('FLO-2D/lastSWMMDir', os.path.dirname(swmm_file))
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            sdp = StormDrainProject(swmm_file)
            sdp.split_by_tags()
            sdp.find_coordinates()
            sdp.find_inlets()
            sdp.find_outlets()
            remove_features(self.swmm_lyr)
            fields = self.swmm_lyr.fields()
            self.swmm_lyr.startEditing()
            for name, values in sdp.coordinates.items():
                if 'subcatchment' in values:
                    sd_type = 'I'
                elif 'out_type' in values:
                    sd_type = 'O'
                else:
                    continue
                feat = QgsFeature()
                x, y = float(values['x']), float(values['y'])
                geom = QgsGeometry.fromPoint(QgsPoint(x, y))
                feat.setGeometry(geom)
                feat.setFields(fields)
                feat.setAttribute('sd_type', sd_type)
                feat.setAttribute('name', name)
                self.swmm_lyr.addFeature(feat)
            self.swmm_lyr.commitChanges()
            self.swmm_lyr.updateExtents()
            self.swmm_lyr.triggerRepaint()
            self.swmm_lyr.removeSelection()
            QApplication.restoreOverrideCursor()
            self.uc.show_info('Importing SWMM input data finished!')
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn('Importing SWMM input data failed! Please check your SWMM input data.')
