# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import os

import numpy as np

from ..flo2d_tools.grid_tools import rasters2centroids

try:
    import h5py
except ImportError:
    pass


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
            if fpath_lower.endswith(".asc"):  # Sees if this is a file ending in .asc.
                self.asc_files.append(fpath)
            elif fpath_lower.endswith(".rfc"):  # Sees if this is a file ending in .rfc (RainFall Catalogue).
                self.rfc = fpath
            else:
                continue

    def parse_rfc(self):
        if self.rfc is None:
            return
        with open(self.rfc) as rfc_file:
            rfc_params = rfc_file.readline().strip().split()
            timestamp = " ".join(rfc_params[:4])
            interval_time = rfc_params[4]
            intervals_number = rfc_params[5]
            self.header += [interval_time, intervals_number, timestamp]
        return self.header

    def rainfall_sampling(self):
        for raster_values in rasters2centroids(self.vlayer, None, *self.asc_files):
            yield raster_values


class HDFProcessor(object):
    def __init__(self, hdf_path):
        self.hdf_path = hdf_path

    def export_rainfall_to_binary_hdf5(self, header, data):
        with h5py.File(self.hdf_path, "w") as hdf_file:
            rainintime, irinters, timestamp = header
            hdf_file.attrs["hdf5_version"] = np.array([h5py.version.hdf5_version], dtype=np.string_)
            hdf_file.attrs["plugin"] = np.array(["FLO-2D"], dtype=np.string_)
            grp = hdf_file.create_group("raincell")
            tstamp = np.array([timestamp], dtype=np.string_)
            datasets = [
                ("RAININTIME", np.int(rainintime), "Time interval in minutes of the realtime rainfall data."),
                ("IRINTERS", np.int(irinters), "Number of intervals in the dataset."),
                ("TIMESTAMP", tstamp, "Timestamp indicates the start and end time of the storm."),
                ("IRAINDUM", np.array(data), "Cumulative rainfall in inches or mm over the time interval."),
            ]
            for name, value, description in datasets:
                dts = grp.create_dataset(name, data=value)
                dts.attrs["description"] = np.array([description], dtype=np.string_)
