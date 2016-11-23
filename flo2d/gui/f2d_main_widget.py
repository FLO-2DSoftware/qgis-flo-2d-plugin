# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt4.QtCore import QSize
from .utils import load_ui
from bc_editor_widget import BCEditorWidget
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

    def setSizeHint(self, width, height):
        self._sizehint = QSize(width, height)

    def sizeHint(self):
        # print('sizeHint:', self._sizehint)
        if self._sizehint is not None:
            return self._sizehint
        return super(FLO2DWidget, self).sizeHint()

    def setup_bc_editor(self):
        self.bc_editor = BCEditorWidget(self.iface, self.plot, self.table, self.lyrs)
        self.bc_editor_lout.addWidget(self.bc_editor)
