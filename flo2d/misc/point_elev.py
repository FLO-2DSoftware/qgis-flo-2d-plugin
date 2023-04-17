# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import subprocess
import sys
import tempfile
import time
import timeit
import traceback
import warnings
from subprocess import PIPE, STDOUT, Popen

import numpy as np

sys.path.append(os.path.dirname(__file__))
from affine import Affine
from pip_install import pip_install

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from osgeo import gdal

    gdal.UseExceptions()
    from osgeo import osr

gdal_default_cachemax = gdal.GetCacheMax()  # bytes

GUI_STDIO = None


# Custom print function to communicate QGIS
def print_line(message, *arg, **kwargs):
    if GUI_STDIO is None:
        print(message, *arg, **kwargs)
    else:
        GUI_STDIO.logMessage.emit(message, False)


def install_dask():
    available = True
    try:
        import dask
        from dask.distributed import Client
    except:
        print_line("Missing dask dependencies.")
        print_line("Trying to install dask library ...\n")
        pip_install("dask[complete],dask[distributed],pandas", pipe=print_line)
        try:
            import dask
        except:
            print_line("Problem with dask library\n")
            print_line(traceback.format_exc() + "\n")
            available = False
    return available


def gdal_progress_callback(complete, message, data):
    value = complete * 100
    if len(data) == 1:
        # data[0] = 'Name of GDAL function'
        print_line(">>> Running %s\n" % data[0], end=" ", flush=True)
    else:
        print_line("{0:.0f}% ...".format(value), end=" ", flush=True)
        if value >= 100:
            print_line("Done.\n", end=" ", flush=True)
    data.append(value)
    return 1


def timer(function):
    def wrapper(*args, **kwargs):
        start_time = timeit.default_timer()
        try:
            return function(*args, **kwargs)
        finally:
            elapsed = timeit.default_timer() - start_time
            if elapsed < 60:
                elapsed = "{0:.4f} seconds".format(elapsed)
            elif elapsed >= 60 and elapsed < 3600:
                elapsed = "{0:.4f} minutes".format(elapsed / 60.0)
            elif elapsed >= 3600 and elapsed < 24 * 3600:
                elapsed = "{0:.4f} hours".format(elapsed / 3600)
            else:
                elapsed = "{0:.4f} days".format(elapsed / (24 * 3600))
            print_line('"{name}" took {time} to complete.\n'.format(name=function.__name__, time=elapsed))

    return wrapper


GDALGRID_METHOD_NAMES = ("average", "invdist", "invdistnn", "nearest", "linear", "linear")
GDALGRID_METHOD_DESC = (
    "Average",
    "Inverse Distance",
    "Inverse Distance Nearest Neighbor",
    "Nearest Neighbor",
    "Linear",
)
GDALGRID_METHOD_PARAMS = (
    "power",
    "smoothing",
    "angle",
    "radius",
    "radius1",
    "radius2",
    "min points",
    "max points",
    "nodata",
)
GDALGRID_METHOD_PARAM_DICT = {
    "Average": ("radius1", "radius2", "angle", "min points", "nodata"),
    "Inverse Distance": ("power", "smoothing", "angle", "radius1", "radius2", "min points", "max points", "nodata"),
    "Inverse Distance Nearest Neighbor": ("power", "smoothing", "radius", "min points", "max points", "nodata"),
    "Nearest Neighbor": ("angle", "radius1", "radius2", "nodata"),
    "Linear": ("radius", "nodata"),
}


