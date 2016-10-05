WSTIME.DAT
==========

WSTIME.DAT information goes into the following GeoPackage tables:

* wstime - point layer with water surface elevation in time for comparison

**gpkg table: wstime**

* "fid" INTEGER NOT NULL PRIMARY KEY,
* "grid_fid" INTEGER, -- IGRIDXSEC, fid of grid cell containing WSEL data
* "wselev" REAL, -- WSELEVTIME, water surface elevation for comparison
* "wstime" REAL -- WSTIME, time of known watersurface elevation
* "geom" POINT -- on import: create the geometry as centroid of grid cell with fid = IGRIDXSEC

