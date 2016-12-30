# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt4.QtCore import Qt
from PyQt4.QtGui import QColor, QIcon, QComboBox, QSizePolicy, QInputDialog
from qgis.core import QgsFeatureRequest
from collections import OrderedDict
from .utils import load_ui, center_canvas, try_disconnect
from ..geopackage_utils import GeoPackageUtils
from ..flo2dobjects import Structure
from ..user_communication import UserCommunication
from ..utils import m_fdata, is_number
from table_editor_widget import StandardItemModel, StandardItem, CommandItemEdit
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

        self.data_model = StandardItemModel()

        # inflow plot data variables
        self.t, self.d, self.m = [[], [], []]
        self.ot, self.od, self.om = [[], [], []]
        # outflow plot data variables
        self.d1, self.d2 = [[], []]
        # set button icons
        self.set_icon(self.create_struct_btn, 'mActionCaptureLine.svg')
        self.set_icon(self.save_changes_btn, 'mActionSaveAllEdits.svg')
        self.set_icon(self.revert_changes_btn, 'mActionUndo.svg')
        self.set_icon(self.delete_struct_btn, 'mActionDeleteSelected.svg')
        self.set_icon(self.add_data_btn, 'add_bc_data.svg')
        self.set_icon(self.schem_struct_btn, 'schematize_struct.svg')
        self.set_icon(self.change_struct_name_btn, 'change_name.svg')
        self.set_icon(self.change_data_name_btn, 'change_name.svg')

        # connections
        self.create_struct_btn.clicked.connect(self.create_struct)
        self.delete_struct_btn.clicked.connect(self.delete_struct)
        self.save_changes_btn.clicked.connect(self.save_struct_lyrs_edits)
        self.revert_changes_btn.clicked.connect(self.cancel_struct_lyrs_edits)
        self.add_data_btn.clicked.connect(self.add_data)
        self.schem_struct_btn.clicked.connect(self.schematize_struct)

        self.struct_cbo.activated.connect(self.struct_changed)
        self.type_cbo.activated.connect(self.type_changed)
        self.rating_cbo.activated.connect(self.rating_changed)
        self.data_cbo.activated.connect(self.data_changed)
        self.change_struct_name_btn.clicked.connect(self.change_struct_name)
        self.change_data_name_btn.clicked.connect(self.change_data_name)

    def populate_structs(self, struct_fid=None, show_last_edited=False):
        # print 'in populate structs'
        if not self.iface.f2d['con']:
            return
        self.tview.setModel(self.data_model)
        self.lyrs.clear_rubber()
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

    def populate_rating_cbo(self):
        self.rating_cbo.clear()
        self.rating_types = OrderedDict([
            ('C', {'name': 'Rating curve', 'cbo_idx': 0}),
            ('R', {'name': 'Replacement rating curve', 'cbo_idx': 1}),
            ('T', {'name': 'Rating table', 'cbo_idx': 2}),
            ('F', {'name': 'Culvert equation', 'cbo_idx': 3}),
            ('D', {'name': 'Drain outlet', 'cbo_idx': 4})
        ])
        for typ, data in self.rating_types.iteritems():
            self.rating_cbo.addItem(data['name'], typ)

    @staticmethod
    def set_icon(btn, icon_file):
        idir = os.path.join(os.path.dirname(__file__), '..\\img')
        btn.setIcon(QIcon(os.path.join(idir, icon_file)))

    def show_editor(self, user_bc_table=None, bc_fid=None):
        typ = 'inflow'
        fid = None
        geom_type_map = {
            'user_bc_points': 'point',
            'user_bc_lines': 'line',
            'user_bc_polygons': 'polygon'
        }
        if user_bc_table:
            qry = '''SELECT
                        fid, type
                    FROM
                        in_and_outflows
                    WHERE
                        bc_fid = ? and
                        geom_type = ? and
                        type = (SELECT type FROM {} WHERE fid = ?);'''.format(user_bc_table)
            data = (bc_fid, geom_type_map[user_bc_table], bc_fid)
            fid, typ = self.gutils.execute(qry, data).fetchone()
        self.change_bc_type(typ, fid)

    def schematize_struct(self):
        qry = 'SELECT * FROM all_schem_bc;'
        exist_bc = self.gutils.execute(qry).fetchone()
        if exist_bc:
            if not self.uc.question('There are some inflow grid cells defined already. Overwrite them?'):
                return
        self.schematize_inflows()
        self.schematize_outflows()
        self.lyrs.lyrs_to_repaint = [
            self.lyrs.data['all_schem_bc']['qlyr']
        ]
        self.lyrs.repaint_layers()

    def struct_changed(self):
        # print 'in struct_changed'
        cur_struct_idx = self.struct_cbo.currentIndex()
        sdata = self.struct_cbo.itemData(cur_struct_idx)
        if sdata:
            fid = sdata
            # print 'cur struct fid: ', fid
        else:
            return
        self.data_model.clear()
        self.struct = Structure(fid, self.iface.f2d['con'], self.iface)
        self.struct.get_row()
        # print self.struct.row
        self.type_changed(typ=self.struct.ifporchan)
        self.rating_changed(rating=self.struct.type)

    def type_changed(self, idx=None, typ=None):
        # print 'in type_changed'
        if not self.struct:
            return
        if not typ:
            cur_type_idx = self.type_cbo.currentIndex()
        else:
            cur_type_idx = typ
        self.struct.ifporchan = cur_type_idx
        # print 'cur typ:', cur_type_idx
        self.type_cbo.setCurrentIndex(cur_type_idx)
        self.struct.set_row()

    def rating_changed(self, idx=None, rating=None):
        # print 'in rating_changed'
        if not self.struct:
            return
        if not rating:
            cur_rating_idx = self.rating_cbo.currentIndex()
            cur_rating = self.rating_cbo.itemData(cur_rating_idx)
        else:
            cur_rating = rating
        self.struct.type = cur_rating
        # print 'cur rating: ', cur_rating
        # print 'current type: ', cur_type
        if cur_rating == 'C':
            self.storm_drain_cap_sbox.setDisabled(True)
        elif cur_rating == 'R':
            self.storm_drain_cap_sbox.setDisabled(True)
        elif cur_rating == 'T':
            self.storm_drain_cap_sbox.setDisabled(True)
        elif cur_rating == 'F':
            self.storm_drain_cap_sbox.setDisabled(True)
        elif cur_rating == 'D':
            self.storm_drain_cap_sbox.setEnabled(True)
        else:
            pass
        self.rating_cbo.setCurrentIndex(self.rating_types[cur_rating]['cbo_idx'])
        self.struct.set_row()

    def data_changed(self):
        pass

    def change_struct_name(self):
        pass

    def change_data_name(self):
        new_name, ok = QInputDialog.getText(None, 'Change data name', 'New name:')
        if not ok or not new_name:
            return
        pass

    def save_struct(self):
        new_name = self.struct_cbo.currentText()
        # check if the name was changed
        if not self.inflow.name == new_name:
            if new_name in self.gutils.get_inflow_names():
                msg = 'Structure with name {} already exists in the database. Please, choose another name.'.format(self.struct.name)
                self.uc.show_warn(msg)
                return False
            else:
                self.inflow.name = new_name
        # save current inflow parameters
        self.inflow.set_row()
        self.save_inflow_data()

    def save_data(self):
        ts_data = []
        for i in range(self.bc_data_model.rowCount()):
            # save only rows with a number in the first column
            if is_number(m_fdata(self.bc_data_model, i, 0)) and not isnan(m_fdata(self.bc_data_model, i, 0)):
                ts_data.append(
                    (
                        self.inflow.time_series_fid,
                        m_fdata(self.bc_data_model, i, 0),
                        m_fdata(self.bc_data_model, i, 1),
                        m_fdata(self.bc_data_model, i, 2)
                    )
                )
            else:
                pass
        data_name = self.inflow_tseries_cbo.currentText()
        self.inflow.set_time_series_data(data_name, ts_data)

    def show_struct_rb(self):
        self.lyrs.show_feat_rubber(self.bc_lyr.id(), self.inflow.bc_fid)

    def create_plot(self):
        """Create initial plot"""
        self.plot.clear()
        self.plot.add_item('Original Discharge', [self.ot, self.od], col=QColor("#7dc3ff"), sty=Qt.DotLine)
        self.plot.add_item('Current Discharge', [self.ot, self.od], col=QColor("#0018d4"))
        self.plot.add_item('Original Mud', [self.ot, self.om], col=QColor("#cd904b"), sty=Qt.DotLine)
        self.plot.add_item('Current Mud', [self.ot, self.om], col=QColor("#884800"))

    def update_plot(self):
        """When time series data for plot change, update the plot"""
        self.t, self.d, self.m = [[], [], []]
        for i in range(self.bc_data_model.rowCount()):
            self.t.append(m_fdata(self.bc_data_model, i, 0))
            self.d.append(m_fdata(self.bc_data_model, i, 1))
            self.m.append(m_fdata(self.bc_data_model, i, 2))
        self.plot.update_item('Current Discharge', [self.t, self.d])
        self.plot.update_item('Current Mud', [self.t, self.m])

    def add_data(self):
        pass

    def delete_bc(self):
        pass

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
        # print 'in save struct'
        if not self.gutils or not self.lyrs.any_lyr_in_edit('user_struct'):
            # print 'not 1'
            return
        # ask user if overwrite imported structures, if any
        if not self.gutils.delete_all_imported_structs():
            # print 'not 2'
            self.cancel_struct_lyrs_edits()
            return
        # print 'saving'
        # try to save user layer (geometry additions/changes)
        user_lyr_edited = self.lyrs.save_lyrs_edits('user_struct')
        # if user bc layers were edited
        if user_lyr_edited:
            # print 'struct were edited'
            self.struct_frame.setEnabled(True)
            # populate widgets and show last edited struct
            self.gutils.copy_new_struct_from_user_lyr()
            self.populate_structs(show_last_edited=True)
        self.repaint_structs()



    def delete_struct(self):
        pass



    def repaint_structs(self):
        self.lyrs.lyrs_to_repaint = [
            self.lyrs.data['user_struct']['qlyr']
        ]
        self.lyrs.repaint_layers()
