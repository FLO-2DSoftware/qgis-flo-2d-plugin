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
from ..flo2dgeopackage import GeoPackageUtils, database_connect

uiDialog, qtBaseClass = load_ui('settings')


class SettingsDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, parent=None):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self, parent)
        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.gpkg = None
        self.gutils = GeoPackageUtils(self.con, self.iface)
        self.widget_map = {
            "ICHANNEL": self.chanChBox,
            "IEVAP": self.evapChBox,
            "IHYDRSTRUCT": self.hystrucChBox,
            "IMULTC": self.multChBox,
            "IMODFLOW": self.modfloChBox,
            "INFIL": self.infilChBox,
            "IRAIN": self.rainChBox,
            "ISED": self.sedChBox,
            "IWRFS": self.redFacChBox,
            "LEVEE": self.leveesChBox,
            # "MUD": self.???,
            # "PROJ": self.projectionSelector,
            # "MANNING": self.manningEdit,
            "SWMM": self.swmmChBox,
            "CELLSIZE": self.cellSizeEdit
        }
        self.setup()

    def setup(self):
        self.gpkg = self.gpkgPathEdit.text()
        if not self.gpkg:
            self.gutils = GeoPackageUtils(self.con, self.iface)
        else:
            pass
        self.read()

    def read(self):
        for name, wid in self.widget_map.iteritems():
            qry = '''SELECT value FROM cont WHERE name = '{0}';'''.format(name)
            value = self.gutils.execute(qry).fetchone()[0]
            if isinstance(wid, QLineEdit):
                wid.setText(str(value))
            elif isinstance(wid, QCheckBox):
                wid.setChecked(int(value))
            elif name == 'PROJ':
                coord = QgsCoordinateReferenceSystem()
                coord.createFromWkt(value)
                wid.setCrs(coord)
            else:
                pass

    def write(self):
        for name, wid in self.widget_map.iteritems():
            qry = '''INSERT value INTO cont WHERE name = '{0}';'''.format(name)
            if isinstance(wid, QLineEdit):
                value = wid.text()
                self.gutils.execute(qry)
            elif isinstance(wid, QCheckBox):
                value = 1 if wid.isChecked() else 0
            elif name == 'PROJ':
                pass
            else:
                pass
            self.gutils.execute(qry.format(value))
