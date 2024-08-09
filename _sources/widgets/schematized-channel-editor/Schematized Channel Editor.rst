Schematized Channel Editor
==========================

This editor widget is used to edit the control data and tabular data of the schematized channels.
It works on any schematized channel data including, imported data, imported RAS data and digitized data.
This data is written to the CHAN.DAT and CHANBANK.DAT files.

Segment Control
---------------

Select a channel segment to load the control data.
The data is different for each channel segment.
Review the Channel Modeling Guidelines (FLO-2D 2018) to assign the parameters.
The sediment transport data will not be used unless the channel option is used in the SED.DAT file.

.. image:: ../../img/Schemetized-Channel-Editor/Scheme002.png

Initial Conditions
------------------

The global initial depth value can be set in the channel segment control data.
This is a single value that is assigned to every cell in the channel segment when the model starts.

.. image:: ../../img/Schemetized-Channel-Editor/Scheme003.png

Initial Water Surface Elevation
-------------------------------

The initial water surface elevation is used to set the variable initial conditions.
The values are assigned to the first and last element in a segment and interpolated to each cell in the channel at runtime.

.. image:: ../../img/Schemetized-Channel-Editor/Scheme004.png

Channel Geometry
----------------

The tabular channel data is edited in the Schematized Channel Geometry dialog box.
This data can be edited by loading any grid element into the editor box or by editing the table directly.
Copy paste options are active in the table editor.

.. image:: ../../img/Schemetized-Channel-Editor/Scheme005.png

Right Bank
----------

A right bank editor is available in the Schematic Chanel Segments dialog box.
Edit the columns directly and click close to apply.

.. image:: ../../img/Schemetized-Channel-Editor/Scheme006.png
