import requests
import processing
from qgis.core import (QgsCoordinateReferenceSystem, QgsFeature, QgsField,
                       QgsGeometry, QgsProcessing, QgsVectorLayer, QgsProject,
                       QgsProcessingException)
from qgis.PyQt.QtWidgets import QProgressDialog
from qgis.PyQt.QtCore import QVariant
from ..user_communication import UserCommunication
from flo2d.misc.SSURGO.config import CONUS_NLCD_SSURGO
import math


class SsurgoSoil(object):
    """Class to get SSURGO soil data"""

    def __init__(self, grid_lyr: QgsVectorLayer, iface):
        """Initialize the required layers"""

        self.grid_lyr = grid_lyr
        self.outputs = {}
        self.uc = UserCommunication(iface, "FLO-2D")
        self.url = "https://sdmdataaccess.sc.egov.usda.gov/TABULAR/post.rest"

        self.soil_att_dict = None
        self.soil_att = None
        self.chorizon_att_dict = None
        self.chorizon_att = None
        self.chorizon_prov = None
        self.grid_lyr_4326 = None
        self.soil_layer = None
        self.soil_prov = None
        self.soil_chorizon = None
        self.soil_chfrags = None
        self.ssurgo_layer = None
        self.aoi_reproj_wkt = None
        self.chfrags_att_dict = None
        self.chfrags_att = None
        self.chfrags_prov = None


    def setup_ssurgo(self):
        """Set up the required layers that will be used in this class"""

        # Create the grid layer in the correct projection
        parameter = {
            'INPUT': self.grid_lyr,
            'TARGET_CRS': 'EPSG:4326',
            'OUTPUT': 'memory:Reprojected'
        }
        self.grid_lyr_4326 = processing.run('native:reprojectlayer', parameter)['OUTPUT']
        uri = "Polygon?crs=epsg:4326"

        self.aoi_reproj_wkt = self.grid_lyr_4326.extent().asWktPolygon()

        # Create soil layer
        self.soil_layer = QgsVectorLayer(uri, "soil layer", "memory")
        self.soil_prov = self.soil_layer.dataProvider()
        self.soil_att = []
        self.soil_att_dict = [
            {"name": "hydc", "type": "double"},
            {"name": "abstrinf", "type": "double"},
            {"name": "rtimpf", "type": "double"},
            {"name": "soil_depth", "type": "double"},
            {"name": "psif", "type": "double"},
            {"name": "dthetad", "type": "double"},
            {"name": "dthetan", "type": "double"},
            {"name": "dthetaw", "type": "double"},
            {"name": "wpoint", "type": "double"},
            {"name": "fcapac", "type": "double"},
            {"name": "sat", "type": "double"},
        ]

        # Initialize soil fields
        for field in self.soil_att_dict:
            self.soil_att.append(QgsField(field["name"], QVariant.Double))
            self.soil_prov.addAttributes(self.soil_att)
            self.soil_layer.updateFields()

        # Create chorizon layer
        self.soil_chorizon = QgsVectorLayer(uri, "chorizon", "memory")
        self.chorizon_prov = self.soil_chorizon.dataProvider()
        self.chorizon_att = []
        self.chorizon_att_dict = [
            {"name": "mupolygonkey", "type": "str"},
            {"name": "mukey", "type": "str"},
            {"name": "hzdept_r", "type": "double"},
            {"name": "hzdepb_r", "type": "double"},
            {"name": "sandtotal", "type": "double"},
            {"name": "silttotal", "type": "double"},
            {"name": "claytotal", "type": "double"},
            {"name": "orgmat", "type": "double"},
        ]

        # Initialize chorizon fields
        for field in self.chorizon_att_dict:
            if field["type"] == "double":
                self.chorizon_att.append(QgsField(field["name"], QVariant.Double))
            else:
                self.chorizon_att.append(QgsField(field["name"], QVariant.String))
            self.chorizon_prov.addAttributes(self.chorizon_att)
            self.soil_chorizon.updateFields()

        # Create the chfrags layer
        self.soil_chfrags = QgsVectorLayer(uri, "chorizon", "memory")
        self.chfrags_prov = self.soil_chfrags.dataProvider()
        self.chfrags_att = []
        self.chfrags_att_dict = [
            {"name": "mupolygonkey", "type": "str"},
            {"name": "mukey", "type": "str"},
            {"name": "fragsize", "type": "double"},
            {"name": "fragvol ", "type": "double"},
         ]

        # Initialize chfrags fields
        for field in self.chfrags_att_dict:
            if field["type"] == "double":
                self.chfrags_att.append(QgsField(field["name"], QVariant.Double))
            else:
                self.chfrags_att.append(QgsField(field["name"], QVariant.String))
            self.chfrags_prov.addAttributes(self.chfrags_att)
            self.soil_chfrags.updateFields()

        self.ssurgo_layer = QgsVectorLayer(uri, "ssurgo", "memory")

    def downloadChorizon(self):
        """Method for downloading the chrozion layer using PostRequest"""

        # Chorizon post request
        body = {
            "format": "JSON",
            "query": f"""
                        SELECT 
                            M.mupolygonkey,
                            C.mukey,
                            Ch.hzdept_r,
                            Ch.hzdepb_r,
                            Ch.sandtotal_r, 
                            Ch.silttotal_r,
                            Ch.claytotal_r,
                            Ch.om_r,
                            M.mupolygongeo
                        FROM chorizon Ch
                            JOIN component C ON C.cokey = Ch.cokey
                            JOIN mupolygon M ON M.mukey = C.mukey
                        WHERE 
                        Ch.hzdept_r = 0
                        AND
                        M.mupolygonkey IN (SELECT 
                                *
                            FROM 
                                SDA_Get_Mupolygonkey_from_intersection_with_WktWgs84('{self.aoi_reproj_wkt.lower()}'))
                        """,
        }

        chorizon_response = requests.post(self.url, json=body).json()

        for row in chorizon_response["Table"]:
            # None attribute for empty data
            row = [None if not attr else attr for attr in row]
            feat = QgsFeature(self.soil_chorizon.fields())
            # populate data
            for index, col in enumerate(row):
                if index != len(self.chorizon_att_dict):
                    feat.setAttribute(self.chorizon_att_dict[index]["name"], col)
                else:
                    feat.setGeometry(QgsGeometry.fromWkt(col))
            self.chorizon_prov.addFeatures([feat])

        self.aggregateChorizon()
        self.soil_chorizon = self.clip(self.soil_chorizon)

    def downloadChfrags(self):
        """Method for downloading the chfrags layer using PostRequest"""

        # Chfrags post request
        body = {
            "format": "JSON",
            "query": f"""
                            SELECT 
                                M.mupolygonkey,
                                C.mukey,
                                Cf.fragsize_r,
                                Cf.fragvol_r,
                                M.mupolygongeo
                            FROM chfrags Cf
                                JOIN chorizon Ch ON Ch.chkey = Cf.chkey
                                JOIN component C ON C.cokey = Ch.cokey
                                JOIN mupolygon M ON M.mukey = C.mukey
                            WHERE 
                            Ch.hzdept_r = 0
                            AND
                            M.mupolygonkey IN (SELECT 
                                    *
                                FROM 
                                    SDA_Get_Mupolygonkey_from_intersection_with_WktWgs84('{self.aoi_reproj_wkt.lower()}'))
                            """,
                             }

        chfrags_response = requests.post(self.url, json=body).json()

        for row in chfrags_response["Table"]:
            # None attribute for empty data
            row = [None if not attr else attr for attr in row]
            feat = QgsFeature(self.soil_chfrags.fields())
            # populate data
            for index, col in enumerate(row):
                if index != len(self.chfrags_att_dict):
                    feat.setAttribute(self.chfrags_att_dict[index]["name"], col)
                else:
                    feat.setGeometry(QgsGeometry.fromWkt(col))
            self.chfrags_prov.addFeatures([feat])

        self.soil_chfrags = self.clip(self.soil_chfrags)

    def combineSsurgoLayers(self):
        """Method for combining the chorizon and chfrags layer"""

        self.ssurgo_layer = self.joinLayers(self.soil_chorizon, self.soil_chfrags)

    def calculateGAparameters(self):
        """Method for calculating the G&A parameters based on JE Fuller"""

        # Start editing the target layer
        self.soil_layer.startEditing()
        fields = self.soil_layer.fields()

        # Iterate over features in the source layer
        for feature in self.ssurgo_layer.getFeatures():
            # Wilting point
            sand = feature['sandtotal'] / 100
            clay = feature['claytotal'] / 100
            orgmat = feature['orgmat']  # DOUBLE CHECK
            if orgmat > 8:
                orgamat = 8
            soil_depth = feature['hzdepb_r']
            if type(feature["fragsize"]) == float:
                gravel = feature["fragsize"]
            else:
                gravel = 0

            predict_wp = -0.024 * sand + 0.487 * clay + 0.006 * orgmat + 0.005 * sand * orgmat - 0.013 * clay * orgmat + 0.068 * sand * clay + 0.031
            wPoint = predict_wp + (0.14 * predict_wp - 0.02)

            # Field Capacity
            predict_fc = -0.251 * sand + 0.195 * clay + 0.011 * orgmat + 0.006 * sand * orgmat - 0.027 * clay * orgmat + 0.452 * sand * clay + 0.299
            FCapac = predict_fc + (1.283 * predict_fc ** 2 - 0.374 * predict_fc - 0.015)

            # Saturation
            predict_sat = 0.278 * sand + 0.034 * clay + 0.022 * orgmat - 0.018 * sand * orgmat - 0.027 * clay * orgmat - 0.584 * sand * clay + 0.078
            S33 = predict_sat + (0.636 * predict_sat - 0.107)
            sat = FCapac + S33 - 0.097 * sand + 0.043

            # Adjustment for organic matter and compaction
            DensityO = (1 - sat) * 2.65
            DensityFactor = 1  # Following the NDOT method
            DensityC = DensityO * DensityFactor
            PorO = 1 - (DensityC / 2.65)
            PorC = PorO - (1 - DensityO / 2.65)
            M33C = FCapac + 0.25 * PorC
            PM33C = PorO - M33C
            if PM33C < 0:
                PM33C = 0

            # Hydraulic Conductivity
            Gadj = (1 - gravel) / (1 - gravel * (1 - 1.5 * ((DensityC) / 2.65)))
            B = (math.log(1500) - math.log(33)) / (math.log(M33C) - math.log(wPoint))
            A = math.exp(math.log(33) + (B * math.log(M33C)))
            lmbda = 1 / B
            XKSAT_fs = 1930 * (PM33C ** (3 - lmbda)) * 0.0393700787 * Gadj
            KsCF = 0.5
            XKSAT_n = XKSAT_fs * KsCF
            if XKSAT_n < 0.01:
                XKSAT_n = 0.01
            if XKSAT_n > 2:
                XKSAT_n = 2

            # Suction(per Rawls, Brackensiek & Miller, 1983)
            BubblingPressure = -21.674 * sand - 27.932 * clay - 81.975 * PM33C + 71.121 * sand * PM33C + 8.294 * clay * PM33C + 14.05 * sand * clay + 27.161
            BPadj = BubblingPressure + (0.02 * BubblingPressure ** 2 - 0.113 * BubblingPressure - 0.7)
            if BubblingPressure >= 0:
                PSIF = (2 * lmbda + 3) / (2 * lmbda + 2) * BubblingPressure / 2 * 4.014630787
            if BPadj >= 0:
                PSIF = (2 * lmbda + 3) / (2 * lmbda + 2) * BPadj / 2 * 4.014630787

            # Create a new feature in the target layer
            target_feature = QgsFeature(fields)
            target_feature.setGeometry(feature.geometry())
            target_feature.setAttributes(feature.attributes())
            target_feature['hydc'] = round(XKSAT_n, 2)
            target_feature['abstrinf'] = 99999
            target_feature['rtimpf'] = 99999
            target_feature['soil_depth'] = round(soil_depth, 2)
            target_feature['psif'] = round(PSIF, 2)
            target_feature['dthetad'] = round(sat - wPoint, 2)
            target_feature['dthetan'] = round(sat - FCapac, 2)
            target_feature['wpoint'] = round(wPoint, 2)
            target_feature['fcapac'] = round(FCapac, 2)
            target_feature['sat'] = round(sat, 2)

            # Add the new feature to the target layer
            self.soil_prov.addFeature(target_feature)

        # Save changes and stop editing the target layer
        self.soil_layer.commitChanges()
        self.soil_layer.updateExtents()

        QgsProject.instance().addMapLayer(self.soil_layer)


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

    def aggregateChorizon(self):
        alg_params = {"INPUT": self.soil_chorizon,
                      'GROUP_BY': '"mupolygonkey"', 'AGGREGATES': [
                        {'aggregate': 'first_value', 'delimiter': ',', 'input': '"mupolygonkey"', 'length': 0,
                         'name': 'mupolygonkey', 'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                        {'aggregate': 'first_value', 'delimiter': ',', 'input': '"mukey"', 'length': 0, 'name': 'mukey',
                         'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                        {'aggregate': 'mean', 'delimiter': ',', 'input': '"hzdept_r"', 'length': 0, 'name': 'hzdept_r',
                         'precision': 1, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                        {'aggregate': 'mean', 'delimiter': ',', 'input': '"hzdepb_r"', 'length': 0, 'name': 'hzdepb_r',
                         'precision': 1, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                        {'aggregate': 'mean', 'delimiter': ',', 'input': '"sandtotal"', 'length': 0, 'name': 'sandtotal',
                         'precision': 1, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                        {'aggregate': 'mean', 'delimiter': ',', 'input': '"silttotal"', 'length': 0, 'name': 'silttotal',
                         'precision': 1, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                        {'aggregate': 'mean', 'delimiter': ',', 'input': '"claytotal"', 'length': 0, 'name': 'claytotal',
                         'precision': 1, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                        {'aggregate': 'mean', 'delimiter': ',', 'input': '"orgmat"', 'length': 0, 'name': 'orgmat',
                         'precision': 1, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'}],
                      "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
                      }

        self.outputs["Aggregate"] = processing.run("native:aggregate", alg_params)["OUTPUT"]
        self.soil_chorizon = self.outputs["Aggregate"]

        return

    def fixGeometries(self, layer):
        alg_params = {"INPUT": layer, "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT}
        self.outputs["FixGeometries"] = processing.run("native:fixgeometries", alg_params)["OUTPUT"]
        self.soil_layer = self.outputs["FixGeometries"]
        return

    def clip(self, layer):
        alg_params = {"INPUT": layer, "OVERLAY": self.grid_lyr, "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT}
        return processing.run("native:clip", alg_params)["OUTPUT"]

    def joinLayers(self, layer1, layer2):
        alg_params = {"INPUT": layer1,
                      "FIELD": "mupolygonkey",
                      "INPUT_2": layer2,
                      "FIELD_2": "mupolygonkey",
                      "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT}
        return processing.run("qgis:joinattributestable", alg_params)["OUTPUT"]

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
