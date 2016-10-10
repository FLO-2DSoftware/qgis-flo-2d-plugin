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
 This script initializes the plugin, making it known to QGIS.
"""

from PyQt4.QtGui import QMessageBox
from qgis.gui import QgsMessageBar
from qgis.core import QgsMessageLog


class UserCommunication(object):
    """Class for communication with user"""

    def __init__(self, iface, context):
        self.iface = iface
        self.context = context

    def show_info(self, msg):
        if self.iface is not None:
            QMessageBox.information(self.iface.mainWindow(), self.context, msg)
        else:
            print(msg)

    def show_warn(self, msg):
        if self.iface is not None:
            QMessageBox.warning(self.iface.mainWindow(), self.context, msg)
        else:
            print(msg)

    def log(self, msg, level):
        if self.iface is not None:
            QgsMessageLog.logMessage(msg, self.context, level)
        else:
            print(msg)

    def log_info(self, msg):
        if self.iface is not None:
            QgsMessageLog.logMessage(msg, self.context, QgsMessageLog.INFO)
        else:
            print(msg)

    def bar_error(self, msg):
        if self.iface is not None:
            self.iface.messageBar().pushMessage(self.context, msg, level=QgsMessageBar.CRITICAL)
        else:
            print(msg)

    def bar_warn(self, msg, dur=5):
        if self.iface is not None:
            self.iface.messageBar().pushMessage(self.context, msg, level=QgsMessageBar.WARNING, duration=dur)
        else:
            print(msg)

    def bar_info(self, msg, dur=5):
        if self.iface is not None:
            self.iface.messageBar().pushMessage(self.context, msg, level=QgsMessageBar.INFO, duration=dur)
        else:
            print(msg)

    def question(self, msg):
        if self.iface is not None:
            m = QMessageBox()
            m.setText(msg)
            m.setStandardButtons(QMessageBox.No | QMessageBox.Yes)
            m.setDefaultButton(QMessageBox.No)
            return m.exec_()
        else:
            print(msg)
