"""Bookmarks (document outline): read, edit as a tree, write back.

The tree is edited with path-based helpers: a *path* is a tuple of child
indices from the root, e.g. ``(1, 0)`` is the first child of the second
top-level bookmark.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Sequence

import pymupdf

from ..errors import InvalidInput

Path = tuple[int, ...]


@dataclass
class Bookmark:
    """One outline entry. ``page`` is 0-based (-1 = no page destination)."""

    title: str
    page: int
    children: list["Bookmark"] = field(default_factory=list)
    dest: dict | None = None  # extra destination details from the file
    original_page: int | None = None  # page the ``dest`` details belong to


def toc_to_tree(toc: Sequence[Sequence]) -> list[Bookmark]:
    """Convert a PyMuPDF table of contents (``[level, title, page, dest?]``) to a tree."""
    roots: list[Bookmark] = []
    stack: list[tuple[int, Bookmark]] = []
    for entry in toc:
        level, title, page = int(entry[0]), str(entry[1]), int(entry[2]) - 1
        dest = dict(entry[3]) if len(entry) > 3 and isinstance(entry[3], dict) else None
        if dest is not None:
            dest.pop("xref", None)
        node = Bookmark(title, page, dest=dest, original_page=page)
        while stack and stack[-1][0] >= level:
            stack.pop()
        (stack[-1][1].children if stack else roots).append(node)
        stack.append((level, node))
    return roots


def tree_to_toc(tree: Sequence[Bookmark]) -> list[list]:
    """Convert a bookmark tree back to PyMuPDF's table-of-contents format."""
    toc: list[list] = []

    def walk(nodes: Sequence[Bookmark], level: int) -> None:
        for node in nodes:
            entry: list = [level, node.title, node.page + 1]
            if node.dest is not None:
                dest = dict(node.dest)
                if node.page != node.original_page:
                    dest.pop("to", None)  # the old target point belongs to another page
                    dest.pop("page", None)
                entry.append(dest)
            toc.append(entry)
            walk(node.children, level + 1)

    walk(tree, 1)
    return toc


def get_bookmarks(doc: pymupdf.Document) -> list[Bookmark]:
    """Read the document outline as a tree."""
    return toc_to_tree(doc.get_toc(simple=False))


def set_bookmarks(doc: pymupdf.Document, tree: Sequence[Bookmark]) -> None:
    """Replace the document outline with ``tree``."""
    for title, page in _walk_pages(tree):
        if not -1 <= page < doc.page_count:
            raise InvalidInput(f"Bookmark '{title}' points to page {page + 1}, which does not exist.")
    doc.set_toc(tree_to_toc(tree))


def _walk_pages(tree: Sequence[Bookmark]):
    for node in tree:
        yield node.title, node.page
        yield from _walk_pages(node.children)


def clone_tree(tree: Sequence[Bookmark]) -> list[Bookmark]:
    """Deep copy of a bookmark tree (edits never alias the original)."""
    return copy.deepcopy(list(tree))


def get_node(tree: list[Bookmark], path: Path) -> Bookmark:
    """Return the bookmark at ``path``."""
    if not path:
        raise InvalidInput("Empty bookmark path.")
    nodes = tree
    node = None
    for i in path:
        if not 0 <= i < len(nodes):
            raise InvalidInput("That bookmark no longer exists.")
        node = nodes[i]
        nodes = node.children
    assert node is not None
    return node


def _siblings(tree: list[Bookmark], path: Path) -> list[Bookmark]:
    return tree if len(path) == 1 else get_node(tree, path[:-1]).children


def add_bookmark(
    tree: list[Bookmark], title: str, page: int, parent: Path = (), index: int | None = None
) -> Path:
    """Insert a bookmark under ``parent`` (root if empty); returns its path."""
    if not title.strip():
        raise InvalidInput("A bookmark needs a title.")
    children = tree if not parent else get_node(tree, parent).children
    position = len(children) if index is None else max(0, min(index, len(children)))
    children.insert(position, Bookmark(title.strip(), page, original_page=page))
    return parent + (position,)


def rename_bookmark(tree: list[Bookmark], path: Path, title: str) -> None:
    """Change a bookmark's title."""
    if not title.strip():
        raise InvalidInput("A bookmark needs a title.")
    get_node(tree, path).title = title.strip()


def set_bookmark_page(tree: list[Bookmark], path: Path, page: int) -> None:
    """Point a bookmark at another page."""
    get_node(tree, path).page = page


def delete_bookmark(tree: list[Bookmark], path: Path) -> Bookmark:
    """Remove a bookmark (and its children); returns the removed node."""
    get_node(tree, path)
    return _siblings(tree, path).pop(path[-1])


def move_bookmark(tree: list[Bookmark], path: Path, new_parent: Path, index: int) -> Path:
    """Move a bookmark under ``new_parent`` at ``index``; returns the new path.

    ``new_parent`` and ``index`` refer to the tree *before* the move.
    """
    if new_parent[: len(path)] == path:
        raise InvalidInput("A bookmark cannot be moved inside itself.")
    node = get_node(tree, path)
    target_children = tree if not new_parent else get_node(tree, new_parent).children
    marker = object()
    target_children.insert(max(0, min(index, len(target_children))), marker)  # type: ignore[arg-type]
    _siblings(tree, path).remove(node)
    position = target_children.index(marker)  # type: ignore[arg-type]
    target_children[position] = node
    return _path_of(tree, node)


def indent_bookmark(tree: list[Bookmark], path: Path) -> Path:
    """Nest a bookmark under its previous sibling; returns the new path."""
    if path[-1] == 0:
        raise InvalidInput("The first bookmark at a level cannot be nested further.")
    siblings = _siblings(tree, path)
    node = siblings.pop(path[-1])
    new_parent = siblings[path[-1] - 1]
    new_parent.children.append(node)
    return path[:-1] + (path[-1] - 1, len(new_parent.children) - 1)


def outdent_bookmark(tree: list[Bookmark], path: Path) -> Path:
    """Move a nested bookmark up one level, right after its parent."""
    if len(path) < 2:
        raise InvalidInput("This bookmark is already at the top level.")
    node = delete_bookmark(tree, path)
    parent_path = path[:-1]
    grand_siblings = _siblings(tree, parent_path)
    grand_siblings.insert(parent_path[-1] + 1, node)
    return parent_path[:-1] + (parent_path[-1] + 1,)


def _path_of(tree: list[Bookmark], target: Bookmark) -> Path:
    def search(nodes: list[Bookmark], prefix: Path) -> Path | None:
        for i, node in enumerate(nodes):
            if node is target:
                return prefix + (i,)
            found = search(node.children, prefix + (i,))
            if found:
                return found
        return None

    result = search(tree, ())
    if result is None:  # pragma: no cover - defensive
        raise InvalidInput("Bookmark not found.")
    return result
