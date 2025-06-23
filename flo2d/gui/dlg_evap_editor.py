# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
from qgis.PyQt.QtCore import QModelIndex, Qt
from qgis.PyQt.QtGui import QStandardItem, QStandardItemModel

from ..flo2dobjects import Evaporation
from ..geopackage_utils import GeoPackageUtils
from .plot_widget import PlotWidget
from .ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("evaporation_editor")


month_names = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


class EvapEditorDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
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
        self.monthlyEvapTView.verticalHeader().setVisible(False)
        self.hourlyEvapTView.horizontalHeader().setStretchLastSection(True)
        self.hourlyEvapTView.verticalHeader().setVisible(False)

        # connections
        self.monthlyEvapTView.clicked.connect(self.update_hourly_data)
        self.hourly_evap_model.dataChanged.connect(self.evaluate_hourly_sum)

    def populate_time_cbos(self):
        """
        Populate month, day and time combos.
        """
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
        self.monthCbo.setCurrentIndex(int(row["ievapmonth"])) # Change made on 21st June 2025.
        self.dayCbo.setCurrentIndex(int(row["iday"])) # Change made on 21st June 2025.
        self.timeCbo.setCurrentIndex(int(row["clocktime"])) # Change made on 21st June 2025.
        self.populate_monthly()

    def populate_monthly(self):
        monthly = self.evap.get_monthly()
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(["Month", "Rate"])
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
        indexes = self.monthlyEvapTView.selectionModel().selectedIndexes()
        if not indexes: # Change made on 21st June
            print("No month selected.") # Change made on 21st June
            return # Change made on 21st June
        cur_index = indexes[0] # Change made on 21st June
        cur_month = self.monthlyEvapTView.model().itemFromIndex(cur_index).text()
        self.evap.month = cur_month
        hourly = self.evap.get_hourly()
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(["Hour", "Percentage"])
        for row in hourly:
            items = [QStandardItem(str(x)) if x is not None else QStandardItem("") for x in row]
            model.appendRow(items)
        self.hourlyEvapTView.setModel(model)
        self.hourlyEvapTView.resizeColumnsToContents()
        self.hourly_evap_model = model
        self.evaluate_hourly_sum()
        self.update_plot()

    def setup_plot(self):
        self.plotWidget = PlotWidget()
        self.plotLayout.addWidget(self.plotWidget)

    def evaluate_hourly_sum(self):
        """
        Evaluate sum of hourly percentage evaporation data and show it.
        """
        sum = self.evap.get_hourly_sum()
        if not sum == 1:
            self.dailySumEdit.setStyleSheet("color: rgb(100, 0, 0);")
        else:
            self.dailySumEdit.setStyleSheet("color: rgb(0, 0, 0);")
        self.dailySumEdit.setText(str(sum))

    def update_hourly_data(self, index):
        """
        Current month has changed - update hourly data for it.
        """

    def save_evap_data(self):
        """
        Save evap data changes in gpkg.
        """

    def revert_evap_data_changes(self):
        """
        Revert any data changes made by users (load original evap data from tables).
        """

    def update_plot(self):
        """
        When time series data for plot change, update the plot.
        """
        self.plotWidget.clear()
        dm = self.hourly_evap_model
        # fix_print_with_import
        x = []
        y = []
        for i in range(dm.rowCount()):
            x.append(float(dm.data(dm.index(i, 0), Qt.DisplayRole)))
            y.append(float(dm.data(dm.index(i, 1), Qt.DisplayRole)))
        # self.plotWidget.add_new_plot([x, y]) # Commented on 21st June 2025
        # self.plotWidget.add_org_plot([x, y]) # Commented on 21st June 2025
        self.plotWidget.add_item("Evaporation", [x, y])  # Change made on 21st June 2025.
