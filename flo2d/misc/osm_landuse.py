import processing
from qgis.core import (QgsProject)
from qgis.PyQt.QtCore import QVariant
from ..user_communication import UserCommunication
from ..geopackage_utils import GeoPackageUtils


class OSMLanduse(object):
    """Class to classify landuse from OSM"""
    def __init__(self, iface):
        """Initialize the required layers"""
        self.iface = iface
        self.uc = UserCommunication(iface, "FLO-2D")

    def add_layer_to_top(self, layer):
        project = QgsProject.instance()
        layers = project.mapLayers()
        layer_ids = [layer.id() for layer in project.mapLayers().values()]
        project.addMapLayer(layer, False)
        for id in layer_ids:
            layer = layers[id]
            project.moveLayer(layer, len(layer_ids))

    def raster_calculator(self, input, band1, band2, band3):

        alg_params = {'EXPRESSION': f'"OSM@1" = {band1} AND \n"OSM@2" = {band2} AND \n"OSM@3" = {band3}',
                      'LAYERS': input,
                      'CRS': QgsProject.instance().crs(),
                      'OUTPUT': 'TEMPORARY_OUTPUT'}

        return processing.run("qgis:rastercalculator", alg_params)['OUTPUT']

    def landuse_calculator(self, layer, input: list, value):

        raster_sum = ""
        for raster in input:
            raster_sum += raster + "@1 + "

        raster_sum = raster_sum[:-3]
        expression = f"IF(({raster_sum}) = 1, {value}, 0)"
        alg_params = {'EXPRESSION': expression,
                      'LAYERS': layer,
                      'CRS': QgsProject.instance().crs(),
                      'OUTPUT': 'TEMPORARY_OUTPUT'}

        return processing.run("qgis:rastercalculator", alg_params)['OUTPUT']

    def landuse_rasterizor(self, layer, input:list):

        raster_sum = ""
        for raster in input:
            raster_sum += raster + "@1 + "

        raster_sum = raster_sum[:-3]
        alg_params = {'EXPRESSION': raster_sum,
                      'LAYERS': layer,
                      'CRS': QgsProject.instance().crs(),
                      'OUTPUT': 'TEMPORARY_OUTPUT'}

        return processing.run("qgis:rastercalculator", alg_params)['OUTPUT']

    def landuse_vectorizor(self, raster, grid_lyr):

        # vectorize the landuse raster
        alg_params = {'INPUT': raster,
                      'BAND': 1,
                      'FIELD': 'DN',
                      'OUTPUT': 'TEMPORARY_OUTPUT'}
        vector_landuse = processing.run("gdal:polygonize", alg_params)['OUTPUT']

        # dissolve grid for speed up
        alg_params = {'INPUT': grid_lyr,
                      'OUTPUT': 'TEMPORARY_OUTPUT'}
        dissolved = processing.run("native:dissolve", alg_params)['OUTPUT']

        # clip landuse vector with dissolved grid
        alg_params = {"INPUT": vector_landuse,
                      "OVERLAY": dissolved,
                      "OUTPUT": 'TEMPORARY_OUTPUT'}
        return processing.run("native:clip", alg_params)["OUTPUT"]








