# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.PyQt.QtCore import Qt, QEvent, QObject, QSize, pyqtSignal
from qgis.PyQt.QtGui import QKeySequence, QStandardItemModel, QStandardItem
from qgis.PyQt.QtWidgets import QApplication, QTableView, QUndoCommand, QUndoStack
from .ui_utils import load_ui
from ..utils import is_number
from ..user_communication import UserCommunication
import io
import csv

uiDialog, qtBaseClass = load_ui('table_editor')


class TableEditorWidget(qtBaseClass, uiDialog):

    before_paste = pyqtSignal()
    after_paste = pyqtSignal()

    def __init__(self, iface, plot, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.plot = plot
        self.lyrs = lyrs
        self.setupUi(self)
        self.setup_tview()
        self.tview.undoStack = QUndoStack(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.gutils = None
        self.copy_btn.clicked.connect(self.copy_selection)
        self.paste_btn.clicked.connect(self.paste)
        self.undo_btn.clicked.connect(self.undo)
        self.redo_btn.clicked.connect(self.redo)

    def undo(self):
        self.tview.undoStack.undo()

    def redo(self):
        self.tview.undoStack.redo()

    def setup_tview(self):
        self.tview = TableView()
        self.tview_lout.addWidget(self.tview)

    def setSizeHint(self, width, height):
        self._sizehint = QSize(width, height)

    def sizeHint(self):
        if self._sizehint is not None:
            return self._sizehint
        return super(TableEditorWidget, self).sizeHint()

    def copy_selection(self):
        selection = self.tview.selectedIndexes()
        if selection:
            rows = sorted(index.row() for index in selection)
            columns = sorted(index.column() for index in selection)
            rowcount = rows[-1] - rows[0] + 1
            colcount = columns[-1] - columns[0] + 1
            table = [[''] * colcount for _ in range(rowcount)]
            for index in selection:
                row = index.row() - rows[0]
                column = index.column() - columns[0]
                table[row][column] = str(index.data())
            stream = io.StringIO()
            csv.writer(stream, delimiter='\t').writerows(table)
            QApplication.clipboard().setText(stream.getvalue())

    def paste(self):
        self.before_paste.emit()
        paste_str = QApplication.clipboard().text()
        rows = paste_str.split('\n')
        num_rows = len(rows) - 1
        num_cols = rows[0].count('\t') + 1
        sel_ranges = self.tview.selectionModel().selection()
        if len(sel_ranges) == 1:
            top_left_idx = sel_ranges[0].topLeft()
            sel_col = top_left_idx.column()
            sel_row = top_left_idx.row()
            if sel_col + num_cols > self.tview.model().columnCount():
                self.uc.bar_warn('Too many columns to paste.')
                return
            if sel_row + num_rows > self.tview.model().rowCount():
                self.tview.model().insertRows(self.tview.model().rowCount(), num_rows - (self.tview.model().rowCount() - sel_row))
                for i in range(self.tview.model().rowCount()):
                    self.tview.setRowHeight(i, 20)
            for row in range(num_rows):
                columns = rows[row].split('\t')
                for i, col in enumerate(columns):
                    if not is_number(col):
                        columns[i] = ''
                [self.tview.model().setItem(sel_row + row, sel_col + col, StandardItem()
                    ) for col in range(len(columns))]
                for col in range(len(columns)):
                    self.tview.model().item(sel_row + row, sel_col + col).setData(columns[col].strip(), role=Qt.EditRole)
            self.after_paste.emit()
            self.tview.model().dataChanged.emit(top_left_idx, self.tview.model().createIndex(sel_row + num_rows, sel_col + num_cols))


class CommandItemEdit(QUndoCommand):
    """
    Command for undoing/redoing text edit changes, to be placed in undostack.
    """
    def __init__(self, widget, item, oldText, newText, description):
        QUndoCommand.__init__(self, description)
        self.item = item
        self.widget = widget
        self.oldText = oldText
        self.newText = newText

    def redo(self):
        self.item.model().itemDataChanged.disconnect(self.widget.itemDataChangedSlot)
        self.item.setText(self.newText)
        self.item.model().itemDataChanged.connect(self.widget.itemDataChangedSlot)

    def undo(self):
        self.item.model().itemDataChanged.disconnect(self.widget.itemDataChangedSlot)
        try:
            self.item.setText(self.oldText)
        except TypeError:
            self.item.setText('')
        self.item.model().itemDataChanged.connect(self.widget.itemDataChangedSlot)


class TableEditorEventFilter(QObject):
    def eventFilter(self, receiver, event):
        if event.type() == QEvent.KeyPress and event.matches(QKeySequence.Copy):
            receiver.copy_selection()
            return True
        elif event.type() == QEvent.KeyPress and event.matches(QKeySequence.Paste):
            receiver.paste()
            return True
        else:
            return super(TableEditorEventFilter, self).eventFilter(receiver, event)


class StandardItemModel(QStandardItemModel):
    """
    Items will emit this signal when edited.
    """
    itemDataChanged = pyqtSignal(object, object, object, object)


class StandardItem(QStandardItem):
    """
    Subclass QStandardItem to reimplement setData to emit itemDataChanged.
    """
    def setData(self, newValue, role=Qt.UserRole + 1):
        if role == Qt.EditRole:
            oldValue = self.data(role)
            QStandardItem.setData(self, newValue, role)
            model = self.model()
            if model is not None and oldValue != newValue:
                model.itemDataChanged.emit(self, oldValue, newValue, role)
            return
        elif role == Qt.CheckStateRole:
            oldValue = self.data(role)
            QStandardItem.setData(self, newValue, role)
            model = self.model()
            if model is not None and oldValue != newValue:
                model.itemDataChanged.emit(self, oldValue, newValue, role)
            return
        else:
            QStandardItem.setData(self, newValue, role)


class TableView(QTableView):
    def __init__(self):
        QTableView.__init__(self)
        model = StandardItemModel()
        self.setModel(model)
        self.model().itemDataChanged.connect(self.itemDataChangedSlot)
        self.undoStack = QUndoStack(self)

    def itemDataChangedSlot(self, item, oldValue, newValue, role):
        """
        Slot used to push changes of existing items onto undoStack.
        """
        if role == Qt.EditRole:
            command = CommandItemEdit(self, item, oldValue, newValue,
                                      "Text changed from '{0}' to '{1}'".format(oldValue, newValue))
            self.undoStack.push(command)
            return True
