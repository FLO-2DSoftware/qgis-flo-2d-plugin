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
from ..flo2dobjects import Outflow
from plot_widget import PlotWidget

uiDialog, qtBaseClass = load_ui('outflow_editor')


class OutflowEditorDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, outflow_fid=None, parent=None):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self, parent)
        self.iface = iface
        self.con = con
        self.setupUi(self)
        self.setup_plot()
        self.setModal(False)
        self.outflow_fid = outflow_fid
        self.nostacfp = None
        self.outflow = None
        self.gutils = GeoPackageUtils(con, iface)
        self.outflow_data_model = QStandardItemModel()
        self.populate_outflows(outflow_fid)
        self.tseriesDataTView.horizontalHeader().setStretchLastSection(True)
        # connections
        self.outflowNameCbo.currentIndexChanged.connect(self.outflow_type)
        self.tseriesCbo.currentIndexChanged.connect(self.populate_series_data)

    def setup_plot(self):
        self.plotWidget = PlotWidget()
        self.plotLayout.addWidget(self.plotWidget)

    def reset_gui(self):
        self.identFloodplainRadio.setDisabled(True)
        self.identChannelRadio.setDisabled(True)
        self.identBothRadio.setDisabled(True)
        self.identFloodplainRadio.setChecked(False)
        self.identChannelRadio.setChecked(False)
        self.identBothRadio.setChecked(False)
        self.tseriesCbo.setDisabled(True)
        self.tseriesCbo.clear()
        self.outflow_data_model.clear()

    def mode1(self):
        self.reset_gui()
        self.outflowTypeCbo.setCurrentIndex(0)

        self.identFloodplainRadio.setEnabled(True)
        self.identChannelRadio.setEnabled(True)
        self.identBothRadio.setEnabled(True)
        self.identFloodplainRadio.setChecked(True)

        self.tableLabel.setText('')
        self.dataTableLabel.setText('')

    def mode2(self):
        self.reset_gui()
        self.outflowTypeCbo.setCurrentIndex(1)

        self.identFloodplainRadio.setEnabled(True)
        self.identChannelRadio.setEnabled(True)
        self.identBothRadio.setDisabled(True)
        self.identFloodplainRadio.setChecked(True)

        self.tableLabel.setText("Time-Stage Relationship")
        self.tableLabel.setEnabled(True)

        self.tseriesCbo.setEnabled(True)

        self.dataTableLabel.setText("Time-Stage Data")
        self.dataTableLabel.setEnabled(True)

    def mode3(self):
        self.reset_gui()
        self.outflowTypeCbo.setCurrentIndex(3)

        self.identChannelRadio.setEnabled(True)
        self.identChannelRadio.setChecked(True)

        self.tableLabel.setText("Channel outflow with stage-discharge")
        self.tableLabel.setEnabled(True)

        self.tseriesCbo.setEnabled(True)

        self.dataTableLabel.setText("Stage-Discharge Relationship")
        self.dataTableLabel.setEnabled(True)

    def mode4(self):
        self.reset_gui()
        self.outflowTypeCbo.setCurrentIndex(4)

        self.identChannelRadio.setEnabled(True)
        self.identFloodplainRadio.setChecked(True)

        self.tableLabel.setText("Channel outflow with depth-discharge")
        self.tableLabel.setEnabled(True)

        self.tseriesCbo.setEnabled(True)

        self.dataTableLabel.setText("Depth-Discharge Relationship")
        self.dataTableLabel.setEnabled(True)

    def add_series(self, series):
        fid_name = '{} {}'
        initial = series[0]
        for row in series:
            row = [x if x is not None else '' for x in row]
            ts_fid, name = row
            series_name = fid_name.format(ts_fid, name).strip()
            self.tseriesCbo.addItem(series_name)
            if ts_fid in initial:
                initial = row
            else:
                pass
        initial_series = fid_name.format(*initial).strip()
        index = self.tseriesCbo.findText(initial_series, Qt.MatchFixedString)
        self.tseriesCbo.setCurrentIndex(index)

    def populate_outflows(self, outflow_fid=None):
        """Read outflow table, populate the cbo and set apropriate outflow"""
        self.outflowNameCbo.clear()
        fid_name = '{} {}'
        all_outflows = self.gutils.execute('SELECT fid, name FROM outflow ORDER BY fid;').fetchall()
        initial = all_outflows[0]
        for row in all_outflows:
            row = [x if x is not None else '' for x in row]
            fid, name = row
            outflow_name = fid_name.format(fid, name).strip()
            self.outflowNameCbo.addItem(outflow_name)
            if fid == outflow_fid:
                initial = row
            else:
                pass
        initial_outflow = fid_name.format(*initial).strip()
        index = self.outflowNameCbo.findText(initial_outflow, Qt.MatchFixedString)
        self.outflowNameCbo.setCurrentIndex(index)
        self.outflow_type()

    def outflow_type(self):
        try:
            cur_out = self.outflowNameCbo.currentText().split()[0]
        except IndexError as e:
            cur_out = self.outflowNameCbo.currentText()
        self.gutils.uc.log_info(repr(cur_out))
        self.mode1()
        self.outflow = Outflow(cur_out, self.con, self.iface)

        row = self.outflow.get_row()
        ident = row['ident']
        self.nostacfp = row['nostacfp']
        series = None
        if ident == 'K':
            if self.outflow.typ == 'qh_params':
                series = self.gutils.execute('SELECT fid, NULL FROM qh_params ORDER BY fid;').fetchall()  #name column should be added
                self.mode3()
            elif self.outflow.typ == 'qh_table':
                series = self.gutils.execute('SELECT fid, name FROM qh_table ORDER BY fid;').fetchall()
                self.mode4()
            else:
                pass
        elif ident == 'N':
            if self.outflow.typ is not None:
                series = self.gutils.execute('SELECT fid, name FROM outflow_time_series ORDER BY fid;').fetchall()
                self.mode2()
            else:
                pass
        if self.outflow.series_fid:
            self.add_series(series)
            self.populate_series_data()
        else:
            pass

    def populate_series_data(self):
        """Get current time series data, populate data table and create plot"""
        try:
            fid = self.tseriesCbo.currentText().split()[0]
        except IndexError as e:
            fid = self.tseriesCbo.currentText()
        self.outflow.series_fid = fid
        typ = self.outflow.typ
        head = None
        series_data = []
        if typ == "outflow_time_series":
            head = ["Time", "Stage"]
            series_data = self.outflow.get_time_series_data()
        elif typ == "qh_params":
            head = ["Hmax", "Coef", "Exponent"]
            series_data = self.outflow.get_qh_params()
        elif typ == "qh_table":
            head = ["Depth", "Discharge"]
            series_data = self.outflow.get_qh_table_data()
        else:
            pass
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(head)
        for row in series_data:
            items = [QStandardItem(str(x)) if x is not None else QStandardItem('') for x in row]
            model.appendRow(items)
        self.tseriesDataTView.setModel(model)
        self.tseriesDataTView.resizeColumnsToContents()
        self.outflow_data_model = model
        self.update_plot()

    def save_tseries_data(self):
        """Get xsection data and save them in gpkg"""

    def revert_tseries_data_changes(self):
        """Revert any time series data changes made by users (load original
        tseries data from tables)"""

    def update_plot(self):
        """When time series data for plot change, update the plot"""
        self.plotWidget.clear_plot()
        dm = self.outflow_data_model
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
