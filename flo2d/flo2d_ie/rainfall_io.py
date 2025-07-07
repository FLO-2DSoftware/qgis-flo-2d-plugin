# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import os

import numpy as np
from netCDF4 import Dataset, num2date
from osgeo import osr
from scipy.interpolate import griddata

from ..flo2d_tools.grid_tools import rasters2centroids, spatial_index
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from qgis.PyQt.QtWidgets import QProgressDialog

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

class NetCDFProcessor:
    def __init__(self, vlayer, nc_file, iface, gutils):
        self.gutils = gutils
        self.vlayer = vlayer
        self.nc = Dataset(nc_file, "r")
        self.iface = iface
        self.uc = UserCommunication(iface, "FLO-2D")

        # Load coordinates and data
        self.tp = self.nc.variables["tp"]  # shape: (time, lat, lon)
        self.lat = self.nc.variables["latitude"][:]
        self.lon = self.nc.variables["longitude"][:]
        self.time = self.nc.variables["valid_time"]
        self.dates = num2date(self.time[:], self.time.units)

        # Create meshgrid
        self.lon_grid, self.lat_grid = np.meshgrid(self.lon, self.lat)

        # Get grid CRS from database
        grid_crs = self.gutils.get_grid_crs()
        epsg_code = int(grid_crs.split(":")[1])
        self.grid_srs = osr.SpatialReference()
        self.grid_srs.ImportFromEPSG(epsg_code)

        self.era5_srs = osr.SpatialReference()
        self.era5_srs.ImportFromEPSG(4326)  # ERA5 is in WGS84
        self.tx = osr.CoordinateTransformation(self.grid_srs, self.era5_srs)  # EPSG:31982 -> WGS84

        # Build mapping between FLO-2D grid and NetCDF grid
        self.grid_map = []  # list of (fid, i, j) tuples
        self.build_grid_mapping()

    def build_grid_mapping(self):
        lat_vals = self.lat
        lon_vals = self.lon

        grid_centroids = self.gutils.grid_centroids_all()

        for fid, (x, y) in grid_centroids:
            lon, lat, _ = self.tx.TransformPoint(x, y)
            i = np.abs(lat_vals - lat).argmin()
            j = np.abs(lon_vals - lon).argmin()
            self.grid_map.append((fid, i, j))

    def parse_header(self):
        # Compute interval (in minutes) from first two timestamps
        delta = (self.dates[1] - self.dates[0]).total_seconds()
        interval_minutes = int(delta / 60)

        # Format start and end timestamps
        start_time = self.dates[0].strftime("%m/%d/%Y %H:%M")
        end_time = self.dates[-1].strftime("%m/%d/%Y %H:%M")

        intervals = str(len(self.dates))

        return [str(interval_minutes), intervals, f"{start_time} {end_time}"]

    def rainfall_sampling(self):
        for i, date in enumerate(self.dates):
            values = self.tp[i, :, :] * 1000  # meters to mm
            series = []
            for fid, ilat, ilon in self.grid_map:
                val = float(values[ilat, ilon])
                val = val if not np.isnan(val) else 0.0
                series.append((val, fid))
            yield series


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
            hdf_file.attrs["hdf5_version"] = np.array([h5py.version.hdf5_version], dtype=np.bytes_)
            hdf_file.attrs["plugin"] = np.array(["FLO-2D"], dtype=np.bytes_)
            grp = hdf_file.create_group("raincell")
            tstamp = np.array([timestamp], dtype=np.bytes_)

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
                dts.attrs["description"] = np.array([description], dtype=np.bytes_)

            # Scalar dataset
            n_cells = self.gutils.execute(qry_size).fetchone()[0] / irinters
            dts = grp.create_dataset("IRAINDUM", (n_cells, int(irinters)), compression="gzip")

            progDialog = QProgressDialog("Exporting RealTime Rainfall (.HDF5)...", None, 0, int(irinters))
            progDialog.setModal(True)
            progDialog.setValue(0)
            progDialog.show()

            timeinterval = self.gutils.execute(qry_timeinterval).fetchall()

            i = 0
            for interval in timeinterval:
                progDialog.setValue(i)
                batch_query = qry_data + f" WHERE time_interval = {interval[0]} ORDER BY rrgrid, time_interval"
                data = self.gutils.execute(batch_query).fetchall()
                data = np.array(data)
                dts[:, i] = data.flatten()
                i += 1

