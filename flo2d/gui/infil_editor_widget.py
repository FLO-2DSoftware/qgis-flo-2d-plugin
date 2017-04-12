# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import traceback

from collections import OrderedDict
from PyQt4.QtGui import QIcon, QComboBox, QCheckBox, QDoubleSpinBox, QSizePolicy, QInputDialog
from qgis.core import QgsFeatureRequest

from ui_utils import load_ui, center_canvas
from flo2d.geopackage_utils import GeoPackageUtils, connection_required
from flo2d.user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui('infil_editor')
uiDialog_pop, qtBaseClass_pop = load_ui('infil_global')


class InfilGlobal(uiDialog_pop, qtBaseClass_pop):

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.global_imethod = 0
        self.current_imethod = 0
        self.green_grp.toggled.connect(self.green_checked)
        self.scs_grp.toggled.connect(self.scs_checked)
        self.horton_grp.toggled.connect(self.horton_checked)
        self.cb_infchan.stateChanged.connect(self.infchan_changed)

    def save_imethod(self):
        self.global_imethod = self.current_imethod

    def green_checked(self):
        if self.green_grp.isChecked():
            if self.horton_grp.isChecked():
                self.horton_grp.setChecked(False)
            if self.scs_grp.isChecked():
                self.current_imethod = 3
            else:
                self.current_imethod = 1
        else:
            if self.scs_grp.isChecked():
                self.current_imethod = 2
            else:
                self.current_imethod = 0

    def scs_checked(self):
        if self.scs_grp.isChecked():
            if self.horton_grp.isChecked():
                self.horton_grp.setChecked(False)
            if self.green_grp.isChecked():
                self.current_imethod = 3
            else:
                self.current_imethod = 2
        else:
            if self.green_grp.isChecked():
                self.current_imethod = 1
            else:
                self.current_imethod = 0

    def horton_checked(self):
        if self.horton_grp.isChecked():
            if self.green_grp.isChecked():
                self.green_grp.setChecked(False)
            if self.scs_grp.isChecked():
                self.scs_grp.setChecked(False)
            self.current_imethod = 4
        else:
            self.current_imethod = 0

    def infchan_changed(self):
        if self.cb_infchan.isChecked():
            self.label_hydcxx.setEnabled(True)
            self.spin_hydcxx.setEnabled(True)
            self.chan_btn.setEnabled(True)
        else:
            self.label_hydcxx.setDisabled(True)
            self.spin_hydcxx.setDisabled(True)
            self.chan_btn.setDisabled(True)


class InfilEditorWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = None
        self.gutils = None
        self.infil_lyr = None
        self.infil_idx = 0
        self.params = [
            'infmethod', 'abstr', 'sati', 'satf', 'poros', 'soild', 'infchan', 'hydcall', 'soilall', 'hydcadj',
            'hydcxx', 'scsnall', 'abstr1', 'fhortoni', 'fhortonf', 'decaya'
        ]
        self.iglobal = InfilGlobal(self.iface, self.lyrs)
        self.groups = set()
        self.imethod_groups = {
            1: {self.iglobal.green_grp},
            2: {self.iglobal.scs_grp},
            3: {self.iglobal.green_grp, self.iglobal.scs_grp},
            4: {self.iglobal.horton_grp}
        }
        self.set_combo()
        self.set_icon(self.create_polygon_btn, 'mActionCapturePolygon.svg')
        self.set_icon(self.save_changes_btn, 'mActionSaveAllEdits.svg')
        self.set_icon(self.schema_btn, 'schematize_res.svg')
        self.set_icon(self.revert_changes_btn, 'mActionUndo.svg')
        self.set_icon(self.delete_btn, 'mActionDeleteSelected.svg')
        self.set_icon(self.change_name_btn, 'change_name.svg')
        self.global_params.clicked.connect(lambda: self.show_global_params())

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
            self.read_global_params()
            #self.infil_lyr = self.lyrs.data['user_infil']['qlyr']
            #self.infil_lyr.editingStopped.connect(lambda: self.populate_infil())

    def set_combo(self):
        sp = QSizePolicy()
        sp.setHorizontalPolicy(QSizePolicy.MinimumExpanding)
        self.infil_name_cbo = QComboBox(self)
        self.infil_name_cbo.setEditable(False)
        self.infil_name_cbo.setSizePolicy(sp)
        self.infil_name_cbo_layout.addWidget(self.infil_name_cbo)

    def show_groups(self):
        imethod = self.iglobal.global_imethod
        if imethod == 0:
            self.single_green_grp.setHidden(True)
            self.single_scs_grp.setHidden(True)
            self.single_horton_grp.setHidden(True)
        elif imethod == 1:
            self.single_green_grp.setHidden(False)
            self.single_scs_grp.setHidden(True)
            self.single_horton_grp.setHidden(True)
        elif imethod == 2:
            self.single_green_grp.setHidden(True)
            self.single_scs_grp.setHidden(False)
            self.single_horton_grp.setHidden(True)
        elif imethod == 3:
            self.single_green_grp.setHidden(False)
            self.single_scs_grp.setHidden(False)
            self.single_horton_grp.setHidden(True)
        elif imethod == 4:
            self.single_green_grp.setHidden(True)
            self.single_scs_grp.setHidden(True)
            self.single_horton_grp.setHidden(False)

    @connection_required
    def read_global_params(self):
        qry = '''SELECT {} FROM infil;'''.format(','.join(self.params))
        glob = self.gutils.execute(qry).fetchone()
        if glob is None:
            self.show_groups()
            return
        row = OrderedDict(zip(self.params, glob))
        try:
            method = row['infmethod']
            self.groups = self.imethod_groups[method]
        except KeyError:
            self.groups = set()
        for grp in self.groups:
            grp.setChecked(True)
            for obj in grp.children():
                if not isinstance(obj, (QDoubleSpinBox, QCheckBox)):
                    continue
                obj_name = obj.objectName()
                name = obj_name.split('_', 1)[-1]
                val = row[name]
                if isinstance(obj, QCheckBox):
                    obj.setChecked(bool(val))
                else:
                    obj.setValue(val)
        self.iglobal.save_imethod()
        self.show_groups()

    def write_global_params(self):
        qry = '''INSERT INTO infil ({0}) VALUES ({1});'''
        method = self.iglobal.global_imethod
        names = ['infmethod']
        vals = [method]
        try:
            self.groups = self.imethod_groups[method]
        except KeyError:
            self.groups = set()
        for grp in self.groups:
            for obj in grp.children():
                if not isinstance(obj, (QDoubleSpinBox, QCheckBox)):
                    continue
                obj_name = obj.objectName()
                name = obj_name.split('_', 1)[-1]
                if isinstance(obj, QCheckBox):
                    val = int(obj.isChecked())
                    obj.setChecked(bool(val))
                else:
                    val = obj.value()
                    obj.setValue(val)
                names.append(name)
                vals.append(val)
        self.gutils.clear_tables('infil')
        names_str = ', '.join(names)
        vals_str = ', '.join(['?'] * len(vals))
        qry = qry.format(names_str, vals_str)
        self.gutils.execute(qry, vals)

    @connection_required
    def show_global_params(self):
        ok = self.iglobal.exec_()
        if ok:
            self.iglobal.save_imethod()
            self.write_global_params()
            self.show_groups()
        else:
            self.read_global_params()
