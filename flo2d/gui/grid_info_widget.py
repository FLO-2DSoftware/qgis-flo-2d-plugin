# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from math import sqrt
from PyQt4.QtCore import QSize
from .utils import load_ui
from qgis.core import QgsFeatureRequest

uiDialog, qtBaseClass = load_ui('grid_info_widget')


class GridInfoWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.lyrs = lyrs
        self.setupUi(self)
        self.setEnabled(True)
        self.grid = None
        self.mann_default = None

    def setSizeHint(self, width, height):
        self._sizehint = QSize(width, height)

    def sizeHint(self):
        # print('sizeHint:', self._sizehint)
        if self._sizehint is not None:
            return self._sizehint
        return super(GridInfoWidget, self).sizeHint()

    def set_info_layer(self, lyr):
        self.grid = lyr

    def update_fields(self, fid):
        if not fid == -1:
            feat = self.grid.getFeatures(QgsFeatureRequest(fid)).next()
            cell_size = sqrt(feat.geometry().area())
            elev = str(feat['elevation'])
            n = feat['n_value']
            cell = '{}'.format(cell_size)
            if not n:
                n = '{} (default)'.format(self.mann_default)
            else:
                pass
            self.elevEdit.setText(elev)
            self.mannEdit.setText(str(n))
            self.cellEdit.setText(cell)
        else:
            self.elevEdit.setText('')
            self.mannEdit.setText('')
            self.cellEdit.setText('')
