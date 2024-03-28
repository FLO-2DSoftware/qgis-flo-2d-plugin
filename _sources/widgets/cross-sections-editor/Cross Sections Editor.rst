Cross Sections Editor
======================

This section will cover many of the tools available to develop channels for FLO-2D.
This is not a step-by-step procedure.
It is a compilation and detailed outline of the tools available and how to use them.
For step-by-step instructions, see the workshop lessons.

Channels
--------

Identify the Channel
---------------------

The elevation raster style can be edited so that the channel is well defined.
Adjust the min / max view setting to enhance the channel depth.

.. image:: ../../img/User-Cross-Sections-Widget/User002.png


Left Bank
----------

1. Select the  
   Left Bank Line layer.

2. Click on both the start  
   editing button and the add feature button.

3. Create a polyline to  
   represent the left bank looking downstream and click to save the layer.

4. It is important to  
   create the segments from order upstream to downstream.

5. Tributaries or  
   split channels should be created once the main channels are complete.

.. image:: ../../img/User-Cross-Sections-Widget/User003.png

.. image:: ../../img/User-Cross-Sections-Widget/User004.png


6. Repeat the process  
   for the all the various channel segments and save.

.. image:: ../../img/User-Cross-Sections-Widget/User005.png
   

Right Bank
------------

1. Select the  
   Right Bank Line layer.

2. Click on both the start  
   editing button and the add feature button.

3. Create a polyline to  
   represent the right bank looking downstream and click to save the layer.

4. It is important to  
   create the segments from order upstream to downstream.

5. Tributaries or split  
   channels should be created once the main channels are complete.

.. image:: ../../img/User-Cross-Sections-Widget/User003.png
   

.. image:: ../../img/User-Cross-Sections-Widget/User006.png


6. Repeat the process for  
   the all the various channel segments and save.

.. image:: ../../img/User-Cross-Sections-Widget/User007.png


Natural Cross Sections
----------------------

To create natural cross sections, the cross sections should be numbered consecutively from upstream to downstream for each channel segment.

1. Click the Add Cross
   sections lines button.

2. Digitize the cross  
   section on the map.

3. Name the cross section and  
   click OK to finish the feature.

4. Click save to complete  
   the process and load the data into the widget.

.. image:: ../../img/User-Cross-Sections-Widget/User008.png
  

.. image:: ../../img/User-Cross-Sections-Widget/User009.png

The cross sections shown in the following image have been digitized.

**Important Notes:**

-  **Draw polylines from left bank to right bank looking downstream.**

-  **The first cross section must cross the left and right bank and be inside the same grid elements.**

-  **The subsequent cross sections can cross the left and right bank and be wider than the channel.**

-  **Place-holder data is added to the cross section station elevation data.
   It is replaced after all cross sections are ready.**

The finished product will look something like the following image.

.. image:: ../../img/User-Cross-Sections-Widget/User010.png


Cross Section Bank and Station Elevation Tool
------------------------------------------------

The preferred and easiest way to sample elevation data for a cross section is by using the FLO-2D Sample Elevation tool.
Once the cross sections are digitized onto the map, the Sample Elevation tools are used to sample elevation data from a raster into Stations/Elevation
data sets for all or individual cross sections.

This section will focus on N type or natural channel geometry.

1. Set the elevation raster as  
   the Source Raster Layer and use either button to sample one or all cross sections.

.. image:: ../../img/User-Cross-Sections-Widget/User011.png


2. The station elevation data is  
   limited to the point where the left and right bank intersect the cross section.

3. If too much or too little data  
   has been sampled, adjust the left or right bank alignment and sample the elevation again.

.. image:: ../../img/User-Cross-Sections-Widget/User012.png


Schematize Channel
------------------

1. Once the banks and cross sections are complete, the next step is to Schematize the channels.
   Click the Schematize left banks and cross sections.

.. image:: ../../img/User-Cross-Sections-Widget/User013.png


2. Errors and warning will appear if  
   something is not configured correctly.

.. image:: ../../img/User-Cross-Sections-Widget/User014.png


3. At the beginning of each segment,  
   the left bank node, right bank node must be in the same cell as the end nodes on the cross sections.

.. image:: ../../img/User-Cross-Sections-Widget/User015.png
  

4. If the cross section does  
   not touch the left or right bank, the following message will appear.

