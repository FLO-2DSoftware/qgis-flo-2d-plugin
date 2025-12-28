# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.PyQt.QtCore import QSize, Qt, QPoint
from qgis.PyQt.QtGui import QColor, QPainter # QPainter is in the widget to draw legend sample line (in LegendLine.paintEvent())
from qgis.PyQt.QtWidgets import *
from PyQt5.QtWidgets import QMenu, QCheckBox, QWidgetAction, QGraphicsProxyWidget # QGraphicsProxyWidget is used to embed legend panel (QWidget) inside pyqtgraph (QGraphicsScene)
from qgis._core import QgsMessageLog

from ..deps import safe_pyqtgraph as pg
import numpy as np

pg.setConfigOption("background", "w")
pg.setConfigOption("foreground", "k")
pg.setConfigOption("antialias", True)

# Custom widget class to draw sample lines in the legend
class LegendLine(QWidget):
    def __init__(self, pen, parent=None):
        super().__init__(parent)
        self.pen = pen # Store the Qpen that defines the line's color, width and style
        self.setFixedSize(26, 10) # Fix the widget size so all legend samples are uniform

    # Custom paint handler
    def paintEvent(self, event):
        painter = QPainter(self) # Painter used to draw sample legend's sample line
        painter.setRenderHint(QPainter.Antialiasing) # Enable anti-aliasing for smoother line edges.
        painter.setPen(self.pen) # Apply the stored pen
        y = self.height() // 2 # Draw the line centered vertically in the small widget
        painter.drawLine(2, y, self.width() - 2, y) # Draw a horizontal line with small left/right margins

