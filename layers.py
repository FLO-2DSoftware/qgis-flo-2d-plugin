# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ViolMapDialog
                                 A QGIS plugin
 Violence Mapping for Public Health Wales
                             -------------------
        begin                : 2016-06-05
        git sha              : $Format:%H$
        copyright            : (C) 2016 by Lutra
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

from PyQt4.QtCore import QObject, pyqtSignal
from PyQt4.QtCore import Qt
import os
from .utils import *

from qgis.core import (
    QgsProject,
    QgsMapLayerRegistry,
    QgsExpression,
    QgsFeatureRequest,
    QgsVectorLayer,
    QgsGeometry,
    QgsLayerTreeLayer
)
from qgis.utils import iface

import utils
from errors import *


class Layers(QObject):
    '''
    Class for managing project layers: load, add to layers tree
    '''

    def __init__(self):
        super(Layers, self).__init__()
        self.root = QgsProject.instance().layerTreeRoot()
    

    def load_layer(self, uri, group, name, style=None, provider='ogr'):
        vlayer = QgsVectorLayer(uri, name, provider)
        if not vlayer.isValid():
            msg = 'Unable to load layer {}'.format(name)
            raise Flo2dLayerInvalid(msg)

        QgsMapLayerRegistry.instance().addMapLayer(vlayer, False)
        grp = self.get_layer_group(group)
        # if a layer exists with the same uri, remove it
        lyr_exists = self.layer_exists_in_group(uri, group)
        if lyr_exists:
            self.remove_layer(lyr_exists)
        # add layer to the group
        grp.addLayer(vlayer)

        if style:
            style_path = get_file_path("styles", style)
            if os.path.isfile(style_path):
                err_msg, res = vlayer.loadNamedStyle(style_path)
                if not res:
                    msg = 'Unable to load style for layer {}.\n{}'.format(name, err_msg)
                    raise Flo2dError(msg)
            else:
                raise Flo2dError('Unable to load style file {}'.format(style_path))

        return vlayer.id()
    
    
    def get_layer_tree_item(self, layer_id):
        if layer_id:
            layeritem = self.root.findLayer(layer_id)
            if not layeritem:
                msg = 'Layer {} doesn\'t exist in the layers tree.'.format(layer_id)
                raise Flo2dLayerNotFound(msg)
            return layeritem
        else:
            raise Flo2dLayerNotFound('Layer id not specified')

    
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
            
    
    def get_layer_group(self, name):
        grp = self.root.findGroup(name)
        if not grp:
            grp = self.root.addGroup(name)
        return grp
    
    
    def layer_exists_in_group(self, uri, group):
        grp = self.root.findGroup(group)
        if grp:
            for lyr in grp.findLayers():
                if lyr.layer().dataProvider().dataSourceUri() == uri:
                    return lyr.layer().id()
        return None


    def remove_layer_by_name(self, name):
        layers = QgsMapLayerRegistry.instance().mapLayersByName(name)
        for layer in layers:
            QgsMapLayerRegistry.instance().removeMapLayer(layer.id())


    def remove_layer(self, layer_id):
        # do nothing if layer id does not exists
        QgsMapLayerRegistry.instance().removeMapLayer(layer_id)
            

    def is_str(self, name):
        if isinstance(name, (str, unicode)):
            return True
        else:
            msg = '{} is of type {}, not a string or unicode'.format(repr(name), type(name))
            raise ViolMapNotString(msg)


