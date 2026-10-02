"""Pages menu: rotate, delete, duplicate, insert, reorder, extract, split, merge, crop."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PySide6.QtCore import QItemSelection, QItemSelectionModel, QObject, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QMessageBox

from ..dialogs.crop import CropDialog
from ..dialogs.insert_pages import InsertPagesDialog, is_image
from ..dialogs.merge import MergeDialog
from ..dialogs.split import SplitDialog
from ..errors import guarded
from ..workers import remove_quietly, start_job, write_temp_copy

if TYPE_CHECKING:  # pragma: no cover
    from ..document_tab import DocumentTab
    from ..main_window import MainWindow

INSERT_FILTER = "PDFs and images (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif *.webp);;All files (*)"


class PageController(QObject):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.w = window

    def _tab(self) -> "DocumentTab | None":
        return self.w.current_tab()

    def _pages(self) -> list[int]:
        return self.w.selected_pages()

    def _select(self, pages: list[int]) -> None:
        """Select ``pages`` in the thumbnail strip after a page operation."""
        tab = self._tab()
        view = self.w.thumbnails
        if tab is None or view.model() is None or not pages:
            return
        selection = QItemSelection()
        for pno in pages:
            index = view.model().index(pno, 0)
            selection.select(index, index)
        view.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        tab.viewer.go_to_page(pages[0])

    # -- simple page operations ---------------------------------------------------
    def rotate_left(self) -> None:
        self._rotate(-90)

    def rotate_right(self) -> None:
        self._rotate(90)

    def rotate_180(self) -> None:
        self._rotate(180)

    def _rotate(self, angle: int) -> None:
        if (tab := self._tab()) is not None:
            pages = self._pages()
            with guarded(self.w):
                tab.doc.rotate_pages(pages, angle)
                self._select(pages)

    def delete_pages(self) -> None:
        tab = self._tab()
        if tab is None:
            return
        pages = self._pages()
        with guarded(self.w, "Cannot delete pages"):
            tab.doc.delete_pages(pages)
            self.w.statusBar().showMessage(f"Deleted {len(pages)} page(s). Use Undo to restore.", 5000)
            self._select([min(pages[0], tab.doc.page_count - 1)])

    def duplicate_pages(self) -> None:
        if (tab := self._tab()) is not None:
            with guarded(self.w):
                self._select(tab.doc.duplicate_pages(self._pages()))

    def insert_blank(self) -> None:
        if (tab := self._tab()) is not None:
            with guarded(self.w):
                index = tab.doc.insert_blank_page(max(self._pages()) + 1)
                self._select([index])

    def insert_from_file(self) -> None:
        tab = self._tab()
        if tab is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(self.w, "Insert Pages From", self.w.settings.last_directory, INSERT_FILTER)
        if paths:
            self.w.settings.last_directory = os.path.dirname(paths[0])
            self.insert_files(tab, paths, None)

    def insert_files(self, tab: "DocumentTab", paths: list[str], index: int | None) -> None:
        """Insert PDFs/images; ``index`` None asks the user where (dialog)."""
        images = [p for p in paths if is_image(p)]
        pdfs = [p for p in paths if not is_image(p)]
        page_size, margin, wanted = None, 0.0, None
        if index is None:
            dialog = InsertPagesDialog(paths, tab.viewer.current_page, tab.doc.page_count, self.w)
            if not dialog.exec():
                return
            index, page_size, margin = dialog.index(), dialog.page_size(), dialog.margin.value()
            wanted = dialog.source_page_list()
        with guarded(self.w, "Insert failed"):
            inserted = 0
            for path in pdfs:
                inserted += tab.doc.insert_pdf(path, index + inserted, wanted)
            if images:
                inserted += tab.doc.insert_images(images, index + inserted, page_size, margin)
            self._select(list(range(index, index + inserted)))

    def move_pages(self, tab: "DocumentTab", pages: list[int], target: int) -> None:
        with guarded(self.w, "Cannot move pages"):
            new_positions = tab.doc.move_pages(pages, target)
            self._select(new_positions)

    # -- new files --------------------------------------------------------------------
    def extract_pages(self) -> None:
        tab = self._tab()
        if tab is None:
            return
        pages = self._pages()
        stem = os.path.splitext(tab.doc.display_name)[0]
        start = os.path.join(self.w.settings.last_directory, f"{stem}_pages.pdf")
        path, _ = QFileDialog.getSaveFileName(self.w, "Extract Pages To", start, "PDF files (*.pdf)")
        if not path:
            return
        with guarded(self.w, "Extract failed") as g:
            tab.doc.extract_pages_to(pages, path)
        if not g.failed and self._ask_open(f"Extracted {len(pages)} page(s) to {os.path.basename(path)}."):
            self.w.file.open_path(path)

    def _ask_open(self, message: str) -> bool:
        answer = QMessageBox.question(self.w, "Done", f"{message}\n\nOpen it now?")
        return answer == QMessageBox.StandardButton.Yes

    def split(self) -> None:
        tab = self._tab()
        if tab is None:
            return
        stem = os.path.splitext(tab.doc.display_name)[0]
        folder = os.path.dirname(tab.doc.path) if tab.doc.path else self.w.settings.last_directory
        dialog = SplitDialog(tab.doc.page_count, stem, folder, self.w)
        if not dialog.exec():
            return
        source = write_temp_copy(tab.doc)
        out_dir = dialog.folder.text()

        def done(paths: list[str]) -> None:
            answer = QMessageBox.question(
                self.w, "Split complete", f"Created {len(paths)} file(s) in\n{out_dir}\n\nOpen the folder?"
            )
            if answer == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(QUrl.fromLocalFile(out_dir))

        start_job(
            self.w, "Splitting document…", "pdf_editor.core.tasks:split_task",
            {"source": source, "groups": dialog.groups(), "output_dir": out_dir,
             "base_name": dialog.base.text() or stem, "password": tab.doc.password},
            on_success=done, on_finally=lambda: remove_quietly(source),
        )

    def merge(self) -> None:
        tab = self._tab()
        initial = [tab.doc.path] if tab is not None and tab.doc.path and not tab.doc.is_modified else []
        dialog = MergeDialog(self.w.settings.last_directory, initial, self.w)
        if not dialog.exec():
            return
        paths = dialog.paths()
        start = os.path.join(os.path.dirname(paths[0]), "merged.pdf")
        output, _ = QFileDialog.getSaveFileName(self.w, "Save Merged PDF As", start, "PDF files (*.pdf)")
        if not output:
            return
        if self.w.find_tab(output) is not None:
            QMessageBox.warning(self.w, "File is open", "Choose a file that is not open in a tab.")
            return

        def done(result: dict) -> None:
            if self._ask_open(f"Merged {len(paths)} files ({result['pages']} pages)."):
                self.w.file.open_path(result["path"])

        start_job(self.w, "Merging PDFs…", "pdf_editor.core.tasks:merge_task",
                  {"paths": paths, "output": output}, on_success=done)

    # -- crop ---------------------------------------------------------------------------
    def crop(self) -> None:
        tab = self._tab()
        if tab is None:
            return
        selected = self._pages()
        dialog = CropDialog(len(selected), self.w)
        if not dialog.exec():
            return
        scope = dialog.scope_name()
        pages = {"current": [tab.viewer.current_page], "selected": selected,
                 "all": list(range(tab.doc.page_count))}[scope]
        with guarded(self.w, "Crop failed"):
            if dialog.reset.isChecked():
                tab.doc.reset_crop(pages)
            else:
                tab.doc.crop_margins(pages, *dialog.margins_pt())