class ResamplingOption:
    def __init__(self, method, **kwargs):
        if method == "Inverse Distance":
            self.power = kwargs.get("power", 2)
            self.smoothing = kwargs.get("power", 0)
            self.radius1 = kwargs.get("radius1", 0)
            self.radius2 = kwargs.get("radius2", 0)
            self.angle = kwargs.get("angle", 0)
            self.max_points = kwargs.get("max_points", 0)
            self.min_points = kwargs.get("min_points", 0)
            self.nodata = kwargs["nodata"]

        elif method == "Inverse Distance Nearest Neighbor":
            self.power = kwargs.get("power", 2)
            self.smoothing = kwargs.get("power", 0)
            self.radius = kwargs.get("radius", 0)
            self.max_points = kwargs.get("max_points", 12)
            self.min_points = kwargs.get("min_points", 0)
            self.nodata = kwargs["nodata"]

        elif method == "Average":
            self.radius1 = kwargs.get("radius1", 0)
            self.radius2 = kwargs.get("radius2", 0)
            self.angle = kwargs.get("angle", 0)
            self.min_points = kwargs.get("min_points", 1)
            self.nodata = kwargs["nodata"]

        elif method == "Nearest Neighbor":
            self.radius1 = kwargs.get("radius1", 0)
            self.radius2 = kwargs.get("radius2", 0)
            self.angle = kwargs.get("angle", 0)
            self.nodata = kwargs["nodata"]

        elif method == "Linear":
            self.radius = kwargs.get("radius", -1)
            self.nodata = kwargs["nodata"]

        else:
            raise Exception("Gdal Grid Resampling method is not valid")

        self.method = GDALGRID_METHOD_NAMES[GDALGRID_METHOD_DESC.index(method)]

    def string(self):
        if self.method == "invdist":
            result = (
                "%s:power=%s:smoothing=%s:radius1=%s:radius2=%s:"
                "angle=%s:min_points=%s:max_points=%s:nodata=%s"
                ""
                % (
                    self.method,
                    self.power,
                    self.smoothing,
                    self.radius1,
                    self.radius2,
                    self.angle,
                    self.min_points,
                    self.max_points,
                    self.nodata,
                )
            )

        elif self.method == "invdistnn":
            result = (
                "%s:power=%s:smoothing=%s:radius=%s:"
                "min_points=%s:max_points=%s:nodata=%s"
                ""
                % (self.method, self.power, self.smoothing, self.radius, self.min_points, self.max_points, self.nodata)
            )

        elif self.method == "average":
            result = (
                "%s:radius1=%s:radius2=%s:"
                "angle=%s:min_points=%s:nodata=%s"
                "" % (self.method, self.radius1, self.radius2, self.angle, self.min_points, self.nodata)
            )

        elif self.method == "nearest":
            result = (
                "%s:radius1=%s:radius2=%s:"
                "angle=%s:nodata=%s"
                "" % (self.method, self.radius1, self.radius2, self.angle, self.nodata)
            )

        elif self.method == "linear":
            result = "%s:radius=%s:" "nodata=%s" "" % (self.method, self.radius, self.nodata)
        else:
            print("Invalid resampling method")
        return result


def get_temp_filepath(src_path, suffix, prefix="temp_"):
    out_directory = src_path
    if not os.path.isdir(src_path):
        out_directory = os.path.dirname(src_path)

    temp_file = tempfile.NamedTemporaryFile("w", prefix=prefix, suffix=suffix, dir=out_directory, delete=False)
    outpath = temp_file.name
    temp_file.close()
    os.unlink(outpath)
    return outpath


def colrow_from_transform(transform, x, y):
    # Returns column, row tuple corresponding to x,y coordinates
    ulX = transform[0]
    ulY = transform[3]
    xDist = transform[1]
    yDist = transform[5]
    col = int((x - ulX) / xDist)
    row = int((ulY - y) / xDist)
    return (col, row)


def create_vrt_file(xyz_filepath, vrt_outpath, x="X", y="Y", z="Z", layername="TOPOXYZ"):
    # create VRT file used as raster input to GDALGRID
    base_path, ext = os.path.splitext(xyz_filepath)
    xyz_name = os.path.abspath(base_path).split(os.sep)[-1]  # filename excluding extension and parent path
    # vrt_out =  '{}.vrt'.format(base_path)
    vrt_string = (
        "<OGRVRTDataSource>\n"
        '     <OGRVRTLayer name="%s">\n'
        "          <SrcDataSource>%s</SrcDataSource>\n"
        "          <SrcLayer>%s</SrcLayer>\n"
        "          <GeometryType>wkbPoint</GeometryType>\n"
        '          <GeometryField encoding="PointFromColumns" x="%s" y="%s" z="%s"/>\n'
        "     </OGRVRTLayer>\n"
        "</OGRVRTDataSource>"
    )
    vrt_string = vrt_string % (layername, xyz_filepath, xyz_name, x, y, z)
    with open(vrt_outpath, "w") as fid:
        fid.write(vrt_string)
    return vrt_outpath


