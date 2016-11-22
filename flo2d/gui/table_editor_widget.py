# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt4.QtCore import QEvent, QObject, QSize
from PyQt4.QtGui import QKeySequence, QStandardItem, QApplication, QIcon
from .utils import load_ui
from ..utils import is_number
from ..user_communication import UserCommunication
import StringIO
import csv
import os


uiDialog, qtBaseClass = load_ui('table_editor')


class TableEditorEventFilter(QObject):
    def eventFilter(self, receiver, event):
        if event.type() == QEvent.KeyPress and event.matches(QKeySequence.Copy):
            # print receiver, type(receiver)
            receiver.copy_selection()
            return True
        elif event.type() == QEvent.KeyPress and event.matches(QKeySequence.Paste):
            receiver.paste()
            return True
        else:
            return super(TableEditorEventFilter, self).eventFilter(receiver, event)


class TableEditorWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, plot, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.plot = plot
        self.lyrs = lyrs
        self.setupUi(self)
        # self.ev_filter = TableEditorEventFilter()
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.gutils = None
        # self.installEventFilter(self.ev_filter)
        self.copy_btn.clicked.connect(self.copy_selection)
        self.paste_btn.clicked.connect(self.paste)

    def setSizeHint(self, width, height):
        self._sizehint = QSize(width, height)

    def sizeHint(self):
        # print('sizeHint:', self._sizehint)
        if self._sizehint is not None:
            return self._sizehint
        return super(TableEditorWidget, self).sizeHint()

    def set_icon(self, btn, icon_file):
        idir = os.path.join(os.path.dirname(__file__), '..\\img')
        btn.setIcon(QIcon(os.path.join(idir, icon_file)))

    def copy_selection(self):
        selection = self.bc_tview.selectedIndexes()
        if selection:
            rows = sorted(index.row() for index in selection)
            columns = sorted(index.column() for index in selection)
            rowcount = rows[-1] - rows[0] + 1
            colcount = columns[-1] - columns[0] + 1
            table = [[''] * colcount for _ in range(rowcount)]
            for index in selection:
                row = index.row() - rows[0]
                column = index.column() - columns[0]
                table[row][column] = unicode(index.data())
            stream = StringIO.StringIO()
            csv.writer(stream, delimiter='\t').writerows(table)
            QApplication.clipboard().setText(stream.getvalue())

    def paste(self):
        paste_str = QApplication.clipboard().text()
        rows = paste_str.split('\n')
        num_rows = len(rows) - 1
        num_cols = rows[0].count('\t') + 1
        sel_ranges = self.bc_tview.selectionModel().selection()
        if len(sel_ranges) == 1:
            top_left_idx = sel_ranges[0].topLeft()
            sel_col = top_left_idx.column()
            sel_row = top_left_idx.row()
            if sel_col + num_cols > self.bc_tview.model().columnCount():
                self.uc.bar_warn('Too many columns to paste.')
                return
            if sel_row + num_rows > self.bc_tview.model().rowCount():
                self.bc_tview.model().insertRows(self.bc_tview.model().rowCount(), num_rows - (self.bc_tview.model().rowCount() - sel_row))
                for i in range(self.bc_tview.model().rowCount()):
                    self.bc_tview.setRowHeight(i, 20)
            self.bc_tview.model().blockSignals(True)
            for row in xrange(num_rows):
                columns = rows[row].split('\t')
                for i, col in enumerate(columns):
                    if not is_number(col):
                        columns[i] = ''
                [self.bc_tview.model().setItem(sel_row + row, sel_col + col, QStandardItem(columns[col].strip())
                    ) for col in xrange(len(columns))]
            self.bc_tview.model().blockSignals(False)
            self.bc_tview.model().dataChanged.emit(top_left_idx, self.bc_tview.model().createIndex(sel_row + num_rows, sel_col + num_cols))
