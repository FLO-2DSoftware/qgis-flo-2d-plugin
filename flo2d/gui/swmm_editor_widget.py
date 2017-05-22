# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import traceback
from math import isnan
from itertools import chain
from collections import OrderedDict
from PyQt4.QtCore import pyqtSignal, pyqtSlot, Qt
from PyQt4.QtGui import QIcon, QCheckBox, QDoubleSpinBox, QInputDialog, QStandardItemModel, QStandardItem, QApplication
from qgis.core import QGis, QgsFeatureRequest
from ui_utils import load_ui, center_canvas
from flo2d.utils import m_fdata
from flo2d.geopackage_utils import GeoPackageUtils, connection_required
from flo2d.user_communication import UserCommunication
from flo2d.flo2d_tools.grid_tools import poly2grid
from flo2d.flo2d_ie.swmm_import import StormDrainProject

uiDialog, qtBaseClass = load_ui('swmm_editor')


class SWMMEditorWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = None
        self.gutils = None
        self.grid_lyr = None
        self.swmm_lyr = None
        self.schema_green = None
        self.schema_inlets = None
        self.schema_outlets = None
        self.all_schema = []
        self.swmm_idx = 0
        self.groups = set()

        self.swmm_columns = [
            'intype', 'swmm_length', 'swmm_width', 'swmm_height', 'swmm_coeff', 'flapgate', 'curbheight', 'out_flo'
        ]
        self.slices = {
            1: slice(0, 7),
            2: slice(7, 8),
        }
        self.set_icon(self.create_point_btn, 'mActionCapturePoint.svg')
        self.set_icon(self.save_changes_btn, 'mActionSaveAllEdits.svg')
        self.set_icon(self.schema_btn, 'schematize_res.svg')
        self.set_icon(self.revert_changes_btn, 'mActionUndo.svg')
        self.set_icon(self.delete_btn, 'mActionDeleteSelected.svg')
        self.set_icon(self.change_name_btn, 'change_name.svg')

        self.create_point_btn.clicked.connect(lambda: self.create_swmm_point())
        self.save_changes_btn.clicked.connect(lambda: self.save_swmm_edits())
        self.revert_changes_btn.clicked.connect(lambda: self.revert_swmm_lyr_edits())
        self.delete_btn.clicked.connect(lambda: self.delete_cur_swmm())
        self.change_name_btn.clicked.connect(lambda: self.rename_swmm())
        self.schema_btn.clicked.connect(lambda: self.schematize_swmm())
        self.import_inp.clicked.connect(lambda: self.import_swmm_input())

    def create_swmm_point(self):
        pass

    def save_swmm_edits(self):
        pass

    def revert_swmm_lyr_edits(self):
        pass

    def delete_cur_swmm(self):
        pass

    def rename_swmm(self):
        pass

    def schematize_swmm(self):
        pass

    def import_swmm_input(self):
        pass

    @staticmethod
    def set_icon(btn, icon_file):
        idir = os.path.join(os.path.dirname(__file__), '..\\img')
        btn.setIcon(QIcon(os.path.join(idir, icon_file)))

    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
            self.grid_lyr = self.lyrs.data['grid']['qlyr']
            self.swmm_lyr = self.lyrs.data['user_swmm']['qlyr']
            self.schema_inlets = self.lyrs.data['swmmflo']['qlyr']
            self.schema_outlets = self.lyrs.data['swmmoutf']['qlyr']
            self.all_schema += [self.schema_inlets, self.schema_outlets]
            self.swmm_lyr.editingStopped.connect(self.populate_swmm)
            self.swmm_name_cbo.activated.connect(self.swmm_changed)

    def repaint_schema(self):
        for lyr in self.all_schema:
            lyr.triggerRepaint()

    def populate_swmm(self):
        pass

    def swmm_changed(self):
        pass
