# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import cProfile
import io

# Lambda may not be necessary
# pylint: disable=W0108
import os
import pstats
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from datetime import datetime
from pstats import SortKey
from subprocess import (
    CREATE_NO_WINDOW,
    PIPE,
    STDOUT,
    CalledProcessError,
    Popen,
    call,
    check_call,
    check_output,
    run,
)
from PyQt5.QtWidgets import QApplication, QToolButton
from qgis._core import QgsMessageLog, QgsCoordinateReferenceSystem
from qgis.core import NULL, QgsProject, QgsWkbTypes
from qgis.gui import QgsDockWidget, QgsProjectionSelectionWidget
from qgis.PyQt import QtCore
from qgis.PyQt.QtCore import (
    QCoreApplication,
    QSettings,
    QSize,
    Qt,
    QTranslator,
    QUrl,
    qVersion,
)
from qgis.PyQt.QtGui import QCursor, QDesktopServices, QIcon, QPixmap
from qgis.PyQt.QtWidgets import (
    QAction,
    QApplication,
    QFileDialog,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSpacerItem,
    qApp,
)
from urllib3.contrib import _securetransport
from .flo2d_ie.flo2dgeopackage import Flo2dGeoPackage
from .flo2d_tools.channel_profile_tool import ChannelProfile
from .flo2d_tools.flopro_tools import (
    FLOPROExecutor,
    MapperExecutor,
    ProgramExecutor,
    TailingsDamBreachExecutor,
)
from .flo2d_tools.grid_info_tool import GridInfoTool
from .flo2d_tools.grid_tools import (
    add_col_and_row_fields,
    assign_col_row_indexes_to_grid,
    cellIDNumpyArray,
    dirID,
    grid_has_empty_elev,
    number_of_elements,
)
from .flo2d_tools.info_tool import InfoTool
from .flo2d_tools.schematic_tools import (
    delete_redundant_levee_directions_np,
    generate_schematic_levees,
)
from .flo2d_tools.schema2user_tools import SchemaSWMMConverter
from collections import OrderedDict, defaultdict

from .geopackage_utils import GeoPackageUtils, connection_required, database_disconnect, database_connect
from .gui import dlg_settings
from .gui.dlg_components import ComponentsDialog
from .gui.dlg_cont_toler_jj import ContToler_JJ
from .gui.dlg_evap_editor import EvapEditorDialog
from .gui.dlg_flopro import ExternalProgramFLO2D
from .gui.dlg_hazus import HazusDialog
from .gui.dlg_issues import ErrorsDialog
from .gui.dlg_levee_elev import LeveesToolDialog
from .gui.dlg_mud_and_sediment import MudAndSedimentDialog
from .gui.dlg_ras_import import RasImportDialog
from .gui.dlg_schem_xs_info import SchemXsecEditorDialog
from .gui.dlg_schema2user import Schema2UserDialog
from .gui.dlg_settings import SettingsDialog
from .gui.dlg_user2schema import User2SchemaDialog
from .gui.f2d_main_widget import FLO2DWidget
from .gui.grid_info_widget import GridInfoWidget
from .gui.plot_widget import PlotWidget
from .gui.table_editor_widget import TableEditorWidget
from .layers import Layers
from .user_communication import UserCommunication

global GRID_INFO, GENERAL_INFO


@contextmanager
def cd(newdir):
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield
    finally:
        os.chdir(prevdir)


