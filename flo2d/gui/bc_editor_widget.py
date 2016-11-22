# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt4.QtCore import Qt
from PyQt4.QtGui import QStandardItemModel, QStandardItem, QColor, QIcon
from qgis.core import QgsFeatureRequest
from .utils import load_ui, center_canvas, try_disconnect
from ..geopackage_utils import GeoPackageUtils
from ..flo2dobjects import Inflow, Outflow
from ..user_communication import UserCommunication
from ..utils import m_fdata, is_number
from math import isnan
import os


uiDialog, qtBaseClass = load_ui('bc_editor')


class BCEditorWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.plot = plot
        self.table_dock = table
        self.bc_tview = table.bc_tview
        self.lyrs = lyrs
        self.setupUi(self)
        self.outflow_frame.setHidden(True)
        # self.ev_filter = BCEditorEventFilter()
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.inflow = None
        self.outflow = None
        self.define_outflow_types()
        self.populate_outflow_type_cbo()
        self.populate_hydrograph_cbo()
        self.gutils = None
        self.bc_data_model = QStandardItemModel()
        # self.installEventFilter(self.ev_filter)
        # inflow plot data variables
        self.t, self.d, self.m = [[], [], []]
        # outflow plot data variables
        self.d1, self.d2 = [[], []]
        # set button icons
        self.set_icon(self.create_point_bc_btn, 'mActionCapturePoint.svg')
        self.set_icon(self.create_line_bc_btn, 'mActionCaptureLine.svg')
        self.set_icon(self.create_polygon_bc_btn, 'mActionCapturePolygon.svg')
        self.set_icon(self.save_user_bc_edits_btn, 'mActionSaveAllEdits.svg')
        # connections
        self.bc_type_inflow_radio.toggled.connect(self.change_bc_type)
        self.bc_data_model.dataChanged.connect(self.update_plot)
        self.add_inflow_tseries_btn.clicked.connect(self.add_inflow_tseries)
        self.add_outflow_data_btn.clicked.connect(self.add_outflow_data)
        self.save_changes_btn.clicked.connect(self.save_bc)
        self.revert_changes_btn.clicked.connect(self.revert_bc_changes)
        self.create_point_bc_btn.clicked.connect(self.create_point_bc)
        self.create_line_bc_btn.clicked.connect(self.create_line_bc)
        self.create_polygon_bc_btn.clicked.connect(self.create_polygon_bc)
        self.save_user_bc_edits_btn.clicked.connect(self.save_bc_edits)
        self.outflow_hydro_cbo.currentIndexChanged.connect(self.outflow_hydrograph_changed)

    def set_icon(self, btn, icon_file):
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
        # print 'in show_bc_editor', typ, fid
        self.change_bc_type(typ, fid)

    def change_bc_type(self, typ=None, fid=None):
        # print 'in change_bc_type'
        if typ == 'inflow' and self.bc_type_outflow_radio.isChecked():
            self.bc_type_inflow_radio.setChecked(True)
            self.bc_type_outflow_radio.setChecked(False)
        elif typ == 'outflow' and self.bc_type_inflow_radio.isChecked():
            self.bc_type_inflow_radio.setChecked(False)
            self.bc_type_outflow_radio.setChecked(True)
        else:
            pass
        self.lyrs.clear_rubber()
        self.bc_data_model.clear()
        if self.bc_type_inflow_radio.isChecked():
            try_disconnect(self.bc_name_cbo.currentIndexChanged, self.outflow_changed)
            try_disconnect(self.outflow_type_cbo.currentIndexChanged, self.outflow_type_changed)
            try_disconnect(self.outflow_data_cbo.currentIndexChanged, self.outflow_data_changed)
            self.inflow_frame.setVisible(True)
            self.outflow_frame.setVisible(False)
            self.populate_inflows(fid)
        else:
            try_disconnect(self.bc_name_cbo.currentIndexChanged, self.inflow_changed)
            try_disconnect(self.inflow_tseries_cbo.currentIndexChanged, self.inflow_data_changed)
            try_disconnect(self.ifc_fplain_radio.toggled, self.inflow_dest_changed)
            try_disconnect(self.inflow_type_cbo.currentIndexChanged, self.inflow_type_changed)
            try_disconnect(self.outflow_hydro_cbo.currentIndexChanged, self.outflow_hydrograph_changed)
            self.inflow_frame.setVisible(False)
            self.outflow_frame.setVisible(True)
            self.populate_outflows(fid)

    def save_bc(self):
        if self.bc_type_inflow_radio.isChecked():
            self.save_inflow()
        else:
            self.save_outflow()

    def revert_bc_changes(self):
        if self.bc_type_inflow_radio.isChecked():
            self.revert_inflow_changes()
        else:
            self.revert_outflow_changes()

    # INFLOWS

    def reset_inflow_gui(self):
        # print 'in reset_inflow_gui'
        try_disconnect(self.bc_name_cbo.currentIndexChanged, self.inflow_changed)
        try_disconnect(self.inflow_tseries_cbo.currentIndexChanged, self.inflow_data_changed)
        try_disconnect(self.ifc_fplain_radio.toggled, self.inflow_dest_changed)
        try_disconnect(self.inflow_type_cbo.currentIndexChanged, self.inflow_type_changed)
        self.bc_name_cbo.clear()
        self.inflow_tseries_cbo.clear()
        self.bc_data_model.clear()
        self.plot.clear()

    def populate_inflows(self, inflow_fid=None):
        # print 'in populate_inflows'
        """Read inflow and inflow_time_series tables, populate proper combo boxes"""
        if not self.iface.f2d['con']:
            return
        self.reset_inflow_gui()
        self.gutils = GeoPackageUtils(self.iface.f2d['con'], self.iface)
        all_inflows = self.gutils.execute('SELECT fid, name, time_series_fid FROM inflow ORDER BY fid;').fetchall()
        if not all_inflows:
            self.uc.bar_info('There is no inflow defined in the database...')
            return
        cur_name_idx = 0
        for i, row in enumerate(all_inflows):
            row = [x if x is not None else '' for x in row]
            fid, name, ts_fid = row
            if not name:
                name = 'Inflow {}'.format(fid)
            self.bc_name_cbo.addItem(name, [fid, ts_fid])
            if inflow_fid and fid == inflow_fid:
                cur_name_idx = i
        self.in_fid, self.ts_fid = self.bc_name_cbo.itemData(cur_name_idx)
        self.inflow = Inflow(self.in_fid, self.iface.f2d['con'], self.iface)
        self.inflow.get_row()
        self.bc_name_cbo.setCurrentIndex(cur_name_idx)
        self.bc_name_cbo.currentIndexChanged.connect(self.inflow_changed)
        self.ifc_fplain_radio.toggled.connect(self.inflow_dest_changed)
        self.inflow_type_cbo.currentIndexChanged.connect(self.inflow_type_changed)
        self.inflow_changed()

    def inflow_changed(self):
        # print 'in inflow_changed'
        try_disconnect(self.inflow_tseries_cbo.currentIndexChanged, self.inflow_data_changed)
        bc_idx = self.bc_name_cbo.currentIndex()
        cur_data = self.bc_name_cbo.itemData(bc_idx)
        self.bc_data_model.clear()
        if cur_data:
            self.in_fid, self.ts_fid = cur_data
        else:
            return
        self.inflow = Inflow(self.in_fid, self.iface.f2d['con'], self.iface)
        row = self.inflow.get_row()
        if not is_number(self.ts_fid) or self.ts_fid == -1:
            self.ts_fid = 0
        else:
            self.ts_fid = int(self.ts_fid)
        self.inflow_tseries_cbo.setCurrentIndex(self.ts_fid)
        self.inflow_tseries_cbo.currentIndexChanged.connect(self.inflow_data_changed)

        if self.inflow.ident == 'F':
            self.ifc_fplain_radio.setChecked(1)
            self.ifc_chan_radio.setChecked(0)
        elif self.inflow.ident == 'C':
            self.ifc_fplain_radio.setChecked(0)
            self.ifc_chan_radio.setChecked(1)
        else:
            self.ifc_fplain_radio.setChecked(0)
            self.ifc_chan_radio.setChecked(0)
        if not self.inflow.inoutfc == '':
            self.inflow_type_cbo.setCurrentIndex(self.inflow.inoutfc)
        else:
            self.inflow_type_cbo.setCurrentIndex(0)

        self.bc_lyr = self.get_user_bc_lyr_for_geomtype(self.inflow.geom_type)
        self.show_inflow_rb()
        if self.bc_center_chbox.isChecked():
            feat = self.bc_lyr.getFeatures(QgsFeatureRequest(self.inflow.bc_fid)).next()
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

        self.populate_inflow_data_cbo()

    def populate_inflow_data_cbo(self):
        """Read and set inflow properties"""
        # print 'in populate_inflow_data_cbo for inflow ', self.inflow.name, self.inflow.fid
        self.time_series = self.inflow.get_time_series()
        # print 'got series', self.time_series
        if not self.time_series:
            self.uc.bar_warn('No data series for this inflow.')
            return
        try_disconnect(self.inflow_tseries_cbo.currentIndexChanged, self.inflow_data_changed)
        self.inflow_tseries_cbo.clear()
        cur_idx = 0
        for i, row in enumerate(self.time_series):
            row = [x if x is not None else '' for x in row]
            ts_fid, ts_name = row
            if not ts_name:
                ts_name = 'Time series {}'.format(ts_fid)
            self.inflow_tseries_cbo.addItem(ts_name, str(ts_fid))
            if ts_fid == self.inflow.time_series_fid:
                cur_idx = i
        # print 'setting new series fid from idx', cur_idx
        self.inflow.time_series_fid = self.inflow_tseries_cbo.itemData(cur_idx)
        self.inflow_tseries_cbo.setCurrentIndex(cur_idx)
        self.inflow_tseries_cbo.currentIndexChanged.connect(self.inflow_data_changed)
        self.inflow_data_changed()

    def inflow_dest_changed(self):
        if self.ifc_fplain_radio.isChecked():
            self.inflow.ident = 'F'
        else:
            self.inflow.ident = 'C'

    def inflow_type_changed(self):
        self.inflow.inoutfc = self.inflow_type_cbo.currentIndex()

    def inflow_data_changed(self):
        # print 'in inflow_data_changed'
        """Get current time series data, populate data table and create plot"""
        cur_ts_idx = self.inflow_tseries_cbo.currentIndex()
        cur_ts_fid = self.inflow_tseries_cbo.itemData(cur_ts_idx)
        self.plot.clear()
        self.inflow.time_series_fid = cur_ts_fid
        self.infow_tseries_data = self.inflow.get_time_series_data()
        self.bc_data_model.clear()
        self.bc_data_model.setHorizontalHeaderLabels(['Time', 'Discharge', 'Mud'])
        self.ot, self.od, self.om = [[], [], []]
        if not self.infow_tseries_data:
            self.uc.bar_warn('No time series data defined for that inflow.')
            return
        for row in self.infow_tseries_data:
            items = [QStandardItem(str(x)) if x is not None else QStandardItem('') for x in row]
            self.bc_data_model.appendRow(items)
            self.ot.append(row[0] if not row[0] is None else float('NaN'))
            self.od.append(row[1] if not row[1] is None else float('NaN'))
            self.om.append(row[2] if not row[2] is None else float('NaN'))
        if self.bc_data_model.rowCount() < 500:
            self.bc_data_model.setRowCount(500)
        # self.bc_data_model.sort(0)
        self.bc_tview.setModel(self.bc_data_model)
        self.bc_tview.resizeColumnsToContents()
        for i in range(self.bc_data_model.rowCount()):
            self.bc_tview.setRowHeight(i, 20)
        self.bc_tview.horizontalHeader().setStretchLastSection(True)
        for i in range(3):
            self.bc_tview.setColumnWidth(i, 90)
        self.create_inflow_plot()

    def save_inflow(self):
        """Get inflow and time series data from table view and save them to gpkg"""
        self.inflow.name = self.bc_name_cbo.currentText()
        self.inflow.set_row()
        # self.bc_data_model.sort(0)
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
        self.populate_inflows(self.inflow.fid)

    def show_inflow_rb(self):
        self.lyrs.show_feat_rubber(self.bc_lyr.id(), self.inflow.bc_fid)

    def revert_inflow_changes(self):
        """Revert any time-series data changes made by users (load original
        tseries data from tables)"""
        self.populate_inflows(self.inflow.fid)

    def create_inflow_plot(self):
        """Create initial plot"""
        self.plot.add_item('Original Discharge', [self.ot, self.od], col=QColor("#7dc3ff"), sty=Qt.DotLine)
        self.plot.add_item('Current Discharge', [self.ot, self.od], col=QColor("#0018d4"))
        self.plot.add_item('Original Mud', [self.ot, self.om], col=QColor("#cd904b"), sty=Qt.DotLine)
        self.plot.add_item('Current Mud', [self.ot, self.om], col=QColor("#884800"))

    def update_inflow_plot(self):
        """When time series data for plot change, update the plot"""
        self.t, self.d, self.m = [[], [], []]
        for i in range(self.bc_data_model.rowCount()):
            self.t.append(m_fdata(self.bc_data_model, i, 0))
            self.d.append(m_fdata(self.bc_data_model, i, 1))
            self.m.append(m_fdata(self.bc_data_model, i, 2))
        self.plot.update_item('Current Discharge', [self.t, self.d])
        self.plot.update_item('Current Mud', [self.t, self.m])

    def add_inflow_tseries(self):
        # print 'in add_inflow_tseries for inflow fid', self.inflow.time_series_fid
        if not self.inflow.time_series_fid:
            # print 'no inflow series_fid'
            return
        self.inflow.add_time_series()
        self.populate_inflow_data_cbo()
        ts_nr = self.inflow_tseries_cbo.count()
        # print 'nr of elements in tseries cbo: ', ts_nr
        self.inflow_tseries_cbo.setCurrentIndex(ts_nr - 1)

    # OUTFLOWS

    def reset_outflow_gui(self):
        # print 'in reset_outflow_gui'
        try_disconnect(self.bc_name_cbo.currentIndexChanged, self.outflow_changed)
        try_disconnect(self.outflow_type_cbo.currentIndexChanged, self.outflow_type_changed)
        try_disconnect(self.outflow_data_cbo.currentIndexChanged, self.outflow_data_changed)
        self.bc_name_cbo.clear()
        self.outflow_data_cbo.clear()
        self.outflow_type_cbo.setCurrentIndex(0)
        self.outflow_hydro_cbo.setCurrentIndex(0)
        self.outflow_hydro_cbo.setDisabled(True)
        self.outflow_data_cbo.setDisabled(True)
        self.bc_data_model.clear()
        self.plot.clear()

    def set_outflow_widgets(self,outflow_type):
        # print 'in set_outflow_widgets'
        try_disconnect(self.outflow_data_cbo.currentIndexChanged, self.outflow_data_changed)
        self.outflow_data_cbo.clear()
        self.outflow_data_cbo.setDisabled(True)
        if not outflow_type == 4:
            self.outflow_hydro_cbo.setCurrentIndex(0)
            self.outflow_hydro_cbo.setDisabled(True)
        self.bc_data_model.clear()
        self.plot.clear()
        if outflow_type == -1:
            outflow_type = 0
        out_par = self.outflow_types[outflow_type]
        for wid in out_par['wids']:
            wid.setEnabled(True)
        self.outflow_data_label.setText(out_par['data_label'])
        self.outflow_tab_head = out_par['tab_head']

    def populate_outflows(self, outflow_fid=None):
        # print 'in populate_outflows'
        """Read outflow table, populate the cbo and set apropriate outflow"""
        if not self.iface.f2d['con']:
            return
        self.reset_outflow_gui()
        self.gutils = GeoPackageUtils(self.iface.f2d['con'], self.iface)
        all_outflows = self.gutils.execute('SELECT fid, name, type, geom_type FROM outflow ORDER BY fid;').fetchall()
        if not all_outflows:
            self.uc.bar_info('There is no outflow defined in the database...')
            return
        cur_out_idx = 0
        for i, row in enumerate(all_outflows):
            row = [x if x is not None else '' for x in row]
            fid, name, typ, geom_type = row
            if not name:
                name = 'Outflow {}'.format(fid)
            self.bc_name_cbo.addItem(name, [fid, typ, geom_type])
            if fid == outflow_fid:
                cur_out_idx = i

        self.out_fid, self.type_fid, self.geom_type = self.bc_name_cbo.itemData(cur_out_idx)
        self.outflow = Outflow(self.out_fid, self.iface.f2d['con'], self.iface)
        self.outflow.get_row()
        msg =  '''In populate_outflows. Got current outflow row:
        name = {}
        chan_out = {}
        fp_out = {}
        hydro_out = {}
        chan_tser_fid = {}
        chan_qhpar_fid = {}
        chan_qhtab_fid = {}
        fp_tser_fid = {}
        typ = {}
        geom_type = {}
        bc_fid = {}
        '''.format(
            self.outflow.name,
            self.outflow.chan_out,
            self.outflow.fp_out,
            self.outflow.hydro_out,
            self.outflow.chan_tser_fid,
            self.outflow.chan_qhpar_fid,
            self.outflow.chan_qhtab_fid,
            self.outflow.fp_tser_fid,
            self.outflow.typ,
            self.outflow.geom_type,
            self.outflow.bc_fid
        )
        # print msg
        self.bc_lyr = self.get_user_bc_lyr_for_geomtype(self.outflow.geom_type)
        self.show_outflow_rb()
        if self.outflow.hydro_out:
            self.outflow_hydro_cbo.setCurrentIndex(self.outflow.hydro_out)
        self.bc_name_cbo.setCurrentIndex(cur_out_idx)
        self.bc_name_cbo.currentIndexChanged.connect(self.outflow_changed)
        self.outflow_changed()

    def outflow_changed(self):
        # print 'in outflow_changed'
        try_disconnect(self.outflow_type_cbo.currentIndexChanged, self.outflow_type_changed)
        bc_idx = self.bc_name_cbo.currentIndex()
        cur_data = self.bc_name_cbo.itemData(bc_idx)
        self.bc_data_model.clear()
        if cur_data:
            self.out_fid, self.type_fid, self.geom_type = cur_data
        else:
            return
        self.outflow = Outflow(self.out_fid, self.iface.f2d['con'], self.iface)
        self.outflow.get_row()
        if not is_number(self.type_fid) or self.type_fid == -1:
            self.type_fid = 0
        else:
            self.type_fid = int(self.type_fid)
        self.bc_lyr = self.get_user_bc_lyr_for_geomtype(self.outflow.geom_type)
        self.show_outflow_rb()
        if self.bc_center_chbox.isChecked():
            feat = self.bc_lyr.getFeatures(QgsFeatureRequest(self.outflow.bc_fid)).next()
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
        self.outflow_type_cbo.setCurrentIndex(self.type_fid)
        self.outflow_type_cbo.currentIndexChanged.connect(self.outflow_type_changed)
        self.outflow_type_changed()

    def outflow_type_changed(self):
        self.bc_data_model.clear()
        typ_idx = self.outflow_type_cbo.currentIndex()
        # print 'in outflow TYPE changed, typ_idx={}'.format(typ_idx)
        self.set_outflow_widgets(typ_idx)
        # print 'checking hydro_out after set out wids:', self.outflow.hydro_out
        self.outflow.set_type_data(typ_idx)
        # print 'checking hydro_out after set type data ({}):'.format(typ_idx), self.outflow.hydro_out
        # print 'outflow typ: ', self.outflow.typ
        self.populate_outflow_data_cbo()

    def outflow_hydrograph_changed(self):
        # print 'set hydrograph to ', self.outflow_hydro_cbo.currentIndex()
        self.outflow.hydro_out = self.outflow_hydro_cbo.currentIndex()

    def populate_outflow_data_cbo(self):
        # print 'in populate_outflow_data_cbo'
        self.series = None
        if self.outflow.typ == 4:
            # print 'should set hydrograph to ', self.outflow.hydro_out
            try_disconnect(self.outflow_hydro_cbo.currentIndexChanged, self.outflow_hydrograph_changed)
            if self.outflow.hydro_out:
                self.outflow_hydro_cbo.setCurrentIndex(self.outflow.hydro_out)
            else:
                self.outflow_hydro_cbo.setCurrentIndex(1)
            self.outflow_hydro_cbo.currentIndexChanged.connect(self.outflow_hydrograph_changed)
            return
        elif self.outflow.typ > 4:
            self.create_outflow_plot()
            self.series = self.outflow.get_data_fid_name()
        else:
            return
        if not self.series:
            self.uc.bar_warn('No data series for this type of outflow.')
            return
        try_disconnect(self.outflow_data_cbo.currentIndexChanged, self.outflow_data_changed)
        self.outflow_data_cbo.clear()
        self.outflow_data_cbo.setEnabled(True)
        cur_idx = 0
        for i, row in enumerate(self.series):
            row = [x if x is not None else '' for x in row]
            s_fid, name = row
            self.outflow_data_cbo.addItem(name, s_fid)
            if s_fid == self.outflow.get_cur_data_fid():
                cur_idx = i
        data_fid = self.outflow_data_cbo.itemData(cur_idx)
        self.outflow.set_new_data_fid(data_fid)
        self.outflow_data_cbo.setCurrentIndex(cur_idx)
        self.outflow_data_cbo.currentIndexChanged.connect(self.outflow_data_changed)
        self.outflow_data_changed()

    def add_outflow_data(self):
        self.outflow.add_data()
        self.populate_outflow_data_cbo()
        out_nr = self.outflow_data_cbo.count()
        self.outflow_data_cbo.setCurrentIndex(out_nr - 1)

    def outflow_data_changed(self):
        # print 'in outflow_data_changed'
        self.outflow.get_cur_data_fid()
        out_nr = self.outflow_data_cbo.count()
        if not out_nr:
            return
        data_idx = self.outflow_data_cbo.currentIndex()
        data_fid = self.outflow_data_cbo.itemData(data_idx)
        # print 'changind out data fid to: ', data_idx
        self.outflow.set_new_data_fid(data_fid)
        head = self.outflow_tab_head
        series_data = self.outflow.get_data()
        # print 'tseries:', series_data, type(series_data)
        self.d1, self.d2 = [[], []]
        self.bc_data_model.clear()
        self.bc_data_model.setHorizontalHeaderLabels(head)
        # print series_data[:2]
        for row in series_data:
            items = [QStandardItem(str(x)) if x is not None else QStandardItem('') for x in row]
            self.d1.append(row[0] if not row[0] is None else float('NaN'))
            self.d2.append(row[1] if not row[1] is None else float('NaN'))
            self.bc_data_model.appendRow(items)
        if self.bc_data_model.rowCount() < 500:
            self.bc_data_model.setRowCount(500)
        # self.bc_data_model.sort(0)
        self.bc_tview.setEnabled(True)
        self.bc_tview.setModel(self.bc_data_model)
        cols = len(head)
        for col in range(cols):
            self.bc_tview.setColumnWidth(col, int(230/cols))
        self.bc_tview.horizontalHeader().setStretchLastSection(True)
        for i in range(self.bc_data_model.rowCount()):
            self.bc_tview.setRowHeight(i, 20)
        self.update_outflow_plot()

    def create_outflow_plot(self):
        """Create initial plot for the current outflow type"""
        self.plot.clear()
        self.plot_item_name = None
        if self.outflow.typ in [5, 6, 7, 8]:
            self.plot_item_name = 'Time'
        elif self.outflow.typ == 11:
            self.plot_item_name = 'Q(h) table'
        else:
            pass
        self.plot.add_item(self.plot_item_name, [self.d1, self.d2], col=QColor("#0018d4"))

    def update_outflow_plot(self):
        """When time series data for plot change, update the plot"""
        if not self.plot_item_name:
            return
        self.d1, self.d2 = [[], []]
        for i in range(self.bc_data_model.rowCount()):
            self.d1.append(m_fdata(self.bc_data_model, i, 0))
            self.d2.append(m_fdata(self.bc_data_model, i, 1))
        self.plot.update_item(self.plot_item_name, [self.d1, self.d2])

    def populate_hydrograph_cbo(self):
        # print 'in populate_hydrograph_cbo'
        try_disconnect(self.outflow_hydro_cbo.currentIndexChanged, self.outflow_hydrograph_changed)
        self.outflow_hydro_cbo.clear()
        self.outflow_hydro_cbo.addItem('', 0)
        for i in range(1, 10):
            h_name = 'O{}'.format(i)
            self.outflow_hydro_cbo.addItem(h_name, i)
        self.outflow_hydro_cbo.currentIndexChanged.connect(self.outflow_hydrograph_changed)

    def populate_outflow_type_cbo(self):
        # print 'in populate_outflow_type_cbo'
        """Populate outflow types cbo and set current type"""
        self.outflow_type_cbo.clear()
        type_name = '{}. {}'
        for typnr in sorted(self.outflow_types.iterkeys()):
            outflow_type = type_name.format(typnr, self.outflow_types[typnr]['name']).strip()
            self.outflow_type_cbo.addItem(outflow_type, typnr)

    def show_outflow_rb(self):
        self.lyrs.show_feat_rubber(self.bc_lyr.id(), self.outflow.bc_fid)

    def outflow_clicked(self, fid):
        typ = self.gutils.execute('SELECT type FROM outflow WHERE fid={};'.format(fid)).fetchone()[0]
        idx = self.bc_name_cbo.findData([fid, typ])
        if not idx == -1:
            self.bc_name_cbo.setCurrentIndex(idx)
        else:
            self.uc.bar_warn('Couldn\'t find outflow fid={} and type={}'.format(fid, typ))

    def get_user_bc_lyr_for_geomtype(self, geom_type):
        table_name = 'user_bc_{}s'.format(geom_type)
        return self.lyrs.data[table_name]['qlyr']

    def get_bc_def_attrs(self):
        if self.bc_type_inflow_radio.isChecked():
            return {'type': "'inflow'"}
        else:
            return {'type': "'outflow'"}

    def create_point_bc(self):
        self.lyrs.enter_edit_mode('user_bc_points', self.get_bc_def_attrs())

    def create_line_bc(self):
        self.lyrs.enter_edit_mode('user_bc_lines', self.get_bc_def_attrs())

    def create_polygon_bc(self):
        self.lyrs.enter_edit_mode('user_bc_polygons', self.get_bc_def_attrs())

    def save_bc_edits(self):
        bc_tables = ['user_bc_points', 'user_bc_lines', 'user_bc_polygons']
        self.lyrs.save_lyrs_edits(bc_tables)
        # update gui
        if self.bc_type_inflow_radio.isChecked():
            self.populate_inflows()
        else:
            self.populate_outflows()

    def save_outflow(self):
        """Get outflow data from widgets and save them to gpkg"""
        self.outflow.name = self.bc_name_cbo.currentText()
        self.outflow.set_row()
        # self.bc_data_model.sort(0)
        data = []
        for i in range(self.bc_data_model.rowCount()):
            # save only rows with a number in the first column
            if is_number(m_fdata(self.bc_data_model, i, 0)) and not isnan(m_fdata(self.bc_data_model, i, 0)):
                data.append(
                    [m_fdata(self.bc_data_model, i, j) for j in range(self.bc_data_model.columnCount())]
                )
            else:
                pass
        # data = [
        #     [m_fdata(self.bc_data_model, i, j) for j in range(self.bc_data_model.columnCount())]
        #     for i in range(self.bc_data_model.rowCount())
        # ]
        data_name = self.outflow_data_cbo.currentText()
        self.outflow.set_data(data_name, data)
        self.populate_outflows(self.outflow.fid)

    def revert_outflow_changes(self):
        """Revert any time-series data changes made by users (load original
        tseries data from tables)"""
        self.populate_outflows(self.outflow.fid)

    def define_outflow_types(self):
        self.outflow_types = {
            0: {
                'name': 'No outflow',
                'wids': [],
                'data_label': '',
                'tab_head': None
            },
            1: {
                'name': 'Floodplain outflow (no hydrograph)',
                'wids': [],
                'data_label': '',
                'tab_head': None
            },
            2: {
                'name': 'Channel outflow (no hydrograph)',
                'wids': [],
                'data_label': '',
                'tab_head': None
            },
            3: {
                'name': 'Floodplain and channel outflow (no hydrograph)',
                'wids': [],
                'data_label': '',
                'tab_head': None
            },
            4: {
                'name': 'Outflow with hydrograph',
                'wids': [self.outflow_hydro_cbo],
                'data_label': '',
                'tab_head': None
            },
            5: {
                'name': 'Time-stage for floodplain',
                'wids': [self.outflow_data_cbo, self.plot],
                'data_label': 'Time series',
                'tab_head': ["Time", "Stage"]
            },
            6: {
                'name': 'Time-stage for channel',
                'wids': [self.outflow_data_cbo, self.plot],
                'data_label': 'Time series',
                'tab_head': ["Time", "Stage"]
            },
            7: {
                'name': 'Time-stage for floodplain and free floodplain and channel',
                'wids': [self.outflow_data_cbo, self.plot],
                'data_label': 'Time series',
                'tab_head': ["Time", "Stage"]
            },
            8: {
                'name': 'Time-stage for channel and free floodplain and channel',
                'wids': [self.outflow_data_cbo, self.plot],
                'data_label': 'Time series',
                'tab_head': ["Time", "Stage"]
            },
            9: {
                'name': 'Channel stage-discharge (Q(h) parameters)',
                'wids': [self.outflow_data_cbo],
                'data_label': 'Q(h) parameters',
                'tab_head': ["Hmax", "Coef", "Exponent"]
            },
            10: {
                'name': 'Channel depth-discharge (Q(h) parameters)',
                'wids': [self.outflow_data_cbo],
                'data_label': 'Q(h) parameters',
                'tab_head': ["Hmax", "Coef", "Exponent"]
            },
            11: {
                'name': 'Channel stage-discharge (Q(h) table)',
                'wids': [self.outflow_data_cbo, self.plot],
                'data_label': 'Q(h) table',
                'tab_head': ["Depth", "Discharge"]
            }
        }

    # common methods
    def create_plot(self):
        """Create initial plot"""
        if self.bc_type_inflow_radio.isChecked():
            self.create_inflow_plot()
        else:
            self.create_outflow_plot()

    def update_plot(self):
        """When data model data change, update the plot"""
        if self.bc_type_inflow_radio.isChecked():
            self.update_inflow_plot()
        else:
            self.update_outflow_plot()
