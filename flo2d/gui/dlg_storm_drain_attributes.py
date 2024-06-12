# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QDockWidget

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version


from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui("inlet_attributes")


class InletAttributes(qtBaseClass, uiDialog):
    def __init__(self, con, iface, layers):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = layers
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = con
        self.gutils = GeoPackageUtils(con, iface)

        # Create a dock widget
        self.dock_widget = QDockWidget("", self.iface.mainWindow())
        self.dock_widget.setObjectName("Inlets/Junctions")
        self.dock_widget.setWidget(self)
