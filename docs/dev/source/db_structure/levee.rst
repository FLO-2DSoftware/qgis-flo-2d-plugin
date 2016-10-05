LEVEE.DAT
=========

LEVEE.DAT information goes into the following GeoPackage tables:

* levee_general - general levee parameters
* levee_data - parameters of a levee in a grid cell
* levee_failure - grid cells with a failure potential
* levee_fragility - individual levee grid element fragility curve table

.. figure:: img/levee.png
   :align: center

:download:`LEVEE.DAT tables schema <img/levee.png>`

**gpkg table: levee_general** (general levee parameters)

* "fid" INTEGER NOT NULL PRIMARY KEY,
* "raiselev" REAL, -- RAISELEV, incremental height that all the levee grid element crest elevations are raised
* "ilevfail" INTEGER, -- ILEVFAIL, switch identifying levee failure mode: 0 for no failure, 1 for prescribed level failure rates, 2 for initiation of levee or dam breach failure routine
* "gfragchar" TEXT, -- GFRAGCHAR, global levee fragility curve ID
* "gfragprob"  REAL -- GFRAGPROB, global levee fragility curve failure probability

**gpkg table: levee_data** (grid cells with a levee defined)

* "fid" INTEGER NOT NULL PRIMARY KEY,
* "grid_fid" INTEGER -- LGRIDNO, grid element fid with a levee
* "ldir" INTEGER -- LDIR, flow direction that will be cutoff (1-8)
* "levcrest" REAL, -- LEVCREST, the elevation of the levee crest
* "geom" LINESTRING - levee segment geometry - one of the 8 grid cell sides

**gpkg table: levee_failure** (grid cells with a failure potential)

* "fid" INTEGER NOT NULL PRIMARY KEY,
* "grid_fid" INTEGER, -- LFAILGRID, grid element fid with a failure potential
* "lfaildir" INTEGER, -- LFAILDIR, the potential failure direction
* "failevel" REAL, -- FAILEVEL, the maximum elevation of the prescribed levee failure
* "failtime" REAL, -- FAILTIME, the duration (hr) that the levee will fail after the FAILEVEL elevation is exceeded by the flow depth
* "levbase" REAL, -- LEVBASE, the prescribed final failure elevation
* "failwidthmax" REAL, -- FAILWIDTHMAX, the maximum breach width
* "failrate" REAL, -- FAILRATE, the rate of vertical levee failure
* "failwidrate" REAL, -- FAILWIDREAL, the rate at which the levee breach widens

**gpkg table: levee_fragility** (individual levee grid element fragility curve table)

* "fid" INTEGER NOT NULL PRIMARY KEY,
* "grid_fid" INTEGER, -- LEVFRAGGRID, grid element fid with an individual fragility curve assignment
* "levfragchar" TEXT, -- LEVFRAGCHAR, levee fragility curve ID
* "levfragprob" REAL -- LEVFRAGPROB, levee fragility curve failure probability

