# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

# Lambda may not be necessary
# pylint: disable=W0108
import os
import sys
import time
import traceback

from qgis.PyQt.QtCore import QSettings, QCoreApplication, QTranslator, qVersion, Qt, QUrl, QSize
from qgis.PyQt.QtGui import QIcon, QDesktopServices
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QApplication, qApp, QMessageBox, QSpacerItem, QSizePolicy, QMenu
from qgis.core import QgsProject, QgsWkbTypes, NULL
from qgis.gui import QgsProjectionSelectionWidget, QgsDockWidget

from datetime import datetime

from .layers import Layers
from .user_communication import UserCommunication
from .geopackage_utils import connection_required, database_disconnect, GeoPackageUtils
from .flo2d_ie.flo2dgeopackage import Flo2dGeoPackage
from .flo2d_tools.grid_info_tool import GridInfoTool
from .flo2d_tools.info_tool import InfoTool
from .flo2d_tools.channel_profile_tool import ChannelProfile
from .flo2d_tools.grid_tools import grid_has_empty_elev
from .flo2d_tools.schematic_tools import generate_schematic_levees, delete_levee_directions_duplicates, delete_levee_directions_duplicates_np
from .flo2d_tools.flopro_tools import FLOPROExecutor, TailingsDamBreachExecutor, MapperExecutor, ProgramExecutor
from .gui.dlg_cont_toler_jj import ContToler_JJ
from .gui.dlg_hazus import HazusDialog
from .gui.dlg_issues import ErrorsDialog
from .gui.dlg_mud_and_sediment import MudAndSedimentDialog
from .gui.dlg_evap_editor import EvapEditorDialog
from .gui.dlg_levee_elev import LeveesToolDialog
from .gui.dlg_schem_xs_info import SchemXsecEditorDialog
from .gui.dlg_settings import SettingsDialog
from .gui.f2d_main_widget import FLO2DWidget
from .gui.grid_info_widget import GridInfoWidget
from .gui.plot_widget import PlotWidget
from .gui.table_editor_widget import TableEditorWidget
from .gui.dlg_schema2user import Schema2UserDialog
from .gui.dlg_user2schema import User2SchemaDialog
from .gui.dlg_ras_import import RasImportDialog
from .gui.dlg_flopro import ExternalProgramFLO2D
from .gui.dlg_components import ComponentsDialog
from .flo2d_tools.grid_tools import dirID, cellIDNumpyArray
from .flo2d_tools.grid_tools import dirID, assign_col_row_indexes_to_grid, number_of_elements, add_col_and_row_fields
from urllib3.contrib import _securetransport