.. image:: ../../img/User-Cross-Sections-Widget/User016.png

5. Correct this condition by  
   making sure each cross section crosses both banks.

.. image:: ../../img/User-Cross-Sections-Widget/User017.png

6. If the channel  
   schematize process was successful, the following message will appear.

7. Click close to load  
   the channel info for the schematized layer.

.. image:: ../../img/User-Cross-Sections-Widget/User018.png


The schematized layers now have complete left bank, right bank, and cross section data.
Adjust cross section and left bank alignment now.
It is easier apply changes before interpolating the cross section data.

.. image:: ../../img/User-Cross-Sections-Widget/User019.png


Interpolate Natural Channel
---------------------------

1. Inspect the cross section n-value field to ensure all n-values are present.
   If missing, fill the required n-value to the field.

.. image:: ../../img/User-Cross-Sections-Widget/User020.png


2. To interpolate the  
   channel segments, export the channel data and run the interpolator.

.. image:: ../../img/User-Cross-Sections-Widget/User021.png

3. Select the folder  
   where the \*.DAT files will be saved.

.. image:: ../../img/User-Cross-Sections-Widget/User022.png


4. Once the data files  
   are written, click ok to close the following dialog box.

.. image:: ../../img/User-Cross-Sections-Widget/User023.png


5. Select the FLO-2D  
   Pro Folder and click Interpolate.

.. image:: ../../img/User-Cross-Sections-Widget/User024.png
  

6. If the interpolation is performed correctly, the following message will appear.
   Get the new data into the GeoPackage by clicking Import CHAN.DAT, AND XSEC.DAT.

.. image:: ../../img/User-Cross-Sections-Widget/User025.png


7. Click OK to  
   close the message.

.. image:: ../../img/User-Cross-Sections-Widget/User026.png
  

Prismatic Cross Sections
------------------------

Prismatic channel data can be entered and interpolated using the cross section editor.
Use this option for creating Rectangular and Trapezoidal channel segments.
This example will use two segments of channel data.
One for a rectangular channel and one for a trapezoidal channel.

Rectangular Cross Sections
---------------------------

1. Set up the Editor Widget.
   Type = Rectangular base n = 0.020

.. image:: ../../img/User-Cross-Sections-Widget/User027.png


2. Click the create  
   cross section button.

.. image:: ../../img/User-Cross-Sections-Widget/User028.png
   
3. Draw the first cross section and enter the Feature Attributes.
   See Sample bank data to

.. image:: ../../img/User-Cross-Sections-Widget/User029.png
  

4. Click Save to load  
   the cross section into the Table Editor.

.. image:: ../../img/User-Cross-Sections-Widget/User030.png


5. Edit the cross section left and right bank elevation and geometry in the table.
   Repeat the process for each cross section.
   See `Sample bank data <#sample-bank-data>`__ to learn how to fill this data automatically.

.. image:: ../../img/User-Cross-Sections-Widget/User031.png
  

Trapezoidal Cross Sections
--------------------------

1. Set up the Editor Widget.
   Type = Trapezoidal base n = 0.020

.. image:: ../../img/User-Cross-Sections-Widget/User032.png
  

2. Click the create  
   cross section button.

.. image:: ../../img/User-Cross-Sections-Widget/User028.png
 

3. Draw the first cross section  
   and enter the Feature Attributes.

.. image:: ../../img/User-Cross-Sections-Widget/User029.png
  

4. Click Save to load the  
   cross section into the Table Editor.

.. image:: ../../img/User-Cross-Sections-Widget/User030.png


6. Edit the cross section left and right bank elevation and geometry in the table.
   Repeat the process for each cross section.
   See `Sample bank data <#sample-bank-data>`__ to learn how to fill this data automatically.

.. image:: ../../img/User-Cross-Sections-Widget/User033.png
  

.. image:: ../../img/User-Cross-Sections-Widget/User034.png
   

Schematize Rectangular and Trapezoidal Channel Segment
--------------------------------------------------------

1. In this example, ten Rectangular,  
   ten Trapezoidal and 10 natural cross sections are digitized.

.. image:: ../../img/User-Cross-Sections-Widget/User055.png

.. image:: ../../img/User-Cross-Sections-Widget/User056.png



2. Click the Schematize button.

