# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

import os

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
from math import exp, log, log10, sqrt

from qgis._core import QgsRasterLayer
from qgis.core import (
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsRectangle,
    QgsSpatialIndex,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QApplication
from qgis.utils import iface

from ..user_communication import UserCommunication
from .grid_tools import (
    centroids2poly_geos,
    gridRegionGenerator,
    intersection_spatial_index,
    poly2poly_geos_from_features,
)

from subprocess import PIPE, STDOUT, Popen
from ..flo2d_tools.grid_tools import raster2grid


class InfiltrationCalculator(object):
    RTYPE = {
        1: "Byte",
        2: "UInt16",
        3: "Int16",
        4: "UInt32",
        5: "Int32",
        6: "Float32",
        7: "Float64",
    }

    def __init__(self, grid_lyr, iface, gutils):

        self.uc = UserCommunication(iface, "FLO-2D")
        self.grid_lyr = grid_lyr
        self.cell_size = float(gutils.get_cont_par("CELLSIZE"))
        self.soil_lyr = None
        self.land_lyr = None
        self.curve_lyr = None
        self.combined_lyr = None
        self.gutils = gutils

        # Soil fields
        self.xksat_fld = None
        self.rtimps_fld = None
        self.soil_depth_fld = None
        self.soil_dthetan_fld = None
        self.soil_dthetad_fld = None
        self.soil_psif_fld = None

        # Land use fields
        self.saturation_fld = None
        self.vc_fld = None
        self.ia_fld = None
        self.rtimpl_fld = None

        self.vc_check = None
        self.log_area_average = None

        # SCS (single) layer fields
        self.curve_fld = None
        self.out_srs = None

        # SCS (raster)
        self.out_raster = None
        self.output_bounds = None
        self.raster_type = None
        self.src_srs = None
        self.src_nodata = None
        self.raster_lyr = None
        self.algorithm = None
        self.nodatavalue = None
        self.fillnodata = None
        self.multithread = None

        # SCS (multiple) combined layers fields
        self.landsoil_fld = None
        self.cd_fld = None
        self.imp_fld = None

    def setup_green_ampt(
            self,
            soil,
            land,
            vc_check,
            log_area_average,
            xksat_fld="XKSAT",
            rtimps_fld="field_4",
            soil_depth_fld="soil_depth",
            dthetan_fld="DTHETAn",
            dthetad_fld="DTHETAd",
            psif_fld="PSIF",
            saturation_fld="field_6",
            vc_fld="field_5",
            ia_fld="field_3",
            rtimpl_fld="field_4",
    ):
        self.soil_lyr = soil
        self.land_lyr = land

        # Soil fields
        self.xksat_fld = xksat_fld
        self.rtimps_fld = rtimps_fld
        self.soil_depth_fld = soil_depth_fld
        self.soil_dthetan_fld = dthetan_fld
        self.soil_dthetad_fld = dthetad_fld
        self.soil_psif_fld = psif_fld

        # Land use fields
        self.saturation_fld = saturation_fld
        self.vc_fld = vc_fld
        self.ia_fld = ia_fld
        self.rtimpl_fld = rtimpl_fld

        self.vc_check = vc_check
        self.log_area_average = log_area_average

        # get area of an item in self.grid_lyr.

        self.gridArea = float(self.gutils.get_cont_par("CELLSIZE")) ** 2
        # gridfeat = next(self.grid_lyr.getFeatures())
        # self.gridArea = gridfeat.geometry().area()

    def setup_scs_single(self, curve_lyr, curve_fld="CurveNum"):
        self.curve_lyr = curve_lyr
        self.curve_fld = curve_fld

    def setup_scs_raster(self, raster_lyr, algorithm, nodatavalue, fillnodata, multithread):
        self.raster_lyr = raster_lyr
        self.algorithm = algorithm
        self.nodatavalue = nodatavalue
        self.fillnodata = fillnodata
        self.multithread = multithread

    def setup_scs_multi(self, combined_lyr, landsoil_fld="LandSoil", cd_fld="cov_den", imp_fld="IMP"):
        self.combined_lyr = combined_lyr
        self.landsoil_fld = landsoil_fld
        self.cd_fld = cd_fld
        self.imp_fld = imp_fld

    def green_ampt_infiltration(self):
        writeDiagnosticCSV = True  # flag to determine if a csv file should be written with computational values
        try:
            grid_params = {}
            green_ampt = GreenAmpt()

            grid_element_count = self.grid_lyr.featureCount()
            if grid_element_count < 0:
                grid_span = 100
            else:
                grid_span = int(max(sqrt(grid_element_count) / 10, 10))

            for request in gridRegionGenerator(
                    self.gutils,
                    self.grid_lyr,
                    gridSpan=grid_span,
                    regionPadding=5,
                    showProgress=True,
            ):
                # calculate extent of concerned grid element
                grid_elems = self.grid_lyr.getFeatures(request)
                grid_elem_extent = QgsRectangle()
                grid_elem_extent.setMinimal()
                for grid_elem in grid_elems:
                    grid_elem_extent.combineExtentWith(grid_elem.geometry().boundingBox())

                grid_elem_extent.grow(grid_elem_extent.width() / 20.0)
                soil_and_land_request = QgsFeatureRequest()
                soil_and_land_request.setFilterRect(grid_elem_extent)

                soil_features, soil_index = intersection_spatial_index(self.soil_lyr, soil_and_land_request, clip=True)
                land_features, land_index = intersection_spatial_index(self.land_lyr, soil_and_land_request, clip=True)

                land_soil_features = {}
                land_soil_index = QgsSpatialIndex()
                land_soil_fields = QgsFields()
                land_soil_fields.append(QgsField("rtimp", QVariant.Double))
                land_soil_fields.append(QgsField("dthetan", QVariant.Double))
                land_soil_fields.append(QgsField("dthetad", QVariant.Double))
                land_soil_fields.append(QgsField("psif", QVariant.Double))
                land_soil_fields.append(QgsField("saturation", QVariant.String))

                land_soil_fid = 0

                for land_feat, engine in land_features.values():
                    land_rtimp = land_feat[self.rtimpl_fld]
                    land_saturation = land_feat[self.saturation_fld]
                    land_geom = land_feat.geometry()

                    soil_fids = soil_index.intersects(land_geom.boundingBox())
                    for soil_fid in soil_fids:
                        soil_feat, soil_engine = soil_features[soil_fid]
                        soil_rtimp = soil_feat[self.rtimps_fld]
                        soil_dthetan = soil_feat[self.soil_dthetan_fld]
                        soil_dthetad = soil_feat[self.soil_dthetad_fld]
                        soil_psif = soil_feat[self.soil_psif_fld]

                        land_soil_geom = land_geom.intersection(soil_feat.geometry())

                        if land_soil_geom.isEmpty():
                            continue

                        land_soil_feat = QgsFeature(land_soil_fields, land_soil_fid)

                        land_soil_feat.setGeometry(land_soil_geom)
                        land_soil_feat["rtimp"] = max(land_rtimp, soil_rtimp)
                        land_soil_feat["dthetan"] = soil_dthetan
                        land_soil_feat["dthetad"] = soil_dthetad
                        land_soil_feat["psif"] = soil_psif
                        land_soil_feat["saturation"] = land_saturation
                        land_soil_features[land_soil_fid] = (
                            land_soil_feat,
                            QgsGeometry.createGeometryEngine(land_soil_geom.constGet()),
                        )
                        land_soil_index.addFeature(land_soil_feat)
                        land_soil_fid = land_soil_fid + 1

                try:
                    soil_values = poly2poly_geos_from_features(
                        self.grid_lyr,
                        soil_features,
                        soil_index,
                        request,
                        self.xksat_fld,
                        self.soil_depth_fld,
                    )
                except Exception as e:
                    self.uc.show_error(
                        "ERROR 051218.2035: Green-Ampt infiltration failed\nwhile intersecting soil layer with grid."
                        + "\n__________________________________________________",
                        e,
                    )
                    return grid_params

                for gid, values in soil_values:
                    try:
                        xksat_parts = [(row[0], row[-1]) for row in values]
                        avg_soil_depth = sum(row[1] * row[-1] for row in values)
                        avg_xksat = green_ampt.calculate_xksat_weighted(xksat_parts)

                        soil_params = {
                            "soilParts": len(values),
                            "soilhydc": avg_xksat,
                            "hydc": avg_xksat,
                            "soil_depth": avg_soil_depth,
                        }
                        if not self.log_area_average:
                            soil_params["soils"] = green_ampt.calculate_psif(avg_xksat)
                        grid_params[gid] = soil_params
                    except Exception as e:
                        self.uc.show_error(
                            "ERROR 1401181951.2035: Green-Ampt infiltration failed"
                            + "\nwhile intersecting soil layer with grid {}".format(gid)
                            + "\n__________________________________________________",
                            e,
                        )
                        return grid_params

                land_values = poly2poly_geos_from_features(
                    self.grid_lyr,
                    land_features,
                    land_index,
                    request,
                    self.saturation_fld,
                    self.vc_fld,
                    self.ia_fld,
                )

                for gid, values in land_values:
                    try:
                        land_params = grid_params[gid]
                        avg_xksat = land_params["hydc"]

                        vc_parts = [(row[1], row[-1]) for row in values]
                        ia_parts = [(row[2], row[-1]) for row in values]

                        if not self.log_area_average:
                            dtheta = sum([green_ampt.calculate_dtheta(avg_xksat, row[0]) * row[-1] for row in values])
                            land_params["dtheta"] = dtheta

                        if self.vc_check is True:
                            # perform vc adjustment
                            xksatc = green_ampt.calculate_xksatc(avg_xksat, vc_parts)
                        else:
                            # don't perform vc adjustment
                            xksatc = avg_xksat

                        iabstr = green_ampt.calculate_iabstr(ia_parts)

                        land_params["hydc"] = xksatc
                        land_params["abstrinf"] = iabstr
                        land_params["luParts"] = len(values)

                    except ValueError as e:
                        raise ValueError(
                            "Calculation of land use variables failed for grid cell with fid: {}".format(gid)
                        )

                land_soil_values = poly2poly_geos_from_features(
                    self.grid_lyr,
                    land_soil_features,
                    land_soil_index,
                    request,
                    "rtimp",
                    "dthetan",
                    "dthetad",
                    "psif",
                    "saturation",
                )
                for gid, values in land_soil_values:
                    try:
                        land_params = grid_params[gid]
                        rtimp_parts, dtheta_parts, psif_parts = [], [], []
                        for rtimp, dthetan, dthetad, psif, saturation, area in values:
                            rtimp_parts.append((rtimp * 0.01, area))
                            if saturation.lower() == "dry":
                                dtheta_parts.append((dthetad, area))
                            elif saturation.lower() == "normal":
                                dtheta_parts.append((dthetan, area))
                            elif saturation.lower() == "wet" or saturation.lower() == "saturated":
                                dtheta_parts.append((0, area))
                            else:
                                raise Exception
                            psif_parts.append((psif, area))
                        land_params["rtimpf"] = green_ampt.calculate_rtimp_n(rtimp_parts)
                        if self.log_area_average:
                            land_params["dtheta"] = green_ampt.calculate_dtheta_weighted(dtheta_parts)
                            land_params["soils"] = green_ampt.calculate_psif_weighted(psif_parts)
                    except Exception as e:
                        self.uc.show_error(
                            "ERROR: Green-Ampt infiltration failed\nwhile defining the saturation."
                            + "\n__________________________________________________",
                            e,
                        )
                        return grid_params

            if writeDiagnosticCSV is True:
                # write a diagnostic CSV file with all fo the information for the calculations in it
                diagCSVFolder = r"C:\temp"
                if os.path.exists(diagCSVFolder) is False:
                    os.mkdir(diagCSVFolder)
                diagFilename = "GA_Diagnostics.csv"
                diagPath = os.path.join(diagCSVFolder, diagFilename)
                # organize the grid data for csv writing
                gids = sorted(grid_params.keys())
                writeVals = (
                    (
                        str(gid),
                        str(grid_params[gid]["soilParts"]),
                        str(grid_params[gid]["soilhydc"]),
                        str(grid_params[gid]["rtimpf"]),
                        str(grid_params[gid]["soil_depth"]),
                        str(grid_params[gid]["luParts"]),
                        str(
                            round(
                                grid_params[gid]["hydc"] / grid_params[gid]["soilhydc"],
                                5,
                            )
                        ),
                        str(grid_params[gid]["hydc"]),
                        str(grid_params[gid]["dtheta"]),
                        str(grid_params[gid]["abstrinf"]),
                        str(grid_params[gid]["soils"]),
                    )
                    for gid in gids
                )
                with open(diagPath, "w") as writer:
                    header = (
                            ",".join(
                                [
                                    "GridNum",
                                    "NumSoilPartsInGrid",
                                    "SoilXKSAT",
                                    "SoilRTIMP",
                                    "InfilDepth",
                                    "NumLUPartsInGrid",
                                    "VCAdjustment",
                                    "VCXKSAT",
                                    "DTHETA",
                                    "IA",
                                    "PSIF",
                                    "LU_RTIMP",
                                ]
                            )
                            + "\n"
                    )
                    writer.write(header)
                    for item in writeVals:
                        writer.write(",".join(item) + "\n")
        except Exception as e:
            self.uc.show_error(
                "ERROR 051218.2001: Green-Ampt infiltration failed!."
                + "\n__________________________________________________",
                e,
            )

        return grid_params

    def scs_infiltration_single(self):
        """
        This code sets the CN based on the centroid of the intersecting layer.
        """
        try:
            grid_params = {}
            curve_values = centroids2poly_geos(self.grid_lyr, self.curve_lyr, None, self.curve_fld)
            for gid, values in curve_values:
                if len(values) == 0:
                    raise Exception("Grid element centroid is not inside the Infiltration Polygon.")
                else:
                    cn = values[0][0]
                    grid_params[gid] = {"scsn": cn}
            return grid_params

        except Exception as e:
            self.uc.show_error(
                "ERROR: SCS infiltration failed!",
                e,
            )
    def scs_infiltration_raster(self):
        """
        Resample raster to be aligned with the grid, then probe values and update elements scs attr.
        """
        self.out_raster = "{}_interp_cn.tif".format(self.raster_lyr[:-4])  # Raster name with suffix '_interp_cn.tif'
        try:
            if os.path.isfile(self.out_raster):
                os.remove(self.out_raster)
        except OSError:
            msg = "WARNING 060319.1651: Couldn't remove existing raster:\n{}\nChoose another filename.".format(
                self.out_raster
            )
            self.uc.show_warn(msg)
            return False
        self.get_worp_opts_data()
        opts = [
            "-of GTiff",
            "-ot {}".format(self.RTYPE[self.raster_type]),
            "-tr {0} {0}".format(self.cell_size),
            '-s_srs "{}"'.format(self.src_srs),
            '-t_srs "{}"'.format(self.out_srs),
            "-te {}".format(" ".join([str(c) for c in self.output_bounds])),
            '-te_srs "{}"'.format(self.out_srs),
            # "-ovr {}".format(self.ovrCbo.itemData(self.ovrCbo.currentIndex())),
            "-dstnodata {}".format(self.src_nodata),
            "-r {}".format(self.algorithm),
            "-co COMPRESS=LZW",
            "-wo OPTIMIZE_SIZE=TRUE",
        ]
        if self.multithread:
            opts.append("-multi -wo NUM_THREADS=ALL_CPUS")
        else:
            pass
        cmd = 'gdalwarp {} "{}" "{}"'.format(" ".join([opt for opt in opts]), self.raster_lyr, self.out_raster)
        # print(cmd)
        proc = Popen(
            cmd,
            shell=True,
            stdin=open(os.devnull),
            stdout=PIPE,
            stderr=STDOUT,
            universal_newlines=True,
        )
        out = proc.communicate()
        for line in out:
            self.uc.log_info(line)
        # Fill NODATA raster cells if desired
        if self.fillnodata:
            self.fill_nodata()
        else:
            pass
        sampler = raster2grid(self.grid_lyr, self.out_raster)

        grid_params = {}
        for cn, gid in sampler:
            try:
                grid_params[gid] = {"scsn": int(round(cn, 0))}
            except ValueError as e:
                raise ValueError("Calculation failed for grid cell with fid: {}".format(gid))

        return grid_params

    def scs_infiltration_multi(self):
        grid_params = {}
        scs = SCPCurveNumber()
        ground_values = centroids2poly_geos(
            self.grid_lyr,
            self.combined_lyr,
            None,
            self.landsoil_fld,
            self.cd_fld,
            self.imp_fld,
        )
        for gid, values in ground_values:
            try:
                grid_cn = scs.calculate_scs_cn(values)
                grid_params[gid] = {"scsn": grid_cn}
            except ValueError as e:
                raise ValueError("Calculation failed for grid cell with fid: {}".format(gid))

        return grid_params

    def get_worp_opts_data(self):
        """
        Get all data needed for GDAL Warp.
        """
        grid_ext = self.grid_lyr.extent()
        xmin = grid_ext.xMinimum()
        xmax = grid_ext.xMaximum()
        ymin = grid_ext.yMinimum()
        ymax = grid_ext.yMaximum()
        self.output_bounds = (xmin, ymin, xmax, ymax)
        self.out_srs = self.grid_lyr.crs().authid()
        src_raster_lyr = QgsRasterLayer(self.raster_lyr)
        self.raster_type = src_raster_lyr.dataProvider().dataType(1)
        self.src_srs = src_raster_lyr.crs().authid()
        if not self.src_srs:
            self.src_srs = self.out_srs
        und = self.nodatavalue
        if und:
            self.src_nodata = int(und)

    def fill_nodata(self):
        # opts = ["-md {}".format(self.radiusSBox.value())]
        # cmd = 'gdal_fillnodata {} "{}"'.format(" ".join([opt for opt in opts]), self.out_raster)
        cmd = f'gdal_fillnodata "{self.raster_lyr}" "{self.out_raster}"'
        self.uc.log_info(str(cmd))
        proc = Popen(
            cmd,
            shell=True,
            stdin=open(os.devnull),
            stdout=PIPE,
            stderr=STDOUT,
            universal_newlines=True,
        )
        out = proc.communicate()
        for line in out:
            self.uc.log_info(line)

class GreenAmpt(object):
    def __init__(self):
        self.uc = UserCommunication(iface, "FLO-2D")

    def calculate_xksat_weighted(self, parts, globalXKSAT=0.06):
        # parts are reported in % of grid area
        try:
            xksat_partial = [area * log10(xksat) for xksat, area in parts if xksat > 0]
            area_total = sum(area for xksat, area in parts)
            if (
                    area_total < 1.0
            ):  # check if intersected parts area is less than grid area, assumes same units. Values would differ if soils did not completely cover cell.
                if (
                        globalXKSAT > 0
                ):  # if it's zero, we don't need to do anything and can't evaluate log10. If it's less than zero, it's not valid input.
                    xksat_partial.append((1.0 - area_total) * log10(globalXKSAT))
            avg_xksat = round(10 ** (sum(xksat_partial)), 4)
            return avg_xksat

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 140119.1715: Green-Ampt infiltration failed!."
                + "\nError while calculating xksat."
                + "\n__________________________________________________",
                e,
            )

    def calculate_dtheta_weighted(self, parts):
        # parts are reported in % of grid area
        try:

            # # Log area average for dry and normal saturation and area weighted average for wet saturation
            # dtheta_partial_dn = []
            # area_dn = []
            # area_sat = []
            # for dtheta, area in parts:
            #     if dtheta > 0:
            #         dtheta_partial_dn.append(area * log10(dtheta))
            #         area_dn.append(area)
            #     else:
            #         area_sat.append(area)
            # area_total = sum(area_dn) + sum(area_sat)
            # # Only dry and normal DTHETA
            # if sum(area_sat) == 0:
            #     avg_dtheta = round(10 ** (sum(dtheta_partial_dn)/sum(area_dn)), 4)
            # # Only wet DTHETA
            # elif sum(area_dn) == 0:
            #     avg_dtheta = 0
            # # Dry, normal and wet DTHETA
            # else:
            #     avg_dtheta = round(((10 ** (sum(dtheta_partial_dn)/sum(area_dn))) * sum(area_dn)) / area_total, 4)

            # Arithmetic weighted average
            dtheta_dn = []
            area_total = []
            for dtheta, area in parts:
                area_total.append(area)
                dtheta_dn.append(dtheta * area)

            avg_dtheta = sum(dtheta_dn) / sum(area_total)

            return avg_dtheta

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 140119.1715: Green-Ampt infiltration failed!."
                + "\nError while calculating DTHETA."
                + "\n__________________________________________________",
                e,
            )

    def calculate_psif_weighted(self, parts):
        # parts are reported in % of grid area
        try:
            psif_partial = [area * log10(psif) for psif, area in parts if psif > 0]
            avg_psif = round(10 ** (sum(psif_partial)), 4)
            return avg_psif

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 140119.1715: Green-Ampt infiltration failed!."
                + "\nError while calculating PSIF."
                + "\n__________________________________________________",
                e,
            )

    @staticmethod
    def calculate_psif(avg_xksat):
        if 0.01 <= avg_xksat:
            psif = exp(
                0.9813 - 0.439 * log(avg_xksat) + 0.0051 * (log(avg_xksat)) ** 2 + 0.0060 * (log(avg_xksat)) ** 3
            )
            return psif
        else:
            raise ValueError(avg_xksat)

    @staticmethod
    def calculate_dtheta(avg_xksat, saturation):
        if saturation == "dry":
            if 0.01 <= avg_xksat <= 0.15:
                dtheta = exp(-0.2394 + 0.3616 * log(avg_xksat))
            elif 0.15 < avg_xksat <= 0.25:
                dtheta = exp(-1.4122 - 0.2614 * log(avg_xksat))
            elif 0.25 < avg_xksat:
                dtheta = 0.35
            else:
                raise ValueError(avg_xksat)
        elif saturation == "normal":
            if 0.01 <= avg_xksat <= 0.02:
                dtheta = exp(1.6094 + log(avg_xksat))
            elif 0.02 < avg_xksat <= 0.04:
                dtheta = exp(-0.0142 + 0.585 * log(avg_xksat))
            elif 0.04 < avg_xksat <= 0.1:
                dtheta = 0.15
            elif 0.1 < avg_xksat <= 0.15:
                dtheta = exp(1.0038 + 1.2599 * log(avg_xksat))
            elif 0.15 < avg_xksat <= 0.4:
                dtheta = 0.25
            elif 0.4 < avg_xksat:
                dtheta = exp(-1.2342 + 0.1660 * log(avg_xksat))
            else:
                raise ValueError(avg_xksat)
        elif saturation == "wet" or saturation == "saturated":
            dtheta = 0.0
        else:
            raise ValueError(saturation)
        return dtheta

    @staticmethod
    def calculate_xksatc(avg_xksat, parts, defaultVCAdj=1.0):
        if avg_xksat < 0.4:
            pc_gen = tuple((((float(vc) - 10.0) / 90.0 + 1.0) * float(area) for vc, area in parts if vc > 10))

            pc_noadj = tuple(
                (float(area) for vc, area in parts if vc <= 10)
            )  # adds areas where adjustment is not applied, assumes a coefficient of 1 for these areas

            areaTotal = sum(float(area) for xksat, area in parts)

            if areaTotal < 1.0:
                if areaTotal == 0:
                    # no intersecting area, calculate using the defaultVCAdj value
                    xksatc = avg_xksat * defaultVCAdj
                else:
                    # composite using the default VCAdj value
                    xksatc = avg_xksat * ((sum(pc_gen) + sum(pc_noadj) + defaultVCAdj * (1.0 - areaTotal)))
            else:
                xksatc = avg_xksat * (sum(pc_gen) + sum(pc_noadj))
        else:
            xksatc = avg_xksat
        return xksatc

    @staticmethod
    def calculate_iabstr(parts, globalIA=0.1):
        iabstr_gen = [area * float(ia) for ia, area in parts]
        areaTotal = sum(area for ia, area in parts)
        if areaTotal < 1.0:
            iabstr_gen.append((1.0 - areaTotal) * globalIA)
        iabstr = sum(iabstr_gen)
        return iabstr

    @staticmethod
    def calculate_rtimp_n(parts, globalRockOutCrop=0.2):
        # calculated naturall occuring RTIMP without consideration of the effective impervious area
        # rtimp_gen_n = (area * (float(rtimps) * float(eff)) for rtimps, eff, area in parts)
        rtimp_gen_n = [area * (float(rtimps)) for rtimps, area in parts]
        areaTotal = sum(area for rtimps, area in parts)
        if areaTotal < 1.0:
            rtimp_gen_n.append((1.0 - areaTotal) * globalRockOutCrop)
        rtimp_n = sum(rtimp_gen_n)
        return rtimp_n

    @staticmethod
    def calculate_rtimp_l(parts, globalRTIMPL=0.2):
        rtimp_l = [area * float(rtimpl) for rtimpl, area in parts]
        areaTotal = sum(area for rtimpl, area in parts)
        if areaTotal < 1.0:
            rtimp_l.append((1.0 - areaTotal) * globalRTIMPL)
        rtimp = sum(rtimp_l)
        return rtimp


