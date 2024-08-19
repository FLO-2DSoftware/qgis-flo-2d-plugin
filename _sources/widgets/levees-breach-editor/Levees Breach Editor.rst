Levees Breach Editor
====================

Breach Prescribed
-----------------

This tool will define a single breach location.
If walls are being designed, use the Levee and Wall method not this method.

1. Use the
   Grid ID tool to pick the levee element to assign a prescribed breach to.

.. image:: ../../img/Levee-Breach/Levees002.png

.. image:: ../../img/Levee-Breach/Levees003.png

2. From the
   Levees and Breach Editor, click Prescribed Failure radio button and then click the Levee Grid Elements button.

.. image:: ../../img/Levee-Breach/Levees004.png

The process to apply levee prescribed breach:

3. Add the grid element number of the levee that will initiate the failure.
   Press the eye button.
   (Green)

4. Place the cursor into the levee elevation combo.
   (Orange)

5. Check the Failure check box.
   (Purple)

6. Fill the failure criteria.
   See Data Input Manual for variables use.
   (Blue)

7. Click Apply Change.
   (Red)

8. Close the
   dialog box after clicking Apply.

.. image:: ../../img/Levee-Breach/Levees005.png

Breach Erosion
--------------

FLO-2D has embedded the Fread BREACH earthen dam breach and erosion model.

Fread, D.
(1988).
BREACH: An erosion model for earthen dam failures.

1. To create Breach Erosion data for this tool, set the Failure Mode to Breach Failure.
   This action will activate the Breach widget.

.. image:: ../../img/Levee-Breach/Levees006.png

2. The General breach data is set in the Breach Widget.
   Fill the boxes below.

.. image:: ../../img/Levee-Breach/Levees007.png

3. Use the Point button to create a Dam Breach Node.
   Click the button and then click the breach location on the map.

.. image:: ../../img/Levee-Breach/Levees008.png

It is important to apply the breach to the reservoir side of the levee.
Do not apply a breach point on the downstream side of the levee.
In this case, the breach starts in the North direction because the Point is closest to that levee.

4. Click
   this location.

.. image:: ../../img/Levee-Breach/Levees009.png

.. image:: ../../img/Levee-Breach/Levees010.png

5. Click OK to close the Dialog box.
   It is not necessary to fill the data here.

.. image:: ../../img/Levee-Breach/Levees011.png

6. Click the Save button on the Breach Widget activate the breach editor.
   Click the Individual Breach Data Button to fill the dam and breach data into the dialog box.

.. image:: ../../img/Levee-Breach/Levees012.png

This dialog box is used to define the followoing data.
For more information see the Data Input Manual and the Erosion Breach Tutorial.

-  Dam geometry

-  Geotechnical soil data

-  Breach methodology data

7. Fill the
   box and click Save.

.. image:: ../../img/Levee-Breach/Levees013.png

8. Export the
   data and check the BREACH.DAT and LEVEE.DAT data files.

.. image:: ../../img/Levee-Breach/Levees014.png

LEVEE.DAT should include the Breach Erosion Switch.

.. image:: ../../img/Levee-Breach/Levees015.png

BREACH.DAT should have only the B lines and D lines for general and individual breach data.

.. image:: ../../img/Levee-Breach/Levees016.png

Important notes for Dam Breach Modeling.

1. The cell elevation should be reset to the base floodplain elevation for any cell that represents the breach flow path.
   See the Elevation Correction section for more details.

2. The breach node should be assigned to a node with a levee and the breach direction should be set so that the breach occurs in the downstream
   direction.

3. It is also
   important to choose a flow direction that contains a levee cutoff.

4. The levee crest elevation is used as the dam crest elevation.
   The base elevation is set by the levee cells where the breach occurs.
