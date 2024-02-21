# -*- coding: utf-8 -*-
# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from flo2d.gui.ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("channel_check_report")


class ChannelCheckReportDialog(qtBaseClass, uiDialog):

    def __init__(self, iface):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.close_btn.clicked.connect(self.close_dialog)

    def close_dialog(self):
        """
        Function to close the dialog
        """
        self.report_te.clear()
        self.close()
