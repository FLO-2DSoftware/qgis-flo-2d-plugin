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
from osgeo import gdal
from .utils import load_ui
from ..flo2dgeopackage import GeoPackageUtils
import os

uiDialog, qtBaseClass = load_ui('eval_arfwrf')


class EvalArfWrfDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, lyrs, gpkg, cell_size):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.con = con
        self.iface = iface
        self.lyrs = lyrs
        self.gpkg = gpkg
        self.gpkg_path = gpkg.get_gpkg_path()
        self.cell_size = float(cell_size)
        self.setupUi(self)
        self.gutils = GeoPackageUtils(con, iface)
        self.populate_src_cbo()

        # connections
        self.browseSrcBtn.clicked.connect(self.browse_src_layer)

    def populate_src_cbo(self):
        """Get loaded polygon layers into combobox"""
        poly_lyrs = self.lyrs.list_group_vlayers()
        for l in poly_lyrs:
            if l.geometryType() == QGis.Polygon:
                self.srcLayerCbo.addItem(l.name(), l.dataProvider().dataSourceUri())

    def browse_src_layer(self):
        """Users pick a source raster not loaded into project"""
        s = QSettings()
        last_block_lyr_dir = s.value('FLO-2D/lastBlockLyrDir', '')
        self.src = QFileDialog.getOpenFileName(None,
                         'Choose layer with blocked polygons...',
                         directory=last_block_lyr_dir)
        if not self.src:
            return
        s.setValue('FLO-2D/lastBlockLyrDir', os.path.dirname(self.src))
        if not self.srcLayerCbo.findData(self.src):
            bname = os.path.basename(self.src)
            self.srcLayerCbo.addItem(bname, self.src)
            self.srcLayerCbo.setCurrentInsex(len(self.srcLayerCbo)-1)

    def evaluate(self):
        """Evaluate ARF and WRF factors and save them to blocked_cells table"""
        # shall we rename the table?


