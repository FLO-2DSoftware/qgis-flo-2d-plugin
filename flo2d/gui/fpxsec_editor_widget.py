# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt4.QtCore import Qt
from PyQt4.QtGui import QColor, QIcon, QComboBox, QSizePolicy, QInputDialog
from qgis.core import QgsFeatureRequest
from .utils import load_ui, center_canvas, try_disconnect
from ..flo2dobjects import Reservoir
from ..geopackage_utils import GeoPackageUtils, connection_required
from ..user_communication import UserCommunication
from ..utils import m_fdata, is_number
from table_editor_widget import StandardItemModel, StandardItem, CommandItemEdit
from math import isnan
import os


uiDialog, qtBaseClass = load_ui('fpxsec_editor')


class FPXsecEditorWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.con = None
        self.gutils = None
        self.uc = UserCommunication(iface, 'FLO-2D')

        # set button icons
        self.set_icon(self.add_user_fpxs_btn, 'add_fpxs.svg')
        self.set_icon(self.save_changes_btn, 'mActionSaveAllEdits.svg')
        self.set_icon(self.revert_changes_btn, 'mActionUndo.svg')
        self.set_icon(self.delete_fpxs_btn, 'mActionDeleteSelected.svg')
        self.set_icon(self.schem_fpxs_btn, 'schematize_fpxs.svg')
        self.set_icon(self.rename_fpxs_btn, 'change_name.svg')
        idir = os.path.join(os.path.dirname(__file__), '..\\img')
        for i in range(8):
            icon_file = 'arrow_{}.svg'.format(i+1)
            self.flow_dir_cbo.setItemIcon(i, QIcon(os.path.join(idir, icon_file)))

        # connections
        self.add_user_fpxs_btn.clicked.connect(self.create_user_fpxs)
        self.save_changes_btn.clicked.connect(self.save_fpxs_lyr_edits)
        self.revert_changes_btn.clicked.connect(self.revert_fpxs_lyr_edits)
        self.delete_fpxs_btn.clicked.connect(self.delete_cur_fpxs)
        self.schem_fpxs_btn.clicked.connect(self.schematize_fpxs)
        self.rename_fpxs_btn.clicked.connect(self.rename_fpxs)
        self.fpxs_cbo.activated.connect(self.cur_fpxs_changed)
        self.flow_dir_cbo.activated.connect(self.save_fpxs)

    @staticmethod
    def set_icon(btn, icon_file):
        idir = os.path.join(os.path.dirname(__file__), '..\\img')
        btn.setIcon(QIcon(os.path.join(idir, icon_file)))

    def populate_cbos(self, fid=None, show_last_edited=False):
        pass

    def cur_fpxs_changed(self, cur_idx):
        pass

    def show_fpxs_rb(self):
        pass

    def create_user_fpxs(self):
        pass

    def save_fpxs_lyr_edits(self):
        pass

    def rename_fpxs(self):
        pass

    def repaint_fpxs(self):
        pass

    def revert_fpxs_lyr_edits(self):
        pass

    def delete_cur_fpxs(self):
        pass

    def schematize_fpxs(self):
        pass

    def save_fpxs(self):
        pass

