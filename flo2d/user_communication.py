# -*- coding: utf-8 -*-
import os
# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

# Unnecessary parens after u'print' keyword
# pylint: disable=C0325
import sys
import traceback

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QGridLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QWidget,
    QSpacerItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QHBoxLayout,    
)
from PyQt5.QtGui import QFont


def is_file_locked(filepath):
    if not os.path.exists(filepath):
        return False
    try:
        os.rename(filepath, filepath)
        return False
    except OSError:
        return True


class UserCommunication(object):
    """
    Class for communication with user.
    """

    def __init__(self, iface, context):
        self.iface = iface
        self.context = context

    def show_info(self, msg):
        if self.iface is not None:
            QMessageBox.information(self.iface.mainWindow(), self.context, msg)
        else:
            print(msg)
            
    def show_msg(self, msg, hSize, type="info"):
        if self.iface is not None:
            msgBox = QMessageBox()
            msgBox.setText(msg)
            msgBox.setWindowTitle("FLO-2D")
            icon = QMessageBox.Information if type=="info" else + \
                    QMessageBox.Warning if type=="warning" else + \
                    QMessageBox.Critical if type=="error" else QMessageBox.Information
            msgBox.setIcon(icon)
            horizontalSpacer = QSpacerItem(hSize, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
            layout = msgBox.layout()
            layout.addItem(horizontalSpacer, layout.rowCount(), 0, 1, layout.columnCount())
            msgBox.setFont(QFont("Courier", 8))
            msgBox.exec_()            
        else:
            print(msg)
            

    def show_warn(self, msg):
        if self.iface is not None:
            QMessageBox.warning(self.iface.mainWindow(), self.context, msg)
        else:
            print(msg)

    def show_critical(self, msg):
        if self.iface is not None:
            QMessageBox.critical(self.iface.mainWindow(), self.context, msg)
        else:
            print(msg)

    def show_error(self, msg, e):
        # try:
        if self.iface is not None:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            filename = exc_tb.tb_frame.f_code.co_filename
            function = exc_tb.tb_frame.f_code.co_name
            line = str(exc_tb.tb_lineno)

            formatted_lines = traceback.format_exc().splitlines()

            QMessageBox.critical(
                self.iface.mainWindow(),
                self.context,
                msg
                + "\n\n"
                + "Error:\n   "
                + str(exc_type.__name__)
                + ": "
                + str(exc_obj)
                + "\n\n"
                + "In file:\n   "
                + filename
                + "\n\n"
                + "In function:\n   "
                + function
                + "\n\n"
                + "On line "
                + line
                + ":\n"
                + formatted_lines[-2].replace(" ", ""),
            )

            # msg = msg + "<br><br>" + "<FONT COLOR=Crimson>In file:</FONT><br>" + filename \
            # + "<br><br>"  + "<FONT COLOR=Crimson>In function:</FONT><br>" + function  + "<br><br>"  \
            # + "<FONT COLOR=Crimson>On line </FONT>" + line + ":<br>"  + formatted_lines[-2] + "<br><br>"  \
            # + "<FONT COLOR=Crimson>Error:</FONT><br>" + str(exc_type.__name__) + ": " + str(exc_obj)
            #
            # QMessageBox.critical(
            # self.iface.mainWindow(),
            # self.context, msg
            # )

        else:
            print(msg)
        # except Exception:
        # self.show_critical("ERROR 200521.1222: Upsss! error within error!!!\n\n" + msg)

    def log(self, msg, level):
        if self.iface is not None:
            QgsMessageLog.logMessage(msg, self.context, level)
        else:
            print(msg)

    def log_info(self, msg):
        if self.iface is not None:
            try:
                QgsMessageLog.logMessage(msg, self.context, Qgis.Info)
            except TypeError:
                QgsMessageLog.logMessage(repr(msg), self.context, Qgis.Info)
        else:
            print(msg)

    def bar_error(self, msg, dur=5):
        if self.iface is not None:
            self.iface.messageBar().pushMessage(self.context, msg, level=Qgis.Critical, duration=dur)
        else:
            print(msg)

    def bar_warn(self, msg, dur=5):
        if self.iface is not None:
            self.iface.messageBar().pushMessage(self.context, msg, level=Qgis.Warning, duration=dur)
        else:
            print(msg)

    def bar_info(self, msg, dur=5):
        if self.iface is not None:
            self.iface.messageBar().pushMessage(self.context, msg, level=Qgis.Info, duration=dur)
        else:
            print(msg)

    def question(self, msg):
        if self.iface is not None:
            m = QMessageBox()
            m.setWindowTitle(self.context)
            m.setText(msg)
            m.setStandardButtons(QMessageBox.No | QMessageBox.Yes)
            m.setDefaultButton(QMessageBox.Yes)
            return True if m.exec_() == QMessageBox.Yes else False
        else:
            print(msg)

    def dialog_with_2_customized_buttons(self, title, msg, text1, text2):
        msgBox = QMessageBox()
        msgBox.setWindowTitle(title)
        if msg != "":
            msgBox.setText(msg)
        msgBox.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Close)
        msgBox.setDefaultButton(QMessageBox.Yes)
        buttonY = msgBox.button(QMessageBox.Yes)
        buttonY.setText(text1)
        buttonN = msgBox.button(QMessageBox.No)
        buttonN.setText(text2)

        # ret = msgBox.exec()
        return msgBox.exec_()

    def customized_question(
        self,
        title,
        text,
        standard_buttons=QMessageBox.No | QMessageBox.Yes,
        default=QMessageBox.Yes,
        icon=QMessageBox.Information,
    ):
        if self.iface is not None:
            parent = self.iface.mainWindow()
            m = QMessageBox(parent)
            m.setWindowTitle(title)
            m.setText(text)
            m.setStandardButtons(standard_buttons)
            m.setDefaultButton(default)
            m.setIcon(icon)

            m.setWindowModality(Qt.ApplicationModal)
            m.setWindowFlags(m.windowFlags() | Qt.WindowStaysOnTopHint)
            m.raise_()
            m.activateWindow()

            return m.exec_()
        else:
            print(text)

    def ask_component_export_action(self, comp_name):
        """
        Ask user how to proceed when a FLO-2D component has data but its CONT.DAT
        switch is OFF.

        Returns one of:
            - "export_only"
            - "export_and_turn_on"
            - "skipped"
        """
        if self.iface is None:
            # Headless / non-GUI mode: default to export_only
            print(
                f"The CONT.DAT switch for {comp_name} is OFF but data exists; "
                f"defaulting to 'export_only' (no GUI available)."
            )
            return "export_only"

        parent = self.iface.mainWindow()
        mb = QMessageBox(parent)
        mb.setIcon(QMessageBox.Question)
        mb.setWindowTitle(f"{comp_name} switch is OFF")
        mb.setText(
            f"The CONT.DAT switch for <b>{comp_name}</b> is currently <b>OFF</b>."
            "<br><br>How would you like to proceed?"
        )

        btn_export_only = mb.addButton("Export ONLY", QMessageBox.AcceptRole)
        btn_export_and_on = mb.addButton("Export and Switch ON", QMessageBox.YesRole)
        mb.addButton("Cancel", QMessageBox.RejectRole)
        mb.exec_()

        clicked = mb.clickedButton()
        if clicked is btn_export_only:
            return "export_only"
        elif clicked is btn_export_and_on:
            return "export_and_turn_on"
        else:
            return "skipped"


    def progress_bar(self, msg, minimum=0, maximum=0, init_value=0):
        pmb = self.iface.messageBar().createMessage(msg)

        pb = QProgressBar()
        pb.setMinimum(minimum)
        pb.setMaximum(maximum)
        pb.setValue(init_value)
        pb.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        pmb.layout().addWidget(pb)
        self.iface.messageBar().pushWidget(pmb, Qgis.Info)
        return pb

    def progress_bar2(
        self,
        message,
        min=0,
        max=0,
        init_value=0,
    ):
        pb = QProgressBar()
        pb.setMinimum(min)
        pb.setMaximum(max)
        pb.setValue(init_value)
        pb.setFormat("%v of %m")
        pb.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        pb.setStyleSheet("QProgressBar::chunk { background-color: lightskyblue}")

        pbm = self.iface.messageBar().createMessage(message)
        pbm.layout().addWidget(pb)

        self.iface.messageBar().pushWidget(pbm, Qgis.Info)
        self.iface.mainWindow().repaint()

        return pb

    def clear_bar_messages(self):
        self.iface.messageBar().clearWidgets()


