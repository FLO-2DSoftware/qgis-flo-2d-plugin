import requests
import processing
from qgis.core import (QgsCoordinateReferenceSystem, QgsFeature, QgsField,
                       QgsGeometry, QgsProcessing, QgsVectorLayer, QgsProject,
                       QgsProcessingException)
from qgis.PyQt.QtCore import QVariant
from ..user_communication import UserCommunication
from flo2d.misc.SSURGO.config import CONUS_NLCD_SSURGO
class SsurgoSoil(object):
    """Class to get SSURGO soil data"""

    def __init__(self, grid_lyr: QgsVectorLayer, iface):

        self.grid_lyr = grid_lyr
        self.outputs = {}
        self.grid_lyr_4326 = None
        self.soil_layer = None

        self.uc = UserCommunication(iface, "FLO-2D")

    def setup_ssurgo(self):
        self.uc.log_info("Setting up SSURGO...")

        parameter = {
            'INPUT': self.grid_lyr,
            'TARGET_CRS': 'EPSG:4326',
            'OUTPUT': 'memory:Reprojected'
        }
        self.grid_lyr_4326 = processing.run('native:reprojectlayer', parameter)['OUTPUT']
        uri = "Polygon?crs=epsg:4326"
        self.soil_layer = QgsVectorLayer(uri, "soil layer", "memory")

    def postRequest(self):
        """Download soil for AOI"""

        # create vector layer structure to store data
        self.uc.log_info("Creating POST request...")
        provider = self.soil_layer.dataProvider()
        attributes = []
        attr_dict = [
            {"name": "mupolygonkey", "type": "str"},
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

        # reproject layer
        aoi_reproj_wkt = self.grid_lyr_4326.extent().asWktPolygon()

        # send post request
        body = {
            "format": "JSON",
            "query": f"""
                SELECT 
                    M.mupolygonkey,
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
                    Cf.fragvol_r,  
                    M.mupolygongeo
                FROM mapunit Mu
                    JOIN mupolygon M ON M.mukey = Mu.mukey
                    JOIN muaggatt Ma ON Ma.mukey = Mu.mukey
                    JOIN component C ON C.mukey = Ma.mukey
                    JOIN chorizon Ch ON Ch.cokey = C.cokey
                    JOIN chfrags Cf ON Cf.chkey = Ch.chkey
                WHERE 
                M.mupolygonkey IN (SELECT 
                        *
                    FROM 
                        SDA_Get_Mupolygonkey_from_intersection_with_WktWgs84('{aoi_reproj_wkt.lower()}'))
                """,
                }

        self.uc.log_info(str(body))

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

        # QgsProject.instance().addMapLayer(self.soil_layer)

        return

    def wfsRequest(self):
        """Download soil for AOI using wfs request and populate self.soil_layer"""
        self.uc.log_info("Creating WFS request...")
        request_URL = CONUS_NLCD_SSURGO["SSURGO_Soil"].format(",".join([str(item) for item in self.getExtent(self.grid_lyr_4326)]))
        self.uc.log_info(str(request_URL))
        alg_params = {"URL": request_URL, "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT}
        self.soil_layer = processing.run("native:filedownloader", alg_params)["OUTPUT"]

        return


        # WfsRequest
        # request_URL = CONUS_NLCD_SSURGO["SSURGO_Soil"].format(",".join([str(item) for item in self.getExtent(self.grid_lyr_4326)]))
        # self.outputs["WFSDownload"] = self.downloadFile(request_URL)
        #
        # alg_params = {
        #     "INPUT": self.outputs["WFSDownload"],
        #     "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        # }
        #
        # self.outputs["SwapXAndYCoordinates"] = processing.run(
        #     "native:swapxy",
        #     alg_params,
        # )["OUTPUT"]
        #
        # self.soil_layer = self.outputs["SwapXAndYCoordinates"]

        # QgsProject.instance().addMapLayer(self.soil_layer)

        # # Fix soil layer
        # parameter = {
        #     "INPUT": self.soil_layer,
        #     "OUTPUT": 'memory:FixedGeoms'}
        # self.soil_layer = processing.run('native:fixgeometries', parameter)['OUTPUT']
        #
        # # Clip soil layer
        # parameter = {
        #     "INPUT": self.soil_layer,
        #     "OVERLAY": self.grid_lyr,
        #     "OUTPUT": 'memory:Clipped'}
        #
        # self.soil_layer = processing.run('native:clip', parameter)['OUTPUT']


        # STOPPED HERE!
        # THE POST REQUEST IS WORKING BUT NO FEATURE IS SHOWN ON THE SOIL LAYER
        # THE ATTRIBUTE TABLE IS CORRECT

        # QgsProject.instance().addMapLayer(self.soil_layer)

    def fixGeometries(self):
        alg_params = {"INPUT": self.soil_layer, "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT}
        self.outputs["FixGeometries"] = processing.run("native:fixgeometries",alg_params)["OUTPUT"]
        self.soil_layer = self.outputs["FixGeometries"]
        return

    def clip(self):
        alg_params = {"INPUT": self.soil_layer, "OVERLAY": self.grid_lyr, "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT}
        self.outputs["Clipped"] = processing.run("native:clip", alg_params)["OUTPUT"]
        self.soil_layer = self.outputs["Clipped"]

    def getExtent(self, layer) -> tuple:
        # Get extent of the area boundary layer
        extent = layer.extent()
        xmin = extent.xMinimum()
        ymin = extent.yMinimum()
        xmax = extent.xMaximum()
        ymax = extent.yMaximum()
        return xmin, ymin, xmax, ymax

    def swapXY(self):
        """Swap X and Y coordinates of WFS Download"""
        alg_params = {
            "INPUT": self.outputs["WFSDownload"],
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        self.outputs["SwapXAndYCoordinates"] = processing.run(
            "native:swapxy",
            alg_params,
            is_child_algorithm=True,
        )["OUTPUT"]
        self.soil_layer = self.outputs["SwapXAndYCoordinates"]
        return
