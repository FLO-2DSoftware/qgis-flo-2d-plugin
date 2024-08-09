Street Editor
=============

The street editor is used to define street data on low resolution urban areas.
This data is written to the STREET.DAT file.
It is used when the grid element size is larger than the width of curb and gutter streets.
This tool works best for streets that collect and distribute water over the grid system.
The street should be able to convey water like a small channel.

.. image:: ../../img/Street-Editor/street002.jpeg

1Source: iStock

Build a street
--------------

Identify a street that meets the criteria
-----------------------------------------

1. Setup a FLO-2D project
   map with easy to identify roads, an elevation raster and a grid layer view.

2. Identify a street that is larger than the grid element size.
   The Santa Paula freeway lanes meet the grid element size criteria.

.. image:: ../../img/Street-Editor/street003.png


3. Determine if the street can convey water.
   The Santa Paula freeway has a well-defined curb and gutter on the outside lane.

.. image:: ../../img/Street-Editor/street004.png


4. Determine the flow direction.
   The Santa Paula freeway has a well-defined slope leading up to the overpass with no storm drain features to divert water off the road.
   This information was collected from creating a profile of the raster along the street and reviewing the Google Maps Street View tool via a web browser.
   The water will flow toward the point where the two arrows meet.
   Then it will overtop the channel onto the floodplain.

.. image:: ../../img/Street-Editor/street005.png


.. image:: ../../img/Street-Editor/street006.png


1. Define the street width, curb height and n-value.
   This street is 13 ft wide from the curb to the crown.
   There is only a gutter on one side so the other side will not convey water.

2. The n-value is 0.020
   and the curb height is 0.67 ft and the limiting Froude number is 1.25 because the street has a steep slope.

.. image:: ../../img/Street-Editor/street007.png
   

3. Click the Global
   Parameters button.

.. image:: ../../img/Street-Editor/street008.png


4. Fill the form and
   click Save.

.. image:: ../../img/Street-Editor/street009.png


Digitize a street segment.
--------------------------

The streets are a collection of cells that share water as a small rectangular channel.
Each segment should represent a single street with an ability to distribute water from one end to the other.
Any place where the street can no longer route water should be eliminated.

1. Click the Add
   a Street Line button.

.. image:: ../../img/Street-Editor/street012.png

2. Digitize
   the street segment on the map.

3. Enter
   the street data and click OK.

.. image:: ../../img/Street-Editor/street010.png

4. Save
   the street segment.

.. image:: ../../img/Street-Editor/street013.png

5. Repeat
   the process for the East Bound Lane.

.. image:: ../../img/Street-Editor/street014.png

6. Click the Schematize Button.
   The streets are schematized.
   Click ok to close the dialog box.

.. image:: ../../img/Street-Editor/street011.png

Troubleshooting

1. The street
   alignment can be adjusted by editing the street line in the user layers.

2. If the data is not written to the STREET.DAT file correctly.
   Check the schematic layer, it can be edited in the schematic layer attribute table.

3. Street intersections do not typically convey water.
   The street crown is designed to keep water out of the intersection.
   Set up intersections by stopping the connecting streets on cell back from the intersection.


