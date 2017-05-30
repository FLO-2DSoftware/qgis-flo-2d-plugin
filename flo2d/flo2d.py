# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

# Lambda may not be necessary
# pylint: disable=W0108

import os
import time
import traceback

from PyQt4.QtCore import QSettings, QCoreApplication, QTranslator, qVersion, Qt, QUrl
from PyQt4.QtGui import QIcon, QAction, QFileDialog, QApplication, QDesktopServices
from qgis.core import QgsProject
from qgis.gui import QgsProjectionSelectionWidget, QgsDockWidget

from layers import Layers
from user_communication import UserCommunication
from geopackage_utils import connection_required, database_disconnect
from flo2d_ie.flo2dgeopackage import Flo2dGeoPackage
from flo2d_tools.grid_info_tool import GridInfoTool
from flo2d_tools.info_tool import InfoTool
from flo2d_tools.channel_profile_tool import ChannelProfile
from flo2d_tools.grid_tools import grid_has_empty_elev
from flo2d_tools.schematic_tools import generate_schematic_levees, DomainSchematizer, Confluences
from gui.dlg_cont_toler import ContTolerDialog
from gui.dlg_evap_editor import EvapEditorDialog
from gui.dlg_levee_elev import LeveesToolDialog
from gui.dlg_schem_xs_info import SchemXsecEditorDialog
from gui.dlg_settings import SettingsDialog
from gui.f2d_main_widget import FLO2DWidget
from gui.grid_info_widget import GridInfoWidget
from gui.plot_widget import PlotWidget
from gui.table_editor_widget import TableEditorWidget
from gui.dlg_schema2user import Schema2UserDialog
from gui.dlg_ras_import import RasImportDialog


