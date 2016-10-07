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

uiDialog, qtBaseClass = load_ui('settings')

class SettingsDialog(qtBaseClass, uiDialog):

    def __init__(self, iface, gpkg=None, parent=None):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self, parent)
        self.setupUi(self)
        self.iface = iface

        self.widget_map = {
            "ICHANNEL": self.chanChBox,
            "IEVAP": self.evapChBox,
            "IHYDRSTRUCT": self.hystrucChBox,
            "IMULTC": self.multChBox,
            "IMODFLOW": self.modfloChBox,
            "INFIL": self.infilChBox,
            "IRAIN": self.rainChBox,
            "ISED": self.sedChBox,
            "IWRFS": self.redFactChBox,
            "LEVEE": self.leveeChBox,
            # "MUD": self.???,
            "SWMM": self.swmmChBox,
            "CELLSIZE": self.cellSizeEdit,
            "MANNING": self.manningEdit,
            "PROJ": self.projectionSelector
        }


