# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ViolMapDialog
                                 A QGIS plugin
 Violence Mapping for Public Health Wales
                             -------------------
        begin                : 2016-06-05
        git sha              : $Format:%H$
        copyright            : (C) 2016 by Lutra
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
    '''General class for the plugin errors'''


class Flo2dLayerNotFound(Flo2dError):
    '''Raise when layer was not found in the layers tree'''
    

class Flo2dNotString(Flo2dError):
    '''Raise when a string or unicode was expected'''
    
    
class Flo2dLayerInvalid(Flo2dError):
    '''Raise when a layer is invalid'''