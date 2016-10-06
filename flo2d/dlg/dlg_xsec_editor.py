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

uiDialog, qtBaseClass = load_ui('xsec_editor')


class XsecEditorDialog(qtBaseClass, uiDialog):

    def __init__(self, iface, parent=None, xsec_fid=1232, gpkg=r'D:\GIS_DATA\GPKG\alawai.gpkg'):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self, parent)
        self.setupUi(self)
        self.setModal(True)
        self.iface = iface
        self.cur_xsec_fid = xsec_fid
        self.gpkg = gpkg
        self.gutils = GeoPackageUtils(gpkg, iface)
        self.populate_seg_cbo(xsec_fid)

    def populate_seg_cbo(self, xsec_fid=None):
        """Read chan table, populate the cbo and set active segment of the
        current xsection"""
        self.gutils.database_connect()
        cur_seg = self.gutils.execute('SELECT seg_fid FROM chan_elems WHERE fid = {0};'.format(xsec_fid)).fetchone()[0]
        all_seg = self.gutils.execute('SELECT fid FROM chan ORDER BY fid;')
        self.comboBox.clear()
        for row in all_seg:
            self.comboBox.addItem(str(row[0]))
        index = self.comboBox.findText(str(cur_seg), Qt.MatchFixedString)
        self.comboBox.setCurrentIndex(index)
        self.gutils.database_disconnect()
        self.populate_xsec_list()
        self.comboBox.currentIndexChanged.connect(self.populate_xsec_list)
        self.xsecList.selectionModel().selectionChanged.connect(self.populate_xsec_data)

    def populate_xsec_list(self):
        """Get chan_elems records of the current segment (chan) and populate
        the xsection list"""
        cur_seg = str(self.comboBox.currentText())
        self.gutils.database_connect()
        qry = 'SELECT fid FROM chan_elems WHERE seg_fid = {0} ORDER BY nr_in_seg;'.format(cur_seg)
        rows = self.gutils.execute(qry)
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
        self.gutils.database_disconnect()
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
        with CrossSection(cur_xsec, self.gpkg, self.iface) as xs:
            row = xs.get_row()
            index = self.xsecTypeCbo.findText(xs_types[row['type']], Qt.MatchFixedString)
            self.xsecTypeCbo.setCurrentIndex(index)
            self.chanLenEdit.setText(str(row['xlen']))
            self.mannEdit.setText(str(row['fcn']))
            self.notesEdit.setText(str(row['notes']))
            chan = xs.chan_table()
            model = QStandardItemModel()
            model.setHorizontalHeaderLabels([''])
            for val in chan.itervalues():
                item = QStandardItem(str(val))
                model.appendRow(item)
            model.setVerticalHeaderLabels(chan.keys())
            self.xsecDataTView.setModel(model)

    def apply_new_xsec_data(self):
        """Get xsection data and save them in gpkg"""

    def revert_xsec_data_changes(self):
        """Revert any xsection data changes made by users (load original
        xsection data from tables)"""

    def update_plot(self):
        """When xsection data for plot change, update the plot"""
#        x,y = [1, 2, 3], [5, 6, 7]
#        pg.plot(x, y)

    def cur_seg_changed(self):
        """User changed current segment. Update xsection list and populate xsection
        data fields and plot for the first xsection for that segment"""

    def cur_xsec_changed(self):
        """User changed current xsection in the xsections list. Populate xsection
        data fields and update the plot"""
