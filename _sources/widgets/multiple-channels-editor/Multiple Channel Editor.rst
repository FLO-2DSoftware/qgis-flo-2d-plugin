Multiple Channels Editor
========================

Multiple channel system is used to represent rill and gully flow in an effort make the time of concentration more effective
on a floodplain.

An overview of the tool is discussed below but see the tutorial for a more detailed description of how to set up the data
using QGIS.
https://documentation.flo-2d.com/Advanced-Lessons/Module%205%20Part%203.html

-The Build 22 Data Input Manual has detailed instructions on each variable.

-The Build 22 FLO-2D Reference Manual has specific information on how FLO-2D models rill and gully flow.

The manuals are installed on the computer along with
the Build 22 Update and can be found here:

C:\\Users\\Public\\Documents\\FLO-2D PRO Documentation\\flo_help\\Manuals

Global Data
------------
1. The multiple channel
   is used to set up the global parameters for the MULT.DAT and SIMPLE_MULT.DAT files.

.. image:: ../../img/Multiple-Channel-Editor/mutipl002.png

2. The data is saved to
   the multiple channel global parameters table.

.. image:: ../../img/Multiple-Channel-Editor/mutipl002a.png


Multiple Channel Lines
----------------------

The Multiple Channel Lines layer is used to set the path of the multiple channels.
This layer is in the User Layers group.

1. Highlight the Multiple Channel Lines layer and click the QGIS vector
   polyline editor pencil in the toolbar.

.. image:: ../../img/Multiple-Channel-Editor/mutipl003.png


2. Use polylines to digitize the drainages,
   rills or gullies in the project area.

.. image:: ../../img/Multiple-Channel-Editor/mutipl009.png


3. Assign the width, depth,
   channel connection, and n-value variable attributes to each line.

.. image:: ../../img/Multiple-Channel-Editor/mutipl005.png
 

4. Save and close the editor to commit the data to the geopackage using a sql trigger.
   This will automatically write the data to the Multiple Tables and assign the grid elements.

.. image:: ../../img/Multiple-Channel-Editor/mutipl004.png


5. Any edits to the polyline will result in an update to the table data.

Simple Multiple Channel Lines
------------------------------

The Simple Multiple Channel Lines layer is used to set the path of the multiple channels that only require a single attribute.
This layer is also in the User Layers group.

1. Highlight the Simple Mult. Channel Lines layer and click the QGIS vector
   polyline editor pencil in the toolbar.

.. image:: ../../img/Multiple-Channel-Editor/mutipl010.png


2. Use polylines to digitize the drainages,
   rills or gullies in the project area.

.. image:: ../../img/Multiple-Channel-Editor/mutipl011.png


3. This layer uses a global n-value attribute only so no spatial data is required for individual lines.

.. image:: ../../img/Multiple-Channel-Editor/mutipl012.png


4. Save and close the editor to commit the data to the geopackage using a sql trigger.
   This will automatically write the data to the Multiple Tables and assign the grid elements.

.. image:: ../../img/Multiple-Channel-Editor/mutipl013.png


5. Any edits to the polyline will result in an update to the table data.

Multiple Channel Areas
----------------------

This layer is activated when data is imported into the geopackage from an existing MULTCHAN.DAT file.  It is not used
for editorial purposes.

.. image:: ../../img/Multiple-Channel-Editor/mutipl014.png

Export MULT.DAT Files
----------------------

1. To export the MULT.DAT file,
   check the Multiple Channel checkbox and click save.


.. image:: ../../img/Multiple-Channel-Editor/mutipl008.png

2. The MULT.DAT file will be
   written the next time the project data is exported.

.. image:: ../../img/Multiple-Channel-Editor/mutipl015.png


.. image:: ../../img/Multiple-Channel-Editor/mutipl016.png

3. The data files are MULT.DAT and SIMPLE_MULT.DAT and can be reviewed in the Data Input Manual Build 22.

.. image:: ../../img/Multiple-Channel-Editor/mutipl017.png
