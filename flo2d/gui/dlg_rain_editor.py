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
from rain_plot_widget import RainPlotWidget

uiDialog, qtBaseClass = load_ui('rain_editor')


class RainEditorDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, fid=None, parent=None):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self, parent)
        self.iface = iface
        self.con = con
        self.setupUi(self)
        self.setup_plot()
        self.setModal(False)
#        self.cur_fid = fid
#        self.gutils = GeoPackageUtils(con, iface)
#        self.rain_data_model = None
#        self.populate_tseries_cbo(fid)
#        self.tseriesDataTView.horizontalHeader().setStretchLastSection(True)

        # connections
        self.tseriesCbo.currentIndexChanged.connect(self.populate_tseries_data)

    def setup_plot(self):
        self.plotWidget = RainPlotWidget()
        self.plotLayout.addWidget(self.plotWidget)

    def populate_tseries_cbo(self, inflow_fid=None):
        """Read inflow_time_series table, populate the cbo and set apropriate tseries"""
#        self.inflowNameCbo.clear()
#        all_tseries = self.gutils.execute('SELECT fid FROM inflow ORDER BY fid;').fetchall()
#        for row in all_tseries:
#            self.inflowNameCbo.addItem(str(row[0]))
#        if inflow_fid is None:
#            inflow_fid = all_tseries[0][0]
#        else:
#            pass
#        index = self.inflowNameCbo.findText(str(inflow_fid), Qt.MatchFixedString)
#        self.inflowNameCbo.setCurrentIndex(index)
#        self.populate_tseries_data()

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
