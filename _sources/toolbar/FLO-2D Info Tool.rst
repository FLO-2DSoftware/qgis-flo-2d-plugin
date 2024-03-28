FLO-2D Info Tool
================

Use the Info Tool to identify data in the User Layers and Schematic Layers.
The layers must be active and checked on in the Layers panel.
This tool also activates the Profile Tool widget.

.. image:: ../img/Flo-2D-Info-Tool/Flo002.png

Layers that work with this tool:

-  Channel layers

-  Left bank

-  Cross sections

-  Structure layers

-  Levee layers

Load the Data
-------------

1. Start by loading the channel
   surface elevation and peak discharge from the HYCHAN.OUT file.

.. image:: ../img/Flo-2D-Info-Tool/Flo005.png

2. Select the
   HYCHAN.OUT file and click Open.

.. image:: ../img/Flo-2D-Info-Tool/Flo008.png

3. Make sure the Elevation raster
   is in the Layers group.  If it is missing, drag Elevation.tif onto the map from QGIS Lesson 1 folder.

Channel Profiles
----------------

1. Click  
   the FLO-2D Info Tool.

.. image:: ../img/Flo-2D-Info-Tool/Flo002.png

2. Click
   any left bank line.

.. image:: ../img/Flo-2D-Info-Tool/Flo009.png

3. The data will  
   load into the Profile Tool widget and the FLO-2D Plot panel.

.. image:: ../img/Flo-2D-Info-Tool/Flo010.png

4. Use the  
   Profile Tool widget to select the data plot source.

5. In this example, the  
   elevation raster is the y axis and the left bank length is the x axis.

.. image:: ../img/Flo-2D-Info-Tool/Flo003.png

6. Change the profile
   source from Raster to Schematic Layer and choose the max_water_elev field.

7. In this example,
   the water surface elevation is the y axis and the left bank length is the x axis.

.. image:: ../img/Flo-2D-Info-Tool/Flo004.png

8. Change the profile source to peak_discharge.  In this case, the y axis is peak discharge and the x
   axis left bank length.

.. image:: ../img/Flo-2D-Info-Tool/Flo011.png

Channel User Layer Cross Sections
--------------------------------------

The FLO-2D info tool can be used to activate a specific user cross section.

1. Click the FLO-2D
   Info tool.

.. image:: ../img/Flo-2D-Info-Tool/Flo002.png

2. Click and select
   a User Layer cross section.

.. image:: ../img/Flo-2D-Info-Tool/Flo014.png

3. This cross  
   section is loaded into the Cross Section Editor widget.

.. image:: ../img/Flo-2D-Info-Tool/Flo015.png

4. This cross
   section is also loaded into the FLO-2D Plot panel.

.. image:: ../img/Flo-2D-Info-Tool/Flo016.png

Channel Schematic Layer Cross Sections
--------------------------------------

The FLO-2D Info Tool can be used to review schematized cross sections.

1. Click the FLO-2D
   Info tool.

.. image:: ../img/Flo-2D-Info-Tool/Flo002.png

2. Click and
   select a Schematic Layer cross section.

.. image:: ../img/Flo-2D-Info-Tool/Flo012.png

3. This cross  
   section data is loaded into a dialog box.

.. image:: ../img/Flo-2D-Info-Tool/Flo013.png

Structure Layers
----------------

The FLO-2D info tool can be used to load and activate hydraulic structures.

1. Click
   the FLO-2D Info tool.

.. image:: ../img/Flo-2D-Info-Tool/Flo002.png

2. Click and
   select a structure line.

3. This line is loaded
   into its editor and plotted.

.. image:: ../img/Flo-2D-Info-Tool/Flo006.png

Levee Layers
------------

Levee Lines
The FLO-2D info tool can be used to load the raster and levee schematized data profile of the levee lines.

1. Click
   the FLO-2D Info tool.

.. image:: ../img/Flo-2D-Info-Tool/Flo002.png

2. Click
   and select a Levee Line.

3. This line
   is loaded into the Profile Tool widget and plotted.

4. In this
   case, the elevation raster is plotted.

.. image:: ../img/Flo-2D-Info-Tool/Flo017.png

5. In the
   schematized profile case, the levcrest field is plotted.

.. image:: ../img/Flo-2D-Info-Tool/Flo018.png

