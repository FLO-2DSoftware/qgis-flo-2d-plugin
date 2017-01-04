# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt4.QtCore import Qt, pyqtSignal
from PyQt4.QtGui import QStandardItem, QIcon, QColor, QInputDialog
from qgis.core import QgsFeatureRequest
from .utils import load_ui, center_canvas,try_disconnect
from ..utils import m_fdata, is_number
from ..geopackage_utils import GeoPackageUtils, connection_required
from ..flo2dobjects import UserCrossSection, ChannelSegment
from ..user_communication import UserCommunication
from table_editor_widget import StandardItemModel, StandardItem, CommandItemEdit
from plot_widget import PlotWidget
import os
from collections import OrderedDict
from math import isnan


uiDialog, qtBaseClass = load_ui('xs_editor')


class XsecEditorWidget(qtBaseClass, uiDialog):

    schematize_1d = pyqtSignal()
    find_confluences = pyqtSignal()

    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.plot = plot
        self.table = table
        self.tview = table.tview
        self.lyrs = lyrs
        self.con = None
        self.cur_xs_fid = None
        self.setupUi(self)
        self.populate_xsec_type_cbo()
        self.xi, self.yi = [[], []]
        self.create_plot()
        self.xs_data_model = StandardItemModel()
        self.tview.setModel(self.xs_data_model)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.set_icon(self.digitize_btn, 'mActionCaptureLine.svg')
        self.set_icon(self.save_changes_btn, 'mActionSaveAllEdits.svg')
        self.set_icon(self.delete_btn, 'mActionDeleteSelected.svg')
        self.set_icon(self.revert_changes_btn, 'mActionUndo.svg')
        self.set_icon(self.schematize_xs_btn, 'schematize_xsec.svg')
        self.set_icon(self.confluences_btn, 'schematize_confluence.svg')
        self.set_icon(self.rename_xs_btn, 'change_name.svg')
        # connections
        self.digitize_btn.clicked.connect(self.digitize_xsec)
        self.save_changes_btn.clicked.connect(self.save_user_lyr_edits)
        self.revert_changes_btn.clicked.connect(self.cancel_user_lyr_edits)
        self.delete_btn.clicked.connect(self.delete_xs)
        self.xs_cbo.activated.connect(self.cur_xsec_changed)
        self.xs_type_cbo.activated.connect(self.cur_xsec_type_changed)
        self.rename_xs_btn.clicked.connect(self.change_xs_name)
        self.schematize_xs_btn.clicked.connect(self.schematize_xs)
        self.confluences_btn.clicked.connect(self.schematize_confluences)
        self.n_sbox.valueChanged.connect(self.save_n)
        self.xs_data_model.dataChanged.connect(self.save_xs_data)
        self.xs_data_model.itemDataChanged.connect(self.itemDataChangedSlot)
        self.table.before_paste.connect(self.block_saving)
        self.table.after_paste.connect(self.unblock_saving)

    def block_saving(self):
        try_disconnect(self.xs_data_model.dataChanged, self.save_xs_data)

    def unblock_saving(self):
        self.xs_data_model.dataChanged.connect(self.save_xs_data)

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

    def schematize_xs(self):
        self.schematize_1d.emit()

    def interp_bed_and_banks(self):
        qry = 'SELECT fid FROM chan;'
        fids = self.gutils.execute(qry).fetchall()
        for fid in fids:
            seg = ChannelSegment(int(fid[0]), self.con, self.iface)
            if not seg.interpolate_bed():
                return False
        return True

    def schematize_confluences(self):
        self.find_confluences.emit()

    def itemDataChangedSlot(self, item, oldValue, newValue, role, save=True):
        """
        Slot used to push changes of existing items onto undoStack.
        """
        if role == Qt.EditRole:
            command = CommandItemEdit(self, item, oldValue, newValue,
                                      "Text changed from '{0}' to '{1}'".format(oldValue, newValue))
            self.tview.undoStack.push(command)
            return True

    def populate_xsec_type_cbo(self):
        """
        Get current xsection data, populate all relevant fields of the dialog and create xsection plot.
        """
        self.xs_type_cbo.clear()
        self.xs_types = OrderedDict()
        self.xs_types['R'] = {'name': 'Rectangular', 'cbo_idx': 0}
        self.xs_types['N'] = {'name': 'Natural', 'cbo_idx': 1}
        self.xs_types['T'] = {'name': 'Trapezoidal', 'cbo_idx': 2}
        self.xs_types['V'] = {'name': 'Variable Area', 'cbo_idx': 3}
        for typ, data in self.xs_types.iteritems():
            self.xs_type_cbo.addItem(data['name'], typ)

    def setup_plot(self):
        self.plotWidget = PlotWidget()
        self.plotLayout.addWidget(self.plotWidget)

    @connection_required
    def populate_xsec_cbo(self, fid=None, show_last_edited=False):
        """
        Populate xsection cbo.
        """
        self.xs_cbo.clear()
        self.xs_type_cbo.setCurrentIndex(0)
        qry = 'SELECT fid, name FROM user_xsections ORDER BY name COLLATE NOCASE;'
        rows = self.gutils.execute(qry).fetchall()
        if not rows:
            return
        cur_idx = 0
        for i, row in enumerate(rows):
            row = [x if x is not None else '' for x in row]
            row_fid, name = row
            self.xs_cbo.addItem(name, str(row_fid))
            if fid:
                if row_fid == int(fid):
                    cur_idx = i
        if show_last_edited:
            cur_idx = i
        self.xs_cbo.setCurrentIndex(cur_idx)
        self.user_xs_lyr = self.lyrs.data['user_xsections']['qlyr']
        self.enable_widgets(False)
        if self.xs_cbo.count():
            self.enable_widgets()
            self.cur_xsec_changed()

    @connection_required
    def digitize_xsec(self, i):
        def_attr_exp = self.lyrs.data['user_xsections']['attrs_defaults']
        if not self.lyrs.enter_edit_mode('user_xsections', def_attr_exp):
            return
        self.enable_widgets(False)

    def enable_widgets(self, enable=True):
        self.xs_cbo.setEnabled(enable)
        self.rename_xs_btn.setEnabled(enable)
        self.xs_type_cbo.setEnabled(enable)
        self.xs_center_chbox.setEnabled(enable)
        self.n_sbox.setEnabled(enable)

    @connection_required
    def cancel_user_lyr_edits(self, i):
        user_lyr_edited = self.lyrs.rollback_lyrs_edits('user_xsections')
        if user_lyr_edited:
            self.populate_xsec_cbo()

    @connection_required
    def save_user_lyr_edits(self, i):
        if not self.gutils or not self.lyrs.any_lyr_in_edit('user_xsections'):
            return
        # try to save user bc layers (geometry additions/changes)
        user_lyr_edited = self.lyrs.save_lyrs_edits('user_xsections')
        # if user bc layers were edited
        if user_lyr_edited:
            self.gutils.fill_empty_user_xsec_names()
            self.gutils.set_def_n()
            self.populate_xsec_cbo(show_last_edited=True)
        self.enable_widgets()

    def repaint_xs(self):
        self.lyrs.lyrs_to_repaint = [
            self.lyrs.data['user_xsections']['qlyr']
        ]
        self.lyrs.repaint_layers()

    @connection_required
    def cur_xsec_changed(self, idx=0):
        """
        User changed current xsection in the xsections list.
        Populate xsection data fields and update the plot.
        """
        if not self.xs_cbo.count():
            return

        fid = self.xs_cbo.itemData(idx)
        self.lyrs.show_feat_rubber(self.user_xs_lyr.id(), int(fid))
        self.xs = UserCrossSection(fid, self.con, self.iface)
        row = self.xs.get_row()
        if self.xs_center_chbox.isChecked():
            feat = self.user_xs_lyr.getFeatures(QgsFeatureRequest(int(self.xs.fid))).next()
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
        typ = row['type']
        fcn = float(row['fcn']) if is_number(row['fcn']) else float(self.gutils.get_cont_par('MANNING'))
        self.xs_type_cbo.setCurrentIndex(self.xs_types[typ]['cbo_idx'])
        self.n_sbox.setValue(fcn)
        chan_x_row = self.xs.get_chan_x_row()
        if typ == 'N':
            xy = self.xs.get_chan_natural_data()
        else:
            xy = None
        self.xs_data_model.clear()
        self.tview.undoStack.clear()
        if not xy:
            self.plot.clear()
            self.xs_data_model.setHorizontalHeaderLabels(['Value'])
            for val in chan_x_row.itervalues():
                item = StandardItem(str(val))
                self.xs_data_model.appendRow(item)
            self.xs_data_model.setVerticalHeaderLabels(chan_x_row.keys())
            self.xs_data_model.removeRows(0,2)
            self.tview.setModel(self.xs_data_model)
        else:
            self.xs_data_model.setHorizontalHeaderLabels(['Station', 'Elevation'])
            for i, pt in enumerate(xy):
                x, y = pt
                xi = QStandardItem(str(x))
                yi = QStandardItem(str(y))
                self.xs_data_model.appendRow([xi, yi])
            self.tview.setModel(self.xs_data_model)
            rc = self.xs_data_model.rowCount()
            if rc < 500:
                for row in range(rc, 500 + 1):
                    items = [StandardItem(x) for x in ('',) * 2]
                    self.xs_data_model.appendRow(items)
        for i in range(self.xs_data_model.rowCount()):
            self.tview.setRowHeight(i, 20)
        self.tview.horizontalHeader().setStretchLastSection(True)
        for i in range(2):
            self.tview.setColumnWidth(i, 100)

        if self.xs_type_cbo.currentText() == 'Natural':
            self.create_plot()
            self.update_plot()

    @connection_required
    def cur_xsec_type_changed(self, idx):
        # print 'type idx', idx
        typ = self.xs_type_cbo.itemData(idx)
        self.xs.set_type(typ)
        xs_cbo_idx = self.xs_cbo.currentIndex()
        self.cur_xsec_changed(xs_cbo_idx)

    def create_plot(self):
        """
        Create initial plot.
        """
        self.plot.clear()
        self.plot.add_item('Cross-section', [self.xi, self.yi], col=QColor("#0018d4"))

    @connection_required
    def update_plot(self):
        """
        When time series data for plot change, update the plot.
        """
        self.xi, self.yi = [[], []]
        for i in range(self.xs_data_model.rowCount()):
            self.xi.append(m_fdata(self.xs_data_model, i, 0))
            self.yi.append(m_fdata(self.xs_data_model, i, 1))
        self.plot.update_item('Cross-section', [self.xi, self.yi])

    @connection_required
    def save_n(self, n_val):
        self.xs.set_n(n_val)

    @connection_required
    def change_xs_name(self, i):
        if not self.xs_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, 'Change name', 'New name:')
        if not ok or not new_name:
            return
        if not self.xs_cbo.findText(new_name) == -1:
            msg = 'Boundary condition with name {} already exists in the database. Please, choose another name.'.format(
                new_name)
            self.uc.show_warn(msg)
            return
        self.xs.name = new_name
        self.xs.set_name()
        self.populate_xsec_cbo(fid=self.xs.fid)

    def save_xs_data(self):
        if self.xs.type == 'N':
            xiyi = []
            for i in range(self.xs_data_model.rowCount()):
                # save only rows with a number in the first column
                if is_number(m_fdata(self.xs_data_model, i, 0)) and not isnan(m_fdata(self.xs_data_model, i, 0)):
                    xiyi.append(
                        (
                            self.xs.fid,
                            m_fdata(self.xs_data_model, i, 0),
                            m_fdata(self.xs_data_model, i, 1)
                        )
                    )
            self.xs.set_chan_natural_data(xiyi)
            self.update_plot()
        else:
            # parametric xsection
            data = []
            for i in range(self.xs_data_model.rowCount()):
                data.append(
                        (
                            m_fdata(self.xs_data_model, i, 0)
                        )
                    )
            self.xs.set_chan_data(data)

    @connection_required
    def delete_xs(self, i):
        """
        Delete the current cross-section from user layer.
        """
        if not self.xs_cbo.count():
            return
        q = 'Are you sure, you want to delete current cross-section?'
        if not self.uc.question(q):
            return
        fid = None
        xs_idx = self.xs_cbo.currentIndex()
        cur_data = self.xs_cbo.itemData(xs_idx)
        if cur_data:
            fid = int(cur_data[0])
        else:
            return
        qry = '''DELETE FROM user_xsections WHERE fid = ?;'''
        self.gutils.execute(qry, (fid,))

        # try to set current xs to the last before the deleted one
        try:
            self.populate_xsec_cbo(fid=fid-1)
        except:
            self.populate_xsec_cbo()
        self.repaint_xs()
