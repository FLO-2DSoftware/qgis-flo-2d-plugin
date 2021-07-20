Elevation Correction Tool
==========================

Overview
--------

This tool is used to correct elevation data for polygons, points or polylines.

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat002.png

The correction datasets are set up in the User Layers group.

-  Elevation Polygons

-  Elevation Points

-  Rasters

Users Layers Mode
-----------------

There are multiple options in this tool.
The following sections will show how to use each option in the Users Layers Mode tab.

Tin from Points and Polygon
---------------------------

1. The first option is to edit the elevation on the grid using elevation points that are contained within a polygon boundary.

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat003.png

2. The tool creates a triangulated irregular network (TIN) that is confined to the elevation polygon layer.
   The TIN elevation is read from the Elevation Points layer.
   The elevation is assigned to the grid from the TIN as a correction to the grid elevation.
   Only grids with a centroid inside the polygon are adjusted.
   In this example, a section of the dam is removed from the grid element elevation so the dam can be breached.
   Most of the dam is left in place so the volume displacement is still occurring.

**Note: The elevation image in this example is not the grid element.
It is a hillshade of the raw raster data.
The tool corrects the grid elevation only.**

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat004.png

3. Here is a before and after image of the calculation.  The tool removed the dam from the grid elevation.
   It interpolated the grid elevations based on the point and a TIN.

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat005.png

Tin from Polygon Boundary
-------------------------

1. The second option is to build a TIN from the grid element elevation surrounding a polygon.
   This will assess the elevation where the polygon intersects the grid and interpolate that elevation to the TIN.

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat006.png

2. This option is used when a Cut or Fill correction is required.
   For example, to fill a channel with elevation data along the bank, cover the channel with an elevation polygon and apply the correction.

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat007.png

Elevation Polygon Attributes
----------------------------

1. This option is used when a single known elevation correction is required.

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat008.png

2. In this example, the invert elevation at the headwall inlet is incorrect.
   The polygon has a new elevation assigned that will be applied directly to the grid layer.
   In this case the correction is applied to centroid of the cell and the selected polygon only.

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat009.png

Grid Statistics within Blocked Areas
------------------------------------

1. In this case, the correction is applied by analyzing the statistics of the elevations within the Blocked Areas Polygons.
   The mean, max or min elevation of the combined cell centroids within the polygon are applied as a general condition to all of the cells centroids
   within the polygon.

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat010.png

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat011.png

External Layer Tab
------------------

This section will review each option in the External Layers Mode tab:

Correction Options
------------------

There are several grid element correction options available in this tool.

-  Select any polygon layer.

-  Define the geometric predicate.
   Grid centroid or grid element.

-  Take the elevation from an attribute table.

-  Take the mean statistics from the elements within the polygons.

-  Use only selected features or all features.

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat012.png

Method 1 Elevation Correction Polygon Attribute
-----------------------------------------------

This method will apply a elevation to each grid element within the polygon from the elevation field of the polygon.

1. Load or create a polygon layer with an elevation and a correction field.
   In this example, the Elevation Polygon layer was used.
   It isn’t’ an external layer but it still works.

2. Click the Elevation Correction Tool and click Correct Grid Elevation

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat013.png

3. Set up the Correct Grid Dialog as shown below and click OK.

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat014.png

4. Click ok to complete the process.

5. The following figure shows the result of the processing.
   The polygon had an elevation attribute of 1400 and a correction attribute of 1401.

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat015.png

Method 2 Elevation Correction Raster within a Polygon
-----------------------------------------------------

This method will apply zonal statistics to a raster within a polygon to calculate the min, max or mean of an area.

1. Import an elevation raster and a create a polygon for the area that needs a correction.

2. Click the Elevation Correction Tool and click Correct Grid Elevation

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat013.png

3. Set up the Correct Grid Dialog as shown below and click OK.

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat016.png

4. Click ok to complete the process.

5. The following figure shows the result of the processing.
   The raster within the polygon had an elevation of 1409.44.
   This was applied to every cell within the polygon.

6. The figure below shows the change in elevation.

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat017.png

Method 3 Elevation Correction Raster within a Selection of Grid Elements
------------------------------------------------------------------------

This method will apply zonal statistics to a raster within individual grid elements to calculate the min, max or mean elevation.

1. Import an elevation raster.

2. Copy a group of grid elements to the Elevation Polygon Layer.

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat018.png

3. Click the Elevation Correction Tool and click Correct Grid Elevation

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat013.png

4. Set up the Correct Grid Dialog as shown below and click OK.

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat016.png

5. Click ok to complete the process.

6. The following figure shows the result of the processing.
   The raster within the polygon had an elevation of 1409.44.
   This was applied to every cell within the polygon.

7. The figure below shows the change in elevation.

.. image:: ../../img/Elevation-Correction-from-Polygons/Elevat017.png
