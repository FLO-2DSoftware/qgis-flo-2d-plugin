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
from ..flo2dobjects import CrossSection
from inflow_plot_widget import InflowPlotWidget

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
        self.gutils = GeoPackageUtils(con, iface)
        self.inflow_data_model = None
        self.populate_tseries_cbo()
        self.tseriesDataTView.horizontalHeader().setStretchLastSection(True)
        self.test_plot()

        # connections
        self.outflowTypeCbo.currentIndexChanged.connect(self.set_active_widgets)
        self.tseriesCbo.currentIndexChanged.connect(self.populate_tseries_data)

    def set_active_widgets(self):
        self.identFloodplainRadio.setDisabled(True)
        self.identChannelRadio.setDisabled(True)
        self.identBothRadio.setDisabled(True)
        self.identFloodplainRadio.setCheckekd(False)
        self.identChannelRadio.setCheckekd(False)
        self.identBothRadio.setCheckekd(False)
        wid_map = {
            "Outflow element (no hydrograph)": {
                "def_for": {"f": 2, "c": 1, "b": 1},
                "tableLabel": None,
                "table": None,
                "dataLabel": None,
                "plot": None
            },
            "Diversion channel element (for inflows)": {
                "def_for": {"f": 0, "c": 2, "b": 0},
                "tableLabel": "Time Series",
                "table": "outflow_time_series",
                "dataLabel": "Time-Discharge Data",
                "dataTable": "outflow_time_series_data",
                "plot": {
                    "xa": "Time", "ya": "Discharge"
                }
            },
            "Outflow with time-stage relationship": {
                "def_for": {"f": 2, "c": 1, "b": 0},
                "tableLabel": "Time-Stage Relationship",
                "table": "outflow_time_series",
                "dataLabel": "Time-Stage Data",
                "dataTable": "outflow_time_series_data",
                "plot": {
                    "xa": "Time", "ya": "Stage"
                }
            },
            "Outflow with time-stage and free floodplain and channel": {
                "def_for": {"f": 2, "c": 1, "b": 0},
                "tableLabel": "Time Series",
                "table": "outflow_time_series",
                "dataLabel": "Time-Stage Data",
                "dataTable": "outflow_time_series_data",
                "plot": {
                    "xa": "Time", "ya": "Stage"
                }
            },
            "Channel outflow with stage-discharge": {
                "def_for": {"f": 0, "c": 2, "b": 0},
                "tableLabel": "Stage-Discharge Relationship",
                "table": "qh_params",
                "dataLabel": "Stage-Discharge Data",
                "plot": {
                    "xa": "Discharge", "ya": "Stage"
                }
            },
            "Channel outflow with depth-discharge": {
                "def_for": {"f": 0, "c": 2, "b": 0},
                "tableLabel": "Depth-Discharge Relationship",
                "dataLabel": "Depth-Discharge Data",
                "plot": {
                    "xa": "Discharge", "ya": "Depth"
                }
            }
        }
        cur_type = self.outflowTypeCbo.currentText()

        # defined for radio buttons
        dff = wid_map[cur_type]["def_for"]["f"]
        self.identFloodplainRadio.setEnabled(dff)
        self.identFloodplainRadio.setChecked(dff == 2)
        dfc = wid_map[cur_type]["def_for"]["c"]
        self.identChannelRadio.setEnabled(dfc)
        self.identChannelRadio.setChecked(dfc == 2)
        dfb = wid_map[cur_type]["def_for"]["b"]
        self.identBothRadio.setEnabled(dfb)
        self.identBothRadio.setChecked(dfb == 2)

        self.tableLabel.setText((wid_map[cur_type]["tableLabel"]))
        self.dataTableLabel.setText((wid_map[cur_type]["dataTableLabel"]))

    def setup_plot(self):
        self.plotWidget = InflowPlotWidget()
        self.plotLayout.addWidget(self.plotWidget)

    def populate_tseries_cbo(self, inflow_fid=None):
        """Read inflow_time_series table, populate the cbo and set apropriate tseries"""
        self.tseriesCbo.clear()
        all_tseries = self.gutils.execute('SELECT fid FROM chan ORDER BY fid;')
        for row in all_tseries:
            self.tseriesCbo.addItem(str(row[0]))
        if inflow_fid is not None:
            cur_tseries = self.gutils.execute('SELECT time_series_fid FROM inflow WHERE fid = ?;', (inflow_fid,)).fetchone()[0]
        else:
            cur_tseries = str(self.tseriesCbo.currentText())
        index = self.tseriesCbo.findText(str(cur_tseries), Qt.MatchFixedString)
        self.tseriesCbo.setCurrentIndex(index)

    def save_tseries_data(self):
        """Get xsection data and save them in gpkg"""

    def revert_tseries_data_changes(self):
        """Revert any time series data changes made by users (load original
        tseries data from tables)"""

    def update_plot(self):
        """When time series data for plot change, update the plot"""
        self.plotWidget.clear_plot()
        dm = self.xs_data_model
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

    # TODO: all below this line is to be changed

    def populate_tseries_data(self):
        """Get current time series data, populate data table and create plot"""
        # TODO
#        cur_index = self.xsecList.selectionModel().selectedIndexes()[0]
#        cur_xsec = self.xsecList.model().itemFromIndex(cur_index).text()
#        xs_types = {'R': 'Rectangular', 'V': 'Variable Area', 'T': 'Trapezoidal', 'N': 'Natural'}
#        self.xsecTypeCbo.clear()
#        for val in xs_types.values():
#            self.xsecTypeCbo.addItem(val)
#        xs = CrossSection(cur_xsec, self.con, self.iface)
#        row = xs.get_row()
#        index = self.xsecTypeCbo.findText(xs_types[row['type']], Qt.MatchFixedString)
#        self.xsecTypeCbo.setCurrentIndex(index)
#        self.chanLenEdit.setText(str(row['xlen']))
#        self.mannEdit.setText(str(row['fcn']))
#        self.notesEdit.setText(str(row['notes']))
#        chan = xs.chan_table()
#        xy = xs.xsec_data()
#
#        model = QStandardItemModel()
#        if not xy:
#            model.setHorizontalHeaderLabels([''])
#            for val in chan.itervalues():
#                item = QStandardItem(str(val))
#                model.appendRow(item)
#            model.setVerticalHeaderLabels(chan.keys())
#            for i in range(len(chan)):
#                self.xsecDataTView.setRowHeight(i, 18)
#        else:
#            model.setHorizontalHeaderLabels(['x', 'y'])
#            for i, pt in enumerate(xy):
#                x, y = pt
#                xi = QStandardItem(str(x))
#                yi = QStandardItem(str(y))
#                model.appendRow([xi, yi])
#            for i in range(len(xy)):
#                self.xsecDataTView.setRowHeight(i, 18)
#        self.xsecDataTView.setModel(model)
#        self.xsecDataTView.resizeColumnsToContents()
#        self.xs_data_model = model
#
#        if self.xsecTypeCbo.currentText() == 'Natural':
#            self.update_plot()
#        else:
#            pass


