FPXSEC.DAT
==========

FPXSEC.DAT information goes into the following GeoPackage tables:

* cont - model control table
* fpxsec - floodplain xsections
* fpxsec_cells - grid cells of each floodplain xsection

.. figure:: img/fpxsec.png
   :align: center

:download:`FPXSEC.DAT tables schema <img/fpxsec.png>`

**gpkg table: cont** (model control table)

* add the "NXPRT" parameter: 1 for cross section summary information reported in the BASE.OUT, 0 for not reporting

**gpkg table: fpxsec** (floodplain xsections)

* "fid" INTEGER NOT NULL PRIMARY KEY,
* "iflo" INTEGER, -- IFLO, general direction that the flow is expected to cross the floodplain cross section
* "nnxsec" INTEGER -- NNXSEC, number of floodplain elements in a given cross section
* "geom" LINESTRING, -- geometry of a fpxsection, on import: create the geometry as a linestring connecting cells centroids of each xsection.

**gpkg table: fpxsec_cells** (grid cells of each floodplain xsection)

* "fid" INTEGER NOT NULL PRIMARY KEY,
* "fpxsec_fid" INTEGER, -- fid of a floodplain xsection from fpxsec table
* "grid_fid" INTEGER -- NODX, fid of grid cell contained in a fpxsection

