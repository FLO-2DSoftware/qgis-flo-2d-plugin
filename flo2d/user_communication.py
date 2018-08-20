# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

# Unnecessary parens after u'print' keyword
#pylint: disable=C0325

import sys
from PyQt4.QtGui import QMessageBox, QProgressBar
from PyQt4.QtCore import Qt
from qgis.gui import QgsMessageBar
from qgis.core import QgsMessageLog


class UserCommunication(object):
    """
    Class for communication with user.
    """

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

    def show_critical(self, msg):
        if self.iface is not None:
            QMessageBox.critical(self.iface.mainWindow(), self.context, msg)
        else:
            print(msg)
    
    def show_error(self, msg, e):
        if self.iface is not None:
            exc_type, exc_obj, exc_tb = sys.exc_info() 
            filename = exc_tb.tb_frame.f_code.co_filename          
            function = exc_tb.tb_frame.f_code.co_name
            line = str(exc_tb.tb_lineno)        
            QMessageBox.critical(self.iface.mainWindow(), self.context, msg  + "\n\n" +
                                 "Error:\n   " + str(exc_obj) + "\n\n" +
                                 "In file:\n   " + filename + "\n\n" +
                                 "In function:\n   " +  function  + "\n\n" +
                                 "On line " + line)
        else:
            print(msg)        

    def log(self, msg, level):
        if self.iface is not None:
            QgsMessageLog.logMessage(msg, self.context, level)
        else:
            print(msg)

    def log_info(self, msg):
        if self.iface is not None:
            try:
                QgsMessageLog.logMessage(msg, self.context, QgsMessageLog.INFO)
            except TypeError:
                QgsMessageLog.logMessage(repr(msg), self.context, QgsMessageLog.INFO)
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
            m.setWindowTitle(self.context)
            m.setText(msg)
            m.setStandardButtons(QMessageBox.No | QMessageBox.Yes)
            m.setDefaultButton(QMessageBox.Yes)
            return True if m.exec_() == QMessageBox.Yes else False
        else:
            print(msg)

    def progress_bar(self, msg, minimum=0, maximum=0, init_value=0):
        pmb = self.iface.messageBar().createMessage(msg)
        pb = QProgressBar()
        pb.setMinimum(minimum)
        pb.setMaximum(maximum)
        pb.setValue(init_value)
        pb.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        pmb.layout().addWidget(pb)
        self.iface.messageBar().pushWidget(pmb, self.iface.messageBar().INFO)
        return pb

    def clear_bar_messages(self):
        self.iface.messageBar().clearWidgets()
