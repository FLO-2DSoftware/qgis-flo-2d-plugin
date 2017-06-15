# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
from flo2d.flo2d_tools.grid_tools import rasters2centroids


class ASCProcessor(object):

    def __init__(self, vlayer, asc_dir):
        self.vlayer = vlayer
        self.asc_dir = asc_dir
        self.asc_files = []
        self.rfc = None
        self.header = []
        for f in sorted(os.listdir(asc_dir)):
            fpath = os.path.join(asc_dir, f)
            fpath_lower = fpath.lower()
            if fpath_lower.endswith('.asc'):
                self.asc_files.append(fpath)
            elif fpath_lower.endswith('.rfc'):
                self.rfc = fpath
            else:
                continue

    def parse_rfc(self):
        if self.rfc is None:
            return
        with open(self.rfc) as rfc_file:
            rfc_params = rfc_file.readline().strip().split()
            timestamp = ' '.join(rfc_params[:4])
            interval_time = rfc_params[4]
            intervals_number = rfc_params[5]
            self.header += [interval_time, intervals_number, timestamp]
        return self.header

    def rainfall_sampling(self):
        for raster_values in rasters2centroids(self.vlayer, None, *self.asc_files):
            yield raster_values


class HDFProcessor(object):

    def __init__(self, header, data, hdf_path):
        self.header = header
        self.data = data
        self.hdf_path = hdf_path
