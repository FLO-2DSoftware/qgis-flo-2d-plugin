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

uiDialog, qtBaseClass = load_ui('eval_arfwrf')


class EvalArfWrfDialog(qtBaseClass, uiDialog):

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.populate_layers()

    def populate_layers(self):
        self.rlayer_cbo.clear()
        lyrs = [lyr.layer() for lyr in self.lyrs.root.findLayers()]
        for lyr in lyrs:
            if lyr.isValid() and lyr.type() == QgsMapLayer.VectorLayer and lyr.geometryType() == QGis.Polygon:
                self.rlayer_cbo.addItem(lyr.name(), lyr)
            else:
                pass
