# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from math import isnan

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QInputDialog,
    QTableWidgetItem,
)

from ..flo2dobjects import InletRatingTable
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..utils import float_or_zero, int_or_zero, is_number, m_fdata
from .table_editor_widget import CommandItemEdit, StandardItem, StandardItemModel
from .ui_utils import load_ui, set_icon

uiDialog, qtBaseClass = load_ui("bridges")


class BridgesDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs, structName):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.structName = structName
        self.structFid = 0
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None

        self.setup_connection()
        self.populate_bridge()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_bridge(self):
        struct_fid = self.gutils.execute("SELECT fid FROM struct WHERE structname = ?;", (self.structName,)).fetchone()
        if struct_fid:
            self.structFid = struct_fid[0]
            if not self.structFid:
                self.uc.warn_bar("No data for structure " + structName)
            else:
                bridge_qry = "SELECT * FROM bridge_variables WHERE struct_fid = ?;"
                row = self.gutils.execute(bridge_qry, (self.structFid,)).fetchone()
                if not row:
                    insert_bridge_sql = """INSERT INTO bridge_variables
                                            (struct_fid, IBTYPE, COEFF, C_PRIME_USER, KF_COEF, 
                                            KWW_COEF,  KPHI_COEF, KY_COEF, KX_COEF, KJ_COEF, 
                                            BOPENING, BLENGTH, BN_VALUE, UPLENGTH12, LOWCHORD,
                                            DECKHT, DECKLENGTH, PIERWIDTH, SLUICECOEFADJ, ORIFICECOEFADJ, 
                                            COEFFWEIRB, WINGWALL_ANGLE, PHI_ANGLE, LBTOEABUT, RBTOEABUT)
                                            VALUES (?, 1,  0.1,  0.5, 0.9,  
                                                    1.0,  0.7,  0.85,  1.0, 0.6,  
                                                    0.0,  0.0,  0.030,  0.0, 0.0,  
                                                    0.0,  0.0,  0.0,  0.0, 0.0, 
                                                    2.65,  30,  0,  0, 0);"""
                    self.gutils.execute(insert_bridge_sql, (self.structFid,))
                row = self.gutils.execute(bridge_qry, (self.structFid,)).fetchone()

                self.IBTYPE_cbo.setCurrentIndex(int_or_zero(row[2] - 1))
                self.COEFF_dbox.setValue(float_or_zero(row[3]))
                self.C_PRIME_USER_dbox.setValue(float_or_zero(row[4]))
                self.KF_COEF_dbox.setValue(float_or_zero(row[5]))
                self.KWW_COEF_dbox.setValue(float_or_zero(row[6]))
                self.KPHI_COEF_dbox.setValue(float_or_zero(row[7]))
                self.KY_COEF_dbox.setValue(float_or_zero(row[8]))
                self.KX_COEF_dbox.setValue(float_or_zero(row[9]))
                self.KJ_COEF_dbox.setValue(float_or_zero(row[10]))
                self.BOPENING_dbox.setValue(float_or_zero(row[11]))
                self.BLENGTH_dbox.setValue(float_or_zero(row[12]))
                self.BN_VALUE_dbox.setValue(float_or_zero(row[13]))
                self.UPLENGTH12_dbox.setValue(float_or_zero(row[14]))
                self.LOWCHORD_dbox.setValue(float_or_zero(row[15]))
                self.DECKHT_dbox.setValue(float_or_zero(row[16]))
                self.DECKLENGTH_dbox.setValue(float_or_zero(row[17]))
                self.PIERWIDTH_dbox.setValue(float_or_zero(row[18]))
                self.SLUICECOEFADJ_dbox.setValue(float_or_zero(row[19]))
                self.ORIFICECOEFADJ_dbox.setValue(float_or_zero(row[20]))
                self.COEFFWEIRB_dbox.setValue(float_or_zero(row[21]))
                self.WINGWALL_ANGLE_dbox.setValue(float_or_zero(row[22]))
                self.PHI_ANGLE_dbox.setValue(float_or_zero(row[23]))
                self.LBTOEABUT_dbox.setValue(float_or_zero(row[24]))
                self.RBTOEABUT_dbox.setValue(float_or_zero(row[25]))

    def save_bridge_variables(self):
        """
        Save changes to bridge variables.
        """

        try:
            update_qry = """
            UPDATE bridge_variables
            SET 
                 IBTYPE = ?,
                 COEFF = ?,
                 C_PRIME_USER = ?,
                 KF_COEF = ?,
                 KWW_COEF = ?,
                 KPHI_COEF = ?,
                 KY_COEF = ?,
                 KX_COEF = ?,
                 KJ_COEF = ?,
                 BOPENING = ?,
                 BLENGTH = ?,
                 BN_VALUE = ?,
                 UPLENGTH12 = ?,
                 LOWCHORD = ?,
                 DECKHT = ?,
                 DECKLENGTH = ?,
                 PIERWIDTH = ?,
                 SLUICECOEFADJ = ?,
                 ORIFICECOEFADJ = ?,
                 COEFFWEIRB = ?,
                 WINGWALL_ANGLE = ?,
                 PHI_ANGLE = ?,
                 LBTOEABUT = ?,
                 RBTOEABUT = ?
            WHERE struct_fid = ? ; """

            self.gutils.execute(
                update_qry,
                (
                    self.IBTYPE_cbo.currentIndex() + 1,
                    self.COEFF_dbox.value(),
                    self.C_PRIME_USER_dbox.value(),
                    self.KF_COEF_dbox.value(),
                    self.KWW_COEF_dbox.value(),
                    self.KPHI_COEF_dbox.value(),
                    self.KY_COEF_dbox.value(),
                    self.KX_COEF_dbox.value(),
                    self.KJ_COEF_dbox.value(),
                    self.BOPENING_dbox.value(),
                    self.BLENGTH_dbox.value(),
                    self.BN_VALUE_dbox.value(),
                    self.UPLENGTH12_dbox.value(),
                    self.LOWCHORD_dbox.value(),
                    self.DECKHT_dbox.value(),
                    self.DECKLENGTH_dbox.value(),
                    self.PIERWIDTH_dbox.value(),
                    self.SLUICECOEFADJ_dbox.value(),
                    self.ORIFICECOEFADJ_dbox.value(),
                    self.COEFFWEIRB_dbox.value(),
                    self.WINGWALL_ANGLE_dbox.value(),
                    self.PHI_ANGLE_dbox.value(),
                    self.LBTOEABUT_dbox.value(),
                    self.RBTOEABUT_dbox.value(),
                    self.structFid,
                ),
            )

            return True
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 030220.0743: update of hydraulic structure bridge variables failed!"
                + "\n__________________________________________________",
                e,
            )
            return False
        pass