class Flo2D(object):
    def __init__(self, iface):
        self.iface = iface
        self.iface.f2d = {}
        self.plugin_dir = os.path.dirname(__file__)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.crs_widget = QgsProjectionSelectionWidget()
        # initialize locale
        s = QSettings()
        locale = s.value("locale/userLocale")[0:2]
        locale_path = os.path.join(self.plugin_dir, "i18n", "Flo2D_{}.qm".format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > "4.3.3":
                QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.project = QgsProject.instance()
        self.actions = []

        self.files_used = ""
        self.files_not_used = ""

        self.menu = self.tr("&Flo2D")
        self.toolbar = self.iface.addToolBar("Flo2D")
        self.toolbar.setObjectName("Flo2D")
        self.con = None
        self.iface.f2d["con"] = self.con
        self.lyrs = Layers(iface)
        self.lyrs.group = None
        self.gutils = None
        self.f2g = None
        self.prep_sql = None
        self.f2d_widget = None
        self.f2d_plot_dock = None
        self.f2d_table_dock = None
        self.f2d_dock = None
        self.f2d_grid_info_dock = None
        self.create_map_tools()
        self.crs = None
        self.cur_info_table = None

        # connections
        self.project.readProject.connect(self.load_gpkg_from_proj)

        self.uc.clear_bar_messages()
        QApplication.restoreOverrideCursor()

    def tr(self, message):
        """
        Get the translation for a string using Qt translation API.
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate("Flo2D", message)

    def setup_dock_widgets(self):
        self.create_f2d_plot_dock()
        self.create_f2d_table_dock()
        self.create_f2d_dock()
        self.create_f2d_grid_info_dock()
        self.add_docks_to_iface()
        self.set_editors_map()

        self.info_tool.feature_picked.connect(self.get_feature_info)
        self.channel_profile_tool.feature_picked.connect(self.get_feature_profile)
        self.grid_info_tool.grid_elem_picked.connect(self.f2d_grid_info.update_fields)

        self.f2d_widget.grid_tools.setup_connection()
        self.f2d_widget.profile_tool.setup_connection()

        self.f2d_widget.bc_editor.setup_connection()
        self.f2d_widget.bc_editor.populate_bcs(widget_setup = True)

        self.f2d_widget.ic_editor.populate_cbos()

        self.f2d_widget.street_editor.setup_connection()
        self.f2d_widget.street_editor.populate_streets()

        self.f2d_widget.struct_editor.populate_structs()

        self.f2d_widget.rain_editor.setup_connection()
        self.f2d_widget.rain_editor.rain_properties()

        self.f2d_widget.channels_editor.setup_connection()
        #         self.f2d_widget.channels_editor.rain_properties()

        self.f2d_widget.xs_editor.setup_connection()
        self.f2d_widget.xs_editor.populate_xsec_cbo()

        self.f2d_widget.fpxsec_editor.setup_connection()

        self.f2d_widget.storm_drain_editor.setup_connection()

        self.f2d_widget.fpxsec_editor.populate_cbos()

        self.f2d_widget.infil_editor.setup_connection()

        self.f2d_widget.levee_and_breach_editor.setup_connection()

        self.f2d_widget.multiple_channels_editor.setup_connection()

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None,
        menu=None,
    ):

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)

        # INFO: action.triggered pass False to callback if it is decorated!
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        #         if menu is not None:
        #             popup = QMenu()
        #             for m in menu:
        #                 popup.addAction(m)
        #             action.setMenu(popup)

        if menu is not None:
            popup = QMenu()
            for m in menu:
                icon = QIcon(m[0])
                act = QAction(icon, m[1], parent)
                act.triggered.connect(m[2])
                popup.addAction(act)

            action.setMenu(popup)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        self.actions.append(action)
        return action

    def initGui(self):
        """
        Create the menu entries and toolbar icons inside the QGIS GUI.
        """
        self.add_action(
            os.path.join(self.plugin_dir, "img/settings.svg"),
            text=self.tr("Settings"),
            callback=self.show_settings,
            parent=self.iface.mainWindow(),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/run_flopro.png"),
            text=self.tr("Run Simulation"),
            callback=self.run_flopro,
            parent=self.iface.mainWindow(),
            menu=(
                (os.path.join(self.plugin_dir, "img/flo2d.svg"), "Run FLO-2D Pro", self.run_flopro),
                (os.path.join(self.plugin_dir, "img/profile_run2.svg"), "Run Profiles", self.run_profiles),
                (os.path.join(self.plugin_dir, "img/hydrog.svg"), "Run Hydrog", self.run_hydrog),
                (os.path.join(self.plugin_dir, "img/maxplot.svg"), "Run MaxPlot", self.run_maxplot),
                (os.path.join(self.plugin_dir, "img/mapper2.svg"), "Run Mapper", self.run_mapper2)
                #                     (os.path.join(self.plugin_dir, 'img/mapper_logo.svg'),'Run Mapper', self.run_program('Mapper PRO.Exe', 'Run Mapper', 'FLO-2D Folder (Mapper PRO.exe)'))
            ),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/gpkg2gpkg.svg"),
            text=self.tr("Import from GeoPackage"),
            callback=lambda: self.import_from_gpkg(),
            parent=self.iface.mainWindow(),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/import_gds.svg"),
            text=self.tr("Import GDS files"),
            callback=lambda: self.import_gds(),
            parent=self.iface.mainWindow(),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/import_components.svg"),
            text=self.tr("Import selected components files"),
            callback=lambda: self.import_selected_components(),
            parent=self.iface.mainWindow(),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/export_gds.svg"),
            text=self.tr("Export GDS files"),
            callback=lambda: self.export_gds(),
            parent=self.iface.mainWindow(),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/import_ras.svg"),
            text=self.tr("Import RAS geometry"),
            callback=lambda: self.import_from_ras(),
            parent=self.iface.mainWindow(),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/show_cont_table.svg"),
            text=self.tr("Set Control Parameters"),
            callback=lambda: self.show_cont_toler(),
            parent=self.iface.mainWindow(),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/schematic_to_user.svg"),
            text=self.tr("Convert Schematic Layers to User Layers"),
            callback=lambda: self.schematic2user(),
            parent=self.iface.mainWindow(),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/user_to_schematic.svg"),
            text=self.tr("Convert User Layers to Schematic Layers"),
            callback=lambda: self.user2schematic(),
            parent=self.iface.mainWindow(),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/profile_tool.svg"),
            text=self.tr("Channel Profile"),
            callback=self.channel_profile,  # Connects to 'init_channel_profile' method, via QAction triggered.connect(callback)
            parent=self.iface.mainWindow(),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/info_tool.svg"),
            text=self.tr("Info Tool"),
            callback=self.identify,
            parent=self.iface.mainWindow(),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/grid_info_tool.svg"),
            text=self.tr("Grid Info Tool"),
            callback=lambda: self.activate_grid_info_tool(),
            parent=self.iface.mainWindow(),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/evaporation_editor.svg"),
            text=self.tr("Evaporation Editor"),
            callback=lambda: self.show_evap_editor(),
            parent=self.iface.mainWindow(),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/set_levee_elev.svg"),
            text=self.tr("Levee Elevation Tool"),
            callback=lambda: self.show_levee_elev_tool(),
            parent=self.iface.mainWindow(),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/hazus.svg"),
            text=self.tr("HAZUS"),
            callback=lambda: self.show_hazus_dialog(),
            parent=self.iface.mainWindow(),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/tailings dam breach.svg"),
            text=self.tr("Tailings Dam Tool"),
            callback=self.run_tailingsdambreach,
            parent=self.iface.mainWindow(),
        )


        self.add_action(
            os.path.join(self.plugin_dir, "img/landslide.svg"),
            text=self.tr("Mud and Sediment Transport"),
            callback=lambda: self.show_mud_and_sediment_dialog(),
            parent=self.iface.mainWindow(),
        )
        
        self.add_action(
            os.path.join(self.plugin_dir, "img/issue.svg"),
            text=self.tr("Warnings and Errors"),
            callback=lambda: self.show_errors_dialog(),
            parent=self.iface.mainWindow(),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/help_contents.svg"),
            text=self.tr("FLO-2D Help"),
            callback=self.show_help,
            parent=self.iface.mainWindow(),
        )

        self.iface.mainWindow().setWindowTitle("No project selected")

    def create_f2d_dock(self):
        self.f2d_dock = QgsDockWidget()
        self.f2d_dock.setWindowTitle("FLO-2D")
        self.f2d_widget = FLO2DWidget(self.iface, self.lyrs, self.f2d_plot, self.f2d_table)
        self.f2d_widget.setSizeHint(350, 600)
        self.f2d_dock.setWidget(self.f2d_widget)
        self.f2d_dock.dockLocationChanged.connect(self.f2d_dock_save_area)

    @staticmethod
    def f2d_dock_save_area(area):
        s = QSettings("FLO2D")
        s.setValue("dock/area", area)

    def create_f2d_plot_dock(self):
        self.f2d_plot_dock = QgsDockWidget()  # The QDockWidget class provides a widget that can be docked inside
        # a QMainWindow or floated as a top-level window on the desktop.
        self.f2d_plot_dock.setWindowTitle("FLO-2D Plot")
        self.f2d_plot = PlotWidget()
        self.f2d_plot.plot.legend = None
        self.f2d_plot.setSizeHint(500, 200)
        self.f2d_plot_dock.setWidget(self.f2d_plot)  # Sets 'f2d_plot_dock' as wrapper its child 'f2d_plot'
        self.f2d_plot_dock.dockLocationChanged.connect(self.f2d_plot_dock_save_area)

    @staticmethod
    def f2d_table_dock_save_area(area):
        s = QSettings("FLO2D")
        s.setValue("table_dock/area", area)

    def create_f2d_table_dock(self):
        self.f2d_table_dock = QgsDockWidget()
        self.f2d_table_dock.setWindowTitle("FLO-2D Table Editor")
        self.f2d_table = TableEditorWidget(self.iface, self.f2d_plot, self.lyrs)
        self.f2d_table.setSizeHint(350, 200)
        self.f2d_table_dock.setWidget(self.f2d_table)
        self.f2d_table_dock.dockLocationChanged.connect(self.f2d_table_dock_save_area)

    @staticmethod
    def f2d_plot_dock_save_area(area):
        s = QSettings("FLO2D")
        s.setValue("plot_dock/area", area)

    def create_f2d_grid_info_dock(self):
        self.f2d_grid_info_dock = QgsDockWidget()
        self.f2d_grid_info_dock.setWindowTitle("FLO-2D Grid Info")
        self.f2d_grid_info = GridInfoWidget(self.iface, self.f2d_plot, self.f2d_table, self.lyrs)
        self.f2d_grid_info.setSizeHint(350, 30)
        grid = self.lyrs.data["grid"]["qlyr"]
        if grid is not None:
            self.f2d_grid_info.set_info_layer(grid)
        self.f2d_grid_info_dock.setWidget(self.f2d_grid_info)
        self.f2d_grid_info_dock.dockLocationChanged.connect(self.f2d_grid_info_dock_save_area)

    @staticmethod
    def f2d_grid_info_dock_save_area(area):
        s = QSettings("FLO2D")
        s.setValue("grid_info_dock/area", area)

    def add_docks_to_iface(self):
        s = QSettings("FLO2D")
        ma = s.value("dock/area", Qt.RightDockWidgetArea, type=int)
        ta = s.value("table_dock/area", Qt.BottomDockWidgetArea, type=int)
        pa = s.value("plot_dock/area", Qt.BottomDockWidgetArea, type=int)
        ga = s.value("grid_info_dock/area", Qt.TopDockWidgetArea, type=int)

        self.iface.addDockWidget(ma, self.f2d_dock)
        self.iface.addDockWidget(ta, self.f2d_table_dock)
        self.iface.addDockWidget(pa, self.f2d_plot_dock)
        self.iface.addDockWidget(ga, self.f2d_grid_info_dock)

    def unload(self):
        """
        Removes the plugin menu item and icon from QGIS GUI.
        """
        self.lyrs.clear_rubber()
        # remove maptools
        del self.info_tool, self.grid_info_tool, self.channel_profile_tool
        # others
        del self.uc
        database_disconnect(self.con)
        for action in self.actions:
            self.iface.removePluginMenu(self.tr("&Flo2D"), action)
            self.iface.removeToolBarIcon(action)
        # remove dialogs
        if self.f2d_table_dock is not None:
            self.f2d_table_dock.close()
            self.iface.removeDockWidget(self.f2d_table_dock)
            del self.f2d_table_dock
        if self.f2d_plot_dock is not None:
            self.f2d_plot_dock.close()
            self.iface.removeDockWidget(self.f2d_plot_dock)
            del self.f2d_plot_dock
        if self.f2d_grid_info_dock is not None:
            self.f2d_grid_info_dock.close()
            self.iface.removeDockWidget(self.f2d_grid_info_dock)
            del self.f2d_grid_info_dock
        if self.f2d_widget is not None:
            if self.f2d_widget.bc_editor is not None:
                self.f2d_widget.bc_editor.close()
                del self.f2d_widget.bc_editor

            if self.f2d_widget.profile_tool is not None:
                self.f2d_widget.profile_tool.close()
                del self.f2d_widget.profile_tool

            if self.f2d_widget.ic_editor is not None:
                self.f2d_widget.ic_editor.close()
                del self.f2d_widget.ic_editor

            if self.f2d_widget.rain_editor is not None:
                self.f2d_widget.rain_editor.close()
                del self.f2d_widget.rain_editor

            if self.f2d_widget.channels_editor is not None:
                self.f2d_widget.channels_editor.close()
                del self.f2d_widget.channels_editor

            if self.f2d_widget.fpxsec_editor is not None:
                self.f2d_widget.fpxsec_editor.close()
                del self.f2d_widget.fpxsec_editor

            if self.f2d_widget.struct_editor is not None:
                self.f2d_widget.struct_editor.close()
                del self.f2d_widget.struct_editor

            if self.f2d_widget.street_editor is not None:
                self.f2d_widget.street_editor.close()
                del self.f2d_widget.street_editor

            if self.f2d_widget.xs_editor is not None:
                self.f2d_widget.xs_editor.close()
                del self.f2d_widget.xs_editor

            if self.f2d_widget.infil_editor is not None:
                self.f2d_widget.infil_editor.close()
                del self.f2d_widget.infil_editor

            if self.f2d_widget.storm_drain_editor is not None:
                self.f2d_widget.storm_drain_editor.close()
                del self.f2d_widget.storm_drain_editor

            if self.f2d_widget.grid_tools is not None:
                self.f2d_widget.grid_tools.close()
                del self.f2d_widget.grid_tools

            self.f2d_widget.save_collapsible_groups()
            self.f2d_widget.close()
            del self.f2d_widget

        if self.f2d_dock is not None:
            self.f2d_dock.close()
            self.iface.removeDockWidget(self.f2d_dock)
            del self.f2d_dock
        # remove the toolbar
        del self.toolbar
        del self.gutils, self.lyrs
        try:
            del self.iface.f2d["con"]
        except KeyError as e:
            pass
        del self.con

    @staticmethod
    def save_dock_geom(dock):
        s = QSettings("FLO2D", dock.windowTitle())
        s.setValue("geometry", dock.saveGeometry())

    @staticmethod
    def restore_dock_geom(dock):
        s = QSettings("FLO2D", dock.windowTitle())
        g = s.value("geometry")
        if g:
            dock.restoreGeometry(g)

    def write_proj_entry(self, key, val):
        return self.project.writeEntry("FLO-2D", key, val)

    def read_proj_entry(self, key):
        r = self.project.readEntry("FLO-2D", key)
        if r[0] and r[1]:
            return r[0]
        else:
            return None

    def show_settings(self):
        dlg_settings = SettingsDialog(self.con, self.iface, self.lyrs, self.gutils)
        dlg_settings.show()
        result = dlg_settings.exec_()
        if result and dlg_settings.con:
            dlg_settings.write()
            self.con = dlg_settings.con
            self.iface.f2d["con"] = self.con
            self.gutils = dlg_settings.gutils
            self.crs = dlg_settings.crs  # Coordinate Reference System.
            gpkg_path = self.gutils.get_gpkg_path().replace("\\", "/")
            self.write_proj_entry("gpkg", gpkg_path)
            self.setup_dock_widgets()
            s = QSettings()
            s.setValue("FLO-2D/last_flopro_project", os.path.dirname(gpkg_path))
            s.setValue("FLO-2D/lastGdsDir", os.path.dirname(gpkg_path))

    def run_flopro(self):
        dlg = ExternalProgramFLO2D(self.iface, "Run FLO-2D model")
        dlg.exec_folder_lbl.setText("FLO-2D Folder (of FLO-2D model executable)")
        ok = dlg.exec_()
        if not ok:
            return
        flo2d_dir, project_dir = dlg.get_parameters()
        if sys.platform != "win32":
            self.uc.bar_warn("Could not run simulation under current operation system!")
            return
        try: 
            return_code = -9999
            if os.path.isfile(flo2d_dir + r"\FLOPRO.exe"):
                debugDAT = os.path.join(project_dir, "QGISDEBUG.DAT")
                if os.path.exists(debugDAT):
                    os.remove(debugDAT)
                simulation = FLOPROExecutor(self.iface, flo2d_dir, project_dir)
                return_code = simulation.run()
                if return_code != 0:
                    self.uc.show_warn(
                        "ERROR 190821.1120: FLO2D.EXE Model run failed!\n\n"
                        + "Program finished with return code " + str(return_code)
                    )
                else:
                    self.uc.show_info( "Model finished with return code "  + str(return_code))       
                
                            
            else:
                self.uc.show_warn("WARNING 180821.0841: Program FLO2D.exe is not in directory\n\n" + flo2d_dir)                
        except Exception as e:
            self.uc.log_info(repr(e))
            self.uc.bar_warn("Running simulation failed!")

    def run_tailingsdambreach(self):
        dlg = ExternalProgramFLO2D(self.iface, "Run Tailings Dam Breach model")
        dlg.debug_run_btn.setVisible(False)
        dlg.exec_folder_lbl.setText("FLO-2D Folder (Tailings Dam Breach.exe)")
        ok = dlg.exec_()
        if not ok:
            return
        flo2d_dir, project_dir = dlg.get_parameters()

        if sys.platform != "win32":
            self.uc.bar_warn("Could not run Tailings Dam Breach program under current operation system!")
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if os.path.isfile(flo2d_dir + r"\Tailings Dam Breach.exe"):
                tailings = TailingsDamBreachExecutor(flo2d_dir, project_dir)
                return_code = tailings.run()
                if return_code != 0:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_warn(
                        "ERROR 240719.1601: Tailings Dam Breach failed!\n\n"
                        + "Program finished with return code "
                        + str(return_code)
                    )
                else:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_info(
                        "Tailings Dam Tool has been closed.\n\n"
                        + "If a new INFLOW.DAT was created, import the data file into FLO-2D QGIS."
                    )
            else:
                QApplication.restoreOverrideCursor()
                self.uc.show_warn(
                    "WARNING 240719.1607: Program Tailings Dam Breach.exe is not in directory\n\n" + flo2d_dir
                )
        except Exception as e:
            QApplication.restoreOverrideCursor()

            self.uc.show_error(
                "ERROR 201019.0917: 'Tailings Dam Breach.exe failed!"
                + "\n__________________________________________________",
                e,
            )

    def run_mapper(self):
        dlg = ExternalProgramFLO2D(self.iface, "Run Mapper")
        dlg.debug_run_btn.setVisible(False)
        dlg.exec_folder_lbl.setText("FLO-2D Folder (Mapper PRO.exe)")
        ok = dlg.exec_()
        if not ok:
            return
        flo2d_dir, project_dir = dlg.get_parameters()

        if sys.platform != "win32":
            self.uc.bar_warn("Could not run Mapper program under current operation system!")
            return
        try:
            if os.path.isfile(flo2d_dir + r"\Mapper PRO.exe"):
                mapper = MapperExecutor(flo2d_dir, project_dir)
                mapper.run()
                self.uc.bar_info("Mapper started!", dur=3)
            else:
                self.uc.show_warn("WARNING 241020.0424: Program Mapper PRO.exe is not in directory\n\n" + flo2d_dir)
        except Exception as e:
            self.uc.log_info(repr(e))
            self.uc.bar_warn("Running Mapper failed!")

    def run_mapper2(self):
        self.run_program("Mapper PRO.exe")

    def run_profiles(self):
        self.run_program("PROFILES.exe")

    def run_hydrog(self):
        self.run_program("HYDROG.exe")

    def run_maxplot(self):
        self.run_program("MAXPLOT.exe")

    def run_program(self, exe_name):
        dlg = ExternalProgramFLO2D(self.iface, exe_name)
        dlg.debug_run_btn.setVisible(False)
        dlg.exec_folder_lbl.setText("FLO-2D Folder (" + exe_name + ")")
        ok = dlg.exec_()
        if not ok:
            return
        flo2d_dir, project_dir = dlg.get_parameters()

        if sys.platform != "win32":
            self.uc.bar_warn("Could not run " + exe_name + " under current operation system!")
            return
        try:
            if os.path.isfile(flo2d_dir + "\\" + exe_name):
                program = ProgramExecutor(flo2d_dir, project_dir, exe_name)
                program.run()
                self.uc.bar_info(exe_name + " started!", dur=3)
            else:
                self.uc.show_warn("WARNING 241020.0424: Program " + exe_name + " is not in directory\n\n" + flo2d_dir)
        except Exception as e:
            self.uc.log_info(repr(e))
            self.uc.bar_warn("Running " + exe_name + " failed!")

    def load_gpkg_from_proj(self):
        """
        If QGIS project has a gpkg path saved ask user if it should be loaded.
        """
        old_gpkg = self.read_proj_entry("gpkg")
        qgs_file = QgsProject.instance().fileName()
        qgs_dir = os.path.dirname(qgs_file)
        if old_gpkg:
            QApplication.restoreOverrideCursor()
            msg = f"This QGIS project uses the FLO-2D Plugin and the following database file:\n\n{old_gpkg}\n\n"
            if not os.path.exists(old_gpkg):
                msg += "Unfortunately it seems that database file doesn't exist at given location."
                gpkg_dir, gpkg_file = os.path.split(old_gpkg)
                _old_gpkg = os.path.join(qgs_dir, gpkg_file)
                if os.path.exists(_old_gpkg):
                    msg += f" However there is a file with the same name at your project location:\n\n{_old_gpkg}\n\n"
                    msg += "Load the model?"
                    old_gpkg = _old_gpkg
                    answer = self.uc.customized_question("FLO-2D", msg)
                else:
                    answer = self.uc.customized_question("FLO-2D", msg, QMessageBox.Cancel, QMessageBox.Cancel)
            else:
                msg += "Load the model?"
                answer = self.uc.customized_question("FLO-2D", msg)
            if answer == QMessageBox.Yes:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                qApp.processEvents()
                dlg_settings = SettingsDialog(self.con, self.iface, self.lyrs, self.gutils)
                dlg_settings.connect(old_gpkg)
                self.con = dlg_settings.con
                self.iface.f2d["con"] = self.con
                self.gutils = dlg_settings.gutils
                self.crs = dlg_settings.crs
                self.setup_dock_widgets()

                s = QSettings()
                s.setValue("FLO-2D/last_flopro_project", qgs_file)
                s.setValue("FLO-2D/lastGdsDir", qgs_dir)
                window_title = s.value("FLO-2D/last_flopro_project", "")
                self.iface.mainWindow().setWindowTitle(window_title)
                QApplication.restoreOverrideCursor()

    def call_IO_methods(self, calls, debug, *args):
        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")
        self.files_used = "CONT.DAT\n"
        self.files_not_used = ""
        n_found = 0
        n_not_found = 0

        for call in calls:
            dat = call.split("_")[-1].upper() + ".DAT"
            if call.startswith("import"):
                if self.f2g.parser.dat_files[dat] is None:
                    self.uc.log_info('Files required for "{0}" not found. Action skipped!'.format(call))
                    self.files_not_used += dat + "\n"
                    continue
                else:
                    if os.path.getsize(os.path.join(last_dir, dat)) > 0:
                        self.files_used += dat + "\n"
                        if dat == "CHAN.DAT":
                            self.files_used += "CHANBANK.DAT" + "\n"
                        pass
                    else:
                        self.files_not_used += dat + "\n"
                        continue

            try:
                start_time = time.time()
                method = getattr(self.f2g, call)
                if method(*args):
                    if call.startswith("export"):
                        self.files_used += dat + "\n"
                        if dat == "CHAN.DAT":
                            self.files_used += "CHANBANK.DAT" + "\n"
                        if dat == "TOPO.DAT":
                            self.files_used += "MANNINGS_N.DAT" + "\n"
                        pass

                self.uc.log_info('{0:.3f} seconds => "{1}"'.format(time.time() - start_time, call))

            except Exception as e:
                if debug is True:
                    self.uc.log_info(traceback.format_exc())
                else:
                    raise

    @connection_required
    def import_gds(self):
        """
        Import traditional GDS files into FLO-2D database (GeoPackage).
        """
        self.gutils.disable_geom_triggers()
        self.f2g = Flo2dGeoPackage(self.con, self.iface)
        import_calls = [
            "import_cont_toler",
            "import_mannings_n_topo",
            "import_inflow",
            "import_outflow",
            "import_rain",
            "import_raincell",
            "import_evapor",
            "import_infil",
            "import_chan",
            "import_xsec",
            "import_hystruc",
            "import_street",
            "import_arf",
            "import_mult",
            "import_sed",
            "import_levee",
            "import_fpxsec",
            "import_breach",
            "import_gutter",
            "import_fpfroude",
            "import_swmmflo",
            "import_swmmflort",
            "import_swmmoutf",
            "import_tolspatial",
            "import_wsurf",
            "import_wstime",
        ]
        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")
        fname, __ = QFileDialog.getOpenFileName(
            None, "Select FLO-2D file to import", directory=last_dir, filter="CONT.DAT"
        )
        if not fname:
            return
        dir_name = os.path.dirname(fname)
        s.setValue("FLO-2D/lastGdsDir", dir_name)
        bname = os.path.basename(fname)
        if self.f2g.set_parser(fname):
            topo = self.f2g.parser.dat_files["TOPO.DAT"]
            if topo is None:
                self.uc.bar_warn("Could not find TOPO.DAT file! Importing GDS files aborted!", dur=3)
                return
            if bname not in self.f2g.parser.dat_files:
                return
            empty = self.f2g.is_table_empty("grid")
            # check if a grid exists in the grid table
            if not empty:
                q = "There is a grid already defined in GeoPackage. Overwrite it?"
                if self.uc.question(q):
                    pass
                else:
                    self.uc.bar_info("Import cancelled", dur=3)
                    return

            # Check if MANNINGS_N.DAT exist:
            if not os.path.isfile(dir_name + r"\MANNINGS_N.DAT") or os.path.getsize(dir_name + r"\MANNINGS_N.DAT") == 0:
                self.uc.show_info("ERROR 241019.1821: file MANNINGS_N.DAT is missing or empty!")
                return

            dlg_components = ComponentsDialog(self.con, self.iface, self.lyrs, "in")
            ok = dlg_components.exec_()
            if ok:
                try:
                    QApplication.setOverrideCursor(Qt.WaitCursor)

                    if "Channels" not in dlg_components.components:
                        import_calls.remove("import_chan")
                        import_calls.remove("import_xsec")

                    if "Reduction Factors" not in dlg_components.components:
                        import_calls.remove("import_arf")

                    if "Streets" not in dlg_components.components:
                        import_calls.remove("import_street")

                    if "Outflow Elements" not in dlg_components.components:
                        import_calls.remove("import_outflow")

                    if "Inflow Elements" not in dlg_components.components:
                        import_calls.remove("import_inflow")

                    if "Levees" not in dlg_components.components:
                        import_calls.remove("import_levee")

                    if "Multiple Channels" not in dlg_components.components:
                        import_calls.remove("import_mult")

                    if "Breach" not in dlg_components.components:
                        import_calls.remove("import_breach")

                    if "Gutters" not in dlg_components.components:
                        import_calls.remove("import_gutter")

                    if "Infiltration" not in dlg_components.components:
                        import_calls.remove("import_infil")

                    if "Floodplain Cross Sections" not in dlg_components.components:
                        import_calls.remove("import_fpxsec")

                    if "Mudflow and Sediment Transport" not in dlg_components.components:
                        import_calls.remove("import_sed")

                    if "Evaporation" not in dlg_components.components:
                        import_calls.remove("import_evapor")

                    if "Hydraulic  Structures" not in dlg_components.components:
                        import_calls.remove("import_hystruc")

                    # if 'MODFLO-2D' not in dlg_components.components:
                    #     import_calls.remove('')

                    if "Rain" not in dlg_components.components:
                        import_calls.remove("import_rain")
                        import_calls.remove("import_raincell")

                    if "Storm Drain" not in dlg_components.components:
                        import_calls.remove("import_swmmflo")
                        import_calls.remove("import_swmmflort")
                        import_calls.remove("import_swmmoutf")

                    if "Spatial Tolerance" not in dlg_components.components:
                        import_calls.remove("import_tolspatial")

                    if "Spatial Froude" not in dlg_components.components:
                        import_calls.remove("import_fpfroude")

                    tables = [
                        "all_schem_bc",
                        "blocked_cells",
                        "breach",
                        "breach_cells",
                        "breach_fragility_curves",
                        "breach_global",
                        "buildings_areas",
                        "buildings_stats",
                        "chan",
                        "chan_confluences",
                        "chan_elems",
                        "chan_elems_interp",
                        "chan_n",
                        "chan_r",
                        "chan_t",
                        "chan_v",
                        "chan_wsel",
                        "chan_elems",
                        "cont",
                        "culvert_equations",
                        "evapor",
                        "evapor_hourly",
                        "evapor_monthly",
                        "fpfroude",
                        "fpfroude_cells",
                        "fpxsec",
                        "fpxsec_cells",
                        "grid",
                        "gutter_areas",
                        "gutter_cells",
                        "gutter_globals",
                        "infil",
                        "infil_areas_chan",
                        "infil_areas_green",
                        "infil_areas_horton",
                        "infil_areas_scs",
                        "infil_cells_green",
                        "infil_cells_horton",
                        "infil_cells_scs",
                        "infil_chan_elems",
                        "infil_chan_seg",
                        "inflow",
                        "inflow_cells",
                        "inflow_time_series",
                        "inflow_time_series_data",
                        "levee_data",
                        "levee_failure",
                        "levee_fragility",
                        "levee_general",
                        "mud_areas",
                        "mud_cells",
                        "mult",
                        "mult_areas",
                        "mult_cells",
                        "noexchange_chan_cells",
                        "outflow",
                        "outflow_cells",
                        "outflow_time_series",
                        "outflow_time_series_data",
                        "qh_params",
                        "qh_params_data",
                        "qh_table",
                        "qh_table_data",
                        "rain",
                        "rain_arf_areas",
                        "rain_arf_cells",
                        "rain_time_series",
                        "rain_time_series_data",
                        "raincell",
                        "raincell_data",
                        "rat_curves",
                        "rat_table",
                        "rbank",
                        "reservoirs",
                        "repl_rat_curves",
                        "reservoirs",
                        "sed_group_areas",
                        "sed_group_cells",
                        "sed_groups",
                        "sed_rigid_areas",
                        "sed_rigid_cells",
                        "sed_supply_areas",
                        "sed_supply_cells",
                        "spatialshallow",
                        "spatialshallow_cells",
                        "storm_drains",
                        "street_elems",
                        "street_general",
                        "street_seg",
                        "streets",
                        "struct",
                        "swmmflo",
                        "swmmflort",
                        "swmmflort_data",
                        "swmmoutf",
                        "tolspatial",
                        "tolspatial_cells",
                        "user_bc_lines",
                        "user_bc_points",
                        "user_bc_polygons",
                        "user_blocked_areas",
                        "user_chan_n",
                        "user_chan_r",
                        "user_chan_t",
                        "user_chan_v",
                        "user_elevation_points",
                        "user_elevation_polygons",
                        "user_fpxsec",
                        "user_infiltration",
                        "user_left_bank",
                        "user_levee_lines",
                        "user_model_boundary",
                        "user_noexchange_chan_areas",
                        "user_reservoirs",
                        "user_right_bank",
                        "user_roughness",
                        "user_streets",
                        "user_struct",
                        "user_swmm_conduits",
                        "user_swmm_nodes",
                        "user_xsec_n_data",
                        "user_xsections",
                        "wstime",
                        "wsurf",
                        "xsec_n_data",
                    ]

                    for table in tables:
                        self.gutils.clear_tables(table)

                    self.call_IO_methods(import_calls, True)  # The strings list 'export_calls', contains the names of
                    # the methods in the class Flo2dGeoPackage to import (read) the
                    # FLO-2D .DAT files

                    # save CRS to table cont
                    self.gutils.set_cont_par("PROJ", self.crs.toProj4())

                    # load layers and tables
                    self.load_layers()
                    self.uc.bar_info("Flo2D model imported", dur=3)
                    self.gutils.enable_geom_triggers()

                    if "import_chan" in import_calls:
                        self.gutils.create_schematized_rbank_lines_from_xs_tips()

                    self.setup_dock_widgets()
                    self.lyrs.refresh_layers()
                    self.lyrs.zoom_to_all()
                    # See if geopackage has grid with 'col' and 'row' fields:
                    grid_lyr = self.lyrs.data["grid"]["qlyr"]
                    field_index = grid_lyr.fields().indexFromName("col")
                    if field_index == -1:
                        QApplication.restoreOverrideCursor()

                        add_new_colums = self.uc.customized_question("FLO-2D", "WARNING 290521.0500:    Old GeoPackage.\n\nGrid table doesn't have 'col' and 'row' fields!\n\n"
                                                   + "Would you like to add the 'col' and 'row' fields to the grid table?",
                                                   QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)

                        if add_new_colums == QMessageBox.Cancel:
                            return

                        if add_new_colums == QMessageBox.No:
                            return
                        else:
                            if add_col_and_row_fields(grid_lyr):
                                assign_col_row_indexes_to_grid(grid_lyr, self.gutils)
                    else:
                        cell = self.gutils.execute("SELECT col FROM grid WHERE fid = 1").fetchone()
                        if cell[0] == NULL:
                            QApplication.restoreOverrideCursor()
                            proceed = self.uc.question("Grid layer's fields 'col' and 'row' have NULL values!\n\nWould you like to assign them?")
                            if proceed:
                                QApplication.setOverrideCursor(Qt.WaitCursor)
                                assign_col_row_indexes_to_grid(self.lyrs.data["grid"]["qlyr"], self.gutils)
                                QApplication.restoreOverrideCursor()
                            else:
                                return

                    QApplication.restoreOverrideCursor()

                    # # See if geopackage has grid with 'col' and 'row' fields:
                    # grid_lyr = self.lyrs.data["grid"]["qlyr"]
                    # field_index = grid_lyr.fields().indexFromName("col")
                    # if field_index == -1:
                        # if self.gutils.is_table_empty("user_model_boundary"):
                            # QApplication.restoreOverrideCursor()
                            # self.uc.bar_warn("WARNING 310521.0445: Old GeoPackage.\n\nGrid table doesn't have 'col' and 'row' fields!", 10)
                        # else:
                            # QApplication.restoreOverrideCursor()
                            # proceed = self.uc.question("WARNING 290521.0500: Old GeoPackage.\n\nGrid table doesn't have 'col' and 'row' fields!\n\n" +
                                                       # "Would you like to create it?")
                            # QApplication.setOverrideCursor(Qt.WaitCursor)
                            # if proceed:
                                # if square_grid_with_col_and_row_fields(self.gutils, self.lyrs.data["user_model_boundary"]["qlyr"]):
                                    # assign_col_row_indexes_to_grid(self.lyrs.data['grid']['qlyr'], self.gutils)

                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 050521.0349: importing .DAT files!.\n", e)
                finally:
                    QApplication.restoreOverrideCursor()
                    if self.files_used != "" or self.files_not_used != "":
                        self.uc.show_info(
                            "Files read by this project:\n\n"
                            + self.files_used
                            + "\n\nFiles not found or empty:\n\n"
                            + self.files_not_used
                        )

                    msg = ""
                    if "import_swmmflo" in import_calls:
                            msg += "* To complete the Storm Drain functionality, the 'Computational Domain' and 'Storm Drains' conversion "
                            msg += "must be done using the "
                            msg += "<FONT COLOR=green>Conversion from Schematic Layers to User Layers</FONT>"
                            msg += " tool in the <FONT COLOR=blue>FLO-2D panel</FONT>...<br>"
                            msg += "...and <FONT COLOR=green>Import SWMM.INP</FONT> from the <FONT COLOR=blue>Storm Drain Editor widget</FONT>."

                    if "import_inflow" in import_calls or "import_outflow" in import_calls:
                        if msg:
                            msg += "<br><br>"
                        msg += "* To complete the Boundary Conditions functionality, the 'Boundary Conditions' conversion "
                        msg +="must be done using the "
                        msg += "<FONT COLOR=green>Conversion from Schematic Layers to User Layers</FONT>"
                        msg += " tool in the <FONT COLOR=blue>FLO-2D panel</FONT>."

                    if msg:
                        self.uc.show_info(msg)

    @connection_required
    def import_selected_components(self):
        """
        Import selected traditional GDS files into FLO-2D database (GeoPackage).
        """
        self.gutils.disable_geom_triggers()
        self.f2g = Flo2dGeoPackage(self.con, self.iface)
        import_calls = [
            "import_tolspatial",
            "import_inflow",
            "import_outflow",
            "import_rain",
            "import_raincell",
            "import_evapor",
            "import_infil",
            "import_chan",
            "import_xsec",
            "import_hystruc",
            "import_street",
            "import_arf",
            "import_mult",
            "import_sed",
            "import_levee",
            "import_fpxsec",
            "import_breach",
            "import_gutter",
            "import_fpfroude",
            "import_swmmflo",
            "import_swmmflort",
            "import_swmmoutf",
            "import_wsurf",
            "import_wstime",
        ]
        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")
        fname, __ = QFileDialog.getOpenFileName(
            None, "Select FLO-2D file to import", directory=last_dir, filter="CONT.DAT"
        )
        if not fname:
            return
        dir_name = os.path.dirname(fname)
        s.setValue("FLO-2D/lastGdsDir", dir_name)
        bname = os.path.basename(fname)
        if self.f2g.set_parser(fname):
            if bname not in self.f2g.parser.dat_files:
                return

            empty = self.f2g.is_table_empty("grid")
            # check if a grid exists in the grid table
            if empty:
                self.uc.show_info("There is no grid defined!")
                return
            QApplication.setOverrideCursor(Qt.WaitCursor)
            dlg_components = ComponentsDialog(self.con, self.iface, self.lyrs, "in")
            QApplication.restoreOverrideCursor()
            ok = dlg_components.exec_()
            if ok:
                try:
                    QApplication.setOverrideCursor(Qt.WaitCursor)

                    if "Channels" not in dlg_components.components:
                        import_calls.remove("import_chan")
                        import_calls.remove("import_xsec")

                    if "Reduction Factors" not in dlg_components.components:
                        import_calls.remove("import_arf")

                    if "Streets" not in dlg_components.components:
                        import_calls.remove("import_street")

                    if "Outflow Elements" not in dlg_components.components:
                        import_calls.remove("import_outflow")

                    if "Inflow Elements" not in dlg_components.components:
                        import_calls.remove("import_inflow")

                    if "Levees" not in dlg_components.components:
                        import_calls.remove("import_levee")

                    if "Multiple Channels" not in dlg_components.components:
                        import_calls.remove("import_mult")

                    if "Breach" not in dlg_components.components:
                        import_calls.remove("import_breach")

                    if "Gutters" not in dlg_components.components:
                        import_calls.remove("import_gutter")

                    if "Infiltration" not in dlg_components.components:
                        import_calls.remove("import_infil")

                    if "Floodplain Cross Sections" not in dlg_components.components:
                        import_calls.remove("import_fpxsec")

                    if "Mudflow and Sediment Transport" not in dlg_components.components:
                        import_calls.remove("import_sed")

                    if "Evaporation" not in dlg_components.components:
                        import_calls.remove("import_evapor")

                    if "Hydraulic  Structures" not in dlg_components.components:
                        import_calls.remove("import_hystruc")

                    # if 'MODFLO-2D' not in dlg_components.components:
                    #     import_calls.remove('')

                    if "Rain" not in dlg_components.components:
                        import_calls.remove("import_rain")
                        import_calls.remove("import_raincell")

                    if "Storm Drain" not in dlg_components.components:
                        import_calls.remove("import_swmmflo")
                        import_calls.remove("import_swmmflort")
                        import_calls.remove("import_swmmoutf")

                    if "Spatial Tolerance" not in dlg_components.components:
                        import_calls.remove("import_tolspatial")

                    if "Spatial Froude" not in dlg_components.components:
                        import_calls.remove("import_fpfroude")

                    tables = [
                        "all_schem_bc",
                        "blocked_cells",
                        "breach",
                        "breach_cells",
                        "breach_fragility_curves",
                        "breach_global",
                        "buildings_areas",
                        "buildings_stats",
                        "chan",
                        "chan_confluences",
                        "chan_elems",
                        "chan_elems_interp",
                        "chan_n",
                        "chan_r",
                        "chan_t",
                        "chan_v",
                        "chan_wsel",
                        "chan_elems",
                        "cont",
                        "culvert_equations",
                        "evapor",
                        "evapor_hourly",
                        "evapor_monthly",
                        "fpfroude",
                        "fpfroude_cells",
                        "fpxsec",
                        "fpxsec_cells",
                        "grid",
                        "gutter_areas",
                        "gutter_cells",
                        "gutter_globals",
                        "infil",
                        "infil_areas_chan",
                        "infil_areas_green",
                        "infil_areas_horton",
                        "infil_areas_scs",
                        "infil_cells_green",
                        "infil_cells_horton",
                        "infil_cells_scs",
                        "infil_chan_elems",
                        "infil_chan_seg",
                        "inflow",
                        "inflow_cells",
                        "inflow_time_series",
                        "inflow_time_series_data",
                        "levee_data",
                        "levee_failure",
                        "levee_fragility",
                        "levee_general",
                        "mud_areas",
                        "mud_cells",
                        "mult",
                        "mult_areas",
                        "mult_cells",
                        "noexchange_chan_cells",
                        "outflow",
                        "outflow_cells",
                        "outflow_time_series",
                        "outflow_time_series_data",
                        "qh_params",
                        "qh_params_data",
                        "qh_table",
                        "qh_table_data",
                        "rain",
                        "rain_arf_areas",
                        "rain_arf_cells",
                        "rain_time_series",
                        "rain_time_series_data",
                        "raincell",
                        "raincell_data",
                        "rat_curves",
                        "rat_table",
                        "rbank",
                        "reservoirs",
                        "repl_rat_curves",
                        "reservoirs",
                        "sed_group_areas",
                        "sed_group_cells",
                        "sed_groups",
                        "sed_rigid_areas",
                        "sed_rigid_cells",
                        "sed_supply_areas",
                        "sed_supply_cells",
                        "spatialshallow",
                        "spatialshallow_cells",
                        "storm_drains",
                        "street_elems",
                        "street_general",
                        "street_seg",
                        "streets",
                        "struct",
                        "swmmflo",
                        "swmmflort",
                        "swmmflort_data",
                        "swmmoutf",
                        "tolspatial",
                        "tolspatial_cells",
                        "user_bc_lines",
                        "user_bc_points",
                        "user_bc_polygons",
                        "user_blocked_areas",
                        "user_chan_n",
                        "user_chan_r",
                        "user_chan_t",
                        "user_chan_v",
                        "user_elevation_points",
                        "user_elevation_polygons",
                        "user_fpxsec",
                        "user_infiltration",
                        "user_left_bank",
                        "user_levee_lines",
                        "user_model_boundary",
                        "user_noexchange_chan_areas",
                        "user_reservoirs",
                        "user_right_bank",
                        "user_roughness",
                        "user_streets",
                        "user_struct",
                        "user_swmm_conduits",
                        "user_swmm_nodes",
                        "user_xsec_n_data",
                        "user_xsections",
                        "wstime",
                        "wsurf",
                        "xsec_n_data",
                    ]

                    #                     for table in tables:
                    #                         self.gutils.clear_tables(table)

                    self.call_IO_methods(import_calls, True)  # The strings list 'export_calls', contains the names of
                    # the methods in the class Flo2dGeoPackage to import (read) the
                    # FLO-2D .DAT files

                    # save CRS to table cont
                    self.gutils.set_cont_par("PROJ", self.crs.toProj4())

                    # load layers and tables
                    self.load_layers()
                    self.uc.bar_info("Flo2D model imported", dur=3)
                    self.gutils.enable_geom_triggers()

                    if "import_chan" in import_calls:
                        self.gutils.create_schematized_rbank_lines_from_xs_tips()

                    self.setup_dock_widgets()
                    self.lyrs.refresh_layers()
                    self.lyrs.zoom_to_all()

                finally:
                    QApplication.restoreOverrideCursor()
                    if self.files_used != "" or self.files_not_used != "":
                        self.uc.show_info(
                            "Files read by this project:\n\n"
                            + self.files_used
                            + "\n\nFiles not found or empty:\n\n"
                            + self.files_not_used
                        )

                    msg = ""
                    if "import_swmmflo" in import_calls:
                        self.clean_rating_tables()

                        if self.gutils.is_table_empty("user_model_boundary"):
                            msg += "* To complete the Storm Drain functionality, the 'Computational Domain' and 'Storm Drains' conversion "
                            msg += "must be done using the "
                            msg += "<FONT COLOR=green>Conversion from Schematic Layers to User Layers</FONT>"
                            msg += " tool in the <FONT COLOR=blue>FLO-2D panel</FONT>...<br>"
                            msg += "...and <FONT COLOR=green>Import SWMM.INP</FONT> from the <FONT COLOR=blue>Storm Drain Editor widget</FONT>."

                        else:
                            msg += "* To complete the Storm Drain functionality, the 'Storm Drains' conversion "
                            msg += "must be done using the "
                            msg += "<FONT COLOR=green>Conversion from Schematic Layers to User Layers</FONT>"
                            msg += " tool in the <FONT COLOR=blue>FLO-2D panel</FONT>...<br>"
                            msg += "...and <FONT COLOR=green>Import SWMM.INP</FONT> from the <FONT COLOR=blue>Storm Drain Editor widget</FONT>."

                    if "import_inflow" in import_calls or "import_outflow" in import_calls:
                        if msg:
                            msg += "<br><br>"
                        msg += "* To complete the Boundary Conditions functionality, the 'Boundary Conditions' conversion "
                        msg +="must be done using the "
                        msg += "<FONT COLOR=green>Conversion from Schematic Layers to User Layers</FONT>"
                        msg += " tool in the <FONT COLOR=blue>FLO-2D panel</FONT>."

                    if msg:
                        self.uc.show_info(msg)

    def clean_rating_tables(self):
        remove_grid = []
        grids = self.gutils.execute("SELECT DISTINCT grid_fid, name FROM swmmflort").fetchall()
        if grids:
            for g in grids:
                row = self.gutils.execute("SELECT fid FROM swmmflo WHERE swmm_jt = ?", (g[0],)).fetchall()
                if not row:
                    remove_grid.append(g)

        if remove_grid:
            for rg in remove_grid:
                self.gutils.execute(
                    "UPDATE swmmflort SET grid_fid = ?, name = ? WHERE grid_fid = ?", (None, rg[1], rg[0])
                )

    @connection_required
    def export_gds(self):
        """
        Export traditional GDS files into FLO-2D database (GeoPackage).
        """
        self.f2g = Flo2dGeoPackage(self.con, self.iface)
        sql = """SELECT name, value FROM cont;"""
        options = {o: v if v is not None else "" for o, v in self.f2g.execute(sql).fetchall()}
        export_calls = [
            "export_cont_toler",
            "export_tolspatial",
            "export_inflow",
            "export_outflow",
            "export_rain",
            "export_raincell",
            "export_evapor",
            "export_infil",
            "export_chan",
            "export_xsec",
            "export_hystruc",
            "export_street",
            "export_arf",
            "export_mult",
            "export_sed",
            "export_levee",
            "export_fpxsec",
            "export_breach",
            "export_gutter",
            "export_fpfroude",
            "export_swmmflo",
            "export_swmmflort",
            "export_swmmoutf",
            "export_wsurf",
            "export_wstime",
            "export_shallowNSpatial",
            "export_mannings_n_topo",
        ]

        dlg_components = ComponentsDialog(self.con, self.iface, self.lyrs, "out")
        ok = dlg_components.exec_()
        if ok:
            QApplication.setOverrideCursor(Qt.WaitCursor)

            if "Channels" not in dlg_components.components:
                export_calls.remove("export_chan")
                export_calls.remove("export_xsec")

            if "Reduction Factors" not in dlg_components.components:
                export_calls.remove("export_arf")

            if "Streets" not in dlg_components.components:
                export_calls.remove("export_street")

            if "Outflow Elements" not in dlg_components.components:
                export_calls.remove("export_outflow")

            if "Inflow Elements" not in dlg_components.components:
                export_calls.remove("export_inflow")

            if "Levees" not in dlg_components.components:
                export_calls.remove("export_levee")

            if "Multiple Channels" not in dlg_components.components:
                export_calls.remove("export_mult")

            if "Breach" not in dlg_components.components:
                export_calls.remove("export_breach")

            if "Gutters" not in dlg_components.components:
                export_calls.remove("export_gutter")

            if "Infiltration" not in dlg_components.components:
                export_calls.remove("export_infil")

            if "Floodplain Cross Sections" not in dlg_components.components:
                export_calls.remove("export_fpxsec")

            if "Mudflow and Sediment Transport" not in dlg_components.components:
                export_calls.remove("export_sed")

            if "Evaporation" not in dlg_components.components:
                export_calls.remove("export_evapor")

            if "Hydraulic  Structures" not in dlg_components.components:
                export_calls.remove("export_hystruc")

            # if 'MODFLO-2D' not in dlg_components.components:
            #     export_calls.remove('')

            if "Rain" not in dlg_components.components:
                export_calls.remove("export_rain")
                export_calls.remove("export_raincell")

            if "Storm Drain" not in dlg_components.components:
                export_calls.remove("export_swmmflo")
                export_calls.remove("export_swmmflort")
                export_calls.remove("export_swmmoutf")

            if "Spatial Shallow-n" not in dlg_components.components:
                export_calls.remove("export_shallowNSpatial")

            if "Spatial Tolerance" not in dlg_components.components:
                export_calls.remove("export_tolspatial")

            if "Spatial Froude" not in dlg_components.components:
                export_calls.remove("export_fpfroude")

            if "Manning's n and Topo" not in dlg_components.components:
                export_calls.remove("export_mannings_n_topo")

            project_dir = QgsProject.instance().absolutePath()
            outdir = QFileDialog.getExistingDirectory(
                None, "Select directory where FLO-2D model will be exported", directory=project_dir
            )
            if outdir:
                try:
                    QApplication.setOverrideCursor(Qt.WaitCursor)

                    s = QSettings()
                    s.setValue("FLO-2D/lastGdsDir", outdir)

                    self.call_IO_methods(
                        export_calls, True, outdir
                    )  # The strings list 'export_calls', contains the names of
                    # the methods in the class Flo2dGeoPackage to export (write) the
                    # FLO-2D .DAT files
                    self.uc.bar_info("Flo2D model exported to " + outdir, dur=3)
                    QApplication.restoreOverrideCursor()
                finally:
                    QApplication.restoreOverrideCursor()

                    if self.files_used != "":
                        self.uc.show_info("Files exported to\n" + outdir + "\n\n" + self.files_used)

                    if self.f2g.export_messages != "":
                        info = "WARNINGS:\n\n" + self.f2g.export_messages
                        self.uc.show_info(info)

        QApplication.restoreOverrideCursor()

    @connection_required
    def import_from_gpkg(self):
        s = QSettings()
        last_dir = s.value("FLO-2D/lastGpkgDir", "")
        attached_gpkg, __ = QFileDialog.getOpenFileName(
            None, "Select GeoPackage with data to import", directory=last_dir, filter="*.gpkg"
        )
        if not attached_gpkg:
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            s.setValue("FLO-2D/lastGpkgDir", os.path.dirname(attached_gpkg))
            self.gutils.copy_from_other(attached_gpkg)
            self.load_layers()
            self.setup_dock_widgets()
        finally:
            QApplication.restoreOverrideCursor()

    @connection_required
    def import_from_ras(self):
        dlg = RasImportDialog(self.con, self.iface, self.lyrs)
        ok = dlg.exec_()
        if ok:
            pass
        else:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            dlg.import_geometry()
            self.setup_dock_widgets()
            self.uc.bar_info("HEC-RAS geometry data imported!")
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.bar_warn("ERROR 030721.0518: Could not read HEC-RAS file!")
        QApplication.restoreOverrideCursor()

    def load_layers(self):
        self.lyrs.load_all_layers(self.gutils)
        self.lyrs.repaint_layers()
        self.lyrs.zoom_to_all()

    @connection_required
    def show_control_table(self):
        try:
            cont_table = self.lyrs.get_layer_by_name("Control", group=self.lyrs.group).layer()
            index = cont_table.fields().lookupField("note")
            tab_conf = cont_table.attributeTableConfig()
            tab_conf.setSortExpression('"name"')
            tab_conf.setColumnWidth(index, 250)
            cont_table.setAttributeTableConfig(tab_conf)
            self.iface.showAttributeTable(cont_table)
        except AttributeError as e:
            pass

    @connection_required
    def show_cont_toler(self):
        try:
            dlg_control = ContToler_JJ(self.con, self.iface, self.lyrs)
            save = dlg_control.exec_()
            if save:
                try:
                    dlg_control.save_parameters_JJ()
                    self.uc.bar_info("Parameters saved!", dur=3)
                except Exception as e:
                    self.uc.show_error("ERROR 110618.1828: Could not save FLO-2D parameters!", e)
                    return
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 110618.1816: Could not save FLO-2D parameters!!", e)

    @connection_required
    def activate_grid_info_tool(self):
        self.f2d_grid_info_dock.setUserVisible(True)
        grid = self.lyrs.data["grid"]["qlyr"]
        if grid is not None:
            self.grid_info_tool.grid = grid
            self.f2d_grid_info.set_info_layer(grid)
            self.f2d_grid_info.mann_default = self.gutils.get_cont_par("MANNING")
            self.f2d_grid_info.cell_Edit = self.gutils.get_cont_par("CELLSIZE")
            self.f2d_grid_info.n_cells = number_of_elements(self.gutils, grid)
            self.f2d_grid_info.gutils = self.gutils
            self.canvas.setMapTool(self.grid_info_tool)
        else:
            self.uc.bar_warn("There is no grid layer to identify.")

    @connection_required
    def show_user_profile(self, fid=None):
        self.f2d_dock.setUserVisible(True)
        self.f2d_widget.profile_tool_grp.setCollapsed(False)
        self.f2d_widget.profile_tool.identify_feature(self.cur_info_table, fid)
        self.cur_info_table = None

    @connection_required
    def show_profile(self, fid=None):
        self.f2d_widget.profile_tool.show_channel(self.cur_profile_table, fid)
        self.cur_profile_table = None

    @connection_required
    def show_xsec_editor(self, fid=None):
        """
        Show Cross-section editor.
        """
        self.f2d_dock.setUserVisible(True)
        self.f2d_widget.xs_editor_grp.setCollapsed(False)
        self.f2d_widget.xs_editor.populate_xsec_cbo(fid=fid)

    @connection_required
    def show_struct_editor(self, fid=None):
        """
        Show hydraulic structure editor.
        """
        self.f2d_dock.setUserVisible(True)
        self.f2d_widget.struct_editor_grp.setCollapsed(False)
        self.f2d_widget.struct_editor.populate_structs(struct_fid=fid)

    @connection_required
    def show_schem_xsec_info(self, fid=None):
        """
        Show schematic cross-section info.
        """
        try:
            self.dlg_schem_xsec_editor = SchemXsecEditorDialog(self.con, self.iface, self.lyrs, self.gutils, fid)
            self.dlg_schem_xsec_editor.show()
        except IndexError:
            self.uc.bar_warn("There is no schematic cross-section data to display!")

    @connection_required
    def show_bc_editor(self, fid=None):
        """
        Show boundary editor.
        """
        self.f2d_dock.setUserVisible(True)
        self.f2d_widget.bc_editor_grp.setCollapsed(False)
        self.f2d_widget.bc_editor.show_editor(self.cur_info_table, fid)
        self.cur_info_table = None

    @connection_required
    def show_evap_editor(self):
        """
        Show evaporation editor.
        """
        try:
            self.dlg_evap_editor = EvapEditorDialog(self.con, self.iface)
            self.dlg_evap_editor.show()
        except TypeError:
            self.uc.bar_warn("There is no evaporation data to display!")

    @connection_required
    def show_levee_elev_tool(self):
        """
        Show levee elevation tool.
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return
        # check for grid elements with null elevation
        null_elev_nr = grid_has_empty_elev(self.gutils)
        if null_elev_nr:
            msg = (
                "WARNING 060319.1805: The grid has {} elements with null elevation.\n\n"
                "Levee elevation tool requires that all grid elements have elevation defined."
            )
            self.uc.show_warn(msg.format(null_elev_nr))
            return
        else:
            pass
        # check if user levee layers are in edit mode
        levee_lyrs = ["Elevation Points", "Levee Lines", "Elevation Polygons"]
        for lyr in levee_lyrs:
            if not self.lyrs.save_edits_and_proceed(lyr):
                return
        # show the dialog
        dlg_levee_elev = LeveesToolDialog(self.con, self.iface, self.lyrs)
        dlg_levee_elev.show()

        while True:
            ok = dlg_levee_elev.exec_()
            if ok:
                if dlg_levee_elev.methods:
                    if 1 in dlg_levee_elev.methods:
                        break
                    else:
                        self.uc.show_warn("WARNING 060319.1831: Levee user lines required!")
            else:
                return

        try:
            #             start = datetime.now()
            QApplication.setOverrideCursor(Qt.WaitCursor)
            n_elements_total = 1
            n_levee_directions_total = 0
            n_fail_features_total = 0

            starttime = time.time()
            for n_elements, n_levee_directions, n_fail_features, ranger in self.schematize_levees():
                n_elements_total += n_elements
                n_levee_directions_total += n_levee_directions
                n_fail_features_total += n_fail_features

                for no in sorted(dlg_levee_elev.methods):
                    if no == 1:
                        # processing for a spatial selection range is enabled on this type
                        dlg_levee_elev.methods[no](rangeReq = ranger)
                    else:
                        dlg_levee_elev.methods[no]()
            inctime = time.time()
            print ("%s seconds to process levee features" % round(inctime - starttime, 2))

            # Delete duplicates:
            grid_lyr = self.lyrs.get_layer_by_name("Grid", group=self.lyrs.group).layer()
            q = False
            if n_elements_total > 0:
                print ("in clear loop")
                dletes = "Cell - Direction\n---------------\n"
                levees = self.lyrs.data["levee_data"]["qlyr"]
                leveesToDelete = delete_levee_directions_duplicates_np(self.gutils, levees, cellIDNumpyArray) # pass grid layer if it exists
                #leveesToDelete = delete_levee_directions_duplicates(self.gutils, levees, grid_lyr)
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
                                        "{:>10}-{:1}({:2})".format(str(levee[0]), str(levee[1]), dirID(levee[1]))
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
                                        "{:>10}-{:1}({:2})".format(str(levee[0]), str(levee[1]), dirID(levee[1]))
                                    )
                                    + "\t"
                                )
                                k = 1

                        else:
                            if k <= 3:
                                dletes += (
                                    "{:<25}".format(
                                        "{:>10}-{:1}({:2})".format(str(levee[0]), str(levee[1]), dirID(levee[1]))
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
                                        "{:>10}-{:1}({:2})".format(str(levee[0]), str(levee[1]), dirID(levee[1]))
                                    )
                                    + "\t"
                                )
                                k = 1

                    dletes += "\n\nWould you like to delete them?"

                    #                     dletes = Qt.convertFromPlainText(dletes)
                    QApplication.restoreOverrideCursor()

                    m = QMessageBox()
                    title = "Duplicate Opposite Levee Directions".center(170)
                    m.setWindowTitle(title)
                    m.setText(
                        "There are "
                        + str(len(leveesToDelete))
                        + " levees directions duplicated. "
                        + "They have lower crest elevation than the opposite direction.\n\n"
                        + "Would you like to delete them?"
                    )
                    m.setDetailedText(dletes)
                    m.setStandardButtons(QMessageBox.No | QMessageBox.Yes)
                    m.setDefaultButton(QMessageBox.Yes)

                    # Spacer                        width, height, h policy, v policy
                    horizontalSpacer = QSpacerItem(0, 300, QSizePolicy.Preferred, QSizePolicy.Preferred)
                    #                     verticalSpacer = QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Expanding)
                    layout = m.layout()
                    layout.addItem(horizontalSpacer)
                    #                     layout.addItem(verticalSpacer)

                    #                     m.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding);
                    #                     m.setSizePolicy(QSizePolicy.Maximum,QSizePolicy.Maximum);
                    #                     m.setFixedHeight(12000);
                    #                     m.setFixedWidth(12000);

                    #                     m.setFixedSize(2000, 1000);
                    #                     m.setBaseSize(QSize(2000, 1000))
                    #                     m.setMinimumSize(1000,1000)

                    #                     m.setInformativeText(dletes + '\n\nWould you like to delete them?')
                    q = m.exec_()
                    if q == QMessageBox.Yes:

                        #                     q = self.uc.question('The following are ' + str(len(leveesToDelete)) + ' opposite levees directions duplicated (with lower crest elevation).\n' +
                        #                                             'Would you like to delete them?\n\n' + dletes + '\n\nWould you like to delete them?')
                        #                     if q:
                        delete_levees_qry = """DELETE FROM levee_data WHERE grid_fid = ? AND ldir = ?;"""
                        delete_failure_qry = """DELETE FROM levee_failure WHERE grid_fid = ? and lfaildir = ?;"""
                        print ("Deleting extra levee and levee failure features")

                        # build indexes to speed up the process
                        qryIndex = """CREATE INDEX if not exists leveeDataGridFID_LDIR  ON levee_data (grid_fid, ldir);"""
                        self.gutils.execute(qryIndex)
                        qryIndex = """CREATE INDEX if not exists leveeFailureGridFID_LFAILDIR  ON levee_failure (grid_fid, lfaildir);"""
                        self.gutils.execute(qryIndex)
                        self.gutils.con.commit()

                        #cur = self.gutils.con.cursor()
                        #cur.executemany(delete_levees_qry, list([(str(levee[0]), str(levee[1]),) for levee in leveesToDelete]))
                        #self.gutils.con.commit()
                        #cur.executemany(delete_failure_qry, list([(str(levee[0]), str(levee[1]),) for levee in leveesToDelete]))
                        #self.gutils.con.commit()
                        #cur.close()

                        for leveeCounter, levee in enumerate(leveesToDelete):
                            #self.gutils.execute(delete_levees_qry, (levee[0], levee[1]))
                            self.gutils.execute("DELETE FROM levee_data WHERE grid_fid = %i AND ldir = %i;" % (levee[0], levee[1]))
                            if leveeCounter % 1000 == 0:
                                print ("DELETE FROM levee_data WHERE grid_fid = %i AND ldir = %i;" % (levee[0], levee[1]))
                            self.gutils.con.commit()
                            #self.gutils.execute(delete_failure_qry, (levee[0], levee[1]))
                            self.gutils.execute("DELETE FROM levee_failure WHERE grid_fid = %i and lfaildir = %i;" % (levee[0], levee[1]))
                            if leveeCounter % 1000 == 0:
                                print ("DELETE FROM levee_failure WHERE grid_fid = %i and lfaildir = %i;" % (levee[0], levee[1]))
                            self.gutils.con.commit()
                        print ("Done deleting extra levee and levee failure features")
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
                "ERROR 060319.1806: Assigning values aborted! Please check your crest elevation source layers.\n", e
            )

    @connection_required
    def show_hazus_dialog(self):
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        s = QSettings()
        project_dir = s.value("FLO-2D/lastGdsDir", "")
        if not os.path.isfile(os.path.join(project_dir, "DEPFP.OUT")):
            self.uc.show_warn(
                "WARNING 060319.1808: File DEPFP.OUT is needed for the Hazus flooding analysis. It is not in the current project directory:\n\n"
                + project_dir
            )
            pass

        lyrs = self.lyrs.list_group_vlayers()
        n_polys = 0
        for l in lyrs:
            if l.geometryType() == QgsWkbTypes.PolygonGeometry:
                n_polys += 1
        if n_polys == 0:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("WARNING 060319.1809: There are not any polygon layers selected (or visible)!")
            return

        #         self.iface.mainWindow().setWindowTitle(s.value('FLO-2D/lastGpkgDir', ''))

        dlg_hazus = HazusDialog(self.con, self.iface, self.lyrs)
        save = dlg_hazus.exec_()
        if save:
            try:
                self.uc.bar_info("Hazus Flooding Analysis performed!")
            except Exception as e:
                self.uc.bar_warn("Could not compute Hazus Flooding Analysis!")
                return

    @connection_required
    def show_errors_dialog(self):
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        dlg_errors = ErrorsDialog(self.con, self.iface, self.lyrs)
        dlg_errors.show()
        while True:
            ok = dlg_errors.exec_()
            if ok:
                break
            #                 if dlg_errors.current_project_radio.isChecked():
            #                     break
            #                 elif dlg_errors.debug_file_lineEdit.text() == "":
            #                     self.uc.show_warn("Select a DEBUG file!")
            #                 else:
            #                     break
            else:
                return

    @connection_required
    def show_mud_and_sediment_dialog(self):
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return
        dlg_ms = MudAndSedimentDialog(self.con, self.iface, self.lyrs)
        dlg_ms.show()
        ok = dlg_ms.exec_()
        if ok:
            try:
                dlg_ms.save_mud_sediment()
            except Exception as e:
                self.uc.show_error(
                    "ERROR 051021.0815: couldn't save Mud and Sediment tables!"
                    + "\n__________________________________________________",
                    e,
                )                
        else:
            return

    @staticmethod
    def show_help():
        QDesktopServices.openUrl(QUrl("https://flo-2dsoftware.github.io/qgis-flo-2d-plugin/"))

    def schematize_levees(self):
        """
        Generate schematic lines for user defined levee lines.
        """
        try:
            levee_lyr = self.lyrs.get_layer_by_name("Levee Lines", group=self.lyrs.group).layer()
            grid_lyr = self.lyrs.get_layer_by_name("Grid", group=self.lyrs.group).layer()

            for n_elements, n_levee_directions, n_fail_features, regionReq in generate_schematic_levees(
                self.gutils, levee_lyr, grid_lyr):
                yield (n_elements, n_levee_directions, n_fail_features, regionReq)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 030120.0723: unable to process user levees!\n", e)

    @connection_required
    def schematic2user(self):
        converter_dlg = Schema2UserDialog(self.con, self.iface, self.lyrs, self.uc)
        ok = converter_dlg.exec_()
        if ok:
            if converter_dlg.methods:
                pass
            else:
                self.uc.show_warn("WARNING 060319.1810: Please choose at least one conversion source!")
                return
        else:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        methods_numbers = sorted(converter_dlg.methods)
        for no in methods_numbers:
            converter_dlg.methods[no]()
        self.setup_dock_widgets()
        QApplication.restoreOverrideCursor()
        self.uc.show_info("Converting Schematic Layers to User Layers finished!")
        if 6 in methods_numbers:  # Storm Drains:
            self.uc.show_info(
                "To complete the Storm Drain functionality 'Import SWMM.INP' from the Storm Drain Editor widget."
            )

    @connection_required
    def user2schematic(self):
        converter_dlg = User2SchemaDialog(self.con, self.iface, self.lyrs, self.uc)
        ok = converter_dlg.exec_()
        if ok:
            if converter_dlg.methods:
                pass
            else:
                self.uc.show_warn("WARNING 060319.1811: Please choose at least one conversion source!")
                return
        else:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        for no in sorted(converter_dlg.methods):
            converter_dlg.methods[no]()
        self.setup_dock_widgets()
        QApplication.restoreOverrideCursor()
        self.uc.show_info("Converting User Layers to Schematic Layers finished!\n\n" + converter_dlg.message)

    def create_map_tools(self):
        self.canvas = self.iface.mapCanvas()
        self.info_tool = InfoTool(self.canvas, self.lyrs)
        self.grid_info_tool = GridInfoTool(self.uc, self.canvas, self.lyrs)
        self.channel_profile_tool = ChannelProfile(self.canvas, self.lyrs)

    def identify(self):
        self.canvas.setMapTool(self.info_tool)
        self.info_tool.update_lyrs_list()

    def get_feature_info(self, table, fid):
        try:
            show_editor = self.editors_map[table]
            self.cur_info_table = table
        except KeyError:
            self.uc.bar_info("Not implemented...")
            return
        show_editor(fid)

    def channel_profile(self):
        self.canvas.setMapTool(
            self.channel_profile_tool
        )  # 'channel_profile_tool' is an instance of ChannelProfile class,
        # created on loading the plugin, and to be used to plot channel
        # profiles using a subtool in the FLO-2D tool bar.
        # The plots will be based on data from the 'chan', 'cham_elems'
        # schematic layers.
        self.channel_profile_tool.update_lyrs_list()

    def get_feature_profile(self, table, fid):
        try:
            self.cur_profile_table = table  # Currently 'table' only gets 'chan' table name
        except KeyError:
            self.uc.bar_info("Channel Profile tool not implemented for selected features.")
            return
        self.show_profile(fid)

    def set_editors_map(self):
        self.editors_map = {
            "user_levee_lines": self.show_user_profile,
            "user_xsections": self.show_xsec_editor,
            "user_streets": self.show_user_profile,
            "user_centerline": self.show_user_profile,
            "chan_elems": self.show_schem_xsec_info,
            "user_left_bank": self.show_user_profile,
            "user_bc_points": self.show_bc_editor,
            "user_bc_lines": self.show_bc_editor,
            "user_bc_polygons": self.show_bc_editor,
            "user_struct": self.show_struct_editor,
            "struct": self.show_struct_editor,
        }

    def restore_settings(self):
        pass
