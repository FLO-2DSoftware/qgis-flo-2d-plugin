"""
/***************************************************************************
 This code is adapted from:

 InvisibleLayersAndGroups
                             A QGIS plugin
 Make some layers and groups invisible in the QGIS Layer Tree (aka Layers panel).
                             -------------------
        begin                : 2017-03-01
        copyright            : (C) 2017 by German Carrillo, GeoTux
        email                : gcarrillo@linuxmail.org
        source               : https://github.com/gacarrillor/InvisibleLayersAndGroups?tab=readme-ov-file
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

from qgis.core import (
    QgsProject,
    QgsLayerTreeLayer,
    QgsLayerTreeGroup,
    QgsMapLayer,
    Qgis,
)


class InvisibleLayersAndGroups:
    def __init__(self, iface):
        self.iface = iface
        self.ltv = self.iface.layerTreeView()
        self.root = QgsProject.instance().layerTreeRoot()
        QgsProject.instance().readProject.connect(self.readHiddenNodes)

    def runHide(self):
        selectedNodes = self.ltv.selectedNodes(True)
        for node in selectedNodes:
            self.hideNode(node)

    def runShow(self):
        self.showHiddenNodes(self.root)

    def hideNode(self, node, bHide=True):
        if type(node) in (QgsLayerTreeLayer, QgsLayerTreeGroup):
            index = self._get_node_index(node)
            self.ltv.setRowHidden(index.row(), index.parent(), bHide)
            node.setCustomProperty("nodeHidden", "true" if bHide else "false")
            self.ltv.setCurrentIndex(self._get_node_index(self.root))

    def _get_node_index(self, node):
        if Qgis.QGIS_VERSION_INT >= 31800:
            return self.ltv.node2index(
                node
            )  # Takes proxy model into account, introduced in QGIS 3.18
        else:  # Older QGIS versions
            return self.ltv.layerTreeModel().node2index(node)

    def showHiddenNodes(self, group):
        for child in group.children():
            if child.customProperty("nodeHidden") == "true":  # Node is currently hidden
                self.hideNode(child, False)
            if isinstance(child, QgsLayerTreeGroup):  # Continue iterating
                self.showHiddenNodes(child)

    def hideNodesByProperty(self, group):
        for child in group.children():
            if child.customProperty("nodeHidden") == "true":  # Node should be hidden
                self.hideNode(child)
            if isinstance(child, QgsLayerTreeGroup):  # Continue iterating
                self.hideNodesByProperty(child)

    def readHiddenNodes(self):
        """SLOT"""
        self.hideNodesByProperty(self.root)

    def hideLayer(self, mapLayer):
        if isinstance(mapLayer, QgsMapLayer):
            self.hideNode(self.root.findLayer(mapLayer.id()))

    def unhideLayer(self, mapLayer):
        if isinstance(mapLayer, QgsMapLayer):
            self.hideNode(self.root.findLayer(mapLayer.id()), bHide=False)

    def hideGroup(self, group):
        if isinstance(group, QgsLayerTreeGroup):
            self.hideNode(group)
        elif isinstance(group, (str, str)):
            self.hideGroup(self.root.findGroup(group))

    def unhideGroup(self, group):
        if isinstance(group, QgsLayerTreeGroup):
            self.hideNode(group, bHide=False)
        elif isinstance(group, (str, str)):
            group_node = self.root.findGroup(group)
            if group_node:
                self.hideNode(group_node, bHide=False)
