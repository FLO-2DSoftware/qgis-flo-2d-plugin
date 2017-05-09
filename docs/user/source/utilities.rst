Tools and widgets
=================
There are several tools and widgets available for users to extract, convert and view various information from the FLO-2D model elements.

Info Tool
---------

To view information related to a FLO-2D element, you can use |InfoTool| Info Tool. This dedicated tool can be used to view hydrograph time series and plots, cross section table and plots, etc. The Info Tool works on both User Layers and Schematized layers.

.. |InfoTool| image:: img/InfoTool.png

Grid Info Tool
--------------

With this |GridInfoTool| tool, you can view elevation and roughness of each grid in a dockable panel. 

.. |GridInfoTool| image:: img/GridInfoTool.png

.. image:: img/GridInfoToolPanel.png
	:align: center
	:alt: Grid Info Tool panel

Import from GeoPackage
----------------------

With |GPKG2GPKG| tool you can import data directly from different Flo2D geopackage.
This can be helpful for importing data from geopackage created by older Flo2D plugin versions.

.. |GPKG2GPKG| image:: ../../../flo2d/img/gpkg2gpkg.png

Import RAS geometry
-------------------
To import geometry data from HEC-RAS 1D model you can use |ImportRas| tool and choose proper .PRJ or .G0n file to import. It can convert and populate RAS geometry into *Left Bank Line* and *Cross-sections* user layers, which can be schematized to valid FLO2D model.
You can also limit imported cross-sections range to Banks and Levees (if available).

.. figure:: img/ImportRAS.png
	:align: center
	:alt: imp_ras

	*Import HEC-RAS geometry* dialog

.. figure:: img/ImportRASRes.png
	:align: center
	:alt: imp_res

	Imported RAS Geometry

.. |ImportRas| image:: ../../../flo2d/img/import_ras.png


Schematic to user layers conversion
-----------------------------------
With |Schema2User| tool you can convert in approximation schematic layers to user layers and continue your work on model with it.
It can be helpful for recreating user layers from just imported GDS models, without need of starting from scratch.

.. |Schema2User| image:: ../../../flo2d/img/schematic_to_user.png

.. figure:: img/S2U.png
	:align: center
	:alt: s2u

	*Schematic to user layers conversion* dialog

.. figure:: img/S2URes.png
	:align: center
	:alt: s2u_res

	User layers obtained from schematic layers conversion
