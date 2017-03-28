# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import traceback
from flo2d.flo2d_tools.schematic_conversion import (
    SchemaBCConverter,
    SchemaDomainConverter,
    SchemaLeveesConverter,
    ModelBoundaryConverter
)
from ui_utils import load_ui

uiDialog, qtBaseClass = load_ui('schema2user')


class Schema2UserDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, lyrs, uc):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.uc = uc
        self.methods = {}

        # connections
        self.ckbox_bc.stateChanged.connect(self.convert_bc_checked)
        self.ckbox_1d.stateChanged.connect(self.convert_1d_checked)
        self.ckbox_levees.stateChanged.connect(self.convert_levees_checked)
        self.ckbox_grid.stateChanged.connect(self.convert_grid_checked)

        self.ckbox_bc.setChecked(True)
        self.ckbox_1d.setChecked(True)
        self.ckbox_levees.setChecked(True)
        self.ckbox_grid.setChecked(True)

    def convert_bc_checked(self):
        if self.ckbox_bc.isChecked():
            self.methods[1] = self.convert_bc
        else:
            self.methods.pop(1)

    def convert_1d_checked(self):
        if self.ckbox_1d.isChecked():
            self.methods[2] = self.convert_1d
        else:
            self.methods.pop(2)

    def convert_levees_checked(self):
        if self.ckbox_levees.isChecked():
            self.methods[3] = self.convert_levees
        else:
            self.methods.pop(3)

    def convert_grid_checked(self):
        if self.ckbox_grid.isChecked():
            self.methods[4] = self.convert_grid
        else:
            self.methods.pop(4)

    def convert_bc(self):
        try:
            bc_converter = SchemaBCConverter(self.con, self.iface, self.lyrs)
            bc_converter.create_user_bc()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.bar_warn("Creating user layers failed on Boundary Conditions conversion!")

    def convert_1d(self):
        try:
            domain_converter = SchemaDomainConverter(self.con, self.iface, self.lyrs)
            domain_converter.create_user_lbank()
            domain_converter.create_user_xs()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.bar_warn("Creating user layers failed on 1D Domain elements conversion!")

    def convert_levees(self):
        try:
            levee_converter = SchemaLeveesConverter(self.con, self.iface, self.lyrs)
            levee_converter.create_user_levees()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.bar_warn("Creating user layers failed on Levees conversion!")

    def convert_grid(self):
        try:
            grid_converter = ModelBoundaryConverter(self.con, self.iface, self.lyrs)
            grid_converter.boundary_from_grid()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.bar_warn("Creating user layers failed on Grid conversion!")
