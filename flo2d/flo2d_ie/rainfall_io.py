# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import os

import numpy as np

from ..deps import safe_h5py as h5py

from qgis._core import QgsCoordinateTransform, QgsProject, QgsCoordinateReferenceSystem, QgsPointXY

from ..flo2d_tools.grid_tools import rasters2centroids
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from qgis.PyQt.QtWidgets import QProgressDialog


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
        self.vlayer = vlayer
        self.uc = UserCommunication(iface, "FLO-2D")

        try:
            from netCDF4 import Dataset, num2date
        except ImportError:
            msg = "The netCDF4 Python package is required to read NetCDF files. Please install it and try again."
            self.uc.bar_error(msg)
            self.uc.log_info(msg)
            raise ImportError(msg)

        self.nc = Dataset(nc_file, "r")
        self.iface = iface
        self.gutils = gutils

        convertion = 1000 if self.gutils.get_cont_par("METRIC") == "1" else 39.37  # Convert m to mm or m to inches

        self.tp = self.nc.variables["tp"][:] * convertion
        self.lat = self.nc.variables["latitude"][:]
        self.lon = self.nc.variables["longitude"][:]
        self.time = self.nc.variables["valid_time"]
        self.dates = num2date(self.time[:], self.time.units)

        if self.lat[0] < self.lat[-1]:  # Flip if needed
            self.lat = self.lat[::-1]
            self.tp = self.tp[:, ::-1, :]

        self.interval_minutes = 60
        self.n_steps = self.tp.shape[0]
        self.layer_crs = self.vlayer.crs()

        self.x_grid, self.y_grid, self.geotransform, self.crs_wkt = self.transform_lonlat_to_grid_crs(
            self.lon, self.lat, self.layer_crs
        )

    def transform_lonlat_to_grid_crs(self, lon, lat, target_crs):
        """
        Transforms ERA5 (lon, lat) grid into the target CRS (e.g., vlayer.crs()).
        Returns transformed x_grid, y_grid, geotransform, and target CRS WKT.
        """

        # Prepare transformer: EPSG:4326 → target_crs
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        transformer = QgsCoordinateTransform(wgs84, target_crs, QgsProject.instance())

        # Flip lat if needed (ERA5 is usually north-to-south)
        if lat[0] < lat[-1]:
            lat = lat[::-1]

        # Build meshgrid of (lon, lat)
        lon_grid, lat_grid = np.meshgrid(lon, lat)

        # Flatten for transformation
        flat_lon = lon_grid.flatten()
        flat_lat = lat_grid.flatten()

        # Transform each (lon, lat) to target CRS
        transformed_x = []
        transformed_y = []
        for x, y in zip(flat_lon, flat_lat):
            try:
                pt = transformer.transform(QgsPointXY(x, y))
                transformed_x.append(pt.x())
                transformed_y.append(pt.y())
            except Exception:
                transformed_x.append(np.nan)
                transformed_y.append(np.nan)

        # Reshape to 2D grid
        x_grid = np.array(transformed_x).reshape(lon_grid.shape)
        y_grid = np.array(transformed_y).reshape(lat_grid.shape)

        # Calculate uniform resolution (assumes regular grid)
        x_res = float(np.mean(np.diff(x_grid[0, :])))
        y_res = float(np.mean(np.diff(y_grid[:, 0])))

        # Upper-left corner
        ulx = x_grid[0, 0] - x_res / 2
        uly = y_grid[0, 0] + y_res / 2

        geotransform = (ulx, x_res, 0, uly, 0, -abs(y_res))
        crs_wkt = target_crs.toWkt()

        return x_grid, y_grid, geotransform, crs_wkt

    def parse_header(self):
        # Compute interval (in minutes) from first two timestamps
        delta = (self.dates[1] - self.dates[0]).total_seconds()
        interval_minutes = int(delta / 60)

        # Format start and end timestamps
        start_time = self.dates[0].strftime("%m/%d/%Y %H:%M")
        end_time = self.dates[-1].strftime("%m/%d/%Y %H:%M")

        intervals = str(len(self.dates))

        return [str(interval_minutes), intervals, f"{start_time} {end_time}"]

    def find_closest_era5_index(self, x, y):
        """
        Given a (x, y) point in layer CRS, find the closest ERA5 index (i, j)
        using Euclidean distance to the transformed ERA5 grid.
        """
        # Flatten the 2D grid
        flat_x = self.x_grid.flatten()
        flat_y = self.y_grid.flatten()

        # Compute squared distances
        dists_squared = (flat_x - x) ** 2 + (flat_y - y) ** 2

        # Get index of minimum distance
        min_idx = np.argmin(dists_squared)

        # Convert flat index to 2D index
        i, j = np.unravel_index(min_idx, self.x_grid.shape)

        return i, j

    def sample_all(self):
        """
        Generator yielding (val, fid) for each rainfall time step.
        """
        grid_centroids = self.gutils.grid_centroids_all()  # list of (fid, (x, y))
        grid_map = {}

        for fid, (x, y) in grid_centroids:
            i, j = self.find_closest_era5_index(x, y)
            grid_map[fid] = (i, j)

        for t in range(self.n_steps):
            rain_step = self.tp[t]  # shape (lat, lon)
            yield [(float(rain_step[i, j]), fid) for fid, (i, j) in grid_map.items()]


