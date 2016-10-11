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
from plot_widget import PlotWidget

uiDialog, qtBaseClass = load_ui('evaporation_editor')


class RainEditorDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, parent=None):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self, parent)
        self.iface = iface
        self.con = con
        self.setupUi(self)
        self.setup_plot()
        self.setModal(False)
        self.populate_time_cbos()
        self.gutils = GeoPackageUtils(con, iface)
        self.rain_data_model = None
        self.populate_time_cbos(fid)
        self.tseriesDataTView.horizontalHeader().setStretchLastSection(True)

        # connections
        self.tseriesCbo.currentIndexChanged.connect(self.populate_tseries_data)
        self.monthlyEvapTView.clicked.connect(self.update_hourly_data)
        self.daily_evap_model.dataChanged.connect(self.evaluate_daily_sum)

    def populate_time_cbos(self):
        """Populate month, day and time combos"""
        self.monthCbo.clear()
        self.dayCbo.clear()
        self.timeCbo.clear()
        for i in range(12):
            self.monthCbo.addItem(month_names[i])
        for i in range(1,32):
            self.dayCbo.addItem(i)
        for i in range(0,24):
            self.timeCbo.addItem(i)

    def setup_plot(self):
        self.plotWidget = PlotWidget()
        self.plotLayout.addWidget(self.plotWidget)

    def evaluate_daily_sum(self, index1, index2):
        """Evaluate sum of hourly percentage evaporation data and show it"""

    def update_hourly_data(self, index):
        """Current month has changed - update hourly data for it"""


    def populate_tseries_data(self):
        """Get current time series data, populate data table and create plot"""
        self.inflow.series_fid = str(self.tseriesCbo.currentText())
        series_data = self.inflow.time_series_data_table()
        model = QStandardItemModel()
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
        dm = self.rain_data_model
        print dm.rowCount()
        x = []
        y = []
        for i in range(dm.rowCount()):
            x.append(float(dm.data(dm.index(i, 0), Qt.DisplayRole)))
            y.append(float(dm.data(dm.index(i, 1), Qt.DisplayRole)))
        self.plotWidget.add_new_plot([x, y])
        self.plotWidget.add_org_plot([x, y])

    def test_plot(self):
        x, y = [1, 2, 3, 4, 5, 6, 7, 8], [5, 6, 5, 3, 2, 3, 7, 8]
        self.plotWidget.add_new_plot([x, y])
        x, y = [1, 2, 3, 4, 5, 6, 7, 8], [5, 6, 5, 2, 1, 2, 7, 8]
        self.plotWidget.add_org_plot([x, y])