class SCPCurveNumber(object):
    def __init__(self):
        self.scs_calc = {
            "desert brush": self.calculate_desert_brush,
            "herbaceous": self.calculate_herbaceous,
            "mountain brush": self.calculate_mountain_brush,
            "juniper - grass": self.calculate_juniper_grass,
            "ponderosa pine": self.calculate_ponderosa_pine,
            "pervious - urban law": self.calculate_ponderosa_pine,
        }

    def calculate_scs_cn(self, parts):
        partial_var = []
        for landsoil, cd, imp, subarea in parts:
            cd = float(cd)
            soil_group, hsc = landsoil.split(" ", 1)
            calc_method = self.scs_calc[hsc.lower()]
            if "%" in soil_group:
                cn = 0
                for sg_perc in soil_group.strip("%").split("%"):
                    sg = sg_perc[0]
                    perc = (float(sg_perc[1:]) * 0.01) * (1 - imp)
                    part_cn = calc_method(sg, cd) * perc
                    cn += part_cn
                cn += imp * 99
            else:
                perc = 1 * (1 - imp)
                cn = calc_method(soil_group, cd) * perc + imp * 99
            var = subarea * cn
            partial_var.append(var)
        grid_cn = sum(partial_var)
        return grid_cn

    @staticmethod
    def calculate_desert_brush(soil_group, cover_density):
        if soil_group == "D":
            cn = -0.08 * cover_density + 93
        elif soil_group == "C":
            cn = -0.08 * cover_density + 90
        elif soil_group == "B":
            cn = -0.07 * cover_density + 84
        else:
            raise ValueError(soil_group)
        return cn

    @staticmethod
    def calculate_herbaceous(soil_group, cover_density):
        if soil_group == "D":
            cn = -0.0875 * cover_density + 93
        elif soil_group == "C":
            cn = -0.1875 * cover_density + 90
        elif soil_group == "B":
            cn = -0.2625 * cover_density + 84
        else:
            raise ValueError(soil_group)
        return cn

    @staticmethod
    def calculate_mountain_brush(soil_group, cover_density):
        if soil_group == "D":
            cn = -0.0013 * cover_density ** 2 + -0.1737 * cover_density + 95
        elif soil_group == "C":
            cn = -0.0014 * cover_density ** 2 + -0.2942 * cover_density + 90
        elif soil_group == "B":
            cn = -0.0025 * cover_density ** 2 + -0.3522 * cover_density + 83
        else:
            raise ValueError(soil_group)
        return cn

    @staticmethod
    def calculate_juniper_grass(soil_group, cover_density):
        if soil_group == "D":
            cn = -0.1125 * cover_density + 93
        elif soil_group == "C":
            cn = -0.34375 * cover_density + 90.5
        elif soil_group == "B":
            cn = -0.525 * cover_density + 84
        else:
            raise ValueError(soil_group)
        return cn

    @staticmethod
    def calculate_ponderosa_pine(soil_group, cover_density):
        if 0 < cover_density <= 10:
            if soil_group == "C":
                cn = -0.08 * cover_density ** 2 + -1.9 * cover_density + 91
            elif soil_group == "B":
                cn = -0.1 * cover_density ** 2 + -2.4 * cover_density + 84
            else:
                raise ValueError(soil_group)
        elif 10 < cover_density <= 80:
            if soil_group == "C":
                cn = -0.242857 * cover_density + 82.42857
            elif soil_group == "B":
                cn = -0.3 * cover_density + 73
            else:
                raise ValueError(soil_group)
        else:
            raise ValueError(cover_density)
        return cn
