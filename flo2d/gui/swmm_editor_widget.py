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
from PyQt4.QtCore import QSettings, Qt
from PyQt4.QtGui import QApplication, QComboBox, QCheckBox, QDoubleSpinBox, QGroupBox, QInputDialog, QFileDialog, QColor
from qgis.core import QgsFeature, QgsGeometry, QgsPoint, QgsFeatureRequest
from ui_utils import load_ui, center_canvas, try_disconnect, set_icon, switch_to_selected
from flo2d.geopackage_utils import GeoPackageUtils
from flo2d.user_communication import UserCommunication
from flo2d.flo2d_ie.swmm_io import StormDrainProject
from flo2d.flo2d_tools.schema2user_tools import remove_features
from flo2d.flo2dobjects import Inlet
from flo2d.utils import is_number, m_fdata
from table_editor_widget import StandardItemModel, StandardItem, CommandItemEdit
from math import isnan

uiDialog, qtBaseClass = load_ui('swmm_editor')


class SWMMEditorWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, plot, table, lyrs):
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
            'max_depth', 'invert_elev', 'rt_fid', 'outf_flo'
        ]

        self.inlet_columns = ['intype', 'swmm_length', 'swmm_width', 'swmm_height', 'swmm_coeff', 'flapgate', 'curbheight']
        self.outlet_columns = ['outf_flo']

        self.inlet = None
        self.plot = plot
        self.table = table
        self.tview = table.tview
        self.inlet_data_model = StandardItemModel()
        self.inlet_series_data = None
        self.plot_item_name = None
        self.d1, self.d2 = [[], []]

        set_icon(self.create_point_btn, 'mActionCapturePoint.svg')
        set_icon(self.save_changes_btn, 'mActionSaveAllEdits.svg')
        set_icon(self.schema_btn, 'schematize_res.svg')
        set_icon(self.revert_changes_btn, 'mActionUndo.svg')
        set_icon(self.delete_btn, 'mActionDeleteSelected.svg')
        set_icon(self.change_name_btn, 'change_name.svg')

        set_icon(self.show_table_btn, 'show_cont_table.svg')
        set_icon(self.remove_rtable_btn, 'mActionDeleteSelected.svg')
        set_icon(self.add_rtable_btn, 'add_bc_data.svg')
        set_icon(self.rename_rtable_btn, 'change_name.svg')

        self.create_point_btn.clicked.connect(self.create_swmm_point)
        self.save_changes_btn.clicked.connect(self.save_swmm_edits)
        self.revert_changes_btn.clicked.connect(self.revert_swmm_lyr_edits)
        self.delete_btn.clicked.connect(self.delete_cur_swmm)
        self.change_name_btn.clicked.connect(self.rename_swmm)
        self.schema_btn.clicked.connect(self.schematize_swmm)
        self.import_inp.clicked.connect(self.import_swmm_input)
        self.update_inp.clicked.connect(self.update_swmm_input)
        self.recalculate_btn.clicked.connect(self.recalculate_max_depth)
        self.inlet_grp.toggled.connect(self.inlet_checked)
        self.outlet_grp.toggled.connect(self.outlet_checked)

        self.show_table_btn.clicked.connect(self.populate_rtables_data)
        self.add_rtable_btn.clicked.connect(self.add_rtables)
        self.remove_rtable_btn.clicked.connect(self.delete_rtables)
        self.rename_rtable_btn.clicked.connect(self.rename_rtables)
        self.inlet_data_model.dataChanged.connect(self.save_rtables_data)
        self.table.before_paste.connect(self.block_saving)
        self.table.after_paste.connect(self.unblock_saving)
        self.inlet_data_model.itemDataChanged.connect(self.itemDataChangedSlot)

    def inlet_checked(self):
        if self.inlet_grp.isChecked():
            if self.outlet_grp.isChecked():
                self.outlet_grp.setChecked(False)
            if self.cbo_intype.currentIndex() + 1 == 4:
                self.rt_grp.setEnabled(False)

    def outlet_checked(self):
        if self.outlet_grp.isChecked():
            if self.inlet_grp.isChecked():
                self.inlet_grp.setChecked(False)
                self.rt_grp.setDisabled(True)

    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
            self.inlet = Inlet(self.con, self.iface)
            self.grid_lyr = self.lyrs.data['grid']['qlyr']
            self.swmm_lyr = self.lyrs.data['user_swmm']['qlyr']
            self.schema_inlets = self.lyrs.data['swmmflo']['qlyr']
            self.schema_outlets = self.lyrs.data['swmmoutf']['qlyr']
            self.all_schema += [self.schema_inlets, self.schema_outlets]
            self.swmm_lyr.editingStopped.connect(self.populate_swmm)
            self.swmm_lyr.selectionChanged.connect(self.switch2selected)
            self.swmm_name_cbo.activated.connect(self.swmm_changed)
            self.populate_swmm()
            self.populate_rtables()
            self.populate_rtables_data()
            self.cbo_rating_tables.activated.connect(self.populate_rtables_data)
            self.cbo_intype.activated.connect(self.check_intype)

    def switch2selected(self):
        switch_to_selected(self.swmm_lyr, self.swmm_name_cbo)
        self.swmm_changed()

    def check_intype(self):
        intype = self.cbo_intype.currentIndex() + 1
        if intype == 4:
            self.rt_grp.setEnabled(True)
        else:
            self.rt_grp.setDisabled(True)

    def repaint_schema(self):
        for lyr in self.all_schema:
            lyr.triggerRepaint()

    def create_swmm_point(self):
        if not self.lyrs.enter_edit_mode('user_swmm'):
            return

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

    def revert_swmm_lyr_edits(self):
        user_swmm_edited = self.lyrs.rollback_lyrs_edits('user_swmm')
        if user_swmm_edited:
            self.populate_swmm()

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
        for obj in self.flatten(grp):
            if isinstance(obj, QDoubleSpinBox):
                obj_name = obj.objectName().split('_', 1)[-1]
                val = swmm_dict[obj_name]
                obj.setValue(val)
            elif isinstance(obj, QComboBox):
                obj_name = obj.objectName().split('_', 1)[-1]
                val = swmm_dict[obj_name]
                if obj_name == 'intype':
                    val -= 1
                obj.setCurrentIndex(val)
            elif isinstance(obj, QCheckBox):
                obj_name = obj.objectName().split('_', 1)[-1]
                val = swmm_dict[obj_name]
                obj.setChecked(val)
            else:
                continue
        if sd_type == 'I' and swmm_dict['intype'] == 4:
            self.rt_grp.setEnabled(True)
            rt_fid = swmm_dict['rt_fid']
            rt_idx = self.cbo_rating_tables.findData(rt_fid)
            self.cbo_rating_tables.setCurrentIndex(rt_idx)
        else:
            self.rt_grp.setDisabled(True)
        self.lyrs.clear_rubber()
        if self.center_chbox.isChecked():
            sfid = swmm_dict['fid']
            self.lyrs.show_feat_rubber(self.swmm_lyr.id(), sfid)
            feat = self.swmm_lyr.getFeatures(QgsFeatureRequest(sfid)).next()
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def flatten(self, grp):
        objects = []
        for obj in grp.children():
            if isinstance(obj, QGroupBox):
                objects += self.flatten(obj)
            else:
                objects.append(obj)
        return objects

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
        for obj in self.flatten(grp):
            obj_name = obj.objectName().split('_', 1)[-1]
            if isinstance(obj, QDoubleSpinBox):
                swmm_dict[obj_name] = obj.value()
            elif isinstance(obj, QComboBox):
                val = obj.currentIndex()
                if obj_name == 'intype':
                    val += 1
                swmm_dict[obj_name] = val
            elif isinstance(obj, QCheckBox):
                swmm_dict[obj_name] = int(obj.isChecked())
            else:
                continue

        sd_type = swmm_dict['sd_type']
        intype = swmm_dict['intype']
        if sd_type == 'I' and intype != 4:
            if swmm_dict['flapgate'] == 1:
                inlet_type = self.cbo_intype.currentText()
                self.uc.bar_warn('Vertical inlet opening is not allowed for {}!'.format(inlet_type))
                return
            swmm_dict['rt_fid'] = None
        elif sd_type == 'I' and intype == 4:
            swmm_dict['rt_fid'] = self.cbo_rating_tables.itemData(self.cbo_rating_tables.currentIndex())
        else:
            pass

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
        qry_rt_update = '''UPDATE swmmflort SET grid_fid = ? WHERE fid = ?;'''
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            inlets = []
            outlets = []
            rt_updates = []
            for feat in self.swmm_lyr.getFeatures():
                geom = feat.geometry()
                point = geom.asPoint()
                grid_fid = self.gutils.grid_on_point(point.x(), point.y())
                sd_type = feat['sd_type']
                name = feat['name']
                rt_fid = feat['rt_fid']
                if sd_type == 'I':
                    intype = feat['intype']
                    if intype == 4 and rt_fid is not None:
                        rt_updates.append((grid_fid, rt_fid))
                    row = [grid_fid, 'D', grid_fid, name] + [feat[col] for col in self.inlet_columns]
                    inlets.append(row)
                elif sd_type == 'O':
                    row = [grid_fid, grid_fid, name] + [feat[col] for col in self.outlet_columns]
                    outlets.append(row)
                else:
                    raise ValueError
            self.gutils.clear_tables('swmmflo', 'swmmoutf')
            cur = self.con.cursor()
            cur.executemany(qry_inlet, inlets)
            cur.executemany(qry_outlet, outlets)
            cur.executemany(qry_rt_update, rt_updates)
            self.con.commit()
            self.repaint_schema()
            QApplication.restoreOverrideCursor()
            self.uc.bar_info('Schematizing of Storm Drains finished!')
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn('Schematizing of Storm Drains failed! Please check user Storm Drains Points layer.')

    def recalculate_max_depth(self):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            qry = 'SELECT elevation FROM grid WHERE fid = ?;'
            qry_update = 'UPDATE user_swmm SET max_depth=?, rim_elev=?, ge_elev=?, difference=? WHERE fid=?;'
            vals = {}
            if self.selected_ckbox.isChecked():
                request = QgsFeatureRequest().setFilterFids(self.swmm_lyr.selectedFeaturesIds())
                features = self.swmm_lyr.getFeatures(request)
            else:
                features = self.swmm_lyr.getFeatures()
            for feat in features:
                invert_elev = feat['invert_elev']
                geom = feat.geometry()
                point = geom.asPoint()
                grid_fid = self.gutils.grid_on_point(point.x(), point.y())
                elev = self.gutils.execute(qry, (grid_fid,)).fetchone()[0]
                max_depth = elev - invert_elev
                rim_elev = invert_elev + max_depth
                difference = elev - rim_elev
                vals[feat['fid']] = (max_depth, rim_elev, elev, difference)
            cur = self.gutils.con.cursor()
            for k, v in vals.items():
                cur.execute(qry_update, v + (k,))
            self.gutils.con.commit()
            self.populate_swmm()
            QApplication.restoreOverrideCursor()
            self.uc.bar_info('Recalculation of Max Depth finished!')
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn('Recalculation of Max Depth failed!')

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
            sdp.find_junctions()
            remove_features(self.swmm_lyr)
            fields = self.swmm_lyr.fields()
            new_feats = []
            for name, values in sdp.coordinates.items():
                if 'subcatchment' in values:
                    sd_type = 'I'
                elif 'out_type' in values:
                    sd_type = 'O'
                else:
                    continue
                feat = QgsFeature()
                x, y = float(values['x']), float(values['y'])
                max_depth = float(values['max_depth']) if 'max_depth' in values else None
                invert_elev = float(values['invert_elev']) if 'invert_elev' in values else None
                rim_elev = invert_elev + max_depth if invert_elev and max_depth else None
                gid = self.gutils.grid_on_point(x, y)
                elev = self.gutils.grid_value(gid, 'elevation')
                geom = QgsGeometry.fromPoint(QgsPoint(x, y))
                feat.setGeometry(geom)
                feat.setFields(fields)
                feat.setAttribute('sd_type', sd_type)
                feat.setAttribute('name', name)
                feat.setAttribute('max_depth', max_depth)
                feat.setAttribute('invert_elev', invert_elev)
                feat.setAttribute('rim_elev', rim_elev)

                feat.setAttribute('max_depth_inp', max_depth)
                feat.setAttribute('invert_elev_inp', invert_elev)
                feat.setAttribute('rim_elev_inp', rim_elev)
                feat.setAttribute('ge_elev', elev)
                difference = elev - rim_elev if elev and rim_elev else None
                feat.setAttribute('difference', difference)
                new_feats.append(feat)

            self.swmm_lyr.startEditing()
            self.swmm_lyr.addFeatures(new_feats)
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

    def update_swmm_input(self):
        s = QSettings()
        last_dir = s.value('FLO-2D/lastSWMMDir', '')
        swmm_file = QFileDialog.getOpenFileName(
            None,
            'Select SWMM input file to update',
            directory=last_dir,
            filter='(*.inp *.INP*)')
        if not swmm_file:
            return
        s.setValue('FLO-2D/lastSWMMDir', os.path.dirname(swmm_file))
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if self.selected_ckbox.isChecked():
                request = QgsFeatureRequest().setFilterFids(self.swmm_lyr.selectedFeaturesIds())
                features = self.swmm_lyr.getFeatures(request)
            else:
                features = self.swmm_lyr.getFeatures()
            depth_dict = {f['name']: {'invert_elev': f['invert_elev'], 'max_depth': f['max_depth']} for f in features}
            sdp = StormDrainProject(swmm_file)
            sdp.split_by_tags()
            sdp.update_junctions(depth_dict)
            sdp.reassemble_inp()
            QApplication.restoreOverrideCursor()
            self.uc.show_info('Updating SWMM input data finished!')
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn('Updating SWMM input data failed! Please check Storm Drain data.')

    def block_saving(self):
        try_disconnect(self.inlet_data_model.dataChanged, self.save_rtables_data)

    def unblock_saving(self):
        self.inlet_data_model.dataChanged.connect(self.save_rtables_data)

    def itemDataChangedSlot(self, item, old_value, new_value, role, save=True):
        """
        Slot used to push changes of existing items onto undoStack.
        """
        if role == Qt.EditRole:
            command = CommandItemEdit(self, item, old_value, new_value,
                                      "Text changed from '{0}' to '{1}'".format(old_value, new_value))
            self.tview.undoStack.push(command)
            return True

    def populate_rtables(self):
        self.cbo_rating_tables.clear()
        for row in self.inlet.get_rating_tables():
            rt_fid, name = [x if x is not None else '' for x in row]
            self.cbo_rating_tables.addItem(name, rt_fid)

    def add_rtables(self):
        if not self.inlet:
            return
        self.inlet.add_rating_table()
        self.populate_rtables()

    def delete_rtables(self):
        if not self.inlet:
            return
        idx = self.cbo_rating_tables.currentIndex()
        rt_fid = self.cbo_rating_tables.itemData(idx)
        self.inlet.del_rating_table(rt_fid)
        self.populate_rtables()

    def rename_rtables(self):
        if not self.inlet:
            return
        new_name, ok = QInputDialog.getText(None, 'Change rating table name', 'New name:')
        if not ok or not new_name:
            return
        if not self.cbo_rating_tables.findText(new_name) == -1:
            msg = 'Rating table with name {} already exists in the database. Please, choose another name.'.format(
                new_name)
            self.uc.show_warn(msg)
            return
        idx = self.cbo_rating_tables.currentIndex()
        rt_fid = self.cbo_rating_tables.itemData(idx)
        self.inlet.set_rating_table_data_name(rt_fid, new_name)
        self.populate_rtables()

    def populate_rtables_data(self):
        idx = self.cbo_rating_tables.currentIndex()
        rt_fid = self.cbo_rating_tables.itemData(idx)
        self.inlet_series_data = self.inlet.get_rating_tables_data(rt_fid)
        if not self.inlet_series_data:
            return
        self.create_plot()
        self.tview.undoStack.clear()
        self.tview.setModel(self.inlet_data_model)
        self.inlet_data_model.clear()
        self.inlet_data_model.setHorizontalHeaderLabels(['Depth', 'Q'])
        self.d1, self.d1 = [[], []]
        for row in self.inlet_series_data:
            items = [StandardItem('{:.4f}'.format(x)) if x is not None else StandardItem('') for x in row]
            self.inlet_data_model.appendRow(items)
            self.d1.append(row[0] if not row[0] is None else float('NaN'))
            self.d2.append(row[1] if not row[1] is None else float('NaN'))
        rc = self.inlet_data_model.rowCount()
        if rc < 500:
            for row in range(rc, 500 + 1):
                items = [StandardItem(x) for x in ('',) * 2]
                self.inlet_data_model.appendRow(items)
        self.tview.horizontalHeader().setStretchLastSection(True)
        for col in range(2):
            self.tview.setColumnWidth(col, 100)
        for i in range(self.inlet_data_model.rowCount()):
            self.tview.setRowHeight(i, 20)
        self.update_plot()

    def save_rtables_data(self):
        idx = self.cbo_rating_tables.currentIndex()
        rt_fid = self.cbo_rating_tables.itemData(idx)
        self.update_plot()
        rt_data = []

        for i in range(self.inlet_data_model.rowCount()):
            # save only rows with a number in the first column
            if is_number(m_fdata(self.inlet_data_model, i, 0)) and not isnan(m_fdata(self.inlet_data_model, i, 0)):
                rt_data.append(
                    (
                        rt_fid,
                        m_fdata(self.inlet_data_model, i, 0),
                        m_fdata(self.inlet_data_model, i, 1)
                    )
                )
            else:
                pass
        data_name = self.cbo_rating_tables.currentText()
        self.inlet.set_rating_table_data(rt_fid, data_name, rt_data)

    def create_plot(self):
        self.plot.clear()
        self.plot_item_name = 'Rating tables'
        self.plot.add_item(self.plot_item_name, [self.d1, self.d2], col=QColor("#0018d4"))

    def update_plot(self):

        if not self.plot_item_name:
            return
        self.d1, self.d2 = [[], []]
        for i in range(self.inlet_data_model.rowCount()):
            self.d1.append(m_fdata(self.inlet_data_model, i, 0))
            self.d2.append(m_fdata(self.inlet_data_model, i, 1))
        self.plot.update_item(self.plot_item_name, [self.d1, self.d2])
