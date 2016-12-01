# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt4.QtCore import QEvent, QObject, Qt
from PyQt4.QtGui import QStandardItemModel, QStandardItem, QColor, QIcon, QComboBox, QSizePolicy
from qgis.core import QgsFeatureRequest
from .utils import load_ui, center_canvas, try_disconnect
from ..geopackage_utils import GeoPackageUtils
from ..schematic_tools import schematize_streets
from ..flo2dobjects import Street
from ..user_communication import UserCommunication
from ..utils import m_fdata, is_number
from math import isnan
import os
import traceback


uiDialog, qtBaseClass = load_ui('street_editor')
uiDialog_pop, qtBaseClass_pop = load_ui('street_global')


class StreetGeneral(uiDialog_pop, qtBaseClass_pop):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')


class StreetEditorWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.gutils = None
        self.street_lyr = None
        self.set_combo()
        self.set_icon(self.create_street, 'mActionCaptureLine.svg')
        self.set_icon(self.save_changes_btn, 'mActionSaveAllEdits.svg')
        self.set_icon(self.revert_changes_btn, 'mActionUndo.svg')
        self.set_icon(self.delete_street, 'mActionDeleteSelected.svg')
        self.set_icon(self.change_street_name_btn, 'change_name.svg')
        self.create_street.clicked.connect(self.create_street_line)
        self.global_params.clicked.connect(self.set_general)
        self.save_changes_btn.clicked.connect(self.save_street_edits)
        self.street_name_cbo.activated.connect(self.street_changed)

    @staticmethod
    def set_icon(btn, icon_file):
        idir = os.path.join(os.path.dirname(__file__), '..\\img')
        btn.setIcon(QIcon(os.path.join(idir, icon_file)))

    def setup_gutils(self):
        if self.gutils is None:
            gutils = GeoPackageUtils(self.iface.f2d['con'], self.iface)
            if gutils.con is None:
                msg = 'Connect to a GeoPackage!'
                self.uc.bar_warn(msg)
                return
            else:
                self.gutils = gutils
                self.street_lyr = self.lyrs.get_layer_by_name('Street Lines', group=self.lyrs.group).layer()

    def set_combo(self):
        sp = QSizePolicy()
        sp.setHorizontalPolicy(QSizePolicy.MinimumExpanding)
        self.street_name_cbo = QComboBox(self)
        self.street_name_cbo.setEditable(False)
        self.street_name_cbo.setSizePolicy(sp)
        self.street_name_cbo_layout.addWidget(self.street_name_cbo)

    def populate_streets(self):
        self.street_name_cbo.clear()
        self.setup_gutils()
        if self.gutils is None:
            return
        qry = '''SELECT fid, name, n_value, elevation, curb_height, street_width FROM user_streets;'''
        for street in self.gutils.execute(qry):
            name = street[1]
            self.street_name_cbo.addItem(name, street)
        self.street_changed()

    def street_changed(self):
        street_idx = self.street_name_cbo.currentIndex()
        cur_data = self.street_name_cbo.itemData(street_idx)
        if cur_data:
            fid, name, n_value, elevation, curb_height, street_width = cur_data
            self.spin_n.setValue(n_value)
            self.spin_e.setValue(elevation)
            self.spin_h.setValue(curb_height)
            self.spin_w.setValue(street_width)
        else:
            return
        if self.street_center_chbox.isChecked():
            feat = self.street_lyr.getFeatures(QgsFeatureRequest(fid)).next()
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def create_street_line(self):
        if not self.lyrs.enter_edit_mode('user_streets'):
            return

    def save_street_edits(self):
        """Save changes of user street layer"""
        self.setup_gutils()
        if not self.lyrs.save_edits_and_proceed("Street Lines"):
            return
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return
        if self.gutils.is_table_empty('user_streets'):
            self.uc.bar_warn("There is no any user streets to schematize! Please digitize them before running tool.")
            return
        cell_size = float(self.gutils.get_cont_par('CELLSIZE'))
        try:
            schematize_streets(self.gutils, self.street_lyr, cell_size)
            streets_schem = self.lyrs.get_layer_by_name("Streets", group=self.lyrs.group).layer()
            if streets_schem:
                streets_schem.triggerRepaint()
            self.uc.show_info("Streets schematized!")
        except Exception as e:
            self.uc.show_warn("Schematizing of streets aborted! Please check Street Lines layer.")
            self.uc.log_info(traceback.format_exc())
            return
        self.populate_streets()

    def set_general(self):
        self.setup_gutils()
        if self.gutils is None:
            return
        qry = '''SELECT strfno, strman, depx, widst, istrflo FROM street_general;'''
        gen = self.gutils.execute(qry).fetchone()
        street_general = StreetGeneral(self.iface, self.lyrs)
        if gen is not None:
            froude, n, curb, width, i2s = gen
            street_general.global_froude.setValue(froude)
            street_general.global_n.setValue(n)
            street_general.global_curb.setValue(curb)
            street_general.global_width.setValue(width)
            if i2s == 1:
                street_general.inflow_to_street.setChecked(True)
            else:
                street_general.inflow_to_street.setChecked(False)
        ok = street_general.exec_()
        if ok:
            self.gutils.clear_tables('street_general')
            update_qry = '''INSERT INTO street_general (strfno, strman, depx, widst, istrflo) VALUES (?,?,?,?,?);'''
            froude = street_general.global_froude.value()
            n = street_general.global_n.value()
            curb = street_general.global_curb.value()
            width = street_general.global_width.value()
            i2s = 1 if street_general.inflow_to_street.isChecked() else 0
            self.gutils.execute(update_qry, (froude, n, curb, width, i2s))
        else:
            return
