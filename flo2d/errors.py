# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version


class Flo2dError(Exception):
    """
    General class for the plugin errors.
    """

    pass


class Flo2dLayerNotFound(Flo2dError):
    """
    Raise when layer was not found in the layers tree.
    """

    pass


class Flo2dNotString(Flo2dError):
    """
    Raise when a string or unicode was expected.
    """

    pass


class Flo2dLayerInvalid(Flo2dError):
    """
    Raise when a layer is invalid.
    """

    pass


class Flo2dQueryResultNull(Flo2dError):
    """
    Raise when db query return None while a value(s) were expected.
    """

    pass


class GeometryValidityErrors(Exception):
    """
    Raise when feature geometry contains validity errors.
    """

    pass