class Flo2D(object):

    def __init__(self, iface):
        self.iface = iface
        self.iface.f2d = {}
        self.plugin_dir = os.path.dirname(__file__)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.crs_widget = QgsProjectionSelectionWidget()
        # initialize locale
        s = QSettings()
        locale = s.value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'Flo2D_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.project = QgsProject.instance()
        self.actions = []
        self.menu = self.tr(u'&Flo2D')
        self.toolbar = self.iface.addToolBar(u'Flo2D')
        self.toolbar.setObjectName(u'Flo2D')
        self.con = None
        self.iface.f2d['con'] = self.con
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
        self.dlg_inflow_editor = None
        # connections
        self.project.readProject.connect(self.load_gpkg_from_proj)

    def tr(self, message):
        """
        Get the translation for a string using Qt translation API.
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('Flo2D', message)

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

        self.f2d_widget.xs_editor.schematize_1d.connect(self.schematize_channels)
        self.f2d_widget.xs_editor.find_confluences.connect(self.schematize_confluences)

        self.f2d_widget.grid_tools.setup_connection()
        self.f2d_widget.profile_tool.setup_connection()
        self.f2d_widget.bc_editor.populate_bcs()
        self.f2d_widget.ic_editor.populate_cbos()
        self.f2d_widget.street_editor.setup_connection()
        self.f2d_widget.street_editor.populate_streets()
        self.f2d_widget.struct_editor.populate_structs()
        self.f2d_widget.rain_editor.setup_connection()
        self.f2d_widget.rain_editor.rain_properties()
        self.f2d_widget.xs_editor.setup_connection()
        self.f2d_widget.xs_editor.populate_xsec_cbo()
        self.f2d_widget.fpxsec_editor.setup_connection()
        self.f2d_widget.fpxsec_editor.populate_cbos()
        self.f2d_widget.infil_editor.setup_connection()
        self.f2d_widget.swmm_editor.setup_connection()

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
            parent=None):

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        # INFO: action.triggered pass False to callback if it is decorated!
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)
        return action

    def initGui(self):
        """
        Create the menu entries and toolbar icons inside the QGIS GUI.
        """
        self.add_action(
            os.path.join(self.plugin_dir, 'img/settings.svg'),
            text=self.tr(u'Settings'),
            callback=self.show_settings,
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/gpkg2gpkg.svg'),
            text=self.tr(u'Import from GeoPackage'),
            callback=lambda: self.import_from_gpkg(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/import_gds.svg'),
            text=self.tr(u'Import GDS files'),
            callback=lambda: self.import_gds(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/export_gds.svg'),
            text=self.tr(u'Export GDS files'),
            callback=lambda: self.export_gds(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/import_ras.svg'),
            text=self.tr(u'Import RAS geometry'),
            callback=lambda: self.import_from_ras(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/schematic_to_user.svg'),
            text=self.tr(u'Convert schematic layers to user layers'),
            callback=lambda: self.schematic2user(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/show_cont_table.svg'),
            text=self.tr(u'Set Control Parameters'),
            callback=lambda: self.show_cont_toler(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/profile_tool.svg'),
            text=self.tr(u'Channel Profile'),
            callback=self.channel_profile,
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/info_tool.svg'),
            text=self.tr(u'Info Tool'),
            callback=self.identify,
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/grid_info_tool.svg'),
            text=self.tr(u'Grid Info Tool'),
            callback=lambda: self.activate_grid_info_tool(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/evaporation_editor.svg'),
            text=self.tr(u'Evaporation Editor'),
            callback=lambda: self.show_evap_editor(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/set_levee_elev.svg'),
            text=self.tr(u'Levee Elevation Tool'),
            callback=lambda: self.show_levee_elev_tool(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/help_contents.svg'),
            text=self.tr(u'FlO-2D Help'),
            callback=self.show_help,
            parent=self.iface.mainWindow())

    def create_f2d_dock(self):
        self.f2d_dock = QgsDockWidget()
        self.f2d_dock.setWindowTitle(u'FLO-2D')
        self.f2d_widget = FLO2DWidget(self.iface, self.lyrs, self.f2d_plot, self.f2d_table)
        self.f2d_widget.setSizeHint(350, 600)
        self.f2d_dock.setWidget(self.f2d_widget)
        self.f2d_dock.dockLocationChanged.connect(self.f2d_dock_save_area)

    @staticmethod
    def f2d_dock_save_area(area):
        s = QSettings('FLO2D')
        s.setValue('dock/area', area)

    def create_f2d_plot_dock(self):
        self.f2d_plot_dock = QgsDockWidget()
        self.f2d_plot_dock.setWindowTitle(u'FLO-2D Plot')
        self.f2d_plot = PlotWidget()
        self.f2d_plot.setSizeHint(500, 200)
        self.f2d_plot_dock.setWidget(self.f2d_plot)
        self.f2d_plot_dock.dockLocationChanged.connect(self.f2d_plot_dock_save_area)

    @staticmethod
    def f2d_plot_dock_save_area(area):
        s = QSettings('FLO2D')
        s.setValue('plot_dock/area', area)

    def create_f2d_table_dock(self):
        self.f2d_table_dock = QgsDockWidget()
        self.f2d_table_dock.setWindowTitle(u'FLO-2D Table Editor')
        self.f2d_table = TableEditorWidget(self.iface, self.f2d_plot, self.lyrs)
        self.f2d_table.setSizeHint(350, 200)
        self.f2d_table_dock.setWidget(self.f2d_table)
        self.f2d_table_dock.dockLocationChanged.connect(self.f2d_table_dock_save_area)

    @staticmethod
    def f2d_table_dock_save_area(area):
        s = QSettings('FLO2D')
        s.setValue('table_dock/area', area)

    def create_f2d_grid_info_dock(self):
        self.f2d_grid_info_dock = QgsDockWidget()
        self.f2d_grid_info_dock.setWindowTitle(u'FLO-2D Grid Info')
        self.f2d_grid_info = GridInfoWidget(self.iface, self.lyrs)
        self.f2d_grid_info.setSizeHint(350, 30)
        self.f2d_grid_info_dock.setWidget(self.f2d_grid_info)
        self.f2d_grid_info_dock.dockLocationChanged.connect(self.f2d_grid_info_dock_save_area)

    @staticmethod
    def f2d_grid_info_dock_save_area(area):
        s = QSettings('FLO2D')
        s.setValue('grid_info_dock/area', area)

    def add_docks_to_iface(self):
        s = QSettings('FLO2D')
        ma = s.value('dock/area', Qt.RightDockWidgetArea)
        ta = s.value('table_dock/area', Qt.BottomDockWidgetArea)
        pa = s.value('plot_dock/area', Qt.BottomDockWidgetArea)
        ga = s.value('grid_info_dock/area', Qt.RightDockWidgetArea)
        self.iface.addDockWidget(ga, self.f2d_grid_info_dock)
        self.iface.addDockWidget(ma, self.f2d_dock)
        self.iface.addDockWidget(pa, self.f2d_plot_dock)
        self.iface.addDockWidget(ta, self.f2d_table_dock)

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
            self.iface.removePluginMenu(
                self.tr(u'&Flo2D'),
                action)
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
            if self.f2d_widget.fpxsec_editor is not None:
                self.f2d_widget.fpxsec_editor.close()
                del self.f2d_widget.fpxsec_editor
            if self.f2d_widget.struct_editor is not None:
                self.f2d_widget.struct_editor.close()
                del self.f2d_widget.struct_editor
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
            del self.iface.f2d['con']
        except KeyError as e:
            pass
        del self.con

    @staticmethod
    def save_dock_geom(dock):
        s = QSettings('FLO2D', dock.windowTitle())
        s.setValue('geometry', dock.saveGeometry())

    @staticmethod
    def restore_dock_geom(dock):
        s = QSettings('FLO2D', dock.windowTitle())
        g = s.value('geometry')
        if g:
            dock.restoreGeometry(g)

    def write_proj_entry(self, key, val):
        return self.project.writeEntry('FLO-2D', key, val)

    def read_proj_entry(self, key):
        r = self.project.readEntry('FLO-2D', key)
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
            self.iface.f2d['con'] = self.con
            self.gutils = dlg_settings.gutils
            self.crs = dlg_settings.crs
            self.write_proj_entry('gpkg', self.gutils.get_gpkg_path().replace('\\', '/'))
            self.setup_dock_widgets()

    def load_gpkg_from_proj(self):
        """
        If QGIS project has a gpkg path saved ask user if it should be loaded.
        """
        old_gpkg = self.read_proj_entry('gpkg')
        if old_gpkg:
            msg = 'This QGIS project was used to work with the FLO-2D plugin and\n'
            msg += 'the following database file:\n'
            msg += '{}\n\n Load the model?'.format(old_gpkg)
            if self.uc.question(msg):
                dlg_settings = SettingsDialog(self.con, self.iface, self.lyrs, self.gutils)
                dlg_settings.connect(old_gpkg)
                self.con = dlg_settings.con
                self.iface.f2d['con'] = self.con
                self.gutils = dlg_settings.gutils
                self.crs = dlg_settings.crs
                self.setup_dock_widgets()
            else:
                self.uc.bar_info('Loading last model cancelled', dur=3)
                return

    def call_methods(self, calls, debug, *args):
        for call in calls:
            dat = call.split('_')[-1].upper() + '.DAT'
            if call.startswith('import') and self.f2g.parser.dat_files[dat] is None:
                self.uc.log_info('Files required for "{0}" not found. Action skipped!'.format(call))
                continue
            else:
                pass
            try:
                start_time = time.time()
                method = getattr(self.f2g, call)
                method(*args)
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
            'import_cont_toler',
            'import_mannings_n_topo',
            'import_inflow',
            'import_outflow',
            'import_rain',
            'import_evapor',
            'import_infil',
            'import_chan',
            'import_xsec',
            'import_hystruc',
            'import_street',
            'import_arf',
            'import_mult',
            'import_sed',
            'import_levee',
            'import_fpxsec',
            'import_breach',
            'import_fpfroude',
            'import_swmmflo',
            'import_swmmflort',
            'import_swmmoutf',
            'import_tolspatial',
            'import_wsurf',
            'import_wstime'
        ]
        s = QSettings()
        last_dir = s.value('FLO-2D/lastGdsDir', '')
        fname = QFileDialog.getOpenFileName(None, 'Select FLO-2D file to import', directory=last_dir, filter='CONT.DAT')
        if not fname:
            return
        s.setValue('FLO-2D/lastGdsDir', os.path.dirname(fname))
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            bname = os.path.basename(fname)
            self.f2g.set_parser(fname)
            topo = self.f2g.parser.dat_files['TOPO.DAT']
            if topo is None:
                self.uc.bar_warn('Could not find TOPO.DAT file! Importing GDS files aborted!', dur=3)
                return
            if bname not in self.f2g.parser.dat_files:
                return
            empty = self.f2g.is_table_empty('grid')
            # check if a grid exists in the grid table
            if not empty:
                q = 'There is a grid already defined in GeoPackage. Overwrite it?'
                if self.uc.question(q):
                    pass
                else:
                    self.uc.bar_info('Import cancelled', dur=3)
                    return
            self.call_methods(import_calls, True)

            # save CRS to table cont
            self.gutils.set_cont_par('PROJ', self.crs.toProj4())

            # load layers and tables
            self.load_layers()
            self.uc.bar_info('Flo2D model imported', dur=3)
            self.gutils.enable_geom_triggers()
            # self.show_bc_editor()
            self.gutils.update_rbank()
            self.setup_dock_widgets()
        finally:
            QApplication.restoreOverrideCursor()

    @connection_required
    def export_gds(self):
        """
        Export traditional GDS files into FLO-2D database (GeoPackage).
        """
        self.f2g = Flo2dGeoPackage(self.con, self.iface)
        export_calls = [
            'export_cont_toler',
            'export_mannings_n_topo',
            'export_inflow',
            'export_outflow',
            'export_rain',
            'export_infil',
            'export_evapor',
            'export_chan',
            'export_xsec',
            'export_hystruc',
            'export_street',
            'export_arf',
            'export_mult',
            'export_sed',
            'export_levee',
            'export_fpxsec',
            'export_breach',
            'export_fpfroude',
            'export_swmmflo',
            'export_swmmflort',
            'export_swmmoutf',
            'export_tolspatial',
            'export_wsurf',
            'export_wstime'
        ]
        s = QSettings()
        last_dir = s.value('FLO-2D/lastGdsDir', '')
        outdir = QFileDialog.getExistingDirectory(None,
                                                  'Select directory where FLO-2D model will be exported',
                                                  directory=last_dir)
        if outdir:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            s.setValue('FLO-2D/lastGdsDir', outdir)
            self.call_methods(export_calls, True, outdir)
            self.uc.bar_info('Flo2D model exported', dur=3)
            QApplication.restoreOverrideCursor()

    @connection_required
    def import_from_gpkg(self):
        s = QSettings()
        last_dir = s.value('FLO-2D/lastGpkgDir', '')
        attached_gpkg = QFileDialog.getOpenFileName(
            None,
            'Select GeoPackage with data to import',
            directory=last_dir,
            filter='*.gpkg')
        if not attached_gpkg:
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            s.setValue('FLO-2D/lastGpkgDir', os.path.dirname(attached_gpkg))
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
            self.uc.bar_info('HEC-RAS geometry data imported!')
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.bar_warn('Could not read HEC-RAS file!')
        QApplication.restoreOverrideCursor()

    def load_layers(self):
        self.lyrs.load_all_layers(self.gutils)
        self.lyrs.repaint_layers()
        self.lyrs.zoom_to_all()

    @connection_required
    def show_control_table(self):
        try:
            cont_table = self.lyrs.get_layer_by_name("Control", group=self.lyrs.group).layer()
            index = cont_table.fieldNameIndex('note')
            tab_conf = cont_table.attributeTableConfig()
            tab_conf.setSortExpression('"name"')
            tab_conf.setColumnWidth(index, 250)
            cont_table.setAttributeTableConfig(tab_conf)
            self.iface.showAttributeTable(cont_table)
        except AttributeError as e:
            pass

    @connection_required
    def show_cont_toler(self):
        dlg = ContTolerDialog(self.con, self.iface)
        save = dlg.exec_()
        if save:
            try:
                dlg.save_parameters()
                self.uc.bar_info("Parameters saved!", dur=3)
            except Exception as e:
                self.uc.bar_warn("Could not save parameters! Please check if they are correct.")
                return

    @connection_required
    def activate_grid_info_tool(self):
        self.f2d_grid_info_dock.setUserVisible(True)
        grid = self.lyrs.data['grid']['qlyr']
        if grid:
            self.grid_info_tool.grid = grid
            self.f2d_grid_info.set_info_layer(grid)
            self.f2d_grid_info.mann_default = self.gutils.get_cont_par('MANNING')
            self.canvas.setMapTool(self.grid_info_tool)
        else:
            self.uc.bar_warn('There is no grid layer to identify.')

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
            self.uc.bar_warn('There is no schematic cross-section data to display!')

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
            self.uc.bar_warn('There is no evaporation data to display!')

    @connection_required
    def show_levee_elev_tool(self):
        """
        Show levee elevation tool.
        """
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return
        if self.gutils.is_table_empty('user_levee_lines'):
            self.uc.bar_warn("There is no any user levee lines! Please create them before running tool.")
            return
        # check for grid elements with null elevation
        null_elev_nr = grid_has_empty_elev(self.gutils)
        if null_elev_nr:
            msg = 'The grid has {} elements with null elevation.\nLevee elevation tool requires that all grid elements have elevation defined.'
            self.uc.show_warn(msg.format(null_elev_nr))
            return
        else:
            pass
        # check if user levee layers are in edit mode
        levee_lyrs = ['Elevation Points', 'Levee Lines', 'Elevation Polygons']
        for lyr in levee_lyrs:
            if not self.lyrs.save_edits_and_proceed(lyr):
                return
        # show the dialog
        dlg_levee_elev = LeveesToolDialog(self.con, self.iface, self.lyrs)
        dlg_levee_elev.show()
        ok = dlg_levee_elev.exec_()
        if ok:
            if dlg_levee_elev.methods:
                pass
            else:
                self.uc.show_warn("Please choose at least one crest elevation source!")
                return
        else:
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.schematize_levees()
            for no in sorted(dlg_levee_elev.methods):
                dlg_levee_elev.methods[no]()
            QApplication.restoreOverrideCursor()
            self.uc.show_info("Values assigned!")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn("Assigning values aborted! Please check your crest elevation source layers.")

    @connection_required
    def schematize_channels(self):
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return
        if self.gutils.is_table_empty('user_left_bank'):
            self.uc.bar_warn("There is no any river center lines! Please digitize them before running the tool.")
            return
        if self.gutils.is_table_empty('user_xsections'):
            self.uc.bar_warn("There is no any user cross sections! Please digitize them before running the tool.")
            return
        ds = DomainSchematizer(self.con, self.iface, self.lyrs)
        try:
            ds.process_bank_lines()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn("Schematizing failed on bank lines! "
                              "Please check your user layers.")
            return
        try:
            ds.process_xsections()
            ds.process_attributes()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn("Schematizing failed on cross-sections! "
                              "Please check your user layers.")
            return
        try:
            ds.make_distance_table()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn("Schematizing failed on preparing interpolation table! "
                              "Please check your user layers.")
            return
        chan_schem = self.lyrs.data['chan']['qlyr']
        chan_elems = self.lyrs.data['chan_elems']['qlyr']
        rbank = self.lyrs.data['rbank']['qlyr']
        confluences = self.lyrs.data['chan_confluences']['qlyr']
        self.lyrs.lyrs_to_repaint = [chan_schem, chan_elems, rbank, confluences]
        self.lyrs.repaint_layers()
        if not self.f2d_widget.xs_editor.interp_bed_and_banks():
            self.uc.show_warn("Schematizing failed on interpolating cross-sections values! "
                              "Please check your user layers.")
            return
        idx = self.f2d_widget.xs_editor.xs_cbo.currentIndex()
        self.f2d_widget.xs_editor.cur_xsec_changed(idx)
        self.uc.show_info("1D Domain schematized!")

    @connection_required
    def schematize_confluences(self):
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return
        if self.gutils.is_table_empty('user_left_bank'):
            self.uc.bar_warn("There is no any river center lines! Please digitize them before running the tool.")
            return
        if self.gutils.is_table_empty('user_xsections'):
            self.uc.bar_warn("There is no any user cross sections! Please digitize them before running the tool.")
            return
        try:
            conf = Confluences(self.con, self.iface, self.lyrs)
            conf.calculate_confluences()
            chan_schem = self.lyrs.data['chan']['qlyr']
            chan_elems = self.lyrs.data['chan_elems']['qlyr']
            rbank = self.lyrs.data['rbank']['qlyr']
            confluences = self.lyrs.data['chan_confluences']['qlyr']
            self.lyrs.lyrs_to_repaint = [chan_schem, chan_elems, rbank, confluences]
            self.lyrs.repaint_layers()
            self.uc.show_info("Confluences schematized!")
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn("Schematizing aborted! Please check your 1D user layers.")

    def schematize_levees(self):
        """
        Generate schematic lines for user defined levee lines.
        """
        levee_lyr = self.lyrs.get_layer_by_name("Levee Lines", group=self.lyrs.group).layer()
        grid_lyr = self.lyrs.get_layer_by_name("Grid", group=self.lyrs.group).layer()
        generate_schematic_levees(self.gutils, levee_lyr, grid_lyr)
        levee_schem = self.lyrs.get_layer_by_name("Levees", group=self.lyrs.group).layer()
        if levee_schem:
            levee_schem.triggerRepaint()

    @connection_required
    def schematic2user(self):
        converter_dlg = Schema2UserDialog(self.con, self.iface, self.lyrs, self.uc)
        ok = converter_dlg.exec_()
        if ok:
            if converter_dlg.methods:
                pass
            else:
                self.uc.show_warn("Please choose at least one conversion source!")
                return
        else:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        for no in sorted(converter_dlg.methods):
            converter_dlg.methods[no]()
        self.setup_dock_widgets()
        self.uc.bar_info('Converting schematic layers to user layers finished!')
        QApplication.restoreOverrideCursor()

    def create_map_tools(self):
        self.canvas = self.iface.mapCanvas()
        self.info_tool = InfoTool(self.canvas, self.lyrs)
        self.grid_info_tool = GridInfoTool(self.canvas, self.lyrs)
        self.channel_profile_tool = ChannelProfile(self.canvas, self.lyrs)

    def identify(self):
        self.canvas.setMapTool(self.info_tool)
        self.info_tool.update_lyrs_list()

    def get_feature_info(self, table, fid):
        try:
            show_editor = self.editors_map[table]
            self.cur_info_table = table
        except KeyError:
            self.uc.bar_info("Not implemented.....")
            return
        show_editor(fid)

    def channel_profile(self):
        self.canvas.setMapTool(self.channel_profile_tool)
        self.channel_profile_tool.update_lyrs_list()

    def get_feature_profile(self, table, fid):
        try:
            self.cur_profile_table = table
        except KeyError:
            self.uc.bar_info("Not implemented.....")
            return
        self.show_profile(fid)

    def set_editors_map(self):
        self.editors_map = {
            'user_levee_lines': self.show_user_profile,
            'user_xsections': self.show_xsec_editor,
            'user_streets': self.show_user_profile,
            'user_centerline': self.show_user_profile,
            'chan_elems': self.show_schem_xsec_info,
            'user_left_bank': self.show_user_profile,
            'user_bc_points': self.show_bc_editor,
            'user_bc_lines': self.show_bc_editor,
            'user_bc_polygons': self.show_bc_editor,
            'user_struct': self.show_struct_editor,
            'struct': self.show_struct_editor
        }

    def restore_settings(self):
        pass

    @staticmethod
    def show_help():
        pth = os.path.dirname(os.path.abspath(__file__))
        help_file = 'file:///{0}/help/index.html'.format(pth)
        QDesktopServices.openUrl(QUrl(help_file))
