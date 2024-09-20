import requests
import processing
from qgis._core import QgsVectorFileWriter
from qgis.core import (QgsDistanceArea, QgsFeature, QgsField,
                       QgsGeometry, QgsProcessing, QgsVectorLayer, QgsProject)
from qgis.PyQt.QtCore import QVariant
from ..user_communication import UserCommunication
import math
from ..geopackage_utils import GeoPackageUtils

class SsurgoSoil(object):
    """Class to get SSURGO soil data"""

    def __init__(self, grid_lyr: QgsVectorLayer, iface):
        """Initialize the required layers"""

        self.grid_lyr = grid_lyr
        self.grid_lyr_4326 = None
        self.aoi_reproj_wkt = None

        self.outputs = {}
        self.uc = UserCommunication(iface, "FLO-2D")
        self.iface = iface
        self.url = "https://sdmdataaccess.sc.egov.usda.gov/TABULAR/post.rest"

        self.soil_layer = None
        self.soil_prov = None
        self.soil_att_dict = None
        self.soil_att = None

        self.soil_chorizon = None
        self.chorizon_att_dict = None
        self.chorizon_att = None
        self.chorizon_prov = None

        self.soil_chfrags = None
        self.chfrags_att_dict = None
        self.chfrags_att = None
        self.chfrags_prov = None

        self.soil_comp = None
        self.comp_att_dict = None
        self.comp_att = None
        self.comp_prov = None

        self.ssurgo_layer = None

        self.holes = None
        self.saveLayers = False

        self.gutils = None
        self.con = None

    def setup_ssurgo(self, saveLayers):
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
            {"name": "MUKEY", "type": "str"},
            {"name": "muname", "type": "str"},
            {"name": "hydc", "type": "double"},
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
            if field["type"] == "double":
                self.soil_att.append(QgsField(field["name"], QVariant.Double))
            else:
                self.soil_att.append(QgsField(field["name"], QVariant.String))
            self.soil_prov.addAttributes(self.soil_att)
            self.soil_layer.updateFields()

        # Create chorizon layer
        self.soil_chorizon = QgsVectorLayer(uri, "chorizon", "memory")
        self.chorizon_prov = self.soil_chorizon.dataProvider()
        self.chorizon_att = []
        self.chorizon_att_dict = [
            {"name": "mupolygonkey", "type": "str"},
            {"name": "mukey", "type": "str"},
            {"name": "muname", "type": "str"},
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
        self.soil_chfrags = QgsVectorLayer(uri, "chfrags", "memory")
        self.chfrags_prov = self.soil_chfrags.dataProvider()
        self.chfrags_att = []
        self.chfrags_att_dict = [
            {"name": "mupolygonkey", "type": "str"},
            {"name": "mukey", "type": "str"},
            {"name": "fragsize", "type": "double"},
            {"name": "fragvol", "type": "double"},
        ]

        # Initialize chfrags fields
        for field in self.chfrags_att_dict:
            if field["type"] == "double":
                self.chfrags_att.append(QgsField(field["name"], QVariant.Double))
            else:
                self.chfrags_att.append(QgsField(field["name"], QVariant.String))
            self.chfrags_prov.addAttributes(self.chfrags_att)
            self.soil_chfrags.updateFields()

        # Create the component layer
        self.soil_comp = QgsVectorLayer(uri, "component", "memory")
        self.comp_prov = self.soil_comp.dataProvider()
        self.comp_att = []
        self.comp_att_dict = [
            {"name": "mupolygonkey", "type": "str"},
            {"name": "mukey", "type": "str"},
            {"name": "compname", "type": "str"},
            {"name": "comppct_r", "type": "double"},
        ]

        # Initialize component fields
        for field in self.comp_att_dict:
            if field["type"] == "double":
                self.comp_att.append(QgsField(field["name"], QVariant.Double))
            else:
                self.comp_att.append(QgsField(field["name"], QVariant.String))
            self.comp_prov.addAttributes(self.comp_att)
            self.soil_comp.updateFields()

        self.ssurgo_layer = QgsVectorLayer(uri, "ssurgo", "memory")
        self.holes = QgsVectorLayer(uri, "holes", "memory")

        self.saveLayers = saveLayers

        con = self.iface.f2d["con"]
        if con is not None:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def downloadChorizon(self):
        """Method for downloading the chrozion layer using PostRequest"""

        # Chorizon post request
        body = {
            "format": "JSON",
            "query": f"""
                        SELECT 
                            M.mupolygonkey,
                            C.mukey,
                            Map.muname,
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
                            JOIN mapunit Map ON Map.mukey = M.mukey
                            JOIN legend l ON l.lkey = Map.lkey
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

        if chorizon_response:
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
            self.soil_chorizon = self.reprojectLayer(self.soil_chorizon, QgsProject.instance().crs())

            self.soil_chorizon.setName("chorizon")

        if self.saveLayers: self.saveSoilDataToGpkg(self.soil_chorizon)

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
                                JOIN mapunit Map ON Map.mukey = M.mukey
                                JOIN legend l ON l.lkey = Map.lkey
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

        if chfrags_response:
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
            self.soil_chfrags = self.reprojectLayer(self.soil_chfrags, QgsProject.instance().crs())

            self.soil_chfrags.setName("chfrags")
        if self.saveLayers: self.saveSoilDataToGpkg(self.soil_chfrags)

    def downloadComp(self):
        """Method for downloading the component layer using PostRequest"""

        # component post request
        body = {
            "format": "JSON",
            "query": f"""
                            SELECT
                                M.mupolygonkey,
                                C.mukey,
                                C.compname,
                                C.comppct_r,
                                M.mupolygongeo
                            FROM component C
                                JOIN mupolygon M ON M.mukey = C.mukey
                                JOIN chorizon Ch ON Ch.cokey = C.cokey
                                JOIN mapunit Map ON Map.mukey = M.mukey
                                JOIN legend l ON l.lkey = Map.lkey
                            WHERE
                                C.compname = 'Rock outcrop'
                            AND
                            M.mupolygonkey IN (SELECT
                                    *
                                FROM
                                    SDA_Get_Mupolygonkey_from_intersection_with_WktWgs84('{self.aoi_reproj_wkt.lower()}'))
                            """,
        }

        comp_response = requests.post(self.url, json=body).json()

        if comp_response:
            for row in comp_response["Table"]:
                # None attribute for empty data
                row = [None if not attr else attr for attr in row]
                feat = QgsFeature(self.soil_comp.fields())
                # populate data
                for index, col in enumerate(row):
                    if index != len(self.comp_att_dict):
                        feat.setAttribute(self.comp_att_dict[index]["name"], col)
                    else:
                        feat.setGeometry(QgsGeometry.fromWkt(col))
                self.comp_prov.addFeatures([feat])

            self.soil_comp = self.clip(self.soil_comp)
            self.soil_comp = self.reprojectLayer(self.soil_comp, QgsProject.instance().crs())

            self.soil_comp.setName("component")

        if self.saveLayers: self.saveSoilDataToGpkg(self.soil_comp)

    def combineSsurgoLayers(self):
        """Method for combining the chorizon and chfrags layer"""
        self.ssurgo_layer = self.joinLayers(self.soil_chorizon, self.soil_chfrags)
        self.ssurgo_layer = self.joinLayers(self.ssurgo_layer, self.soil_comp)
        self.ssurgo_layer = self.deleteHoles(self.ssurgo_layer)
        self.ssurgo_layer.setName("ssurgo")
        if self.saveLayers: self.saveSoilDataToGpkg(self.ssurgo_layer)

    def calculateGAparameters(self):
        """Method for calculating the G&A parameters based on JE Fuller"""

        self.soil_layer = self.reprojectLayer(self.soil_layer, QgsProject.instance().crs())
        self.soil_prov = self.soil_layer.dataProvider()

        # Start editing the target layer
        self.soil_layer.startEditing()
        fields = self.soil_layer.fields()

        # Check the model unit
        if self.gutils.get_cont_par("METRIC") == "1":
            depth_unit = 100  # meters
            xksat_unit = 1  # mm/hr
        else:
            depth_unit = 30.48  # ft
            xksat_unit = 25.4  # in/hr

        # Iterate over features in the source layer
        for feature in self.ssurgo_layer.getFeatures():

            # sand
            if type(feature['sandtotal']) == float:
                sand = feature['sandtotal'] / 100  # Data is in %, need to change to dec
            else:
                sand = 0

            # clay
            if type(feature['claytotal']) == float:
                clay = feature['claytotal'] / 100  # Data is in %, need to change to dec
            else:
                clay = 0

            # organic material
            if type(feature['orgmat']) == float:
                orgmat = feature['orgmat']  # Data is in %, keep on %
            else:
                orgmat = 0
            if orgmat > 8:
                orgamat = 8

            soil_depth = feature['hzdepb_r'] / depth_unit  # meters or ft

            # fragvol is the volume percentage of the horizon occupied by the 2 mm or larger fraction
            if type(feature['fragvol']) == float:
                gravel = feature['fragvol'] / 100
                if gravel > 0.5:
                    gravel = 0.5
            else:
                gravel = 0

            if type(feature['comppct_r']) == float:
                rtimpf = feature['comppct_r']
            else:
                rtimpf = 0

            # Wilting point
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
            M33C = FCapac + 0.25 * PorC  # DIFFERENT FROM THE NDOT (0.2)
            PM33C = PorO - M33C
            if PM33C < 0:
                PM33C = 0

            # Hydraulic Conductivity (mm/hr) - Spreadsheet
            lmbda = (math.log(M33C) - math.log(wPoint)) / (math.log(1500) - math.log(33))
            Gadj = (1 - gravel) / (1 - gravel * (1 - 1.5 * ((DensityC) / 2.65)))
            XKSAT_fs = 1930 * (PM33C ** (3 - lmbda)) * Gadj # DIFFERENT FROM THE NDOT
            KsCF = 0.5
            XKSAT_n = XKSAT_fs * KsCF
            if XKSAT_n < 0.254:
                XKSAT_n = 0.254
            if XKSAT_n > 50.8:
                XKSAT_n = 50.8

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
            target_feature['MUKEY'] = feature['MUKEY']
            target_feature['MUNAME'] = feature['muname']
            target_feature['hydc'] = round(XKSAT_n / xksat_unit, 3)
            target_feature['rtimpf'] = rtimpf
            target_feature['soil_depth'] = round(soil_depth, 2)
            target_feature['psif'] = round(PSIF, 3)
            target_feature['dthetad'] = round(sat - wPoint, 3)
            target_feature['dthetan'] = round(sat - FCapac, 3)
            target_feature['dthetaw'] = round(sat - sat, 3)
            target_feature['wpoint'] = round(wPoint, 3)
            target_feature['fcapac'] = round(FCapac, 3)
            target_feature['sat'] = round(sat, 3)

            # Add the new feature to the target layer
            self.soil_prov.addFeature(target_feature)

        # Save changes and stop editing the target layer
        self.soil_layer.commitChanges()
        self.soil_layer.updateExtents()

    def postProcess(self):

        # Get the holes polygons
        self.holes = self.symetricalDifference(self.soil_layer, self.grid_lyr)

        # Dissolve the fields
        self.holes = self.dissolve(self.holes)

        # check if there is holes
        if self.holes.isValid():
            # Delete fields
            field_indices = list(range(self.holes.fields().count()))
            self.holes.dataProvider().deleteAttributes(field_indices)
            self.holes.updateFields()
            self.holes.commitChanges()

            # Union with the soil data
            self.soil_layer = self.union(self.soil_layer, self.holes)

            # Get the index of the "hydc" field
            hydc_field_index = self.soil_layer.fields().indexFromName('hydc')

            # Get the field names of all fields
            field_names = [field.name() for field in self.soil_layer.fields()]

            # Create a dictionary to store the feature IDs and their corresponding values
            feature_values = {}

            # Create a QgsDistanceArea object for distance calculations
            distance_area = QgsDistanceArea()

            # Iterate over all features in the layer
            for feature in self.soil_layer.getFeatures():
                # Get the feature ID
                feature_id = feature.id()

                # Get the value of the "hydc" field
                hydc_value = feature.attribute(hydc_field_index)

                # Check if the "hydc" field is null
                if hydc_value is None:
                    # Get the closest feature's values
                    closest_values = None
                    closest_distance = float('inf')
                    for neighbor in self.soil_layer.getFeatures():
                        if neighbor.id() != feature_id:
                            neighbor_hydc = neighbor.attribute(hydc_field_index)
                            if neighbor_hydc is not None:
                                # Calculate the geometric distance between the features
                                distance = distance_area.measureLine(feature.geometry().centroid().asPoint(),
                                                                     neighbor.geometry().centroid().asPoint())
                                if distance < closest_distance:
                                    closest_distance = distance
                                    closest_values = {field_index: neighbor.attribute(field_index) for field_index in
                                                      range(len(field_names))}

                    if closest_values:
                        feature_values[feature_id] = closest_values

            # Update the null values in the layer with the closest values
            self.soil_layer.startEditing()
            for feature_id, closest_values in feature_values.items():
                self.soil_layer.changeAttributeValues(feature_id, closest_values)

            # Commit the changes
            self.soil_layer.commitChanges()
            self.soil_layer.updateExtents()

            self.soil_layer.setName("soil_layer")

            if self.saveLayers:
                self.saveSoilDataToGpkg(self.soil_layer)
            else:
                QgsProject.instance().addMapLayer(self.soil_layer)

    def soil_lyr(self):
        return self.soil_layer

    def aggregateChorizon(self):
        alg_params = {"INPUT": self.soil_chorizon,
                      'GROUP_BY': '"mupolygonkey"', 'AGGREGATES': [
                {'aggregate': 'first_value', 'delimiter': ',', 'input': '"mupolygonkey"', 'length': 0,
                 'name': 'mupolygonkey', 'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                {'aggregate': 'first_value', 'delimiter': ',', 'input': '"mukey"', 'length': 0, 'name': 'mukey',
                 'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                {'aggregate': 'first_value', 'delimiter': ',', 'input': '"muname"', 'length': 0, 'name': 'muname',
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

    def symetricalDifference(self, layer1, layer2):
        alg_params = {'INPUT': layer1,
                      'OVERLAY': layer2,
                      'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT}

        return processing.run("native:symmetricaldifference", alg_params)["OUTPUT"]

    def dissolve(self, layer):
        alg_params = {'INPUT': layer,
                      'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT}
        return processing.run("native:dissolve", alg_params)["OUTPUT"]

    def union(self, layer1, layer2):
        alg_params = {'INPUT': layer1,
                      'OVERLAY': layer2,
                      'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT}
        return processing.run("native:union", alg_params)["OUTPUT"]

    def reprojectLayer(self, layer, target_crs):
        alg_params = {
            "INPUT": layer,
            "OPERATION": "",
            "TARGET_CRS": target_crs,
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        return processing.run("native:reprojectlayer", alg_params)["OUTPUT"]

    def getExtent(self, layer) -> tuple:
        # Get extent of the area boundary layer
        extent = layer.extent()
        xmin = extent.xMinimum()
        ymin = extent.yMinimum()
        xmax = extent.xMaximum()
        ymax = extent.yMaximum()
        return xmin, ymin, xmax, ymax

    def deleteHoles(self, layer):
        alg_params = {
                      'INPUT' : layer,
                      'MIN_AREA': 0,
                      'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                     }
        return processing.run("native:deleteholes", alg_params)["OUTPUT"]

    def saveSoilDataToGpkg(self, layer):
        """
        Function to save the soil layer into the gpkg
        """
        gpkg_path = self.gutils.get_gpkg_path()
        root_group = QgsProject.instance().layerTreeRoot()
        flo2d_name = f"FLO-2D_{self.gutils.get_metadata_par('PROJ_NAME')}"
        group_name = "SSURGO Generator"
        flo2d_grp = root_group.findGroup(flo2d_name)
        if flo2d_grp.findGroup(group_name):
            group = flo2d_grp.findGroup(group_name)
        else:
            group = flo2d_grp.insertGroup(-1, group_name)

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.includeZ = True
        options.overrideGeometryType = layer.wkbType()
        options.layerName = layer.name()
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
        QgsVectorFileWriter.writeAsVectorFormatV3(
            layer,
            gpkg_path,
            QgsProject.instance().transformContext(),
            options)
        # Add back to the project
        gpkg_uri = f"{gpkg_path}|layername={layer.name()}"
        gpkg_layer = QgsVectorLayer(gpkg_uri, layer.name(), "ogr")
        QgsProject.instance().addMapLayer(gpkg_layer, False)
        gpkg_layer.setRenderer(layer.renderer().clone())
        gpkg_layer.triggerRepaint()
        group.insertLayer(0, gpkg_layer)
        layer = QgsProject.instance().mapLayersByName(gpkg_layer.name())[0]
        myLayerNode = root_group.findLayer(layer.id())
        myLayerNode.setExpanded(False)
