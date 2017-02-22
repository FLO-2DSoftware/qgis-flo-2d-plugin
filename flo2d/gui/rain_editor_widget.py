# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt4.QtCore import Qt
from PyQt4.QtGui import QStandardItemModel, QStandardItem
from .utils import load_ui
from ..utils import is_number
from ..geopackage_utils import GeoPackageUtils, connection_required
from ..flo2dobjects import Rain
from plot_widget import PlotWidget

uiDialog, qtBaseClass = load_ui('rain_editor')


class RainEditorWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, plot, table):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.plot = plot
        self.table = table
        self.tview = table.tview
        self.rain = None
        self.gutils = None
        self.rain_data_model = None
        # self.rain_properties()
        # self.tview.horizontalHeader().setStretchLastSection(True)

        # connections
        self.tseries_cbo.currentIndexChanged.connect(self.populate_tseries_data)
        self.simulate_rain_chbox.stateChanged.connect(self.set_rain)
        self.real_time_chbox.stateChanged.connect(self.set_realtime)
        self.building_chbox.stateChanged.connect(self.set_building)
        self.arf_chbox.stateChanged.connect(self.set_arf)
        self.moving_storm_chbox.stateChanged.connect(self.set_moving_storm)
        self.total_rainfall_sbox.editingFinished.connect(self.set_tot_rainfall)
        self.rainfall_abst_sbox.editingFinished.connect(self.set_rainfall_abst)

    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
            qry = '''SELECT value FROM cont WHERE name = 'IRAIN';'''
            row = self.gutils.execute(qry).fetchone()
            if is_number(row[0]) and not row[0] == '0':
                self.simulate_rain_chbox.setChecked(True)
            self.rain = Rain(self.con, self.iface)

    def setup_plot(self):
        self.plotWidget = PlotWidget()
        self.plotLayout.addWidget(self.plotWidget)

    @connection_required
    def rain_properties(self):
        if not self.rain:
            return
        row = self.rain.get_row()
        if self.gutils.get_cont_par('IRAIN') == '1':
            self.simulate_rain_chbox.setChecked(True)
        else:
            self.simulate_rain_chbox.setChecked(False)
        if row['irainreal'] == '1':
            self.real_time_chbox.setChecked(True)
        else:
            self.real_time_chbox.setChecked(False)
        if row['irainbuilding'] == '1':
            self.building_chbox.setChecked(True)
        else:
            self.building_chbox.setChecked(False)
        if row['movingstrom'] == '1':
            self.moving_storm_chbox.setChecked(True)
        else:
            self.moving_storm_chbox.setChecked(False)
        if row['irainarf'] == '1':
            self.arf_chbox.setChecked(True)
        else:
            self.moving_storm_chbox.setChecked(False)
        if is_number(row['tot_rainfall']):
            self.total_rainfall_sbox.setValue(float((row['tot_rainfall'])))
        else:
            self.total_rainfall_sbox.setValue(0)
        if is_number(row['rainabs']):
            self.rainfall_abst_sbox.setValue(float(row['rainabs']))
        else:
            self.rainfall_abst_sbox.setValue(0)
        fid_name = '{} {}'
        for row in self.rain.get_time_series():
            row = [x if x is not None else '' for x in row]
            ts_fid, name = row
            series_name = fid_name.format(ts_fid, name).strip()
            self.tseries_cbo.addItem(series_name)
        self.tseries_cbo.setCurrentIndex(0)
        self.populate_tseries_data()

    def populate_tseries_data(self):
        """
        Get current time series data, populate data table and create plot.
        """
        try:
            fid = self.tseries_cbo.currentText().split()[0]
        except IndexError as e:
            fid = self.tseries_cbo.currentText()
        self.rain.series_fid = fid
        series_data = self.rain.get_time_series_data()
        model = QStandardItemModel()
        for row in series_data:
            items = [QStandardItem(str(x)) if x is not None else QStandardItem('') for x in row]
            model.appendRow(items)
        self.tview.setModel(model)
        self.tview.resizeColumnsToContents()
        self.rain_data_model = model
        for i in range(len(series_data)):
            self.tview.setRowHeight(i, 18)
        for i in range(3):
            self.tview.setColumnWidth(i, 80)
        self.update_plot()

    def save_tseries_data(self):
        """
        Get xsection data and save them in gpkg.
        """

    def revert_tseries_data_changes(self):
        """
        Revert any time series data changes made by users (load original tseries data from tables).
        """

    def update_plot(self):
        """
        When time series data for plot change, update the plot.
        """
        self.plot.clear()
        dm = self.rain_data_model
        x = []
        y = []
        for i in range(dm.rowCount()):
            x.append(float(dm.data(dm.index(i, 0), Qt.DisplayRole)))
            y.append(float(dm.data(dm.index(i, 1), Qt.DisplayRole)))
        self.plot.add_item('org_ts', [x, y])
        self.plot.add_item('new_ts', [x, y])

    def set_rain(self):
        if not self.rain:
            return
        if self.simulate_rain_chbox.isChecked():
            self.gutils.set_cont_par('IRAIN', 1)
        else:
            self.gutils.set_cont_par('IRAIN', 0)

    def set_realtime(self):
        if not self.rain:
            return
        self.rain.row['irainreal'] = self.real_time_chbox.isChecked()
        self.rain.set_row()

    def set_building(self):
        if not self.rain:
            return
        self.rain.row['irainbuilding'] = self.building_chbox.isChecked()
        self.rain.set_row()

    def set_arf(self):
        if not self.rain:
            return
        self.rain.row['irainarf'] = self.arf_chbox.isChecked()
        self.rain.set_row()

    def set_moving_storm(self):
        if not self.rain:
            return
        self.rain.row['movingstrom'] = self.moving_storm_chbox.isChecked()
        self.rain.set_row()

    def set_tot_rainfall(self):
        if not self.rain:
            return
        self.rain.row['tot_rainfall'] = self.total_rainfall_sbox.value()
        self.rain.set_row()

    def set_rainfall_abst(self):
        if not self.rain:
            return
        self.rain.row['rainabs'] = self.rainfall_abst_sbox.value()
        self.rain.set_row()
