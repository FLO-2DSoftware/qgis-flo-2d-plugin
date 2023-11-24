# -*- coding: utf-8 -*-
import os

from PyQt5.QtCore import QSettings
import qgis
from PyQt5.QtWidgets import QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox
from qgis._core import QgsProject, QgsCoordinateReferenceSystem, QgsUnitTypes

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version


from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..utils import get_plugin_version, get_flo2dpro_version

uiDialog, qtBaseClass = load_ui("update_gpkg")


class UpdateGpkg(qtBaseClass, uiDialog):
    def __init__(self, con, iface):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.con = con
        self.setupUi(self)
        self.gutils = GeoPackageUtils(con, iface)

        self.populate_gpgk_data()

    def populate_gpgk_data(self):
        """
        Function to populate data to update_gpkg
        """
        s = QSettings()

        geo_path = self.gutils.get_gpkg_path()
        self.label_path.setText(geo_path)

        proj_name = os.path.splitext(os.path.basename(geo_path))[0]
        self.label_pn.setText(proj_name)

        sql = """SELECT srs_id FROM gpkg_contents WHERE table_name='grid';"""
        rc = self.gutils.execute(sql)
        rt = rc.fetchone()[0]
        crs = QgsCoordinateReferenceSystem()
        crs.createFromId(rt)
        self.proj_lab.setText(crs.description())

        if crs.mapUnits() == QgsUnitTypes.DistanceMeters:
            mu = "meters"
        elif crs.mapUnits() == QgsUnitTypes.DistanceFeet:
            mu = "feet"
        self.unit_lab.setText(mu)

        contact = QgsProject.instance().metadata().author()
        self.lineEdit_au.setText(contact)

        plugin_v = get_plugin_version()
        self.label_pv.setText(plugin_v)

        qgis_v = qgis.core.Qgis.QGIS_VERSION
        self.label_qv.setText(qgis_v)

        flo2d_v = get_flo2dpro_version(s.value("FLO-2D/last_flopro") + "/FLOPRO.exe")
        self.label_fv.setText(flo2d_v)

    def write(self):
        """
        Function to write the update gpkg data
        """

        proj_name = self.label_pn.text()
        sql = """SELECT srs_id FROM gpkg_contents WHERE table_name='grid';"""
        rc = self.gutils.execute(sql)
        rt = rc.fetchone()[0]
        crs = QgsCoordinateReferenceSystem()
        crs.createFromId(rt)
        units = self.unit_lab.text()
        contact = self.lineEdit_au.text()
        company = self.lineEdit_co.text()
        email = self.lineEdit_em.text()
        phone = self.lineEdit_te.text()
        plugin_v = self.label_pv.text()
        qgis_v = self.label_qv.text()
        flo2d_v = self.label_fv.text()
        cell_size = str(self.cellSizeDSpinBox.value())
        default_n = str(self.manningDSpinBox.value())

        self.gutils.set_metadata_par("PROJ_NAME", proj_name)
        self.gutils.set_metadata_par("CONTACT", contact)
        self.gutils.set_metadata_par("EMAIL", email)
        self.gutils.set_metadata_par("COMPANY", company)
        self.gutils.set_metadata_par("PHONE", phone)
        self.gutils.set_metadata_par("PLUGIN_V", plugin_v)
        self.gutils.set_metadata_par("QGIS_V", qgis_v)
        self.gutils.set_metadata_par("FLO-2D_V", flo2d_v)
        self.gutils.set_metadata_par("CRS", crs.authid())

        self.gutils.set_cont_par("CELLSIZE", cell_size)
        self.gutils.set_cont_par("MANNING", default_n)
        self.gutils.set_cont_par("PROJ", crs.toProj())
        self.gutils.set_cont_par("METRIC", units)

        self.gutils.fill_empty_mult_globals()