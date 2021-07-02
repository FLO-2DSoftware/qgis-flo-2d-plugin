QGIS Tools
============

QGIS Settings
-------------

Setting up QGIS before starting a project. One startup setting makes
adding layers and importing files easier. Set up the coordinate reference system (CRS) of imported
layers. Click Settings/Options

.. image:: ../img/QGIS-General-Tools/qgisgeneraltools1.png


1. Set the Default CRS to the coordinate system that is most commonly used.
   Select the Use project CRS radio button. See the following image for an
   example.

.. image:: ../img/QGIS-General-Tools/qgisgeneraltools2.png


Save Project
-------------

.. image:: ../img/Buttons/savebutton.png


2. Click the Save Icon on the QGIS toolbar. Save the file to the project
   directory.

.. image:: ../img/QGIS-General-Tools/qgisgeneraltools4.png


Open a Project
--------------

.. image:: ../img/Buttons/openproject.png


1. Click the open icon on the QGIS toolbar. Navigate to the project
   folder, select the \*.qgs file and click Open.

.. image:: ../img/QGIS-General-Tools/qgisgeneraltools9.png


2. Click Yes
   to load the GeoPackage in the FLO-2D Plugin.

.. image:: ../img/QGIS-General-Tools/qgisgeneraltools6.png


Project Path Changes
--------------------

Path corrections may be required if the project folder was changed or moved to a new computer.
External data links can be correct using number 1 below and the geopackage links are automatically
corrected by the plugin as shown in number 3 below.

**Important Note:  If the ProjectName.gpkg file is still in the old path, it will be chosen
automatically.**

1. Fix the links
   with QGIS and the FLO-2D plugin with this process.

2. Fix the external data links with the Handle Unavailable Layers
   window. Auto find works well. Apply Changes to close the window.

.. image:: ../img/QGIS-General-Tools/qgisgeneraltools7.png


3. The Load Model window finds the GeoPackage and fixes the path. Click
   yes to load the model from the new path.

.. image:: ../img/QGIS-General-Tools/qgisgeneraltools8.png

