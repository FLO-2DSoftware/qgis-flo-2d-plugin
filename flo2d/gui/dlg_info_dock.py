# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Flo2D
                                 A QGIS plugin
 FLO-2D tools for QGIS
                             -------------------
        begin                : 2016-08-28
        copyright            : (C) 2016 by Lutra Consulting for FLO-2D
        email                : info@lutraconsulting.co.uk
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 FLO-2D Preprocessor tools for QGIS.
"""
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from .utils import load_ui
from qgis.gui import QgsMapToolIdentify
import time

uiDialog, qtBaseClass = load_ui('info_dock')


class InfoDock(qtBaseClass, uiDialog):

    def __init__(self, iface, lyrs, tool):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.lyrs = lyrs
        self.tool = tool
        self.setupUi(self)
        self.timer = QTimer()
        self.timer.start(500)
        self.activeChBox.toggled.connect(self.toggle_active)
        self.setEnabled(True)

    def toggle_active(self, on):
        print on
        if on:
#            QObject.connect(self.canvas, SIGNAL("xyCoordinates(const QgsPoint &)"), self.set_value)
            self.timer.timeout.connect(self.set_value)
        else:
#            QObject.disconnect(self.canvas, SIGNAL("xyCoordinates(const QgsPoint &)"), self.set_value)
            self.timer.timeout.disconnect(self.set_value)

    def set_value(self):
        e = self.canvas.mouseLastXY()
        res = self.tool.identify(e.x(), e.y(), self.lyrs_list, QgsMapToolIdentify.ActiveLayer)
        if res:
            self.elevEdit.setText(str(res[0].mFeature["elevation"]))
            self.mannEdit.setText(str(res[0].mFeature['n_value']))



