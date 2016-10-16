# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Flo2D
                                 A QGIS plugin
 FLO-2D tools for QGIS
                              -------------------
        begin                : 2016-08-28
        git sha              : $Format:%H$
        copyright            : (C) 2016 by Lutra Consulting for FLO-2D
        email                : info@lutraconsulting.co.uk
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from .utils import *
from ..flo2dgeopackage import GeoPackageUtils
from ..flo2dobjects import Outflow
from ..user_communication import UserCommunication
from plot_widget import PlotWidget

uiDialog, qtBaseClass = load_ui('outflow_editor')


class OutflowEditorDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, lyrs, outflow_fid=None, parent=None):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self, parent)
        self.iface = iface
        self.con = con
        self.lyrs = lyrs
        self.out_lyr = self.lyrs.get_layer_by_name('Outflow', lyrs.group).layer()
        self.out_lyr_id = self.lyrs.get_layer_by_name('Outflow', lyrs.group).layer().id()
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.setupUi(self)
        self.setup_plot()
        self.setModal(False)
        self.outflow_fid = outflow_fid
        self.outflow = None
        self.types_defined = False
        self.gutils = GeoPackageUtils(con, iface)
        self.outflow_data_model = QStandardItemModel()
        self.populate_outflows_cbo(outflow_fid)


    def setup_plot(self):
        self.plotWidget = PlotWidget()
        self.plotLayout.addWidget(self.plotWidget)

    def reset_gui(self):
        self.hydroCbo.setCurrentIndex(0)
        self.hydroCbo.setDisabled(True)
        self.dataCbo.setDisabled(True)
        self.dataCbo.clear()
        self.outflow_data_model.clear()
        self.dataFrame.setDisabled(True)
        self.plotWidget.clear_plot()
        self.plotWidget.setDisabled(True)

    def define_out_types(self):
        if not self.outflow:
            return
        self.out_types = {
            # TODO: remove data_retr and data_fid
            0: {
                'name': 'No Outflow',
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
                'name': 'Floodplain nad Channel outflow (no hydrograph)',
                'wids': [],
                'data_label': '',
                'tab_head': None
            },
            4: {
                'name': 'Outflow with hydrograph',
                'wids': [self.hydroCbo],
                'data_label': '',
                'tab_head': None
            },
            5: {
                'name': 'Time-stage for Floodplain',
                'wids': [self.dataFrame, self.plotFrame],
                'data_label': 'Time series',
                'tab_head': ["Time", "Stage"]
            },
            6: {
                'name': 'Time-stage for Channel',
                'wids': [self.dataFrame, self.plotFrame],
                'data_label': 'Time series',
                'tab_head': ["Time", "Stage"]
            },
            7: {
                'name': 'Time-stage for Floodplain and free floodplain and channel',
                'wids': [self.dataFrame, self.plotFrame],
                'data_label': 'Time series',
                'tab_head': ["Time", "Stage"]
            },
            8: {
                'name': 'Time-stage for Channel and free floodplain and channel',
                'wids': [self.dataFrame, self.plotFrame],
                'data_label': 'Time series',
                'tab_head': ["Time", "Stage"]
            },
            9: {
                'name': 'Channel stage-discharge (Q(h) parameters)',
                'wids': [self.dataFrame],
                'data_label': 'Q(h) parameters',
                'tab_head': ["Hmax", "Coef", "Exponent"]
            },
            10: {
                'name': 'Channel depth-discharge (Q(h) parameters)',
                'wids': [self.dataFrame],
                'data_label': 'Q(h) parameters',
                'tab_head': ["Hmax", "Coef", "Exponent"]
            },
            11: {
                'name': 'Channel stage-discharge (Q(h) table)',
                'wids': [self.dataFrame, self.plotFrame],
                'data_label': 'Q(h) table',
                'tab_head': ["Depth", "Discharge"]
            }
        }
        self.types_defined = True

    def set_data_widgets(self, outflow_type):
        self.reset_gui()
        out_par = self.out_types[outflow_type]
        for wid in out_par['wids']:
            wid.setEnabled(True)
        self.dataLabel.setText(out_par['data_label'])
        self.tab_head = out_par['tab_head']

        # TODO: add button actions for add, remove, import, apply...

    def show_outflow_rb(self):
        self.lyrs.show_feat_rubber(self.out_lyr_id, self.out_fid)

    def populate_outflows_cbo(self, outflow_fid=None):
        """Read outflow table, populate the cbo and set apropriate outflow"""
        self.outflowNameCbo.clear()
        fid_name = '{} {}'
        all_outflows = self.gutils.execute('SELECT fid, name, type FROM outflow ORDER BY fid;').fetchall()
        if not all_outflows:
            self.uc.bar_info('There is no outflow defined in the outflow GeoPackage table...')
            return
        cur_idx = 0
        for i, row in enumerate(all_outflows):
            row = [x if x is not None else '' for x in row]
            fid, name, typ = row
            outflow_name = fid_name.format(fid, name).strip()
            self.outflowNameCbo.addItem(outflow_name, [fid, typ])
            if fid == outflow_fid:
                cur_idx = i
            else:
                pass
        self.outflowNameCbo.setCurrentIndex(cur_idx)
        self.out_fid, self.type_fid = self.outflowNameCbo.itemData(cur_idx)
        self.outflow = Outflow(self.out_fid, self.con, self.iface)
        row = self.outflow.get_row()
        self.define_out_types()
        self.populate_type_cbo()

        self.outTypeCbo.setCurrentIndex(self.type_fid)
        if self.outflow.hydro_out:
            self.populate_hydrograph_cbo()
            self.hydroCbo.setCurrentIndex(self.outflow.hydro_out)
        self.show_outflow_rb()
        if self.series:
            self.populate_data_cbo(self.series)
        self.outflowNameCbo.currentIndexChanged.connect(self.outflow_changed)

    def outflow_changed(self, out_idx):
        self.out_fid, self.type_fid = self.outflowNameCbo.itemData(out_idx)
        self.show_outflow_rb()
        self.outflow = Outflow(self.out_fid, self.con, self.iface)
        row = self.outflow.get_row()
        self.outTypeCbo.setCurrentIndex(self.type_fid)
        self.out_type_changed(self.type_fid)
        if self.centerChBox.isChecked():
            feat = self.out_lyr.getFeatures(QgsFeatureRequest(self.out_fid)).next()
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def populate_hydrograph_cbo(self):
        nbase = 'O{}'
        self.hydroCbo.addItem('', 0)
        for i in range(1, 10):
            h_name = nbase.format(i)
            self.hydroCbo.addItem(h_name, i)
        self.hydroCbo.currentIndexChanged.connect(self.hydro_cbo_changed)

    def hydro_cbo_changed(self, idx):
        self.outflow.hydro_out = idx

    def populate_type_cbo(self):
        """Populate outflow types cbo and set current type"""
        self.outTypeCbo.clear()
        type_name = '{}. {}'
        for typnr in sorted(self.out_types.iterkeys()):
            outflow_type = type_name.format(typnr, self.out_types[typnr]['name']).strip()
            self.outTypeCbo.addItem(outflow_type, typnr)
        self.outTypeCbo.currentIndexChanged.connect(self.out_type_changed)
        self.dataCbo.currentIndexChanged.connect(self.out_data_changed)

    def out_type_changed(self, typ_idx):
        self.set_data_widgets(typ_idx)
        self.outflow.typ = typ_idx
        self.series = None
        if typ_idx == 4:
            self.hydroCbo.setCurrentIndex(self.outflow.hydro_out)
        elif typ_idx > 4:
            self.series = self.outflow.get_data_fid_name()
            if self.series:
                self.populate_data_cbo(self.series)
            else:
                self.uc.bar_info('There is no data defined for this outflow type...')
        else:
            pass

    def populate_data_cbo(self, series):
        self.dataCbo.clear()
        self.dataCbo.setEnabled(True)
        fid_name = '{} {}'
        initial = series[0]
        cur_idx = 0
        for i, row in enumerate(series):
            row = [x if x is not None else '' for x in row]
            s_fid, name = row
            series_name = fid_name.format(s_fid, name).strip()
            self.dataCbo.addItem(series_name, s_fid)
            if s_fid in initial:
                cur_idx = i
            else:
                pass
        self.dataCbo.setCurrentIndex(cur_idx)
        self.data_fid = self.dataCbo.itemData(cur_idx)
        self.outflow.set_new_data_fid(self.data_fid)

    def out_data_changed(self, data_idx):
        self.data_fid = self.dataCbo.itemData(data_idx)
        self.outflow.set_new_data_fid(self.data_fid)
        self.populate_data_table()

    def populate_data_table(self):
        """Populate table and create plot"""
        self.dataTView.setEnabled(True)
        typ = self.outflow.typ
        head = self.tab_head
        series_data = self.outflow.get_data()
        if not series_data:
            return
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(head)
        for row in series_data:
            items = [QStandardItem(str(x)) if x is not None else QStandardItem('') for x in row]
            model.appendRow(items)
        self.dataTView.setModel(model)
        cols = len(head)
        for col in range(cols):
            self.dataTView.setColumnWidth(col, int(210/cols))
        self.dataTView.horizontalHeader().setStretchLastSection(True)
        for r in range(len(series_data)):
            self.dataTView.setRowHeight(i, 18)
        self.outflow_data_model = model
        if self.plotFrame.isEnabled():
            self.update_plot()

    def update_plot(self):
        """When time series data for plot change, update the plot"""
        self.plotWidget.clear_plot()
        dm = self.outflow_data_model
        x = []
        y = []
        for i in range(dm.rowCount()):
            x.append(float(dm.data(dm.index(i, 0), Qt.DisplayRole)))
            y.append(float(dm.data(dm.index(i, 1), Qt.DisplayRole)))
        self.plotWidget.add_new_plot([x, y])
        self.plotWidget.add_org_plot([x, y])

    def data_table_changed(self):
        """User changed current time series. Populate time series
        data fields and plot"""

    def save_tseries_data(self):
        """Get xsection data and save them in gpkg"""

    def revert_tseries_data_changes(self):
        """Revert any time series data changes made by users (load original
        tseries data from tables)"""

    def test_plot(self):
        x, y = [1, 2, 3, 4, 5, 6, 7, 8], [5, 6, 5, 3, 2, 3, 7, 8]
        self.plotWidget.add_new_plot([x, y])
        x, y = [1, 2, 3, 4, 5, 6, 7, 8], [5, 6, 5, 2, 1, 2, 7, 8]
        self.plotWidget.add_org_plot([x, y])
