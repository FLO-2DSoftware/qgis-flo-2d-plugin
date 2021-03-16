# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
from qgis.core import QgsWkbTypes, Qgis
from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from qgis.PyQt.QtCore import QSettings, Qt 
from qgis.PyQt.QtWidgets import QFileDialog, QApplication, QProgressBar
import time

uiDialog, qtBaseClass = load_ui("sampling_xyz")
class SamplingXYZDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.con = con
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.gutils = GeoPackageUtils(con, iface)
        self.gpkg_path = self.gutils.get_gpkg_path()
        self.uc = UserCommunication(iface, "FLO-2D")
        self.current_lyr = None
        self.setup_layer_cbo()
        # connections
        self.points_cbo.currentIndexChanged.connect(self.populate_fields_cbo)
        self.points_layer_grp.clicked.connect(self.points_layer_selected)
        self.lidar_grp.clicked.connect(self.lidar_selected)

    def setup_layer_cbo(self):
        """
        Filter layer combo for points and connect field cbo.
        """
        try:
            lyrs = self.lyrs.list_group_vlayers()
            for l in lyrs:
                if l.geometryType() == QgsWkbTypes.PointGeometry:
                    if l.featureCount() != 0:
                        self.points_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())
                else:
                    pass
            self.populate_fields_cbo(self.points_cbo.currentIndex())
        except Exception as e:
            pass

    def populate_fields_cbo(self, idx):
        uri = self.points_cbo.itemData(idx)
        lyr_id = self.lyrs.layer_exists_in_group(uri)
        self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()
        self.fields_cbo.setLayer(self.current_lyr)
        self.fields_cbo.setCurrentIndex(0)

    def points_layer_selected(self):
        self.lidar_grp.setChecked(not self.points_layer_grp.isChecked())

    def lidar_selected(self):
        self.points_layer_grp.setChecked(not self.lidar_grp.isChecked())
                    
    def interpolate_from_lidar(self):

        s = QSettings()
        last_dir = s.value("FLO-2D/lastLIDARDir", "")
        lidar_files, __ = QFileDialog.getOpenFileNames(
            None,
            "Select LIDAR files",
            directory=last_dir,
            filter="(ELEVFILES.DAT   ELEVFILESBIN.DAT   *.TXT   *.DAT   *.FLT);;(ELEVFILES.DAT);;(ELEVFILEBIN.DAT);;(*.TXT);;(*.FLT);;(*.DAT);;(*.*)",
        )

        if not lidar_files:
            return
        s.setValue("FLO-2D/lastLIDARDir", os.path.dirname(lidar_files[0]))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            errors0 = []
            errors1 = []
            warnings = []
            accepted_files = []
            goodRT = 0



            progressMessageBar = self.iface.messageBar().createMessage("Doing something boring...")
            progress = QProgressBar()
            progress.setMaximum(len(lidar_files))
            progress.setAlignment(Qt.AlignLeft|Qt.AlignVCenter)
            progressMessageBar.layout().addWidget(progress)
            self.iface.messageBar().pushWidget(progressMessageBar, Qgis.Info)




            for file in lidar_files:
#                 err0, err1 = self.check_LIDAR_file(file)
#                 if err0 == "" and err1 == "" :


                
#                 for i in range(len(lidar_files)):
#                     time.sleep(1)
#                     progress.setValue(i + 1)
                

                # See if comma delimited:
                with open(file, "r") as f:
                  line = f.readline()  
                  n_commas = line.count(",")
                  n_spaces = line.count(" ")
      
#                     self.iface.messageBar().pushMessage(
#                             "Interpolating points from file " + file  +  ". The process may take several minutes...",
#                             level=Qgis.Warning)
                i= 0        
                goodRT += 1                    
                with open(file, "r") as f1:
                    i += 1
                    time.sleep(1)
                    progress.setValue(i)
                    for line in f1:
                        pass
#                             row = line.split()

                    
            self.iface.messageBar().clearWidgets()        
                    
                    
#             len_errors = len(errors0) + len(errors1)
# 
#             if errors0:
#                 errors0.append("\n")
#             if errors1:
#                 errors1.append("\n")
# 
#             warnings = errors0 + errors1
# 
#             if len_errors + goodRT > 0:
# 
#                 QApplication.restoreOverrideCursor()
# 
#                 txt1 = " could not be read (maybe wrong format).\n\n"
# 
#                 self.uc.show_info(
#                     "INFO 150321.0951:\n\n"
#                     + "* "
#                     + str(len(lidar_files))
#                     + " files selected"
#                     + (", of which " + str(len_errors) + txt1 if len_errors > 0 else ".\n\n")
#                     + "* "
#                     + str(goodRT)
#                     + " lidar files were read."
#                 )
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    

