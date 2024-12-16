# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import os
import time
from itertools import chain

import qgis
from qgis._core import QgsProject
from qgis.core import QgsCoordinateReferenceSystem, QgsUnitTypes
from qgis.gui import QgsProjectionSelectionWidget
from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QLineEdit,
    QSpinBox,
)

from .dlg_flopro import ExternalProgramFLO2D
from ..errors import Flo2dQueryResultNull
from ..flo2d_ie.flo2d_parser import ParseDAT
from ..geopackage_utils import (
    GeoPackageUtils,
    database_connect,
    database_create,
    database_disconnect,
)
from ..misc.invisible_lyrs_grps import InvisibleLayersAndGroups
from ..user_communication import UserCommunication
from ..utils import is_number, get_plugin_version, get_flo2dpro_version
from .ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("settings")


class SettingsDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs, gutils):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.ilg = InvisibleLayersAndGroups(self.iface)
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.setModal(True)
        self.con = con
        self.parser = ParseDAT()
        self.lyrs = lyrs
        self.gutils = gutils
        self.si_units = None
        self.crs = None
        self.projectionSelector = QgsProjectionSelectionWidget()
        self.projectionSelector.setCrs(self.iface.mapCanvas().mapSettings().destinationCrs())
        self.widget_map = {
            "MANNING": self.manningDSpinBox,
            "CELLSIZE": self.cellSizeDSpinBox,
        }

        self.setup()

        # connection
        self.gpkgCreateBtn.clicked.connect(self.create_db)

        self.groupBox.setEnabled(False)
        self.groupBox_2.setEnabled(False)

    def set_metadata(
                    self,
                    proj_name,
                    contact,
                    email,
                    company,
                    phone,
                    plugin_v,
                    qgis_v,
                    flo2d_v,
                    crs):
        """
        Function to set the geopackage metadata
        """

        defaults = {
            "PROJ_NAME": proj_name,
            "CONTACT": contact,
            "EMAIL": email,
            "COMPANY": company,
            "PHONE": phone,
            "PLUGIN_V": plugin_v,
            "QGIS_V": qgis_v,
            "FLO-2D_V": flo2d_v,
            "CRS": crs,
        }
        qry = """INSERT INTO metadata (name, value, note) VALUES (?,?,?);"""

        parameters = defaults.items()

        values = []
        for param, val in parameters:
            row = (param, val, GeoPackageUtils.METADATA_DESCRIPTION[param])
            values.append(row)

        self.con.executemany(qry, values)

    def set_default_controls(self, con):
        defaults = {
            "build": None,
            "COURCHAR_C": "C",
            "COURCHAR_T": "T",
            "COURANTC": 0.6,
            "COURANTFP": 0.6,
            "COURANTST": 0.6,
            "NOPRTC": 2,
            "SHALLOWN": 0.2,
            "TOLGLOBAL": 0.004,
            "NOPRTFP": 2,
            "TOUT": 0.1,
            "SIMUL": 0.1,
            "GRAPTIM": 0.1
        }
        qry = """INSERT INTO cont (name, value, note) VALUES (?,?,?);"""
        cont_rows = self.parser.cont_rows
        toler_rows = self.parser.toler_rows
        extra_rows = [["IHOURDAILY", "IDEPLT"]]
        parameters = chain(
            chain.from_iterable(cont_rows),
            chain.from_iterable(toler_rows),
            chain.from_iterable(extra_rows),
        )
        values = []
        for param in parameters:
            if param in defaults:
                val = defaults[param]
            else:
                val = 0
            row = (param, val, GeoPackageUtils.PARAMETER_DESCRIPTION[param])
            values.append(row)
        con.executemany(qry, values)

    def read(self):
        for name, wid in self.widget_map.items():
            qry = """SELECT value FROM cont WHERE name = ?;"""
            row = self.gutils.execute(qry, (name,)).fetchone()
            if not row:
                QApplication.restoreOverrideCursor()
                msg = "Database query for param {} from cont table return null. Check your DB.".format(name)
                raise Flo2dQueryResultNull(msg)
            value = row[0]
            if isinstance(wid, QLineEdit):
                wid.setText(str(value))
            elif isinstance(wid, QCheckBox):
                wid.setChecked(int(value))
            elif isinstance(wid, QSpinBox):
                if value and is_number(value):
                    wid.setValue(int(float(value)))
                else:
                    pass
            elif isinstance(wid, QDoubleSpinBox):
                if value and is_number(value):
                    wid.setValue(float(value))
                else:
                    pass
            else:
                pass
        cs = QgsCoordinateReferenceSystem()
        proj = self.gutils.get_grid_crs()
        if proj:
            cs.createFromUserInput(proj)
        else:
            proj = self.gutils.get_cont_par("PROJ")
            cs.createFromProj(proj)
        self.projectionSelector.setCrs(cs)
        self.crs = self.projectionSelector.crs()
        if self.gutils.get_cont_par("METRIC") == "1":
            self.si_units = True
        elif self.gutils.get_cont_par("METRIC") == "0":
            self.si_units = False
        else:
            pass
        if self.crs:
            pd = self.crs.description()
        else:
            pd = "----"
        self.proj_lab.setText(pd)
        if self.si_units == True:
            mu = "Metric (International System)"
        elif self.si_units == False:
            mu = "English (Imperial System)"
        else:
            mu = "Unknown System"
        self.unit_lab.setText(mu)

        contact = self.gutils.get_metadata_par("CONTACT")
        email = self.gutils.get_metadata_par("EMAIL")
        company = self.gutils.get_metadata_par("COMPANY")
        phone = self.gutils.get_metadata_par("PHONE")

        pn = self.gutils.get_metadata_par("PROJ_NAME")
        plugin_v = self.gutils.get_metadata_par("PLUGIN_V")
        qgis_v = self.gutils.get_metadata_par("QGIS_V")
        flo2d_v = self.gutils.get_metadata_par("FLO-2D_V")

        self.lineEdit_au.setText(contact)
        self.lineEdit_co.setText(company)
        self.lineEdit_em.setText(email)
        self.lineEdit_te.setText(phone)

        self.label_pn.setText(pn)
        self.label_pv.setText(plugin_v)
        self.label_qv.setText(qgis_v)
        self.label_fv.setText(flo2d_v)

    def setup(self):
        if not self.gutils:
            return
        self.gutils.path = self.gutils.get_gpkg_path()
        self.gpkgPathEdit.setText(self.gutils.path)
        self.gutils = GeoPackageUtils(self.con, self.iface)
        self.read()

    def create_db(self, gpkg_path=None, crs=None):
        """
        Create FLO-2D model database (GeoPackage).
        """
        s = QSettings()
        if not gpkg_path:
            last_gpkg_dir = s.value("FLO-2D/lastGpkgDir", "")
            gpkg_path, __ = QFileDialog.getSaveFileName(
                None, "Create GeoPackage As...", directory=last_gpkg_dir, filter="*.gpkg"
            )
        if not gpkg_path:
            return
        else:
            pass

        s.setValue("FLO-2D/lastGpkgDir", os.path.dirname(gpkg_path))
        start_time = time.time()
        con = database_create(gpkg_path)
        self.uc.log_info("{0:.3f} seconds => database create".format(time.time() - start_time))
        if not con:
            QApplication.restoreOverrideCursor()
            self.uc.show_warn("WARNING 060319.1653: Couldn't create new database {}".format(gpkg_path))
            self.uc.log_info("WARNING 060319.1653: Couldn't create new database {}".format(gpkg_path))
            return
        else:
            self.uc.log_info("Connected to {}".format(gpkg_path))
        # Inserting default values into the 'cont' table.
        self.set_default_controls(con)

        start_time = time.time()
        gutils = GeoPackageUtils(con, self.iface)
        if gutils.check_gpkg():
            self.uc.bar_info("GeoPackage {} is OK".format(gpkg_path))
            self.uc.log_info("GeoPackage {} is OK".format(gpkg_path))
            gutils.path = gpkg_path
            self.gpkgPathEdit.setText(gutils.path)
        else:
            self.uc.bar_error("{} is NOT a GeoPackage!".format(gpkg_path))
            self.uc.log_info("{} is NOT a GeoPackage!".format(gpkg_path))
        QApplication.restoreOverrideCursor()
        self.uc.log_info("{0:.3f} seconds => create gutils ".format(time.time() - start_time))
        # CRS
        start_time = time.time()
        if crs is None:
            self.projectionSelector.selectCrs()
            if self.projectionSelector.crs().isValid():
                self.crs = self.projectionSelector.crs()
            else:
                msg = "WARNING 060319.1655: Choose a valid CRS!"
                self.uc.show_warn(msg)
                self.uc.log_info(msg)
                return
        else:
            if crs.isValid():
                self.crs = crs
            else:
                msg = "The geopackage does not contain a valid CRS!"
                self.uc.show_warn(msg)
                self.uc.log_info(msg)
                return
        auth, crsid = self.crs.authid().split(":")
        self.proj_lab.setText(self.crs.description())

        si_units = [QgsUnitTypes.DistanceMeters,
                    QgsUnitTypes.DistanceKilometers,
                    QgsUnitTypes.DistanceCentimeters,
                    QgsUnitTypes.DistanceMillimeters
                    ]
        imperial_units = [QgsUnitTypes.DistanceFeet,
                    QgsUnitTypes.DistanceNauticalMiles,
                    QgsUnitTypes.DistanceYards,
                    QgsUnitTypes.DistanceMiles,
                    QgsUnitTypes.Inches
                    ]

        if self.crs.mapUnits() in si_units:
            self.si_units = True
            mu = "Metric (International System)"
        elif self.crs.mapUnits() in imperial_units:
            self.si_units = False
            mu = "English (Imperial System)"
        else:
            msg = "WARNING 060319.1654: Unknown map units. Choose a different projection!"
            self.uc.show_warn(msg)
            self.uc.log_info(msg)
            return
        self.unit_lab.setText(mu)
        proj = self.crs.toProj()

        # check if the CRS exist in the db
        sql = "SELECT * FROM gpkg_spatial_ref_sys WHERE srs_id=?;"
        rc = gutils.execute(sql, (crsid,))
        rt = rc.fetchone()
        if not rt:
            sql = """INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)"""
            data = (self.crs.description(), crsid, auth, crsid, proj, "")
            rc = gutils.execute(sql, data)
            del rc
            srsid = crsid
        else:
            q = "There is a coordinate system defined in the GeoPackage.\n"
            q += "Would you like to use it?\n\nDetails:\n"
            q += "Name: {}\n".format(rt[0])
            q += "SRS id: {}\n".format(rt[1])
            q += "Organization: {}\n".format(rt[2])
            q += "Organization id: {}\n".format(rt[3])
            q += "Definition: {}".format(rt[4])
            if self.uc.question(q):
                srsid = rt[1]
            else:
                return
        if self.con:
            database_disconnect(self.con)
        self.gpkg_path = gpkg_path
        self.con = con
        self.gutils = gutils
        if self.si_units:
            self.gutils.set_cont_par("METRIC", 1)
        else:
            self.gutils.set_cont_par("METRIC", 0)

        self.set_other_global_defaults(con)

        QApplication.setOverrideCursor(Qt.WaitCursor)
        # assign the CRS to all geometry columns
        sql = "UPDATE gpkg_geometry_columns SET srs_id = ?"
        self.gutils.execute(sql, (srsid,))
        sql = "UPDATE gpkg_contents SET srs_id = ?"
        self.gutils.execute(sql, (srsid,))
        self.uc.log_info("{0:.3f} seconds => spatial ref of tables".format(time.time() - start_time))
        self.srs_id = srsid

        start_time = time.time()
        self.lyrs.load_all_layers(self.gutils)
        self.lyrs.zoom_to_all()
        QApplication.restoreOverrideCursor()

        self.uc.log_info("{0:.3f} seconds => loading layers".format(time.time() - start_time))

        self.iface.actionPan().trigger()

        proj_name = os.path.splitext(os.path.basename(self.gpkg_path))[0]
        contact = QgsProject.instance().metadata().author()
        plugin_v = get_plugin_version()
        qgis_v = qgis.core.Qgis.QGIS_VERSION
        # Referencing the variable before. It will be updated if there is a FLOPRO.exe or FLOPRO_Demo.exe if FLO-2D is
        # installed correctly on the user's computer
        flo2d_v = "FLOPRO not found"

        flopro_dir = s.value("FLO-2D/last_flopro")
        if flopro_dir is not None:
            # Check for FLOPRO.exe
            if os.path.isfile(flopro_dir + "/FLOPRO.exe"):
                flo2d_v = get_flo2dpro_version(flopro_dir + "/FLOPRO.exe")
            # Check for FLOPRO_Demo.exe
            elif os.path.isfile(flopro_dir + "/FLOPRO_Demo.exe"):
                flo2d_v = get_flo2dpro_version(flopro_dir + "/FLOPRO_Demo.exe")
        else:
            dlg = ExternalProgramFLO2D(self.iface, "Run Settings")
            # dlg.debug_run_btn.setVisible(False)
            ok = dlg.exec_()
            if not ok:
                return
            flo2d_dir, project_dir, advanced_layers = dlg.get_parameters()
            s = QSettings()
            s.setValue("FLO-2D/lastGdsDir", project_dir)
            s.setValue("FLO-2D/last_flopro", flo2d_dir)

            if advanced_layers != s.value("FLO-2D/advanced_layers", ""):
                # show advanced layers
                if advanced_layers:
                    s.setValue("FLO-2D/advanced_layers", True)
                    lyrs = self.lyrs.data
                    for key, value in lyrs.items():
                        group = value.get("sgroup")
                        subsubgroup = value.get("ssgroup")
                        self.ilg.unhideLayer(self.lyrs.data[key]["qlyr"])
                        self.ilg.unhideGroup(group)
                        self.ilg.unhideGroup(subsubgroup, group)

                # hide advanced layers
                else:
                    s.setValue("FLO-2D/advanced_layers", False)
                    lyrs = self.lyrs.data
                    for key, value in lyrs.items():
                        advanced = value.get("advanced")
                        if advanced:
                            subgroup = value.get("sgroup")
                            subsubgroup = value.get("ssgroup")
                            self.ilg.hideLayer(self.lyrs.data[key]["qlyr"])
                            if subsubgroup == "Gutters" or subsubgroup == "Multiple Channels" or subsubgroup == "Streets":
                                self.ilg.hideGroup(subsubgroup, subgroup)
                            else:
                                self.ilg.hideGroup(subgroup)

            if project_dir != "" and flo2d_dir != "":
                s.setValue("FLO-2D/run_settings", True)
                if os.path.isfile(flo2d_dir + "/FLOPRO.exe"):
                    flo2d_v = get_flo2dpro_version(flo2d_dir + "/FLOPRO.exe")
                # Check for FLOPRO_Demo.exe
                elif os.path.isfile(flo2d_dir + "/FLOPRO_Demo.exe"):
                    flo2d_v = get_flo2dpro_version(flo2d_dir + "/FLOPRO_Demo.exe")

        self.lineEdit_au.setText(contact)
        self.lineEdit_co.setText("")
        self.lineEdit_em.setText("")

        self.label_pn.setText(proj_name)
        self.label_pv.setText(plugin_v)
        self.label_qv.setText(qgis_v)
        self.label_fv.setText(flo2d_v)

        self.groupBox.setEnabled(True)
        self.groupBox_2.setEnabled(True)

    def connect(self, gpkg_path=None):
        """
        Connect to FLO-2D model database (GeoPackage).
        """
        s = QSettings()
        last_gpkg_dir = s.value("FLO-2D/lastGpkgDir", "")
        if not gpkg_path:
            gpkg_path, __ = QFileDialog.getOpenFileName(
                None,
                "Select GeoPackage to connect",
                directory=last_gpkg_dir,
                filter="*.gpkg",
            )
        if not gpkg_path:
            return
        else:
            pass
        if self.con:
            database_disconnect(self.con)
        self.gpkg_path = gpkg_path
        s.setValue("FLO-2D/lastGpkgDir", os.path.dirname(self.gpkg_path))
        start_time = time.time()
        self.con = database_connect(self.gpkg_path)
        self.uc.log_info("Connected to {}".format(self.gpkg_path))
        self.uc.log_info("{0:.3f} seconds => connecting".format(time.time() - start_time))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.gutils = GeoPackageUtils(self.con, self.iface)
        # Check if file is GeoPackage.
        if self.gutils.check_gpkg():
            self.gutils.path = self.gpkg_path
            self.uc.bar_info("GeoPackage {} is OK".format(self.gutils.path))
            self.uc.log_info("GeoPackage {} is OK".format(self.gutils.path))
            sql = """SELECT srs_id FROM gpkg_contents WHERE table_name='grid';"""
            rc = self.gutils.execute(sql)
            rt = rc.fetchone()[0]
            self.srs_id = rt
            start_time = time.time()
            self.lyrs.load_all_layers(self.gutils)
            self.uc.log_info("{0:.3f} seconds => loading layers".format(time.time() - start_time))
            self.lyrs.zoom_to_all()
        else:
            self.uc.bar_error("{} is NOT a GeoPackage!".format(self.gutils.path))
            self.uc.log_info("{} is NOT a GeoPackage!".format(self.gutils.path))
        self.gpkgPathEdit.setText(self.gutils.path)
        self.read()
        QApplication.restoreOverrideCursor()

        return True

    def set_other_global_defaults(self, con):
        qry = """INSERT INTO mult (wmc, wdrall, dmall, nodchansall, xnmultall, sslopemin, sslopemax, avuld50, simple_n) VALUES (?,?,?,?,?,?,?,?,?);"""
        con.execute(
            qry,
            (
                "0",
                "3",
                "1",
                "1",
                "0.04",
                "1",
                "0",
                "0",
                "0.04",
            ),
        )

    def write(self):
        for name, wid in self.widget_map.items():
            value = None
            if isinstance(wid, QLineEdit):
                value = wid.text()
            elif isinstance(wid, QSpinBox):
                value = int(float(wid.value()))
            elif isinstance(wid, QDoubleSpinBox):
                value = str(wid.value())
            elif isinstance(wid, QCheckBox):
                value = 1 if wid.isChecked() else 0

            else:
                pass
            self.gutils.set_cont_par(name, value)
        self.gutils.set_cont_par("PROJ", self.crs.toProj())
        if self.crs.mapUnits() == QgsUnitTypes.DistanceMeters:
            metric = 1
        elif self.crs.mapUnits() == QgsUnitTypes.DistanceFeet:
            self.si_units = False
            metric = 0
        else:
            metric = 1
        self.gutils.set_cont_par("METRIC", metric)
        self.gutils.fill_empty_mult_globals()

    def select_all_modules(self):
        for cbx in self.modulesGrp.findChildren(QCheckBox):
            cbx.setChecked(True)

    def deselect_all_modules(self):
        for cbx in self.modulesGrp.findChildren(QCheckBox):
            cbx.setChecked(False)
