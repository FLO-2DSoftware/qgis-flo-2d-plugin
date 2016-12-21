# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt4.QtCore import QSize
from .utils import load_ui
from xs_editor_widget import XsecEditorWidget
from bc_editor_widget import BCEditorWidget
from ic_editor_widget import ICEditorWidget
from street_editor_widget import StreetEditorWidget
from rain_editor_widget import RainEditorWidget
from profile_tool import ProfileTool
from ..user_communication import UserCommunication


uiDialog, qtBaseClass = load_ui('f2d_widget')


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
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.setup_bc_editor()
        self.setup_ic_editor()
        self.setup_street_editor()
        self.setup_rain_editor()
        self.setup_xsec_editor()
        self.setup_profile_tool()

        self.cgroups = [
            self.bc_editor_grp, self.evap_editor_grp, self.ic_editor_grp, self.street_editor_grp,
            self.profile_tool_grp, self.rain_editor_grp, self.xs_editor_grp
        ]
        self.set_collapsible_groups()

    def setSizeHint(self, width, height):
        self._sizehint = QSize(width, height)

    def sizeHint(self):
        if self._sizehint is not None:
            return self._sizehint
        return super(FLO2DWidget, self).sizeHint()

    def setup_xsec_editor(self):
        self.xs_editor = XsecEditorWidget(self.iface, self.plot, self.table, self.lyrs)
        self.xs_editor_lout.addWidget(self.xs_editor)

    def setup_bc_editor(self):
        self.bc_editor = BCEditorWidget(self.iface, self.plot, self.table, self.lyrs)
        self.bc_editor_lout.addWidget(self.bc_editor)

    def setup_ic_editor(self):
        self.ic_editor = ICEditorWidget(self.iface, self.lyrs)
        self.ic_editor_lout.addWidget(self.ic_editor)

    def setup_rain_editor(self):
        self.rain_editor = RainEditorWidget(self.iface, self.plot, self.table)
        self.rain_editor_lout.addWidget(self.rain_editor)

    def setup_street_editor(self):
        self.street_editor = StreetEditorWidget(self.iface, self.lyrs)
        self.street_editor_lout.addWidget(self.street_editor)

    def setup_profile_tool(self):
        self.profile_tool = ProfileTool(self.iface, self.plot, self.table, self.lyrs)
        self.profile_tool_lout.addWidget(self.profile_tool)

    def set_collapsible_groups(self):
        for grp in self.cgroups:
            grp.setSettingGroup('FLO-2D/Collapsible_groups')
            grp.setSaveCollapsedState(True)
            grp.setScrollOnExpand(True)
            grp.loadState()

    def save_collapsible_groups(self):
        for grp in self.cgroups:
            grp.saveState()