# Sub INTERPOLATE_LIDAR_VB6(Cota_En_Centro() As Single, N_Max_Points As Long, Error_Tolerance As Single)
#     
#   Dim NUMBER_OF_LIDAR_FILES As Long
#   Dim LIDARFILES() As String
#   Dim Xmin As Double, Ymin As Double, Zmin As Double, Xmax As Double, Ymax As Double, Zmax As Double
#   Dim XCMIN As Double, YCMIN As Double, XCMAX As Double, YCMAX As Double
#   Dim IMIN As Long, JMIN As Long, iMax As Long, JMAX As Long
#   Dim NPOINTSC() As Long, IDCELL() As Long
#   Dim SUMT() As Double
#   Dim FILE_EXISTS As Boolean
#   Dim XPP   As Double, YPP As Double
#   Dim ZPP As Single
#   Dim ICELL As Long, I As Long, J As Long, K As Long, NTILES As Long, ITILE As Integer
#   Dim F As Integer
#   Dim II As Integer, Ln As String, Pos As Integer, s1 As String, Comma As Boolean
#   Dim III As Long, JJJ As Long
#   Dim errorMsg As String
#   
#   
#   On Error GoTo Error_01
# 
#   ReDim SUMT(1 To MaxI_Malla, 1 To MaxJ_Malla)
#   ReDim IDCELL(1 To MaxI_Malla, 1 To MaxJ_Malla)
#   ReDim NPOINTSC(1 To MaxI_Malla, 1 To MaxJ_Malla)
# 
#   
#   If N_Max_Points = 0 And Error_Tolerance = -9999 Then
#     'Use maximum number of points on each element to interpolate
#     N_Max_Points = 1  'Assumes this maximum
#   Else
#     N_Max_Points = Int(100 / N_Max_Points) 'Do nothing and assume N_Max_Points will be taken as limit
#   End If
# 
# '  IDCELL = -9999
# 
# '  For ICELL = 1 To N_Celdas_Int
# '    If En_Malla_Double(Centro_X(ICELL), Centro_Y(ICELL), i, J) Then
# '      IDCELL(i, J) = ICELL
# '    End If
# '  Next
# 
#   NTILES = LIDAR_File_Names.Count2
# '  SUMT = 0
# '  NPOINTSC = 0
#   
#   'For each elevation LIDAR file
#   For ITILE = 0 To NTILES - 1
#     If Dire(Trim(LIDAR_File_Names.item(ITILE))) <> 0 Then
#       F = FreeFile(0)
#       Open LIDAR_File_Names.item(ITILE) For Input As #F
#       
#       'See if comma delimited:
#         Line Input #1, Ln
#         Ln = Trim(Ln)
#         Pos = InStr(Trim(Ln), ",")
#         If Pos > 0 Then
#           Comma = True
#         Else
#           Comma = False
#         End If
#         Close
#         
#       'See if 3 or 5 columns:
#       
#         Open LIDAR_File_Names.item(ITILE) For Input As #F
#         
#         If Comma Then
#           Line Input #F, Ln
#           Ln = Trim(Ln)
#           Pos = InStr(Ln, ",")
#           II = 0
#           Do While Pos <> 0
#             II = II + 1
#             Ln = Trim(Mid(Ln, Pos + 1))
#             Pos = InStr(Ln, ",")
#           Loop
#           
#           If II = 2 Then
#             '3 columns
#           ElseIf II = 4 Then
#             '5 columns
#           End If
#           
#         Else 'separated by spaces
#           Line Input #F, Ln
#           Ln = Trim(Ln)
#           Pos = InStr(Ln, " ")
#           II = 0
#           Do While Pos <> 0
#             II = II + 1
#             Ln = Trim(Mid(Ln, Pos + 1))
#             Pos = InStr(Ln, " ")
#           Loop
#           
#           If II = 2 Then
#             '3 columns
#           ElseIf II = 4 Then
#             '5 columns
#           End If
#         End If
#         Close #F
# 
#       Open LIDAR_File_Names.item(ITILE) For Input As #F
# 
#       Wait.Mensaje.Caption = "Interpolating points from file " & LIDAR_File_Names.item(ITILE) & "." & _
#                               Chr(10) & "The process may take several minutes..."
#       Wait.Cancel.Visible = False
#       Wait.Show
#       Wait.Refresh
#       
#       K = 0
#       Do While Not EOF(F)
#         If K >= N_Max_Points Then
#            'No more points needed
#            K = 0
#         Else
#           K = K + 1
#           
#           If II = 2 Then '3 columns
#             If Comma Then 'space delimited
#               Line Input #F, Ln
#                 
#               Ln = Trim(Ln)
#               Pos = InStr(Ln, ",")
#               XPP = Val(Left(Ln, Pos))
#               
#               Ln = Trim(Mid(Ln, Pos + 1))
#               Pos = InStr(Ln, ",")
#               YPP = Val(Left(Ln, Pos))
# 
#               ZPP = Val(Mid(Ln, Pos + 1))
#               
#             Else 'space delimited, no comma
#               Input #F, XPP, YPP, ZPP
#             End If
#             
#           ElseIf II = 3 Then '4 columns
#            If Comma Then 'space delimited
#              Line Input #F, Ln
#                
#              Ln = Trim(Ln)
#              Pos = InStr(Ln, ",")
#              XPP = Val(Left(Ln, Pos))
#              
#              Ln = Trim(Mid(Ln, Pos + 1))
#              Pos = InStr(Ln, ",")
#              YPP = Val(Left(Ln, Pos))
# 
#              ZPP = Val(Mid(Ln, Pos + 1))
#              
#            Else 'space delimited, no comma
#              Input #F, XPP, YPP, ZPP
#            End If
#             
#           Else '5 columns
#             If Comma Then 'comma delimited
#               Line Input #F, Ln
#                 
#               Ln = Trim(Ln)
#               Pos = InStr(Ln, ",")
#               s1 = Val(Left(Ln, Pos))
#               
#               Ln = Trim(Mid(Ln, Pos + 1))
#               Pos = InStr(Ln, ",")
#               XPP = Val(Left(Ln, Pos))
#             
#               Ln = Trim(Mid(Ln, Pos + 1))
#               Pos = InStr(Ln, ",")
#               YPP = Val(Left(Ln, Pos))
#               
#               Ln = Trim(Mid(Ln, Pos + 1))
#               Pos = InStr(Ln, ",")
#               ZPP = Val(Left(Ln, Pos))
# 
#             Else 'space delimited
#               Line Input #F, Ln
#                 
#               Ln = Trim(Ln)
#               Pos = InStr(Ln, " ")
#               s1 = Val(Left(Ln, Pos))
#               
#               Ln = Trim(Mid(Ln, Pos + 1))
#               Pos = InStr(Ln, " ")
#               XPP = Val(Left(Ln, Pos))
#             
#               Ln = Trim(Mid(Ln, Pos + 1))
#               Pos = InStr(Ln, " ")
#               YPP = Val(Left(Ln, Pos))
#               
#               Ln = Trim(Mid(Ln, Pos + 1))
#               Pos = InStr(Ln, " ")
#               ZPP = Val(Left(Ln, Pos))
#             End If
#               
#           End If
#           
#           'With the points read, calculate the number of points and sum of elevations for this (i,j):
#           If Int(K / N_Max_Points) = K / N_Max_Points Then 'Sample points: count points every NP_MAX points
#             'What happens if XPP, YPP is not contained in any cell
#             'If En_Malla_Double(XPP, YPP, I, J) Then
#             
#                     III = Int((XPP - X0_Malla) / X_CeldaMalla) + 1
#                     JJJ = Int((YPP - Y0_Malla) / Y_CeldaMalla) + 1
#                     
#                     If III > MaxI_Malla Or JJJ > MaxJ_Malla Or III < 1 Or JJJ < 1 Then
#                       'Outside the grid
#                     Else
#                       ' WHAT IF THERE ARE NO POINTS IN ELEMENT I J?
#                         NPOINTSC(III, JJJ) = NPOINTSC(III, JJJ) + 1
#                         SUMT(III, JJJ) = SUMT(III, JJJ) + ZPP
#                     End If
#             
#             'End If
#           End If
#         End If
#       Loop
#       Close #F
#     Else
#       errorMsg = errorMsg & CR_LF & "File " & LIDAR_File_Names.item(ITILE) & " does not exist."
#     End If
#   Next
#   
#   If errorMsg <> "" Then
#     MsgBox errorMsg, vbExclamation
#   End If
#     
#   'Calculate interpolated cell elevation:
#     K = 0
#     For I = 1 To MaxI_Malla
#       For J = 1 To MaxJ_Malla
#         If Celda_Interior(I, J) Then
#            K = K + 1
# '          If IDCELL(I, J) <> -9999 Then
#               If NPOINTSC(I, J) <> 0 Then
#                 Cota_En_Centro(K) = SUMT(I, J) / NPOINTSC(I, J) ' COMPUTES ELEVATION AT IDCELL(I,J)
#               Else
#                 Cota_En_Centro(K) = -9999 ' ASSINGS THIS VALUE TO CELLS WITHOUT ELEVATIONS
#               End If
# '          End If
#         End If
#       Next
#     Next
#     
#   Close
#   Wait.Hide
#   Exit Sub
#   
# Error_01:
#   Close
#   Wait.Hide
#   MsgBox "ERROR 1906101111: error while interpolating LIDAR files", vbExclamation
#   Tell_About_The_Error
#   Exit Sub
# 
# End Sub


            QApplication.restoreOverrideCursor()
            self.uc.show_info("Elevations assigned from LIDAR files.")

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 140321.1653: importing LIDAR files failed!", e)
            return
        
    def check_LIDAR_file(self, file):
        file_name, file_ext = os.path.splitext(os.path.basename(file))
        error0 = ""
        error1 = ""

        # Is file empty?:
        if not os.path.isfile(file):
            error0 = "File " + file_name + file_ext + " is being used by another process!"
            return error0, error1
        elif os.path.getsize(file) == 0:
            error0 = "File " + file_name + file_ext + " is empty!"
            return error0, error1

        # Check 2 float values in columns:
        try:
            with open(file, "r") as f:
                for line in f:
                    row = line.split()
                    if row:
                        if len(row) != 2:
                            error1 = "File " + file_name + file_ext + " must have 2 columns in all lines!"
                            return error0, error1
        except UnicodeDecodeError:
            error0 = "File " + file_name + file_ext + " is not a text file!"
        finally:
             return error0, error1
           