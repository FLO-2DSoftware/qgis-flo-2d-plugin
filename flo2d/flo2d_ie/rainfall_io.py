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
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from qgis.PyQt.QtWidgets import QProgressBar

try:
    import h5py
except ImportError:
    pass


class ASCProcessor(object):
    def __init__(self, vlayer, asc_dir, iface):
        self.vlayer = vlayer
        self.asc_dir = asc_dir
        self.asc_files = []
        self.rfc = None
        self.header = []
        self.iface = iface
        self.uc = UserCommunication(iface, "FLO-2D")
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
    def __init__(self, hdf_path, iface):
        self.iface = iface
        self.con = None
        self.gutils = None
        self.hdf_path = hdf_path
        self.uc = UserCommunication(iface, "FLO-2D")

    def export_rainfall_to_binary_hdf5(self, header, qry_data, qry_size, qry_timeinterval):

        con = self.iface.f2d["con"]
        if con is None:
            return
        self.con = con
        self.gutils = GeoPackageUtils(self.con, self.iface)

        with h5py.File(self.hdf_path, "w") as hdf_file:

            rainintime, irinters, timestamp = header
            hdf_file.attrs["hdf5_version"] = np.array([h5py.version.hdf5_version], dtype=np.string_)
            hdf_file.attrs["plugin"] = np.array(["FLO-2D"], dtype=np.string_)
            grp = hdf_file.create_group("raincell")
            tstamp = np.array([timestamp], dtype=np.string_)

            # Not scalar datasets
            datasets = [
                (
                    "RAININTIME",
                    int(rainintime),
                    "Time interval in minutes of the realtime rainfall data.",
                ),

                (
                    "IRINTERS",
                    int(irinters),
                    "Number of intervals in the dataset."),

                (
                    "TIMESTAMP",
                    tstamp,
                    "Timestamp indicates the start and end time of the storm.",
                )
            ]
            for name, value, description in datasets:
                dts = grp.create_dataset(name, data=value)
                dts.attrs["description"] = np.array([description], dtype=np.string_)

            # Scalar dataset
            n_cells = self.gutils.execute(qry_size).fetchone()[0] / irinters
            dts = grp.create_dataset("IRAINDUM", (n_cells, int(irinters)), compression="gzip")

            pb = self.uc.progress_bar2("Exporting RealTime Rainfall...", 0, int(irinters), 0)
            timeinterval = self.gutils.execute(qry_timeinterval).fetchall()

            i = 0
            for interval in timeinterval:
                pb.setValue(i)
                batch_query = qry_data + f" WHERE time_interval = {interval[0]} ORDER BY rrgrid, time_interval"
                data = self.gutils.execute(batch_query).fetchall()
                data = np.array(data)
                dts[:, i] = data.flatten()
                i += 1

            pb.close()
