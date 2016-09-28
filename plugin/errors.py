# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Flo2D
                                 A QGIS plugin
 FLO-2D tools for QGIS
                              -------------------
        begin                : 2016-08-28
        git sha              : $Format:%H$
        copyright            : (C) 2016 by Lutra Consulting for FLO-2D
        email                : info@lutraconsulting.co.uk
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
class Flo2dError(Exception):
    """General class for the plugin errors"""
    pass


class Flo2dLayerNotFound(Flo2dError):
    """Raise when layer was not found in the layers tree"""
    pass
    

class Flo2dNotString(Flo2dError):
    """Raise when a string or unicode was expected"""
    pass
    
    
class Flo2dLayerInvalid(Flo2dError):
    """Raise when a layer is invalid"""
    pass
