# -*- coding: utf-8 -*-
from .table_editor_widget import StandardItemModel
# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui("areas_editor")


class AreasEditorWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.con = None
        self.setupUi(self)
        self.lyrs = lyrs
        self.gutils = None
        self.uc = UserCommunication(iface, "FLO-2D")

        self.setup_connection()

        self.areas_grps = {
            self.ne_channel_grp: 'user_noexchange_chan_areas',
            self.building_areas_grp: 'buildings_areas',
            self.shallown_grp: 'spatialshallow',
            self.froude_areas_grp: 'fpfroude',
            self.tolerance_areas_grp: 'tolspatial',
            self.blocked_areas_grp: 'user_blocked_areas',
            self.roughness_grp: 'user_roughness',
            self.steep_slopen_grp: ''
        }

        self.areas_grp_cbo = {
            self.noexchange_cbo: 'user_noexchange_chan_areas',
            self.buildings_cbo: 'buildings_areas',
            self.shallown_cbo: 'spatialshallow',
            self.froude_cbo: 'fpfroude',
            self.tolerance_cbo: 'tolspatial',
            self.blocked_cbo: 'user_blocked_areas',
            self.roughness_cbo: 'user_roughness',
            self.steep_slopen_cbo: 'user_steep_slope_n'
        }

        self.populate_grps()

        self.areas_cbo.currentIndexChanged.connect(self.populate_grps)
        self.create_polygon_btn.clicked.connect(self.create_areas_polygon)
        self.revert_changes_btn.clicked.connect(self.revert_changes)

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        self.con = con
        self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_grps(self):
        """
        This function populates the groups on the editor based on the areas_cbo
        """
        selected_areas_idx = self.areas_cbo.currentIndex()
        if selected_areas_idx != 0:
            self.enable_btns(True)
            for i, areas_grp in enumerate(self.areas_grps.keys(), start=1):
                if i == selected_areas_idx:
                    areas_grp.setVisible(True)
                else:
                    areas_grp.setVisible(False)
        else:
            self.enable_btns(False)
            for areas_grp in self.areas_grps.keys():
                areas_grp.setVisible(False)

    def enable_btns(self, enable):
        """
        Function to enable or disable the buttons based on the selected areas
        """
        self.create_polygon_btn.setEnabled(enable)
        self.revert_changes_btn.setEnabled(enable)
        self.schema_btn.setEnabled(enable)

    def create_areas_polygon(self):

        selected_areas_idx = self.areas_cbo.currentIndex()
        selected_areas_name = self.areas_cbo.currentText()
        if selected_areas_idx != 0:
            for i, areas_lyr in enumerate(self.areas_grps.values(), start=1):
                if i == selected_areas_idx:
                    if self.lyrs.any_lyr_in_edit(areas_lyr):
                        self.uc.bar_info(f"{selected_areas_name} saved!")
                        self.uc.log_info(f"{selected_areas_name} saved!")
                        self.lyrs.save_lyrs_edits(areas_lyr)
                        self.create_polygon_btn.setChecked(False)
                        self.populate_cbos()
                        return
                    else:
                        self.create_polygon_btn.setChecked(True)
                        self.lyrs.enter_edit_mode(areas_lyr)

    def revert_changes(self):

        selected_areas_idx = self.areas_cbo.currentIndex()
        if selected_areas_idx != 0:
            for i, areas_lyr in enumerate(self.areas_grps.values(), start=1):
                if i == selected_areas_idx:
                    self.lyrs.rollback_lyrs_edits(areas_lyr)
                    self.populate_cbos()

    def populate_cbos(self):

        pass


