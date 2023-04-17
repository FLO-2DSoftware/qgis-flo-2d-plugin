# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

import collections
import math

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import os
import sys
import traceback
import warnings

sys.path.append(os.path.dirname(__file__))
from affine import Affine
from transform import TransformMethodsMixin

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from osgeo import gdal

    gdal.UseExceptions()


class GDALRasterLayer(TransformMethodsMixin):
    def __init__(self, raster_file):
        self.raster_file = raster_file
        self.ds = gdal.Open(raster_file)

    @property
    def transform(self):
        geotransform = self.ds.GetGeoTransform()
        return Affine.from_gdal(*geotransform)
