Storm Drain Editor
==================

The Storm Drain Editor tool has several functions to prepare the data that integrates the FLO-2D surface water model
with the storm drain model.  This document will explain the functionality of each button.

.. image:: ../../img/Storm-Drain/Storm002.png

.. note:: For a step-by-step tutorial, use the QGIS Workshop Lessons or the Self-Help training package.
          `Storm Drain Tutorial <https://documentation.flo-2d.com/Workshops/Lesson%203.html>`_

Storm Drain Editor
-------------------

1. The digitize storm drain buttons are inactive.
   It is recommended to create a storm drain network in separate storm drain shapefiles as discussed below.

2. The blue schematize button
   is used when the storm drain system is complete and ready to convert to the FLO-2D schema layers.

3. The simulate storm drain
   check box will turn on the storm drain switch in the Control Variables.

.. image:: ../../img/Storm-Drain/Storm003.png

Storm Drain Network
-------------------

The select component from shapefile feature is used to build a storm drain network from a set of shapefiles.
Some projects have a storm drain system already developed.
Some projects have no network and start from scratch.
Either way, this information will serve as a template for the data needed to create a storm drain system.

1. Load the shapefiles
   onto the map or digitize new shapefiles with QGIS.

.. image:: ../../img/Storm-Drain/Storm004.png

The shapefiles can be described as follow:

-  Lesson3InletsJunctions.shp is a point shapefile that contains the inlets nodes, manholes, and junctions.
-  Lesson3Outfalls.shp is a point shapefile that contains the outfalls.
-  Lesson3Conduits.shp is a line shapefile that contains the conduits system.
-  Lesson3Pumps.shp is a line shapefile that contains the pump system. (Not required)
-  Lesson3Orifices.shp is a line shapefile that contains the orifices system. (Not required)
-  Lesson3Weirs.shp is a line shapefile that contains the weirs system. (Not Required)

The following data must be available in the shapefile to create the storm drain data
files: SWMM.INP, SWMMFLO.DAT, SWMMOUTF.DAT and SWMMFLORT.DAT.

.. image:: ../../img/Storm-Drain/Storm005a.png

.. image:: ../../img/Storm-Drain/Storm005b.png

.. image:: ../../img/Storm-Drain/Storm005c.png

.. image:: ../../img/Storm-Drain/Storm005d.png

.. image:: ../../img/Storm-Drain/Storm005e.png

.. image:: ../../img/Storm-Drain/Storm005f.png

Inlets/Junctions Shapefile
--------------------------

This is a sample of the attributes table for the Inlet/Junctions shapefile.

.. image:: ../../img/Storm-Drain/Storm007.png

The fields from the attribute table are selected using the Select Components from Shapefile dialog box.

.. image:: ../../img/Storm-Drain/Storm008.png

.. image:: ../../img/Storm-Drain/Storm009.png

Outfall Shapefiles
------------------

This is a sample of the attributes table for the outfall shapefile.

.. image:: ../../img/Storm-Drain/Storm012.png

The fields from the attribute table are selected using the Select Components from Shapefile dialog box.

.. image:: ../../img/Storm-Drain/Storm008.png

.. image:: ../../img/Storm-Drain/Storm009a.png

Conduits Shapefiles
-------------------

This is a sample of the attributes table for the conduit shapefile.

.. image:: ../../img/Storm-Drain/Storm010.png

The fields from the attribute table are selected using the Select Components from Shapefile dialog box.

.. image:: ../../img/Storm-Drain/Storm008.png

.. image:: ../../img/Storm-Drain/Storm009b.png

Pumps Shapefiles
-------------------

This is a sample of the attributes table for the conduit shapefile.

.. image:: ../../img/Storm-Drain/Storm010a.png

The fields from the attribute table are selected using the Select Components from Shapefile dialog box.

.. image:: ../../img/Storm-Drain/Storm008.png

.. image:: ../../img/Storm-Drain/Storm009c.png

Orifices Shapefiles
-------------------

This is a sample of the attributes table for the conduit shapefile.

.. image:: ../../img/Storm-Drain/Storm010b.png

The fields from the attribute table are selected using the Select Components from Shapefile dialog box.

.. image:: ../../img/Storm-Drain/Storm008.png

.. image:: ../../img/Storm-Drain/Storm009d.png

Weirs Shapefiles
-------------------

This is a sample of the attributes table for the conduit shapefile.

.. image:: ../../img/Storm-Drain/Storm010c.png

The fields from the attribute table are selected using the Select Components from Shapefile dialog box.

.. image:: ../../img/Storm-Drain/Storm008.png

.. image:: ../../img/Storm-Drain/Storm009e.png


Import SWMM.inp
---------------

1. An existing SWMM.inp project can be imported in a FLO-2D Surface System.

2. Click on Import SWMM.inp and browse the project folder that contains the file.

.. image:: ../../img/Storm-Drain/Storm014.png

This button loads inlets/junctions, outfalls and conduits from an \*.INP file.
The Storm Drain data needs to be schematized; the table components that can be opened from the Storm Drain Editor will
contain the variables from the SWMM.inp file.

Additional data is needed for the SWMMFLO.DAT, SWMMOUTF.DAT and SWMMFLORT.DAT files.

QGIS FLO-2D layers will be filled up with the data from the following \*.INP groups:

-  Inlets/Junctions

-  Outfalls

-  Conduits

-  Cross sections

-  Losses

