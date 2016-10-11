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
from .utils import load_ui
from ..flo2dgeopackage import GeoPackageUtils
from ..flo2dobjects import Inflow
from plot_widget import PlotWidget

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
        self.cur_inflow_fid = inflow_fid
        self.inflow = None
        self.gutils = GeoPackageUtils(con, iface)
        self.inflow_data_model = None
        self.populate_inflows(inflow_fid)
        self.tseriesDataTView.horizontalHeader().setStretchLastSection(True)

        # connections
        self.inflowNameCbo.currentIndexChanged.connect(self.populate_tseries)
        self.tseriesCbo.currentIndexChanged.connect(self.populate_tseries_data)

    def setup_plot(self):
        self.plotWidget = PlotWidget()
        self.plotLayout.addWidget(self.plotWidget)

    def populate_inflows(self, inflow_fid=None):
        """Read inflow_time_series table, populate the cbo and set apropriate tseries"""
        self.inflowNameCbo.clear()
        fid_name = '{} {}'
        all_inflows = self.gutils.execute('SELECT fid, name, time_series_fid FROM inflow ORDER BY fid;').fetchall()
        initial = all_inflows[0]
        for row in all_inflows:
            row = [x if x is not None else '' for x in row]
            fid, name, ts_fid = row
            inflow_name = fid_name.format(fid, name)
            self.inflowNameCbo.addItem(inflow_name)
            if fid == inflow_fid:
                initial = row
            else:
                pass
        all_tseries = self.gutils.execute('SELECT fid, name FROM inflow_time_series ORDER BY fid;').fetchall()
        for row in all_tseries:
            row = [x if x is not None else '' for x in row]
            ts_fid, name = row
            tseries_name = fid_name.format(ts_fid, name)
            self.tseriesCbo.addItem(tseries_name)
            if ts_fid in initial:
                initial.append(name)
            else:
                pass
        initial_inflow = fid_name.format(*initial[:2])
        initial_series = fid_name.format(*initial[2:])
        index = self.inflowNameCbo.findText(initial_inflow, Qt.MatchFixedString)
        self.inflowNameCbo.setCurrentIndex(index)
        index = self.inflowNameCbo.findText(initial_series, Qt.MatchFixedString)
        self.tseriesCbo.setCurrentIndex(index)
        self.populate_tseries()

    def populate_tseries(self):
        """Read inflow_time_series table, populate the cbo and set apropriate tseries"""
        cur_inf = self.inflowNameCbo.currentText().split()[0]
        self.inflow = Inflow(cur_inf, self.con, self.iface)
        row = self.inflow.get_row()
        ident = row['ident']
        inoutfc = row['inoutfc']
        if ident == 'F':
            self.ifcFloodplainRadio.setChecked(1)
            self.ifcChannelRadio.setChecked(0)
        else:
            self.ifcFloodplainRadio.setChecked(0)
            self.ifcChannelRadio.setChecked(1)
        self.inflowTypeCbo.setCurrentIndex(inoutfc)
        self.populate_tseries_data()

    def populate_tseries_data(self):
        """Get current time series data, populate data table and create plot"""
        self.inflow.series_fid = self.tseriesCbo.currentText().split()[0]
        series_data = self.inflow.get_time_series_data()
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(['Time', 'Discharge', 'Mud'])
        for row in series_data:
            items = [QStandardItem(str(x)) if x is not None else QStandardItem('') for x in row]
            model.appendRow(items)
        self.tseriesDataTView.setModel(model)
        self.tseriesDataTView.resizeColumnsToContents()
        self.inflow_data_model = model
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

    def cur_tseries_changed(self):
        """User changed current time series. Populate time series
        data fields and plot"""

    def test_plot(self):
        x, y = [1, 2, 3, 4, 5, 6, 7, 8], [5, 6, 5, 3, 2, 3, 7, 8]
        self.plotWidget.add_new_plot([x, y])
        x, y = [1, 2, 3, 4, 5, 6, 7, 8], [5, 6, 5, 2, 1, 2, 7, 8]
        self.plotWidget.add_org_plot([x, y])
