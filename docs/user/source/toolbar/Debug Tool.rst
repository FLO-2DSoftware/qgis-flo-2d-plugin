Debug Tool
===========

Data Warnings and Errors
-------------------------

The Data Warnings and Error button opens a system that helps the user
debug data files and search for data conflicts.

.. image:: ../img/Buttons/debug.png


1. Perform
   a debug run.


2. `Export
   the \*.DAT Files <Export%20Project.html>`__.

3. Click the
   Run FLO-2D button.

.. image:: ../img/Debug/debug2.png


4. This will automatically trigger the FLO-2D check system performed by
   the engine FLOPRO.EXE.

.. image:: ../img/Debug/debug3.png


.. image:: ../img/Debug/debug4.png


5. The model will execute, perform the data checks and then
   automatically shut down. Every time the debug is executed, a new
   debug file with a timestamp is saved to the project folder.

.. image:: ../img/Debug/debug5.png


6. Click the Error and
   Warning button to open the import dialog box.

.. image:: ../img/Buttons/debug.png

.. image:: ../img/Debug/debug6.png

Debug
-----

7. To import the Debug files, click the Import DEBUG File button. The
   DEBUG file will have a date and timestamp to track progress.

.. image:: ../img/Debug/debug7.png



8. The import process will include several files that can be used to
   help users review surface features such as rim elevations, depressed
   elements and channel – floodplain interface. Click Yes to load the
   Errors and Warning Dialog box and import the review files.

.. image:: ../img/Debug/debug8.png

Conflicts
---------

The Current Project option will create a list of data conflicts. These
conflicts are not necessarily errors, they are generated based on the
conflict matrix. The conflict matrix is located Here:
c:\users\public\documents\FLO-2D Pro Documentation\Handouts\Conflict
Matrix.pdf

Levee Crests
------------

The final option is Levee Crest validation tool. It is used to review
the levees and grid element elevations.

Dialog Boxes
------------

The Errors and Warnings Dialog box shows all Errors, Conflicts, and
Warnings created by the file checking program. All of these boxes can be
used to sort and view and pan to cells with potential issues.

.. image:: ../img/Debug/debug9.png


.. image:: ../img/Debug/debug10.png


.. image:: ../img/Debug/debug11.png


Debug Layers
------------

The layers show points where there are differences between channel bank
and floodplain bank elevations, rim and floodplain inlet elevations, and
depressed elements and levee crest elevations. In this example, the
layers are grouped using a QGIS standard layer grouping procedure.

.. image:: ../img/Debug/debug12.png

Each layer has an attribute table that can be sorted and used to find
grid elements that may need elevation edits.

.. image:: ../img/Debug/debug13.png
