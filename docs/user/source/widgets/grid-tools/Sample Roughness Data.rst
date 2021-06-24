Sample Roughness Data
=====================

Overview
--------

In this task, the spatially variable manning’s roughness is calculated from a polygon shapefile.
The polygons represent roughness associated with different LandUse categories such as building, street, grass, desert brush and many others.

.. image:: ../../img/Sample-Roughness-Data/sample002.png

The plugin has 4 methods for calculating roughness.
Use the Sampling Manning’s tool to access the calculator.

1. Click the *Sample Manning’s icon*
   from polygon layers.

.. image:: ../../img/Sample-Roughness-Data/sample003.png

This layer requires a polygon shapefile with roughness data or digitized data assigned to the *Roughness User Layer*.
The tool will calculate Manning’s roughness values with three different processes.

Roughness Polygon Intersection
------------------------------

2. To calculate a weighted average of manning’s polygons
   to grid element polygons, use the Source Layer and Intersect cell rectangle option.

.. image:: ../../img/Sample-Roughness-Data/sample004.png

Roughness Point Sample
----------------------

3. To calculate a point sample from the centroid
   of the grid element on the manning’s polygons, use the Source Layer and Intersect cell centroid option.

.. image:: ../../img/Sample-Roughness-Data/sample005.png

Roughness Update
----------------

4. To calculate a point sample from the centroid of the grid element on the manning’s polygons, use the Source Layer and Intersect cell centroid option.
   This option will only update cells whose centroid lies within the Roughness Layer polygons and leave all other values as is.

.. image:: ../../img/Sample-Roughness-Data/sample006.png

5. Once the sample is complete, the following window will appear.
   Click *OK* to close the window.

.. image:: ../../img/Sample-Roughness-Data/sample007.png

The roughness values are assigned to the *Grid* layer in *the Schematized Layers* group.

.. image:: ../../img/Sample-Roughness-Data/sample008.png

6. If it is necessary to update or change a
   small selection of elements, use the *Roughness* layer in the *User Layers* group.

.. image:: ../../img/Sample-Roughness-Data/sample009.png

Troubleshooting

1. The Roughness layer must be a polygon layer.
   It is usually a shapefile.

2. The layer
   CRS must match the project CRS.

3. The polygon geometry must be valid to process the intersection area average.
   Try Check Geometries if the calculation fails.

4. If a Python error appears during the sampling process, it may indicate that attribute table is missing.
   Save and reload the project into QGIS and try again.
