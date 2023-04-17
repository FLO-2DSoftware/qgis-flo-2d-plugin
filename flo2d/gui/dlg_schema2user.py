# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import traceback

from qgis.PyQt.QtWidgets import QApplication

from ..flo2d_tools.schema2user_tools import (
    Schema1DConverter,
    SchemaBCConverter,
    SchemaFPXSECConverter,
    SchemaGridConverter,
    SchemaLeveesConverter,
    SchemaSWMMConverter,
)
from ..geopackage_utils import GeoPackageUtils
from .ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("schema2user")


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
        self.gutils = GeoPackageUtils(self.con, self.iface)

        # connections
        self.ckbox_domain.stateChanged.connect(self.convert_domain_checked)
        self.ckbox_bc.stateChanged.connect(self.convert_bc_checked)
        self.ckbox_1d.stateChanged.connect(self.convert_1d_checked)
        self.ckbox_levees.stateChanged.connect(self.convert_levees_checked)
        self.ckbox_fpxsec.stateChanged.connect(self.convert_fpxsec_checked)
        self.ckbox_swmm.stateChanged.connect(self.convert_swmm_checked)

        self.populate_components()

    def populate_components(self):
        schema_domain_tables = ["grid"]
        schema_bc_tables = ["all_schem_bc"]
        schema_1d_tables = ["chan", "chan_elems"]
        schema_levee_tables = ["levee_data"]
        schema_fpxsec_tables = ["fpxsec"]
        schema_swwmm_tables = ["swmmflo"]

        if all(self.gutils.is_table_empty(t) for t in schema_domain_tables):
            self.ckbox_domain.setDisabled(True)
        else:
            self.ckbox_domain.setEnabled(True)

        if any(self.gutils.is_table_empty(t) for t in schema_bc_tables):
            self.ckbox_bc.setDisabled(True)
        else:
            self.ckbox_bc.setEnabled(True)

        if any(self.gutils.is_table_empty(t) for t in schema_1d_tables):
            self.ckbox_1d.setDisabled(True)
        else:
            self.ckbox_1d.setEnabled(True)

        if any(self.gutils.is_table_empty(t) for t in schema_levee_tables):
            self.ckbox_levees.setDisabled(True)
        else:
            self.ckbox_levees.setEnabled(True)

        if any(self.gutils.is_table_empty(t) for t in schema_fpxsec_tables):
            self.ckbox_fpxsec.setDisabled(True)
        else:
            self.ckbox_fpxsec.setEnabled(True)

        if any(self.gutils.is_table_empty(t) for t in schema_swwmm_tables):
            self.ckbox_swmm.setDisabled(True)
        else:
            self.ckbox_swmm.setEnabled(True)

    def convert_domain_checked(self):
        if self.ckbox_domain.isChecked():
            self.methods[1] = self.convert_domain
        else:
            self.methods.pop(1)

    def convert_bc_checked(self):
        if self.ckbox_bc.isChecked():
            self.methods[2] = self.convert_bc
        else:
            self.methods.pop(2)

    def convert_1d_checked(self):
        if self.ckbox_1d.isChecked():
            self.methods[3] = self.convert_1d
        else:
            self.methods.pop(3)

    def convert_levees_checked(self):
        if self.ckbox_levees.isChecked():
            self.methods[4] = self.convert_levees
        else:
            self.methods.pop(4)

    def convert_fpxsec_checked(self):
        if self.ckbox_fpxsec.isChecked():
            self.methods[5] = self.convert_fpxsec
        else:
            self.methods.pop(5)

    def convert_swmm_checked(self):
        if self.ckbox_swmm.isChecked():
            self.methods[6] = self.convert_swmm
        else:
            self.methods.pop(6)

    def convert_domain(self):
        try:
            grid_converter = SchemaGridConverter(self.con, self.iface, self.lyrs)
            grid_converter.boundary_from_grid()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.bar_warn("Creating User Layers failed on Grid to Computational Domain conversion!")

    def convert_bc(self):
        try:
            bc_converter = SchemaBCConverter(self.con, self.iface, self.lyrs)
            bc_converter.create_user_bc()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.bar_warn("Creating User Layers failed on Boundary Conditions conversion!")

    def convert_1d(self):
        try:
            domain_converter = Schema1DConverter(self.con, self.iface, self.lyrs)
            domain_converter.create_user_lbank()
            domain_converter.create_user_xs()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.bar_warn("Creating User Layers failed on 1D Domain elements conversion!")

    def convert_levees(self):
        try:
            levee_converter = SchemaLeveesConverter(self.con, self.iface, self.lyrs)
            levee_converter.create_user_levees()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.bar_warn("Creating User Layers failed on Levees conversion!")

    def convert_fpxsec(self):
        try:
            fpxsec_converter = SchemaFPXSECConverter(self.con, self.iface, self.lyrs)
            fpxsec_converter.create_user_fpxsec()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.bar_warn("Creating User Layers failed on Floodplain cross-sections conversion!")

    def convert_swmm(self):
        try:
            swmm_converter = SchemaSWMMConverter(self.con, self.iface, self.lyrs)
            swmm_converter.create_user_swmm_nodes()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 040319.1915:\n\nConverting Schematic SD Inlets to User Storm Drain Nodes failed!"
                + "\n_______________________________________________________________",
                e,
            )
