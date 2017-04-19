# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import traceback
from math import log, exp
from collections import defaultdict, OrderedDict
from itertools import izip
from operator import itemgetter

from PyQt4.QtCore import QPyNullVariant
from qgis.core import QgsSpatialIndex, QgsFeature, QgsFeatureRequest, QgsVector, QgsGeometry, QgsPoint

from grid_tools import grid_intersections
from flo2d.geopackage_utils import GeoPackageUtils


class InfiltrationCalculator(GeoPackageUtils):

    def __init__(self, con, iface, lyrs):
        super(InfiltrationCalculator, self).__init__(con, iface)
        self.lyrs = lyrs
        self.schema_grid_lyr = self.lyrs.data['grid']['qlyr']
        self.land_lyr = None
        self.land_field = None
        self.soil_lyr = None
        self.soil_field = None
        self.impervious_lyr = None
        self.impervious_field = None

    def setup_green_ampt(self, land, land_fld, soil, soil_fld):
        self.land_lyr = land
        self.land_field = land_fld
        self.soil_lyr = soil
        self.soil_field = soil_fld

    def setup_scp(self, land, land_fld, soil, soil_fld, impervious, impervious_fld):
        self.land_lyr = land
        self.land_field = land_fld
        self.soil_lyr = soil
        self.soil_field = soil_fld
        self.impervious_lyr = impervious
        self.impervious_field = impervious_fld

    def green_ampt_infiltration(self):
        grid_params = {}
        soil_values = grid_intersections(self.schema_grid_lyr, self.soil_lyr)


class GreenAmpt(object):

    def __init__(self, gid, soil_params, land_use):
        self.gid = gid
        self.parameters = {}

    @staticmethod
    def calculate_xksat(part_area, part_xksat, full_area):
        # avg_xksat = exp((0.625 * log(0.40) + 0.375 * log(0.06)) / 1)
        xksat_gen = (part_area * log(part_xksat))
        avg_xksat = exp(sum(xksat_gen) / full_area)
        return avg_xksat

    @staticmethod
    def calculate_psif(avg_xksat):
        if 0.01 <= avg_xksat <= 1.2:
            psif = exp(0.9813 - 0.439 * log(avg_xksat) + 0.0051 * (log(avg_xksat)) ** 2 + 0.0060 * (log(avg_xksat)) ** 3)
            return psif
        else:
            raise ValueError

    @staticmethod
    def calculate_dtheta(avg_xksat, saturation):
        if saturation == 'dry':
            if 0.01 <= avg_xksat <= 0.15:
                dtheta = exp(-0.2394 + 0.3616 * log(avg_xksat))
            elif 0.15 < avg_xksat <= 0.25:
                dtheta = exp(-1.4122 - 0.2614 * log(avg_xksat))
            elif 0.25 < avg_xksat <= 1.2:
                dtheta = 0.35
            else:
                raise ValueError
        elif saturation == 'normal':
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
            elif 0.4 < avg_xksat <= 1.2:
                dtheta = exp(-1.2342 + 0.1660 * log(avg_xksat))
            else:
                raise ValueError
        elif saturation == 'wet' or saturation == 'saturated':
            dtheta = 0
        else:
            raise ValueError
        return dtheta

    @staticmethod
    def calculate_xksatc(avg_xksat, part_area, part_vc):
        part_c = (part_vc - 10) / 90 + 1


class SCPCurveNumber(object):

    def __init__(self):
        pass
