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

from flo2d.flo2d_tools.schematic_tools import schematize_streets
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
        self.cb_infchan.stateChanged.connect(self.infchan_changed)

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
        self.infil_global = InfilGlobal(self.iface, self.lyrs)
        self.groups = []
        self.all_groups = [self.infil_global.green_grp, self.infil_global.scs_grp, self.infil_global.horton_grp]
        self.set_combo()
        self.set_icon(self.create_polygon_btn, 'mActionCapturePolygon.svg')
        self.set_icon(self.save_changes_btn, 'mActionSaveAllEdits.svg')
        self.set_icon(self.schema_btn, 'schematize_res.svg')
        self.set_icon(self.revert_changes_btn, 'mActionUndo.svg')
        self.set_icon(self.delete_btn, 'mActionDeleteSelected.svg')
        self.set_icon(self.change_name_btn, 'change_name.svg')
        self.global_params.clicked.connect(lambda: self.set_global_params())

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
            #self.infil_lyr = self.lyrs.data['user_infil']['qlyr']
            #self.infil_lyr.editingStopped.connect(lambda: self.populate_infil())

    def set_combo(self):
        sp = QSizePolicy()
        sp.setHorizontalPolicy(QSizePolicy.MinimumExpanding)
        self.infil_name_cbo = QComboBox(self)
        self.infil_name_cbo.setEditable(False)
        self.infil_name_cbo.setSizePolicy(sp)
        self.infil_name_cbo_layout.addWidget(self.infil_name_cbo)

    @connection_required
    def set_global_params(self):
        params = [
            'infmethod', 'abstr', 'sati', 'satf', 'poros', 'soild', 'infchan', 'hydcall', 'soilall', 'hydcadj',
            'hydcxx', 'scsnall', 'abstr1', 'fhortoni', 'fhortonf', 'decaya'
        ]
        qry = '''SELECT {} FROM infil;'''.format(','.join(params))
        glob = self.gutils.execute(qry).fetchone()
        row = OrderedDict(zip(params, glob))
        if glob is not None:
            method = row['infmethod']
            if method == 1:
                self.groups = [self.infil_global.green_grp]
            elif method == 2:
                self.groups = [self.infil_global.scs_grp]
            elif method == 3:
                self.groups = [self.infil_global.green_grp, self.infil_global.scs_grp]
            elif method == 4:
                self.groups = [self.infil_global.horton_grp]
            else:
                self.groups = []
        for g in self.all_groups:
            g.setChecked(False)
        for grp in self.groups:
            grp.setChecked(True)
            for obj in grp.children():
                if not isinstance(obj, (QDoubleSpinBox, QCheckBox)):
                    continue
                obj_name = obj.objectName()
                typ, name = obj_name.split('_', 1)
                val = row[name]
                if typ == 'cb':
                    obj.setChecked(bool(val))
                else:
                    obj.setValue(val)
        ok = self.infil_global.exec_()