-  Coordinates (required coordinates only)

Export SWMM.inp
---------------

Export SWMM.inp file in a FLO-2D format prior to running.
The SWMM.INP can be created from shapefiles and then exported or it might be modified from an existing SWMM.INP.

.. image:: ../../img/Storm-Drain/Storm015.png

Data save in the Components tables is written to the .INP file using this function.

Components: Inlets/Junctions
----------------------------

.. important:: While it is possible to edit and correct attributes in the following dialog boxes, it is
          recommended to make editorial changes in the original shapefiles so that those files carry forward as the
          project evolves.  The process to recalculate the storm drain from the shapefiles is very fast and effective.

Edit components that already exist using the Components editors for Inlets/Junctions, Outfalls and Conduits.

.. image:: ../../img/Storm-Drain/Storm016.png

A dialog is shown with data for the selected component, in this case the Inlets/Junctions were selected, the user can edit the tables.

.. image:: ../../img/Storm-Drain/Storm017.png

Components: Outfalls
--------------------

Edit components that already exist using the Components editors for Inlets/Junctions, Outfalls and Conduits.

.. image:: ../../img/Storm-Drain/Storm018.png

A dialog is shown with data for the selected component, in this case the Outfalls were selected, the user can edit the tables.

.. image:: ../../img/Storm-Drain/Storm019.png

Components: Conduits
--------------------

Edit components that already exist using the Components editors for Inlets/Junctions, Outfalls and Conduits.

.. image:: ../../img/Storm-Drain/Storm020.png

A dialog is shown with data for the selected component, in this case the Outfalls were selected, the user can edit the tables.

.. image:: ../../img/Storm-Drain/Storm021.png

Components: Pumps
--------------------

Edit components that already exist using the Components editors for Inlets/Junctions, Outfalls and Conduits.

.. image:: ../../img/Storm-Drain/Storm020a.png

A dialog is shown with data for the selected component, in this case the Outfalls were selected, the user can edit the tables.

.. image:: ../../img/Storm-Drain/Storm021a.png

Components: Orifices
--------------------

Edit components that already exist using the Components editors for Inlets/Junctions, Outfalls and Conduits.

.. image:: ../../img/Storm-Drain/Storm020b.png

A dialog is shown with data for the selected component, in this case the Outfalls were selected, the user can edit the tables.

.. image:: ../../img/Storm-Drain/Storm021b.png

Components: Weirs
-----------------

Edit components that already exist using the Components editors for Inlets/Junctions, Outfalls and Conduits.

.. image:: ../../img/Storm-Drain/Storm020c.png

A dialog is shown with data for the selected component, in this case the Outfalls were selected, the user can edit the tables.

.. image:: ../../img/Storm-Drain/Storm021c.png

Auto-assign conduit nodes
-------------------------

This tool will automatically fill the node names required for the conduit connections.  Use this calculator individually
by clicking each option once.  If the option isn't used, i.e. weirs are not used, it is not necessary to click that option.

.. image:: ../../img/Storm-Drain/Storm022.png

Links are connected to the node they touch on the upstream and downstream end of each polyline by the name of the node.

.. image:: ../../img/Storm-Drain/Storm023.png

In a storm drain network there is a separate link feature between each node.
The auto-assign button finds the node in proximity of the end of each feature and assigns it to the table.
It is important to orient the conduit features so that the first vertex is near the inlet node and the last vertex is near the outlet node.
See the flow direction arrows in the following image.

.. image:: ../../img/Storm-Drain/Storm024.png

Rating Tables
-------------

Rating tables define the flow at a given depth.
They are used for headwalls.
There are two methods for building rating tables.
`Method 1 <#method-1.-create-with-the-flo-2d-plugin>`__ uses the Plugin to build the tables.
This method is good if only a few tables are required.
`Method 2 <#method-2.-import-multiple-tables>`__ imports tables from a text file.
This method is better if many tables are required.

Method 1. Create with the FLO-2D Plugin
----------------------------------------

1. Set up the rating
   tables with the Plugin by adding a rating table to the table editor and assigning the table to the correct inlet.

.. image:: ../../img/Storm-Drain/Storm025.png

2. Use the Inlet Editor to
   assign the table to the Type 4 inlet.

.. image:: ../../img/Storm-Drain/Storm026.png

Method 2. Import multiple tables
------------------------------------

1. Click the
   Import Rating Table… button.

.. image:: ../../img/Storm-Drain/Storm027.png

2. Select all of the rating
   tables that match the type 4 inlets.

3. The Plugin will load the tables
   based on the node name and automatically assign each table.

.. image:: ../../img/Storm-Drain/Storm028.png

4. Tables are space or tab delimited
   and are created using culvert equations or HY-8.

.. image:: ../../img/Storm-Drain/Storm029.png

External Inflow Data
--------------------

1. Set up the external inflow data for a storm drain node.

2. Use the Inlet/Junction editor to set up external inflow parameters and data.

.. image:: ../../img/Storm-Drain/Storm030.png

3. Use the Internal Inflow tools to define parameters and select time series data.

Simple parameters are used in this case.

-  Inflow constituent: water only (no pollutants)

-  Baseline flow: 0 cfs(cms)

-  Baseline pattern: hourly with no multiplier

-  Scale factor: none

-  Time series file: Example Project/QGIS Lesson 3/SDInflow.dat

.. image:: ../../img/Storm-Drain/Storm031.png