@timer
def clip_raster_aligned(raster_inpath, raster_outpath, clip_extents):
    # clip raster larger or equal to the grid
    # clip_extents = (xmin,ymin,xmax,ymax)
    ds = gdal.Open(raster_inpath)
    geo_transform = ds.GetGeoTransform()
    src_rows, src_cols = ds.RasterYSize, ds.RasterXSize
    xmin, ymin, xmax, ymax = clip_extents
    ul_col, ul_row = colrow_from_transform(geo_transform, xmin, ymax)
    lr_col, lr_row = colrow_from_transform(geo_transform, xmax, ymin)
    # TODO: check the extents
    dst_rows = lr_row - ul_row + 1
    dst_cols = lr_col - ul_col + 1
    gdal_callback_data = ["Raster-Clip"]
    opt = gdal.TranslateOptions(
        srcWin=[ul_col, ul_row, dst_cols, dst_rows],
        format="GTiff",
        callback=gdal_progress_callback,
        callback_data=gdal_callback_data,
    )
    gdal.Translate(raster_outpath, ds, options=opt)
    ds = None


@timer
def raster_to_xyz(raster_inpath, xyz_outpath, set_integer_nodata=False, remove_nodata=True):
    if os.path.exists(xyz_outpath):
        os.unlink(xyz_outpath)

    # In order to remove nodata points from xyz file, the nodata must be integer
    # Replace nodata with -9999 if source nodata is float
    raster_src = raster_inpath
    ds = gdal.Open(raster_src)
    band = ds.GetRasterBand(1)
    src_nodata = band.GetNoDataValue()

    if set_integer_nodata:
        # replace nodata using gdal Warp
        src_nodata = -9999.0
        base_path, ext = os.path.splitext(raster_src)
        raster_dest = "{}_9999{}".format(base_path, ext)
        warp_opt = gdal.WarpOptions(
            dstNodata=src_nodata,
            warpMemoryLimit=1000,
            multithread=True,  # multithread compute and I/O operations
            warpOptions=["NUM_THREADS=ALL_CPUS"],  # multithread compute
        )
        gdal.Warp(raster_dest, raster_src, options=warp_opt)
        raster_src = raster_dest
        ds, band = (None, None)
        ds = gdal.Open(raster_src)
    else:
        src_nodata = src_nodata + 1  # large negative nodata expected

    # Export to XYZ file containing nodata values
    @timer
    def _raster_to_xyz():
        gdal_callback_data = ["Raster-to-XYZ"]
        # Note: DECIMAL_PRECISION works with gdal >= 3.0.0.
        trans_opt = gdal.TranslateOptions(
            creationOptions=["DECIMAL_PRECISION=4", "COLUMN_SEPARATOR=COMMA", "ADD_HEADER_LINE=YES"],
            format="XYZ",
            callback=gdal_progress_callback,
            callback_data=gdal_callback_data,
        )

        gdal.Translate(xyz_outpath, ds, options=trans_opt)

    _raster_to_xyz()

    gdal_callback_data = None
    print_line("Continue ...\n")

    # Remove nodata from XYZ file and save in another file, whose filename is random
    xyz_temp_outpath = get_temp_filepath(xyz_outpath, os.path.splitext(xyz_outpath)[1])

    @timer
    def _remove_xyz_nodata():
        if not install_dask():
            gdal_callback_data = ["XYZ file--Remove Nodata"]
            ogr_opt = gdal.VectorTranslateOptions(
                format="CSV",
                accessMode="overwrite",
                SQLStatement="SELECT CAST(X as float),CAST(Y as float),CAST(Z as float) FROM {0:s} WHERE Z > '{1:f}'".format(
                    os.path.basename(xyz_outpath)[:-4], src_nodata
                ),
                options=["SEPARATOR=COMMA"],  # 'STRING_QUOTING=IF_NEEDED'],
                callback=gdal_progress_callback,
                callback_data=gdal_callback_data,
            )
            gdal.VectorTranslate(xyz_temp_outpath, xyz_outpath, options=ogr_opt)
        else:
            print_line(">>> Using dask to remove nodata from XYZ file.\n")
            import dask.dataframe as dd

            df = dd.read_csv(xyz_outpath)
            df_revised = df[df.Z > src_nodata]
            df_revised.to_csv(xyz_temp_outpath, single_file=True, index=False)

    if remove_nodata:
        _remove_xyz_nodata()
        if os.path.exists(xyz_temp_outpath):
            os.replace(xyz_temp_outpath, xyz_outpath)

    # Clean up ........................................
    ds, band = (None, None)  # this may be not necessary
    if raster_src != raster_inpath:
        os.unlink(raster_src)

    return xyz_outpath


