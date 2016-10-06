Installation instructions
=========================

Document below provides details of installing QGIS and FLO-2D plugin from Lutra repo.

QGIS
----

To install QGIS, we recommend using `OSGeo4W 64 bit installer <http://download.osgeo.org/osgeo4w/osgeo4w-setup-x86_64.exe>`_.

During installation, select **Advanced Install** > **Install from Internet** > **All Users** > Path to download > **Direct Connection** > The default available download website

A new window will appear to **Select Packages**. Select the following packages from the **Desktop** section:

- qgis: 2.16.x
- qgis-dev: 2.17.x
- qgis-ltr: 2.14.x

(Keep clicking on **Skip** until the latest version appears).

All the dependencies will be automatically selected.

For future update/upgrade, with a new release of QGIS, you can run the installer and the new packages will appear.

FLo-2D plugin installation
^^^^^^^^^^^^^^^^^^^^^^^^^^
The plugin is hosted on our repository and accessible by using username and password. First you need to add the repository:

Adding repo
^^^^^^^^^^^

In QGIS, from the main menu, select **Plugins** > **Manage and Install Plugins**

A new window will appear. From the left panel, select **Settings**

Click on **Add...**

A new window will appear:

For **Name** type **FLO-2D**

For **URL** type **http://www.lutraconsulting.co.uk/client_files/flo2d/qgis-repo/plugins.xml**

For **Authentication** click on **Edit**

A new window will appear

Click on **Add**

Another window will appear

For **Name** type **flo-2d**

Use **Basic authentication**

For **Username** type **flo2duser**

For **Password** type **d2362e91b2**

Click **Save**

Click **OK**

In your **Repository details** window, you should have a text for **Authentication**

Click **OK**


FLO-2D repository should be added to your QGIS plugin repos.


Installing FLO-2D plugin
------------------------

In QGIS, from the main menu, select **Plugins** > **Manage and Install Plugins **

From the left panel, select **All**

In the **Search** box (top of the window) type **flo-2d**

Select the plugin from the list and click **Install plugin**

To upgrade the plugin, repeat the above, but in the last step, select **Upgrade plugin**