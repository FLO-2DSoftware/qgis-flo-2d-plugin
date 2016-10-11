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
from xsec_plot_widget import XsecPlotWidget

uiDialog, qtBaseClass = load_ui('xsec_editor')


class XsecEditorDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, xsec_fid=None, parent=None):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self, parent)
        self.iface = iface
        self.con = con
        self.setupUi(self)
        self.setup_plot()
        self.setModal(False)
        self.cur_xsec_fid = xsec_fid
        self.gutils = GeoPackageUtils(con, iface)
        self.xs_data_model = None
        self.populate_seg_cbo(xsec_fid)
        self.xsecDataTView.horizontalHeader().setStretchLastSection(True)

        # connections
        self.segCbo.currentIndexChanged.connect(self.cur_seg_changed)

    def setup_plot(self):
        self.plotWidget = XsecPlotWidget()
        self.plotLayout.addWidget(self.plotWidget)

    def populate_seg_cbo(self, xsec_fid=None):
        """Read chan table, populate the cbo and set active segment of the
        current xsection"""
        self.segCbo.clear()
        all_seg = self.gutils.execute('SELECT fid FROM chan ORDER BY fid;')
        for row in all_seg:
            self.segCbo.addItem(str(row[0]))
        if xsec_fid is not None:
            cur_seg = self.gutils.execute('SELECT seg_fid FROM chan_elems WHERE fid = ?;', (xsec_fid,)).fetchone()[0]
        else:
            cur_seg = str(self.segCbo.currentText())
        index = self.segCbo.findText(str(cur_seg), Qt.MatchFixedString)
        self.segCbo.setCurrentIndex(index)
        self.populate_xsec_list()
        self.segCbo.currentIndexChanged.connect(self.populate_xsec_list)
        self.xsecList.selectionModel().selectionChanged.connect(self.populate_xsec_data)

    def populate_xsec_list(self):
        """Get chan_elems records of the current segment (chan) and populate
        the xsection list"""
        cur_seg = str(self.segCbo.currentText())
        qry = 'SELECT fid FROM chan_elems WHERE seg_fid = ? ORDER BY nr_in_seg;'
        rows = self.gutils.execute(qry, (cur_seg,))
        position = 0
        model = QStandardItemModel()
        for i, f in enumerate(rows):
            gid = f[0]
            item = QStandardItem(str(gid))
            model.appendRow(item)
            if gid == self.cur_xsec_fid:
                position = i
            else:
                pass
        self.xsecList.setModel(model)
        index = self.xsecList.model().index(position, 0, QModelIndex())
        self.xsecList.selectionModel().select(index, self.xsecList.selectionModel().Select)
        self.xsecList.selectionModel().selectionChanged.connect(self.populate_xsec_data)
        self.populate_xsec_data()

    def populate_xsec_data(self):
        """Get current xsection data and populate all relevant fields of the
        dialog and create xsection plot"""
        cur_index = self.xsecList.selectionModel().selectedIndexes()[0]
        cur_xsec = self.xsecList.model().itemFromIndex(cur_index).text()
        xs_types = {'R': 'Rectangular', 'V': 'Variable Area', 'T': 'Trapezoidal', 'N': 'Natural'}
        self.xsecTypeCbo.clear()
        for val in xs_types.values():
            self.xsecTypeCbo.addItem(val)
        xs = CrossSection(cur_xsec, self.con, self.iface)
        row = xs.get_row()
        index = self.xsecTypeCbo.findText(xs_types[row['type']], Qt.MatchFixedString)
        self.xsecTypeCbo.setCurrentIndex(index)
        self.chanLenEdit.setText(str(row['xlen']))
        self.mannEdit.setText(str(row['fcn']))
        self.notesEdit.setText(str(row['notes']))
        chan = xs.chan_table()
        xy = xs.xsec_data()

        model = QStandardItemModel()
        if not xy:
            model.setHorizontalHeaderLabels([''])
            for val in chan.itervalues():
                item = QStandardItem(str(val))
                model.appendRow(item)
            model.setVerticalHeaderLabels(chan.keys())
            data_len = len(chan)
        else:
            model.setHorizontalHeaderLabels(['Station', 'Elevation'])
            for i, pt in enumerate(xy):
                x, y = pt
                xi = QStandardItem(str(x))
                yi = QStandardItem(str(y))
                model.appendRow([xi, yi])
            data_len = len(xy)
        self.xsecDataTView.setModel(model)
        self.xs_data_model = model
        for i in range(data_len):
            self.xsecDataTView.setRowHeight(i, 18)
        self.xsecDataTView.resizeColumnsToContents()
        if self.xsecTypeCbo.currentText() == 'Natural':
            self.update_plot()
        else:
            pass

    def apply_new_xsec_data(self):
        """Get xsection data and save them in gpkg"""

    def revert_xsec_data_changes(self):
        """Revert any xsection data changes made by users (load original
        xsection data from tables)"""

    def update_plot(self):
        """When xsection data for plot change, update the plot"""
        self.plotWidget.clear_plot()
        dm = self.xs_data_model
        print(dm.rowCount())
        x = []
        y = []
        for i in range(dm.rowCount()):
            x.append(float(dm.data(dm.index(i, 0), Qt.DisplayRole)))
            y.append(float(dm.data(dm.index(i, 1), Qt.DisplayRole)))
        self.plotWidget.add_new_bed_plot([x, y])
        self.plotWidget.add_org_bed_plot([x, y])

    def cur_seg_changed(self):
        """User changed current segment. Update xsection list and populate xsection
        data fields and plot for the first xsection for that segment"""
        print self.segCbo.currentIndex()

    def cur_xsec_changed(self):
        """User changed current xsection in the xsections list. Populate xsection
        data fields and update the plot"""

    def test_plot(self):
        x, y = [1, 2, 3, 4, 5, 6, 7, 8], [5, 6, 5, 3, 2, 3, 7, 8]
        self.plotWidget.add_new_bed_plot([x, y])
        x, y = [1, 2, 3, 4, 5, 6, 7, 8], [5, 6, 5, 2, 1, 2, 7, 8]
        self.plotWidget.add_org_bed_plot([x, y])
