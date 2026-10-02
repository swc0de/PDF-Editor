"""The main window: document tabs, side panels, toolbars, menus and status bar."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QCursor, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QDockWidget, QMainWindow, QStackedWidget, QTabWidget, QWidget

from .. import APP_NAME
from ..core.document import PdfDocument
from ..settings import Settings
from . import menus
from .actions import SPECS, create_actions
from .annotations_panel import AnnotationsPanel
from .autosave import AutosaveManager
from .controllers.annotate_ops import AnnotController
from .controllers.content_ops import ContentController
from .controllers.edit_ops import EditController, HelpController, ToolController
from .controllers.file_ops import FileController
from .controllers.page_ops import PageController
from .controllers.tool_ops import ToolsController
from .controllers.view_ops import ViewController
from .document_tab import DocumentTab
from .outline_panel import OutlinePanel
from .qt_utils import glyph_icon
from .search import SearchBar
from .theme import canvas_color
from .thumbnails import ThumbnailModel, ThumbnailPanel
from .tool_options import ToolOptions, ToolOptionsBar
from .workers import cancel_all_jobs
from .widgets import PageNumberBox, StatusLabels, WelcomePage, ZoomBox
from .window_events import WindowEventsMixin
from .window_recovery import RecoveryMixin


class MainWindow(RecoveryMixin, WindowEventsMixin, QMainWindow):
    """Top-level window holding one tab per open document."""

    def __init__(self, settings: Settings, effective_theme: str = "light") -> None:
        super().__init__()
        self.settings = settings
        self.effective_theme = effective_theme
        self.cursor_busy = QCursor(Qt.CursorShape.WaitCursor)
        self.setWindowTitle(APP_NAME)
        self.setAcceptDrops(True)
        self.resize(1280, 860)
        self.recent_menu = None
        self.tools_toolbar = None

        self.file = FileController(self)
        self.edit = EditController(self)
        self.view = ViewController(self)
        self.tool_ctl = ToolController(self)
        self.tools = ToolsController(self)
        self.pages_ctl = PageController(self)
        self.annot_ctl = AnnotController(self)
        self.content_ctl = ContentController(self)
        self.help = HelpController(self)
        self.tool_options = ToolOptions(settings, self)
        self.autosave = AutosaveManager(settings.autosave_minutes, parent=self)
        self._init_extensions()

        self.page_box = PageNumberBox(self)
        self.zoom_box = ZoomBox(self)
        self.search_bar = SearchBar(self)
        self.actions = create_actions(self, self._resolve)

        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.file.close_tab)
        self.tabs.currentChanged.connect(self._on_current_tab_changed)
        self.welcome = WelcomePage(self)
        self.welcome.openRequested.connect(self.file.open_dialog)
        self.welcome.recentRequested.connect(self.file.open_recent)
        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.welcome)
        self.stack.addWidget(self.tabs)
        self.setCentralWidget(self.stack)

        self.thumbnails = ThumbnailPanel(self)
        self.thumbnails.pageActivated.connect(lambda p: self._with_tab(lambda t: t.viewer.go_to_page(p)))
        self.thumbnails.customContextMenuRequested.connect(self._thumbnail_menu)
        self.thumbnails.deleteRequested.connect(lambda: self.pages_ctl.delete_pages())
        self.outline = OutlinePanel(self)
        self.outline.pageRequested.connect(lambda p: self._with_tab(lambda t: t.viewer.go_to_page(p)))
        self.docks: dict[str, QDockWidget] = {}
        self._add_dock("thumbnails", "Pages", self.thumbnails, Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("outline", "Bookmarks", self.outline, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.annotations_panel = AnnotationsPanel(self)
        self.annotations_panel.annotationActivated.connect(
            lambda p, x: self._with_tab(lambda t: t.select_annotation(p, x)))
        self.annotations_panel.deleteRequested.connect(
            lambda p, x: self._with_tab(lambda t: t.doc.delete_annotation(p, x)))
        self._add_dock("annotations", "Annotations", self.annotations_panel, Qt.DockWidgetArea.RightDockWidgetArea)
        self.tabifyDockWidget(self.docks["thumbnails"], self.docks["outline"])
        self.docks["thumbnails"].raise_()

        self.page_box.pageRequested.connect(lambda p: self._with_tab(lambda t: t.viewer.go_to_page(p)))
        self.zoom_box.zoomRequested.connect(self.view.apply_zoom_request)
        self.options_bar = ToolOptionsBar(self.tool_options, self, settings)
        self.options_bar.signatureNewRequested.connect(self.create_signature)
        self.options_bar.signatureDeleteRequested.connect(self.content_ctl.delete_signature)
        self.options_bar.refresh_signatures()
        menus.build_toolbars(self)
        menus.build_menus(self)
        self.status = StatusLabels(self.statusBar())
        self._restore_window_state()
        self._sync_checkable_actions()
        self.refresh_recent()
        self.update_ui()

    # ------------------------------------------------------------------
    # wiring helpers
    def _init_extensions(self) -> None:
        """Hook for registering additional controllers."""

    def _resolve(self, handler: str):
        name, _, method = handler.partition(".")
        if name == "tool":
            return lambda: self.tool_ctl.set(method)
        controller = {"file": self.file, "edit": self.edit, "view": self.view, "tools": self.tools,
                      "help": self.help}.get(name) or getattr(self, f"{name}_ctl", None)
        if controller is None or not hasattr(controller, method):
            raise AttributeError(f"No handler for action '{handler}'")
        return getattr(controller, method)

    def _add_dock(self, name: str, title: str, widget: QWidget, area: Qt.DockWidgetArea) -> None:
        dock = QDockWidget(title, self)
        dock.setObjectName(f"dock_{name}")
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        dock.visibilityChanged.connect(lambda _v, n=name: self._sync_dock_action(n))
        self.docks[name] = dock

    def toggle_dock(self, name: str) -> None:
        dock = self.docks[name]
        dock.setVisible(not dock.isVisible())
        if dock.isVisible():
            dock.raise_()

    def _sync_dock_action(self, name: str) -> None:
        action = self.actions.get(f"view.panel_{name}")
        if action is not None:
            action.blockSignals(True)
            action.setChecked(self.docks[name].isVisible())
            action.blockSignals(False)

    def _sync_checkable_actions(self) -> None:
        for key, value in (("view.continuous", self.settings.continuous_scroll),
                           ("view.invert", self.settings.invert_pages)):
            self.actions[key].blockSignals(True)
            self.actions[key].setChecked(value)
            self.actions[key].blockSignals(False)
        self.actions[f"view.theme_{self.settings.theme}"].setChecked(True)
        for name in self.docks:
            self._sync_dock_action(name)

    def _with_tab(self, func) -> None:
        tab = self.current_tab()
        if tab is not None:
            func(tab)

    # ------------------------------------------------------------------
    # tabs
    def current_tab(self) -> DocumentTab | None:
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, DocumentTab) else None

    def tabs_list(self) -> list[DocumentTab]:
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def find_tab(self, path: str) -> DocumentTab | None:
        target = os.path.normcase(os.path.abspath(path))
        for tab in self.tabs_list():
            if tab.doc.path and os.path.normcase(tab.doc.path) == target:
                return tab
        return None

    def add_document(self, doc: PdfDocument) -> DocumentTab:
        tab = DocumentTab(doc, self.settings, self.tool_options, self)
        tab.viewer.setBackgroundBrush(canvas_color(self.effective_theme))
        tab.thumb_model = ThumbnailModel(doc, tab.scheduler, self.devicePixelRatioF(), tab)
        tab.thumb_model.pagesDropped.connect(lambda pages, target, t=tab: self.on_pages_dropped(t, pages, target))
        tab.thumb_model.filesDropped.connect(lambda paths, target, t=tab: self.on_files_dropped(t, paths, target))
        tab.modifiedChanged.connect(lambda _m, t=tab: self._update_tab_title(t))
        tab.documentChanged.connect(lambda event, t=tab: self._on_document_changed(t, event))
        tab.currentPageChanged.connect(lambda _p, t=tab: self._on_page_changed(t))
        tab.zoomChanged.connect(lambda _z, t=tab: self._on_zoom_changed(t))
        tab.toolChanged.connect(lambda name, t=tab: self._on_tool_changed(t, name))
        tab.history.changed.connect(lambda t=tab: self._on_history_changed(t))
        self.autosave.watch(tab)
        tab.annotationSelected.connect(
            lambda p, x, t=tab: self.annotations_panel.select(p, x) if t is self.current_tab() else None)
        index = self.tabs.addTab(tab, doc.display_name)
        self.tabs.setTabToolTip(index, doc.path or doc.display_name)
        self.tabs.setCurrentIndex(index)
        self.stack.setCurrentWidget(self.tabs)
        self._update_tab_title(tab)
        return tab

    def remove_tab(self, tab: DocumentTab) -> None:
        self.autosave.unwatch(tab)
        index = self.tabs.indexOf(tab)
        if index >= 0:
            self.tabs.removeTab(index)
        tab.close_document()
        tab.deleteLater()
        if self.tabs.count() == 0:
            self.stack.setCurrentWidget(self.welcome)
            self.refresh_recent()
            self._on_current_tab_changed(-1)

    def _update_tab_title(self, tab: DocumentTab) -> None:
        index = self.tabs.indexOf(tab)
        if index >= 0:
            self.tabs.setTabText(index, tab.title)
            self.tabs.setTabToolTip(index, tab.doc.path or tab.doc.display_name)
        if tab is self.current_tab():
            self.setWindowTitle(f"{tab.title} — {APP_NAME}")
            self.update_ui()

    def _on_current_tab_changed(self, _index: int) -> None:
        tab = self.current_tab()
        self.thumbnails.setModel(tab.thumb_model if tab else None)
        self.outline.set_tab(tab)
        self.search_bar.set_controller(tab.search if tab else None)
        self.bind_panels(tab)
        if tab is not None:
            self.setWindowTitle(f"{tab.title} — {APP_NAME}")
            self.thumbnails.sync_current(tab.viewer.current_page)
            self._on_tool_changed(tab, tab.tool_name)
        else:
            self.setWindowTitle(APP_NAME)
        self.update_ui()

    def bind_panels(self, tab: DocumentTab | None) -> None:
        """Point the side panels at ``tab``."""
        self.annotations_panel.set_tab(tab)

    # ------------------------------------------------------------------
    # UI state
    def update_ui(self) -> None:
        tab = self.current_tab()
        has_tab = tab is not None
        for key, action in self.actions.items():
            if key.startswith(("file.new", "file.open", "file.quit", "help.", "edit.settings", "view.theme",
                               "view.continuous", "view.invert", "view.panel_")):
                continue
            action.setEnabled(has_tab)
        if tab is not None:
            history = tab.history
            self.actions["edit.undo"].setEnabled(history.can_undo)
            self.actions["edit.redo"].setEnabled(history.can_redo)
            self.actions["edit.undo"].setText(f"&Undo {history.undo_label}".rstrip())
            self.actions["edit.redo"].setText(f"&Redo {history.redo_label}".rstrip())
            self.page_box.set_state(tab.viewer.current_page, tab.viewer.page_count)
            self.zoom_box.set_zoom(tab.viewer.zoom, tab.viewer.fit_mode)
        else:
            self.page_box.set_state(0, 0)
        self.page_box.setEnabled(has_tab)
        self.zoom_box.setEnabled(has_tab)
        self.search_bar.setEnabled(has_tab)
        self.status.update(tab)

    def refresh_recent(self) -> None:
        recent = self.settings.recent_files()
        self.welcome.set_recent(recent)
        if self.recent_menu is None:
            return
        self.recent_menu.clear()
        for i, path in enumerate(recent):
            action = self.recent_menu.addAction(f"&{i + 1} {os.path.basename(path)}")
            action.setToolTip(path)
            action.triggered.connect(lambda _c=False, p=path: self.file.open_recent(p))
        if recent:
            self.recent_menu.addSeparator()
            clear = self.recent_menu.addAction("Clear List")
            clear.triggered.connect(lambda: (self.settings.clear_recent_files(), self.refresh_recent()))
        self.recent_menu.setEnabled(bool(recent))

    def on_theme_changed(self) -> None:
        for key, action in self.actions.items():
            glyph = SPECS[key].glyph
            if glyph:
                action.setIcon(glyph_icon(glyph))
        for tab in self.tabs_list():
            tab.viewer.setBackgroundBrush(canvas_color(self.effective_theme))

    def refresh_ocr_action(self) -> None:
        """Label the OCR action when Tesseract is missing (the dialog explains how to install it)."""
        status = self.tools.ocr_status(refresh=True)
        action = self.actions["tools.ocr"]
        if status.available:
            action.setText("Recognize Text (&OCR)…")
            action.setStatusTip("Make scanned pages searchable and selectable")
        else:
            action.setText("Recognize Text (OCR) — Tesseract not installed…")
            action.setStatusTip("OCR is disabled because Tesseract is not installed. Click for instructions.")

    def apply_settings(self) -> None:
        """Re-read settings after the settings dialog was accepted."""
        from PySide6.QtWidgets import QApplication

        from .theme import apply_theme

        self.effective_theme = apply_theme(QApplication.instance(), self.settings.theme)
        self.on_theme_changed()
        self._sync_checkable_actions()
        self.autosave.set_interval(self.settings.autosave_minutes)
        self.tool_options.set(stroke=self.settings.annotation_color, highlight=self.settings.highlight_color,
                              author=self.settings.author)

    # ------------------------------------------------------------------
    # drag & drop, window state, closing
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls() and any(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        files = [p for p in paths if os.path.isfile(p)]
        if files:
            event.acceptProposedAction()
            self.file.open_paths(files)

    def _restore_window_state(self) -> None:
        geometry = self.settings.window_geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = self.settings.window_state()
        if state is not None:
            self.restoreState(state)
        else:
            self.docks["annotations"].hide()

    def save_window_state(self) -> None:
        self.settings.set_window_geometry(self.saveGeometry())
        self.settings.set_window_state(self.saveState())
        self.settings.sync()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.save_window_state()  # before tabs close, so open panels are remembered
        if not self.file.close_all():
            event.ignore()
            return
        cancel_all_jobs()
        self.autosave.shutdown()
        event.accept()
