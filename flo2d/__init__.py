# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version


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
