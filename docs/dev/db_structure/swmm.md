
<a name="swmmflo"></a>
## SWMMFLO.DAT 

SWMMFLO.DAT information goes into the following GeoPackage tables:

* swmmflo - polygon layer of grid cells with SWMM drain inlets

![SWMM tables graph](db_schema_graphs/swmm.png)

**gpkg table: swmmflo** 

* "fid" INTEGER NOT NULL PRIMARY KEY,
* "swmm_jt" INTEGER -- SWMM_JT, fid of the grid element with storm drain inlet
* "intype" INTEGER, -- INTYPE, inlet type (1-5)
* "swmm_length" REAL, -- SWMMlength, storm drain inlet curb opening lengths along the curb
* "swmm_height" REAL, -- SWMMheight, storm drain curb opening height
* "swmm_coeff" REAL, -- SWMMcoeff, storm drain inlet weir discharge coefficient
* "flapgate" INTEGER -- FLAPGATE, switch (0 no flap gate, 1 flapgate)
* "name" TEXT, -- optional inlet name
* "geom" POLYGON -- grid element with storm drain inlet, on import: create the geometry as grid cell with fid = SWMM_JT


<a name="swmmflort"></a>
## SWMMFLORT.DAT 


SWMMFLORT.DAT information goes into the following GeoPackage tables:

* swmmflort - rating tables for storm drain inlets
* swmmflort_data - storm drain rating tables data

**gpkg table: swmmflort** 

* "fid" INTEGER NOT NULL PRIMARY KEY,
* "grid_fid" INTEGER -- SWMM_JT, fid of the grid element with a storm drain inlet
* "name" TEXT, -- optional name of the rating table

**gpkg table: swmmflort_data** 

* "fid" INTEGER NOT NULL PRIMARY KEY,
* "swmm_rt_fid" INTEGER, -- fid of a rating table from swmmflort
* "depth" REAL, -- DEPTHSWMMRT, flow depths for the discharge rating table pairs
* "q" REAL -- QSWMMRT, discharge values for the storm drain inlet rating table


<a name="swmmoutf"></a>
## SWMMOUTF.DAT 

SWMMOUTF.DAT information goes into the following GeoPackage tables:

* swmmoutf - polygon layer of grid cells with SWMM drain outflows

**gpkg table: swmmoutf**

* "fid" INTEGER NOT NULL PRIMARY KEY,
* "grid_fid" INTEGER, -- OUTF_GRID, fid of the grid element with a storm drain outflow
* "name" TEXT, -- OUTF_NAME, name of the outflow
* "outf_flo" INTEGER -- OUTF_FLO2DVOL, switch, 0 for all discharge removed from strom drain system, 1 allows for the discharge to be returned to FLO-2D
* "geom" POLYGON -- grid element with storm drain outflow, on import: create the geometry as grid cell with fid = OUTF_GRID

