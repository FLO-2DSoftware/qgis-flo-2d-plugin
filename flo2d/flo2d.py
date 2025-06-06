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
import re
import sys
import time
import traceback
from contextlib import contextmanager

from PyQt5.QtWidgets import QToolButton, QProgressDialog, QPushButton
from osgeo import gdal, ogr
from qgis._core import  QgsCoordinateReferenceSystem, QgsVectorLayer, QgsRasterLayer
from qgis.core import NULL, QgsProject, QgsWkbTypes
from qgis.gui import QgsDockWidget, QgsProjectionSelectionWidget
from qgis.PyQt.QtCore import (
    QCoreApplication,
    QSettings,
    Qt,
    QTranslator,
    QUrl,
    qVersion,
)
from qgis.PyQt.QtGui import QDesktopServices, QIcon
from qgis.PyQt.QtWidgets import (
    QAction,
    QApplication,
    QFileDialog,
    QMenu,
    QMessageBox,
    qApp,
)
from qgis.utils import plugins
from .flo2d_ie.flo2dgeopackage import Flo2dGeoPackage
from .flo2d_tools.flopro_tools import (
    ProgramExecutor,
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
from .flo2d_tools.results_tool import ResultsTool
from .flo2d_tools.schematic_tools import (
    delete_redundant_levee_directions_np,
    generate_schematic_levees,
)
from .geopackage_utils import GeoPackageUtils, connection_required, database_disconnect, database_connect
from .gui.dlg_components import ComponentsDialog
from .gui.dlg_cont_toler_jj import ContToler_JJ
from .gui.dlg_evap_editor import EvapEditorDialog
from .gui.dlg_export_multidomain import ExportMultipleDomainsDialog
from .gui.dlg_flopro import ExternalProgramFLO2D
from .gui.dlg_gpkg_backup import GpkgBackupDialog
from .gui.dlg_gpkg_management import GpkgManagementDialog
from .gui.dlg_hazus import HazusDialog
from .gui.dlg_import_multidomain import ImportMultipleDomainsDialog
from .gui.dlg_issues import ErrorsDialog
from .gui.dlg_levee_elev import LeveesToolDialog
from .gui.dlg_mud_and_sediment import MudAndSedimentDialog
from .gui.dlg_ras_import import RasImportDialog
from .gui.dlg_schem_xs_info import SchemXsecEditorDialog
from .gui.dlg_schema2user import Schema2UserDialog
from .gui.dlg_settings import SettingsDialog
from .gui.dlg_storm_drain_attributes import InletAttributes, ConduitAttributes, OutletAttributes, PumpAttributes, \
    OrificeAttributes, WeirAttributes, StorageUnitAttributes
from .gui.dlg_update_gpkg import UpdateGpkg
from .gui.dlg_user2schema import User2SchemaDialog
from .gui.f2d_main_widget import FLO2DWidget
from .gui.grid_info_widget import GridInfoWidget
from .gui.plot_widget import PlotWidget
from .gui.storm_drain_editor_widget import StormDrainEditorWidget
from .gui.table_editor_widget import TableEditorWidget
from .layers import Layers
from .misc.invisible_lyrs_grps import InvisibleLayersAndGroups
from .user_communication import UserCommunication
from .utils import get_flo2dpro_version, get_plugin_version

from PIL import Image

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
        self.toolButtons = []
        self.toolActions = []

        self.files_used = ""
        self.files_not_used = ""

        self.menu = self.tr("&FLO-2D")
        self.toolbar = self.iface.addToolBar("FLO-2D")
        self.toolbar.setObjectName("FLO-2D")
        self.con = None
        self.iface.f2d["con"] = self.con
        self.lyrs = Layers(iface)
        self.ilg = InvisibleLayersAndGroups(self.iface)
        self.lyrs.group = None
        self.gutils = None
        self.f2g = None
        self.prep_sql = None
        self.f2d_widget = None
        self.f2d_plot_dock = None
        self.f2d_table_dock = None
        self.f2d_dock = None
        self.f2d_grid_info_dock = None
        self.f2d_inlets_junctions_dock = None
        self.f2d_outlets_dock = None
        self.f2d_conduits_dock = None
        self.f2d_pumps_dock = None
        self.f2d_orifices_dock = None
        self.f2d_weirs_dock = None
        self.f2d_storage_units_dock = None
        self.create_map_tools()
        self.crs = None
        self.cur_info_table = None
        self.infoToolCalled = False
        self.new_gpkg = None

        # connections
        self.project.readProject.connect(self.load_gpkg_from_proj)
        self.project.writeProject.connect(self.flo_save_project)
        self.project.layersAdded.connect(self.layerAdded)
        self.project.layersWillBeRemoved.connect(self.change_external_layer_type)

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

        if not self.infoToolCalled:
            self.info_tool.feature_picked.connect(self.get_feature_info)
            self.infoToolCalled = True

        self.results_tool.feature_picked.connect(self.get_feature_profile)
        self.grid_info_tool.grid_elem_picked.connect(self.f2d_grid_info.update_fields)

        self.f2d_widget.grid_tools.setup_connection()

        self.f2d_widget.pre_processing_tools.setup_connection()

        self.f2d_widget.profile_tool.setup_connection()

        self.f2d_widget.rain_editor.setup_connection()
        self.f2d_widget.rain_editor.rain_properties()

        self.f2d_widget.bc_editor_new.setup_connection()
        self.f2d_widget.bc_editor_new.populate_bcs(widget_setup=True)

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

        self.f2d_widget.multiple_domains_editor.setup_connection()

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

        if text in ["FLO-2D Grid Info Tool", "FLO-2D Info Tool", "FLO-2D Results"]:
            action.setCheckable(True)
            action.setChecked(False)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:

            tool_button_mapping = {
                "FLO-2D Project": ("/img/mGeoPackage.svg", "<b>FLO-2D Project</b>"),
                "Run FLO-2D Pro": ("/img/flo2d.svg", "<b>Run FLO-2D Pro</b>"),
                "FLO-2D Import/Export": ("/img/ie.svg", "<b>FLO-2D Import/Export</b>"),
                "FLO-2D Project Review": ("/img/editmetadata.svg", "<b>FLO-2D Project Review</b>", True),
                "FLO-2D Parameters": ("/img/show_cont_table.svg", "<b>FLO-2D Parameters</b>")
            }

            if text in tool_button_mapping:
                toolButton = QToolButton()
                toolButton.setMenu(popup)
                toolButton.setIcon(QIcon(self.plugin_dir + tool_button_mapping[text][0]))
                toolButton.setPopupMode(QToolButton.InstantPopup)

                if len(tool_button_mapping[text]) >= 3 and tool_button_mapping[text][2]:
                    toolButton.setCheckable(True)

                self.toolbar.addWidget(toolButton)
                toolButton.setToolTip(tool_button_mapping[text][1])
                self.toolButtons.append(toolButton)
            else:
                self.toolbar.addAction(action)
                self.toolActions.append(action)

        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        self.actions.append(action)
        return action

    def initGui(self):
        """
        Create the menu entries and toolbar icons inside the QGIS GUI.
        """
        # global GRID_INFO, GENERAL_INFO

        self.add_action(
            os.path.join(self.plugin_dir, "img/mGeoPackage.svg"),
            text=self.tr("FLO-2D Project"),
            callback=None,
            parent=self.iface.mainWindow(),
            menu=(
                (
                    os.path.join(self.plugin_dir, "img/mActionNewGeoPackageLayer.svg"),
                    "New FLO-2D Project",
                    lambda: self.show_settings(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/mActionAddGeoPackageLayer.svg"),
                    "Open FLO-2D Project",
                    lambda: self.flo_open_project(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/gpkg_backup.svg"),
                    "Create FLO-2D Backup",
                    lambda: self.gpkg_backup(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/gpkg.svg"),
                    "FLO-2D GeoPackage Management",
                    lambda: self.gpkg_management(),
                )
            )
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/ie.svg"),
            text=self.tr("FLO-2D Import/Export"),
            callback=None,
            parent=self.iface.mainWindow(),
            menu=(
                (
                    os.path.join(self.plugin_dir, "img/import_gpkg.svg"),
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
                    os.path.join(self.plugin_dir, "img/import_hdf5.svg"),
                    "Import from HDF5",
                    lambda: self.import_hdf5(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/export_hdf5.svg"),
                    "Export to HDF5",
                    lambda: self.export_hdf5(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/import_swmm.svg"),
                    "Import from INP",
                    lambda: self.import_inp(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/export_swmm.svg"),
                    "Export to INP",
                    lambda: self.export_inp(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/import_multidomains.svg"),
                    "Import multiple domains",
                    lambda: self.import_multidomains(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/export_multidomains.svg"),
                    "Export multiple domains",
                    lambda: self.export_multidomains(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/import_ras.svg"),
                    "Import RAS geometry",
                    lambda: self.import_from_ras(),
                )
            )
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/flo2d.svg"),
            text=self.tr("Run FLO-2D Pro"),
            callback=None,
            parent=self.iface.mainWindow(),
            menu=(
                (
                    os.path.join(self.plugin_dir, "img/mActionOptions.svg"),
                    "FLO-2D Settings",
                    lambda: self.run_settings(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/flo2d.svg"),
                    "Quick Run FLO-2D Pro",
                    lambda: self.quick_run_flopro(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/FLO.svg"),
                    "Run FLO-2D Pro",
                    self.run_flopro,
                ),
                (
                    os.path.join(self.plugin_dir, "img/swmm5.png"),
                    "Run SWMM 5 GUI ",
                    self.run_swmm5_gui,
                ),
                (
                    os.path.join(self.plugin_dir, "img/tailings dam breach.svg"),
                    "Run Tailings Dam Tool ",
                    self.run_tailingsdambreach,
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
                    os.path.join(self.plugin_dir, "img/mapcrafter.svg"),
                    "Run MapCrafter",
                    self.run_mapcrafter,
                ),
                (
                    os.path.join(self.plugin_dir, "img/rasterizor.svg"),
                    "Run Rasterizor",
                    self.run_rasterizor,
                ),
            )
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/show_cont_table.svg"),
            text=self.tr("FLO-2D Parameters"),
            callback=None,
            parent=self.iface.mainWindow(),
            menu=(
                (
                    os.path.join(self.plugin_dir, "img/show_cont_table.svg"),
                    "Set Control Parameters (CONT.DAT)",
                    lambda: self.show_cont_toler(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/landslide.svg"),
                    "Mud and Sediment Transport (SED.DAT)",
                    lambda: self.show_mud_and_sediment_dialog(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/schematic_to_user.svg"),
                    "Convert Schematic Layers to User Layers",
                    lambda: self.schematic2user(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/evaporation_editor.svg"),
                    "Evaporation Editor",
                    lambda: self.show_evap_editor(),
                ),
                (
                    os.path.join(self.plugin_dir, "img/set_levee_elev.svg"),
                    "Levee Elevation Tool",
                    lambda: self.show_levee_elev_tool(),
                ),
            )
        )

        # self.add_action(
        #     os.path.join(self.plugin_dir, "img/info_tool.svg"),
        #     text=self.tr("FLO-2D Info Tool"),
        #     callback=None,
        #     parent=self.iface.mainWindow(),
        #     menu=(
        #         (
        #             os.path.join(self.plugin_dir, "img/info_tool.svg"),
        #             "Info Tool",
        #             lambda: self.activate_general_info_tool(),
        #         ),
        #         (
        #             os.path.join(self.plugin_dir, "img/import_swmm.svg"),
        #             "Select .RPT file",
        #             lambda: self.select_RPT_File(),
        #         ),
        #         # (
        #         #     os.path.join(self.plugin_dir, "img/grid_info_tool.svg"),
        #         #     "Grid Info Tool",
        #         #     lambda: self.activate_grid_info_tool(),
        #         # ),
        #     )
        # )

        self.add_action(
            os.path.join(self.plugin_dir, "img/grid_info_tool.svg"),
            text=self.tr("FLO-2D Grid Info Tool"),
            callback=lambda: self.activate_grid_info_tool(),
            parent=self.iface.mainWindow(),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/info_tool.svg"),
            text=self.tr("FLO-2D Info Tool"),
            callback=lambda: self.activate_general_info_tool(),
            parent=self.iface.mainWindow(),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/results.svg"),
            text=self.tr("FLO-2D Results"),
            callback=lambda: self.activate_results_info_tool(),
            parent=self.iface.mainWindow(),
        )

        self.add_action(
            os.path.join(self.plugin_dir, "img/editmetadata.svg"),
            text=self.tr("FLO-2D Project Review"),
            callback=None,
            parent=self.iface.mainWindow(),
            menu=(
                (
                    os.path.join(self.plugin_dir, "img/hazus.svg"),
                    "HAZUS",
                    lambda: self.show_hazus_dialog(),
                ),
                # (
                #     os.path.join(self.plugin_dir, "img/profile_tool.svg"),
                #     "Channel Profile",
                #     lambda: self.channel_profile(),
                # ),
                (
                    os.path.join(self.plugin_dir, "img/issue.svg"),
                    "Warnings and Errors",
                    lambda: self.show_errors_dialog(),
                ),
            )
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
        del self.info_tool, self.grid_info_tool, self.results_tool
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
            # if self.f2d_widget.bc_editor is not None:
            #     self.f2d_widget.bc_editor.close()
            #     del self.f2d_widget.bc_editor

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
        self.uncheck_all_info_tools()
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
            self.write_proj_entry("gpkg", gpkg_path_adj)
            self.setup_dock_widgets()
            s = QSettings()
            s.setValue("FLO-2D/last_flopro_project", os.path.dirname(gpkg_path_adj))
            s.setValue("FLO-2D/lastGdsDir", os.path.dirname(gpkg_path_adj))

            contact = dlg_settings.lineEdit_au.text()
            email = dlg_settings.lineEdit_co.text()
            company = dlg_settings.lineEdit_em.text()
            phone = dlg_settings.lineEdit_te.text()

            pn = dlg_settings.label_pn.text()
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

            uri = f'geopackage:{gpkg_path}?projectName={pn}'
            self.project.write(uri)

            self.uc.bar_info("Project sucessfully created!")
            self.uc.log_info("Project sucessfully created!")

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
            QApplication.setOverrideCursor(Qt.WaitCursor)
            s.setValue("FLO-2D/lastGpkgDir", os.path.dirname(gpkg_path))

            self.new_gpkg = gpkg_path
            proj_name = os.path.splitext(os.path.basename(gpkg_path))[0]
            uri = f'geopackage:{gpkg_path}?projectName={proj_name}'

            self.con = database_connect(gpkg_path)
            self.gutils = GeoPackageUtils(self.con, self.iface)

            if not self.gutils.check_gpkg_version():
                QApplication.restoreOverrideCursor()
                if self.uc.question("This GeoPackage is outdated. Would you like to update it?"):
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    # Create an updated geopackage and copy old package data to it
                    plugin_v = get_plugin_version()
                    original_base_path = gpkg_path[:-5]

                    # Check for the versioning pattern to avoid duplicating versions
                    pattern = r"_v\d+\.\d+\.\d+"
                    if re.search(pattern, original_base_path):
                        # Replace the existing version with the plugin version
                        base_path = re.sub(pattern, f"_v{plugin_v}", original_base_path)
                    else:
                        # Append the plugin version if no pattern is found
                        base_path = f"{original_base_path}_v{plugin_v}"

                    # Start with the base path + ".gpkg"
                    new_gpkg_path = f"{base_path}.gpkg"
                    counter = 1

                    # Regular expression to match files with counters in parentheses
                    counter_pattern = r" \((\d+)\)\.gpkg"

                    # Check for existing file paths and append a counter if necessary
                    while os.path.exists(new_gpkg_path):
                        # Check if the file name has a counter and extract the number
                        match = re.search(counter_pattern, new_gpkg_path)
                        if match:
                            current_counter = int(match.group(1)) + 1
                            new_gpkg_path = re.sub(counter_pattern, f" ({current_counter}).gpkg", new_gpkg_path)
                        else:
                            # If no counter is present, append the first counter
                            new_gpkg_path = f"{base_path} ({counter}).gpkg"
                        counter += 1

                    crs = QgsCoordinateReferenceSystem()
                    proj = self.gutils.get_grid_crs()
                    if proj:
                        crs.createFromUserInput(proj)
                    else:
                        proj = self.gutils.get_cont_par("PROJ")
                        crs.createFromProj(proj)
                    cell_size = self.gutils.grid_cell_size()
                    # create new geopackage TODO: This should be on the geopackage_utils and not on the settings
                    dlg_settings = SettingsDialog(self.con, self.iface, self.lyrs, self.gutils)
                    dlg_settings.create_db(new_gpkg_path, crs)
                    # disconnect from the outdated geopackage
                    database_disconnect(self.con)
                    # connect to the new geopackage
                    self.con = database_connect(new_gpkg_path)
                    self.gutils = GeoPackageUtils(self.con, self.iface)
                    dlg_update_gpkg = UpdateGpkg(self.con, self.iface)
                    dlg_update_gpkg.cellSizeDSpinBox.setValue(cell_size)
                    dlg_update_gpkg.show()
                    QApplication.restoreOverrideCursor()
                    result = dlg_update_gpkg.exec_()
                    if result:
                        QApplication.setOverrideCursor(Qt.WaitCursor)
                        dlg_update_gpkg.write()
                        dlg_settings.set_default_controls(
                            self.con)  # TODO: This should be on the geopackage_utils and not on the settings
                        self.gutils.copy_from_other(gpkg_path)
                        # Old gpkg used float values for CELLSIZE, need to explicitly convert it
                        cell_size = self.gutils.get_cont_par("CELLSIZE")
                        self.gutils.set_cont_par("CELLSIZE", int(float(cell_size)))
                        contact = dlg_update_gpkg.lineEdit_au.text()
                        email = dlg_update_gpkg.lineEdit_co.text()
                        company = dlg_update_gpkg.lineEdit_em.text()
                        phone = dlg_update_gpkg.lineEdit_te.text()
                        pn = dlg_update_gpkg.label_pn.text()
                        plugin_v = dlg_update_gpkg.label_pv.text()
                        qgis_v = dlg_update_gpkg.label_qv.text()
                        flo2d_v = dlg_update_gpkg.label_fv.text()
                        self.gutils.set_metadata_par("PROJ_NAME", pn)
                        self.gutils.set_metadata_par("CONTACT", contact)
                        self.gutils.set_metadata_par("EMAIL", email)
                        self.gutils.set_metadata_par("PHONE", phone)
                        self.gutils.set_metadata_par("COMPANY", company)
                        self.gutils.set_metadata_par("PLUGIN_V", plugin_v)
                        self.gutils.set_metadata_par("QGIS_V", qgis_v)
                        self.gutils.set_metadata_par("FLO-2D_V", flo2d_v)
                        self.gutils.set_metadata_par("CRS", crs.authid())
                        uri = f'geopackage:{new_gpkg_path}?projectName={os.path.splitext(os.path.basename(new_gpkg_path))[0]}'
                        gpkg_path = new_gpkg_path

                        # add ported external layers back into the project
                        gpkg_tables = self.gutils.current_gpkg_tables
                        tab_sql = """SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'gpkg_%' AND name NOT LIKE 'rtree_%';"""
                        tabs = [row[0] for row in self.gutils.execute(tab_sql)]
                        do_not_port = [
                            'sqlite_sequence',
                            'qgis_projects',
                            'infil_areas_scs',
                            'infil_areas_green',
                            'infil_areas_horton',
                            'rain_arf_areas',
                            'infil_areas_chan',
                        ]
                        for table in tabs:
                            if table not in gpkg_tables and table not in do_not_port:
                                try:
                                    ds = ogr.Open(gpkg_path)
                                    layer = ds.GetLayerByName(table)
                                    # Vector
                                    if layer.GetGeomType() != ogr.wkbNone:
                                        gpkg_uri = f"{gpkg_path}|layername={table}"
                                        gpkg_layer = QgsVectorLayer(gpkg_uri, table, "ogr")
                                        self.project.addMapLayer(gpkg_layer, False)
                                        root = self.project.layerTreeRoot()
                                        group_name = "External Layers"
                                        flo2d_name = f"FLO-2D_{self.gutils.get_metadata_par('PROJ_NAME')}"
                                        flo2d_grp = root.findGroup(flo2d_name)
                                        if flo2d_grp.findGroup(group_name):
                                            group = flo2d_grp.findGroup(group_name)
                                        else:
                                            group = flo2d_grp.insertGroup(-1, group_name)
                                        group.insertLayer(0, gpkg_layer)

                                        # Add information to the external_layers tab
                                        self.gutils.execute(
                                            f"INSERT INTO external_layers (name, type) VALUES ('{table}', 'external');")

                                        continue
                                except Exception as e:
                                    pass

                                try:
                                    raster_ds = gdal.Open(f"GPKG:{new_gpkg_path}:{table}", gdal.OF_READONLY)
                                    if raster_ds:
                                        gpkg_uri = f"GPKG:{gpkg_path}:{table}"
                                        gpkg_layer = QgsRasterLayer(gpkg_uri, table, "gdal")
                                        self.project.addMapLayer(gpkg_layer, False)
                                        root = self.project.layerTreeRoot()
                                        flo2d_name = f"FLO-2D_{self.gutils.get_metadata_par('PROJ_NAME')}"
                                        group_name = "External Layers"
                                        flo2d_grp = root.findGroup(flo2d_name)
                                        if flo2d_grp.findGroup(group_name):
                                            group = flo2d_grp.findGroup(group_name)
                                        else:
                                            group = flo2d_grp.insertGroup(-1, group_name)
                                        group.insertLayer(0, gpkg_layer)
                                        self.lyrs.collapse_flo2d_subgroup(flo2d_name, group_name)

                                        # Add information to the external_layers tab
                                        self.gutils.execute(
                                            f"INSERT INTO external_layers (name, type) VALUES ('{table}', 'external');")

                                except Exception as e:
                                    pass

                        QApplication.restoreOverrideCursor()
                else:
                    self.uc.log_info("Connection closed")
                    return False

            if not self.project.read(uri):

                QApplication.setOverrideCursor(Qt.WaitCursor)
                dlg_settings = SettingsDialog(self.con, self.iface, self.lyrs, self.gutils)
                if not dlg_settings.connect(gpkg_path):
                    return
                self.con = dlg_settings.con
                self.iface.f2d["con"] = self.con
                self.gutils = dlg_settings.gutils
                self.crs = QgsCoordinateReferenceSystem()
                proj = self.gutils.get_grid_crs()
                if proj:
                    self.crs.createFromUserInput(proj)
                else:
                    proj = self.gutils.get_cont_par("PROJ")
                    self.crs.createFromProj(proj)
                self.setup_dock_widgets()
                self.project.setCrs(self.crs)
                gpkg_path_adj = gpkg_path.replace("\\", "/")
                self.write_proj_entry("gpkg", gpkg_path_adj)
                # uri = f'geopackage:{gpkg_path_adj}?projectName={proj_name + "_v1.0.0"}'
                # # self.project.write(uri)
                self.iface.mainWindow().findChild(QAction, 'mActionSaveProject').trigger()
                QApplication.restoreOverrideCursor()
                self.uc.bar_info("Project created into the Geopackage!")
                self.uc.log_info("Project created into the Geopackage!")

            else:
                QApplication.restoreOverrideCursor()
                self.uc.bar_info("Project successfully loaded!")
                self.uc.log_info("Project successfully loaded!")

        finally:
            QApplication.restoreOverrideCursor()

    def flo_save_project(self):
        """
        Function to save a FLO-2D project into a geopackage
        """

        # QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            gpkg_path = self.gutils.get_gpkg_path()
        except AttributeError:
            return

        proj_name = os.path.splitext(os.path.basename(gpkg_path))[0]
        uri = f'geopackage:{gpkg_path}?projectName={proj_name}'

        layers = self.project.mapLayers()
        checked_layers = False
        not_added = []

        QApplication.setOverrideCursor(Qt.WaitCursor)
        for layer_id, layer in layers.items():
            if self.check_layer_source(layer, gpkg_path):
                if not checked_layers:
                    msg = f"External layers were added to the project.\n\n"
                    msg += "Click Yes to save the external data to the GeoPackage.\n"
                    msg += "    Yes results in a larger GeoPackage, but eliminates the need to reconnect data paths.\n\n"
                    msg += "Click No to save the external paths to the GeoPackage.\n"
                    msg += "    No is faster and has a smaller GeoPackage, but if the paths change, the external data must be reloaded."
                    QApplication.restoreOverrideCursor()
                    answer = self.uc.customized_question("FLO-2D", msg)
                    dlg_gpkg_management = GpkgManagementDialog(self.iface, self.lyrs, self.gutils)
                    if answer == QMessageBox.Yes:
                        dlg_gpkg_management.show()
                        while True:
                            ok = dlg_gpkg_management.exec_()
                            if ok:
                                QApplication.setOverrideCursor(Qt.WaitCursor)
                                dlg_gpkg_management.save_layers()
                                QApplication.restoreOverrideCursor()
                                return
                            else:
                                return

                    elif answer == QMessageBox.No:
                        QApplication.setOverrideCursor(Qt.WaitCursor)
                        dlg_gpkg_management.populate_user_lyrs()
                        dlg_gpkg_management.save_layers()
                        QApplication.restoreOverrideCursor()
                        return
                    else:
                        QApplication.restoreOverrideCursor()
                        break

        QApplication.restoreOverrideCursor()

        self.uc.bar_info("Project saved!")
        self.uc.log_info("Project saved!")

    @connection_required
    def gpkg_management(self):
        """
        Function to run the GeoPackage Management
        """
        self.uncheck_all_info_tools()
        self.dlg_gpkg_management = GpkgManagementDialog(self.iface, self.lyrs, self.gutils)
        self.dlg_gpkg_management.show()

    @connection_required
    def gpkg_backup(self):
        """
        Function to create a geopackage backup
        """
        self.dlg_gpkg_backup = GpkgBackupDialog(self.iface, self.gutils)
        self.dlg_gpkg_backup.show()

    def run_settings(self):
        """
        Function to set the run settings: FLO-2D and Project folders
        """
        self.uncheck_all_info_tools()
        dlg = ExternalProgramFLO2D(self.iface, "Run Settings")
        dlg.exec_folder_lbl.setText("FLO-2D Folder")
        ok = dlg.exec_()
        if not ok:
            return
        else:

            flopro_found = False

            # Project is loaded
            if self.gutils:
                flo2d_dir, project_dir, advanced_layers = dlg.get_parameters()
                s = QSettings()
                s.setValue("FLO-2D/lastGdsDir", project_dir)
                s.setValue("FLO-2D/last_flopro", flo2d_dir)
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
                flo2d_dir, project_dir, _ = dlg.get_parameters()
                s = QSettings()
                s.setValue("FLO-2D/lastGdsDir", project_dir)
                s.setValue("FLO-2D/last_flopro", flo2d_dir)

                if project_dir != "" and flo2d_dir != "":
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

    @connection_required
    def quick_run_flopro(self):
        """
        Function to export and run FLO-2D Pro
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            self.uc.log_info("There is no grid! Please create it before running tool.")
            return

        s = QSettings()
        project_dir = s.value("FLO-2D/lastGdsDir")
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
                "export_outrc",
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
                "export_steep_slopen",
                "export_lid_volume",
                "export_swmmflo",
                "export_swmmflort",
                "export_swmmoutf",
                "export_swmmflodropbox",
                "export_sdclogging",
                "export_wsurf",
                "export_wstime",
                "export_shallowNSpatial",
                "export_mannings_n_topo",
            ]

            s.setValue("FLO-2D/lastGdsDir", outdir)

            dlg_components = ComponentsDialog(self.con, self.iface, self.lyrs, "out")

            # Check the presence of fplain cadpts neighbors dat files
            files = [
                "FPLAIN.DAT",
                "CADPTS.DAT",
                "NEIGHBORS.DAT"
            ]
            for file in files:
                file_path = os.path.join(outdir, file)
                if os.path.exists(file_path):
                    dlg_components.remove_files_chbox.setEnabled(True)
                    break

            ok = dlg_components.exec_()
            if ok:
                if dlg_components.remove_files_chbox.isChecked():
                    for file in files:
                        file_path = os.path.join(outdir, file)
                        if os.path.exists(file_path):
                            os.remove(file_path)

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

                if "Surface Water Rating Tables" not in dlg_components.components:
                    export_calls.remove("export_outrc")

                if "Tailings" not in dlg_components.components:
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
                    export_calls.remove("export_swmmflodropbox")
                    export_calls.remove("export_sdclogging")

                if "Spatial Shallow-n" not in dlg_components.components:
                    export_calls.remove("export_shallowNSpatial")

                if "Spatial Tolerance" not in dlg_components.components:
                    export_calls.remove("export_tolspatial")

                if "Spatial Froude" not in dlg_components.components:
                    export_calls.remove("export_fpfroude")

                if "Manning's n and Topo" not in dlg_components.components:
                    export_calls.remove("export_mannings_n_topo")

                if "Spatial Steep Slope-n" not in dlg_components.components:
                    export_calls.remove("export_steep_slopen")

                if "LID Volume" not in dlg_components.components:
                    export_calls.remove("export_lid_volume")

                try:

                    QApplication.setOverrideCursor(Qt.WaitCursor)

                    s = QSettings()
                    s.setValue("FLO-2D/lastGdsDir", outdir)

                    self.call_IO_methods(export_calls, True, outdir)

                    # The strings list 'export_calls', contains the names of
                    # the methods in the class Flo2dGeoPackage to export (write) the
                    # FLO-2D .DAT files

                    self.uc.bar_info("Project exported to " + outdir, dur=3)
                    self.uc.log_info("Project exported to " + outdir)

                finally:

                    if "export_tailings" in export_calls:
                        MUD = self.gutils.get_cont_par("MUD")
                        concentration_sql = """SELECT 
                                               CASE WHEN COUNT(*) > 0 THEN True
                                                    ELSE False
                                               END AS result
                                               FROM 
                                                   tailing_cells
                                               WHERE 
                                                   concentration <> 0 OR concentration IS NULL;"""
                        cv = self.gutils.execute(concentration_sql).fetchone()[0]
                        # TAILINGS.DAT and TAILINGS_CV.DAT
                        if MUD == '1':
                            # Export TAILINGS_CV.DAT
                            if cv == 1:
                                new_files_used = self.files_used.replace("TAILINGS.DAT\n", "TAILINGS_CV.DAT\n")
                                self.files_used = new_files_used
                        # TAILINGS_STACK_DEPTH.DAT
                        elif MUD == '2':
                            new_files_used = self.files_used.replace("TAILINGS.DAT\n", "TAILINGS_STACK_DEPTH.DAT\n")
                            self.files_used = new_files_used

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

            else:
                return

            flopro_dir = s.value("FLO-2D/last_flopro")
            flo2d_v = "FLOPRO not found"
            program = None
            if flopro_dir is not None:
                # Check for FLOPRO.exe
                if os.path.isfile(flopro_dir + "/FLOPRO.exe"):
                    flo2d_v = get_flo2dpro_version(flopro_dir + "/FLOPRO.exe")
                    self.gutils.set_metadata_par("FLO-2D_V", flo2d_v)
                    program = "FLOPRO.exe"
                # Check for FLOPRO_Demo.exe
                elif os.path.isfile(flopro_dir + "/FLOPRO_Demo.exe"):
                    flo2d_v = get_flo2dpro_version(flopro_dir + "/FLOPRO_Demo.exe")
                    self.gutils.set_metadata_par("FLO-2D_V", flo2d_v)
                    program = "FLOPRO_Demo.exe"
            else:
                self.run_settings()

            if program:
                self.uc.bar_info(f"Running {program}...")
                self.uc.log_info(f"Running {program}...")
                self.run_program(program)
            else:
                self.uc.bar_warn("No FLOPRO.exe found, check your FLO-2D installation folder!")
                self.uc.log_info("No FLOPRO.exe found, check your FLO-2D installation folder!")

            QApplication.restoreOverrideCursor()

    def run_flopro(self):
        self.uncheck_all_info_tools()
        s = QSettings()
        flopro_dir = s.value("FLO-2D/last_flopro")
        flo2d_v = "FLOPRO not found"
        user_program = None
        # Check if the FLOPRO directory is in the FLO-2D Settings
        if flopro_dir is not None:
            # Check if the user has the FLOPRO version
            if os.path.isfile(flopro_dir + "/FLOPRO.exe"):
                flo2d_v = get_flo2dpro_version(flopro_dir + "/FLOPRO.exe")
                user_program = "FLOPRO.exe"
            # Check for the FLOPRO_Demo
            elif os.path.isfile(flopro_dir + "/FLOPRO_Demo.exe"):
                flo2d_v = get_flo2dpro_version(flopro_dir + "/FLOPRO_Demo.exe")
                user_program = "FLOPRO_Demo.exe"

            # Only add to metadata if there is a project loaded, otherwise just run FLOPRO
            if self.gutils:
                self.gutils.set_metadata_par("FLO-2D_V", flo2d_v)
        else:
            self.run_settings()

        if user_program:
            self.uc.bar_info(f"Running {user_program}...")
            self.uc.log_info(f"Running {user_program}...")
            self.run_program(user_program)
        else:
            self.uc.bar_warn("No FLOPRO.exe found, check your FLO-2D installation folder!")
            self.uc.log_info("No FLOPRO.exe found, check your FLO-2D installation folder!")

    def run_swmm5gui(self):
        self.uncheck_all_info_tools()
        self.run_program("Epaswmm5.exe")

    def run_tailingsdambreach(self):
        self.uncheck_all_info_tools()
        self.run_program("Tailings Dam Breach.exe")

    def run_mapcrafter(self):
        """
        Function to call MapCrafter
        """
        self.uncheck_all_info_tools()
        if 'flo2d_mapcrafter' not in plugins:
            self.uc.show_info(
                "FLO-2D MapCrafter not found! Please, use QGIS Official Plugin Repository to install MapCrafter.")
        else:
            mapcrafter = plugins['flo2d_mapcrafter']
            mapcrafter.open()

    def run_rasterizor(self):
        """
        Function to call Rasterizor
        """
        self.uncheck_all_info_tools()
        if 'rasterizor' not in plugins:
            self.uc.show_info(
                "FLO-2D Rasterizor not found! Please, use QGIS Official Plugin Repository to install Rasterizor.")
        else:
            rasterizor = plugins['rasterizor']
            rasterizor.open()

    def run_profiles(self):
        self.uncheck_all_info_tools()

        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")

        # Check if CHAN.DAT exists in the last_dir
        chan_file = os.path.join(last_dir, "CHAN.DAT")
        if not os.path.exists(chan_file):
            self.uc.bar_warn("CHAN.DAT file is missing in the directory: " + last_dir)
            self.uc.log_info("CHAN.DAT file is missing in the directory: " + last_dir)
            return

        self.run_program("PROFILES.exe")

    def run_hydrog(self):
        self.uncheck_all_info_tools()

        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")

        # Check if CHAN.DAT exists in the last_dir
        summary_file = os.path.join(last_dir, "SUMMARY.OUT")
        if not os.path.exists(summary_file):
            self.uc.bar_warn("SUMMARY.OUT file is missing in the directory: " + last_dir)
            self.uc.log_info("SUMMARY.OUT file is missing in the directory: " + last_dir)
            return

        self.run_program("HYDROG.exe")

    def run_maxplot(self):
        self.uncheck_all_info_tools()

        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")

        # Check if CHAN.DAT exists in the last_dir
        cadpts_file = os.path.join(last_dir, "CADPTS.DAT")
        if not os.path.exists(cadpts_file):
            self.uc.bar_warn("CADPTS.DAT file is missing in the directory: " + last_dir)
            self.uc.log_info("CADPTS.DAT file is missing in the directory: " + last_dir)
            return

        self.run_program("MAXPLOT.exe")

    def run_swmm5_gui(self):
        """
        Function to run the SWMM 5 GUI
        """
        self.uncheck_all_info_tools()
        s = QSettings()
        # check if run was configured
        if not s.contains("FLO-2D/run_settings"):
            self.run_settings()
        if s.value("FLO-2D/last_flopro") == "" or s.value("FLO-2D/lastGdsDir") == "":
            self.run_settings()
        flo2d_dir = s.value("FLO-2D/last_flopro")
        project_dir = s.value("FLO-2D/lastGdsDir")

        if sys.platform != "win32":
            self.uc.bar_warn("Could not run Epaswmm5.exe under current operation system!")
            return
        try:
            # Try to run from FLO-2D folder
            if os.path.isfile(flo2d_dir + '\\Epaswmm5.exe'):
                program = ProgramExecutor(flo2d_dir, project_dir, 'Epaswmm5.exe')
                program.perform()
                self.uc.bar_info("Epaswmm5.exe started!", dur=3)
                self.uc.log_info("Epaswmm5.exe started!")
            # Try to run from EPA SWMM 5 folder
            elif os.path.isfile(rf'C:\Program Files (x86)\EPA SWMM 5.0\Epaswmm5.exe'):
                program = ProgramExecutor(r'C:\Program Files (x86)\EPA SWMM 5.0', project_dir, 'Epaswmm5.exe')
                program.perform()
                self.uc.bar_info("Epaswmm5.exe started!", dur=3)
                self.uc.log_info("Epaswmm5.exe started!")
            # Executable not available
            else:
                self.uc.bar_warn("WARNING 241020.0424: Program Epaswmm5.exe is not in directory")
                self.uc.log_info("WARNING 241020.0424: Program Epaswmm5.exe is not in directory\n"
                                 + flo2d_dir
                                 + '\nor\n'
                                 + rf'C:\Program Files (x86)\EPA SWMM 5.0\Epaswmm5.exe')
        except Exception as e:
            self.uc.log_info(repr(e))
            self.uc.bar_warn("Running Epaswmm5.exe failed!")

    def run_program(self, exe_name):
        """
        Function to run programs
        """
        self.uncheck_all_info_tools()
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
                    self.uc.log_info(exe_name + " started!")
                else:
                    if os.path.isfile(project_dir + "\\" + "CONT.DAT"):
                        program = ProgramExecutor(flo2d_dir, project_dir, exe_name)
                        program.perform()
                        self.uc.bar_info(exe_name + " started!", dur=3)
                        self.uc.log_info(exe_name + " started!")
                    else:
                        self.uc.show_warn(
                            "CONT.DAT is not in directory:\n\n" + f"{project_dir}\n\n" + f"Select the correct directory.")
                        self.uc.log_info(
                            "CONT.DAT is not in directory:\n\n" + f"{project_dir}\n\n" + f"Select the correct directory.")
                        self.run_settings()
            else:
                self.uc.show_warn("WARNING 241020.0424: Program " + exe_name + " is not in directory\n\n" + flo2d_dir)
                self.uc.log_info("WARNING 241020.0424: Program " + exe_name + " is not in directory\n\n" + flo2d_dir)
        except Exception as e:
            self.uc.log_info(repr(e))
            self.uc.bar_warn("Running " + exe_name + " failed!")

    def select_RPT_File(self):
        self.uncheck_all_info_tools()

        grid = self.lyrs.data["grid"]["qlyr"]
        if grid is not None:
            if self.f2d_widget.storm_drain_editor.create_SD_discharge_table_and_plots("Just assign FLO-2D settings"):
                self.canvas.setMapTool(self.info_tool)
        else:
            self.uc.bar_warn("There is no grid layer to identify.")

    def load_gpkg_from_proj(self):
        """
        If QGIS project has a gpkg path saved ask user if it should be loaded.
        """
        old_gpkg = self.read_proj_entry("gpkg")
        if not old_gpkg:
            return
        if '%20' in old_gpkg:
            old_gpkg = old_gpkg.replace('%20', ' ')
        new_gpkg = self.new_gpkg

        qgs_file = QgsProject.instance().fileName()
        qgs_dir = os.path.dirname(qgs_file)

        # File adjustment from loading recent projects
        if new_gpkg is None:
            uri = self.project.fileName()
            if uri.startswith("geopackage:"):
                new_gpkg = uri[len("geopackage:"):].split('?')[0]
            else:
                QApplication.restoreOverrideCursor()
                msg = ("<b>It looks like you're trying to open an old FLO-2D geopackage or FLO-2D *.qgz project.</b><br><br>"
                          "Please use the 'Open FLO-2D Project' option on the toolbar to port your project to the new format. This process will not damage your old project.<br><br>"
                          "<a href='https://documentation.flo-2d.com/Plugin1000/toolbar/flo-2d-project/Open%20FLO-2D%20Project.html'>Open Project Instructions</a><br>"
                          "<a href='https://flo-2d.com/contact'>Tech Support</a>"
                )
                self.uc.show_warn(msg)
                self.uc.log_info(msg)
                return

        if '%20' in new_gpkg:
            new_gpkg = new_gpkg.replace('%20', ' ')

        self.con = database_connect(new_gpkg)
        self.gutils = GeoPackageUtils(self.con, self.iface)

        if not self.gutils.check_gpkg_version():
            QApplication.restoreOverrideCursor()
            msg = (
                "<b>It looks like you're trying to open an old FLO-2D geopackage or FLO-2D *.qgz project.</b><br><br>"
                "Please use the 'Open FLO-2D Project' option on the toolbar to port your project to the new format. This process will not damage your old project.<br><br>"
                "<a href='https://documentation.flo-2d.com/Plugin1000/toolbar/flo-2d-project/Open%20FLO-2D%20Project.html'>Open Project Instructions</a><br>"
                "<a href='https://flo-2d.com/contact'>Tech Support</a>"
                )
            self.uc.show_warn(msg)
            self.uc.log_info(msg)
            return

        # Geopackage associated with the project
        if old_gpkg:
            # Check if opening gpkg (new_gpkg) is the same as the project gpkg (old_gpkg)
            # Project gpkg is the same as the gpkg being opened or gpkg being opened is None (load from recent projects)
            if old_gpkg == new_gpkg:
                msg = f"This QGIS project uses the FLO-2D Plugin and the following database file:\n\n{old_gpkg}\n\n"
                # Geopackage does not exist at original path
                if not os.path.exists(old_gpkg):
                    msg += "Unfortunately it seems that database file doesn't exist at given location."
                    gpkg_dir, gpkg_file = os.path.split(old_gpkg)
                    _old_gpkg = os.path.join(qgs_dir, gpkg_file)
                    if os.path.exists(_old_gpkg):
                        msg += f" However there is a file with the same name at your project location:\n\n{_old_gpkg}\n\n"
                        msg += "Load the model?"
                        old_gpkg = _old_gpkg
                        QApplication.restoreOverrideCursor()
                        answer = self.uc.customized_question("FLO-2D", msg)
                    else:

                        answer = self.uc.customized_question("FLO-2D", msg, QMessageBox.Cancel, QMessageBox.Cancel)
                # Geopackage exists at the original path
                else:
                    msg += "Load the model?"
                    QApplication.restoreOverrideCursor()
                    answer = self.uc.customized_question("FLO-2D", msg)
                if answer == QMessageBox.Yes:
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    qApp.processEvents()
                    dlg_settings = SettingsDialog(self.con, self.iface, self.lyrs, self.gutils)
                    if not dlg_settings.connect(old_gpkg):
                        return
                    self.con = dlg_settings.con
                    self.iface.f2d["con"] = self.con
                    self.gutils = dlg_settings.gutils
                    self.crs = dlg_settings.crs
                    self.setup_dock_widgets()

                    s = QSettings()
                    s.setValue("FLO-2D/last_flopro_project", qgs_file)
                    s.setValue("FLO-2D/lastGdsDir", os.path.dirname(old_gpkg))
                    window_title = s.value("FLO-2D/last_flopro_project", "")
                    self.iface.mainWindow().setWindowTitle(window_title)
                    QApplication.restoreOverrideCursor()
                else:
                    return
            # Project gpkg is not the same as the gpkg being opened
            else:
                msg = f"This QGIS project uses the FLO-2D Plugin and the following database file:\n\n{new_gpkg}\n\n"
                # Geopackage exists at the original path
                msg += "Load the model?"
                QApplication.restoreOverrideCursor()
                answer = self.uc.customized_question("FLO-2D", msg)
                if answer == QMessageBox.Yes:
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    qApp.processEvents()
                    dlg_settings = SettingsDialog(self.con, self.iface, self.lyrs, self.gutils)
                    if not dlg_settings.connect(new_gpkg):
                        return
                    self.con = dlg_settings.con
                    self.iface.f2d["con"] = self.con
                    self.gutils = dlg_settings.gutils
                    self.crs = dlg_settings.crs
                    self.setup_dock_widgets()

                    s = QSettings()
                    s.setValue("FLO-2D/last_flopro_project", qgs_file)
                    s.setValue("FLO-2D/lastGdsDir", os.path.dirname(new_gpkg))
                    window_title = s.value("FLO-2D/last_flopro_project", "")
                    self.iface.mainWindow().setWindowTitle(window_title)
                    QApplication.restoreOverrideCursor()
                else:
                    return

        # Geopackage not associated with the project -> This is not going to happen in the future because the project
        # is now located inside the geopackage
        else:
            msg = f"This QGIS project uses the FLO-2D Plugin but does not have a database associated.\n\n"
            msg += "Would you like to load the geopackage?"
            QApplication.restoreOverrideCursor()
            answer = self.uc.customized_question("FLO-2D", msg)
            if answer == QMessageBox.Yes:
                s = QSettings()
                last_gpkg_dir = s.value("FLO-2D/lastGpkgDir", "")
                gpkg_path, __ = QFileDialog.getOpenFileName(
                    None,
                    "Select GeoPackage to connect",
                    directory=last_gpkg_dir,
                    filter="*.gpkg",
                )
                if not gpkg_path:
                    return

                self.new_gpkg = gpkg_path
                QApplication.setOverrideCursor(Qt.WaitCursor)
                qApp.processEvents()
                dlg_settings = SettingsDialog(self.con, self.iface, self.lyrs, self.gutils)
                if not dlg_settings.connect(new_gpkg):
                    return
                self.con = dlg_settings.con
                self.iface.f2d["con"] = self.con
                self.gutils = dlg_settings.gutils
                self.crs = dlg_settings.crs
                self.setup_dock_widgets()

                s = QSettings()
                s.setValue("FLO-2D/last_flopro_project", qgs_file)
                s.setValue("FLO-2D/lastGdsDir", os.path.dirname(new_gpkg))
                window_title = s.value("FLO-2D/last_flopro_project", "")
                self.iface.mainWindow().setWindowTitle(window_title)
                QApplication.restoreOverrideCursor()

        # gpkg_path = self.gutils.get_gpkg_path()
        # proj_name = os.path.splitext(os.path.basename(gpkg_path))[0]
        # uri = f'geopackage:{gpkg_path}?projectName={proj_name}'
        # self.project.write(uri)

    def call_IO_methods(self, calls, debug, *args):
        if self.f2g.parsed_format == Flo2dGeoPackage.FORMAT_DAT:
            self.call_IO_methods_dat(calls, debug, *args)
        elif self.f2g.parsed_format == Flo2dGeoPackage.FORMAT_HDF5:
            self.call_IO_methods_hdf5(calls, debug, *args)

    def call_IO_methods_hdf5(self, calls, debug, *args):
        self.f2g.parser.write_mode = "w"

        progDialog = QProgressDialog("Exporting to HDF5...", None, 0, len(calls))
        progDialog.setModal(True)
        progDialog.setValue(0)
        progDialog.show()
        i = 0

        for call in calls:
            i += 1
            progDialog.setValue(i)
            progDialog.setLabelText(call)
            QApplication.processEvents()
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

        QApplication.setOverrideCursor(Qt.WaitCursor)
        for call in calls:
            if call == "export_bridge_xsec":
                dat = "BRIDGE_XSEC.DAT"
            elif call == "export_bridge_coeff_data":
                dat = "BRIDGE_COEFF_DATA.DAT"
            elif call == "import_hystruc_bridge_xs":
                dat = "BRIDGE_XSEC.DAT"
            elif call == "import_swmminp":
                dat = "SWMM.INP"
            elif call == 'export_steep_slopen':
                dat = "STEEP_SLOPEN.DAT"
            elif call == 'import_steep_slopen':
                dat = "STEEP_SLOPEN.DAT"
            elif call == 'export_lid_volume':
                dat = "LID_VOLUME.DAT"
            elif call == 'import_lid_volume':
                dat = "LID_VOLUME.DAT"
            elif call == 'import_shallowNSpatial':
                dat = "SHALLOWN_SPATIAL.DAT"
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

        QApplication.restoreOverrideCursor()

    @connection_required
    def import_gds(self):
        """
        Import traditional GDS files into FLO-2D database (GeoPackage).
        """
        self.uncheck_all_info_tools()
        self.gutils.disable_geom_triggers()
        self.f2g = Flo2dGeoPackage(self.con, self.iface)
        import_calls = [
            "import_cont_toler",
            "import_mannings_n_topo",
            "import_inflow",
            "import_tailings",
            # "import_outrc",  Add back when the OUTRC process is completed
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
            "import_steep_slopen",
            "import_lid_volume",
            "import_shallowNSpatial",
            "import_swmminp",
            "import_swmmflo",
            "import_swmmflort",
            "import_swmmoutf",
            "import_swmmflodropbox",
            "import_sdclogging",
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
            self.uc.bar_info("Import cancelled!")
            self.uc.log_info("Import cancelled!")
            self.gutils.enable_geom_triggers()
            return
        dir_name = os.path.dirname(fname)
        s.setValue("FLO-2D/lastGdsDir", dir_name)
        bname = os.path.basename(fname)
        if self.f2g.set_parser(fname):
            topo = self.f2g.parser.dat_files["TOPO.DAT"]
            if topo is None:
                self.uc.bar_error("Could not find TOPO.DAT file! Importing GDS files aborted!", dur=3)
                self.uc.log_info("Could not find TOPO.DAT file! Importing GDS files aborted!")
                self.gutils.enable_geom_triggers()
                return
            if bname not in self.f2g.parser.dat_files:
                self.uc.bar_info("Import cancelled!")
                self.uc.log_info("Import cancelled!")
                self.gutils.enable_geom_triggers()
                return
            empty = self.f2g.is_table_empty("grid")
            # check if a grid exists in the grid table
            if not empty:
                q = "There is a grid already defined in GeoPackage. Overwrite it?"
                if self.uc.question(q):
                    pass
                else:
                    self.uc.bar_info("Import cancelled!", dur=3)
                    self.uc.log_info("Import cancelled!")
                    self.gutils.enable_geom_triggers()
                    return

            # Check if MANNINGS_N.DAT exist:
            if not os.path.isfile(dir_name + r"\MANNINGS_N.DAT") or os.path.getsize(dir_name + r"\MANNINGS_N.DAT") == 0:
                self.uc.bar_error("ERROR 241019.1821: file MANNINGS_N.DAT is missing or empty!")
                self.uc.log_info("ERROR 241019.1821: file MANNINGS_N.DAT is missing or empty!")
                self.gutils.enable_geom_triggers()
                return

            # Check if TOLER.DAT exist:
            if not os.path.isfile(dir_name + r"\TOLER.DAT") or os.path.getsize(dir_name + r"\TOLER.DAT") == 0:
                self.uc.bar_error("ERROR 200322.0911: file TOLER.DAT is missing or empty!")
                self.uc.log_info("ERROR 200322.0911: file TOLER.DAT is missing or empty!")
                self.gutils.enable_geom_triggers()
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

                    # if "Surface Water Rating Tables" not in dlg_components.components: Add back when OUTRC is completed
                    #     import_calls.remove("import_outrc")

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

                    if "Rain" not in dlg_components.components:
                        import_calls.remove("import_rain")
                        import_calls.remove("import_raincell")

                    if "Storm Drain" not in dlg_components.components:
                        import_calls.remove("import_swmminp")
                        import_calls.remove("import_swmmflo")
                        import_calls.remove("import_swmmflort")
                        import_calls.remove("import_swmmoutf")
                        import_calls.remove("import_swmmflodropbox")
                        import_calls.remove("import_sdclogging")

                    if "Spatial Tolerance" not in dlg_components.components:
                        import_calls.remove("import_tolspatial")

                    if "Spatial Froude" not in dlg_components.components:
                        import_calls.remove("import_fpfroude")

                    if "Spatial Steep Slope-n" not in dlg_components.components:
                        import_calls.remove("import_steep_slopen")

                    if "LID Volume" not in dlg_components.components:
                        import_calls.remove("import_lid_volume")

                    if "Spatial Shallow-n" not in dlg_components.components:
                        import_calls.remove("import_shallowNSpatial")

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
                        "lid_volume_cells"
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
                        "steep_slope_n_cells",
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
                        "swmmflo_culvert",
                        "swmm_inflows",
                        "swmm_inflow_patterns",
                        "swmm_time_series",
                        "swmm_time_series_data",
                        "swmm_tidal_curve",
                        "swmm_tidal_curve_data",
                        "swmm_pumps_curve_data",
                        "swmm_other_curves",
                        "tailing_reservoirs",
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
                        "user_lid_volume_areas",
                        "user_model_boundary",
                        "user_noexchange_chan_areas",
                        "user_reservoirs",
                        "user_right_bank",
                        "user_roughness",
                        "user_steep_slope_n_areas",
                        "user_streets",
                        "user_struct",
                        "user_swmm_conduits",
                        "user_swmm_pumps",
                        "user_swmm_orifices",
                        "user_swmm_weirs",
                        "user_swmm_inlets_junctions",
                        "user_swmm_outlets",
                        "user_swmm_storage_units",
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

                    # Save CRS to table cont
                    self.gutils.set_cont_par("PROJ", self.crs.toProj())

                    # load layers and tables
                    self.load_layers()
                    self.uc.bar_info("Project successfully imported!", dur=3)
                    self.uc.log_info("Project successfully imported!")
                    self.gutils.enable_geom_triggers()

                    if "import_chan" in import_calls:
                        self.gutils.create_schematized_rbank_lines_from_xs_tips()

                    self.setup_dock_widgets()
                    self.lyrs.refresh_layers()
                    self.lyrs.zoom_to_all()

                    QApplication.restoreOverrideCursor()

                    # See if geopackage has grid with 'col' and 'row' fields:
                    grid_lyr = self.lyrs.data["grid"]["qlyr"]
                    field_index = grid_lyr.fields().indexFromName("col")
                    if field_index == -1:

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
                            proceed = self.uc.question(
                                "Grid layer's fields 'col' and 'row' have NULL values!\n\nWould you like to assign them?"
                            )
                            if proceed:
                                assign_col_row_indexes_to_grid(self.lyrs.data["grid"]["qlyr"], self.gutils)

                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 050521.0349: importing .DAT files!.\n", e)
                    self.uc.log_info(f"ERROR 050521.0349: importing .DAT files!.\n{e}")
                finally:
                    if self.files_used != "" or self.files_not_used != "":
                        msg = (
                            "Files read by this project:\n\n"
                            + self.files_used
                            + (
                                ""
                                if self.files_not_used == ""
                                else "\n\nFiles not found or empty:\n\n" + self.files_not_used
                            )
                        )
                        self.uc.show_info(msg)
                        self.uc.log_info(msg)

                    # Check the imported components on the schema2user
                    specific_components = []

                    # Boundary Conditions
                    if "import_inflow" in import_calls or "import_outflow" in import_calls or "import_tailings" in import_calls:
                        specific_components.append(2)

                    if "import_chan" in import_calls or "import_xsec" in import_calls:
                        specific_components.append(3)

                    if "import_hystruc" in import_calls or "import_hystruc_bridge_xs" in import_calls:
                        specific_components.append(7)

                    if "import_levee" in import_calls:
                        specific_components.append(4)

                    if "import_fpxsec" in import_calls:
                        specific_components.append(5)

                    if "import_mannings_n_topo" in import_calls:
                        specific_components.append(1)

                    if len(specific_components) > 0:
                        msg = "To complete the user layer functionality, use the <FONT COLOR=black>Convert Schematic " \
                              "Layers to User Layers</FONT> tool in the FLO-2D panel."
                        self.uc.show_info(msg)
                        self.schematic2user(True)

            # Update the lastGdsDir to the original
            s.setValue("FLO-2D/lastGdsDir", last_dir)
            self.gutils.enable_geom_triggers()
        else:
            self.gutils.enable_geom_triggers()

    @connection_required
    def import_hdf5(self):
        """
        Import HDF5 datasets into FLO-2D database (GeoPackage).
        """
        self.uncheck_all_info_tools()
        self.gutils.disable_geom_triggers()
        import_calls = [
            "import_cont_toler",
            "import_mannings_n_topo",
            "import_tolspatial",
            "import_inflow",
            "import_tailings",
            # "import_outrc",
            "import_outflow",
            "import_rain",
            # "import_raincell",
            # "import_evapor",
            "import_infil",
            "import_chan",
            "import_xsec",
            # "import_hystruc",
            # "import_hystruc_bridge_xs",
            # "import_street",
            "import_arf",
            # "import_mult",
            # "import_sed",
            # "import_levee",
            # "import_fpxsec",
            # "import_breach",
            # "import_gutter",
            # "import_fpfroude",
            # "import_steep_slopen",
            # "import_shallowNSpatial",
            # "import_lid_volume",
            # "import_swmminp",
            # "import_swmmflo",
            # "import_swmmflort",
            # "import_swmmoutf",
            # "import_swmmflodropbox",
            # "import_sdclogging",
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
            self.uc.bar_info("Import cancelled!")
            self.uc.log_info("Import cancelled!")
            self.gutils.enable_geom_triggers()
            return
        indir = os.path.dirname(input_hdf5)
        s = QSettings()
        s.setValue("FLO-2D/lastGdsDir", indir)
        self.f2g = Flo2dGeoPackage(self.con, self.iface, parsed_format=Flo2dGeoPackage.FORMAT_HDF5)
        self.f2g.set_parser(input_hdf5)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        empty = self.f2g.is_table_empty("grid")
        if not empty:
            QApplication.restoreOverrideCursor()
            q = "There is a grid already defined in GeoPackage. Overwrite it?"
            if self.uc.question(q):
                pass
            else:
                self.uc.bar_info("Import cancelled!", dur=3)
                self.uc.log_info("Import cancelled!")
                self.gutils.enable_geom_triggers()
                return

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
            "lid_volume_cells",
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
            "tailing_reservoirs",
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
            "user_lid_volume_areas",
            "user_model_boundary",
            "user_noexchange_chan_areas",
            "user_reservoirs",
            "user_right_bank",
            "user_roughness",
            "user_streets",
            "user_struct",
            "user_swmm_conduits",
            "user_swmm_inlets_junctions",
            "user_swmm_outlets",
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
        self.gutils.set_cont_par("PROJ", self.crs.toProj())
        self.gutils.set_cont_par("CELLSIZE", int(round(self.f2g.parser.calculate_cellsize())))

        # load layers and tables
        self.load_layers()
        self.uc.bar_info("Project successfully imported!", dur=3)
        self.uc.log_info("Project successfully imported!")
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
                QApplication.setOverrideCursor(Qt.ArrowCursor)
                proceed = self.uc.question(
                    "Grid layer's fields 'col' and 'row' have NULL values!\n\nWould you like to assign them?"
                )
                QApplication.restoreOverrideCursor()
                if proceed:
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    assign_col_row_indexes_to_grid(self.lyrs.data["grid"]["qlyr"], self.gutils)
                    QApplication.restoreOverrideCursor()
                else:
                    return

        QApplication.restoreOverrideCursor()
        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.show_error("ERROR 050521.0349: importing from .HDF5 file!.\n", e)
        # finally:
        QApplication.restoreOverrideCursor()
        self.gutils.enable_geom_triggers()

        # Check the imported components on the schema2user
        specific_components = []

        # Boundary Conditions
        if "import_inflow" in import_calls or "import_outflow" in import_calls or "import_tailings" in import_calls:
            specific_components.append(2)

        if "import_chan" in import_calls or "import_xsec" in import_calls:
            specific_components.append(3)

        if "import_hystruc" in import_calls or "import_hystruc_bridge_xs" in import_calls:
            specific_components.append(7)

        if "import_levee" in import_calls:
            specific_components.append(4)

        if "import_fpxsec" in import_calls:
            specific_components.append(5)

        if "import_mannings_n_topo" in import_calls:
            specific_components.append(1)

        if len(specific_components) > 0:
            msg = "To complete the user layer functionality, use the <FONT COLOR=black>Convert Schematic " \
                  "Layers to User Layers</FONT> tool in the FLO-2D panel."
            self.uc.show_info(msg)
            self.schematic2user(True)

    @connection_required
    def import_components(self):
        """
        Import selected traditional GDS files into FLO-2D database (GeoPackage).
        """
        self.uncheck_all_info_tools()
        msg = "This import method imports .DAT files without importing grid related files.\n\n" \
              "* Select 'Several Components' to import multiple *.DAT files.\n" \
              "* Select 'One Single Component' to import one single *.DAT file.\n"
        imprt = self.uc.dialog_with_2_customized_buttons(
            "Select import method", msg, " Several Components", " One Single Component"
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
            # "import_outrc",
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
            "import_steep_slopen",
            "import_shallowNSpatial",
            "import_lid_volume",
            "import_swmminp",
            "import_swmmflo",
            "import_swmmflort",
            "import_swmmoutf",
            "import_swmmflodropbox",
            "import_sdclogging",
        ]

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
                    self.gutils.enable_geom_triggers()
                    return

            empty = self.f2g.is_table_empty("grid")
            # check if a grid exists in the grid table
            if empty:
                self.uc.show_info("There is no grid defined!")
                self.gutils.enable_geom_triggers()
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

                    # if "Surface Water Rating Tables" not in dlg_components.components:
                    #     import_calls.remove("import_outrc")

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

                    # if "Surface Water Rating Tables" not in dlg_components.components:
                    #     import_calls.remove("import_outrc")

                    if "Hydraulic  Structures" not in dlg_components.components:
                        import_calls.remove("import_hystruc")
                        import_calls.remove("import_hystruc_bridge_xs")

                    # if 'MODFLO-2D' not in dlg_components.components:
                    #     import_calls.remove('')

                    if "Rain" not in dlg_components.components:
                        import_calls.remove("import_rain")
                        import_calls.remove("import_raincell")

                    if "Storm Drain" not in dlg_components.components:
                        import_calls.remove("import_swmminp")
                        import_calls.remove("import_swmmflo")
                        import_calls.remove("import_swmmflort")
                        import_calls.remove("import_swmmoutf")
                        import_calls.remove("import_swmmflodropbox")
                        import_calls.remove("import_sdclogging")

                    if "Spatial Tolerance" not in dlg_components.components:
                        import_calls.remove("import_tolspatial")

                    if "Spatial Froude" not in dlg_components.components:
                        import_calls.remove("import_fpfroude")

                    if "Spatial Steep Slope-n" not in dlg_components.components:
                        import_calls.remove("import_steep_slopen")

                    if "LID Volume" not in dlg_components.components:
                        import_calls.remove("import_lid_volume")

                    if "Spatial Shallow-n" not in dlg_components.components:
                        import_calls.remove("import_shallowNSpatial")

                    if import_calls:

                        self.call_IO_methods(
                            import_calls, True
                        )  # The strings list 'import_calls', contains the names of
                        # the methods in the class Flo2dGeoPackage to import (read) the
                        # FLO-2D .DAT files

                        # save CRS to table cont
                        self.gutils.set_cont_par("PROJ", self.crs.toProj())

                        # load layers and tables
                        self.load_layers()
                        self.uc.bar_info("Project model imported!", dur=3)
                        self.uc.log_info("Project model imported!")
                        self.gutils.enable_geom_triggers()

                        if "import_chan" in import_calls:
                            self.gutils.create_schematized_rbank_lines_from_xs_tips()

                        self.setup_dock_widgets()
                        self.lyrs.refresh_layers()
                        self.lyrs.zoom_to_all()

                        QApplication.restoreOverrideCursor()

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

                    # Check the imported components on the schema2user
                    specific_components = []

                    # Boundary Conditions
                    if "import_inflow" in import_calls or "import_outflow" in import_calls or "import_tailings" in import_calls:
                        specific_components.append(2)

                    if "import_chan" in import_calls or "import_xsec" in import_calls:
                        specific_components.append(3)

                    if "import_hystruc" in import_calls or "import_hystruc_bridge_xs" in import_calls:
                        specific_components.append(7)

                    if "import_levee" in import_calls:
                        specific_components.append(4)

                    if "import_fpxsec" in import_calls:
                        specific_components.append(5)

                    if "import_mannings_n_topo" in import_calls:
                        specific_components.append(1)

                    if len(specific_components) > 0:
                        msg = "To complete the user layer functionality, use the <FONT COLOR=black>Convert Schematic " \
                              "Layers to User Layers</FONT> tool in the FLO-2D panel."
                        self.uc.show_info(msg)
                        self.schematic2user(True)

            else:
                self.gutils.enable_geom_triggers()
        else:
            self.gutils.enable_geom_triggers()

    @connection_required
    def import_selected_components2(self):
        """
        Import selected traditional GDS files into FLO-2D database (GeoPackage).
        """
        self.gutils.disable_geom_triggers()
        self.f2g = Flo2dGeoPackage(self.con, self.iface)
        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")
        fname, __ = QFileDialog.getOpenFileName(
            None, "Select FLO-2D file to import", directory=last_dir, filter="DAT or INP (*.DAT *.dat *.INP *.inp)"
        )
        if not fname:
            self.gutils.enable_geom_triggers()
            return
        dir_name = os.path.dirname(fname)
        s.setValue("FLO-2D/lastGdsDir", dir_name)
        bname = os.path.basename(fname)

        if bname.lower().endswith("inp"):
            swmm_file_name = bname
            swmm_file_path = fname
        else:
            swmm_file_name = "SWMM.INP"
            swmm_file_path = os.path.join(dir_name, swmm_file_name)

        file_to_import_calls = {
            "CONT.DAT": "import_cont_toler",
            "TOLER.DAT": "import_cont_toler",
            "TOLSPATIAL.DAT": "import_tolspatial",
            "INFLOW.DAT": "import_inflow",
            "TAILINGS.DAT": "import_tailings",
            "TAILINGS_CV.DAT": "import_tailings",
            "TAILINGS_STACK_DEPTH.DAT": "import_tailings",
            # "OUTRC.DAT": "import_outrc",
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
            "STEEP_SLOPEN.DAT": "import_steep_slopen",
            "LID_VOLUME.DAT": "import_lid_volume",
            "SHALLOWN_SPATIAL.DAT": "import_shallowNSpatial",
            f"{swmm_file_name}": "import_swmminp",
            "SWMMFLO.DAT": "import_swmmflo",
            "SWMMFLORT.DAT": "import_swmmflort",
            "SWMMOUTF.DAT": "import_swmmoutf",
            "SWMMFLODROPBOX.DAT": "import_swmmflodropbox",
            "SDCLOGGING.DAT": "import_sdclogging",
            "WSURF.DAT": "import_wsurf",
            "WSTIME.DAT": "import_wstime",
            "MANNINGS_N.DAT": "import_mannings_n",
            "TOPO.DAT": "import_topo"
        }

        if bname not in file_to_import_calls:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Import selected DAT file",
                "Import from {0} file is not supported.".format(bname),
            )
            self.uc.log_info(f"Import from {bname} file is not supported.")
            self.gutils.enable_geom_triggers()
            return

        if self.f2g.set_parser(fname):
            call_string = file_to_import_calls[bname]
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                method = getattr(self.f2g, call_string)
                if call_string == "import_swmminp":
                    method(swmm_file=swmm_file_path)
                else:
                    method()
                QApplication.restoreOverrideCursor()
                QMessageBox.information(
                    self.iface.mainWindow(),
                    "Import selected DAT file",
                    "Import from {0} was successful.".format(bname),
                )
                self.uc.log_info(f"Import from {bname} was successful.")
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
                self.uc.log_info(f"Import from {bname} fails.")

            finally:
                self.gutils.enable_geom_triggers()
                # Check the imported components on the schema2user
                specific_components = []

                # Boundary Conditions
                if "import_inflow" in call_string or "import_outflow" in call_string or "import_tailings" in call_string:
                    specific_components.append(2)

                if "import_chan" in call_string or "import_xsec" in call_string:
                    specific_components.append(3)

                if "import_hystruc" in call_string or "import_hystruc_bridge_xs" in call_string:
                    specific_components.append(7)

                if "import_levee" in call_string:
                    specific_components.append(4)

                if "import_fpxsec" in call_string:
                    specific_components.append(5)

                if "import_mannings_n_topo" in call_string:
                    specific_components.append(1)

                if len(specific_components) > 0:
                    msg = "To complete the user layer functionality, use the Convert Schematic " \
                          "Layers to User Layers tool in the FLO-2D panel."
                    self.uc.show_info(msg)
                    self.uc.log_info(msg)
                    self.schematic2user(True)
        else:
            self.gutils.enable_geom_triggers()

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
        self.uncheck_all_info_tools()
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        s = QSettings()
        project_dir = s.value("FLO-2D/lastGdsDir")

        # This is a workaround. It will work, but it not a good coding practice
        if project_dir.startswith("geopackage:"):
            project_dir = project_dir[len("geopackage:"):].strip("/")

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
                'export_outrc',
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
                "export_steep_slopen",
                "export_lid_volume",
                "export_swmmflo",
                "export_swmmflort",
                "export_swmmoutf",
                "export_swmmflodropbox",
                "export_sdclogging",
                "export_wsurf",
                "export_wstime",
                "export_shallowNSpatial",
                "export_mannings_n_topo",
            ]

            s.setValue("FLO-2D/lastGdsDir", outdir)

            dlg_components = ComponentsDialog(self.con, self.iface, self.lyrs, "out")

            # Check the presence of fplain cadpts neighbors dat files
            files = [
                "FPLAIN.DAT",
                "CADPTS.DAT",
                "NEIGHBORS.DAT"
            ]
            for file in files:
                file_path = os.path.join(outdir, file)
                if os.path.exists(file_path):
                    dlg_components.remove_files_chbox.setEnabled(True)
                    break

            ok = dlg_components.exec_()
            if ok:
                if dlg_components.remove_files_chbox.isChecked():
                    for file in files:
                        file_path = os.path.join(outdir, file)
                        if os.path.exists(file_path):
                            os.remove(file_path)

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

                if "Tailings" not in dlg_components.components:
                    export_calls.remove("export_tailings")

                if "Surface Water Rating Tables" not in dlg_components.components:
                    export_calls.remove("export_outrc")

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
                    export_calls.remove("export_swmmflodropbox")
                    export_calls.remove("export_sdclogging")

                if "Spatial Shallow-n" not in dlg_components.components:
                    export_calls.remove("export_shallowNSpatial")

                if "Spatial Tolerance" not in dlg_components.components:
                    export_calls.remove("export_tolspatial")

                if "Spatial Froude" not in dlg_components.components:
                    export_calls.remove("export_fpfroude")

                if "Manning's n and Topo" not in dlg_components.components:
                    export_calls.remove("export_mannings_n_topo")

                if "Spatial Steep Slope-n" not in dlg_components.components:
                    export_calls.remove("export_steep_slopen")

                if "LID Volume" not in dlg_components.components:
                    export_calls.remove("export_lid_volume")

                try:
                    s = QSettings()
                    s.setValue("FLO-2D/lastGdsDir", outdir)

                    # QApplication.setOverrideCursor(Qt.WaitCursor)
                    self.call_IO_methods(export_calls, True, outdir)

                    # The strings list 'export_calls', contains the names of
                    # the methods in the class Flo2dGeoPackage to export (write) the
                    # FLO-2D .DAT files

                finally:

                    if "export_tailings" in export_calls:
                        MUD = self.gutils.get_cont_par("MUD")
                        concentration_sql = """SELECT 
                                            CASE WHEN COUNT(*) > 0 THEN True
                                                 ELSE False
                                            END AS result
                                            FROM 
                                                tailing_cells
                                            WHERE 
                                                concentration <> 0 OR concentration IS NULL;"""
                        cv = self.gutils.execute(concentration_sql).fetchone()[0]
                        # TAILINGS.DAT and TAILINGS_CV.DAT
                        if MUD == '1':
                            # Export TAILINGS_CV.DAT
                            if cv == 1:
                                new_files_used = self.files_used.replace("TAILINGS.DAT\n", "TAILINGS_CV.DAT\n")
                                self.files_used = new_files_used
                        # TAILINGS_STACK_DEPTH.DAT
                        elif MUD == '2':
                            new_files_used = self.files_used.replace("TAILINGS.DAT\n", "TAILINGS_STACK_DEPTH.DAT\n")
                            self.files_used = new_files_used

                    if "export_swmmflo" in export_calls:
                        self.f2d_widget.storm_drain_editor.export_storm_drain_INP_file()

                    # Delete .DAT files the model will try to use if existing:
                    if "export_mult" in export_calls:
                        if self.gutils.is_table_empty("simple_mult_cells"):
                            new_files_used = self.files_used.replace("SIMPLE_MULT.DAT\n", "")
                            self.files_used = new_files_used
                            if os.path.isfile(outdir + r"\SIMPLE_MULT.DAT"):
                                QApplication.setOverrideCursor(Qt.ArrowCursor)
                                if self.uc.question(
                                        "There are no simple multiple channel cells in the project but\n"
                                        + "there is a SIMPLE_MULT.DAT file in the directory.\n"
                                        + "If the file is not deleted it will be used by the model.\n\n"
                                        + "Delete SIMPLE_MULT.DAT?"
                                ):
                                    os.remove(outdir + r"\SIMPLE_MULT.DAT")
                                QApplication.restoreOverrideCursor()
                        if self.gutils.is_table_empty("mult_cells"):
                            new_files_used = self.files_used.replace("\nMULT.DAT\n", "\n")
                            self.files_used = new_files_used
                            if os.path.isfile(outdir + r"\MULT.DAT"):
                                QApplication.setOverrideCursor(Qt.ArrowCursor)
                                if self.uc.question(
                                        "There are no multiple channel cells in the project but\n"
                                        + "there is a MULT.DAT file in the directory.\n"
                                        + "If the file is not deleted it will be used by the model.\n\n"
                                        + "Delete MULT.DAT?"
                                ):
                                    os.remove(outdir + r"\MULT.DAT")
                                QApplication.restoreOverrideCursor()
                    if self.files_used != "":
                        QApplication.setOverrideCursor(Qt.ArrowCursor)
                        info = "Files exported to\n" + outdir + "\n\n" + self.files_used
                        self.uc.show_info(info)
                        QApplication.restoreOverrideCursor()

                    if self.f2g.export_messages != "":
                        QApplication.setOverrideCursor(Qt.ArrowCursor)
                        info = "WARNINGS 100424.0613:\n\n" + self.f2g.export_messages
                        self.uc.show_info(info)
                        QApplication.restoreOverrideCursor()

                    self.uc.bar_info("FLO-2D model exported to " + outdir, dur=3)

        QApplication.restoreOverrideCursor()

    @connection_required
    def export_hdf5(self):
        """
        Export FLO-2D database (GeoPackage) data into HDF5 format.
        """
        self.uncheck_all_info_tools()
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
                "export_inflow",
                "export_outflow",
                "export_infil",
                "export_arf",
                "export_rain",
                "export_levee",
                "export_hystruc",
                "export_chan",
                "export_bridge_xsec",
                "export_xsec",
                "export_breach",
                "export_mult",
                "export_fpxsec",
                "export_fpfroude",
                "export_steep_slopen",
                "export_lid_volume",
                "export_sed",
                "export_swmmflo",
                "export_swmmflort",
                "export_swmmoutf",
                "export_sdclogging",
                "export_swmmflodropbox",
                "export_swmminp",
                "export_evapor",
                "export_street",
                "export_shallowNSpatial",
                "export_gutter",
                "export_tailings",
                "export_outrc",
                "export_tolspatial"
            ]

            s.setValue("FLO-2D/lastGdsDir", outdir)

            dlg_components = ComponentsDialog(self.con, self.iface, self.lyrs, "out")
            ok = dlg_components.exec_()
            if ok:
                if "Channels" not in dlg_components.components:
                    export_calls.remove("export_chan")
                    export_calls.remove("export_xsec")

                if "Reduction Factors" not in dlg_components.components:
                    export_calls.remove("export_arf")

                # if "Streets" not in dlg_components.components:
                #     export_calls.remove("export_street")

                if "Outflow Elements" not in dlg_components.components:
                    export_calls.remove("export_outflow")

                if "Inflow Elements" not in dlg_components.components:
                    export_calls.remove("export_inflow")
                    # export_calls.remove("export_tailings")

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
                else:
                    # if not self.uc.question("Did you schematize Hydraulic Structures? Do you want to export Hydraulic Structures files?"):
                    #     export_calls.remove("export_hystruc")
                    #     export_calls.remove("export_bridge_xsec")
                    #     export_calls.remove("export_bridge_coeff_data")
                    # else:
                    xsecs = self.gutils.execute("SELECT fid FROM struct WHERE icurvtable = 3").fetchone()
                    if not xsecs:
                        export_calls.remove("export_bridge_xsec")
                        # export_calls.remove("export_bridge_coeff_data")

                if "Rain" not in dlg_components.components:
                    export_calls.remove("export_rain")

                if "Storm Drain" not in dlg_components.components:
                    export_calls.remove("export_swmmflo")
                    export_calls.remove("export_swmmflort")
                    export_calls.remove("export_swmmoutf")
                    export_calls.remove("export_sdclogging")
                    export_calls.remove("export_swmmflodropbox")
                    export_calls.remove("export_swmminp")

                if "Spatial Shallow-n" not in dlg_components.components:
                    export_calls.remove("export_shallowNSpatial")

                if "Spatial Tolerance" not in dlg_components.components:
                    export_calls.remove("export_tolspatial")

                if "Spatial Froude" not in dlg_components.components:
                    export_calls.remove("export_fpfroude")

                if "Manning's n and Topo" not in dlg_components.components:
                    export_calls.remove("export_mannings_n_topo")

                if "Spatial Steep Slope-n" not in dlg_components.components:
                    export_calls.remove("export_steep_slopen")

                if "LID Volume" not in dlg_components.components:
                    export_calls.remove("export_lid_volume")

                try:
                    s = QSettings()
                    s.setValue("FLO-2D/lastGdsDir", outdir)

                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    self.call_IO_methods(export_calls, True)

                    if "export_swmmflo" in export_calls:
                        self.f2d_widget.storm_drain_editor.export_storm_drain_INP_file(outdir, output_hdf5)

                    self.uc.bar_info("FLO-2D model exported to " + output_hdf5, dur=3)

                finally:
                    QApplication.restoreOverrideCursor()
                    if self.f2g.export_messages != "":
                        info = "WARNINGS:\n\n" + self.f2g.export_messages
                        self.uc.show_info(info)

    @connection_required
    def import_from_gpkg(self):
        self.uncheck_all_info_tools()

        # get metadata parameters
        contact = self.gutils.get_metadata_par("CONTACT")
        email = self.gutils.get_metadata_par("EMAIL")
        company = self.gutils.get_metadata_par("COMPANY")
        phone = self.gutils.get_metadata_par("PHONE")
        pn = self.gutils.get_metadata_par("PROJ_NAME")
        plugin_v = self.gutils.get_metadata_par("PLUGIN_V")
        qgis_v = self.gutils.get_metadata_par("QGIS_V")
        flo2d_v = self.gutils.get_metadata_par("FLO-2D_V")

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

            # save original metadata parameters because it was overwritten by the import from gpkg.
            self.gutils.set_metadata_par("PROJ_NAME", pn)
            self.gutils.set_metadata_par("CONTACT", contact)
            self.gutils.set_metadata_par("EMAIL", email)
            self.gutils.set_metadata_par("PHONE", phone)
            self.gutils.set_metadata_par("COMPANY", company)
            self.gutils.set_metadata_par("PLUGIN_V", plugin_v)
            self.gutils.set_metadata_par("QGIS_V", qgis_v)
            self.gutils.set_metadata_par("FLO-2D_V", flo2d_v)
            self.gutils.set_metadata_par("CRS", self.crs.authid())

            self.load_layers()
            self.setup_dock_widgets()
        finally:
            QApplication.restoreOverrideCursor()

    @connection_required
    def import_inp(self):
        """
        Function to export FLO-2D to SWMM's INP file
        """
        try:

            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                self.uc.log_info("There is no grid! Please create it before running tool.")
                return False

            QApplication.setOverrideCursor(Qt.WaitCursor)

            self.f2g = Flo2dGeoPackage(self.con, self.iface, parsed_format="DAT")
            s = QSettings()
            last_dir = s.value("FLO-2D/lastGdsDir", "")
            fname, __ = QFileDialog.getOpenFileName(
                None, "Select SWMM INP file to import", directory=last_dir, filter="(*.INP)"
            )
            if not fname:
                QApplication.restoreOverrideCursor()
                return

            dir_name = os.path.dirname(fname)
            s.setValue("FLO-2D/lastGdsDir", dir_name)

            sd_user_tables = [
                'user_swmm_inlets_junctions',
                'user_swmm_conduits',
                'user_swmm_pumps',
                'user_swmm_orifices',
                'user_swmm_weirs',
                'user_swmm_outlets',
                'user_swmm_storage_units'
            ]
            empty_sd = all((self.gutils.is_table_empty(sd_user_table) for sd_user_table in sd_user_tables))

            if self.f2g.set_parser(fname, get_cell_size=False):
                if not empty_sd:
                    QApplication.restoreOverrideCursor()
                    msg = QMessageBox()
                    msg.setWindowTitle("Replace or complete Storm Drain User Data")
                    msg.setText(
                        "There is already Storm Drain data in the Users Layers.\n\nWould you like to keep it and "
                        "complete it with data taken from the .INP file?\n\n"
                        + "or you prefer to erase it and create new storm drains from the .INP file?\n"
                    )

                    msg.addButton(QPushButton("Keep existing and complete"), QMessageBox.YesRole)
                    msg.addButton(QPushButton("Create new Storm Drains"), QMessageBox.NoRole)
                    msg.addButton(QPushButton("Cancel"), QMessageBox.RejectRole)
                    msg.setDefaultButton(QMessageBox().Cancel)
                    msg.setIcon(QMessageBox.Question)
                    ret = msg.exec_()
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    if ret == 0:
                        self.f2g.import_swmminp(swmm_file=fname, delete_existing=False)
                    elif ret == 1:
                        self.f2g.import_swmminp(swmm_file=fname)
                    else:
                        QApplication.restoreOverrideCursor()
                        return
                else:
                    self.f2g.import_swmminp(swmm_file=fname)

            self.lyrs.refresh_layers()

            self.uc.bar_info("Import from INP completed! Check log messages for more information. ")
            self.uc.log_info("Import from INP completed!")

            QApplication.restoreOverrideCursor()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(f"ERROR 08272024.0932: Could not import SWMM INP file!\n{e}")
            self.uc.bar_error("ERROR 08272024.0932: Could not import SWMM INP file!")

    @connection_required
    def export_inp(self):
        """
        Function to import SWMM's INP file to FLO-2D project
        """
        sd_editor = StormDrainEditorWidget(self.iface, self.f2d_plot, self.f2d_table, self.lyrs)
        sd_editor.export_storm_drain_INP_file(set_dat_dir=True)

    @connection_required
    def import_multidomains(self):
        """
        Function to import multiple domains into the FLO-2D project
        """
        dlg = ImportMultipleDomainsDialog(self.con, self.iface, self.lyrs)
        ok = dlg.exec_()
        if not ok:
            return
        else:
            pass

    @connection_required
    def export_multidomains(self):
        """
        Function to export multiple domains into the FLO-2D project
        """
        dlg = ExportMultipleDomainsDialog(self.con, self.iface, self.lyrs)
        ok = dlg.exec_()
        if not ok:
            return
        else:
            pass

    @connection_required
    def import_from_ras(self):
        self.uncheck_all_info_tools()
        dlg = RasImportDialog(self.con, self.iface, self.lyrs)
        ok = dlg.exec_()
        if ok:
            pass
        else:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            dlg.import_geometry()
            # self.setup_dock_widgets()
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
        self.uncheck_all_info_tools()
        try:
            dlg_control = ContToler_JJ(self.con, self.iface, self.lyrs)
            while True:
                save = dlg_control.exec_()
                if save:
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    try:
                        if dlg_control.save_parameters_JJ():
                            self.f2d_widget.ic_editor.populate_cbos()
                            self.uc.bar_info("Parameters saved!", dur=3)
                            QApplication.restoreOverrideCursor()
                            break
                        else:
                            QApplication.restoreOverrideCursor()
                    except Exception as e:
                        QApplication.restoreOverrideCursor()
                        self.uc.show_error("ERROR 110618.1828: Could not save FLO-2D parameters!", e)
                        return
                else:
                    break
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 110618.1816: Could not save FLO-2D parameters!!", e)

    @connection_required
    def activate_general_info_tool(self):
        """
        Function to activate the Info Tool
        """
        info_ac = None
        for ac in self.toolActions:
            if ac.toolTip() == "<b>FLO-2D Info Tool</b>":
                info_ac = ac

        if self.f2d_table_dock is not None:
            self.iface.addDockWidget(Qt.BottomDockWidgetArea, self.f2d_table_dock)

        if self.f2d_plot_dock is not None:
            self.iface.addDockWidget(Qt.BottomDockWidgetArea, self.f2d_plot_dock)

        grid = self.lyrs.data["grid"]["qlyr"]
        if grid is not None:
            tool = self.canvas.mapTool()
            if tool == self.info_tool:
                if info_ac:
                    info_ac.setChecked(False)
                self.uncheck_all_info_tools()
            else:
                if tool is not None:
                    self.uncheck_all_info_tools()
                    if info_ac:
                        info_ac.setChecked(False)
                self.canvas.setMapTool(self.info_tool)
                if info_ac:
                    info_ac.setChecked(True)

    @connection_required
    def activate_grid_info_tool(self):
        """
        Function to activate the Grid Info Tool
        """
        info_ac = None
        for ac in self.toolActions:
            if ac.toolTip() == "<b>FLO-2D Grid Info Tool</b>":
                info_ac = ac

        if self.f2d_grid_info_dock is not None:
            self.iface.addDockWidget(Qt.TopDockWidgetArea, self.f2d_grid_info_dock)

        grid = self.lyrs.data["grid"]["qlyr"]
        if grid is not None:
            tool = self.canvas.mapTool()
            if tool == self.grid_info_tool:
                self.uncheck_all_info_tools()
                if info_ac:
                    info_ac.setChecked(False)
            else:
                if tool is not None:
                    self.uncheck_all_info_tools()
                    if info_ac:
                        info_ac.setChecked(False)
                self.grid_info_tool.grid = grid
                self.f2d_grid_info.set_info_layer(grid)
                self.f2d_grid_info.mann_default = self.gutils.get_cont_par("MANNING")
                self.f2d_grid_info.cell_Edit = self.gutils.get_cont_par("CELLSIZE")
                self.f2d_grid_info.n_cells = number_of_elements(self.gutils, grid)
                self.f2d_grid_info.gutils = self.gutils
                self.canvas.setMapTool(self.grid_info_tool)
                if info_ac:
                    info_ac.setChecked(True)
        else:
            self.uc.bar_warn("There is no grid layer to identify.")

    @connection_required
    def activate_results_info_tool(self):
        """
        Function to activate the Results Tool
        """
        info_ac = None
        for ac in self.toolActions:
            if ac.toolTip() == "<b>FLO-2D Results</b>":
                info_ac = ac

        if self.f2d_table_dock is not None:
            self.iface.addDockWidget(Qt.BottomDockWidgetArea, self.f2d_table_dock)

        if self.f2d_plot_dock is not None:
            self.iface.addDockWidget(Qt.BottomDockWidgetArea, self.f2d_plot_dock)

        tool = self.canvas.mapTool()
        if tool == self.results_tool:
            if info_ac:
                info_ac.setChecked(False)
            self.uncheck_all_info_tools()
        else:
            if tool is not None:
                self.uncheck_all_info_tools()
                if info_ac:
                    info_ac.setChecked(False)
            self.canvas.setMapTool(self.results_tool)
            # 'channel_profile_tool' is an instance of ChannelProfile class,
            # created on loading the plugin, and to be used to plot channel
            # profiles using a subtool in the FLO-2D tool bar.
            # The plots will be based on data from the 'chan', 'cham_elems'
            # schematic layers.
            self.results_tool.update_lyrs_list()
            if info_ac:
                info_ac.setChecked(True)

    @connection_required
    def show_user_profile(self, fid=None):
        self.f2d_dock.setUserVisible(True)
        self.f2d_widget.profile_tool_grp.setCollapsed(False)
        self.f2d_widget.profile_tool.identify_feature(self.cur_info_table, fid)
        self.cur_info_table = None

    @connection_required
    def show_channel_profile(self, fid=None):
        self.f2d_widget.xs_editor.show_channel(fid)
        self.cur_info_table = None

    @connection_required
    def show_profile(self, fid=None):
        self.f2d_widget.xs_editor.show_channel_peaks(self.cur_profile_table, fid)
        self.cur_profile_table = None

    @connection_required
    def show_xsec_hydrograph(self, fid=None):
        """
        Show the cross-section hydrograph from HYCHAN.OUT
        """
        self.f2d_widget.xs_editor.show_hydrograph(self.cur_profile_table, fid)
        self.cur_profile_table = None

    @connection_required
    def show_fpxsec_hydrograph(self, fid=None):
        """
        Show the floodplain cross-section hydrograph from HYCROSS.OUT
        """
        self.f2d_widget.fpxsec_editor.show_hydrograph(self.cur_profile_table, fid)
        self.cur_profile_table = None

    @connection_required
    def show_fpxsec_cells_hydrograph(self, fid=None):
        """
        Show the floodplain cross-section hydrograph from HYCROSS.OUT
        """
        self.f2d_widget.fpxsec_editor.show_cells_hydrograph(self.cur_profile_table, fid)
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
    def show_sd_node_profile(self, fid=None, extra=""):
        """
        Show the selected sd node info
        """
        name = self.gutils.execute("SELECT name FROM user_swmm_inlets_junctions WHERE fid = ?", (fid,)).fetchone()
        self.uc.bar_info("Selected Storm Drain Node: " + str(name[0]))
        self.f2d_widget.storm_drain_editor.center_chbox.setChecked(True)
        self.f2d_widget.storm_drain_editor.update_profile_cbos(extra, name[0])

    @connection_required
    def show_sd_outfall_profile(self, fid=None, extra=""):
        """
        Show the selected sd outfall info
        """
        name = self.gutils.execute("SELECT name FROM user_swmm_outlets WHERE fid = ?", (fid,)).fetchone()
        self.uc.bar_info("Selected Storm Drain Outfall: " + str(name[0]))
        self.f2d_widget.storm_drain_editor.center_chbox.setChecked(True)
        self.f2d_widget.storm_drain_editor.update_profile_cbos(extra, name[0])

    @connection_required
    def show_sd_su_profile(self, fid=None, extra=""):
        """
        Show the selected sd su info
        """
        name = self.gutils.execute("SELECT name FROM user_swmm_storage_units WHERE fid = ?", (fid,)).fetchone()
        self.uc.bar_info("Selected Storm Drain Storage Unit: " + str(name[0]))
        self.f2d_widget.storm_drain_editor.center_chbox.setChecked(True)
        self.f2d_widget.storm_drain_editor.update_profile_cbos(extra, name[0])

    @connection_required
    def show_sd_inlets_junctions_attributes(self, fid=None, extra=""):
        """
        Show the selected sd inlet/junctions attributes
        """
        if self.f2d_inlets_junctions_dock:
            self.iface.removeDockWidget(self.f2d_inlets_junctions_dock)
            self.f2d_inlets_junctions_dock.close()
            self.f2d_inlets_junctions_dock.deleteLater()
            self.f2d_inlets_junctions_dock = None

        name = self.gutils.execute("SELECT name FROM user_swmm_inlets_junctions WHERE fid = ?", (fid,)).fetchone()
        self.uc.bar_info("Selected Storm Drain Inlet/Junction: " + str(name[0]))

        if extra in ["Start", "End"]:
            self.f2d_widget.storm_drain_editor.update_profile_cbos(extra, name[0])
        else:
            dlg = InletAttributes(self.con, self.iface, self.lyrs)
            self.iface.mainWindow().addDockWidget(Qt.RightDockWidgetArea, dlg.dock_widget)
            self.iface.mainWindow().tabifyDockWidget(self.f2d_dock, dlg.dock_widget)
            dlg.dock_widget.setFloating(False)
            dlg.populate_attributes(fid)
            dlg.dock_widget.show()
            dlg.dock_widget.raise_()

            self.f2d_inlets_junctions_dock = dlg.dock_widget

    @connection_required
    def show_sd_outlets_attributes(self, fid=None, extra=""):
        """
        Show the selected sd outlets attributes
        """
        if self.f2d_outlets_dock:
            self.iface.removeDockWidget(self.f2d_outlets_dock)
            self.f2d_outlets_dock.close()
            self.f2d_outlets_dock.deleteLater()
            self.f2d_outlets_dock = None

        name = self.gutils.execute("SELECT name FROM user_swmm_outlets WHERE fid = ?", (fid,)).fetchone()
        self.uc.bar_info("Selected Storm Drain Outfall: " + str(name[0]))
        if extra in ["Start", "End"]:
            self.f2d_widget.storm_drain_editor.update_profile_cbos(extra, name[0])
        else:
            dlg = OutletAttributes(self.con, self.iface, self.lyrs)
            self.iface.mainWindow().addDockWidget(Qt.RightDockWidgetArea, dlg.dock_widget)
            self.iface.mainWindow().tabifyDockWidget(self.f2d_dock, dlg.dock_widget)
            dlg.dock_widget.setFloating(False)
            dlg.populate_attributes(fid)
            dlg.dock_widget.show()
            dlg.dock_widget.raise_()

            self.f2d_outlets_dock = dlg.dock_widget

    @connection_required
    def show_sd_storage_unit_attributes(self, fid=None, extra=""):
        """
        Show the selected sd storage unit attributes
        """
        if self.f2d_storage_units_dock:
            self.iface.removeDockWidget(self.f2d_storage_units_dock)
            self.f2d_storage_units_dock.close()
            self.f2d_storage_units_dock.deleteLater()
            self.f2d_storage_units_dock = None

        storage_unit_name = self.gutils.execute("SELECT name FROM user_swmm_storage_units WHERE fid = ?",
                                                (fid,)).fetchone()
        self.uc.bar_info("Selected Storm Drain Storage Unit: " + str(storage_unit_name[0]))
        if extra in ["Start", "End"]:
            self.f2d_widget.storm_drain_editor.update_profile_cbos(extra, storage_unit_name[0])
        else:
            dlg = StorageUnitAttributes(self.con, self.iface, self.lyrs)
            self.iface.mainWindow().addDockWidget(Qt.RightDockWidgetArea, dlg.dock_widget)
            self.iface.mainWindow().tabifyDockWidget(self.f2d_dock, dlg.dock_widget)
            dlg.dock_widget.setFloating(False)
            dlg.populate_attributes(fid)
            dlg.dock_widget.show()
            dlg.dock_widget.raise_()

            self.f2d_storage_units_dock = dlg.dock_widget

    @connection_required
    def show_sd_weir_attributes(self, fid=None):
        """
        Show the selected sd weir attributes
        """
        if self.f2d_weirs_dock:
            self.iface.removeDockWidget(self.f2d_weirs_dock)
            self.f2d_weirs_dock.close()
            self.f2d_weirs_dock.deleteLater()
            self.f2d_weirs_dock = None

        weir_name = self.gutils.execute("SELECT weir_name FROM user_swmm_weirs WHERE fid = ?",
                                        (fid,)).fetchone()
        self.uc.bar_info("Selected Storm Drain Weir: " + str(weir_name[0]))

        dlg = WeirAttributes(self.con, self.iface, self.lyrs)
        self.iface.mainWindow().addDockWidget(Qt.RightDockWidgetArea, dlg.dock_widget)
        self.iface.mainWindow().tabifyDockWidget(self.f2d_dock, dlg.dock_widget)
        dlg.dock_widget.setFloating(False)
        dlg.populate_attributes(fid)
        dlg.dock_widget.show()
        dlg.dock_widget.raise_()

        self.f2d_weirs_dock = dlg.dock_widget

    @connection_required
    def show_sd_orifice_attributes(self, fid=None):
        """
        Show the selected sd orifice attributes
        """
        if self.f2d_orifices_dock:
            self.iface.removeDockWidget(self.f2d_orifices_dock)
            self.f2d_orifices_dock.close()
            self.f2d_orifices_dock.deleteLater()
            self.f2d_orifices_dock = None

        orifice_name = self.gutils.execute("SELECT orifice_name FROM user_swmm_orifices WHERE fid = ?",
                                           (fid,)).fetchone()
        self.uc.bar_info("Selected Storm Drain Orifice: " + str(orifice_name[0]))

        dlg = OrificeAttributes(self.con, self.iface, self.lyrs)
        self.iface.mainWindow().addDockWidget(Qt.RightDockWidgetArea, dlg.dock_widget)
        self.iface.mainWindow().tabifyDockWidget(self.f2d_dock, dlg.dock_widget)
        dlg.dock_widget.setFloating(False)
        dlg.populate_attributes(fid)
        dlg.dock_widget.show()
        dlg.dock_widget.raise_()

        self.f2d_orifices_dock = dlg.dock_widget

    @connection_required
    def show_sd_pump_attributes(self, fid=None):
        """
        Show the selected sd pump attributes
        """
        if self.f2d_pumps_dock:
            self.iface.removeDockWidget(self.f2d_pumps_dock)
            self.f2d_pumps_dock.close()
            self.f2d_pumps_dock.deleteLater()
            self.f2d_pumps_dock = None

        pump_name = self.gutils.execute("SELECT pump_name FROM user_swmm_pumps WHERE fid = ?",
                                        (fid,)).fetchone()
        self.uc.bar_info("Selected Storm Drain Pump: " + str(pump_name[0]))

        dlg = PumpAttributes(self.con, self.iface, self.lyrs)
        self.iface.mainWindow().addDockWidget(Qt.RightDockWidgetArea, dlg.dock_widget)
        self.iface.mainWindow().tabifyDockWidget(self.f2d_dock, dlg.dock_widget)
        dlg.dock_widget.setFloating(False)
        dlg.populate_attributes(fid)
        dlg.dock_widget.show()
        dlg.dock_widget.raise_()

        self.f2d_pumps_dock = dlg.dock_widget

    @connection_required
    def show_sd_conduit_attributes(self, fid=None):
        """
        Show the selected sd conduit attributes
        """
        if self.f2d_conduits_dock:
            self.iface.removeDockWidget(self.f2d_conduits_dock)
            self.f2d_conduits_dock.close()
            self.f2d_conduits_dock.deleteLater()
            self.f2d_conduits_dock = None

        conduit_name = self.gutils.execute("SELECT conduit_name FROM user_swmm_conduits WHERE fid = ?",
                                           (fid,)).fetchone()
        self.uc.bar_info("Selected Storm Drain Conduit: " + str(conduit_name[0]))

        dlg = ConduitAttributes(self.con, self.iface, self.lyrs)
        self.iface.mainWindow().addDockWidget(Qt.RightDockWidgetArea, dlg.dock_widget)
        self.iface.mainWindow().tabifyDockWidget(self.f2d_dock, dlg.dock_widget)
        dlg.dock_widget.setFloating(False)
        dlg.populate_attributes(fid)
        dlg.dock_widget.show()
        dlg.dock_widget.raise_()

        self.f2d_conduits_dock = dlg.dock_widget

    @connection_required
    def show_struct_hydrograph(self, fid=None):
        """
        Show the Hydraulic Structure Hydrograph from HYDROSTRUCT.OUT
        """
        self.f2d_widget.struct_editor.show_hydrograph(self.cur_profile_table, fid)
        self.cur_profile_table = None

    @connection_required
    def show_sd_node_discharge(self, fid=None):
        """
        Show storm drain discharge for a given node.
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        name, grid = self.gutils.execute("SELECT name, grid FROM user_swmm_inlets_junctions WHERE fid = ?",
                                         (fid,)).fetchone()
        self.f2d_dock.setUserVisible(True)
        self.f2d_widget.storm_drain_editor.create_SD_discharge_table_and_plots('node', name)

    @connection_required
    def show_sd_outfall_discharge(self, fid=None):
        """
        Show storm drain discharge for a given outfall node.
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        name, grid = self.gutils.execute("SELECT name, grid FROM user_swmm_outlets WHERE fid = ?", (fid,)).fetchone()
        self.f2d_dock.setUserVisible(True)
        self.f2d_widget.storm_drain_editor.create_SD_discharge_table_and_plots('outfall', name)

    @connection_required
    def show_sd_su_discharge(self, fid=None):
        """
        Show storm drain discharge for a given storage unit
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        name, grid = self.gutils.execute("SELECT name, grid FROM user_swmm_storage_units WHERE fid = ?", (fid,)).fetchone()
        self.f2d_dock.setUserVisible(True)
        self.f2d_widget.storm_drain_editor.create_SD_discharge_table_and_plots('storage_unit', name)

    @connection_required
    def show_conduit_discharge(self, fid=None):
        """
        Show storm drain discharge for a given conduit link.
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        name = self.gutils.execute(f"SELECT conduit_name FROM user_swmm_conduits WHERE fid = '{fid}'").fetchone()[0]
        self.f2d_dock.setUserVisible(True)
        self.f2d_widget.storm_drain_editor.create_conduit_discharge_table_and_plots(name)

    @connection_required
    def show_pump_discharge(self, fid=None):
        """
        Show storm drain discharge for a given pump link.
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        name = self.gutils.execute(f"SELECT pump_name FROM user_swmm_pumps WHERE fid = '{fid}'").fetchone()[0]
        self.f2d_dock.setUserVisible(True)
        self.f2d_widget.storm_drain_editor.create_conduit_discharge_table_and_plots(name)

    @connection_required
    def show_2d_plot(self, fid=None):
        """
        Show 2d results for a given grid.
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        self.f2d_dock.setUserVisible(True)
        self.f2d_widget.grid_tools.plot_2d_grid_data(fid)
        self.f2d_grid_info.find_cell(fid)

    @connection_required
    def show_orifice_discharge(self, fid=None):
        """
        Show storm drain discharge for a given orifice link.
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        name = self.gutils.execute(f"SELECT orifice_name FROM user_swmm_orifices WHERE fid = '{fid}'").fetchone()[0]
        self.f2d_dock.setUserVisible(True)
        self.f2d_widget.storm_drain_editor.create_conduit_discharge_table_and_plots(name)

    @connection_required
    def show_weir_discharge(self, fid=None):
        """
        Show storm drain discharge for a given weir link.
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        name = self.gutils.execute(f"SELECT weir_name FROM user_swmm_weirs WHERE fid = '{fid}'").fetchone()[0]
        self.f2d_dock.setUserVisible(True)
        self.f2d_widget.storm_drain_editor.create_conduit_discharge_table_and_plots(name)

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
        self.gutils.enable_geom_triggers()
        self.f2d_dock.setUserVisible(True)
        self.f2d_widget.bc_editor_new_grp.setCollapsed(False)
        self.f2d_widget.bc_editor_new.show_editor(self.cur_info_table, fid)
        self.cur_info_table = None

    @connection_required
    def show_evap_editor(self):
        """
        Show evaporation editor.
        """
        self.uncheck_all_info_tools()
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
        self.uncheck_all_info_tools()
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
            self.uc.log_info(msg.format(null_elev_nr))
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

        # try:
        #             start = datetime.now()
        QApplication.setOverrideCursor(Qt.WaitCursor)
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
        for no in sorted(dlg_levee_elev.methods):
            dlg_levee_elev.methods[no]()

        inctime = time.time()
        print("%s seconds to process levee features" % round(inctime - starttime, 2))

        # Delete duplicates:
        grid_lyr = self.lyrs.get_layer_by_name("Grid", group=self.lyrs.group).layer()
        q = False
        if n_elements_total > 0:
            print("in clear loop")
            dletes = "Cell - Direction\n---------------\n"

            # delete duplicate elements with the same direction and elevation too
            qryIndex = "CREATE INDEX if not exists levee_dataFIDGRIDFIDLDIRLEVCEST  ON levee_data (fid, grid_fid, ldir, levcrest);"
            self.gutils.con.execute(qryIndex)
            self.gutils.con.commit()

            # levees_dup_qry = "SELECT min(fid), grid_fid, ldir, levcrest FROM levee_data GROUP BY grid_fid, ldir, levcrest HAVING COUNT(ldir) > 1 and count(levcrest) > 1 ORDER BY grid_fid"
            levees_dup_qry = "SELECT fid, grid_fid, ldir, max(levcrest) FROM levee_data GROUP BY grid_fid, ldir HAVING COUNT(grid_fid) = 2"

            leveeDups = self.gutils.execute(levees_dup_qry).fetchall()  # min FID, grid fid, ldir, min levcrest
            # grab the values
            print(
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

        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.log_info(traceback.format_exc())
        #     self.uc.show_error(
        #         "ERROR 060319.1806: Assigning values aborted! Please check your crest elevation source layers.\n",
        #         e,
        #     )

    @connection_required
    def show_hazus_dialog(self):
        self.uncheck_all_info_tools()
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
        self.uncheck_all_info_tools()
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
        self.uncheck_all_info_tools()
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
                        self.f2d_widget.ic_editor.populate_cbos()
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
        QDesktopServices.openUrl(
            QUrl("https://flo-2dsoftware.github.io/FLO-2D-Documentation/Plugin1000/toolbar/index.html"))

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
    def schematic2user(self, check_components=False):
        components = {
            1: "Computational Domain",
            2: "Boundary Conditions",
            3: "Channel Banks and Cross-Sections",
            4: "Levees",
            5: "Floodplain Cross-Sections",
            6: "Storm Drains",
            7: "Hydraulic structures",
        }
        self.uncheck_all_info_tools()
        converter_dlg = Schema2UserDialog(self.con, self.iface, self.lyrs, self.uc)
        if check_components:
            converter_dlg.check_imported_components(True)
        ok = converter_dlg.exec_()
        if ok:
            if converter_dlg.methods:
                pass
            else:
                self.uc.bar_warn("WARNING 060319.1810: Please choose at least one conversion source!")
                self.uc.log_info("WARNING 060319.1810: Please choose at least one conversion source!")
                return
        else:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        methods_numbers = sorted(converter_dlg.methods)
        msg = ""
        for no in methods_numbers:
            converter_dlg.methods[no]()
            msg += components[no] + "\n"
        self.setup_dock_widgets()
        QApplication.restoreOverrideCursor()
        self.uc.bar_info("Converting Schematic Layers to User Layers finished!")
        self.uc.log_info("Converting Schematic Layers to User Layers finished for:\n\n" + msg)

        # if 6 in methods_numbers:  # Storm Drains:
        #     self.uc.show_info(
        #         "To complete the Storm Drain functionality, select 'Import from .INP' from the 'FLO-2D' toolbar."
        #     )

    @connection_required
    def user2schematic(self):
        self.uncheck_all_info_tools
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
        self.info_tool = InfoTool(self.canvas, self.lyrs, self.uc)
        self.grid_info_tool = GridInfoTool(self.uc, self.canvas, self.lyrs)
        self.results_tool = ResultsTool(self.canvas, self.lyrs, self.uc)

    def get_feature_info(self, table, fid, extra):
        try:
            show_editor = self.editors_map[table]
            self.cur_info_table = table
        except KeyError:
            self.uc.bar_info("Not implemented...")
            return
        if show_editor:
            if extra:
                show_editor(fid, extra)
            else:
                show_editor(fid)

    def get_feature_profile(self, table, fid, extra):
        # try:
        if table == 'chan':
            self.cur_profile_table = table
            self.show_profile(fid)
        if table == 'chan_elems':
            self.cur_profile_table = table
            self.show_xsec_hydrograph(fid)
        if table == 'fpxsec':
            self.cur_profile_table = table
            self.show_fpxsec_hydrograph(fid)
        if table == 'fpxsec_cells':
            self.cur_profile_table = table
            self.show_fpxsec_cells_hydrograph(fid)
        if table == 'struct':
            self.cur_profile_table = table
            self.show_struct_hydrograph(fid)
        if table == 'user_swmm_inlets_junctions':
            if extra == "See Results":
                self.cur_profile_table = table
                self.show_sd_node_discharge(fid)
            else:
                self.show_sd_node_profile(fid, extra)
        if table == 'user_swmm_outlets':
            if extra == "See Results":
                self.cur_profile_table = table
                self.show_sd_outfall_discharge(fid)  # FIX THIS
            else:
                self.show_sd_outfall_profile(fid, extra)
        if table == 'user_swmm_storage_units':
            if extra == "See Results":
                self.cur_profile_table = table
                self.show_sd_su_discharge(fid)  # FIX THIS
            else:
                self.show_sd_su_profile(fid, extra)
        if table == 'user_swmm_conduits':
            self.cur_profile_table = table
            self.show_conduit_discharge(fid)
        if table == 'user_swmm_weirs':
            self.cur_profile_table = table
            self.show_weir_discharge(fid)
        if table == 'user_swmm_orifices':
            self.cur_profile_table = table
            self.show_orifice_discharge(fid)
        if table == 'user_swmm_pumps':
            self.cur_profile_table = table
            self.show_pump_discharge(fid)
        if table == 'grid':
            self.cur_profile_table = table
            self.show_2d_plot(fid)

        # except KeyError:
        #     self.uc.bar_info("Channel Profile tool not implemented for selected features.")
        #     return

    def set_editors_map(self):
        self.editors_map = {
            "chan": self.show_channel_profile,
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
            "user_swmm_inlets_junctions": self.show_sd_inlets_junctions_attributes,
            "user_swmm_outlets": self.show_sd_outlets_attributes,
            "user_swmm_conduits": self.show_sd_conduit_attributes,
            "user_swmm_weirs": self.show_sd_weir_attributes,
            "user_swmm_orifices": self.show_sd_orifice_attributes,
            "user_swmm_pumps": self.show_sd_pump_attributes,
            "user_swmm_storage_units": self.show_sd_storage_unit_attributes,
        }

    def restore_settings(self):
        pass

    def grid_info_tool_clicked(self):
        self.uc.bar_info("grid info tool clicked.")

    def uncheck_toolbar_tb(self, tool_button):
        """
        Function to uncheck the toolbar toolbuttons
        """
        for tb in self.toolButtons:
            if not tb.toolTip() == tool_button:
                tb.setChecked(False)

    def uncheck_all_info_tools(self):
        """
        Function to uncheck the info tools
        """
        self.canvas.unsetMapTool(self.grid_info_tool)
        self.canvas.unsetMapTool(self.info_tool)
        self.canvas.unsetMapTool(self.results_tool)

        for tb in self.toolButtons:
            tb.setChecked(False)
            if tb.toolTip() == "<b>FLO-2D Project Review</b>":
                tb.setIcon(QIcon(os.path.join(self.plugin_dir, "img/editmetadata.svg")))

        for ac in self.toolActions:
            ac.setChecked(False)

        for tb in self.toolButtons:
            tb.setChecked(False)
            if tb.toolTip() == "<b>FLO-2D Project Review</b>":
                tb.setIcon(QIcon(os.path.join(self.plugin_dir, "img/editmetadata.svg")))

        for ac in self.toolActions:
            ac.setChecked(False)

    def check_layer_source(self, layer, gpkg_path):
        """
        Function to check if the layer source is on the geopackage or not
        """
        gpkg_path_adj = gpkg_path.replace("\\", "/")
        layer_source_adj = layer.source().replace("\\", "/")

        # Check 0: Layer already on the external_layers table
        qry = f"SELECT * FROM external_layers WHERE name = '{layer.name()}';"
        data = self.gutils.execute(qry).fetchone()
        if data:
            return False

        # Check 1: Path cannot be equal to gpkg_path
        if gpkg_path_adj in layer_source_adj:
            return False

        # Check 2: Check based on the provider if the layer is raster or vector
        providers = ['ogr', 'gpkg', 'spatialite', 'memory', 'delimitedtext', 'gdal']
        if layer.dataProvider().name() not in providers:
            return False

        # Check 3: Check if it is an online raster or located in a MapCrafter folder
        if "MapCrafter" in layer.source():
            return False

        # Check 4: If the file is a raster
        if isinstance(layer, QgsVectorLayer):
            return True

        # Check 5: If the file is a vector
        if isinstance(layer, QgsRasterLayer):
            return True

        return False

    def add_flo2d_logo(self):
        """
        Function to add the flo2d logo to recent projects
        """

        thumbnail = QSettings().value('UI/recentProjects/1/previewImage')

        picture = Image.open(thumbnail)

        # Open the logo
        logo_path = self.plugin_dir + "/img/F2D 400 Transparent.png"
        logo = Image.open(logo_path)

        # Resize the logo to your desired size
        logo = logo.resize((100, 30))

        # Choose the position to paste the logo on the picture
        position = (10, 10)

        # Paste the logo on the picture
        picture.paste(logo, position, logo)

        # Save the result
        picture.save(thumbnail)

    def layerAdded(self, layers):
        """
        This function does two things:
            1. Check the layer name and rename it if necessary to avoid duplicated layers
            2. Force all layers added to the user on the top of the layer tree
        """

        for layer in layers:
            layer_name = layer.name()
            layer_source = layer.source()
            try:
                gpkg_path = self.gutils.get_gpkg_path()
                layer_source = layer_source.replace('/', '\\')
                if layer_name in self.lyrs.layer_names and gpkg_path not in layer_source:
                    renamed_layer = layer_name + '_ext'
                    layer.setName(renamed_layer)
                    self.uc.bar_warn('FLO-2D Plugin does not allow layers with the name equal to the FLO-2D layers! The '
                                     f'{layer_name} layer was renamed to {renamed_layer}.')
                    self.uc.log_info(f'FLO-2D Plugin does not allow layers with the name equal to the FLO-2D layers! The '
                                     f'{layer_name} layer was renamed to {renamed_layer}.')
            except:
                pass

        self.iface.layerTreeView().setCurrentIndex(
            self.iface.layerTreeView().layerTreeModel().node2index(self.project.layerTreeRoot()))

    def change_external_layer_type(self, layer_ids):
        """
        Function to update the layer type on the external_layers table
        """
        gpkg = self.read_proj_entry("gpkg")
        uri = self.project.fileName()
        if not gpkg:
            return
        if not uri.startswith("geopackage:"):
            return

        self.con = database_connect(gpkg)
        self.gutils = GeoPackageUtils(self.con, self.iface)
        try:
            for layer_id in layer_ids:
                layer = QgsProject.instance().mapLayer(layer_id)
                if layer:
                    layer_name = layer.name()
                    external_layers = self.gutils.execute(
                        f"SELECT fid FROM external_layers WHERE name = '{layer_name}' AND type = 'user';").fetchall()
                    if external_layers:
                        fid = external_layers[0][0]
                        self.gutils.execute(f"DELETE FROM external_layers WHERE fid = '{fid}';")
        except:
            pass