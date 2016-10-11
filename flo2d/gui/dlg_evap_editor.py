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
from ..flo2dobjects import Evaporation
from plot_widget import PlotWidget

uiDialog, qtBaseClass = load_ui('evaporation_editor')


class EvapEditorDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, parent=None):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self, parent)
        self.iface = iface
        self.con = con
        self.setupUi(self)
        self.setup_plot()
        self.setModal(False)
        self.evap = None
        self.gutils = GeoPackageUtils(con, iface)
        self.populate_time_cbos()
        self.monthly_evap_model = QStandardItemModel()
        self.hourly_evap_model = QStandardItemModel()
        self.populate_time_cbos()
        self.monthlyEvapTView.horizontalHeader().setStretchLastSection(True)
        self.hourlyEvapTView.horizontalHeader().setStretchLastSection(True)

        # connections
        self.monthlyEvapTView.clicked.connect(self.update_hourly_data)
        #self.hourly_evap_model.dataChanged.connect(self.evaluate_hourly_sum)

    def populate_time_cbos(self):
        """Populate month, day and time combos"""
        self.monthCbo.clear()
        self.dayCbo.clear()
        self.timeCbo.clear()
        for i in range(12):
            self.monthCbo.addItem(month_names[i])
        for i in range(1, 32):
            self.dayCbo.addItem(str(i))
        for i in range(1, 25):
            self.timeCbo.addItem(str(i))
        self.evap = Evaporation(self.con, self.iface)
        row = self.evap.get_row()
        self.monthCbo.setCurrentIndex(row['ievapmonth'])
        self.dayCbo.setCurrentIndex(row['iday'])
        self.timeCbo.setCurrentIndex(row['clocktime'])
        self.populate_monthly()

    def populate_monthly(self):
        monthly = self.evap.get_monthly()
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(['Month', 'Monthly evaporation'])
        for month, mevap in monthly:
            item = [QStandardItem(month), QStandardItem(str(mevap))]
            model.appendRow(item)
        self.monthlyEvapTView.setModel(model)
        self.monthlyEvapTView.resizeColumnsToContents()
        self.monthly_evap_model = model
        index = self.monthlyEvapTView.model().index(0, 0, QModelIndex())
        self.monthlyEvapTView.selectionModel().select(index, self.monthlyEvapTView.selectionModel().Select)
        self.monthlyEvapTView.selectionModel().selectionChanged.connect(self.populate_hourly)
        self.populate_hourly()

    def populate_hourly(self):
        cur_index = self.monthlyEvapTView.selectionModel().selectedIndexes()[0]
        cur_month = self.monthlyEvapTView.model().itemFromIndex(cur_index).text()
        self.evap.month = cur_month
        hourly = self.evap.get_hourly()
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(['Hour', 'Hourly evaporation'])
        for row in hourly:
            items = [QStandardItem(str(x)) if x is not None else QStandardItem('') for x in row]
            model.appendRow(items)
        self.hourlyEvapTView.setModel(model)
        self.hourlyEvapTView.resizeColumnsToContents()
        self.hourly_evap_model = model
        self.update_plot()

    def setup_plot(self):
        self.plotWidget = PlotWidget()
        self.plotLayout.addWidget(self.plotWidget)

    def evaluate_hourly_sum(self, index1, index2):
        """Evaluate sum of hourly percentage evaporation data and show it"""

    def update_hourly_data(self, index):
        """Current month has changed - update hourly data for it"""

    def save_evap_data(self):
        """Save evap data changes in gpkg"""

    def revert_evap_data_changes(self):
        """Revert any data changes made by users (load original
        evap data from tables)"""

    def update_plot(self):
        """When time series data for plot change, update the plot"""
        self.plotWidget.clear_plot()
        dm = self.hourly_evap_model
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