class Flo2D(object):

    def __init__(self, iface):
        # self.pr = cProfile.Profile()
        # self.pr.enable()

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

        self.menu = self.tr("&FLO-2D")
        self.toolbar = self.iface.addToolBar("FLO-2D")
        self.toolbar.setObjectName("FLO-2D")
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
        self.new_gpkg = None

        # if hasattr(QtCore.Qt, 'AA_EnableHighDpiScaling'):
        #     QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
        #
        # if hasattr(QtCore.Qt, 'AA_UseHighDpiPixmaps'):
        #     QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
        # else:
        #     QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, False)

        # connections
        self.project.readProject.connect(self.load_gpkg_from_proj)

        self.uc.clear_bar_messages()
        QApplication.restoreOverrideCursor()

    def tr(self, message):
        """
        Get the translation for a string using Qt translation API.
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate("FLO-2D", message)

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

        self.f2d_widget.rain_editor.setup_connection()
        self.f2d_widget.rain_editor.rain_properties()

        self.f2d_widget.bc_editor.setup_connection()
        self.f2d_widget.bc_editor.populate_bcs(widget_setup=True)

        self.f2d_widget.ic_editor.populate_cbos()

        self.f2d_widget.street_editor.setup_connection()
        self.f2d_widget.street_editor.populate_streets()

        self.f2d_widget.struct_editor.populate_structs()

        self.f2d_widget.channels_editor.setup_connection()

        self.f2d_widget.xs_editor.setup_connection()
        self.f2d_widget.xs_editor.populate_xsec_cbo()

        self.f2d_widget.fpxsec_editor.setup_connection()

        self.f2d_widget.storm_drain_editor.setup_connection()

        self.f2d_widget.fpxsec_editor.populate_cbos()

        self.f2d_widget.infil_editor.setup_connection()

        self.f2d_widget.levee_and_breach_editor.setup_connection()

        self.f2d_widget.multiple_channels_editor.setup_connection()

        self.f2d_widget.pre_processing_tools.setup_connection()

    def add_action(
            self,
            icon_path,
            text,
            callback=None,
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
        if callback is not None:
            action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if menu is not None:
            popup = QMenu()

            for m in menu:
                icon = QIcon(m[0])
                act = QAction(icon, m[1], parent)
                act.triggered.connect(m[2])
                popup.addAction(act)
            action.setMenu(popup)

        if text == "Grid Info Tool":
            action.setCheckable(True)
            action.setChecked(False)
            pass

        if text == "Info Tool":
            action.setCheckable(True)
            action.setChecked(False)
            pass

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:

            if text == "Run Simulation":
                toolButton = QToolButton()
                toolButton.setMenu(popup)
                toolButton.setIcon(QIcon(self.plugin_dir + "/img/flo2d.svg"))
                toolButton.setPopupMode(QToolButton.InstantPopup)
                self.toolbar.addWidget(toolButton)
            elif text == "Import/Export":
                toolButton = QToolButton()
                toolButton.setMenu(popup)
                toolButton.setIcon(QIcon(self.plugin_dir + "/img/export.png"))
                toolButton.setPopupMode(QToolButton.InstantPopup)
                self.toolbar.addWidget(toolButton)
            else:
                self.toolbar.addAction(action)


        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        self.actions.append(action)
        return action

    def initGui(self):
        """
        Create the menu entries and toolbar icons inside the QGIS GUI.
        """
        global GRID_INFO, GENERAL_INFO

        self.add_action(
            os.path.join(self.plugin_dir, "img/settings.svg"),
            text=self.tr("Settings"),
            callback=self.show_settings,
            parent=self.iface.mainWindow()
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/flo_open_project.svg"),
            text=self.tr("Open FLO-2D geopackage"),
            callback=lambda: self.flo_open_project(),
            parent=self.iface.mainWindow()
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/flo_save_project.svg"),
            text=self.tr("Save FLO-2D geopackage"),
            callback=lambda: self.flo_save_project(),
            parent=self.iface.mainWindow()
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/flo2d.svg"),
            text=self.tr("Run Simulation"),
            callback=None,
            parent=self.iface.mainWindow(),
            menu=(
                (
                    os.path.join(self.plugin_dir, "img/flo2d.svg"),
                    "Quick Run FLO-2D Pro",
                    lambda: self.quick_run_flopro(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/FLO.png"),
                    "Run FLO-2D Pro",
                    self.run_flopro,
                ),
                (
                    os.path.join(self.plugin_dir, "img/profile_run2.svg"),
                    "Run Profiles",
                    self.run_profiles,
                ),
                (
                    os.path.join(self.plugin_dir, "img/hydrog.svg"),
                    "Run Hydrog",
                    self.run_hydrog,
                ),
                (
                    os.path.join(self.plugin_dir, "img/maxplot.svg"),
                    "Run MaxPlot",
                    self.run_maxplot,
                ),
                (
                    os.path.join(self.plugin_dir, "img/mapper2.svg"),
                    "Run Mapper",
                    self.run_mapper,
                ),
                (
                    os.path.join(self.plugin_dir, "img/tailings dam breach.svg"),
                    "Run Tailings Dam Tool ",
                    self.run_tailingsdambreach,
                ),
                (
                    os.path.join(self.plugin_dir, "img/settings2.svg"),
                    "Run Settings",
                    self.run_settings,
                )
            )
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/export.png"),
            text=self.tr("Import/Export"),
            callback=None,
            parent=self.iface.mainWindow(),
            menu=(
                (
                    os.path.join(self.plugin_dir, "img/gpkg2gpkg.svg"),
                    "Import from GeoPackage",
                    lambda: self.import_from_gpkg(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/import_gds.svg"),
                    "Import data (*.DAT) files",
                    lambda: self.import_gds(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/import_components.svg"),
                    "Import selected components files",
                    lambda: self.import_components(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/export_gds.svg"),
                    "Export data (*.DAT) files",
                    lambda: self.export_gds(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/import_hdf.svg"),
                    "Import from HDF5",
                    lambda: self.import_hdf5(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/export_hdf.svg"),
                    "Export to HDF5",
                    lambda: self.export_hdf5(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/import_ras.svg"),
                    "Import RAS geometry",
                    lambda: self.import_from_ras(),
                )
            )
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

        # self.add_action(
        #     os.path.join(self.plugin_dir, "img/user_to_schematic.svg"),
        #     text=self.tr("Convert User Layers to Schematic Layers"),
        #     callback=lambda: self.user2schematic(),
        #     parent=self.iface.mainWindow(),
        # )

        self.add_action(
            os.path.join(self.plugin_dir, "img/profile_tool.svg"),
            text=self.tr("Channel Profile"),
            callback=self.channel_profile,
            # Connects to 'init_channel_profile' method, via QAction triggered.connect(callback)
            parent=self.iface.mainWindow(),
        )

        GENERAL_INFO = self.add_action(
            os.path.join(self.plugin_dir, "img/info_tool.svg"),
            text=self.tr("Info Tool"),
            callback=self.activate_general_info_tool,
            parent=self.iface.mainWindow(),
            menu=(
                (
                    os.path.join(self.plugin_dir, "img/info_tool.svg"),
                    "Info Tool",
                    self.activate_general_info_tool ,
                ),                
                (
                    os.path.join(self.plugin_dir, "img/flo2d.svg"),
                    "Select .RPT file",
                    self.select_RPT_File,
                ),
            ),
        )

        GRID_INFO = self.add_action(
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

        # self.add_action(
        #     os.path.join(self.plugin_dir, "img/tailings dam breach.svg"),
        #     text=self.tr("Tailings Dam Tool"),
        #     callback=self.run_tailingsdambreach,
        #     parent=self.iface.mainWindow(),
        # )

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

        if ma == 0:
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.f2d_dock)
            self.f2d_dock.setFloating(True)
        else:
            self.iface.addDockWidget(ma, self.f2d_dock)

        if ta == 0:
            self.iface.addDockWidget(Qt.BottomDockWidgetArea, self.f2d_table_dock)
            self.f2d_table_dock.setFloating(True)
        else:
            self.iface.addDockWidget(ta, self.f2d_table_dock)

        if pa == 0:
            self.iface.addDockWidget(Qt.BottomDockWidgetArea, self.f2d_plot_dock)
            self.f2d_plot_dock.setFloating(True)
        else:
            self.iface.addDockWidget(pa, self.f2d_plot_dock)

        if ga == 0:
            self.iface.addDockWidget(Qt.TopDockWidgetArea, self.f2d_grid_info_dock)
            self.f2d_grid_info_dock.setFloating(True)
        else:
            self.iface.addDockWidget(ga, self.f2d_grid_info_dock)

    def unload(self):
        """
        Removes the plugin menu item and icon from QGIS GUI.
        """

        # Close and safe routines execution times statistics:
        # try:
        #     s = QSettings()
        #     lastDir = s.value("FLO-2D/lastGdsDir", "")
        #     stts = os.path.join(lastDir, "STATS.TXT")
        #     with open(stts, "w") as f:
        #         self.pr.disable()
        #         sortby = SortKey.TIME
        #         ps = pstats.Stats(self.pr, stream=f).sort_stats(sortby)
        #         ps.print_stats()
        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.show_error("ERROR", e)
        #     time.sleep(3)

        self.lyrs.clear_rubber()
        # remove maptools
        del self.info_tool, self.grid_info_tool, self.channel_profile_tool
        # others
        del self.uc
        database_disconnect(self.con)
        for action in self.actions:
            self.iface.removePluginMenu(self.tr("&FLO-2D"), action)
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
        """
        Function to create a new geopackage
        """
        self.uncheck_all_info_toggles()
        dlg_settings = SettingsDialog(self.con, self.iface, self.lyrs, self.gutils)
        dlg_settings.show()
        result = dlg_settings.exec_()
        if result and dlg_settings.con:
            dlg_settings.write()
            self.con = dlg_settings.con
            self.iface.f2d["con"] = self.con
            self.gutils = dlg_settings.gutils
            self.crs = dlg_settings.crs  # Coordinate Reference System.
            gpkg_path = self.gutils.get_gpkg_path()
            gpkg_path_adj = gpkg_path.replace("\\", "/")
            self.write_proj_entry("gpkg", gpkg_path_adj)  # TODO check if this could cause an error
            self.setup_dock_widgets()
            s = QSettings()
            s.setValue("FLO-2D/last_flopro_project", os.path.dirname(gpkg_path_adj))
            s.setValue("FLO-2D/lastGdsDir", os.path.dirname(gpkg_path_adj))

            proj_name = "FLO-2D-Plugin"
            uri = f'geopackage:{gpkg_path}?projectName={proj_name}'
            self.project.write(uri)

            pn = dlg_settings.lineEdit_pn.text()
            contact = dlg_settings.lineEdit_au.text()
            email = dlg_settings.lineEdit_co.text()
            company = dlg_settings.lineEdit_em.text()
            phone = dlg_settings.lineEdit_te.text()

            plugin_v = dlg_settings.label_pv.text()
            qgis_v = dlg_settings.label_qv.text()
            flo2d_v = dlg_settings.label_fv.text()

            self.gutils.set_metadata_par("PROJ_NAME", pn)
            self.gutils.set_metadata_par("CONTACT", contact)
            self.gutils.set_metadata_par("EMAIL", email)
            self.gutils.set_metadata_par("PHONE", phone)
            self.gutils.set_metadata_par("COMPANY", company)
            self.gutils.set_metadata_par("PLUGIN_V", plugin_v)
            self.gutils.set_metadata_par("QGIS_V", qgis_v)
            self.gutils.set_metadata_par("FLO-2D_V", flo2d_v)
            self.gutils.set_metadata_par("CRS", self.crs.authid())

            self.uc.show_info("FLO-2D-Project sucessfully created.")

    def flo_open_project(self):
        """
        Function to open a FLO-2D project from geopackage
        """
        s = QSettings()
        last_dir = s.value("FLO-2D/lastGpkgDir", "")
        gpkg_path, __ = QFileDialog.getOpenFileName(
            None,
            "Select GeoPackage with data to import",
            directory=last_dir,
            filter="*.gpkg",
        )
        if not gpkg_path:
            return
        try:
            s.setValue("FLO-2D/lastGpkgDir", os.path.dirname(gpkg_path))

            self.new_gpkg = gpkg_path
            proj_name = "FLO-2D-Plugin"
            uri = f'geopackage:{gpkg_path}?projectName={proj_name}'

            # No project inside the geopackage
            if not self.project.read(uri):

                title = "Missing Project File"
                msg = "No FLO-2D-Project file (*.qgz) was found in the geopackage. Would you like to create a new one or open an existing?"
                text1 = "Create"
                text2 = "Open"

                answer = self.uc.dialog_with_2_customized_buttons(title, msg, text1, text2)
                # Create new project
                if answer == QMessageBox.Yes:
                    dlg_settings = SettingsDialog(self.con, self.iface, self.lyrs, self.gutils)
                    dlg_settings.connect(gpkg_path)
                    self.con = dlg_settings.con
                    self.iface.f2d["con"] = self.con
                    self.gutils = dlg_settings.gutils
                    self.crs = dlg_settings.crs
                    self.setup_dock_widgets()

                    proj = self.gutils.get_cont_par("PROJ")
                    cs = QgsCoordinateReferenceSystem()
                    cs.createFromProj(proj)
                    self.project.setCrs(cs)
                    gpkg_path_adj = gpkg_path.replace("\\", "/")
                    self.write_proj_entry("gpkg", gpkg_path_adj)
                    self.project.write(uri)
                    self.uc.show_info("FLO-2D-Project created into the Geopackage.")
                # Open existing project
                elif answer == QMessageBox.No:
                    # Open the project and geopackage and then save the project into the geopackage
                    qgz_path, __ = QFileDialog.getOpenFileName(
                        None,
                        "Select FLO-2D-Project (*.qgz) to import",
                        directory=last_dir,
                        filter="*.qgz",
                    )
                    if not qgz_path:
                        return

                    self.project.read(qgz_path)
                    self.project.write(uri)
                    self.uc.show_info("FLO-2D-Project added into the Geopackage.")

                # Cancel
                else:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_info("FLO-2D-Project opening cancelled.")
                    return

            else:
                QApplication.restoreOverrideCursor()
                self.uc.show_info("FLO-2D-Project successfully loaded.")

        finally:
            QApplication.restoreOverrideCursor()

    @connection_required
    def flo_save_project(self):
        """
        Function to save a FLO-2D project into a geopackage
        """
        gpkg_path = self.gutils.get_gpkg_path()
        proj_name = "FLO-2D-Plugin"
        uri = f'geopackage:{gpkg_path}?projectName={proj_name}'
        self.project.write(uri)
        self.uc.show_info("FLO-2D-Project saved!")

    def run_settings(self):
        """
        Function to set the run settings: FLO-2D and Project folders
        """
        self.uncheck_all_info_toggles()
        dlg = ExternalProgramFLO2D(self.iface, "Run Settings")
        dlg.debug_run_btn.setVisible(False)
        dlg.exec_folder_lbl.setText("FLO-2D Folder")
        ok = dlg.exec_()
        if not ok:
            return
        flo2d_dir, project_dir = dlg.get_parameters()
        s = QSettings()
        s.setValue("FLO-2D/lastGdsDir", project_dir)
        s.setValue("FLO-2D/last_flopro", flo2d_dir)

        if project_dir != "" and flo2d_dir != "":
            s.setValue("FLO-2D/run_settings", True)

        self.uc.show_info("Run Settings saved!")

    @connection_required
    def quick_run_flopro(self):
        """
        Function to export and run FLO-2D Pro
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        project_dir = QgsProject.instance().absolutePath()
        outdir = QFileDialog.getExistingDirectory(
            None,
            "Select directory where FLO-2D model will run",
            directory=project_dir,
        )

        if outdir:
            self.f2g = Flo2dGeoPackage(self.con, self.iface)
            sql = """SELECT name, value FROM cont;"""
            options = {o: v if v is not None else "" for o, v in self.f2g.execute(sql).fetchall()}
            export_calls = [
                "export_cont_toler",
                "export_tolspatial",
                "export_inflow",
                "export_tailings",
                "export_outflow",
                "export_rain",
                "export_evapor",
                "export_infil",
                "export_chan",
                "export_xsec",
                "export_hystruc",
                "export_bridge_xsec",
                "export_bridge_coeff_data",
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

            s = QSettings()
            s.setValue("FLO-2D/lastGdsDir", outdir)

            dlg_components = ComponentsDialog(self.con, self.iface, self.lyrs, "out")
            QgsMessageLog.logMessage(str(dlg_components))
            ok = dlg_components.exec_()
            if ok:
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
                    export_calls.remove("export_tailings")

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
                    export_calls.remove("export_bridge_xsec")
                    export_calls.remove("export_bridge_coeff_data")
                else:
                    xsecs = self.gutils.execute("SELECT fid FROM struct WHERE icurvtable = 3").fetchone()
                    if not xsecs:
                        if os.path.isfile(outdir + r"\BRIDGE_XSEC.DAT"):
                            os.remove(outdir + r"\BRIDGE_XSEC.DAT")
                        export_calls.remove("export_bridge_xsec")
                        export_calls.remove("export_bridge_coeff_data")

                if "Rain" not in dlg_components.components:
                    export_calls.remove("export_rain")

                if "Storm Drain" not in dlg_components.components:
                    export_calls.remove("export_swmmflo")
                    export_calls.remove("export_swmmflort")
                    export_calls.remove("export_swmmoutf")
                else:
                    self.uc.show_info("Storm Drain features not allowed on the Quick Run FLO-2D Pro.")
                    return

                if "Spatial Shallow-n" not in dlg_components.components:
                    export_calls.remove("export_shallowNSpatial")

                if "Spatial Tolerance" not in dlg_components.components:
                    export_calls.remove("export_tolspatial")

                if "Spatial Froude" not in dlg_components.components:
                    export_calls.remove("export_fpfroude")

                if "Manning's n and Topo" not in dlg_components.components:
                    export_calls.remove("export_mannings_n_topo")

                QApplication.setOverrideCursor(Qt.WaitCursor)

                try:
                    s = QSettings()
                    s.setValue("FLO-2D/lastGdsDir", outdir)

                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    self.call_IO_methods(export_calls, True, outdir)

                    # The strings list 'export_calls', contains the names of
                    # the methods in the class Flo2dGeoPackage to export (write) the
                    # FLO-2D .DAT files

                    self.uc.bar_info("Flo2D model exported to " + outdir, dur=3)
                    QApplication.restoreOverrideCursor()

                finally:
                    QApplication.restoreOverrideCursor()

                    if "export_swmmflo" in export_calls:
                        self.f2d_widget.storm_drain_editor.export_storm_drain_INP_file()

                    # Delete .DAT files the model will try to use if existing:
                    if "export_mult" in export_calls:
                        if self.gutils.is_table_empty("simple_mult_cells"):
                            new_files_used = self.files_used.replace("SIMPLE_MULT.DAT\n", "")
                            self.files_used = new_files_used
                            if os.path.isfile(outdir + r"\SIMPLE_MULT.DAT"):
                                if self.uc.question(
                                        "There are no simple multiple channel cells in the project but\n"
                                        + "there is a SIMPLE_MULT.DAT file in the directory.\n"
                                        + "If the file is not deleted it will be used by the model.\n\n"
                                        + "Delete SIMPLE_MULT.DAT?"
                                ):
                                    os.remove(outdir + r"\SIMPLE_MULT.DAT")

                        if self.gutils.is_table_empty("mult_cells"):
                            new_files_used = self.files_used.replace("\nMULT.DAT\n", "\n")
                            self.files_used = new_files_used
                            if os.path.isfile(outdir + r"\MULT.DAT"):
                                if self.uc.question(
                                        "There are no multiple channel cells in the project but\n"
                                        + "there is a MULT.DAT file in the directory.\n"
                                        + "If the file is not deleted it will be used by the model.\n\n"
                                        + "Delete MULT.DAT?"
                                ):
                                    os.remove(outdir + r"\MULT.DAT")

                    if self.f2g.export_messages != "":
                        info = "WARNINGS:\n\n" + self.f2g.export_messages
                        self.uc.show_info(info)

            QApplication.restoreOverrideCursor()
            self.run_program("FLOPRO.exe")

    def run_flopro(self):
        self.uncheck_all_info_toggles()
        self.run_program("FLOPRO.exe")

    def run_tailingsdambreach(self):
        self.uncheck_all_info_toggles()
        self.run_program("Tailings Dam Breach.exe")

    def run_mapper(self):
        self.uncheck_all_info_toggles()
        self.run_program("Mapper PRO.exe")

    def run_profiles(self):
        self.uncheck_all_info_toggles()
        self.run_program("PROFILES.exe")

    def run_hydrog(self):
        self.uncheck_all_info_toggles()
        self.run_program("HYDROG.exe")

    def run_maxplot(self):
        self.uncheck_all_info_toggles()
        self.run_program("MAXPLOT.exe")

    def run_program(self, exe_name):
        """
        Function to run programs
        """
        self.uncheck_all_info_toggles()
        s = QSettings()
        # check if run was configured
        if not s.contains("FLO-2D/run_settings"):
            self.run_settings()
        if s.value("FLO-2D/last_flopro") == "" or s.value("FLO-2D/lastGdsDir") == "":
            self.run_settings()
        flo2d_dir = s.value("FLO-2D/last_flopro")
        project_dir = s.value("FLO-2D/lastGdsDir")

        if sys.platform != "win32":
            self.uc.bar_warn("Could not run " + exe_name + " under current operation system!")
            return
        try:
            if os.path.isfile(flo2d_dir + "\\" + exe_name):
                if exe_name == "Tailings Dam Breach.exe":
                    program = ProgramExecutor(flo2d_dir, project_dir, exe_name)
                    program.perform()
                    self.uc.bar_info(exe_name + " started!", dur=3)
                else:
                    if os.path.isfile(project_dir + "\\" + "CONT.DAT"):
                        program = ProgramExecutor(flo2d_dir, project_dir, exe_name)
                        program.perform()
                        self.uc.bar_info(exe_name + " started!", dur=3)
                    else:
                        self.uc.show_warn("CONT.DAT is not in directory:\n\n" + f"{project_dir}\n\n" + f"Select the correct directory.")
                        self.run_settings()
            else:
                self.uc.show_warn("WARNING 241020.0424: Program " + exe_name + " is not in directory\n\n" + flo2d_dir)
        except Exception as e:
            self.uc.log_info(repr(e))
            self.uc.bar_warn("Running " + exe_name + " failed!")

    def select_RPT_File(self):
        self.uncheck_all_info_toggles()

        grid = self.lyrs.data["grid"]["qlyr"]
        if grid is not None:
            if self.f2d_widget.storm_drain_editor.create_SD_discharge_table_and_plots("Just assign FLO-2D settings"):
                GENERAL_INFO.setChecked(True)
                self.canvas.setMapTool(self.info_tool)
        else:
            self.uc.bar_warn("There is no grid layer to identify.")

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

            GRID_INFO.setChecked(False)
            GENERAL_INFO.setChecked(False)

    def call_IO_methods(self, calls, debug, *args):
        if self.f2g.parsed_format == Flo2dGeoPackage.FORMAT_DAT:
            self.call_IO_methods_dat(calls, debug, *args)
        elif self.f2g.parsed_format == Flo2dGeoPackage.FORMAT_HDF5:
            self.call_IO_methods_hdf5(calls, debug, *args)

    def call_IO_methods_hdf5(self, calls, debug, *args):
        self.f2g.parser.write_mode = "w"
        for call in calls:
            method = getattr(self.f2g, call)
            try:
                method(*args)
                self.f2g.parser.write_mode = "a"
            except Exception as e:
                if debug is True:
                    self.uc.log_info(traceback.format_exc())
                else:
                    raise
        self.f2g.parser.write_mode = "w"

    def call_IO_methods_dat(self, calls, debug, *args):
        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")

        self.files_used = ""
        self.files_not_used = ""
        if calls[0] == "export_cont_toler":
            self.files_used = "CONT.DAT\n"

        for call in calls:
            if call == "export_bridge_xsec":
                dat = "BRIDGE_XSEC.DAT"
            elif call == "export_bridge_coeff_data":
                dat = "BRIDGE_COEFF_DATA.DAT"
            elif call == "import_hystruc_bridge_xs":
                dat = "BRIDGE_XSEC.DAT"
            else:
                dat = call.split("_")[-1].upper() + ".DAT"
            if call.startswith("import"):
                if self.f2g.parser.dat_files[dat] is None:
                    if dat == "MULT.DAT":
                        if self.f2g.parser.dat_files["SIMPLE_MULT.DAT"] is None:
                            self.uc.log_info('Files required for "{0}" not found. Action skipped!'.format(call))
                            self.files_not_used += dat + "\n"
                            continue
                        else:
                            self.files_used += "SIMPLE_MULT.DAT\n"
                            pass
                    else:
                        self.uc.log_info('Files required for "{0}" not found. Action skipped!'.format(call))
                        if dat not in ["WSURF.DAT", "WSTIME.DAT"]:
                            self.files_not_used += dat + "\n"
                        continue
                else:
                    if dat == "MULT.DAT":
                        self.files_used += dat + " and/or SIMPLE_MULT.DAT" + "\n"
                        pass
                    elif os.path.getsize(os.path.join(last_dir, dat)) > 0:
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
                        if dat == "SWMMFLO.DAT":
                            self.files_used += "SWMM.INP" + "\n"
                        if dat == "TOPO.DAT":
                            self.files_used += "MANNINGS_N.DAT" + "\n"
                        if dat == "MULT.DAT":
                            self.files_used += "SIMPLE_MULT.DAT" + "\n"
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
        self.uncheck_all_info_toggles()
        self.gutils.disable_geom_triggers()
        self.f2g = Flo2dGeoPackage(self.con, self.iface)
        import_calls = [
            "import_cont_toler",
            "import_mannings_n_topo",
            "import_inflow",
            "import_tailings",
            "import_outflow",
            "import_rain",
            "import_raincell",
            "import_evapor",
            "import_infil",
            "import_chan",
            "import_xsec",
            "import_hystruc",
            "import_hystruc_bridge_xs",
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

            # Check if TOLER.DAT exist:
            if not os.path.isfile(dir_name + r"\TOLER.DAT") or os.path.getsize(dir_name + r"\TOLER.DAT") == 0:
                self.uc.show_info("ERROR 200322.0911: file TOLER.DAT is missing or empty!")
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
                        import_calls.remove("import_tailings")

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
                        import_calls.remove("import_hystruc_bridge_xs")

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
                        "user_swmm_pumps",
                        "user_swmm_orifices",
                        "user_swmm_weirs",
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

                    if "Storm Drain" in dlg_components.components:
                        try:
                            swmm_converter = SchemaSWMMConverter(self.con, self.iface, self.lyrs)
                            swmm_converter.create_user_swmm_nodes()
                        except Exception as e:
                            self.uc.log_info(traceback.format_exc())
                            QApplication.restoreOverrideCursor()
                            self.uc.show_error(
                                "ERROR 040723.1749:\n\nConverting Schematic SD Inlets to User Storm Drain Nodes failed!"
                                + "\n_______________________________________________________________",
                                e,
                            )

                        if os.path.isfile(dir_name + r"\SWMM.INP"):
                            # if self.f2d_widget.storm_drain_editor.import_storm_drain_INP_file("Choose"):
                            if self.f2d_widget.storm_drain_editor.import_storm_drain_INP_file(
                                    "Force import of SWMM.INP", False
                            ):
                                self.files_used += "SWMM.INP" + "\n"
                        else:
                            self.uc.bar_error("ERROR 100623.0944: SWMM.INP file not found!")

                    self.setup_dock_widgets()
                    self.lyrs.refresh_layers()
                    self.lyrs.zoom_to_all()

                    # See if geopackage has grid with 'col' and 'row' fields:
                    grid_lyr = self.lyrs.data["grid"]["qlyr"]
                    field_index = grid_lyr.fields().indexFromName("col")
                    if field_index == -1:
                        QApplication.restoreOverrideCursor()

                        add_new_colums = self.uc.customized_question(
                            "FLO-2D",
                            "WARNING 290521.0500:    Old GeoPackage.\n\nGrid table doesn't have 'col' and 'row' fields!\n\n"
                            + "Would you like to add the 'col' and 'row' fields to the grid table?",
                            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                            QMessageBox.Cancel,
                        )

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
                            proceed = self.uc.question(
                                "Grid layer's fields 'col' and 'row' have NULL values!\n\nWould you like to assign them?"
                            )
                            if proceed:
                                QApplication.setOverrideCursor(Qt.WaitCursor)
                                assign_col_row_indexes_to_grid(self.lyrs.data["grid"]["qlyr"], self.gutils)
                                QApplication.restoreOverrideCursor()
                            else:
                                return

                    QApplication.restoreOverrideCursor()

                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 050521.0349: importing .DAT files!.\n", e)
                finally:
                    QApplication.restoreOverrideCursor()
                    if self.files_used != "" or self.files_not_used != "":
                        self.uc.show_info(
                            "Files read by this project:\n\n"
                            + self.files_used
                            + (
                                ""
                                if self.files_not_used == ""
                                else "\n\nFiles not found or empty:\n\n" + self.files_not_used
                            )
                        )

                    msg = ""
                    if "import_swmmflo" in import_calls:
                        msg += "* To complete the Storm Drain functionality, the 'Computational Domain' and 'Storm Drains' conversion "
                        msg += "must be done using the "
                        msg += "<FONT COLOR=green>Conversion from Schematic Layers to User Layers</FONT>"
                        msg += " tool in the <FONT COLOR=blue>FLO-2D panel</FONT>...<br>"
                        if "SWMM.INP" not in self.files_used:
                            msg += "...and <FONT COLOR=green>Import SWMM.INP</FONT> from the <FONT COLOR=blue>Storm Drain Editor widget</FONT>."

                    if "import_inflow" in import_calls or "import_outflow" in import_calls:
                        if msg:
                            msg += "<br><br>"
                        msg += (
                            "* To complete the Boundary Conditions functionality, the 'Boundary Conditions' conversion "
                        )
                        msg += "must be done using the "
                        msg += "<FONT COLOR=green>Conversion from Schematic Layers to User Layers</FONT>"
                        msg += " tool in the <FONT COLOR=blue>FLO-2D panel</FONT>."

                    if msg:
                        self.uc.show_info(msg)

    @connection_required
    def import_hdf5(self):
        """
        Import HDF5 datasets into FLO-2D database (GeoPackage).
        """
        self.uncheck_all_info_toggles()
        self.gutils.disable_geom_triggers()
        self.f2g = Flo2dGeoPackage(self.con, self.iface)
        import_calls = [
            "import_cont_toler",
            "import_mannings_n_topo",
        ]
        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")
        input_hdf5, _ = QFileDialog.getOpenFileName(
            None,
            "Import FLO-2D model data from HDF5 format",
            directory=last_dir,
            filter="HDF5 file (*.hdf5; *.HDF5)",
        )

        if not input_hdf5:
            return
        indir = os.path.dirname(input_hdf5)
        self.f2g = Flo2dGeoPackage(self.con, self.iface, parsed_format=Flo2dGeoPackage.FORMAT_HDF5)
        self.f2g.set_parser(input_hdf5)
        try:
            s = QSettings()
            s.setValue("FLO-2D/lastGdsDir", indir)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.call_IO_methods(import_calls, True)
            self.uc.bar_info("Flo2D model imported from " + input_hdf5, dur=3)
            QApplication.restoreOverrideCursor()
        finally:
            QApplication.restoreOverrideCursor()
            empty = self.f2g.is_table_empty("grid")
            # check if a grid exists in the grid table
            if not empty:
                q = "There is a grid already defined in GeoPackage. Overwrite it?"
                if self.uc.question(q):
                    pass
                else:
                    self.uc.bar_info("Import cancelled", dur=3)
                    return
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
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

                self.call_IO_methods(import_calls, True)

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

                    add_new_colums = self.uc.customized_question(
                        "FLO-2D",
                        "WARNING 290521.0500:    Old GeoPackage.\n\nGrid table doesn't have 'col' and 'row' fields!\n\n"
                        + "Would you like to add the 'col' and 'row' fields to the grid table?",
                        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                        QMessageBox.Cancel,
                    )

                    if add_new_colums == QMessageBox.Cancel:
                        return

                    if add_new_colums == QMessageBox.No:
                        return
                    else:
                        if add_col_and_row_fields(grid_lyr):
                            assign_col_row_indexes_to_grid(grid_lyr, self.gutils)
                else:
                    cell = self.gutils.execute("SELECT col FROM grid WHERE fid = 1").fetchone()
                    if cell is None:
                        QApplication.restoreOverrideCursor()
                        proceed = self.uc.question(
                            "Grid layer's fields 'col' and 'row' have NULL values!\n\nWould you like to assign them?"
                        )
                        if proceed:
                            QApplication.setOverrideCursor(Qt.WaitCursor)
                            assign_col_row_indexes_to_grid(self.lyrs.data["grid"]["qlyr"], self.gutils)
                            QApplication.restoreOverrideCursor()
                        else:
                            return

                QApplication.restoreOverrideCursor()
            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error("ERROR 050521.0349: importing from .HDF5 file!.\n", e)
            finally:
                QApplication.restoreOverrideCursor()
                msg = ""
                if "import_swmmflo" in import_calls:
                    msg += "* To complete the Storm Drain functionality, the 'Computational Domain' and 'Storm Drains' conversion "
                    msg += "must be done using the "
                    msg += "<FONT COLOR=green>Conversion from Schematic Layers to User Layers</FONT>"
                    msg += " tool in the <FONT COLOR=blue>FLO-2D panel</FONT>...<br>"
                    # msg += "...and <FONT COLOR=green>Import SWMM.INP</FONT> from the <FONT COLOR=blue>Storm Drain Editor widget</FONT>."

                if "import_inflow" in import_calls or "import_outflow" in import_calls:
                    if msg:
                        msg += "<br><br>"
                    msg += "* To complete the Boundary Conditions functionality, the 'Boundary Conditions' conversion "
                    msg += "must be done using the "
                    msg += "<FONT COLOR=green>Conversion from Schematic Layers to User Layers</FONT>"
                    msg += " tool in the <FONT COLOR=blue>FLO-2D panel</FONT>."

                if msg:
                    self.uc.show_info(msg)

    @connection_required
    def import_components(self):
        """
        Import selected traditional GDS files into FLO-2D database (GeoPackage).
        """
        self.uncheck_all_info_toggles()
        imprt = self.uc.dialog_with_2_customized_buttons(
            "Select import method", "", " Several Components", " One Single Component "
        )

        if imprt == QMessageBox.Yes:
            self.import_selected_components()
        elif imprt == QMessageBox.No:
            self.import_selected_components2()

    @connection_required
    def import_selected_components(self):
        self.gutils.disable_geom_triggers()
        self.f2g = Flo2dGeoPackage(self.con, self.iface)
        import_calls = [
            # "import_cont_toler",
            "import_tolspatial",
            "import_inflow",
            "import_tailings",
            "import_outflow",
            "import_rain",
            "import_raincell",
            "import_evapor",
            "import_infil",
            "import_chan",
            "import_xsec",
            "import_hystruc",
            "import_hystruc_bridge_xs",
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
        ]

        # s = QSettings()
        # last_dir = s.value("FLO-2D/lastGdsDir", "")
        # fname, __ = QFileDialog.getOpenFileName(
        #     None, "Select FLO-2D file to import", directory=last_dir, filter="CONT.DAT"
        # )
        # if not fname:
        #     return
        # dir_name = os.path.dirname(fname)
        # s.setValue("FLO-2D/lastGdsDir", dir_name)
        # bname = os.path.basename(fname)
        #
        # if self.f2g.set_parser(fname):
        #     if bname not in self.f2g.parser.dat_files:
        #         return

        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")
        # project_dir = QgsProject.instance().absolutePath()
        outdir = QFileDialog.getExistingDirectory(None, "Select directory of files to be imported", directory=last_dir)
        if outdir:
            s.setValue("FLO-2D/lastGdsDir", outdir)
            bname = "CONT.DAT"
            fname = outdir + "/CONT.DAT"
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
                        import_calls.remove("import_tailings")

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
                        import_calls.remove("import_hystruc_bridge_xs")

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

                    if import_calls:
                        self.call_IO_methods(
                            import_calls, True
                        )  # The strings list 'import_calls', contains the names of
                        # the methods in the class Flo2dGeoPackage to import (read) the
                        # FLO-2D .DAT files

                        # save CRS to table cont
                        self.gutils.set_cont_par("PROJ", self.crs.toProj4())

                        # load layers and tables
                        self.load_layers()
                        self.uc.bar_info("Flo2D model imported", dur=3)
                        self.gutils.enable_geom_triggers()

                        if "Storm Drain" in dlg_components.components:
                            try:
                                swmm_converter = SchemaSWMMConverter(self.con, self.iface, self.lyrs)
                                swmm_converter.create_user_swmm_nodes()
                            except Exception as e:
                                self.uc.log_info(traceback.format_exc())
                                QApplication.restoreOverrideCursor()
                                self.uc.show_error(
                                    "ERROR 100623.1044:\n\nConverting Schematic SD Inlets to User Storm Drain Nodes failed!"
                                    + "\n_______________________________________________________________",
                                    e,
                                )

                            if os.path.isfile(outdir + r"\SWMM.INP"):
                                # if self.f2d_widget.storm_drain_editor.import_storm_drain_INP_file("Choose"):
                                if self.f2d_widget.storm_drain_editor.import_storm_drain_INP_file(
                                        "Force import of SWMM.INP", True
                                ):
                                    self.files_used += "SWMM.INP" + "\n"
                            else:
                                self.uc.bar_error("ERROR 100623.0944: SWMM.INP file not found!")
                        # if "Storm Drain" in dlg_components.components:
                        #     if self.f2d_widget.storm_drain_editor.import_storm_drain_INP_file("Force import of SWMM.INP", True):
                        #         self.files_used += "SWMM.INP" + "\n"

                        if "import_chan" in import_calls:
                            self.gutils.create_schematized_rbank_lines_from_xs_tips()

                        self.setup_dock_widgets()
                        self.lyrs.refresh_layers()
                        self.lyrs.zoom_to_all()
                    else:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_info("No component was selected!")

                finally:
                    QApplication.restoreOverrideCursor()
                    if self.files_used != "" or self.files_not_used != "":
                        self.uc.show_info(
                            "Files read by this project:\n\n"
                            + self.files_used
                            + (
                                ""
                                if self.files_not_used == ""
                                else "\n\nFiles not found or empty:\n\n" + self.files_not_used
                            )
                        )

                    msg = ""
                    if "import_swmmflo" in import_calls:
                        self.clean_rating_tables()

                        if self.gutils.is_table_empty("user_model_boundary"):
                            msg += "* To complete the Storm Drain functionality, the 'Computational Domain' and 'Storm Drains' conversion "
                            msg += "must be done using the "
                            msg += "<FONT COLOR=green>Conversion from Schematic Layers to User Layers</FONT>"
                            msg += " tool in the <FONT COLOR=blue>FLO-2D panel</FONT>...<br>"
                            if "SWMM.INP" not in self.files_used:
                                msg += "...and <FONT COLOR=green>Import SWMM.INP</FONT> from the <FONT COLOR=blue>Storm Drain Editor widget</FONT>."
                        else:
                            msg += "* To complete the Storm Drain functionality, the 'Storm Drains' conversion "
                            msg += "must be done using the "
                            msg += "<FONT COLOR=green>Conversion from Schematic Layers to User Layers</FONT>"
                            msg += " tool in the <FONT COLOR=blue>FLO-2D panel</FONT>...<br>"
                            if "SWMM.INP" not in self.files_used:
                                msg += "...and <FONT COLOR=green>Import SWMM.INP</FONT> from the <FONT COLOR=blue>Storm Drain Editor widget</FONT>."

                    if "import_inflow" in import_calls or "import_outflow" in import_calls:
                        if msg:
                            msg += "<br><br>"
                        msg += (
                            "* To complete the Boundary Conditions functionality, the 'Boundary Conditions' conversion "
                        )
                        msg += "must be done using the "
                        msg += "<FONT COLOR=green>Conversion from Schematic Layers to User Layers</FONT>"
                        msg += " tool in the <FONT COLOR=blue>FLO-2D panel</FONT>."

                    if msg:
                        self.uc.show_info(msg)

    @connection_required
    def import_selected_components2(self):
        """
        Import selected traditional GDS files into FLO-2D database (GeoPackage).
        """
        self.gutils.disable_geom_triggers()
        self.f2g = Flo2dGeoPackage(self.con, self.iface)
        file_to_import_calls = {
            "CONT.DAT": "import_cont_toler",
            "TOLER.DAT": "import_cont_toler",
            "TOLSPATIAL.DAT": "import_tolspatial",
            "INFLOW.DAT": "import_inflow",
            "TAILINGS.DAT": "import_tailings",
            "OUTFLOW.DAT": "import_outflow",
            "RAIN.DAT": "import_rain",
            "RAINCELL.DAT": "import_raincell",
            "EVAPOR.DAT": "import_evapor",
            "INFIL.DAT": "import_infil",
            "CHAN.DAT": "import_chan",
            "XSEC.DAT": "import_xsec",
            "HYSTRUC.DAT": "import_hystruc",
            "BRIDGE_XSEC.DAT": "import_hystruc_bridge_xs",
            "STREET.DAT": "import_street",
            "ARF.DAT": "import_arf",
            "MULT.DAT": "import_mult",
            "SED.DAT": "import_sed",
            "LEVEE.DAT": "import_levee",
            "FPXSEC.DAT": "import_fpxsec",
            "BREACH.DAT": "import_breach",
            "GUTTER.DAT": "import_gutter",
            "FPFROUDE.DAT": "import_fpfroude",
            "SWMMFLO.DAT": "import_swmmflo",
            "SWMMFLORT.DAT": "import_swmmflort",
            "SWMMOUTETF.DAT": "import_swmmoutf",
            "WSURF.DAT": "import_wsurf",
            "WSTIME.DAT": "import_wstime",
        }
        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")
        fname, __ = QFileDialog.getOpenFileName(
            None, "Select FLO-2D file to import", directory=last_dir, filter="(*.DAT)"
        )
        if not fname:
            return
        dir_name = os.path.dirname(fname)
        s.setValue("FLO-2D/lastGdsDir", dir_name)
        bname = os.path.basename(fname)

        if bname not in file_to_import_calls:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Import selected GDS file",
                "Import from {0} file is not supported.".format(bname),
            )
            return

        if self.f2g.set_parser(fname):
            call_string = file_to_import_calls[bname]
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                method = getattr(self.f2g, call_string)
                method()
                QApplication.restoreOverrideCursor()
                QMessageBox.information(
                    self.iface.mainWindow(),
                    "Import selected GDS file",
                    "Import from {0} is successful".format(bname),
                )
                if call_string == "import_chan":
                    self.gutils.create_schematized_rbank_lines_from_xs_tips()

                self.setup_dock_widgets()
                self.lyrs.refresh_layers()

            except Exception as e:
                QApplication.restoreOverrideCursor()
                QMessageBox.critical(
                    self.iface.mainWindow(),
                    "Import selected GDS file",
                    "Import from {0} fails".format(bname),
                )

            finally:
                msg = ""
                if call_string == "import_swmmflo":
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

                if call_string == "import_inflow" or call_string == "import_outflow":
                    if msg:
                        msg += "<br><br>"
                    msg += "* To complete the Boundary Conditions functionality, the 'Boundary Conditions' conversion "
                    msg += "must be done using the "
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
                    "UPDATE swmmflort SET grid_fid = ?, name = ? WHERE grid_fid = ?",
                    (None, rg[1], rg[0]),
                )

    @connection_required
    def export_gds(self):
        """
        Export traditional GDS files into FLO-2D database (GeoPackage).
        """
        self.uncheck_all_info_toggles()
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        project_dir = QgsProject.instance().absolutePath()
        outdir = QFileDialog.getExistingDirectory(
            None,
            "Select directory where FLO-2D model will be exported",
            directory=project_dir,
        )
        if outdir:
            self.f2g = Flo2dGeoPackage(self.con, self.iface)
            sql = """SELECT name, value FROM cont;"""
            options = {o: v if v is not None else "" for o, v in self.f2g.execute(sql).fetchall()}
            export_calls = [
                "export_cont_toler",
                "export_tolspatial",
                "export_inflow",
                "export_tailings",
                "export_outflow",
                "export_rain",
                "export_evapor",
                "export_infil",
                "export_chan",
                "export_xsec",
                "export_hystruc",
                "export_bridge_xsec",
                "export_bridge_coeff_data",
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

            s = QSettings()
            s.setValue("FLO-2D/lastGdsDir", outdir)

            dlg_components = ComponentsDialog(self.con, self.iface, self.lyrs, "out")
            ok = dlg_components.exec_()
            if ok:
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
                    export_calls.remove("export_tailings")

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
                    export_calls.remove("export_bridge_xsec")
                    export_calls.remove("export_bridge_coeff_data")
                else:
                    # if not self.uc.question("Did you schematize Hydraulic Structures? Do you want to export Hydraulic Structures files?"):
                    #     export_calls.remove("export_hystruc")
                    #     export_calls.remove("export_bridge_xsec")
                    #     export_calls.remove("export_bridge_coeff_data")
                    # else:
                    xsecs = self.gutils.execute("SELECT fid FROM struct WHERE icurvtable = 3").fetchone()
                    if not xsecs:
                        if os.path.isfile(outdir + r"\BRIDGE_XSEC.DAT"):
                            os.remove(outdir + r"\BRIDGE_XSEC.DAT")
                        export_calls.remove("export_bridge_xsec")
                        export_calls.remove("export_bridge_coeff_data")

                if "Rain" not in dlg_components.components:
                    export_calls.remove("export_rain")

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

                if "export_swmmflort" in export_calls:
                    if not self.uc.question(
                            "Did you schematize Storm Drains? Do you want to export Storm Drain files?"
                    ):
                        export_calls.remove("export_swmmflo")
                        export_calls.remove("export_swmmflort")
                        export_calls.remove("export_swmmoutf")

                QApplication.setOverrideCursor(Qt.WaitCursor)

                try:
                    s = QSettings()
                    s.setValue("FLO-2D/lastGdsDir", outdir)

                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    self.call_IO_methods(export_calls, True, outdir)

                    # The strings list 'export_calls', contains the names of
                    # the methods in the class Flo2dGeoPackage to export (write) the
                    # FLO-2D .DAT files

                    self.uc.bar_info("Flo2D model exported to " + outdir, dur=3)
                    QApplication.restoreOverrideCursor()

                finally:
                    QApplication.restoreOverrideCursor()

                    if "export_swmmflo" in export_calls:
                        self.f2d_widget.storm_drain_editor.export_storm_drain_INP_file()

                    # Delete .DAT files the model will try to use if existing:
                    if "export_mult" in export_calls:
                        if self.gutils.is_table_empty("simple_mult_cells"):
                            new_files_used = self.files_used.replace("SIMPLE_MULT.DAT\n", "")
                            self.files_used = new_files_used
                            if os.path.isfile(outdir + r"\SIMPLE_MULT.DAT"):
                                if self.uc.question(
                                        "There are no simple multiple channel cells in the project but\n"
                                        + "there is a SIMPLE_MULT.DAT file in the directory.\n"
                                        + "If the file is not deleted it will be used by the model.\n\n"
                                        + "Delete SIMPLE_MULT.DAT?"
                                ):
                                    os.remove(outdir + r"\SIMPLE_MULT.DAT")

                        if self.gutils.is_table_empty("mult_cells"):
                            new_files_used = self.files_used.replace("\nMULT.DAT\n", "\n")
                            self.files_used = new_files_used
                            if os.path.isfile(outdir + r"\MULT.DAT"):
                                if self.uc.question(
                                        "There are no multiple channel cells in the project but\n"
                                        + "there is a MULT.DAT file in the directory.\n"
                                        + "If the file is not deleted it will be used by the model.\n\n"
                                        + "Delete MULT.DAT?"
                                ):
                                    os.remove(outdir + r"\MULT.DAT")

                    if self.files_used != "":
                        self.uc.show_info("Files exported to\n" + outdir + "\n\n" + self.files_used)

                    if self.f2g.export_messages != "":
                        info = "WARNINGS:\n\n" + self.f2g.export_messages
                        self.uc.show_info(info)

        QApplication.restoreOverrideCursor()

    @connection_required
    def export_hdf5(self):
        """
        Export FLO-2D database (GeoPackage) data into HDF5 format.
        """
        self.uncheck_all_info_toggles()
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")
        output_hdf5, _ = QFileDialog.getSaveFileName(
            None,
            "Save FLO-2D model data into HDF5 format",
            directory=last_dir,
            filter="HDF5 file (*.hdf5; *.HDF5)",
        )
        if output_hdf5:
            outdir = os.path.dirname(output_hdf5)
            self.f2g = Flo2dGeoPackage(self.con, self.iface, parsed_format=Flo2dGeoPackage.FORMAT_HDF5)
            self.f2g.set_parser(output_hdf5, get_cell_size=False)
            export_calls = [
                "export_cont_toler",
                "export_mannings_n_topo",
                "export_neighbours",
            ]
            try:
                s = QSettings()
                s.setValue("FLO-2D/lastGdsDir", outdir)

                QApplication.setOverrideCursor(Qt.WaitCursor)
                self.call_IO_methods(export_calls, True)
                self.uc.bar_info("Flo2D model exported to " + output_hdf5, dur=3)
                QApplication.restoreOverrideCursor()
            finally:
                QApplication.restoreOverrideCursor()
                if self.f2g.export_messages != "":
                    info = "WARNINGS:\n\n" + self.f2g.export_messages
                    self.uc.show_info(info)

    @connection_required
    def import_from_gpkg(self):
        self.uncheck_all_info_toggles()
        s = QSettings()
        last_dir = s.value("FLO-2D/lastGpkgDir", "")
        attached_gpkg, __ = QFileDialog.getOpenFileName(
            None,
            "Select GeoPackage with data to import",
            directory=last_dir,
            filter="*.gpkg",
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
        self.uncheck_all_info_toggles()
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
        self.uncheck_all_info_toggles()
        try:
            dlg_control = ContToler_JJ(self.con, self.iface, self.lyrs)
            while True:
                save = dlg_control.exec_()
                if save:
                    try:
                        if dlg_control.save_parameters_JJ():
                            self.uc.bar_info("Parameters saved!", dur=3)
                            break
                    except Exception as e:
                        self.uc.show_error("ERROR 110618.1828: Could not save FLO-2D parameters!", e)
                        return
                else:
                    break
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 110618.1816: Could not save FLO-2D parameters!!", e)

    def activate_general_info_tool(self):
        # GRID_INFO.setChecked(False)  
        # GENERAL_INFO.setChecked(False)
        # self.canvas.unsetMapTool(self.info_tool)  
        # self.canvas.unsetMapTool(self.grid_info_tool)  
        grid = self.lyrs.data["grid"]["qlyr"]
        if grid is not None:
            self.f2d_grid_info_dock.setUserVisible(True)
            tool = self.canvas.mapTool()
            if tool == self.info_tool:
                self.canvas.unsetMapTool(self.info_tool)
            else:
                if tool is not None:
                    self.canvas.unsetMapTool(tool)
                self.canvas.setMapTool(self.info_tool)
                GRID_INFO.setChecked(False)
                GENERAL_INFO.setChecked(True)
        else:
            self.uc.bar_warn("Define a database connection first!")
            GENERAL_INFO.setChecked(False)

    @connection_required
    def activate_grid_info_tool(self):
        self.f2d_grid_info_dock.setUserVisible(True)
        grid = self.lyrs.data["grid"]["qlyr"]
        if grid is not None:
            tool = self.canvas.mapTool()
            if tool == self.grid_info_tool:
                self.canvas.unsetMapTool(self.grid_info_tool)
            else:
                if tool is not None:
                    self.canvas.unsetMapTool(tool)
                self.grid_info_tool.grid = grid
                self.f2d_grid_info.set_info_layer(grid)
                self.f2d_grid_info.mann_default = self.gutils.get_cont_par("MANNING")
                self.f2d_grid_info.cell_Edit = self.gutils.get_cont_par("CELLSIZE")
                self.f2d_grid_info.n_cells = number_of_elements(self.gutils, grid)
                self.f2d_grid_info.gutils = self.gutils
                self.canvas.setMapTool(self.grid_info_tool)
                GENERAL_INFO.setChecked(False)
        else:
            self.uc.bar_warn("There is no grid layer to identify.")
            GRID_INFO.setChecked(False)

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
    def show_sd_discharge(self, fid=None):
        """
        Show storm drain discharge for a given inlet node.
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return
                
        name, grid = self.gutils.execute("SELECT name, grid FROM user_swmm_nodes WHERE fid = ?", (fid,)).fetchone()
        self.f2d_dock.setUserVisible(True)
        self.f2d_widget.storm_drain_editor_grp.setCollapsed(False)
        self.f2d_widget.storm_drain_editor.create_SD_discharge_table_and_plots(name)

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
        self.uncheck_all_info_toggles()
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
        self.uncheck_all_info_toggles()
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
            for (
                    n_elements,
                    n_levee_directions,
                    n_fail_features,
                    ranger,
            ) in self.schematize_levees():
                n_elements_total += n_elements
                n_levee_directions_total += n_levee_directions
                n_fail_features_total += n_fail_features

                for no in sorted(dlg_levee_elev.methods):
                    if no == 1:
                        # processing for a spatial selection range is enabled on this type
                        dlg_levee_elev.methods[no](rangeReq=ranger)
                    else:
                        dlg_levee_elev.methods[no]()
            inctime = time.time()
            print("%s seconds to process levee features" % round(inctime - starttime, 2))

            # Delete duplicates:
            grid_lyr = self.lyrs.get_layer_by_name("Grid", group=self.lyrs.group).layer()
            q = False
            if n_elements_total > 0:
                print("in clear loop")
                dletes = "Cell - Direction\n---------------\n"
                levees = self.lyrs.data["levee_data"]["qlyr"]

                # delete duplicate elements with the same direction and elevation too
                qryIndex = "CREATE INDEX if not exists levee_dataFIDGRIDFIDLDIRLEVCEST  ON levee_data (fid, grid_fid, ldir, levcrest);"
                self.gutils.con.execute(qryIndex)
                self.gutils.con.commit()

                levees_dup_qry = "SELECT min(fid), grid_fid, ldir, levcrest FROM levee_data GROUP BY grid_fid, ldir, levcrest HAVING COUNT(ldir) > 1 and count(levcrest) > 1 ORDER BY grid_fid"
                leveeDups = self.gutils.execute(levees_dup_qry).fetchall()  # min FID, grid fid, ldir, min levcrest
                # grab the values
                print(
                    "Found {valer} levee elements with duplicated grid, ldir, and elev; deleting the duplicates;".format(
                        valer=len(leveeDups)
                    )
                )
                del_dup_data = (
                    (item[1], item[2], item[3], item[0]) for item in leveeDups
                )  # grid fid, ldir, crest elev, fid

                # delete any duplicates in directions that aren't the min elevation
                levees_dup_delete_qry = (
                    "DELETE FROM levee_data WHERE grid_fid = ? and ldir = ? and levcrest = ? and fid <> ?;"
                )
                self.gutils.con.executemany(levees_dup_delete_qry, (del_dup_data))
                self.gutils.con.commit()

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

                    m = QMessageBox()
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
                        print("Deleting extra levee and levee failure features")

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
                        print("Done deleting extra levee and levee failure features")
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

    @connection_required
    def show_hazus_dialog(self):
        self.uncheck_all_info_toggles()
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
        self.uncheck_all_info_toggles()
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        dlg_errors = ErrorsDialog(self.con, self.iface, self.lyrs)
        dlg_errors.show()
        while True:
            ok = dlg_errors.exec_()
            if ok:
                break
            else:
                return

    @connection_required
    def show_mud_and_sediment_dialog(self):
        self.uncheck_all_info_toggles()
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        dlg_ms = MudAndSedimentDialog(self.con, self.iface, self.lyrs)
        dlg_ms.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        dlg_ms.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        repeat = True
        while repeat:
            dlg_ms.show()
            ok = dlg_ms.exec_()
            if ok:
                if dlg_ms.ok_to_save():
                    try:
                        dlg_ms.save_mud_sediment()
                        repeat = False
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

    @connection_required
    def schematic2user(self):
        self.uncheck_all_info_toggles()
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
        self.uncheck_all_info_toggles
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

    def get_feature_info(self, table, fid):
        try:
            show_editor = self.editors_map[table]
            self.cur_info_table = table
        except KeyError:
            self.uc.bar_info("Not implemented...")
            return
        show_editor(fid)

    def channel_profile(self):
        self.uncheck_all_info_toggles()
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
            "user_swmm_nodes": self.show_sd_discharge,
        }

    def restore_settings(self):
        pass

    def grid_info_tool_clicked(self):
        self.uc.bar_info("grid info tool clicked.")
        
    def uncheck_all_info_toggles(self):
        GRID_INFO.setChecked(False)
        GENERAL_INFO.setChecked(False)
        self.canvas.unsetMapTool(self.grid_info_tool)
        self.canvas.unsetMapTool(self.info_tool)  
