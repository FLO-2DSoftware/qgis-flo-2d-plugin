Levee Elevation Tool
=====================

.. image:: ../img/Buttons/Leveetool.png
 
The *Levee Elevation* Tool will create levees, berms, walls and dams. It
uses data from 5 sources:

.. image:: ../img/Levee-Tool/leveetool2.png


The method to create data from each source is outlined below.

Create Levee Lines
------------------

1. Start by creating a Levee Line any place where a levee should be
   positioned.

2. Select the Levee Lines layer in User Layers and toggle the Edit
   Pencil.

3. Click the Create Line Feature button and add a polyline to the center
   crest of the levee.

4. Right
   click anywhere after the last vertex to close the line.

5. Assign a levee crest elevation for a
   uniform levee.

6. If a correction is used, it will be added to the elevation field. It
   is not needed.

7. Failure data is not
   needed at this time.

.. image:: ../img/Levee-Tool/leveetool3.png
 

.. image:: ../img/Levee-Tool/leveetool9.png


Create a Levee Polygon
----------------------

1. Digitize a polygon feature in the
   Elevation Polygons layer.

2. Select the Elevation Polygons layer
   and click the Toggle Editing
   pencil.

3. Create a polygon
   and assign the levee crest elevation.

4. The levee line feature must also be present for the levee position to
   be applied.

5. See
   `Create Levee Lines <#create-levee-lines>`__.

.. image:: ../img/Levee-Tool/leveetool10.png


.. image:: ../img/Levee-Tool/leveetool11.png

Create Levee Points
-------------------

1. Digitize points
   feature in the Elevation Points layer.

2. Select the Elevation Points layer and click the Toggle Editing
   pencil.

3. Create a series of points and assign the levee crest elevation. Turn
   on snapping so the points will snap to the levee line.

4. The levee line feature must also be present for the levee position to
   be applied. See the instructions above.

5. In this example, a correction was applied to a location where a
   spillway was designed.

.. image:: ../img/Levee-Tool/leveetool12.png
 

.. image:: ../img/Levee-Tool/leveetool13.png
  

Levee from Elevation Polygon
----------------------------

.. image:: ../img/Buttons/Leveetool.png


The polygon layer is also used to define a uniform elevation for a
levee.

1. Click the
   *Levee Elevation Tool* icon.

2. Select *User elevation polygons* and click *Create Schematic Layers
   from User Levees*.

3. The Plugin will build the levee into a schematic layer, set the
   elevation data for the crest and apply a correction if used.

4. The data can be
   reviewed in the attribute table of the levee layer.

5. The Levee user lines will be used to set crest elevations where
   polygons are not covering the levee.

.. image:: ../img/Levee-Tool/leveetool15.png


.. image:: ../img/Levee-Tool/leveetool16.png
 

*Levee from Elevation Points within Search Radius*


.. image:: ../img/Buttons/Leveetool.png


1. Click the Levee Elevation Tool icon and select User elevation points
   within search radius and click OK.

2. The plugin will schematize the Levee Lines layer, set the elevation
   data for the crest and apply a correction if used.

3. The levee crest
   elevation is interpolated between the two points.

4. If the Levee user lines is also checked, that layer will be used to
   set crest elevations where points are not connected to the levee.

.. image:: ../img/Levee-Tool/leveetool17.png


.. image:: ../img/Levee-Tool/leveetool16.png


Levee from Levee User Lines
---------------------------

.. image:: ../img/Buttons/Leveetool.png


1. Click the Levee Elevation Tool icon and select User elevation points
   within search radius and click OK.

2. The plugin will schematize the Levee Lines layer, set the elevation
   data for the crest and apply a correction if used.

3. The levee crest
   elevation is interpolated between the two points.

.. image:: ../img/Levee-Tool/leveetool18.png


Levee from Import External 3D Levee Lines
-----------------------------------------

.. image:: ../img/Buttons/Leveetool.png


1. The levee data comes from an external point text file with a \*.xyz
   extension:

-  Xcoord –x coordinate of the center of the levee crest

-  Ycoord – y coordinate of the center of the levee crest

-  Z – crest elevation of the levee

2. The levee points should be in order from one side of the levee to the
   other. The direction is not important. Two levees should be separated
   by a blank line (text file carriage return).

.. image:: ../img/Levee-Tool/leveetool19.png


3. Call the levee data from the Levee Elevation Tool by clicking the “…”
   button under Import external 3D lines.

.. image:: ../img/Levee-Tool/leveetool20.png


4. Once the data is
   identified, click the Import 3D levee lines button.

5. The imported levees are written to the elevation points and Levee
   Lines User Layer. Click Create Schematic Layers from User Layers to
   schematize the levee.

.. image:: ../img/Levee-Tool/leveetool21.png

