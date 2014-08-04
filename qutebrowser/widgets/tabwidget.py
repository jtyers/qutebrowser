# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:

# Copyright 2014 Florian Bruhin (The Compiler) <mail@qutebrowser.org>
#
# This file is part of qutebrowser.
#
# qutebrowser is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# qutebrowser is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with qutebrowser.  If not, see <http://www.gnu.org/licenses/>.

"""The tab widget used for TabbedBrowser from browser.py.

Module attributes:
    PM_TabBarPadding: The PixelMetric value for TabBarStyle to get the padding
                      between items.
"""

import functools

from PyQt5.QtCore import pyqtSlot, Qt, QSize, QRect, QPoint
from PyQt5.QtWidgets import (QTabWidget, QTabBar, QSizePolicy, QCommonStyle,
                             QStyle, QStylePainter, QStyleOptionTab,
                             QApplication)
from PyQt5.QtGui import QIcon, QPalette, QColor

from qutebrowser.utils.qt import qt_ensure_valid
import qutebrowser.config.config as config


PM_TabBarPadding = QStyle.PM_CustomBase


class TabWidget(QTabWidget):

    """The tabwidget used for TabbedBrowser."""

    def __init__(self, parent):
        super().__init__(parent)
        bar = TabBar()
        self.setTabBar(bar)
        bar.tabCloseRequested.connect(self.tabCloseRequested)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setDocumentMode(True)
        self.setElideMode(Qt.ElideRight)
        self.setUsesScrollButtons(True)
        bar.setDrawBase(False)
        self._init_config()

    def _init_config(self):
        """Initialize attributes based on the config."""
        position_conv = {
            'north': QTabWidget.North,
            'south': QTabWidget.South,
            'west': QTabWidget.West,
            'east': QTabWidget.East,
        }
        select_conv = {
            'left': QTabBar.SelectLeftTab,
            'right': QTabBar.SelectRightTab,
            'previous': QTabBar.SelectPreviousTab,
        }
        tabbar = self.tabBar()
        self.setMovable(config.get('tabbar', 'movable'))
        self.setTabsClosable(False)
        posstr = config.get('tabbar', 'position')
        selstr = config.get('tabbar', 'select-on-remove')
        position = position_conv[posstr]
        self.setTabPosition(position)
        tabbar.vertical = position in (QTabWidget.West, QTabWidget.East)
        tabbar.setSelectionBehaviorOnRemove(select_conv[selstr])
        tabbar.refresh()

    @pyqtSlot(str, str)
    def on_config_changed(self, section, option):
        """Update attributes when config changed."""
        self.tabBar().on_config_changed(section, option)
        if section == 'tabbar':
            self._init_config()