class TIFProcessor(object):
    def __init__(self, vlayer, tif_dir, iface):
        self.vlayer = vlayer
        self.tif_dir = tif_dir
        self.tif_files = []
        self.rfc = None
        self.header = []
        self.iface = iface
        self.uc = UserCommunication(iface, "FLO-2D")
        for f in sorted(os.listdir(tif_dir)):
            fpath = os.path.join(tif_dir, f)
            fpath_lower = fpath.lower()
            if fpath_lower.endswith((".tif", ".geotiff", ".tiff")):  # Sees if this is a file ending in ".tif", "geotiff", "tiff"
                self.tif_files.append(fpath)
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
        for raster_values in rasters2centroids(self.vlayer, None, *self.tif_files):
            yield raster_values

class HDFProcessor(object):
    def __init__(self, hdf_path, iface):
        self.uc = UserCommunication(iface, "FLO-2D")
        self.iface = iface
        self.con = None
        self.gutils = None
        self.hdf_path = hdf_path

    def export_rainfall_to_binary_hdf5(self, header, qry_data, qry_size, qry_timeinterval, subdomain):

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
            dts.attrs["description"] = np.array(["Rainfall data in the grid cells"], dtype=np.bytes_)

            progDialog = QProgressDialog("Exporting RealTime Rainfall (.HDF5)...", None, 0, int(irinters))
            progDialog.setModal(True)
            progDialog.setValue(0)
            progDialog.show()

            timeinterval = self.gutils.execute(qry_timeinterval).fetchall()

            i = 0
            for interval in timeinterval:
                progDialog.setValue(i)
                if not subdomain:
                    batch_query = qry_data + f" WHERE time_interval = {interval[0]} ORDER BY rrgrid, time_interval"
                else:
                    batch_query = qry_data + f" WHERE time_interval = {interval[0]} AND md.domain_fid = '{subdomain}' ORDER BY md.domain_cell, rd.time_interval"
                data = self.gutils.execute(batch_query).fetchall()
                data = np.array(data)
                dts[:, i] = data.flatten()
                i += 1

    def export_rainfallraw_to_binary_hdf5(self, header, raincellraw_qry_data, raincellraw_size, flo2draincell_qry_data, flo2draincell_size):

        con = self.iface.f2d["con"]
        if con is None:
            return
        self.con = con
        self.gutils = GeoPackageUtils(self.con, self.iface)

        with h5py.File(self.hdf_path, "w") as hdf_file:

            rainintime, irinters = header
            hdf_file.attrs["hdf5_version"] = np.array([h5py.version.hdf5_version], dtype=np.bytes_)
            hdf_file.attrs["plugin"] = np.array(["FLO-2D"], dtype=np.bytes_)
            grp = hdf_file.create_group("raincellraw")

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
            ]
            for name, value, description in datasets:
                dts = grp.create_dataset(name, data=value)
                dts.attrs["description"] = np.array([description], dtype=np.bytes_)

            # Scalar dataset
            n_lines = self.gutils.execute(raincellraw_size).fetchone()[0]
            dts = grp.create_dataset("RAINCELLRAW", (n_lines, 3), compression="gzip")
            dts.attrs["description"] = np.array(["Cumulative realtime rainfall data"], dtype=np.bytes_)

            # Export the RAINCELLRAW data
            for i, row in enumerate(self.gutils.execute(raincellraw_qry_data).fetchall()):
                dts[i, :] = np.array([row[0], row[1], row[2]])

            # Export the FLO2DRAINCELL data
            n_lines2 = self.gutils.execute(flo2draincell_size).fetchone()[0]
            dts = grp.create_dataset("FLO2DRAINCELL", (n_lines2, 2), compression="gzip")
            dts.attrs["description"] = np.array(["Intersected realtime rainfall data"], dtype=np.bytes_)
            progDialog = QProgressDialog("Exporting FLO2DRAINCELL (.HDF5)...", None, 0, int(n_lines2))
            progDialog.setModal(True)
            progDialog.setValue(0)
            progDialog.show()

            for i, row in enumerate(self.gutils.execute(flo2draincell_qry_data).fetchall()):
                progDialog.setValue(i)
                dts[i, :] = np.array([row[0], row[1]])

