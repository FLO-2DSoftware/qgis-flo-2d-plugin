import os
import sys
import traceback
import warnings

import dask
import dask.dataframe as dd
import numpy as np
from dask.distributed import Client

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from osgeo import gdal

    gdal.UseExceptions()
    from osgeo import osr

sys.path.append(os.path.dirname(__file__))

from affine import Affine
from transform import rowcol

if __name__ == "__main__":
    args = sys.argv
    # args[0] = calc_average_elev.py file
    # args[1] = csv file path
    # args[2] = xmin
    # args[3] = ymin
    # args[4] = xmax
    # args[5] = ymax
    # args[6] = raster rows
    # args[7] = raster columns
    # args[8] = wkt or proj crs string
    # args[9] = true/false flag for dask dashboard
    # args[10] = process count
    # args[11] = thread count per process
    # args[12] = nodata value or None string
    print(args)
    # Parse arguments
    csv_file = os.path.abspath(args[1])
    extents = [float(x) for x in args[2:6]]
    shape = [int(x) for x in args[6:8]]
    srs = args[8]
    open_dashboard = args[9].lower()
    if open_dashboard in ["0", "false"]:
        open_dashboard = False
    else:
        open_dashboard = True

    nprocs = int(args[10])
    nthreads = int(args[11])
    nodata = args[12]

    print(
        f"Given arguments: csv file = {csv_file}\n"
        f"extents = {extents}\n"
        f"shape = {shape}\n"
        f"srs = {srs}\n"
        f"open_dashboard = {open_dashboard}"
    )
    grid_nodata = "-9999"
    xmin, ymin, xmax, ymax = extents
    cellsize = (ymax - ymin) * 1.0 / shape[0]
    transform = Affine(cellsize, 0, xmin, 0, -cellsize, ymax)

    # Provide custom core and thread counts here
    client = Client(processes=True, n_workers=nprocs, threads_per_worker=nthreads)
    print("Using %s threads" % (len(client.nthreads())))
    print("Compute scheduler info: %r" % client)

    try:
        if open_dashboard:
            os.startfile(client.dashboard_link)

        def pixel_coord_from_xy(row, trans, rows, cols):
            # TODO: Check if this operation on dataframe can be vectorized using
            # numba jit
            r, c = rowcol(trans, row.X, row.Y)
            result = grid_nodata
            if r < rows and r >= 0 and c < cols and c >= 0:
                result = "{}_{}".format(r, c)
            return result

        # find raster position for each data point and
        # compute average elevation for each pixel
        df = dd.read_csv(csv_file, dtype={"X": float, "Y": float, "Z": float})
        if not nodata in ["None", "none"]:
            df = df[df.Z > (float(nodata) + 0.1)]  # assuming elevation smaller than nodata is nodata too
        df["gridno"] = str(grid_nodata)
        df["gridno"] = df.apply(
            pixel_coord_from_xy,
            axis=1,
            args=(transform, shape[0], shape[1]),
            meta=("str"),
        )
        print("Long computation ...\n")
        series = df.groupby("gridno").Z.mean().compute()

        # remove out of bound data
        try:
            series.pop(grid_nodata)
        except:
            pass

    except:
        print(traceback.format_exc())
        raise Exception("Problem with dask computation")

    else:
        print("XYZ to Raster process finished.")

    finally:
        client.close()

    def _create_raster():
        print("Creating raster file\n")
        base_path, ext = os.path.splitext(csv_file)
        raster_outpath = "{}_gdsgrid.tif".format(base_path)
        if os.path.exists(raster_outpath):
            os.unlink(raster_outpath)
        raster_array = np.full(shape, int(grid_nodata), dtype=np.float32)
        for key, avg_elev in series.items():
            r, c = [int(x) for x in key.split("_")]
            raster_array[r, c] = avg_elev

        driver = gdal.GetDriverByName("GTiff")
        ds = driver.Create(raster_outpath, shape[1], shape[0], 1, gdal.GDT_Float32)
        crs = osr.SpatialReference()
        wkt = srs
        try:
            # check if srs is Proj
            crs.ImportFromProj4(srs)
            wkt = crs.ExportToWkt()
        except:
            pass

        ds.SetProjection(wkt)
        ds.SetGeoTransform(transform.to_gdal())
        band = ds.GetRasterBand(1)
        band.WriteArray(raster_array)
        band.SetNoDataValue(float(grid_nodata))
        band.FlushCache()
        ds = None
        return raster_outpath

    raster_outpath = _create_raster()
    print("Ok\n")