class ScrollMessageBox(QMessageBox):
    def __init__(self, msg, *args, **kwargs):
        QMessageBox.__init__(self, *args, **kwargs)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        self.content = QWidget()
        scroll.setWidget(self.content)
        lay = QVBoxLayout(self.content)
        lay.addWidget(QLabel(msg, self))
        self.layout().addWidget(scroll, 0, 0, 1, self.layout().columnCount())
        self.setStyleSheet("QScrollArea{min-width:300 px; min-height: 400px}")


class ScrollMessageBox2(QMessageBox):
    def __init__(self, *args, **kwargs):
        QMessageBox.__init__(self, *args, **kwargs)
        chldn = self.children()
        scrll = QScrollArea(self)
        scrll.setWidgetResizable(True)
        grd = self.findChild(QGridLayout)
        lbl = QLabel(chldn[1].text(), self)
        lbl.setWordWrap(True)
        
        font = QFont("Courier")
        lbl.setFont(font)
                
        scrll.setWidget(lbl)
        scrll.setMinimumSize(750, 100)
        grd.addWidget(scrll, 1, 1, 1, self.layout().columnCount())
        chldn[1].setText("")

class TwoInputsDialog(QDialog):
    def __init__(self, label_text, first_label, first_value, second_label, second_value):
        super(TwoInputsDialog, self).__init__()

        self.setWindowTitle("FLO-2D")
        self.label = QLabel(label_text, self)
        self.first_label = QLabel(first_label, self)
        self.first_input = QSpinBox(self)
        self.first_input.setFixedWidth(70)
        self.first_input.setMaximum(1000)
        self.first_input.setValue(first_value)
        first_input_layout = QHBoxLayout()
        first_input_layout.addWidget(self.first_label)
        first_input_layout.addWidget(self.first_input)
        first_input_layout.setAlignment(Qt.AlignCenter)        
              
        layout = QVBoxLayout(self)
        layout.addWidget(self.label, alignment=Qt.AlignCenter)
        layout.addSpacing(20)
        layout.addLayout(first_input_layout) 
              
        if second_label:
            self.second_label = QLabel(second_label, self)
            self.second_input = QSpinBox(self)
            self.second_input.setFixedWidth(70)
            self.first_input.setMaximum(1000)
            self.Second_input.setValue(second_value)
            second_input_layout = QHBoxLayout()
            second_input_layout.addWidget(self.second_label)
            second_input_layout.addWidget(self.second_input)
            second_input_layout.setAlignment(Qt.AlignCenter)
            layout.addLayout(second_input_layout)
                       
        self.yes_button = QPushButton('Yes', self)
        self.yes_button.clicked.connect(self.accept)
        self.no_button = QPushButton('No', self)
        self.no_button.clicked.connect(self.reject)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self.yes_button)
        button_layout.addWidget(self.no_button)
        button_layout.setAlignment(Qt.AlignCenter)

        layout.addSpacing(20)
        layout.addLayout(button_layout)

