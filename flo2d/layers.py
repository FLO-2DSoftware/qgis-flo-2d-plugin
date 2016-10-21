# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Flo2D
                                 A QGIS plugin
 FLO-2D tools for QGIS
                             -------------------
        begin                : 2016-08-28
        copyright            : (C) 2016 by Lutra Consulting for FLO-2D
        email                : info@lutraconsulting.co.uk
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 FLO-2D Preprocessor tools for QGIS.
"""
from PyQt4.QtCore import QObject
from PyQt4.QtCore import Qt
from PyQt4.QtGui import QColor
import os
from utils import *
from collections import OrderedDict

from qgis.core import (
    QgsProject,
    QgsMapLayerRegistry,
    QgsFeatureRequest,
    QgsVectorLayer
)
from qgis.gui import QgsRubberBand
from errors import *


class Layers(QObject):
    """
    Class for managing project layers: load, add to layers tree
    """

    def __init__(self, iface):
        super(Layers, self).__init__()
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.root = QgsProject.instance().layerTreeRoot()
        self.rb = None
        self.gutils = None
        self.lyrs_to_repaint = []

    def load_layer(self, uri, group, name, subgroup=None, style=None, visible=True, provider='ogr'):
        vlayer = QgsVectorLayer(uri, name, provider)
        if not vlayer.isValid():
            msg = 'Unable to load layer {}'.format(name)
            raise Flo2dLayerInvalid(msg)

        QgsMapLayerRegistry.instance().addMapLayer(vlayer, False)
        if subgroup:
            grp = self.get_subgroup(group, subgroup)
            if not subgroup == 'User Layers' and not subgroup == 'Schematic Layers':
                grp.setExpanded(False)
            else:
                pass
        else:
            grp = self.get_group(group)
        # if a layer exists with the same uri, reload it
        lyr_exists = self.layer_exists_in_group(uri, group)
        if lyr_exists:
            # get the parent tree node and reload the layer completely
            p = self.get_layer_tree_item(lyr_exists).parent()
            self.remove_layer(lyr_exists)
            tree_lyr = p.addLayer(vlayer)

#            # try this - sometimes works....:
#            tree_lyr = self.get_layer_by_name(name, group)
#            tree_lyr.layer().reload()
#            tree_lyr.layer().updateExtents()
#            return tree_lyr.layer().id()
        else:
            # add layer to the group of the tree
            tree_lyr = grp.addLayer(vlayer)
        # set visibility
        if visible:
            vis = Qt.Checked
        else:
            vis = Qt.Unchecked
        tree_lyr.setVisible(vis)
        if style:
            style_path = get_file_path("styles", style)
            if os.path.isfile(style_path):
                err_msg, res = vlayer.loadNamedStyle(style_path)
                if not res:
                    msg = 'Unable to load style for layer {}.\n{}'.format(name, err_msg)
                    raise Flo2dError(msg)
            else:
                raise Flo2dError('Unable to load style file {}'.format(style_path))
        return tree_lyr.layer().id()


    def get_layer_tree_item(self, layer_id):
        if layer_id:
            layeritem = self.root.findLayer(layer_id)
            if not layeritem:
                msg = 'Layer {} doesn\'t exist in the layers tree.'.format(layer_id)
                raise Flo2dLayerNotFound(msg)
            return layeritem
        else:
            raise Flo2dLayerNotFound('Layer id not specified')

    def get_layer_by_name(self, name, group=None):
        if group:
            gr = self.get_group(group)
        else:
            gr = self.root
        if name:
            layers = QgsMapLayerRegistry.instance().mapLayersByName(name)
            layeritem = None
            for layer in layers:
                layeritem = gr.findLayer(layer.id())
                if not layeritem:
                    continue
                else:
                    return layeritem
            if not layeritem:
                msg = 'Layer {} doesn\'t exist in the layers tree.'.format(name)
                raise Flo2dLayerNotFound(msg)
        else:
            raise Flo2dLayerNotFound('Layer name not specified')

    def list_group_vlayers(self, group=None, only_visible=True, skip_views=False):
        if not group:
            grp = self.root
        else:
            grp = self.get_group(group)
        views_list = []

        l = []
        for lyr in grp.findLayers():
            if lyr.layer().type() == 0 and lyr.layer().geometryType() < 3:
                if skip_views and lyr.layer().name() in views_list:
                    continue
                else:
                    if only_visible and not lyr.isVisible():
                        continue
                    else:
                        l.append(lyr.layer())
        return l

    def list_group_rlayers(self, group=None):
        if not group:
            grp = self.root
        else:
            grp = self.get_group(group)
        l = []
        for lyr in grp.findLayers():
            if lyr.layer().type() == 1:
                l.append(lyr.layer())
        return l

    def repaint_layers(self):
        for lyr in self.lyrs_to_repaint:
            lyr.triggerRepaint()
        self.lyrs_to_repaint = []

    def new_group(self, name):
        if isinstance(name, (str, unicode)):
            self.root.addGroup(name)
        else:
            raise Flo2dNotString('{} is not a string or unicode'.format(repr(name)))

    def new_subgroup(self, group, subgroup):
        grp = self.root.findGroup(group)
        grp.addGroup(subgroup)

    def remove_group_by_name(self, name):
        grp = self.root.findGroup(name)
        if grp:
            self.root.removeChildNode(grp)

    def get_group(self, name):
        grp = self.root.findGroup(name)
        if not grp:
            grp = self.root.addGroup(name)
        return grp

    def get_subgroup(self, group, subgroup):
        grp = self.get_group(group)
        subgrp = grp.findGroup(subgroup)
        if not subgrp:
            subgrp = grp.addGroup(subgroup)
        return subgrp

    def layer_exists_in_group(self, uri, group):
        grp = self.root.findGroup(group)
        if grp:
            for lyr in grp.findLayers():
                if lyr.layer().dataProvider().dataSourceUri() == uri:
                    return lyr.layer().id()
        return None

    @staticmethod
    def remove_layer_by_name(name):
        layers = QgsMapLayerRegistry.instance().mapLayersByName(name)
        for layer in layers:
            QgsMapLayerRegistry.instance().removeMapLayer(layer.id())

    @staticmethod
    def remove_layer(layer_id):
        # do nothing if layer id does not exists
        QgsMapLayerRegistry.instance().removeMapLayer(layer_id)

    @staticmethod
    def is_str(name):
        if isinstance(name, (str, unicode)):
            return True
        else:
            msg = '{} is of type {}, not a string or unicode'.format(repr(name), type(name))
            raise Flo2dNotString(msg)

    def load_all_layers(self, gutils):
        self.gutils = gutils
        self.layers_data = OrderedDict([
            ('user_channel_seg', {
                'name': 'Channel Segments',
                'sgroup': 'User Layers',
                'styles': ['user_line.qml'],
                'attrs_edit_widgets': {},
                'module': ['chan']
            }),
            ('user_xsections', {
                'name': 'Cross-sections',
                'sgroup': 'User Layers',
                'styles': ['user_line.qml'],
                'attrs_edit_widgets': {},
                'module': ['chan']
            }),
            ('user_levees', {
                'name': 'Levees',
                'sgroup': 'User Layers',
                'styles': ['user_line.qml'],
                'attrs_edit_widgets': {},
                'module': ['levees']
            }),
            ('user_streets', {
                'name': 'Streets',
                'sgroup': 'User Layers',
                'styles': ['user_line.qml'],
                'attrs_edit_widgets': {},
                'module': ['streets']
            }),
            ('user_model_boundary', {
                'name': 'Model Boundary',
                'sgroup': 'User Layers',
                'styles': ['model_boundary.qml'],
                'attrs_edit_widgets': {},
                'module': ['all']
            }),
            ('user_roughness', {
                'name': 'Roughness',
                'sgroup': 'User Layers',
                'styles': ['user_roughness.qml'],
                'attrs_edit_widgets': {},
                'module': ['all']
            }),
            ('inflow', {
                'name': 'Inflow',
                'sgroup': 'User Layers',
                'styles': ['inflow.qml'],
                'attrs_edit_widgets': {
                    2: {'name': 'ValueMap', 'config': {u'Channel': u'C', u'Floodplain': u'F'}},
                    3: {'name': 'ValueMap', 'config': {u'Inflow': 0, u'Outflow': 1}}
                }
            }),
            ('outflow', {
                'name': 'Outflow',
                'sgroup': 'User Layers',
                'styles': ['outflow.qml'],
                'attrs_edit_widgets': {}
            }),
            ('blocked_areas', {
                'name': 'Blocked areas',
                'sgroup': 'User Layers',
                'styles': ['blocked_areas.qml'],
                'attrs_edit_widgets': {},
                'module': ['redfac']
            }),
            ('mult_areas', {
                'name': 'Multiple Channel Areas',
                'sgroup': 'User Layers',
                'styles': ['mult_areas.qml'],
                'attrs_edit_widgets': {}
            }),
            ('rain_arf_areas', {
                'name': 'Rain ARF Areas',
                'sgroup': 'User Layers',
                'styles': ['rain_arf_areas.qml'],
                'attrs_edit_widgets': {}
            }),
            ('tolspatial', {
                'name': 'Tolerance Areas',
                'sgroup': 'User Layers',
                'styles': ['tolspatial.qml'],
                'attrs_edit_widgets': {},
                'visible': False
            }),
            ('fpfroude', {
                'name': 'Froude numbers for grid elems',
                'sgroup': 'User Layers',
                'styles': ['fpfroude.qml'],
                'attrs_edit_widgets': {}
            }),

            ('breach', {
                'name': 'Breach Locations',
                'sgroup': 'Schematic Layers',
                'styles': ['breach.qml'],
                'attrs_edit_widgets': {},
                'module': ['breach']
            }),
            ('levee_data', {
                'name': 'Levees',
                'sgroup': 'Schematic Layers',
                'styles': ['levee.qml'],
                'attrs_edit_widgets': {},
                'module': ['levees']
            }),
            ('struct', {
                'name': 'Structures',
                'sgroup': 'Schematic Layers',
                'styles': ['struc.qml'],
                'attrs_edit_widgets': {},
                'module': ['struct']
            }),
            ('street_seg', {
                'name': 'Streets',
                'sgroup': 'Schematic Layers',
                'styles': ['street.qml'],
                'attrs_edit_widgets': {},
                'module': ['struct']
            }),
            ('chan', {
                'name': 'Channel segments (left bank)',
                'sgroup': 'Schematic Layers',
                'styles': ['chan.qml'],
                'attrs_edit_widgets': {},
                'module': ['chan']
            }),
            ('chan_elems', {
                'name': 'Cross sections',
                'sgroup': 'Schematic Layers',
                'styles': ['chan_elems.qml'],
                'attrs_edit_widgets': {},
                'visible': True,
                'module': ['chan']
            }),
            ('fpxsec', {
                'name': 'Flodplain cross-sections',
                'sgroup': 'Schematic Layers',
                'styles': ['fpxsec.qml'],
                'attrs_edit_widgets': {}
            }),
            ('chan_confluences', {
                'name': 'Channel confluences',
                'sgroup': 'Schematic Layers',
                'styles': ['chan_confluences.qml'],
                'attrs_edit_widgets': {
                    1: {'name': 'ValueMap', 'config': {u'Tributary': 0, u'Main': 1}}
                }
            }),

            ('grid', {
                'name': 'Grid',
                'sgroup': 'Schematic Layers',
                'styles': ['grid.qml'],
                'attrs_edit_widgets': {}
            }),
            ('blocked_cells', {
                'name': 'ARF_WRF',
                'sgroup': 'Schematic Layers',
                'styles': ['arfwrf.qml'],
                'attrs_edit_widgets': {}
            }),

            ('reservoirs', {
                'name': 'Reservoirs',
                'sgroup': 'Schematic Layers',
                'styles': ['reservoirs.qml'],
                'attrs_edit_widgets': {}
            }),


            ('sed_supply_areas', {
                'name': 'Supply Areas',
                'sgroup': 'Sediment Transport',
                'styles': ['sed_supply_areas.qml'],
                'attrs_edit_widgets': {},
                'visible': False
            }),
            ('sed_group_areas', {
                'name': 'Group Areas',
                'sgroup': 'Sediment Transport',
                'styles': ['sed_group_areas.qml'],
                'attrs_edit_widgets': {},
                'visible': False
            }),
            ('sed_rigid_areas', {
                'name': 'Rigid Bed Areas',
                'sgroup': 'Sediment Transport',
                'styles': ['sed_rigid_areas.qml'],
                'attrs_edit_widgets': {},
                'visible': False
            }),
            ('mud_areas', {
                'name': 'Mud Areas',
                'sgroup': 'Sediment Transport',
                'styles': ['mud_areas.qml'],
                'attrs_edit_widgets': {},
                'visible': False
            }),
            ('sed_groups', {
                'name': 'Sediment Groups',
                'sgroup': 'Sediment Transport Tables',
                'styles': None,
                'attrs_edit_widgets': {},
                'visible': False
            }),
            ('sed_group_cells', {
                'name': 'Group Cells',
                'sgroup': 'Sediment Transport Tables',
                'styles': None,
                'attrs_edit_widgets': {},
                'visible': False
            }),
            ('sed_supply_cells', {
                'name': 'Supply Cells',
                'sgroup': 'Sediment Transport Tables',
                'styles': None,
                'attrs_edit_widgets': {},
                'visible': False
            }),
            ('sed_rigid_cells', {
                'name': 'Rigid Bed Cells',
                'sgroup': 'Sediment Transport Tables',
                'styles': None,
                'attrs_edit_widgets': {},
                'visible': False
            }),
            ('mud_cells', {
                'name': 'Mud Cells',
                'sgroup': 'Sediment Transport Tables',
                'styles': None,
                'attrs_edit_widgets': {},
                'visible': False
            }),
            ('infil_areas_green', {
                'name': 'Areas Green Ampt',
                'sgroup': 'Infiltration layers',
                'styles': ['infil_areas.qml'],
                'attrs_edit_widgets': {},
                'visible': False
            }),
            ('infil_areas_scs', {
                'name': 'Areas SCS',
                'sgroup': 'Infiltration layers',
                'styles': ['infil_areas.qml'],
                'attrs_edit_widgets': {},
                'visible': False
            }),
            ('infil_areas_horton', {
                'name': 'Areas Horton',
                'sgroup': 'Infiltration layers',
                'styles': ['infil_areas.qml'],
                'attrs_edit_widgets': {},
                'visible': False
            })
            ,
            ('infil_areas_chan', {
                'name': 'Areas for Channels',
                'sgroup': 'Infiltration layers',
                'styles': ['infil_areas.qml'],
                'attrs_edit_widgets': {},
                'visible': False
            }),
            ('swmmflo', {
                'name': 'SD Inlets',
                'sgroup': 'Storm Drain',
                'styles': ['swmmflo.qml'],
                'attrs_edit_widgets': {},
                'visible': False
            }),
            ('swmmoutf', {
                'name': 'SD Outlets',
                'sgroup': 'Storm Drain',
                'styles': ['swmmoutf.qml'],
                'attrs_edit_widgets': {},
                'visible': False
            }),
            ('swmmflort', {
                'name': 'Rating tables',
                'sgroup': 'Storm Drain',
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('swmmflort_data', {
                'name': 'Rating Tables Data',
                'sgroup': 'Storm Drain',
                'styles': None,
                'attrs_edit_widgets': {}
            }),

            ('tolspatial_cells', {
                'name': 'Tolerance Cells',
                'sgroup': 'Tables',
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('wstime', {
                'name': 'Water Surface in Time',
                'sgroup': 'Calibration Data',
                'styles': ['wstime.qml'],
                'attrs_edit_widgets': {},
                'visible': False
            }),
            ('wsurf', {
                'name': 'Water Surface',
                'sgroup': 'Calibration Data',
                'styles': ['wsurf.qml'],
                'attrs_edit_widgets': {},
                'visible': False
            }),
            ('cont', {
                'name': 'Control',
                'sgroup': "Tables",
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('inflow_cells', {
                'name': 'Inflow Cells',
                'sgroup': 'Tables',
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('outflow_cells', {
                'name': 'Outflow Cells',
                'sgroup': 'Tables',
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('qh_params', {
                'name': 'QH Parameters',
                'sgroup': 'Tables',
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('qh_params_data', {
                'name': 'QH Parameters Data',
                'sgroup': 'Tables',
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('qh_table', {
                'name': 'QH Tables',
                'sgroup': 'Tables',
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('qh_table_data', {
                'name': 'QH Tables Data',
                'sgroup': 'Tables',
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('inflow_time_series', {
                'name': 'Inflow Time Series',
                'sgroup': 'Tables',
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('inflow_time_series_data', {
                'name': 'Inflow Time Series Data',
                'sgroup': 'Tables',
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('outflow_time_series', {
                'name': 'Outflow Time Series',
                'sgroup': 'Tables',
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('outflow_time_series_data', {
                'name': 'Outflow Time Series Data',
                'sgroup': 'Tables',
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('rain_time_series', {
                'name': 'Rain Time Series',
                'sgroup': 'Tables',
                'styles': None,
                'attrs_edit_widgets': {}
            }),
            ('rain_time_series_data', {
                'name': 'Rain Time Series Data',
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
            ('noexchange_chan_elems', {
                'name': 'No-exchange Channel Elements',
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
            })
        ])
        group = 'FLO-2D_{}'.format(os.path.basename(self.gutils.path).replace('.gpkg', ''))
        self.group = group
        for lyr in self.layers_data:
            data = self.layers_data[lyr]
            if data['styles']:
                lstyle = data['styles'][0]
            else:
                lstyle = None
            uri = self.gutils.path + '|layername={}'.format(lyr)
            try:
                lyr_is_on = data['visible']
            except:
                lyr_is_on = True
            lyr_id = self.load_layer(uri, group, data['name'], style=lstyle, subgroup=data['sgroup'], visible=lyr_is_on)
            if lyr == 'blocked_cells':
                self.update_style_blocked(lyr_id)
            if data['attrs_edit_widgets']:
                c = self.get_layer_tree_item(lyr_id).layer().editFormConfig()
                for attr, widget_data in data['attrs_edit_widgets'].iteritems():
                    c.setWidgetType(attr, widget_data['name'])
                    c.setWidgetConfig(attr, widget_data['config'])
            else:
                pass # no attributes edit widgets config

    def update_style_blocked(self, lyr_id):
        cst = self.gutils.get_cont_par('CELLSIZE')
        if is_number(cst) and not cst == '':
            cs = float(cst)
        else:
            return
        # update geometry gen definitions for WRFs
        s = cs * 0.35
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
        lyr = self.get_layer_tree_item(lyr_id).layer()
        sym = lyr.rendererV2().symbol()
        for nr in range(1, sym.symbolLayerCount()):
            exp = 'make_line(translate(centroid($geometry), {}, {}), translate(centroid($geometry), {}, {}))'
            sym.symbolLayer(nr).setGeometryExpression(exp.format(*dir_lines[nr]))
        # ARF
        exp_arf = '''make_polygon( make_line(translate( $geometry , -{0}, {0}), translate($geometry, {0}, {0}), translate($geometry, {0}, -{0}), translate($geometry, -{0}, -{0}), translate($geometry, -{0}, {0})))'''.format(cs * 0.5)
        sym.symbolLayer(0).setGeometryExpression(exp_arf)

    def show_feat_rubber(self, lyr_id, fid, color=QColor(255, 0, 0)):
        lyr = self.get_layer_tree_item(lyr_id).layer()
        gt = lyr.geometryType()
        self.clear_rubber()
        self.rb = QgsRubberBand(self.canvas, gt)
        self.rb.setColor(color)
        if gt == 2:
            fill_color = color
            fill_color.setAlpha(100)
            self.rb.setFillColor(fill_color)
        self.rb.setWidth(2)
        feat = lyr.getFeatures(QgsFeatureRequest(fid)).next()
        self.rb.setToGeometry(feat.geometry(), lyr)

    def clear_rubber(self):
        if self.rb:
            for i in range(3):
                self.rb.reset(i)

    def zoom_to_all(self):
        grid = self.get_layer_by_name('Grid', self.group)
        extent = grid.layer().extent()
        self.iface.mapCanvas().setExtent(extent)
        self.iface.mapCanvas().refresh()
