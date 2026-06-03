# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os

from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtWidgets import QApplication, QFileDialog

from ..flo2d_tools.flopro_tools import FLOPROExecutor
from ..misc.invisible_lyrs_grps import InvisibleLayersAndGroups
from ..user_communication import UserCommunication
from .ui_utils import load_ui
from ..utils import qt_window_flag, get_flo2dpro_version

uiDialog, qtBaseClass = load_ui("flopro")


class ExternalProgramFLO2D(qtBaseClass, uiDialog):
    def __init__(self, iface, title, gutils, f2d_widget, lyrs):
        qtBaseClass.__init__(self, iface.mainWindow())
        uiDialog.__init__(self)
        self.setupUi(self)
        self.setWindowFlags(qt_window_flag("Dialog") | qt_window_flag("Tool"))
        self.iface = iface
        self.gutils = gutils
        self.f2d_widget = f2d_widget
        self.lyrs = lyrs
        self.ilg = InvisibleLayersAndGroups(self.iface)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.flo2d_browse.clicked.connect(self.get_flo2d_dir)
        self.project_browse.clicked.connect(self.get_project_dir)
        self.debug_run_btn.clicked.connect(self.debug_run)
        self.set_previous_paths(title)
        self.buttonBox.accepted.connect(self.save_settings)

    def set_previous_paths(self, title):
        self.setWindowTitle(title)
        s = QSettings()
        flo2d_dir = s.value("FLO-2D/last_flopro", "")
        project_dir = last_dir = s.value("FLO-2D/lastGdsDir", "")
        advanced_layers = s.value("FLO-2D/advanced_layers", "")
        self.flo2d_le.setText(flo2d_dir)
        self.project_le.setText(project_dir)
        if advanced_layers == "false" or not advanced_layers:
            self.advanced_lyrs_chbox.setChecked(False)
        else:
            self.advanced_lyrs_chbox.setChecked(True)

    def get_flo2d_dir(self):
        s = QSettings()
        flo2d_dir = QFileDialog.getExistingDirectory(
            None, "Select FLO-2D program folder", directory=self.flo2d_le.text()
        )
        if not flo2d_dir:
            return
        self.flo2d_le.setText(flo2d_dir)
        s.setValue("FLO-2D/last_flopro", flo2d_dir)

    def get_project_dir(self):
        s = QSettings()
        project_dir = QFileDialog.getExistingDirectory(
            None, "Select FLO-2D project folder", directory=self.project_le.text()
        )
        if not project_dir:
            return
        self.project_le.setText(project_dir)
        s.setValue("FLO-2D/lastGdsDir", project_dir)

    def get_parameters(self):
        return self.flo2d_le.text(), self.project_le.text(), self.advanced_lyrs_chbox.isChecked()

    def debug_run(self):
        try:
            flo2d_dir = self.flo2d_le.text()
            if os.path.isfile(flo2d_dir + r"\FLOPRO.exe"):
                self.uc.show_info("Running FLOPRO.exe")
                program = "FLOPRO.exe"
            elif os.path.isfile(flo2d_dir + r"\FLOPRO_Demo.exe"):
                self.uc.show_info("Running FLOPRO_Demo.exe")
                program = "FLOPRO_Demo.exe"
            else:
                self.uc.show_warn("WARNING 221022.0911: Program FLOPRO.exe or FLOPRO_Demo.exe is not in directory\n\n" + flo2d_dir)
                self.uc.log_info(
                    "WARNING 221022.0911: Program FLOPRO.exe or FLOPRO_Demo.exe is not in directory\n\n" + flo2d_dir)
            project_dir = self.project_le.text()
            contDAT = os.path.join(project_dir, "CONT.DAT")
            if not os.path.exists(contDAT):
                self.uc.show_warn("CONT.DAT is not in project directory.\n\n" + project_dir)
                self.uc.log_info("CONT.DAT is not in project directory.\n\n" + project_dir)
                return
            debugDAT = os.path.join(project_dir, "QGISDEBUG.DAT")
            with open(debugDAT, "w") as f:
                f.write("")
            debug_simulation = FLOPROExecutor(self.iface, flo2d_dir, project_dir, program)
            return_code = debug_simulation.perform()
            self.uc.show_info(
                "FLO-2D PRO DEBUG simulation completed."
            )

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 250419.1729: can't run debug model!.\n", e)

        finally:
            self.close()

    def save_settings(self):
        """
        Function to save the settings in the flopro dialog
        """
        flopro_found = False

        # Project is loaded
        if self.gutils:
            flo2d_dir, project_dir, advanced_layers = self.get_parameters()
            s = QSettings()
            s.setValue("FLO-2D/lastGdsDir", project_dir)
            s.setValue("FLO-2D/last_flopro", flo2d_dir)
            self.f2d_widget.setup_project_folder()
            if advanced_layers != s.value("FLO-2D/advanced_layers", ""):
                # show advanced layers
                if advanced_layers:
                    lyrs = self.lyrs.data
                    for key, value in lyrs.items():
                        group = value.get("sgroup")
                        subsubgroup = value.get("ssgroup")
                        self.ilg.unhideLayer(self.lyrs.data[key]["qlyr"])
                        self.ilg.unhideGroup(group)
                        self.ilg.unhideGroup(subsubgroup, group)
                # hide advanced layers
                else:
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
            s.setValue("FLO-2D/advanced_layers", advanced_layers)

            if project_dir != "" and flo2d_dir != "":
                s.setValue("FLO-2D/run_settings", True)

                flopro_dir = s.value("FLO-2D/last_flopro")
                flo2d_v = "FLOPRO not found"
                # Check for FLOPRO.exe
                if os.path.isfile(flopro_dir + "/FLOPRO.exe"):
                    flopro_found = True
                    flo2d_v = get_flo2dpro_version(flopro_dir + "/FLOPRO.exe")
                # Check for FLOPRO_Demo.exe
                elif os.path.isfile(flopro_dir + "/FLOPRO_Demo.exe"):
                    flopro_found = True
                    flo2d_v = get_flo2dpro_version(flopro_dir + "/FLOPRO_Demo.exe")
                else:
                    flopro_found = False

                self.gutils.set_metadata_par("FLO-2D_V", flo2d_v)

        # Project not loaded
        else:
            flo2d_dir, project_dir, _ = self.get_parameters()
            s = QSettings()
            s.setValue("FLO-2D/lastGdsDir", project_dir)
            s.setValue("FLO-2D/last_flopro", flo2d_dir)

            if self.f2d_widget:
                self.f2d_widget.setup_project_folder()

            if project_dir != "" or flo2d_dir != "":
                s.setValue("FLO-2D/run_settings", True)

                flopro_dir = s.value("FLO-2D/last_flopro")
                # Check for FLOPRO.exe
                if os.path.isfile(flopro_dir + "/FLOPRO.exe"):
                    flopro_found = True
                # Check for FLOPRO_Demo.exe
                elif os.path.isfile(flopro_dir + "/FLOPRO_Demo.exe"):
                    flopro_found = True
                else:
                    flopro_found = False

        if flopro_found:
            self.uc.bar_info("Run Settings saved!")
            self.uc.log_info(f"Run Settings saved!\nProject Folder: {project_dir}\nFLO-2D Folder: {flo2d_dir}")
        else:
            self.uc.bar_warn("Run Settings saved! No FLOPRO.exe found, check your FLO-2D installation folder!")
            self.uc.log_info(f"Run Settings saved! No FLOPRO.exe found, check your FLO-2D installation "
                             f"folder!\nProject Folder: {project_dir}\nFLO-2D Folder: {flo2d_dir}")
