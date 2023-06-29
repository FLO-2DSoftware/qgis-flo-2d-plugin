import requests
import processing
from qgis.core import (QgsCoordinateReferenceSystem, QgsFeature, QgsField,
                       QgsGeometry, QgsProcessing, QgsVectorLayer, QgsProject)
from qgis.PyQt.QtCore import QVariant
from ..user_communication import UserCommunication

class SsurgoSoil(object):
    """Class to get SSURGO soil data"""

    def __init__(self, grid_lyr: QgsVectorLayer, iface):

        self.grid_lyr = grid_lyr
        self.outputs = {}
        self.grid_lyr_4326 = None
        self.soil_layer = None

        self.uc = UserCommunication(iface, "FLO-2D")

    def postRequest(self):
        """Download soil for AOI using post request and populate self.soil_layer"""

        # create vector layer structure to store data
        self.uc.log_info("Creating POST request...")
        uri = "Polygon?crs=epsg:4326"
        self.soil_layer = QgsVectorLayer(uri, "soil layer", "memory")
        provider = self.soil_layer.dataProvider()
        attributes = []
        attr_dict = [
            {"name": "areasymbol", "type": "str"},
            {"name": "musym", "type": "str"},
            {"name": "muname", "type": "str"},
            {"name": "mukey", "type": "str"},
            {"name": "hzdept_r", "type": "str"},
            {"name": "hzdepb_r", "type": "str"},
            {"name": "sandtotal", "type": "str"},
            {"name": "silttotal", "type": "str"},
            {"name": "claytotal", "type": "str"},
            {"name": "fragsize", "type": "str"},
            {"name": "fragvol ", "type": "str"},

        ]

        # initialize fields
        for field in attr_dict:
            attributes.append(QgsField(field["name"], QVariant.String))
            provider.addAttributes(attributes)
            self.soil_layer.updateFields()

        parameter = {
            'INPUT': self.grid_lyr,
            'TARGET_CRS': 'EPSG:4326',
            'OUTPUT': 'memory:Reprojected'
        }
        self.grid_lyr_4326 = processing.run('native:reprojectlayer', parameter)['OUTPUT']
        aoi_reproj_wkt = self.grid_lyr_4326.extent().asWktPolygon()

        # send post request
        body = {
            "format": "JSON",
            "query": f"""
                SELECT 
                    M.areasymbol,
                    Ma.musym,
                    Ma.muname,
                    Ma.mukey,
                    Ch.hzdept_r,
                    Ch.hzdepb_r,
                    Ch.sandtotal_r, 
                    Ch.silttotal_r,
                    Ch.claytotal_r,
                    Cf.fragsize_r,
                    Cf.fragvol_r
                FROM muaggatt Ma
                    JOIN mupolygon M ON M.mukey = Ma.mukey
                    JOIN component C ON C.mukey = Ma.mukey
                    JOIN chorizon Ch ON Ch.cokey = C.cokey
                    JOIN chfrags Cf ON Cf.chkey = Ch.chkey
                WHERE 
                M.mupolygonkey IN (SELECT 
                        *
                    FROM
                        SDA_Get_Mupolygonkey_from_intersection_with_WktWgs84('{aoi_reproj_wkt.lower()}'))
                    AND M.mukey = Ma.mukey
                """,
                }

        self.uc.log_info(str(body["query"]))

        url = "https://sdmdataaccess.sc.egov.usda.gov/TABULAR/post.rest"
        soil_response = requests.post(url, json=body).json()

        for row in soil_response["Table"]:
            # None attribute for empty data
            row = [None if not attr else attr for attr in row]
            feat = QgsFeature(self.soil_layer.fields())
            # populate data
            for index, col in enumerate(row):
                if index != len(attr_dict):
                    feat.setAttribute(attr_dict[index]["name"], col)
                else:
                    feat.setGeometry(QgsGeometry.fromWkt(col))
            provider.addFeatures([feat])

        # STOPPED HERE!
        # THE POST REQUEST IS WORKING BUT NO FEATURE IS SHOWN ON THE SOIL LAYER
        # THE ATTRIBUTE TABLE IS CORRECT

        QgsProject.instance().addMapLayer(self.soil_layer)

        return

    # def reprojectLayer(self, grid_lyr, target_crs, output=QgsProcessing.TEMPORARY_OUTPUT):
    #     alg_params = {
    #         "INPUT": grid_lyr,
    #         "OPERATION": "",
    #         "TARGET_CRS": target_crs,
    #         "OUTPUT": output,
    #     }
    #     return processing.run(
    #         "native:reprojectlayer",
    #         alg_params,
    #         is_child_algorithm=True,
    #     )["OUTPUT"]

