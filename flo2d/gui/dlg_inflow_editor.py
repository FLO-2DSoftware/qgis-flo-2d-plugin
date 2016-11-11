# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from .utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..flo2dobjects import Inflow
from plot_widget import PlotWidget
from ..user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui('inflow_editor')


class InflowEditorDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, inflow_fid=None, parent=None):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self, parent)
        self.iface = iface
        self.con = con
        self.setupUi(self)
        self.setup_plot()
        self.setModal(False)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.cur_inflow_fid = inflow_fid
        self.inflow = None
        self.gutils = GeoPackageUtils(con, iface)
        self.inflow_data_model = None
        self.populate_inflows(inflow_fid)
        self.tseriesDataTView.horizontalHeader().setStretchLastSection(True)

        # connections
        self.inflowNameCbo.currentIndexChanged.connect(self.populate_inflow_properties)
        self.tseriesCbo.currentIndexChanged.connect(self.populate_tseries_data)

    def setup_plot(self):
        self.plotWidget = PlotWidget()
        self.plotLayout.addWidget(self.plotWidget)

    def populate_inflows(self, inflow_fid=None):
        """Read inflow and inflow_time_series tables, populate proper combo boxes"""
        self.inflowNameCbo.clear()
        fid_name = '{} {}'
        all_inflows = self.gutils.execute('SELECT fid, name, time_series_fid FROM inflow ORDER BY fid;').fetchall()
        if not all_inflows:
            self.uc.bar_info('There is no inflow defined in the database...')
            return
        cur_idx = 0
        for i, row in enumerate(all_inflows):
            row = [x if x is not None else '' for x in row]
            fid, name, ts_fid = row
            inflow_name = fid_name.format(fid, name).strip()
            self.inflowNameCbo.addItem(inflow_name, [fid, ts_fid])
            if fid == inflow_fid:
                cur_idx = i
            else:
                pass
        self.inflowNameCbo.setCurrentIndex(cur_idx)
        self.in_fid, self.ts_fid = self.inflowNameCbo.itemData(cur_idx)
        self.inflow = Inflow(self.in_fid, self.con, self.iface)
        self.inflow.get_row()
        self.inflow.get_time_series()
        cur_ts_idx = 0
        for i, row in enumerate(self.inflow.time_series):
            row = [x if x is not None else '' for x in row]
            ts_fid, name = row
            tseries_name = fid_name.format(ts_fid, name).strip()
            self.tseriesCbo.addItem(tseries_name, ts_fid)
            if ts_fid == self.ts_fid:
                cur_ts_idx = i
            else:
                pass
        self.tseriesCbo.setCurrentIndex(cur_ts_idx)
        self.populate_inflow_properties()

    def populate_inflow_properties(self):
        """Read and set inflow properties"""
        cur_inf = self.inflowNameCbo.currentText().split()[0]
        self.inflow = Inflow(cur_inf, self.con, self.iface)
        row = self.inflow.get_row()
        ident = row['ident']
        inoutfc = row['inoutfc']
        series_fid = str(row['time_series_fid'])
        if ident == 'F':
            self.ifcFloodplainRadio.setChecked(1)
            self.ifcChannelRadio.setChecked(0)
        else:
            self.ifcFloodplainRadio.setChecked(0)
            self.ifcChannelRadio.setChecked(1)
        index = self.tseriesCbo.findText(series_fid, Qt.MatchFixedString)
        self.tseriesCbo.setCurrentIndex(index)
        self.inflowTypeCbo.setCurrentIndex(inoutfc)
        self.populate_tseries_data()

    def populate_tseries_data(self):
        """Get current time series data, populate data table and create plot"""
        try:
            fid = self.tseriesCbo.currentText().split()[0]
        except IndexError as e:
            fid = self.tseriesCbo.currentText()
        self.inflow.series_fid = fid
        series_data = self.inflow.get_time_series_data()
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(['Time', 'Discharge', 'Mud'])
        for row in series_data:
            items = [QStandardItem(str(x)) if x is not None else QStandardItem('') for x in row]
            model.appendRow(items)
        self.tseriesDataTView.setModel(model)
        self.tseriesDataTView.resizeColumnsToContents()
        self.inflow_data_model = model
        for i in range(len(series_data)):
            self.tseriesDataTView.setRowHeight(i, 18)
        for i in range(3):
            self.tseriesDataTView.setColumnWidth(i, 80)
        self.update_plot()

    def save_tseries_data(self):
        """Get xsection data and save them in gpkg"""

    def revert_tseries_data_changes(self):
        """Revert any time series data changes made by users (load original
        tseries data from tables)"""

    def update_plot(self):
        """When time series data for plot change, update the plot"""
        self.plotWidget.clear_plot()
        dm = self.inflow_data_model
        print dm.rowCount()
        x = []
        y = []
        for i in range(dm.rowCount()):
            x.append(float(dm.data(dm.index(i, 0), Qt.DisplayRole)))
            y.append(float(dm.data(dm.index(i, 1), Qt.DisplayRole)))
        self.plotWidget.add_new_plot([x, y])
        self.plotWidget.add_org_plot([x, y])
