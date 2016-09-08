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
import os.path


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def is_even(number):
    return number % 2 == 0


def square_from_center_and_size(x, y, size):
    x, y, size = (float(x), float(y), float(size))
    g = "AsGPB(ST_GeomFromText('POLYGON(({} {}, {} {}, {} {}, {} {}, {} {}))'))".format(
        x-size/2, y-size/2,
        x+size/2, y-size/2,
        x+size/2, y+size/2,
        x-size/2, y+size/2,
        x-size/2, y-size/2
    )
    return g


def get_file_path(*paths):
    temp_dir = os.path.dirname(os.path.realpath(__file__))
    path = os.path.join(temp_dir, *paths)
    return path
