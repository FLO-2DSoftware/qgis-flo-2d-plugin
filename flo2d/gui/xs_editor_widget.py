# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt4.QtCore import Qt, QModelIndex
from PyQt4.QtGui import QStandardItemModel, QStandardItem, QIcon
from .utils import load_ui
from ..geopackage_utils import GeoPackageUtils, connection_required
from ..flo2dobjects import CrossSection
from plot_widget import PlotWidget
import os

uiDialog, qtBaseClass = load_ui('xs_editor')


class XsecEditorWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.plot = plot
        self.table = table
        self.lyrs = lyrs
        self.user_xs_lyr = lyrs.data['user_xsections']['qlyr']
        self.con = None
        self.cur_xs_fid = None
        # self.xsec_lyr_id = self.lyrs.data['user_xsections']['qlyr'].id()
        self.setupUi(self)
        # self.setup_plot()
        self.xs_data_model = None
        self.set_icon(self.digitize_btn, 'mActionCaptureLine.svg')
        self.set_icon(self.save_changes_btn, 'mActionSaveAllEdits.svg')
        self.set_icon(self.delete_btn, 'mActionDeleteSelected.svg')
        self.set_icon(self.revert_changes_btn, 'mActionUndo.svg')
        self.set_icon(self.schematize_xs_btn, 'schematize_xsec.svg')
        self.set_icon(self.rename_xs_btn, 'change_name.svg')
        # connections
        self.digitize_btn.clicked.connect(self.digitize_xsec)
        self.save_changes_btn.clicked.connect(self.save_user_lyr_edits)
        self.xs_cbo.currentIndexChanged.connect(self.cur_xsec_changed)

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

    def setup_plot(self):
        self.plotWidget = PlotWidget()
        self.plotLayout.addWidget(self.plotWidget)

    @connection_required
    def populate_xsec_cbo(self, show_last_edited=False):
        """populate xsection cbo"""
        self.xs_cbo.clear()
        qry = 'SELECT fid, name FROM user_xsections ORDER BY name COLLATE NOCASE;'
        rows = self.gutils.execute(qry)
        cur_idx = 0
        for i, row in enumerate(rows):
            row = [x if x is not None else '' for x in row]
            fid, name = row
            self.xs_cbo.addItem(name, str(fid))
            if fid == self.cur_xs_fid:
                cur_idx = i
        if show_last_edited:
            cur_idx = i
        self.xs_cbo.setCurrentIndex(cur_idx)
        # self.populate_xsec_data()

    @connection_required
    def digitize_xsec(self, i):
        if not self.lyrs.enter_edit_mode('user_xsections'):
            return
        self.enable_widgets(False)

    def enable_widgets(self, enable=True):
        self.xs_cbo.setEnabled(enable)
        self.rename_xs_btn.setEnabled(enable)
        self.xs_type_cbo.setEnabled(enable)
        self.xs_center_chbox.setEnabled(enable)
        self.n_sbox.setEnabled(enable)

    @connection_required
    def save_user_lyr_edits(self, i):
        if not self.gutils or not self.lyrs.any_lyr_in_edit('user_xsections'):
            return
        # try to save user bc layers (geometry additions/changes)
        user_lyr_edited = self.lyrs.save_lyrs_edits('user_xsections')
        # if user bc layers were edited
        if user_lyr_edited:
            self.gutils.fill_empty_user_xsec_names()
            self.populate_xsec_cbo(show_last_edited=True)
        self.enable_widgets()

    @connection_required
    def populate_xsec_data(self):
        """Get current xsection data and populate all relevant fields of the
        dialog and create xsection plot"""
        cur_index = self.xsecList.selectionModel().selectedIndexes()[0]
        cur_xsec = self.xsecList.model().itemFromIndex(cur_index).text()
        # rubberband
        self.lyrs.show_feat_rubber(self.xsec_lyr_id, int(cur_xsec))
        xs_types = {'R': 'Rectangular', 'V': 'Variable Area', 'T': 'Trapezoidal', 'N': 'Natural'}
        self.xsecTypeCbo.clear()
        for val in xs_types.values():
            self.xsecTypeCbo.addItem(val)
        xs = CrossSection(cur_xsec, self.con, self.iface)
        row = xs.get_row()
        typ = row['type']
        name = xs.get_chan_table()['xsecname'] if typ == 'N' else ''
        index = self.xsecTypeCbo.findText(xs_types[typ], Qt.MatchFixedString)
        self.xsecTypeCbo.setCurrentIndex(index)
        self.xsecNameEdit.setText(name)
        self.chanLenEdit.setText(str(row['xlen']))
        self.mannEdit.setText(str(row['fcn']))
        self.notesEdit.setText(str(row['notes']))
        chan = xs.get_chan_table()
        xy = xs.get_xsec_data()

        model = QStandardItemModel()
        if not xy:
            model.setHorizontalHeaderLabels([''])
            for val in chan.itervalues():
                item = QStandardItem(str(val))
                model.appendRow(item)
            model.setVerticalHeaderLabels(chan.keys())
            data_len = len(chan)
        else:
            model.setHorizontalHeaderLabels(['Station', 'Elevation'])
            for i, pt in enumerate(xy):
                x, y = pt
                xi = QStandardItem(str(x))
                yi = QStandardItem(str(y))
                model.appendRow([xi, yi])
            data_len = len(xy)
        self.xsecDataTView.setModel(model)
        self.xs_data_model = model
        for i in range(data_len):
            self.xsecDataTView.setRowHeight(i, 18)
        self.xsecDataTView.resizeColumnsToContents()
        if self.xsecTypeCbo.currentText() == 'Natural':
            self.update_plot()
        else:
            pass

    @connection_required
    def apply_new_xsec_data(self):
        """Get xsection data and save them in gpkg"""

    @connection_required
    def revert_xsec_data_changes(self):
        """Revert any xsection data changes made by users (load original
        xsection data from tables)"""

    @connection_required
    def update_plot(self):
        """When xsection data for plot change, update the plot"""
        self.plotWidget.clear()
        dm = self.xs_data_model
        x = []
        y = []
        for i in range(dm.rowCount()):
            x.append(float(dm.data(dm.index(i, 0), Qt.DisplayRole)))
            y.append(float(dm.data(dm.index(i, 1), Qt.DisplayRole)))
        self.plotWidget.add_new_bed_plot([x, y])
        self.plotWidget.add_org_bed_plot([x, y])

    @connection_required
    def cur_xsec_changed(self, i):
        """User changed current xsection in the xsections list. Populate xsection
        data fields and update the plot"""
        pass