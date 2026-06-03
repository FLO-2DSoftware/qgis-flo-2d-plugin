# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import os
import time
import traceback
from datetime import datetime

from qgis.core import QgsFeature, QgsGeometry, QgsPointXY
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QApplication, QDialogButtonBox, QFileDialog, QMessageBox

from ..flo2d_tools.elevation_correctors import LeveesElevation
from ..flo2d_tools.grid_tools import cellIDNumpyArray, dirID
from ..geopackage_utils import GeoPackageUtils
from ..gui.dlg_walls_shapefile import WallsShapefile
from ..user_communication import UserCommunication
from .ui_utils import load_ui
from ..utils import qdialogbuttonbox_button, qt_window_flag, qt_cursor_shape

from ..flo2d_tools.schematic_tools import (
    delete_redundant_levee_directions_np,
    generate_schematic_levees,
)

uiDialog, qtBaseClass = load_ui("levees_elevation")


class LeveesToolDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self, iface.mainWindow())
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.setWindowFlags(
            qt_window_flag("Window") |
            qt_window_flag("WindowMinimizeButtonHint") |
            qt_window_flag("WindowCloseButtonHint") |
            qt_window_flag("WindowSystemMenuHint")
        )
        self.con = con
        self.lyrs = lyrs
        self.uc = UserCommunication(iface, "FLO-2D")
        self.gutils = GeoPackageUtils(con, iface)
        self.corrector = LeveesElevation(self.gutils, self.lyrs)
        self.corrector.setup_layers()
        self.methods = {}

        self.levees_tool_buttonBox.button(qdialogbuttonbox_button("Ok")).setText("Create Schematic Layers from User Levees")

        # connections
        self.elev_polygons_chbox.stateChanged.connect(self.polygons_checked)
        self.elev_points_chbox.stateChanged.connect(self.points_checked)
        self.elev_lines_chbox.stateChanged.connect(self.lines_checked)

        self.enable_sources()
        self.browse_btn.clicked.connect(self.get_xyz_file)
        self.xyz_line.textChanged.connect(self.activate_import)
        self.import_levee_lines_btn.clicked.connect(self.run_import_z)
        self.create_walls_btn.clicked.connect(self.create_walls)
        self.levees_tool_buttonBox.accepted.connect(self.check_sources)

    def enable_sources(self):
        # Check presence of layers:
        if self.gutils.is_table_empty("user_elevation_points"):
            self.elev_points_chbox.setChecked(False)
            self.elev_points_chbox.setEnabled(False)
        else:
            self.elev_points_chbox.setChecked(True)
            self.elev_points_chbox.setEnabled(True)

        if self.gutils.is_table_empty("user_levee_lines"):
            self.elev_lines_chbox.setChecked(False)
            self.elev_lines_chbox.setEnabled(False)
        else:
            self.elev_lines_chbox.setChecked(True)
            self.elev_lines_chbox.setEnabled(True)

        if self.gutils.is_table_empty("user_elevation_polygons"):
            self.elev_polygons_chbox.setChecked(False)
            self.elev_polygons_chbox.setEnabled(False)
        else:
            self.elev_polygons_chbox.setChecked(True)
            self.elev_polygons_chbox.setEnabled(True)

    def get_xyz_file(self):
        s = QSettings()
        last_dir = s.value("FLO-2D/lastXYZDir", "")
        xyz_file, __ = QFileDialog.getOpenFileName(
            None, "Select 3D levee lines file", directory=last_dir, filter="*.xyz"
        )
        if not xyz_file:
            return
        self.xyz_line.setText(xyz_file)
        s.setValue("FLO-2D/lastXYZDir", os.path.dirname(xyz_file))

    def activate_import(self):
        if self.xyz_line.text():
            self.import_levee_lines_btn.setEnabled(True)
        else:
            self.import_levee_lines_btn.setDisabled(True)

    def run_import_z(self):
        try:
            self.import_z_data()
            self.enable_sources()
            self.uc.bar_info("3D levee lines data imported!")
            self.uc.log_info("3D levee lines data imported!")
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.bar_error("Could not import 3D levee lines data!")
            self.uc.log_info("Could not import 3D levee lines data!")

    def create_walls(self):
        dlg_walls_shapefile = WallsShapefile(self.con, self.iface, self.lyrs)
        save = dlg_walls_shapefile.exec()
        QApplication.restoreOverrideCursor()

    def check_sources(self):
        if not self.methods:
            self.uc.show_warn("WARNING 060319.1612: Please choose at least one crest elevation source!")
            self.uc.log_info("WARNING 060319.1612: Please choose at least one crest elevation source!")
            return False

        try:
            start = datetime.now()
            QApplication.setOverrideCursor(qt_cursor_shape("WaitCursor"))
            n_elements_total = 1
            n_levee_directions_total = 0
            n_fail_features_total = 0

            starttime = time.time()
            levees = self.lyrs.data["levee_data"]["qlyr"]

            # This for loop creates the attributes in the levee_dat
            for (
                    n_elements,
                    n_levee_directions,
                    n_fail_features,
                    ranger,
            ) in self.schematize_levees():
                n_elements_total += n_elements
                n_levee_directions_total += n_levee_directions
                n_fail_features_total += n_fail_features

            # This for loop corrects the elevation
            for no in sorted(self.methods):
                self.methods[no]()

            inctime = time.time()
            self.uc.log_info("%s seconds to process levee features" % round(inctime - starttime, 2))

            # Delete duplicates:
            q = False
            if n_elements_total > 0:
                dletes = "Cell - Direction\n---------------\n"

                # delete duplicate elements with the same direction and elevation too
                qryIndex = "CREATE INDEX if not exists levee_dataFIDGRIDFIDLDIRLEVCEST  ON levee_data (fid, grid_fid, ldir, levcrest);"
                self.gutils.con.execute(qryIndex)
                self.gutils.con.commit()

                # levees_dup_qry = "SELECT min(fid), grid_fid, ldir, levcrest FROM levee_data GROUP BY grid_fid, ldir, levcrest HAVING COUNT(ldir) > 1 and count(levcrest) > 1 ORDER BY grid_fid"
                levees_dup_qry = "SELECT fid, grid_fid, ldir, max(levcrest) FROM levee_data GROUP BY grid_fid, ldir HAVING COUNT(grid_fid) = 2"

                leveeDups = self.gutils.execute(levees_dup_qry).fetchall()  # min FID, grid fid, ldir, min levcrest
                # grab the values
                self.uc.log_info(
                    "Found {valer} levee elements with duplicated grid, ldir, and elev; deleting the duplicates;".format(
                        valer=len(leveeDups)
                    )
                )

                delete_fids = []

                for item in leveeDups:
                    delete_fids.append(item[0])

                # delete any duplicates in directions that aren't the min elevation
                for fid in delete_fids:
                    self.gutils.execute(f"DELETE FROM levee_data WHERE fid = {fid};")
                # levees_dup_delete_qry =
                #     "DELETE FROM levee_data WHERE fid = ?;"
                # )
                # self.gutils.con.executemany(levees_dup_delete_qry, del_dup_data)
                # self.gutils.con.commit()

                qryIndexDrop = "DROP INDEX if exists levee_dataFIDGRIDFIDLDIRLEVCEST;"
                self.gutils.con.execute(qryIndexDrop)
                self.gutils.con.commit()

                leveesToDelete = delete_redundant_levee_directions_np(
                    self.gutils, cellIDNumpyArray
                )  # pass grid layer if it exists
                # leveesToDelete = delete_levee_directions_duplicates(self.gutils, levees, grid_lyr)
                if len(leveesToDelete) > 0:
                    k = 0
                    i = 0
                    for levee in leveesToDelete:
                        k += 1

                        i += 1

                        if i < 50:
                            if k <= 3:
                                dletes += (
                                        "{:<25}".format(
                                            "{:>10}-{:1}({:2})".format(
                                                str(levee[0]),
                                                str(levee[1]),
                                                dirID(levee[1]),
                                            )
                                        )
                                        + "\t"
                                )
                            elif k == 4:
                                dletes += "{:<25}".format(
                                    "{:>10}-{:1}({:2})".format(str(levee[0]), str(levee[1]), dirID(levee[1]))
                                )
                            elif k > 4:
                                dletes += (
                                        "\n"
                                        + "{:<25}".format(
                                    "{:>10}-{:1}({:2})".format(
                                        str(levee[0]),
                                        str(levee[1]),
                                        dirID(levee[1]),
                                    )
                                )
                                        + "\t"
                                )
                                k = 1

                        else:
                            if k <= 3:
                                dletes += (
                                        "{:<25}".format(
                                            "{:>10}-{:1}({:2})".format(
                                                str(levee[0]),
                                                str(levee[1]),
                                                dirID(levee[1]),
                                            )
                                        )
                                        + "\t"
                                )
                            elif k == 4:
                                dletes += "{:<25}".format(
                                    "{:>10}-{:1}({:2})".format(str(levee[0]), str(levee[1]), dirID(levee[1]))
                                )
                            elif k > 4:
                                dletes += (
                                        "\n"
                                        + "{:<25}".format(
                                    "{:>10}-{:1}({:2})".format(
                                        str(levee[0]),
                                        str(levee[1]),
                                        dirID(levee[1]),
                                    )
                                )
                                        + "\t"
                                )
                                k = 1

                    dletes += "\n\nWould you like to delete them?"

                    #                     dletes = Qt.convertFromPlainText(dletes)
                    QApplication.restoreOverrideCursor()

                    parent = self.iface.mainWindow() if self.iface and self.iface.mainWindow() else None
                    m = QMessageBox(parent)
                    title = "Duplicate Opposite Levee Directions".center(170)
                    m.setWindowTitle(title)
                    m.setText(
                        "There are "
                        + str(len(leveesToDelete))
                        + " redundant levees directions. "
                        + "They have lower crest elevation than the opposite direction.\n\n"
                        + "Would you like to delete them?"
                    )
                    m.setDetailedText(dletes)
                    m.setStandardButtons(self.uc.msgbox_button("No") | self.uc.msgbox_button("Yes"))
                    m.setDefaultButton(self.uc.msgbox_button("Yes"))

                    # Spacer                        width, height, h policy, v policy
                    # horizontalSpacer = QSpacerItem(0, 300, QSizePolicy.Preferred, QSizePolicy.Preferred)
                    #                     verticalSpacer = QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Expanding)
                    layout = m.layout()
                    # layout.addItem(horizontalSpacer)
                    #                     layout.addItem(verticalSpacer)

                    #                     m.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding);
                    #                     m.setSizePolicy(QSizePolicy.Maximum,QSizePolicy.Maximum);
                    #                     m.setFixedHeight(12000);
                    #                     m.setFixedWidth(12000);

                    #                     m.setFixedSize(2000, 1000);
                    #                     m.setBaseSize(QSize(2000, 1000))
                    #                     m.setMinimumSize(1000,1000)

                    #                     m.setInformativeText(dletes + '\n\nWould you like to delete them?')
                    q = m.exec()
                    if q == self.uc.msgbox_button("Yes"):
                        #                     q = self.uc.question('The following are ' + str(len(leveesToDelete)) + ' opposite levees directions duplicated (with lower crest elevation).\n' +
                        #                                             'Would you like to delete them?\n\n' + dletes + '\n\nWould you like to delete them?')
                        #                     if q:
                        delete_levees_qry = """DELETE FROM levee_data WHERE grid_fid = ? AND ldir = ?;"""
                        delete_failure_qry = """DELETE FROM levee_failure WHERE grid_fid = ? and lfaildir = ?;"""
                        self.uc.log_info("Deleting extra levee and levee failure features")

                        # build indexes to speed up the process
                        qryIndex = (
                            """CREATE INDEX if not exists leveeDataGridFID_LDIR  ON levee_data (grid_fid, ldir);"""
                        )
                        self.gutils.execute(qryIndex)
                        qryIndex = """CREATE INDEX if not exists leveeFailureGridFID_LFAILDIR  ON levee_failure (grid_fid, lfaildir);"""
                        self.gutils.execute(qryIndex)
                        self.gutils.con.commit()

                        # cur = self.gutils.con.cursor()
                        # cur.executemany(delete_levees_qry, list([(str(levee[0]), str(levee[1]),) for levee in leveesToDelete]))
                        # self.gutils.con.commit()
                        # cur.executemany(delete_failure_qry, list([(str(levee[0]), str(levee[1]),) for levee in leveesToDelete]))
                        # self.gutils.con.commit()
                        # cur.close()

                        for leveeCounter, levee in enumerate(leveesToDelete):
                            # self.gutils.execute(delete_levees_qry, (levee[0], levee[1]))
                            self.gutils.execute(
                                "DELETE FROM levee_data WHERE grid_fid = %i AND ldir = %i;" % (levee[0], levee[1])
                            )
                            if leveeCounter % 1000 == 0:
                                print(
                                    "DELETE FROM levee_data WHERE grid_fid = %i AND ldir = %i;" % (levee[0], levee[1])
                                )
                            self.gutils.con.commit()
                            # self.gutils.execute(delete_failure_qry, (levee[0], levee[1]))
                            self.gutils.execute(
                                "DELETE FROM levee_failure WHERE grid_fid = %i and lfaildir = %i;"
                                % (levee[0], levee[1])
                            )
                            if leveeCounter % 1000 == 0:
                                print(
                                    "DELETE FROM levee_failure WHERE grid_fid = %i and lfaildir = %i;"
                                    % (levee[0], levee[1])
                                )
                            self.gutils.con.commit()
                        self.uc.log_info("Done deleting extra levee and levee failure features")
                        qryIndex = """DROP INDEX if exists leveeDataGridFID_LDIR;"""
                        self.gutils.execute(qryIndex)
                        qryIndex = """DROP INDEX if exists leveeFailureGridFID_LFAILDIR;"""
                        self.gutils.execute(qryIndex)
                        self.gutils.con.commit()

                        levees.triggerRepaint()

                levee_schem = self.lyrs.get_layer_by_name("Levees", group=self.lyrs.group).layer()
                if levee_schem:
                    levee_schem.triggerRepaint()
            if q:
                n_levee_directions_total -= len(leveesToDelete)
                n_fail_features_total -= len(leveesToDelete)
                if n_fail_features_total < 0:
                    n_fail_features_total = 0

            #             end = datetime.now()
            #             time_taken = end - start
            #             self.uc.show_info("Time to schematize levee cells. " + str(time_taken))

            levees = self.lyrs.data["levee_data"]["qlyr"]
            idx = levees.fields().indexOf("grid_fid")
            values = levees.uniqueValues(idx)
            QApplication.restoreOverrideCursor()
            info = (
                    "Values assigned to the Schematic Levees layer!"
                    + "\n\nThere are now "
                    + str(len(values))
                    + " grid elements with levees,"
                    + "\nwith "
                    + str(n_levee_directions_total)
                    + " levee directions,"
                    + "\nof which, "
                    + str(n_fail_features_total)
                    + " have failure data."
            )
            if n_fail_features_total > n_levee_directions_total:
                info += "\n\n(WARNING 191219.1649: Please review the input User Levee Lines. There may be more than one line intersecting grid elements)"
            self.uc.show_info(info)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(traceback.format_exc())
            self.uc.show_error(
                "ERROR 060319.1806: Assigning values aborted! Please check your crest elevation source layers.\n",
                e,
            )

    def import_z_data(self):
        elev_points_lyr = self.lyrs.data["user_elevation_points"]["qlyr"]
        levee_line_lyr = self.lyrs.data["user_levee_lines"]["qlyr"]

        elev_fields = elev_points_lyr.fields()
        levee_fields = levee_line_lyr.fields()

        elev_points_lyr.startEditing()
        levee_line_lyr.startEditing()

        fpath = self.xyz_line.text()
        with open(fpath, "r") as xyz_file:
            polyline = []
            while True:
                try:
                    row = next(xyz_file)
                    values = row.split()
                    x, y, z = [float(i) for i in values]
                    point_feat = QgsFeature()
                    pnt = QgsPointXY(x, y)
                    point_geom = QgsGeometry().fromPointXY(pnt)
                    point_feat.setGeometry(point_geom)
                    point_feat.setFields(elev_fields)
                    point_feat.setAttribute("elev", z)
                    point_feat.setAttribute("membership", "levees")
                    elev_points_lyr.addFeature(point_feat)
                    polyline.append(pnt)
                except (ValueError, StopIteration) as e:
                    if not polyline:
                        break
                    line_feat = QgsFeature()
                    line_geom = QgsGeometry().fromPolylineXY(polyline)
                    line_feat.setGeometry(line_geom)
                    line_feat.setFields(levee_fields)
                    levee_line_lyr.addFeature(line_feat)
                    del polyline[:]
        elev_points_lyr.commitChanges()
        elev_points_lyr.updateExtents()
        elev_points_lyr.triggerRepaint()
        elev_points_lyr.removeSelection()

        levee_line_lyr.commitChanges()
        levee_line_lyr.updateExtents()
        levee_line_lyr.triggerRepaint()
        levee_line_lyr.removeSelection()

    def points_checked(self):
        if self.elev_points_chbox.isChecked():
            self.buffer_size.setEnabled(True)
            if self.buffer_size.value() == 0:
                val = float(self.gutils.get_cont_par("CELLSIZE"))
                self.buffer_size.setValue(val)
            else:
                pass
            self.methods[2] = self.elev_from_points
        else:
            self.buffer_size.setDisabled(True)
            self.methods.pop(2)

    def lines_checked(self):
        if self.elev_lines_chbox.isChecked():
            self.methods[1] = self.elev_from_lines
        else:
            self.methods.pop(1)

    def polygons_checked(self):
        if self.elev_polygons_chbox.isChecked():
            self.methods[3] = self.elev_from_polys
        else:
            self.methods.pop(3)

    def elev_from_points(self):
        try:
            self.corrector.set_filter()
            self.corrector.elevation_from_points(self.buffer_size.value())
        finally:
            self.corrector.clear_filter()

    def elev_from_lines(self):
        self.corrector.elevation_from_lines()

    def elev_from_polys(self):
        try:
            self.corrector.set_filter()
            self.corrector.elevation_from_polygons()
        finally:
            self.corrector.clear_filter()

    def schematize_levees(self):
        """
        Generate schematic lines for user defined levee lines.
        """
        try:
            levee_lyr = self.lyrs.get_layer_by_name("Levee Lines", group=self.lyrs.group).layer()
            grid_lyr = self.lyrs.get_layer_by_name("Grid", group=self.lyrs.group).layer()

            for (
                    n_elements,
                    n_levee_directions,
                    n_fail_features,
                    regionReq,
            ) in generate_schematic_levees(self.gutils, levee_lyr, grid_lyr):
                yield (n_elements, n_levee_directions, n_fail_features, regionReq)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 030120.0723: unable to process user levees!\n", e)