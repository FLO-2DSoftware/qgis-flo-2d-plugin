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

import os
from .utils import load_ui

from xsec_plot_widget import XsecPlotWidget

uiDialog, qtBaseClass = load_ui('xsec_editor')

class XsecEditorDialog(qtBaseClass, uiDialog):

    def __init__(self, iface, xsec_fid, parent=None):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.setupUi(self)
        self.setModal(True)
        self.iface = iface
        self.cur_xsec_fid = xsec_fid
        self.setup_plot()

        # connections
        self.segCbo.currentIndexChanged.connect(self.cur_seg_changed)

    def setup_plot(self):
        self.plotWidget = XsecPlotWidget()
        self.plotLayout.addWidget(self.plotWidget)
        self.test_plot()

    def populate_seg_cbo(self, cur_xsec_fid=None):
        """Read chan table, populate the cbo and set active segment of the
        current xsection"""

    def populate_xsec_list(self, cur_seg_fid):
        """Get chan_elems records of the current segment (chan) and populate
        the xsection list"""

    def populate_xsec_data(self, cur_xsec_fid=None):
        """Get current xsection data and populate all relevant fields of the
        dialog and create xsection plot"""

    def apply_new_xsec_data(self):
        """Get xsection data and save them in gpkg"""

    def revert_xsec_data_changes(self):
        """Revert any xsection data changes made by users (load original
        xsection data from tables)"""

    def update_plot(self):
        """When xsection data for plot change, update the plot"""

    def cur_seg_changed(self):
        """User changed current segment. Update xsection list and populate xsection
        data fields and plot for the first xsection for that segment"""
        print self.segCbo.currentIndex()

    def cur_xsec_changed(self):
        """User changed current xsection in the xsections list. Populate xsection
        data fields and update the plot"""

    def test_plot(self):
        x,y = [1, 2, 3, 4, 5, 6, 7, 8], [5, 6, 5, 3, 2, 3, 7, 8]
        self.plotWidget.add_new_bed_plot([x,y])
        x,y = [1, 2, 3, 4, 5, 6, 7, 8], [5, 6, 5, 2, 1, 2, 7, 8]
        self.plotWidget.add_org_bed_plot([x,y])


