Floodplain Cross Section Editor
================================

The floodplain cross section editor is used to set up the FPXSEC.DAT file.
This section will describe how to digitize and schematize the data.

Use the editor widget to create the cross section.

.. image:: ../../img/Floodplain-Cross-Section-Editor/floodp005.png

1. Click the
   floodplain cross section button.

.. image:: ../../img/Floodplain-Cross-Section-Editor/floodp004.png

2. Digitize the cross section and fill the dialog box.
   Click OK.

.. image:: ../../img/Floodplain-Cross-Section-Editor/floodp002.png


3. Click save to preserve the data. The user cross section is
   a green line.

.. image:: ../../img/Floodplain-Cross-Section-Editor/floodp006.png

4. Check the editor
   and make any adjustments necessary.

.. image:: ../../img/Floodplain-Cross-Section-Editor/floodp009.png

.. image:: ../../img/Floodplain-Cross-Section-Editor/floodp008.png

5. Click Schematize to save the data.
   The schematized cross section is corrected to meet the FLO-2D criteria for Floodplain cross sections.

.. image:: ../../img/Floodplain-Cross-Section-Editor/floodp007.png

.. image:: ../../img/Floodplain-Cross-Section-Editor/floodp003.png

Troubleshooting
---------------

1. Make sure the
   cross-section lines are within the grid system.

2. If copying cross
   section data into the layer, make sure the FID is numbered 1 to n number of cross sections.

3. Make sure the iflo is
   assigned to a number 1 – 8 that is a flow direction most perpendicular to the polyline.

4. Try to make the lines horizontal, vertical or diagonal to the grid elements.
   If the line is not very close to the grid alignment, the intersector may have trouble finding the correct alignment.

5. Use the Velocity Vectors from Mapper or Crayfish to help set up the line.
   Place the lines in a location where all flow crosses the line.
   Do not place the line where flow is parallel to the line.



