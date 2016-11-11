# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Flo2D
                                 A QGIS plugin
 FLO-2D tools for QGIS
                             -------------------
        begin                : 2016-08-28
        copyright            : (C) 2016 by Lutra Consulting for FLO-2D
        email                : info@lutraconsulting.co.uk
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""

# DO NOT REMOVE 
# when used mixture of for qgis.PyQt.* and PyQt4.* in the project
# we need to have consistent sip version set
# see /usr/lib/python2.7/dist-packages/qgis/PyQt/QtCore.py
import qgis.PyQt
# END DO NOT REMOVE 


def classFactory(iface):  # pylint: disable=invalid-name
    """Load Flo2D class from file Flo2D.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .flo2d import Flo2D
    return Flo2D(iface)
