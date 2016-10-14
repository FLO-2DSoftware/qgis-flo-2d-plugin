# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Flo2D
                                 A QGIS plugin
 FLO-2D tools for QGIS
                              -------------------
        begin                : 2016-08-28
        git sha              : $Format:%H$
        copyright            : (C) 2016 by Lutra Consulting for FLO-2D
        email                : info@lutraconsulting.co.uk
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import os
import time
import traceback
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import uic
from qgis.gui import QgsProjectionSelectionWidget, QgsMapToolIdentify
from qgis.core import *
from flo2d_dialog import Flo2DDialog
from layers import Layers
from user_communication import UserCommunication
from flo2dgeopackage import *
from grid_tools import square_grid, roughness2grid
from info_tool import InfoTool
from utils import *

from .gui.dlg_xsec_editor import XsecEditorDialog
from .gui.dlg_inflow_editor import InflowEditorDialog
from .gui.dlg_rain_editor import RainEditorDialog
from .gui.dlg_evap_editor import EvapEditorDialog
from .gui.dlg_outflow_editor import OutflowEditorDialog
from .gui.dlg_settings import SettingsDialog


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
        self.actions = []
        self.menu = self.tr(u'&Flo2D')
        self.toolbar = self.iface.addToolBar(u'Flo2D')
        self.toolbar.setObjectName(u'Flo2D')
        self.con = None
        self.lyrs = Layers(iface)
        self.gpkg = None
        self.prep_sql = None
        self.set_editors_map()

        self.create_map_tools()

        # connections
        self.info_tool.feature_picked.connect(self.get_feature_info)

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.
        """
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
            callback=self.import_gds,
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/export_gds.svg'),
            text=self.tr(u'Export GDS files'),
            callback=self.export_gds,
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/info_tool.svg'),
            text=self.tr(u'Info Tool'),
            callback=self.identify,
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/create_model_boundary.svg'),
            text=self.tr(u'Create Modeling Boundary'),
            callback=self.create_model_boundary,
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/create_grid.svg'),
            text=self.tr(u'Create Grid'),
            callback=self.create_grid,
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/create_model_boundary.svg'),
            text=self.tr(u'Roughness probing'),
            callback=self.get_roughness,
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/xsec_editor.svg'),
            text=self.tr(u'XSection Editor'),
            callback=self.show_xsec_editor,
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/rain_editor.svg'),
            text=self.tr(u'Rain Editor'),
            callback=self.show_rain_editor,
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'img/evaporation_editor.svg'),
            text=self.tr(u'Evaporation Editor'),
            callback=self.show_evap_editor,
            parent=self.iface.mainWindow())

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        database_disconnect(self.con)
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Flo2D'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar
        del self.con, self.gpkg, self.lyrs

    def show_settings(self):
        dlg_settings = SettingsDialog(self.con, self.iface, self.lyrs, self.gpkg)
        dlg_settings.show()
        result = dlg_settings.exec_()
        if result:
            dlg_settings.write()
            self.con = dlg_settings.con
            self.gpkg = dlg_settings.gpkg
            self.crs = dlg_settings.crs

    def call_methods(self, calls, debug, *args):
        for call in calls:
            dat = call.split('_')[-1].upper() + '.DAT'
            if call.startswith('import') and self.gpkg.parser.dat_files[dat] is None:
                self.uc.log_info('Files required for "{0}" not found. Action skipped!'.format(call))
                continue
            else:
                pass
            try:
                start_time = time.time()
                method = getattr(self.gpkg, call)
                method(*args)
                self.uc.log_info('{0:.3f} seconds => "{1}"'.format(time.time() - start_time, call))
            except Exception as e:
                if debug is True:
                    self.uc.log_info(traceback.format_exc())
                else:
                    raise

    def import_gds(self):
        """Import traditional GDS files into FLO-2D database (GeoPackage)"""
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
            self.gpkg.set_parser(fname)
            if bname in self.gpkg.parser.dat_files:
                empty = self.gpkg.is_table_empty('grid')
                # check if a grid exists in the grid table
                if not empty:
                    r = self.uc.question('There is a grid already defined in GeoPackage. Overwrite it?')
                    if r == QMessageBox.Yes:
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
                rc = self.gpkg.execute(sql, data)
                del rc

                # load layers and tables
                self.load_layers()
                self.uc.bar_info('Flo2D model imported', dur=3)
            else:
                pass
            QApplication.restoreOverrideCursor()
        else:
            pass

    def load_layers(self):
        self.lyrs.load_all_layers(self.gpkg)

    def export_gds(self):
        """Export traditional GDS files into FLO-2D database (GeoPackage)"""
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
        outdir = QFileDialog.getExistingDirectory(None, 'Select directory where FLO-2D model will be exported', directory=last_dir)
        if outdir:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            s.setValue('FLO-2D/lastGdsDir', outdir)
            self.call_methods(export_calls, True, outdir)
            self.uc.bar_info('Flo2D model exported', dur=3)
            QApplication.restoreOverrideCursor()

    def create_model_boundary(self):
        """Create model boundary and get grid cell size from user"""
        if not self.gpkg:
            self.uc.bar_warn("Define a database connections first!")
            return
        self.get_cell_size()
        bl = self.lyrs.get_layer_by_name("Model Boundary", group=self.lyrs.group).layer()
        self.iface.setActiveLayer(bl)
        bl.startEditing()
        self.iface.actionAddFeature().trigger()

    def get_cell_size(self):
        """Ask for cell size if not defined in cont table"""
        if not self.gpkg:
            self.uc.bar_warn("Define a database connections first!")
            return
        # is cell size defined?
        if not self.gpkg.get_cont_par("CELLSIZE"):
            r, ok = QInputDialog.getInt(None, "Grid Cell Size", "Enter grid element cell size", min=1, max=99999)
            if ok:
                cell_size = r
            else:
                return
            # save cell size to table cont
            sql = '''UPDATE cont SET value = ? WHERE name='CELLSIZE';'''
            rc = self.gpkg.execute(sql, (cell_size, ))
            del rc

    def create_grid(self):
        self.get_cell_size()
        if not self.gpkg:
            self.uc.bar_warn("Define a database connections first!")
            return
        self.gpkg = GeoPackageUtils(self.con, self.iface)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        bl = self.lyrs.get_layer_by_name("Model Boundary", group=self.lyrs.group).layer()
        square_grid(self.gpkg, bl)
        grid_lyr = self.lyrs.get_layer_by_name("Grid", group=self.lyrs.group).layer()
        if grid_lyr:
            grid_lyr.triggerRepaint()
        QApplication.restoreOverrideCursor()

    def get_roughness(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        grid_lyr = self.lyrs.get_layer_by_name("Grid", group=self.lyrs.group).layer()
        rough_lyr = self.lyrs.get_layer_by_name("Roughness", group=self.lyrs.group).layer()
        roughness2grid(grid_lyr, rough_lyr, 'man')
        if grid_lyr:
            grid_lyr.triggerRepaint()
        QApplication.restoreOverrideCursor()

    def show_xsec_editor(self, fid=None):
        """Show Cross-section editor"""
        if not self.gpkg:
            self.uc.bar_warn("Define a database connections first!")
            return
        self.dlg_xsec_editor = XsecEditorDialog(self.con, self.iface, self.lyrs, fid)
        self.dlg_xsec_editor.rejected.connect(self.lyrs.clear_rubber)
        self.dlg_xsec_editor.show()

    def show_inflow_editor(self, fid=None):
        """Show inflows editor"""
        if not self.gpkg:
            self.uc.bar_warn("Define a database connections first!")
            return
        self.dlg_inflow_editor = InflowEditorDialog(self.con, self.iface, fid)
        self.dlg_inflow_editor.show()

    def show_outflow_editor(self, fid=None):
        """Show outflows editor"""
        if not self.gpkg:
            self.uc.bar_warn("Define a database connections first!")
            return
        self.dlg_outflow_editor = OutflowEditorDialog(self.con, self.iface, fid)
        self.dlg_outflow_editor.show()

    def show_rain_editor(self):
        """Show rain editor"""
        if not self.gpkg:
            self.uc.bar_warn("Define a database connections first!")
            return
        self.dlg_rain_editor = RainEditorDialog(self.con, self.iface)
        self.dlg_rain_editor.show()

    def show_evap_editor(self):
        """Show evaporation editor"""
        if not self.gpkg:
            self.uc.bar_warn("Define a database connections first!")
            return
        self.dlg_evap_editor = EvapEditorDialog(self.con, self.iface)
        self.dlg_evap_editor.show()

    def create_map_tools(self):
        self.canvas = self.iface.mapCanvas()
        self.info_tool = InfoTool(self.canvas, self.lyrs)

    def identify(self):
        if not self.gpkg:
            self.uc.bar_warn("Define a database connections first!")
            return
        self.canvas.setMapTool(self.info_tool)

    def get_feature_info(self, table, fid):
        # what is the proper dialog for this kind of feature?
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
