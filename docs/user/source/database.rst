Plugin's Data Storage
=====================

Database Format
---------------

The plugin uses the [GeoPackage](http://www.geopackage.org/spec/) for data storage. It is a [SQLite](http://www.sqlite.org/) database with spatial extensions for storing vector and raster data.


Data Model
----------

Data are stored in database tables. Some of the tables have a geometry column that makes them a spatial layer loadable by almost any GIS application. All layers use a **single projection for geometry data**, defined during database creation.

In QGIS model data are loaded into current project when users connect to a database. Alternatively, users can load any table using QGIS Browser or DB Manager plugin.

Data are organized in several dozen tables which are mostly referenced by each other. **Manual adding or modifying the data could potentially brake the references**.

Detailed description of database structure is available from [Developers Documentation](../dev/db_structure/db_structure.md)


Connecting To a Database
------------------------

When users start to work with the plugin they must connect to a database - either create a new one or pick an existing one.
