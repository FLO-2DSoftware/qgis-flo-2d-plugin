# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import traceback

from ..flo2d_tools.schema2user_tools import (
    Schema1DConverter,
    SchemaBCConverter,
    SchemaFPXSECConverter,
    SchemaGridConverter,
    SchemaInfiltrationConverter,
    SchemaLeveesConverter,
    SchemaSWMMConverter,
)
from .ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("user2schema")


class User2SchemaDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs, uc):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.uc = uc
        self.methods = {}
        self.message = ""

        # connections
        self.user_bc_chbox.stateChanged.connect(self.convert_user_bc_checked)
        self.user_streets_chbox.stateChanged.connect(self.convert_user_streets_checked)
        self.user_channels_chbox.stateChanged.connect(self.convert_user_channels_checked)
        self.user_levees_chbox.stateChanged.connect(self.convert_user_levees_checked)
        self.user_structures_chbox.stateChanged.connect(self.convert_user_structures_checked)
        self.user_reservoirs_chbox.stateChanged.connect(self.convert_reservoirs_checked)
        self.user_fpxsec_chbox.stateChanged.connect(self.convert_user_fpxsec_checked)
        self.user_infil_chbox.stateChanged.connect(self.convert_user_infil_checked)
        self.user_storm_drains_chbox.stateChanged.connect(self.convert_user_storm_drains_checked)

    def convert_user_bc_checked(self):
        if self.user_bc_chbox.isChecked():
            self.methods[1] = self.convert_user_bc
        else:
            self.methods.pop(1)

    def convert_user_streets_checked(self):
        if self.user_streets_chbox.isChecked():
            self.methods[2] = self.convert_user_streets
        else:
            self.methods.pop(2)

    def convert_user_channels_checked(self):
        if self.user_channels_chbox.isChecked():
            self.methods[3] = self.convert_user_channels
        else:
            self.methods.pop(3)

    def convert_user_levees_checked(self):
        if self.user_levees_chbox.isChecked():
            self.methods[4] = self.convert_user_levees
        else:
            self.methods.pop(4)

    def convert_user_structures_checked(self):
        if self.user_structures_chbox.isChecked():
            self.methods[5] = self.convert_user_structures
        else:
            self.methods.pop(5)

    def convert_reservoirs_checked(self):
        if self.user_reservoirs_chbox.isChecked():
            self.methods[6] = self.convert_user_reservoirs
        else:
            self.methods.pop(6)

    def convert_user_fpxsec_checked(self):
        if self.user_fpxsec_chbox.isChecked():
            self.methods[7] = self.convert_user_fpxsec
        else:
            self.methods.pop(7)

    def convert_user_infil_checked(self):
        if self.user_infil_chbox.isChecked():
            self.methods[8] = self.convert_user_infil
        else:
            self.methods.pop(8)

    def convert_user_storm_drains_checked(self):
        if self.user_storm_drains_chbox.isChecked():
            self.methods[9] = self.convert_user_storm_drains
        else:
            self.methods.pop(9)

    def convert_user_bc(self):
        self.message += "User boundary conditions converted!\n"
        pass

    def convert_user_streets(self):
        self.message += "User streets converted!\n"
        pass

    def convert_user_channels(self):
        self.message += "User channels converted!\n"
        pass

    def convert_user_levees(self):
        self.message += "User levees converted!\n"
        pass

    def convert_user_structures(self):
        self.message += "User structures converted!\n"
        pass

    def convert_user_reservoirs(self):
        self.message += "User reservoirs converted!\n"
        pass

    def convert_user_fpxsec(self):
        self.message += "User floodplain xsections converted!\n"
        pass

    def convert_user_infil(self):
        self.message += "User infiltration converted!\n"
        pass

    def convert_user_storm_drains(self):
        self.message += "User storm drains converted!\n"
        pass
