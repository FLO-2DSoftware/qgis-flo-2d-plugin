# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt4.QtCore import Qt
from PyQt4.QtGui import QColor, QIcon, QInputDialog
from qgis.core import QgsFeatureRequest
from collections import OrderedDict
from .utils import load_ui, center_canvas
from ..geopackage_utils import GeoPackageUtils
from ..flo2dobjects import Structure
from ..user_communication import UserCommunication
from ..utils import m_fdata, is_number
from table_editor_widget import StandardItemModel, StandardItem
from math import isnan
import os


uiDialog, qtBaseClass = load_ui('struct_editor')


class StructEditorWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.plot = plot
        self.twidget = table
        self.tview = table.tview
        self.lyrs = lyrs
        self.setupUi(self)
        self.populate_rating_cbo()
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.struct = None
        self.gutils = None
        self.define_data_table_head()
        self.data_model = StandardItemModel()

        # set button icons
        self.set_icon(self.create_struct_btn, 'mActionCaptureLine.svg')
        self.set_icon(self.save_changes_btn, 'mActionSaveAllEdits.svg')
        self.set_icon(self.revert_changes_btn, 'mActionUndo.svg')
        self.set_icon(self.delete_struct_btn, 'mActionDeleteSelected.svg')
        self.set_icon(self.schem_struct_btn, 'schematize_struct.svg')
        self.set_icon(self.change_struct_name_btn, 'change_name.svg')

        # connections
        self.data_model.dataChanged.connect(self.save_data)
        self.create_struct_btn.clicked.connect(self.create_struct)
        self.save_changes_btn.clicked.connect(self.save_struct_lyrs_edits)
        self.revert_changes_btn.clicked.connect(self.cancel_struct_lyrs_edits)
        self.delete_struct_btn.clicked.connect(self.delete_struct)
        self.schem_struct_btn.clicked.connect(self.schematize_struct)
        self.struct_cbo.activated.connect(self.struct_changed)
        self.type_cbo.activated.connect(self.type_changed)
        self.rating_cbo.activated.connect(self.rating_changed)
        self.change_struct_name_btn.clicked.connect(self.change_struct_name)
        self.storm_drain_cap_sbox.editingFinished.connect(self.save_stormdrain_capacity)
        self.stormdrain_chbox.stateChanged.connect(self.clear_stormdrain_data)
        self.ref_head_elev_sbox.editingFinished.connect(self.save_head_ref_elev)
        self.culvert_len_sbox.editingFinished.connect(self.save_culvert_len)
        self.culvert_width_sbox.editingFinished.connect(self.save_culvert_width)

    def populate_structs(self, struct_fid=None, show_last_edited=False):
        if not self.iface.f2d['con']:
            return
        self.struct_cbo.clear()
        self.tview.setModel(self.data_model)
        self.lyrs.clear_rubber()
        self.struct_lyr = self.lyrs.data['struct']['qlyr']
        self.user_struct_lyr = self.lyrs.data['user_struct']['qlyr']
        self.gutils = GeoPackageUtils(self.iface.f2d['con'], self.iface)
        all_structs = self.gutils.get_structs_list()
        cur_name_idx = 0
        for i, row in enumerate(all_structs):
            row = [x if x is not None else '' for x in row]
            fid, name, typ, notes = row
            if not name:
                name = 'Structure {}'.format(fid)
            self.struct_cbo.addItem(name, fid)
            if fid == struct_fid:
                cur_name_idx = i
        if not self.struct_cbo.count():
            return
        if show_last_edited:
            cur_name_idx = i
        self.struct_cbo.setCurrentIndex(cur_name_idx)
        self.struct_changed()

    @staticmethod
    def set_icon(btn, icon_file):
        idir = os.path.join(os.path.dirname(__file__), '..\\img')
        btn.setIcon(QIcon(os.path.join(idir, icon_file)))

    def struct_changed(self):
        cur_struct_idx = self.struct_cbo.currentIndex()
        sdata = self.struct_cbo.itemData(cur_struct_idx)
        if sdata:
            fid = sdata
        else:
            return
        self.clear_data_widgets()
        self.data_model.clear()
        self.struct = Structure(fid, self.iface.f2d['con'], self.iface)
        self.struct.get_row()
        self.show_struct_rb()
        if self.center_chbox.isChecked():
            feat = self.user_struct_lyr.getFeatures(QgsFeatureRequest(self.struct.fid)).next()
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

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

        self.show_table_data()

    def type_changed(self, idx):
        if not self.struct:
            return
        if idx is None:
            idx = self.struct.ifporchan
            if is_number(idx):
                self.type_cbo.setCurrentIndex(idx)
        else:
            self.struct.ifporchan = idx
            self.struct.set_row()

    def rating_changed(self, idx):
        if not self.struct:
            return
        if idx is None:
            idx = self.struct.icurvtable
            if is_number(idx):
                self.rating_cbo.setCurrentIndex(idx)
        else:
            self.struct.icurvtable = idx
            self.struct.set_row()

    def twater_changed(self, idx):
        if not self.struct:
            return
        if idx is None:
            idx = self.struct.inoutcont
            if is_number(idx):
                self.twater_effect_cbo.setCurrentIndex(idx)
        else:
            self.struct.inoutcont = idx
            self.struct.set_row()

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

    def schematize_struct(self):
        qry = 'SELECT * FROM struct WHERE geom IS NOT NULL;'
        exist_struct = self.gutils.execute(qry).fetchone()
        if exist_struct:
            if not self.uc.question('There are some schematised structures created already. Overwrite them?'):
                return
        del_qry = 'DELETE FROM struct WHERE fid NOT IN (SELECT fid FROM user_struct);'
        self.gutils.execute(del_qry)
        upd_cells_qry = '''UPDATE struct SET
            inflonod = (
                SELECT g.fid FROM
                    grid AS g,
                    user_struct AS us
                WHERE
                    ST_Intersects(ST_StartPoint(GeomFromGPB(us.geom)), GeomFromGPB(g.geom)) AND
                    us.fid = struct.fid
                LIMIT 1
            ),
            outflonod = (
                SELECT g.fid FROM
                    grid AS g,
                    user_struct AS us
                WHERE
                    ST_Intersects(ST_EndPoint(GeomFromGPB(us.geom)), GeomFromGPB(g.geom)) AND
                    us.fid = struct.fid
                LIMIT 1);'''
        self.gutils.execute(upd_cells_qry)

        upd_stormdrains_qry = '''UPDATE storm_drains SET
                    istormdout = (
                        SELECT outflonod FROM
                            struct
                        WHERE
                            storm_drains.struct_fid = struct.fid
                        LIMIT 1
                    );'''
        self.gutils.execute(upd_stormdrains_qry)

        qry = 'SELECT fid, inflonod, outflonod FROM struct;'
        structs = self.gutils.execute(qry).fetchall()
        for struct in structs:
            fid, inflo, outflo = struct
            geom = self.gutils.build_linestring([inflo, outflo])
            upd_geom_qry = '''UPDATE struct SET geom = ? WHERE fid = ?;'''
            self.gutils.execute(upd_geom_qry, (geom, fid, ))
        self.lyrs.lyrs_to_repaint = [
            self.lyrs.data['struct']['qlyr']
        ]
        self.lyrs.repaint_layers()

    def clear_data_widgets(self):
        self.storm_drain_cap_sbox.clear()
        self.ref_head_elev_sbox.clear()
        self.culvert_len_sbox.clear()
        self.culvert_width_sbox.clear()

    def populate_rating_cbo(self):
        self.rating_cbo.clear()
        self.rating_types = OrderedDict([
            (0, 'Rating curve'),
            (1, 'Rating table'),
            (2, 'Culvert equation')
        ])
        for typ, name in self.rating_types.iteritems():
            self.rating_cbo.addItem(name, typ)

    def change_struct_name(self):
        if not self.struct_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, 'Change name', 'New name (no spaces, max 15 characters):')
        if not ok or not new_name:
            return
        if not self.struct_cbo.findText(new_name) == -1:
            msg = 'Structure with name {} already exists in the database. Please, choose another name.'.format(
                new_name)
            self.uc.show_warn(msg)
            return
        self.struct.name = new_name.replace(' ', '_')[:15]
        self.struct.set_row()
        self.populate_structs(struct_fid=self.struct.fid)

    def save_stormdrain_capacity(self):
        cap = self.storm_drain_cap_sbox.value()
        self.struct.set_stormdrain_capacity(cap)

    def save_head_ref_elev(self):
        self.struct.headrefel = self.ref_head_elev_sbox.value()
        self.struct.set_row()

    def save_culvert_len(self):
        self.struct.clength = self.culvert_len_sbox.value()
        self.struct.set_row()

    def save_culvert_width(self):
        self.struct.cdiameter = self.culvert_width_sbox.value()
        self.struct.set_row()

    def define_data_table_head(self):
        self.tab_heads = {
            0: ['hdepexc', 'coefq', 'expq', 'coefa', 'expa', 'repdep', 'rqcoef', 'rqexp', 'racoef', 'raexp'],
            1: ['hdepth', 'qtable', 'atable'],
            2: ['typec', 'typeen', 'culvertn', 'ke', 'cubase']
        }
        
    def show_table_data(self):
        if not self.struct:
            return
        self.tview.undoStack.clear()
        self.tview.setModel(self.data_model)
        self.struct_data = self.struct.get_table_data()
        self.data_model.clear()
        self.data_model.setHorizontalHeaderLabels(self.tab_heads[self.struct.icurvtable])
        for row in self.struct_data:
            items = [StandardItem(str(x)) if x is not None else StandardItem('') for x in row]
            self.data_model.appendRow(items)
        rc = self.data_model.rowCount()
        if rc < 10:
            for row in range(rc, 10 + 1):
                items = [StandardItem(x) for x in ('',) * len(self.tab_heads[self.struct.icurvtable])]
                self.data_model.appendRow(items)
        self.tview.resizeColumnsToContents()
        for i in range(self.data_model.rowCount()):
            self.tview.setRowHeight(i, 20)
        self.tview.horizontalHeader().setStretchLastSection(True)

    def save_data(self):
        data = []
        for i in range(self.data_model.rowCount()):
            # save only rows with a number in the first column
            if is_number(m_fdata(self.data_model, i, 0)) and not isnan(m_fdata(self.data_model, i, 0)):
                data.append(
                    [m_fdata(self.data_model, i, j) for j in range(self.data_model.columnCount())]
                )
        self.struct.set_table_data(data)

    def show_struct_rb(self):
        self.lyrs.show_feat_rubber(self.user_struct_lyr.id(), self.struct.fid)

    def delete_struct(self):
        if not self.struct_cbo.count() or not self.struct.fid:
            return
        q = 'Are you sure, you want delete the current structure?'
        if not self.uc.question(q):
            return
        old_fid = self.struct.fid
        self.struct.del_row()
        self.repaint_structs()
        # try to set current struct to the last before the deleted one
        try:
            self.populate_structs(struct_fid=old_fid-1)
        except:
            self.populate_structs()

    def create_struct(self):
        if not self.lyrs.enter_edit_mode('user_struct'):
            return
        self.struct_frame.setDisabled(True)

    def cancel_struct_lyrs_edits(self):
        user_lyr_edited = self.lyrs.rollback_lyrs_edits('user_struct')
        if user_lyr_edited:
            try:
                self.populate_structs(self.struct.fid)
            except AttributeError:
                self.populate_structs()
        self.struct_frame.setEnabled(True)

    def save_struct_lyrs_edits(self):
        """Save changes of user layer"""
        if not self.gutils or not self.lyrs.any_lyr_in_edit('user_struct'):
            return
        # ask user if overwrite imported structures, if any
        if not self.gutils.delete_all_imported_structs():
            self.cancel_struct_lyrs_edits()
            return
        # try to save user layer (geometry additions/changes)
        user_lyr_edited = self.lyrs.save_lyrs_edits('user_struct')
        # if user layer was edited
        if user_lyr_edited:
            self.struct_frame.setEnabled(True)
            # populate widgets and show last edited struct
            self.gutils.copy_new_struct_from_user_lyr()
            self.gutils.fill_empty_struct_names()
            self.populate_structs(show_last_edited=True)
        self.repaint_structs()

    def repaint_structs(self):
        self.lyrs.lyrs_to_repaint = [
            self.lyrs.data['user_struct']['qlyr'],
            self.lyrs.data['struct']['qlyr']
        ]
        self.lyrs.repaint_layers()