@timer
def xyz_to_raster(xyz_inpath, extents, shape, resampling_option, srs, layername="TOPOXYZ", z="Z"):
    base_path, ext = os.path.splitext(xyz_inpath)
    vrt_filepath = "{}_gdalgrid.vrt".format(base_path)
    raster_outpath = "{}_gdalgrid.tif".format(base_path)
    if os.path.exists(vrt_filepath):
        os.unlink(vrt_filepath)
    if os.path.exists(raster_outpath):
        os.unlink(raster_outpath)

    create_vrt_file(xyz_inpath, vrt_filepath)

    resampling_method_string = resampling_option.string()
    llx, lly, urx, ury = extents
    height, width = shape
    ulx = llx
    uly = ury
    lrx = urx
    lry = lly

    gdal_callback_data = ["XYZ-to-Raster"]
    opt = gdal.GridOptions(
        width=width,
        height=height,
        outputBounds=[ulx, uly, lrx, lry],
        layers=[layername],
        zfield=z,
        outputSRS=srs,
        algorithm=resampling_method_string,
        format="GTiff",
        callback=gdal_progress_callback,
        callback_data=gdal_callback_data,
    )

    gdal.Grid(raster_outpath, vrt_filepath, options=opt)

    if os.path.exists(vrt_filepath):
        os.unlink(vrt_filepath)

    return raster_outpath


@timer
def xyz_to_raster_gds_average(csv_file, extents, shape, srs, open_dashboard, procs, threads, nodata=None):
    print_line("XYZ-to-Raster-Average\n")
    if install_dask():
        base_path, ext = os.path.splitext(csv_file)
        raster_outpath = "{}_gdsgrid.tif".format(base_path)  # hard-coded path
        py_script = os.path.join(os.path.dirname(__file__), "calc_average_elev.py")
        xmin, ymin, xmax, ymax = [str(x) for x in extents]
        rows, cols = [str(x) for x in shape]
        try:
            result = subprocess.run(
                [
                    "python3",
                    py_script,
                    csv_file,
                    xmin,
                    ymin,
                    xmax,
                    ymax,
                    rows,
                    cols,
                    srs,
                    str(open_dashboard),
                    str(procs),
                    str(threads),
                    str(nodata),
                ],
                capture_output=True,
                check=True,
                # stdout = PIPE,
                # stderr= STDOUT,
                text=True,
                env=os.environ,
            )
        except subprocess.CalledProcessError as e:
            print_line("Subprocess output: %s" % e.output)
            print_line("Subprocess STDError: %s" % e.stderr)
            raise Exception("xyz to raster failed. Check the printed error message.")

        else:
            print_line("Subprocess STDOUT: %s" % result.stdout)
            return raster_outpath


if __name__ == "__main__":
    extents = (656965.3593088828492910, 957283.4235482572112232, 665321.0101062507601455, 963900.0000000000000000)
    cell_size = 30
    xmin, ymin, xmax, ymax = extents
    srs = r"+proj=tmerc +lat_0=31 +lon_0=-111.9166666666667 +k=0.9999 +x_0=213360 +y_0=0 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=ft +no_defs"
    rows = int((ymax - ymin) / cell_size)
    cols = int((xmax - xmin) / cell_size)
    shape = (rows, cols)
    transform = Affine(cell_size, 0, xmin, 0, -cell_size, ymax)
    xyz_file = os.path.join(r"C:\projects\FLO-2D\Lesson1 welev", "Elevation_xyz.csv")
    raster_grid = r"C:\projects\FLO-2D\Lesson1 welev\Elevation_xyz_gdalgrid.tif"
    # test code follows
