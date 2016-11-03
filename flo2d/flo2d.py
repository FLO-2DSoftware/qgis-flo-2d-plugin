# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import time
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.gui import QgsProjectionSelectionWidget
from qgis.core import *
from layers import Layers
from geopackage_utils import *
from flo2dgeopackage import Flo2dGeoPackage
from grid_tools import square_grid, update_roughness, update_elevation, evaluate_arfwrf
from schematic_tools import schematize_channels, schematize_streets, generate_schematic_levees
from info_tool import InfoTool
from grid_info_tool import GridInfoTool
from utils import *

from .gui.dlg_xsec_editor import XsecEditorDialog
from .gui.dlg_inflow_editor import InflowEditorDialog
from .gui.dlg_rain_editor import RainEditorDialog
from .gui.dlg_evap_editor import EvapEditorDialog
from .gui.dlg_outflow_editor import OutflowEditorDialog
from .gui.dlg_settings import SettingsDialog
from .gui.dlg_sampling_elev import SamplingElevDialog
from .gui.dlg_sampling_mann import SamplingManningDialog
from .gui.dlg_grid_info_dock import GridInfoDock
from .gui.dlg_levee_elev import LeveesToolDialog


class Flo2D(object):

    def __init__(self, iface):
        self.iface = iface
        # initialize plugin directory
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
        self.lyrs = Layers(iface)
        self.lyrs.group = None
        self.gutils = None
        self.f2g = None
        self.prep_sql = None
        self.create_grid_info_dock()
        self.set_editors_map()
        self.create_map_tools()

        # connections
        self.project.readProject.connect(self.load_gpkg_from_proj)

    def tr(self, message):
        """Get the translation for a string using Qt translation API."""
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('Flo2D', message)

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
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        self.add_action(
            os.path.join(self.plugin_dir, 'img/settings.svg'),
            text=self.tr(u'Settings'),
            callback=self.show_settings,
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
            os.path.join(self.plugin_dir, 'img/info_tool.svg'),
            text=self.tr(u'Info Tool'),
            callback=self.identify,
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/create_grid.svg'),
            text=self.tr(u'Create Grid'),
            callback=lambda: self.create_grid(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/sample_elev.svg'),
            text=self.tr(u'Sampling Grid Elevation'),
            callback=lambda: self.get_elevation(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/sample_manning.svg'),
            text=self.tr(u'Sampling Manning\'s n'),
            callback=lambda: self.get_roughness(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/eval_arfwrf.svg'),
            text=self.tr(u'Evaluate Reduction Factors (ARF and WRF)'),
            callback=lambda: self.eval_arfwrf(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/grid_info_tool.svg'),
            text=self.tr(u'Grid Info Tool'),
            callback=lambda: self.activate_grid_info_tool(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/xsec_editor.svg'),
            text=self.tr(u'XSection Editor'),
            callback=lambda: self.show_xsec_editor(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/rain_editor.svg'),
            text=self.tr(u'Rain Editor'),
            callback=lambda: self.show_rain_editor(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/evaporation_editor.svg'),
            text=self.tr(u'Evaporation Editor'),
            callback=lambda: self.show_evap_editor(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/sample_elev.svg'),
            text=self.tr(u'Assign Elevation from polygons'),
            callback=lambda: self.single_elevation(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/set_levee_elev.svg'),
            text=self.tr(u'Levee Elevation Tool'),
            callback=lambda: self.show_levee_elev_tool(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/schematize_channels.svg'),
            text=self.tr(u'Schematize channels'),
            callback=lambda: self.schematize_channels(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/schematize_streets.svg'),
            text=self.tr(u'Schematize streets'),
            callback=lambda: self.schematize_streets(),
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/schematize_levees.svg'),
            text=self.tr(u'Generate Schematic Levees'),
            callback=lambda: self.schematize_levees(),
            parent=self.iface.mainWindow())

    def create_grid_info_dock(self):
        self.grid_info_dock = GridInfoDock(self.iface, self.lyrs)
        self.iface.addDockWidget(Qt.LeftDockWidgetArea, self.grid_info_dock)

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        database_disconnect(self.con)
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Flo2D'),
                action)
            self.iface.removeToolBarIcon(action)
        if self.grid_info_dock is not None:
            self.grid_info_dock.close()
            self.iface.removeDockWidget(self.grid_info_dock)

        # remove the toolbar
        del self.toolbar
        del self.con, self.gutils, self.lyrs
        # remove maptools
        del self.info_tool, self.grid_info_tool

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
            self.gutils = dlg_settings.gutils
            self.crs = dlg_settings.crs
            self.write_proj_entry('gpkg', self.gutils.get_gpkg_path().replace('\\', '/'))
        self.grid_info_dock.setVisible(True)

    def load_gpkg_from_proj(self):
        """If QGIS project has a gpkg path saved ask user if it should be loaded"""
        old_gpkg = self.read_proj_entry('gpkg')
        if old_gpkg:
            msg = 'This QGIS project was used to work with the FLO-2D plugin and\n'
            msg += 'the following database file:\n'
            msg += '{}\n\n Load the model?'.format(old_gpkg)
            if self.uc.question(msg):
                dlg_settings = SettingsDialog(self.con, self.iface, self.lyrs, self.gutils)
                dlg_settings.connect(old_gpkg)
                self.con = dlg_settings.con
                self.gutils = dlg_settings.gutils
                self.crs = dlg_settings.crs
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
        """Import traditional GDS files into FLO-2D database (GeoPackage)"""
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
        if fname:
            s.setValue('FLO-2D/lastGdsDir', os.path.dirname(fname))
            QApplication.setOverrideCursor(Qt.WaitCursor)
            bname = os.path.basename(fname)
            self.f2g.set_parser(fname)
            if bname in self.f2g.parser.dat_files:
                empty = self.f2g.is_table_empty('grid')
                # check if a grid exists in the grid table
                if not empty:
                    q = 'There is a grid already defined in GeoPackage. Overwrite it?'
                    if self.uc.question(q):
                        pass
                    else:
                        self.uc.bar_info('Import cancelled', dur=3)
                        return
                else:
                    pass
                self.call_methods(import_calls, True)

                # save CRS to table cont
                sql = '''INSERT INTO cont (name, value) VALUES ('PROJ', ?);'''
                data = (self.crs.toProj4(), )
                rc = self.gutils.execute(sql, data)
                del rc

                # load layers and tables
                self.load_layers()
                self.uc.bar_info('Flo2D model imported', dur=3)
            else:
                pass
            QApplication.restoreOverrideCursor()
        else:
            pass

    @connection_required
    def export_gds(self):
        """Export traditional GDS files into FLO-2D database (GeoPackage)"""
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

    def load_layers(self):
        self.lyrs.load_all_layers(self.gutils)
        self.lyrs.repaint_layers()
        self.lyrs.zoom_to_all()

    def get_cell_size(self):
        """Get cell size from:
            - model boundary attr table (if defined, will be written to cont table)
            - cont table
            - ask user
        """
        bl = self.lyrs.get_layer_by_name("Model Boundary", group=self.lyrs.group).layer()
        bfeat = bl.getFeatures().next()
        if bfeat['cell_size']:
            cs = bfeat['cell_size']
            self.gutils.set_cont_par('CELLSIZE', cs)
        else:
            cs = self.gutils.get_cont_par('CELLSIZE')
            cs = None if cs == '' else cs
        if cs:
            return cs
        else:
            r, ok = QInputDialog.getDouble(None, "Grid Cell Size", "Enter grid element cell size", value=100, min=0.1, max=99999)
            if ok:
                cs = r
                self.gutils.set_cont_par('CELLSIZE', cs)
            else:
                return None

    @connection_required
    def create_grid(self):
        if not self.lyrs.save_edits_and_proceed("Model Boundary"):
            return
        if self.gutils.is_table_empty('user_model_boundary'):
            self.uc.bar_warn("There is no model boundary! Please digitize it before running tool.")
            return
        if not self.gutils.is_table_empty('grid'):
            if not self.uc.question('There is a grid already saved in the database. Overwrite it?'):
                return
        self.get_cell_size()
        self.uc.progress_bar('Creating grid...')
        self.gutils = GeoPackageUtils(self.con, self.iface)
        bl = self.lyrs.get_layer_by_name("Model Boundary", group=self.lyrs.group).layer()
        result = square_grid(self.gutils, bl)
        grid_lyr = self.lyrs.get_layer_by_name("Grid", group=self.lyrs.group).layer()
        self.lyrs.update_layer_extents(grid_lyr)
        if grid_lyr:
            grid_lyr.triggerRepaint()
        self.uc.clear_bar_messages()
        if result > 0:
            self.uc.show_info("Grid created!")
        else:
            self.uc.show_warn("Creating grid aborted! Please check model boundary layer.")

    @connection_required
    def get_roughness(self):
        if not self.lyrs.save_edits_and_proceed("Roughness"):
            return
        if self.gutils.is_table_empty('user_roughness'):
            self.uc.bar_warn("There is no roughness polygon! Please digitize them before running tool.")
            return
        rough_lyr = self.lyrs.get_layer_by_name("Roughness", group=self.lyrs.group).layer()
        cell_size = self.get_cell_size()
        self.mann_dlg = SamplingManningDialog(self.con, self.iface, self.lyrs, cell_size)
        ok = self.mann_dlg.exec_()
        if ok:
            if self.mann_dlg.allGridElemsRadio.isChecked():
                # do stuff for all grid elems
                pass
            else:
                # update only user polygons
                try:
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    grid_lyr = self.lyrs.get_layer_by_name("Grid", group=self.lyrs.group).layer()
                    update_roughness(self.gutils, grid_lyr, rough_lyr, 'n')
                    QApplication.restoreOverrideCursor()
                    self.uc.show_info("Assigning roughness finished!")
                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.log_info(traceback.format_exc())
                    self.uc.show_warn("Assigning roughness aborted! Please check roughness layer.")
        else:
            pass

    @connection_required
    def single_elevation(self):
        if not self.lyrs.save_edits_and_proceed("Grid Elevation"):
            return
        if self.gutils.is_table_empty('user_elevation_polygons'):
            self.uc.bar_warn("There is no any grid elevation polygons! Please digitize them before running tool.")
            return
        elev_lyr = self.lyrs.get_layer_by_name("Grid Elevation", group=self.lyrs.group).layer()
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            grid_lyr = self.lyrs.get_layer_by_name("Grid", group=self.lyrs.group).layer()
            update_elevation(self.gutils, grid_lyr, elev_lyr, 'elev')
            QApplication.restoreOverrideCursor()
            self.uc.show_info("Assigning grid elevation finished!")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn("Assigning grid elevation aborted! Please check grid elevation layer.")

    @connection_required
    def get_elevation(self):
        if self.gutils.is_table_empty('user_model_boundary'):
            self.uc.bar_warn("There is no model boundary! Please digitize it before running tool.")
            return
        cell_size = self.get_cell_size()
        dlg = SamplingElevDialog(self.con, self.iface, self.lyrs, cell_size)
        ok = dlg.exec_()
        if ok:
            pass
        else:
            return
        res = dlg.probe_elevation()
        if res:
            dlg.show_probing_result_info()

    @connection_required
    def eval_arfwrf(self):
        if not self.gutils.is_table_empty('arfwrf'):
            q = 'There are some ARFs and WRFs already defined in the database. Overwrite it?\n\n'
            q += 'Please, note that the new reduction factors will be evaluated for existing blocked ares ONLY.'
            if not self.uc.question(q):
                return
        if not self.lyrs.save_edits_and_proceed("Blocked areas"):
            return
        if self.gutils.is_table_empty('blocked_areas'):
            self.uc.bar_warn("There is no any blocking polygons! Please digitize them before running tool.")
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        # try:
        grid_lyr = self.lyrs.get_layer_by_name("Grid", group=self.lyrs.group).layer()
        user_arf_lyr = self.lyrs.get_layer_by_name("Blocked areas", group=self.lyrs.group).layer()
        evaluate_arfwrf(self.gutils, grid_lyr, user_arf_lyr)
        arf_lyr = self.lyrs.get_layer_by_name("ARF_WRF", group=self.lyrs.group).layer()
        arf_lyr.reload()
        self.lyrs.update_layer_extents(arf_lyr)

        self.lyrs.update_style_blocked(arf_lyr.id())
        self.iface.mapCanvas().clearCache()
        user_arf_lyr.triggerRepaint()
        QApplication.restoreOverrideCursor()
        self.uc.show_info("ARF and WRF values calculated!")

    @connection_required
    def activate_grid_info_tool(self):
        grid = self.lyrs.get_layer_by_name('Grid', self.lyrs.group)
        if grid:
            self.grid_info_tool.grid = grid.layer()
            self.grid_info_dock.set_info_layer(grid.layer())
            self.grid_info_dock.mann_default = self.gutils.get_cont_par('MANNING')
            self.canvas.setMapTool(self.grid_info_tool)
        else:
            self.uc.bar_warn('There is no grid layer to identify.')

    @connection_required
    def show_xsec_editor(self, fid=None):
        """Show Cross-section editor"""
        try:
            self.dlg_xsec_editor = XsecEditorDialog(self.con, self.iface, self.lyrs, fid)
            self.dlg_xsec_editor.rejected.connect(self.lyrs.clear_rubber)
            self.dlg_xsec_editor.show()
        except IndexError:
            self.uc.bar_warn('There is no cross-section data to display!')

    @connection_required
    def show_inflow_editor(self, fid=None):
        """Show inflows editor"""
        self.dlg_inflow_editor = InflowEditorDialog(self.con, self.iface, fid)
        self.dlg_inflow_editor.show()

    @connection_required
    def show_outflow_editor(self, fid=None):
        """Show outflows editor"""
        try:
            self.dlg_outflow_editor.outflow_clicked(fid)
        except AttributeError:
            self.dlg_outflow_editor = OutflowEditorDialog(self.con, self.iface, self.lyrs, fid)
        self.dlg_outflow_editor.rejected.connect(self.lyrs.clear_rubber)
        self.dlg_outflow_editor.show()

    @connection_required
    def show_rain_editor(self):
        """Show rain editor"""
        try:
            self.dlg_rain_editor = RainEditorDialog(self.con, self.iface)
            self.dlg_rain_editor.show()
        except TypeError:
            self.uc.bar_warn('There is no rain data to display!')

    @connection_required
    def show_evap_editor(self):
        """Show evaporation editor"""
        try:
            self.dlg_evap_editor = EvapEditorDialog(self.con, self.iface)
            self.dlg_evap_editor.show()
        except TypeError:
            self.uc.bar_warn('There is no evaporation data to display!')

    @connection_required
    def show_levee_elev_tool(self):
        """Show levee elevation tool"""
        dlg_levee_elev = LeveesToolDialog(self.con, self.iface, self.lyrs)
        dlg_levee_elev.show()
        ok = dlg_levee_elev.exec_()
        if ok:
            pass
        else:
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            dlg_levee_elev.method()
            QApplication.restoreOverrideCursor()
            self.uc.show_info("Values assigned!")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn("Assigning values aborted! Please check your levees layers.")

    @connection_required
    def schematize_channels(self):
        segments = self.lyrs.get_layer_by_name("Channel Segments", group=self.lyrs.group).layer()
        cell_size = float(self.gutils.get_cont_par('CELLSIZE'))
        try:
            schematize_channels(self.gutils, segments, cell_size)
            chan_schem = self.lyrs.get_layer_by_name("Channel segments (left bank)", group=self.lyrs.group).layer()
            if chan_schem:
                chan_schem.triggerRepaint()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())

    @connection_required
    def schematize_streets(self):
        segments = self.lyrs.get_layer_by_name("Street Lines", group=self.lyrs.group).layer()
        cell_size = float(self.gutils.get_cont_par('CELLSIZE'))
        try:
            schematize_streets(self.gutils, segments, cell_size)
            streets_schem = self.lyrs.get_layer_by_name("Streets", group=self.lyrs.group).layer()
            if streets_schem:
                streets_schem.triggerRepaint()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())

    @connection_required
    def schematize_levees(self):
        """Generate schematic lines for user defined levee lines"""
        levee_lyr = self.lyrs.get_layer_by_name("Levee Lines", group=self.lyrs.group).layer()
        grid_lyr = self.lyrs.get_layer_by_name("Grid", group=self.lyrs.group).layer()
        generate_schematic_levees(self.gutils, levee_lyr, grid_lyr)
        levee_schem = self.lyrs.get_layer_by_name("Levees", group=self.lyrs.group).layer()
        if levee_schem:
            levee_schem.triggerRepaint()

    def create_map_tools(self):
        self.canvas = self.iface.mapCanvas()
        self.info_tool = InfoTool(self.canvas, self.lyrs)
        self.info_tool.feature_picked.connect(self.get_feature_info)
        self.grid_info_tool = GridInfoTool(self.canvas, self.lyrs)
        self.grid_info_tool.grid_elem_picked.connect(self.grid_info_dock.update_fields)

    def identify(self):
        self.canvas.setMapTool(self.info_tool)
        self.info_tool.update_lyrs_list()

    def get_feature_info(self, table, fid):
        try:
            show_editor = self.editors_map[table]
        except KeyError:
            self.uc.bar_info("Not implemented.....")
            return
        show_editor(fid)

    def set_editors_map(self):
        self.editors_map = {
            'chan_elems': self.show_xsec_editor,
            'inflow': self.show_inflow_editor,
            'outflow': self.show_outflow_editor
        }

    def restore_settings(self):
        pass

    def show_help(self, page='index.html'):
        helpFile = 'file:///{0}/help/{1}'.format(self.plugin_dir, page)
        self.uc.log_info(helpFile)
        QDesktopServices.openUrl(QUrl(helpFile))

    def help_clicked(self):
        self.show_help(page='index.html')