class PlotWidget(QWidget):
    sizehint = None # Optional cached QSize returned by sizeHint()

    def __init__(self):
        QWidget.__init__(self)
        self.items = {}
        self.legend_checks = {} # Maps curve names to their legend checkboxes
        self.chbox = []
        self.layout = QHBoxLayout() # Main horizontal layout for the widget
        self.left_layout = QVBoxLayout() # Vertical layout holding the plot and controls
        self.pw = pg.PlotWidget()

        # Floating legend overlay (stays a child of the plot)
        self.legend_panel = QFrame() # Floating panel widget that displays legend entries
        self.legend_panel.setObjectName("floatingLegend") # Assign object name for stylesheet targeting
        self.legend_panel.setFrameShape(QFrame.StyledPanel) # Subtle frame panel border
        self.legend_panel.setStyleSheet("""
        QFrame#floatingLegend {
            background: rgba(255,255,255,230);
            border: 1px solid #C0C0C0;
            border-radius: 6px;
        }
        QCheckBox {
            font-size: 10pt;
        }
        """)
        self.drag_offset = None # Track mouse offset when dragging the legend
        self.legend_panel.mousePressEvent = self.legend_mouse_press # Override mouse press to start drag
        self.legend_panel.mouseMoveEvent = self.legend_mouse_move # Override mose move to reposition legend
        self.legend_panel.mouseReleaseEvent = self.legend_mouse_release # Override mouse release to end drag
        self.legend_container = QWidget() # Inner container widget that hold legend row widgets
        self.legend_panel.setAttribute(Qt.WA_TranslucentBackground) # Allow legend to blend with background
        self.legend_container.setAttribute(Qt.WA_TranslucentBackground) # Same translucency for contents
        self.legend_layout = QVBoxLayout(self.legend_container) # Vertical layout for legend rows
        self.legend_layout.setContentsMargins(6, 6, 6, 6) # Padding around legend contents
        self.legend_layout.setSpacing(4) # Space between legend rows
        self.legend_layout.addStretch(1) # Spacer to push rows to the top

        # Layout for legend panel
        panel_layout = QVBoxLayout(self.legend_panel) # Layout manager for the outer legend panel
        panel_layout.setContentsMargins(0, 0, 0, 0) # No extra padding around inner container
        panel_layout.addWidget(self.legend_container) # Insert the legend row container widget

        # Initial size and position
        self.legend_panel.resize(220, 300) # Initial floating panel size
        self.legend_panel.hide() # Hide legend until items are added

        # Create plot & ViewBox
        self.plot = self.pw.getPlotItem()
        self.plot.showGrid(True, True, 0.25)
        self.plot.legend = None # Disable pyqtgraph's built-in legend
        self.left_layout.addWidget(self.pw) # Add the plot widget to the left-side layout
        self.vb = self.plot.getViewBox() # Reference to the plot's ViewBox (graphics container)

        # Attach legend INSIDE ViewBox (clipped)
        self.legend_proxy = QGraphicsProxyWidget(parent=self.vb) # Embed legend panel into the plot scene
        self.legend_proxy.setWidget(self.legend_panel) # Assign the plotting legend widget to the proxy
        self.legend_proxy.setPos(350, 10) # Initial position of the legend inside the plot area (grid)

        # Create a horizontal layout for the auto range button
        button_layout = QHBoxLayout()

        self.hover_chbox = QCheckBox("Inspect values")
        self.hover_chbox.setChecked(False) # Start unchecked
        self.hover_chbox.stateChanged.connect(self.toggle_hover)
        button_layout.addWidget(self.hover_chbox)

        self.auto_range_btn = QPushButton('Auto Range', self)
        self.auto_range_btn.clicked.connect(self.auto_range)

        button_layout.addWidget(self.auto_range_btn)
        button_layout.setAlignment(Qt.AlignRight)
        self.left_layout.addLayout(button_layout) # Place controls (hover + autorange) beneath the plot
        self.layout.addLayout(self.left_layout, 1) # Insert left-layout into main layout with stretch factor
        self.setLayout(self.layout)

        self.pw.scene().sigMouseMoved.connect(self.mouse_moved)

        self.init_hover_items()

        self.hover_enabled = False # Disable hover by default
        self.toggle_hover(Qt.Unchecked) # Enforce initial hidden state

    # Handle mouse press on the legend panel
    def legend_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_offset = event.pos() # Record where inside the panel the click occurred
            event.accept() # Mark event as handled

    # Handle mouse movement while dragging the legend
    def legend_mouse_move(self, event):
        if self.drag_offset is not None and (event.buttons() & Qt.LeftButton): # Only move if dragging is active and left mouse button is still pressed
            new_pos = self.legend_proxy.pos() + (event.pos() - self.drag_offset) # Compute new position by adding drag delta to the current legend position
            self.legend_proxy.setPos(new_pos) # Reposition legend panel
            event.accept() # Mark event as handled

    # Handle mouse release after dragging the legend
    def legend_mouse_release(self, event):
        self.drag_offset = None # Reset drag offset to disable dragging
        event.accept() # Mark event as handled

    def init_hover_items(self):
        self.vb = self.plot.getViewBox()

        self.vline = pg.InfiniteLine(angle=90, movable=False)
        self.hline = pg.InfiniteLine(angle=0, movable=False)

        pen = pg.mkPen(
            color=(0, 0, 0),  # RGB or QColor
            width=0.25
        )

        self.vline.setPen(pen)
        self.hline.setPen(pen)

        self.hover_label = pg.TextItem(anchor=(0, 1))
        self.hover_label.setColor(QColor("#000000"))  # black

        # Marker at snapped point
        self.hover_marker = pg.ScatterPlotItem(size=8, pen=pg.mkPen(None), brush=pg.mkBrush(50, 50, 50, 200))

        for it in (self.vline, self.hline, self.hover_label, self.hover_marker):
            it.setZValue(1e9)

        self.plot.addItem(self.vline, ignoreBounds=True)
        self.plot.addItem(self.hline, ignoreBounds=True)
        self.plot.addItem(self.hover_label)
        self.plot.addItem(self.hover_marker)

        if not getattr(self, "hover_enabled", True):
            self.vline.hide()
            self.hline.hide()
            self.hover_label.hide()
            self.hover_marker.hide()

    def _visible_curves(self):
        return [(name, item) for name, item in self.items.items() if item is not None and item.isVisible()]

    def _nearest_index_sorted(self, x_arr, x_target):
        # x_arr must be 1D sorted ascending
        idx = int(np.searchsorted(x_arr, x_target))
        if idx <= 0:
            return 0
        if idx >= len(x_arr):
            return len(x_arr) - 1
        # choose closer of idx and idx-1
        return idx if abs(x_arr[idx] - x_target) < abs(x_arr[idx - 1] - x_target) else idx - 1

    def _nearest_point_on_curve(self, item, x_target):
        x_arr, y_arr = item.getData()
        if x_arr is None or y_arr is None:
            return None

        x_arr = np.asarray(x_arr, dtype=float)
        y_arr = np.asarray(y_arr, dtype=float)

        finite = np.isfinite(x_arr) & np.isfinite(y_arr)
        if not np.any(finite):
            return None

        x = x_arr[finite]
        y = y_arr[finite]

        if len(x) == 0:
            return None

        # If x is sorted, use searchsorted (fast). If not, fall back to argmin.
        if np.all(x[1:] >= x[:-1]):
            i = self._nearest_index_sorted(x, x_target)
        else:
            i = int(np.abs(x - x_target).argmin())

        return float(x[i]), float(y[i])

    def mouse_moved(self, evt):

        if not getattr(self, "hover_enabled", True):
            return

        pos = evt[0] if isinstance(evt, (tuple, list)) else evt

        if not self.pw.sceneBoundingRect().contains(pos):
            self.vline.hide()
            self.hline.hide()
            self.hover_label.hide()
            self.hover_marker.hide()
            return

        mp = self.vb.mapSceneToView(pos)
        x_mouse = float(mp.x())
        y_mouse = float(mp.y())

        best = None  # (dist2, name, x_snap, y_snap)

        for name, item in self._visible_curves():
            pt = self._nearest_point_on_curve(item, x_mouse)
            if pt is None:
                continue

            x_snap, y_snap = pt

            # Compare distances in scene (pixel-like) coordinates
            scene_snap = self.vb.mapViewToScene(pg.Point(x_snap, y_snap))
            dx = float(scene_snap.x() - pos.x())
            dy = float(scene_snap.y() - pos.y())
            dist2 = dx * dx + dy * dy

            if best is None or dist2 < best[0]:
                best = (dist2, name, x_snap, y_snap)

        if best is None:
            # fall back to plain coords if nothing visible
            self.vline.setPos(x_mouse)
            self.hline.setPos(y_mouse)
            self.hover_label.setText(f"x = {x_mouse:.3f}\ny = {y_mouse:.3f}")
            self.hover_label.setPos(x_mouse, y_mouse)

            self.vline.show()
            self.hline.show()
            self.hover_label.show()
            self.hover_marker.hide()
            return

        _dist2, name, x_snap, y_snap = best

        self.vline.setPos(x_snap)
        self.hline.setPos(y_snap)
        self.vline.show()
        self.hline.show()

        self.hover_marker.setData([x_snap], [y_snap])
        self.hover_marker.show()

        self.hover_label.setText(f"{name}\nx = {x_snap:.3f}\ny = {y_snap:.3f}")
        self.hover_label.setPos(x_snap, y_snap)
        self.hover_label.show()

    def setSizeHint(self, width, height):
        self.sizehint = QSize(width, height)

    def sizeHint(self):
        if self.sizehint is not None:
            return self.sizehint
        return super(PlotWidget, self).sizeHint()

    def clear(self):
        self.plot.clear()
        self.plot.setTitle()
        self.plot.setLabel("bottom", text="")
        self.plot.setLabel("left", text="")
        self.items = {}
        self.init_hover_items()

        # Remove all legend row widgets except the final stretch spacer
        while self.legend_layout.count() > 1:
            item = self.legend_layout.takeAt(0) # Remove the first layout item
            if item.widget():                   # If the item is a Qwidget (legend row)
                item.widget().deleteLater()     # Schedule it for deletion to free memory
        self.legend_checks = {} # Reset mapping of plot names to legend checkboxes
        self.legend_panel.hide() # Hide the floating legend panel until new items are added

    def add_item(self, name, data, col=QColor("#0000aa"), sty=Qt.SolidLine, hide=False):
        x, y = data
        pen = pg.mkPen(color=col, width=1.5, style=sty, cosmetic=True)
        self.items[name] = self.plot.plot(x=x, y=y, connect="finite", pen=pen) # Add the curve to the plot and store it by name
        self.items[name].legend_pen = pen # Save the pen so the legend sample line matches the plotted curve
        self.items[name].legend_color = col # Store the base color separately for later use
        if not hide:
            self.items[name].show()
        else:
            self.items[name].hide()

        self.plot.autoRange()

        # Legend row widget
        row = QWidget() # Container widget representing one legend entry row
        row_layout = QHBoxLayout(row) # Horizontal layout to place icon + checkbox side-by-side
        row_layout.setContentsMargins(0, 0, 0, 0) # Remove outer padding so content is compact
        row_layout.setSpacing(6) # Space between the line sample and checkbox
        row_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter) # Align row contents left and vertically centered

        line_sample = LegendLine(self.items[name].legend_pen) # Mini widget displaying the curve's line style

        # Checkbox
        cb = QCheckBox(name) # Checkbox labeled with the curve name
        cb.setChecked(not hide) # Reflect initial visibility state of the curve
        cb.stateChanged.connect(lambda state, n=name: self.checkboxChanged(state, n)) # Toggle curve visibility when checked/unchecked

        # Assemble row
        row_layout.addWidget(line_sample) # Add line preview icon
        row_layout.addWidget(cb) # Add checkbox next to it

        # Insert into legend
        self.legend_layout.insertWidget(self.legend_layout.count() - 1, row) # Add the completed row above the stretch spacer
        self.legend_checks[name] = cb # Track the checkbox for programmatic access
        self.legend_panel.show() # Ensure the floating legend becomes visible

    def checkboxChanged(self, state, name):
        try:
            item = self.items.get(name)
            if item is None:
                return

            visible = (state == Qt.Checked)
            item.setVisible(visible)

            # If nothing is visible, do not leave a "latest plot" on screen
            any_visible = any(it.isVisible() for it in self.items.values())
            if not any_visible:
                self.hide_hover_overlays()
                self.pw.repaint()  # force refresh in some QGIS embed cases
                return

            self.plot.autoRange()

        except:
            return

    def hide_hover_overlays(self):
        if hasattr(self, "vline"):
            self.vline.hide()
        if hasattr(self, "hline"):
            self.hline.hide()
        if hasattr(self, "hover_label"):
            self.hover_label.hide()
        if hasattr(self, "hover_marker"):
            self.hover_marker.hide()

    def mouseDoubleClickEvent(self, e):
        # print the message
        print("Mouse Double Click Event")

    def update_item(self, name, data):
        x, y = data
        if name in self.items:
            self.items[name].setData(x, y)

    def auto_range(self):
        """
        Function to auto range the plot
        """
        self.plot.autoRange()

    def toggle_hover(self, state):
        self.hover_enabled = bool(state)

        if not self.hover_enabled:
            # Hide overlays immediately
            if hasattr(self, "vline"):
                self.vline.hide()
            if hasattr(self, "hline"):
                self.hline.hide()
            if hasattr(self, "hover_label"):
                self.hover_label.hide()
            if hasattr(self, "hover_marker"):
                self.hover_marker.hide()