Working With the Plugin
=======================

In the example below, it is assumed that user is generating a hydraulic model from scratch. First step to build a model, is to create fresh database, where all the model files will reside.

Creating a new database
-------------------
To create a new database:
* In QGIS, from the main menu **Plugins > Flo2D > Settings**
* A new window will appear:

	* Click on **Create**
	* In the new window, type in your database name and hit **OK**
	* Select the projection in the next window
	* Set the default **Grid cell size** and the **Manning's n**

* Click **OK**


Import GDS ASCII Files (Optional)
---------------------------------

Users can import model data created in GDS.

Create or Modify Model Data
---------------------------

Create new model from scratch using plugin tools and/or modify existing model data.
Various tools help to view/inspect model data.

Export GDS ASCII Files
----------------------

Once the model data is defined, users can export it to ASCII files read by the solver or GDS.