.. image:: ../../img/User-Cross-Sections-Widget/User035.png


3. If the following message  
   appears, the schematization worked properly.

4. This dialog box  
   shows the number of original cross sections and the number of schematized cross sections.

.. image:: ../../img/User-Cross-Sections-Widget/User036.png


Sample Bank Data
----------------

There are many ways to edit the bank data for R and T type channels.
This section will show two different ways to create and correct bank elevation data.

.. image:: ../../img/User-Cross-Sections-Widget/User037.png


The bank elevation data can be sampled in two methods.

Method 1: Elevation from Grid
------------------------------

The first method is from the Grid layer and the second is from the elevation Raster.

1. Click the From Grid  
   radio button and select Individual or all cross sections to sample.

.. image:: ../../img/User-Cross-Sections-Widget/User038.png


The bank data is the reference point to determine the bed elevation of the channel so it can influence the profile.
For example, if one uses the grid element elevation to set the bank elevation, the channel profile is wrong.
The Grid method should only be used if a good raster is not available.

2. Click the channel profile tool 
   and the left bank to check the profile of the channel.

.. image:: ../../img/User-Cross-Sections-Widget/User039.png
  

.. image:: ../../img/User-Cross-Sections-Widget/User040.png


This is not the preferred method since a grid elevation for a grid is always somewhere in between the bank of the channel and the internal channel
data.

.. image:: ../../img/User-Cross-Sections-Widget/User041.png


Method 2: Elevation from Raster
-----------------------------------

This method is used if an elevation raster can be used to define the bank elevation.

1. Click the From Raster radio  
   button and select Individual or all cross sections to sample.

.. image:: ../../img/User-Cross-Sections-Widget/User042.png


.. image:: ../../img/User-Cross-Sections-Widget/User043.png


Interpolate Prismatic Channel Data
-----------------------------------

1. Finish the cross sections and  
   layer organization of the trapezoidal and or rectangular channels.

2. Click the Interpolate button  
   to interpolate the left and right bank of the rectangular channel.

.. image:: ../../img/User-Cross-Sections-Widget/User044.png


3. If the process finished correctly, the following box will appear.
   Click OK to close the box.

.. image:: ../../img/User-Cross-Sections-Widget/User045.png
 

4. Click the channel profile tool  
   and the left bank to check the profile of the channel.

.. image:: ../../img/User-Cross-Sections-Widget/User039.png


.. image:: ../../img/User-Cross-Sections-Widget/User046.png


Channel N-value Interpolator
------------------------------

1. The channel n-Value interpolator  
   tool is used to define the n-value of a channel cross section based on the cross section geometry.

.. image:: ../../img/User-Cross-Sections-Widget/User047.png


2. The button calls the tool externally.

.. image:: ../../img/User-Cross-Sections-Widget/User048.png


The tool assigns an n-value for the chan.dat file based on the picture below.
The user can choose the n-values for a minimum or maximum cross section area.

.. image:: ../../img/User-Cross-Sections-Widget/User049.png

.. image:: ../../img/User-Cross-Sections-Widget/User050.png


.. image:: ../../img/User-Cross-Sections-Widget/User051.png

Alternate Bank and Channel Profile Tool
----------------------------------------

A secondary method can be used to create the cross section data.
This example will sample the map for station-elevation data using a Plugin called Profile Tool.
This tool is not the preferred method but it has some handy features that make it useful.

1. Find and install  
   the Plugin Profile Tool.

2. Select the first cross section in the Cross Section Editor widget.
   This activates the cross section table and plot.

3. Click the Profile  
   button to open the Profile Tool Plugin,

4. Click the add  
   layer button and select the Elevation Raster layer.

5. Draw a simple  
   line over cross section 1.

.. image:: ../../img/User-Cross-Sections-Widget/User052.png

6. The cross section station elevation data is listed in the Table tab shown below.
   Copy it to the clipboard.

.. image:: ../../img/User-Cross-Sections-Widget/User053.png

7.  Place the cursor  
    in the first cell of the FLO-2D Table Editor and click Paste.

8.  The cross section  
    data is pasted to the table.

9.  Repeat the process  
    for the remaining cross sections.

10. The cross section 
    is then loaded in the layer as shown below.

.. image:: ../../img/User-Cross-Sections-Widget/User054.png


