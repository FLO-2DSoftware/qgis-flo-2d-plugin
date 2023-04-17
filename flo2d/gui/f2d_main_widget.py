# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.PyQt.QtCore import QSize

from ..user_communication import UserCommunication
from .bc_editor_widget import BCEditorWidget
from .channels_editor_widget import ChannelsEditorWidget
from .fpxsec_editor_widget import FPXsecEditorWidget
from .grid_tools_widget import GridToolsWidget
from .ic_editor_widget import ICEditorWidget
from .infil_editor_widget import InfilEditorWidget
from .levee_and_breach_editor_widget import LeveeAndBreachEditorWidget
from .multiple_channels_editor_widget import MultipleChannelsEditorWidget
from .profile_tool import ProfileTool
from .rain_editor_widget import RainEditorWidget
from .storm_drain_editor_widget import StormDrainEditorWidget
from .street_editor_widget import StreetEditorWidget
from .struct_editor_widget import StructEditorWidget
from .ui_utils import load_ui, set_icon
from .xs_editor_widget import XsecEditorWidget

uiDialog, qtBaseClass = load_ui("f2d_widget")


class FLO2DWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs, plot, table):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.con = None
        self.lyrs = lyrs
        self.plot = plot
        self.table = table
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.setup_grid_tools()
        self.setup_bc_editor()
        self.setup_ic_editor()
        self.setup_street_editor()
        self.setup_struct_editor()
        self.setup_rain_editor()
        self.setup_channels_editor()
        self.setup_xsec_editor()
        self.setup_storm_drain_editor()
        self.setup_profile_tool()
        self.setup_fpxsec_editor()
        self.setup_infil_editor()
        self.setup_levee_and_breach_editor()
        self.setup_multiple_channels_editor()

        self.cgroups = [
            self.grid_tools_grp,
            self.bc_editor_grp,
            self.fpxsec_editor_grp,
            self.infil_editor_grp,
            self.storm_drain_editor_grp,
            self.ic_editor_grp,
            self.street_editor_grp,
            self.rain_editor_grp,
            self.channels_editor_grp,
            self.struct_editor_grp,
            self.xs_editor_grp,
            self.profile_tool_grp,
            self.levee_and_breach_editor_grp,
            self.multiple_channels_editor_grp,
        ]
        self.set_collapsible_groups()

        # connections
        self.collapse_groups_btn.clicked.connect(self.collapse_all_groups)
        self.expand_groups_btn.clicked.connect(self.expand_all_groups)

        # set icons
        set_icon(self.collapse_groups_btn, "collapse_groups.svg")
        set_icon(self.expand_groups_btn, "expand_groups.svg")

    def collapse_all_groups(self):
        for grp in self.cgroups:
            grp.setCollapsed(True)

    def expand_all_groups(self):
        for grp in self.cgroups:
            grp.setCollapsed(False)

    def setSizeHint(self, width, height):
        self._sizehint = QSize(width, height)

    def sizeHint(self):
        if self._sizehint is not None:
            return self._sizehint
        return super(FLO2DWidget, self).sizeHint()

    def setup_grid_tools(self):
        self.grid_tools = GridToolsWidget(self.iface, self.lyrs)
        self.grid_tools_lout.addWidget(self.grid_tools)

    def setup_xsec_editor(self):
        self.xs_editor = XsecEditorWidget(self.iface, self.plot, self.table, self.lyrs)
        self.xs_editor_lout.addWidget(self.xs_editor)

    def setup_bc_editor(self):
        self.bc_editor = BCEditorWidget(self.iface, self.plot, self.table, self.lyrs)
        self.bc_editor_lout.addWidget(self.bc_editor)

    def setup_struct_editor(self):
        self.struct_editor = StructEditorWidget(self.iface, self.plot, self.table, self.lyrs)
        self.struct_editor_lout.addWidget(self.struct_editor)

    def setup_ic_editor(self):
        self.ic_editor = ICEditorWidget(self.iface, self.lyrs)
        self.ic_editor_lout.addWidget(self.ic_editor)

    def setup_rain_editor(self):
        self.rain_editor = RainEditorWidget(self.iface, self.plot, self.table, self.lyrs)
        self.rain_editor_lout.addWidget(self.rain_editor)

    def setup_channels_editor(self):
        self.channels_editor = ChannelsEditorWidget(self.iface, self.lyrs)
        self.channels_editor_lout.addWidget(self.channels_editor)

    def setup_street_editor(self):
        self.street_editor = StreetEditorWidget(self.iface, self.lyrs)
        self.street_editor_lout.addWidget(self.street_editor)

    def setup_profile_tool(self):
        self.profile_tool = ProfileTool(self.iface, self.plot, self.table, self.lyrs)
        self.profile_tool_lout.addWidget(self.profile_tool)

    def setup_fpxsec_editor(self):
        self.fpxsec_editor = FPXsecEditorWidget(self.iface, self.lyrs)
        self.fpxsec_editor_lout.addWidget(self.fpxsec_editor)

    def setup_infil_editor(self):
        self.infil_editor = InfilEditorWidget(self.iface, self.lyrs)
        self.infil_editor_lout.addWidget(self.infil_editor)

    def setup_storm_drain_editor(self):
        self.storm_drain_editor = StormDrainEditorWidget(self.iface, self.plot, self.table, self.lyrs)
        self.storm_drain_editor_lout.addWidget(self.storm_drain_editor)

    def setup_levee_and_breach_editor(self):
        self.levee_and_breach_editor = LeveeAndBreachEditorWidget(self.iface, self.lyrs)
        self.levee_and_breach_lout.addWidget(self.levee_and_breach_editor)

    def setup_multiple_channels_editor(self):
        self.multiple_channels_editor = MultipleChannelsEditorWidget(self.iface, self.lyrs)
        self.multiple_channels_lout.addWidget(self.multiple_channels_editor)

    def set_collapsible_groups(self):
        for grp in self.cgroups:
            grp.setSettingGroup("FLO2DWidget")
            grp.setSaveCollapsedState(True)
            grp.setScrollOnExpand(True)
            grp.loadState()

    def save_collapsible_groups(self):
        for grp in self.cgroups:
            grp.saveState()