class TabBar(QTabBar):

    """Custom tabbar with our own style.

    FIXME: Dragging tabs doesn't look as nice as it does in QTabBar.  However,
    fixing this would be a lot of effort, so we'll postpone it until we're
    reimplementing drag&drop for other reasons.

    Attributes:
        vertical: When the tab bar is currently vertical.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyle(TabBarStyle(self.style()))
        self.setFont(config.get('fonts', 'tabbar'))
        self.vertical = False

    def __repr__(self):
        return '<{} with {} tabs>'.format(self.__class__.__name__,
                                          self.count())

    def refresh(self):
        """Properly repaint the tab bar and relayout tabs."""
        # This is a horrible hack, but we need to do this so the underlaying Qt
        # code sets layoutDirty so it actually relayouts the tabs.
        self.setIconSize(self.iconSize())

    def set_tab_indicator_color(self, idx, color):
        """Set the tab indicator color.

        Args:
            idx: The tab index.
            color: A QColor.
        """
        self.setTabData(idx, color)
        self.update(self.tabRect(idx))

    @pyqtSlot(str, str)
    def on_config_changed(self, section, option):
        """Update attributes when config changed."""
        if section == 'fonts' and option == 'tabbar':
            self.setFont(config.get('fonts', 'tabbar'))

    def mousePressEvent(self, e):
        """Override mousePressEvent to close tabs if configured."""
        button = config.get('tabbar', 'close-mouse-button')
        if (e.button() == Qt.RightButton and button == 'right' or
                e.button() == Qt.MiddleButton and button == 'middle'):
            idx = self.tabAt(e.pos())
            if idx != -1:
                e.accept()
                self.tabCloseRequested.emit(idx)
                return
        super().mousePressEvent(e)

    def minimumTabSizeHint(self, index):
        """Override minimumTabSizeHint because we want no hard minimum.

        There are two problems with having a hard minimum tab size:
        - When expanding is True, the window will expand without stopping
          on some window managers.
        - We don't want the main window to get bigger with many tabs. If
          nothing else helps, we *do* want the tabs to get smaller instead
          of enforcing a minimum window size.

        Args:
            index: The index of the tab to get a sizehint for.

        Return:
            A QSize.
        """
        icon = self.tabIcon(index)
        padding_count = 0
        if not icon.isNull():
            extent = self.style().pixelMetric(QStyle.PM_TabBarIconSize, None,
                                              self)
            icon_size = icon.actualSize(QSize(extent, extent))
            padding_count += 1
        else:
            icon_size = QSize(0, 0)
        padding_width = self.style().pixelMetric(PM_TabBarPadding, None, self)
        height = self.fontMetrics().height()
        width = (self.fontMetrics().size(0, '\u2026').width() +
                 icon_size.width() + padding_count * padding_width)
        return QSize(width, height)

    def tabSizeHint(self, index):
        """Override tabSizeHint so all tabs are the same size.

        https://wiki.python.org/moin/PyQt/Customising%20tab%20bars

        Args:
            index: The index of the tab.

        Return:
            A QSize.
        """
        minimum_size = self.minimumTabSizeHint(index)
        height = self.fontMetrics().height()
        if self.vertical:
            confwidth = str(config.get('tabbar', 'width'))
            if confwidth.endswith('%'):
                perc = int(confwidth.rstrip('%'))
                width = QApplication.instance().mainwindow.width() * perc / 100
            else:
                width = int(confwidth)
            size = QSize(max(minimum_size.width(), width), height)
        elif self.count() * minimum_size.width() > self.width():
            # If we don't have enough space, we return the minimum size so we
            # get scroll buttons as soon as needed.
            size = minimum_size
        else:
            # If we *do* have enough space, tabs should occupy the whole window
            # width.
            size = QSize(self.width() / self.count(), height)
        qt_ensure_valid(size)
        return size

    def paintEvent(self, _e):
        """Override paintEvent to draw the tabs like we want to."""
        p = QStylePainter(self)
        tab = QStyleOptionTab()
        selected = self.currentIndex()
        for idx in range(self.count()):
            self.initStyleOption(tab, idx)
            if idx == selected:
                color = config.get('colors', 'tab.bg.selected')
            elif idx % 2:
                color = config.get('colors', 'tab.bg.odd')
            else:
                color = config.get('colors', 'tab.bg.even')
            tab.palette.setColor(QPalette.Window, color)
            tab.palette.setColor(QPalette.WindowText,
                                 config.get('colors', 'tab.fg'))
            indicator_color = self.tabData(idx)
            if indicator_color is None:
                indicator_color = QColor()
            tab.palette.setColor(QPalette.Base, indicator_color)
            if tab.rect.right() < 0 or tab.rect.left() > self.width():
                # Don't bother drawing a tab if the entire tab is outside of
                # the visible tab bar.
                continue
            p.drawControl(QStyle.CE_TabBarTab, tab)


class TabBarStyle(QCommonStyle):

    """Qt style used by TabBar to fix some issues with the default one.

    This fixes the following things:
        - Remove the focus rectangle Ubuntu draws on tabs.
        - Force text to be left-aligned even though Qt has "centered"
          hardcoded.

    Unfortunately PyQt doesn't support QProxyStyle, so we need to do this the
    hard way...

    Based on:

    http://stackoverflow.com/a/17294081
    https://code.google.com/p/makehuman/source/browse/trunk/makehuman/lib/qtgui.py

    Attributes:
        _style: The base/"parent" style.
    """

    def __init__(self, style):
        """Initialize all functions we're not overriding.

        This simply calls the corresponding function in self._style.

        Args:
            style: The base/"parent" style.
        """
        self._style = style
        for method in ('drawComplexControl', 'drawItemPixmap',
                       'generatedIconPixmap', 'hitTestComplexControl',
                       'itemPixmapRect', 'itemTextRect',
                       'polish', 'styleHint', 'subControlRect', 'unpolish',
                       'drawItemText', 'sizeFromContents', 'drawPrimitive'):
            target = getattr(self._style, method)
            setattr(self, method, functools.partial(target))
        super().__init__()

    def drawControl(self, element, opt, p, widget=None):
        """Override drawControl to draw odd tabs in a different color.

        Draws the given element with the provided painter with the style
        options specified by option.

        Args:
            element: ControlElement
            option: const QStyleOption *
            painter: QPainter *
            widget: const QWidget *
        """
        if element == QStyle.CE_TabBarTab:
            # We override this so we can control TabBarTabShape/TabBarTabLabel.
            self.drawControl(QStyle.CE_TabBarTabShape, opt, p, widget)
            self.drawControl(QStyle.CE_TabBarTabLabel, opt, p, widget)
        elif element == QStyle.CE_TabBarTabShape:
            p.fillRect(opt.rect, opt.palette.window())
            indicator_color = opt.palette.base().color()
            indicator_width = config.get('tabbar', 'indicator-width')
            if indicator_color.isValid() and indicator_width != 0:
                topleft = opt.rect.topLeft()
                topleft += QPoint(config.get('tabbar', 'indicator-space'), 2)
                p.fillRect(topleft.x(), topleft.y(), indicator_width,
                           opt.rect.height() - 4, indicator_color)
            # We use super() rather than self._style here because we don't want
            # any sophisticated drawing.
            super().drawControl(QStyle.CE_TabBarTabShape, opt, p, widget)
        elif element == QStyle.CE_TabBarTabLabel:
            text_rect, icon_rect = self._tab_layout(opt)
            if not opt.icon.isNull():
                qt_ensure_valid(icon_rect)
                icon_mode = (QIcon.Normal if opt.state & QStyle.State_Enabled
                             else QIcon.Disabled)
                icon_state = (QIcon.On if opt.state & QStyle.State_Selected
                              else QIcon.Off)
                icon = opt.icon.pixmap(opt.iconSize, icon_mode, icon_state)
                p.drawPixmap(icon_rect.x(), icon_rect.y(), icon)
            self._style.drawItemText(p, text_rect,
                                     Qt.AlignLeft | Qt.AlignVCenter,
                                     opt.palette,
                                     opt.state & QStyle.State_Enabled,
                                     opt.text, QPalette.WindowText)
        else:
            # For any other elements we just delegate the work to our real
            # style.
            self._style.drawControl(element, opt, p, widget)

    def pixelMetric(self, metric, option=None, widget=None):
        """Override pixelMetric to not shift the selected tab.

        Args:
            metric: PixelMetric
            option: const QStyleOption *
            widget: const QWidget *

        Return:
            An int.
        """
        if (metric == QStyle.PM_TabBarTabShiftHorizontal or
                metric == QStyle.PM_TabBarTabShiftVertical or
                metric == QStyle.PM_TabBarTabHSpace or
                metric == QStyle.PM_TabBarTabVSpace):
            return 0
        elif metric == PM_TabBarPadding:
            return 4
        else:
            return self._style.pixelMetric(metric, option, widget)

    def subElementRect(self, sr, opt, widget=None):
        """Override subElementRect to use our own _tab_layout implementation.

        Args:
            sr: SubElement
            opt: QStyleOption
            widget: QWidget

        Return:
            A QRect.
        """
        if sr == QStyle.SE_TabBarTabText:
            text_rect, _icon_rect = self._tab_layout(opt)
            return text_rect
        else:
            return self._style.subElementRect(sr, opt, widget)

    def _tab_layout(self, opt):
        """Compute the text/icon rect from the opt rect.

        This is based on Qt's QCommonStylePrivate::tabLayout
        (qtbase/src/widgets/styles/qcommonstyle.cpp) as we can't use the
        private implementation.

        Args:
            opt: QStyleOptionTab

        Return:
            A (text_rect, icon_rect) tuple (both QRects).
        """
        padding = self.pixelMetric(PM_TabBarPadding, opt)
        icon_rect = QRect()
        text_rect = QRect(opt.rect)
        qt_ensure_valid(text_rect)
        indicator_width = config.get('tabbar', 'indicator-width')
        text_rect.adjust(padding, 0, 0, 0)
        if indicator_width != 0:
            text_rect.adjust(indicator_width +
                             config.get('tabbar', 'indicator-space'), 0, 0, 0)
        if not opt.icon.isNull():
            icon_rect = self._get_icon_rect(opt, text_rect)
            text_rect.adjust(icon_rect.width() + padding, 0, 0, 0)
        text_rect = self._style.visualRect(opt.direction, opt.rect, text_rect)
        return (text_rect, icon_rect)

    def _get_icon_rect(self, opt, text_rect):
        """Get a QRect for the icon to draw.

        Args:
            opt: QStyleOptionTab
            text_rect: The QRect for the text.

        Return:
            A QRect.
        """
        icon_size = opt.iconSize
        if not icon_size.isValid():
            icon_extent = self.pixelMetric(QStyle.PM_SmallIconSize)
            icon_size = QSize(icon_extent, icon_extent)
        icon_mode = (QIcon.Normal if opt.state & QStyle.State_Enabled
                     else QIcon.Disabled)
        icon_state = (QIcon.On if opt.state & QStyle.State_Selected
                      else QIcon.Off)
        tab_icon_size = opt.icon.actualSize(icon_size, icon_mode, icon_state)
        tab_icon_size = QSize(min(tab_icon_size.width(), icon_size.width()),
                              min(tab_icon_size.height(), icon_size.height()))
        icon_rect = QRect(text_rect.left(),
                          text_rect.center().y() - tab_icon_size.height() / 2,
                          tab_icon_size.width(), tab_icon_size.height())
        icon_rect = self._style.visualRect(opt.direction, opt.rect, icon_rect)
        qt_ensure_valid(icon_rect)
        return icon_rect
