Sample Elevation from Points and LiDAR
=======================================


Load Elevation Points
----------------------

.. image:: ../../img/Buttons/addlayer.png

1. Click on Layer>\ Add Layers >\ Add Delimited Text Layer or click on the Open Data Source Manager button and navigate to the Delimited Text tab.
   Add the delimited text data, following the figure below.

2. There are many options to help sort the data.
   Select the options that reflect the desired dataset and click add.

.. image:: ../../img/Sample-Elevation-From-Points/Sample002.png

Apply a Style
-------------

The data has a default style so it isn’t very easy to view elevation.

1. Adjust the Style properties of the elevation data to assist the quality control measures for reviewing the data.
   For example, elevation data that has a large range can wash out the detail in local areas of the project area.

2. Double
   click the layer to open the Properties window and select the style tab to perform the following.

3. Assign
   graduated colors;

4. Select field
   to represent colors;

5. Select
   color ramp;

6. Classify the data
   (classifying the data adjustments will assist in locating erroneous data).

.. image:: ../../img/Sample-Elevation-From-Points/Sample003.png

7. The point data style
   is a graduated color scheme set to the elevation scale (see the figure below).

.. image:: ../../img/Sample-Elevation-From-Points/Sample004.png

Sample Data
-----------

1. Click the Assign Elevation
   to Grid button to interpolate the elevation data to the grid.

.. image:: ../../img/Sample-Elevation-From-Points/Sample005.png

2. The sampling dialog box
   appears to select the point source, elevation field, and calculation type.

3. Choose a max search distance to extend the search for empty grid elements.
   The distance is in the native map units.

4. This field can be
   assigned a zero value to default to the minimum search distance.

.. image:: ../../img/Sample-Elevation-From-Points/Sample006.png


5. Once the calculation is complete, the following dialog is displayed.
   Click OK to continue.

.. image:: ../../img/Sample-Elevation-From-Points/Sample008.png

6. The elevation
   data is saved to the Grid Layer in the Schematic Layers group.

.. image:: ../../img/Sample-Elevation-From-Points/Sample009.png

LiDAR Data
----------

The LiDAR method can interpolate data from multiple files.
It applies a simple average to the point within a cell and can patch missing LiDAR elevation from areas that are filtered from the ground data
category.

1. Click the
   Assign Elevation to Grid button to interpolate the elevation data to the grid.

.. image:: ../../img/Sample-Elevation-From-Points/Sample005.png

2. Choose the Interpolate from LiDAR files option and click OK.

.. image:: ../../img/Sample-Elevation-From-Points/Sample014.png

3. These files are created from LasTools using the LiDAR *.LAS
   files and the position is identified by a tiles shapefile.  Each filename has a
   distinct tile associated with it.  The LiDAR xyz file must have a *.txt extension.

4. Select the files and click Open.

.. image:: ../../img/Sample-Elevation-From-Points/Sample010.png

5. When the file is processing,
   two progress bars can be seen in QGIS.

.. image:: ../../img/Sample-Elevation-From-Points/Sample011.png

6. Once the processing is complete
   a dialog box appears with information about the processing points and time.
   Click OK to close this window.

.. image:: ../../img/Sample-Elevation-From-Points/Sample016.png

7. LiDAR data is bare earth data
   so categories such as buildings, bridges, overpasses are removed from the point data.

.. image:: ../../img/Sample-Elevation-From-Points/Sample012.png

8. The plugin will color the grid layers so that elevation data can be identified and allow
   the user to fill this data with a nearest neighbor patch or assign a value to
   non-interpolated cells.
   Select the first option and click ok to fill the missing data and click OK.

.. image:: ../../img/Sample-Elevation-From-Points/Sample013.png

9. This system may cycle a few times until all cells are filled.
   Once the cells are filled, it is OK to cancel the dialog box.

10. The final results
    should be a grid with all elevation data complete.

.. image:: ../../img/Sample-Elevation-From-Points/Sample017.png

Troubleshooting
---------------

1. If the elevation data is not visible, check the CRS.
   It may be necessary to transform the data into the correct CRS.

2. If the elevation layer does not show up in the Sample Elevation Dialog box, make sure it is a point layer and that
   it is checked on in the Layers List.

3. If a Python error appears during the sampling, it may indicate that there is no attribute table.
   Save and reload the project into QGIS and try again.
