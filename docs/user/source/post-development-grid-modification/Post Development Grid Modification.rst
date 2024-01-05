Post Development Grid Modification
==================================

This section outlines a process to port data after the domain has been changed or the grid elements size has been changed.

.. note:: The process will be outlined based on the available layers and procedures in the QGIS FLO-2D Plugin order.
          If the user data does not have a section below, skip that bullet.

1. Computational Domain Layer
------------------------------

-  Update polygon to cover complete project extent.

-  Set cell size.

2. Grid
--------

-  Create the grid.

3. Interpolate Elevation
---------------------------

-  Import full coverage raster.

   -  If a new area is needed, it is easy to create a mosaic of the two rasters.

   -  Export the grid layer as a raster and use a mosaic tool to combine the two rasters.

   -  It is a good idea to use the new grid element resolution and alignment as the extent and size for the raster.

-  Sample full coverage raster with the Sampling grid elevation from raster layer.

4. Roughness
--------------

-  Recalculate from a full coverage shapefile/raster.

-  If shapefile is not available,

   -  Export the old grid and intersect it with roughness polygons for the new grid.

   -  Use a Dissolve tool to simplify the shapefile so it combines like polygons with the same n-value.

5. Buildings
-------------

-  Recalculate from Blocked Areas layer.

-  It may be necessary to add buildings from additional area.

6. Extra Grid features
-----------------------

-  Run separate tools for Spatial Tol, Spatial Froude, Spatial Shallow n, and Gutters.

7. Infiltration
-----------------

-  Recalculate from external layers.

-  It may be necessary to add infiltration areas to the infiltration shapefile.

   -  If extra data is needed, intersect the new data into the Soil and Landuse shapefiles.

8. Hydraulic Structures
-------------------------

-  Copy polyline features from Structures Schematic Layer.

-  Paste into Structures User Layer.

-  Run structures schematize tool to refresh data.

-  Add new structures using the editor tool and table editor after refreshing the data.

-  Rerun schematize tool to add new data to final Schematic Layer.

9. Levees
----------

-  If User Layers Levee Lines are available, use them to recalculate the levees.

-  If Levee Lines User Layer is not present, use this simple process to copy them from the Schematized Levees.

   -  Create levee lines the center of the levee.
      This is just the standard create levee polyline using the editor add polyline process.

   -  Make certain these lines cross the Schematic Levees frequently.

   -  Intersect the Levee Lines Layer and Levees Layer to generate a point file with crest elevation.

   -  Copy that to the Elevation Points Layer.

   -  Run the Levee Calc tool with Levee Lines and Points.

   -  The idea is to intersect the schema lines and get the crest elevation for the points layer.

   .. note:: This does not work for walls.

-  Walls

   -  Recalculate walls from wall data.

10. Boundary Conditions
-----------------------

-  Run schematize button.

-  The downstream boundary might need to be edited or repositioned.

11. Rain
--------

-  Rerun depth Area Reduction sampler if used.

-  Save and export data.

12. Channels
-------------

-  Rerun schematize.

-  Export .DAT files.

-  Run Interpolator.

-  Import interpolated channels.

-  It may be necessary to make left and right bank alignment corrections.

13. Floodplain cross sections
------------------------------

-  Rerun schematize.

-  It may be necessary to add new cross sections.

Storm Drain
------------

-  Add new data to the storm drain shapefiles.

-  Rerun storm drain calculator tool to convert to the FLO-2D User layers.

-  Run schematize.

-  Export swmm.inp.

FLO-2D Pro
-----------

-  Export Data

-  Run Model

   -  It is probably wise to export the data and test run at more convenient points along this outline.
