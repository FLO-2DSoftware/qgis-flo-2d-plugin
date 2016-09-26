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
from qgis.gui import QgsProjectionSelectionWidget
from qgis.core import *
from flo2d_dialog import Flo2DDialog
from .user_communication import UserCommunication
from flo2dgeopackage import Flo2dGeoPackage
from .utils import *
from .layers import Layers
from collections import OrderedDict


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
        self.conn = None
        self.lyrs  = Layers()
        self.gpkg = None
        self.prep_sql = None

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
            os.path.join(self.plugin_dir,'img/new_db.svg'),
            text=self.tr(u'Create FLO-2D Database'),
            callback=self.create_db,
            parent=self.iface.mainWindow())
        
        self.add_action(
            os.path.join(self.plugin_dir,'img/connect.svg'),
            text=self.tr(u'Connect to FLO-2D Database'),
            callback=self.connect,
            parent=self.iface.mainWindow())
            
        self.add_action(
            os.path.join(self.plugin_dir,'img/import_gds.svg'),
            text=self.tr(u'Import GDS files'),
            callback=self.import_gds,
            parent=self.iface.mainWindow())
            
        self.add_action(
            os.path.join(self.plugin_dir,'img/export_gds.svg'),
            text=self.tr(u'Export GDS files'),
            callback=self.export_gds,
            parent=self.iface.mainWindow())

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Flo2D'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar
        del self.conn, self.gpkg, self.lyrs

    def create_db(self):
        """Create FLO-2D model database (GeoPackage)"""
        self.gpkg_fname = None
        # CRS
        self.crs_widget.selectCrs()
        if self.crs_widget.crs().isValid():
            self.crs = self.crs_widget.crs()
            auth, crsid = self.crs.authid().split(':')
            proj = 'PROJCS["{}"]'.format(self.crs.toProj4())
        else:
            msg = 'Choose a valid CRS!'
            self.uc.show_warn(msg)
            return
        s = QSettings()
        last_gpkg_dir = s.value('FLO-2D/lastGpkgDir', '')
        gpkg_fname = QFileDialog.getSaveFileName(None,
                         'Create GeoPackage As...',
                         directory=last_gpkg_dir, filter='*.gpkg')
        if not gpkg_fname:
            return
        s.setValue('FLO-2D/lastGpkgDir', os.path.dirname(gpkg_fname))

        self.gpkg = Flo2dGeoPackage(gpkg_fname, self.iface)
        if not self.gpkg.database_create():
            self.uc.show_warn("Couldn't create new database {}\n{}".format(gpkg_fname, self.gpkg.msg))
        else:
            self.uc.log_info("Connected to {}".format(gpkg_fname))
        if self.gpkg.check_gpkg():
            self.uc.bar_info("GeoPackage {} is OK".format(gpkg_fname))
        else:
            self.uc.bar_error("{} is NOT a GeoPackage!".format(gpkg_fname))
        
        # check if the CRS exist in the db
        sql = 'SELECT srs_id FROM gpkg_spatial_ref_sys WHERE organization=? AND organization_coordsys_id=?;'
        rc = self.gpkg.execute(sql, (auth, crsid))
        rt = rc.fetchone()
        if not rt:
            sql = '''INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)'''
            data = (self.crs.description(), crsid, auth, crsid, proj, '',)
            rc = self.gpkg.execute(sql, data)
            del rc
            srsid = crsid
        else:
            srsid = rt[0]
        
        # assign the CRS to all geometry columns
        sql = "UPDATE gpkg_geometry_columns SET srs_id = ?"
        rc = self.gpkg.execute(sql, (srsid,))
        sql = "UPDATE gpkg_contents SET srs_id = ?"
        rc = self.gpkg.execute(sql, (srsid,))
        self.srs_id = srsid

    def connect(self):
        """Connect to FLO-2D model database (GeoPackage)"""
        self.gpkg_fname = None
        s = QSettings()
        last_gpkg_dir = s.value('FLO-2D/lastGpkgDir', '')
        gpkg_fname = QFileDialog.getOpenFileName(None,
                         'Select GeoPackage to connect',
                         directory=last_gpkg_dir)
        if gpkg_fname:
            s.setValue('FLO-2D/lastGpkgDir', os.path.dirname(gpkg_fname))
            self.gpkg = Flo2dGeoPackage(gpkg_fname, self.iface)
            self.gpkg.database_connect()
            self.uc.log_info("Connected to {}".format(gpkg_fname))
            if self.gpkg.check_gpkg():
                self.uc.bar_info("GeoPackage {} is OK".format(gpkg_fname))
                sql = '''SELECT srs_id FROM gpkg_contents WHERE table_name='grid';'''
                rc = self.gpkg.execute(sql)
                rt = rc.fetchone()[0]
                self.srs_id = rt
                self.load_layers()
            else:
                self.uc.bar_error("{} is NOT a GeoPackage!".format(gpkg_fname))
        else:
            pass

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
            #'import_infil',
            'import_chan',
            'import_xsec',
            'import_hystruc',
            'import_street',
            'import_arf',
            'import_mult',
            'import_levee',
            'import_fpxsec',
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
                # load layers and tables
                self.load_layers()
                self.uc.bar_info('Flo2D model imported', dur=3)
            else:
                pass
        else:
            pass

    def load_layers(self):
        self.layers_data = OrderedDict([
        
        # LAYERS
            
            ('levee_data', {
                'name': 'Levees',
                'sgroup': None,
                'styles': ['levee.qml'],
                'attrs_edit_widgets': {}
            }),
            ('struct', {
                'name': 'Structures',
                'sgroup': None,
                'styles': ['struc.qml'],
                'attrs_edit_widgets': {}
            }),
            ('street_seg', {
                'name': 'Streets',
                'sgroup': None,
                'styles': ['street.qml'],
                'attrs_edit_widgets': {}
            }),
            ('chan_r', {
                'name': 'Rectangular Xsec',
                'sgroup': 'XSections',
                'styles': ['xsec.qml'],
                'attrs_edit_widgets': {}
            }),
            ('chan_v', {
                'name': 'Variable Area Xsec',
                'sgroup': 'XSections',
                'styles': ['xsec.qml'],
                'attrs_edit_widgets': {}
            }),
            ('chan_t', {
                'name': 'Trapezoidal Xsec',
                'sgroup': 'XSections',
                'styles': ['xsec.qml'],
                'attrs_edit_widgets': {}
            }),
            ('chan_n', {
                'name': 'Natural Xsec',
                'sgroup': 'XSections',
                'styles': ['xsec.qml'],
                'attrs_edit_widgets': {}
            }),
            ('chan', {
                'name': 'Channel segments (left bank)',
                'sgroup': None,
                'styles': ['chan.qml'],
                'attrs_edit_widgets': {}
            }),
            ('fpxsec', {
                'name': 'Flodplain cross-sections',
                'sgroup': None,
                'styles': ['fpxsec.qml'],
                'attrs_edit_widgets': {}
            }),
            ('chan_confluences', {
                'name': 'Channel confluences',
                'sgroup': None,
                'styles': ['chan_confluences.qml'],
                'attrs_edit_widgets': {
                    1: {'name': 'ValueMap', 'config': {u'Tributary': 0, u'Main': 1}}
                }
            }),
            ('inflow', {
                'name': 'Inflow',
                'sgroup': None,
                'styles': ['inflow.qml'],
                'attrs_edit_widgets': {
                    2: {'name': 'ValueMap', 'config': {u'Channel': u'C', u'Floodplain': u'F'}},
                    3: {'name': 'ValueMap', 'config': {u'Inflow': 0, u'Outflow': 1}}
                }
            }),
            ('outflow', {
                'name': 'Outflow',
                'sgroup': None,
                'styles': ['outflow.qml'],
                'attrs_edit_widgets': {
                    1: {'name': 'ValueMap', 'config': {u'Grid element': u'N', u'Channel element': u'K'}},
                    2: {'name': 'ValueMap', 'config': {u'Channel': 0, u'Floodplain': 1}}
                }
            }),
            ('grid', {
                'name': 'Grid',
                'sgroup': None,
                'styles': ['grid.qml'],
                'attrs_edit_widgets': {}
            }),
            ('rain_arf_areas', {
                'name': 'Rain ARF Areas',
                'sgroup': None,
                'styles': ['rain_arf_areas.qml'],
                'attrs_edit_widgets': {}
            }),
            ('reservoirs', {
                'name': 'Reservoirs',
                'sgroup': None,
                'styles': ['reservoirs.qml'],
                'attrs_edit_widgets': {}
            }),
            ('blocked_areas', {
                'name': 'Area and Width Reduction',
                'sgroup': None,
                'styles': ['blocked_areas.qml'],
                'attrs_edit_widgets': {}
            }),
            ('blocked_areas_tot', {
                'name': 'Totally blocked cells',
                'sgroup': None,
                'styles': ['blocked_areas_tot.qml'],
                'attrs_edit_widgets': {}
            }),
            ('fpfroude', {
                'name': 'Froude numbers for grid elems',
                'sgroup': None,
                'styles': ['fpfroude.qml'],
                'attrs_edit_widgets': {}
            }),
            ('infil_areas_green', {
                'name': 'Areas Green Ampt',
                'sgroup': 'Infiltration layers',
                'styles': ['infil_areas.qml'],
                'attrs_edit_widgets': {}
            }),
            ('infil_areas_scs', {
                'name': 'Areas SCS',
                'sgroup': 'Infiltration layers',
                'styles': ['infil_areas.qml'],
                'attrs_edit_widgets': {}
            }),
            ('infil_areas_horton', {
                'name': 'Areas Horton',
                'sgroup': 'Infiltration layers',
                'styles': ['infil_areas.qml'],
                'attrs_edit_widgets': {}
            })
            ,
            ('infil_areas_chan', {
                'name': 'Areas for Channels',
                'sgroup': 'Infiltration layers',
                'styles': ['infil_areas.qml'],
                'attrs_edit_widgets': {}
            }),

            # TABLES

            ('cont', {
                'name': 'Control',
                'sgroup': "Tables",
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('infil_cells_green', {
                'name': 'Cells Green Ampt',
                'sgroup': "Infiltration Tables",
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('infil_cells_scs', {
                'name': 'Cells SCS',
                'sgroup': "Infiltration Tables",
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('infil_cells_horton', {
                'name': 'Cells Horton',
                'sgroup': "Infiltration Tables",
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('infil_chan_elems', {
                'name': 'Channel elements',
                'sgroup': "Infiltration Tables",
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('outflow_cells', {
                'name': 'Outflow Cells',
                'sgroup': 'Tables',
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('outflow_chan_elems', {
                'name': 'Outflow Channel Elements',
                'sgroup': 'Tables',
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('rain', {
                'name': 'Rain',
                'sgroup': 'Tables',
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('rain_arf_cells', {
                'name': 'Rain ARF Cells',
                'sgroup': "Tables",
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('xsec_n_data', {
                'name': 'Natural xsecs data',
                'sgroup': "Tables",
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('fpxsec_cells', {
                'name': 'Floodplain cross-sections cells',
                'sgroup': "Tables",
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('fpfroude_cells', {
                'name': 'Froude numbers for grid elems',
                'sgroup': "Tables",
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('evapor', {
                'name': 'Evaporation',
                'sgroup': 'Evaporation Tables',
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('evapor_hourly', {
                'name': 'Hourly data',
                'sgroup': "Evaporation Tables",
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('evapor_monthly', {
                'name': 'Monthly data',
                'sgroup': "Evaporation Tables",
                'styles': None,
                'attrs_edit_widgets': {}
            })
        ])
        for lyr in self.layers_data:
            data = self.layers_data[lyr]
            if data['styles']:
                lstyle = data['styles'][0]
            else:
                lstyle = None
            uri = self.gpkg.path + '|layername={}'.format(lyr)
            lyr_id = self.lyrs.load_layer(uri, self.gpkg.group, data['name'], style=lstyle, subgroup=data['sgroup'])
            if lyr == 'blocked_areas':
                self.update_style_blocked(lyr_id)
            if data['attrs_edit_widgets']:
                c = self.lyrs.get_layer_tree_item(lyr_id).layer().editFormConfig()
                for attr, widget_data in data['attrs_edit_widgets'].iteritems():
                    c.setWidgetType(attr, widget_data['name'])
                    c.setWidgetConfig(attr, widget_data['config'])
            else:
                pass # no attributes edit widgets config

    def export_gds(self):
        """Export traditional GDS files into FLO-2D database (GeoPackage)"""
        export_calls = [
            'export_cont',
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
            'export_levee',
            'export_fpxsec',
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
            s.setValue('FLO-2D/lastGdsDir', outdir)
            self.call_methods(export_calls, True, outdir)
            self.uc.bar_info('Flo2D model exported', dur=3)
    
    def update_style_blocked(self, lyr_id):
        if not self.gpkg.cell_size:
            sql = '''SELECT value FROM cont WHERE name='CELLSIZE';'''
            self.gpkg.cell_size = float(self.gpkg.execute(sql).fetchone()[0])
        else:
            pass
        s = self.gpkg.cell_size * 0.44
        dir_lines = {
            1: (-s/2.414, s, s/2.414, s),
            2: (s, s/2.414, s, -s/2.414),
            3: (s/2.414, -s, -s/2.414, -s),
            4: (-s, -s/2.414, -s, s/2.414),
            5: (s/2.414, s, s, s/2.414),
            6: (s, -s/2.414, s/2.414, -s),
            7: (-s/2.414, -s, -s, -s/2.414),
            8: (-s, s/2.414, -s/2.414, s)
        } 
        lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()
        sym = lyr.rendererV2().symbol()
        for nr in range(sym.symbolLayerCount()):
            exp = 'make_line(translate(centroid($geometry), {}, {}), translate(centroid($geometry), {}, {}))'
            sym.symbolLayer(nr).setGeometryExpression(exp.format(*dir_lines[nr+1]))

    def settings(self):
        self.dlg_settings = SettingsDialog(self)
        self.dlg_settings.show()
        result = self.dlg_settings.exec_()
        if result:
            self.dlg_settings.save_settings()

    def restore_settings(self):
        pass

    def show_help(self, page='index.html'):
        helpFile = 'file:///{0}/help/{1}'.format(self.plugin_dir, page)
        self.uc.log_info(helpFile)
        QDesktopServices.openUrl(QUrl(helpFile))

    def help_clicked(self):
        self.show_help(page='index.html')
