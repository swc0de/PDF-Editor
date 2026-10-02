"""Tests for core.operations.outline (bookmarks)."""

from __future__ import annotations

import pymupdf
import pytest

from pdf_editor.core.errors import InvalidInput
from pdf_editor.core.operations import outline as ops


@pytest.fixture
def outline_doc(outline_pdf):
    doc = pymupdf.open(outline_pdf)
    yield doc
    doc.close()


def titles(tree):
    return [(n.title, [c.title for c in n.children]) for n in tree]


def test_toc_to_tree_nesting():
    tree = ops.toc_to_tree([[1, "A", 1], [2, "A.1", 2], [3, "A.1.a", 2], [1, "B", 3]])
    assert titles(tree) == [("A", ["A.1"]), ("B", [])]
    assert tree[0].children[0].children[0].title == "A.1.a"


def test_toc_to_tree_empty():
    assert ops.toc_to_tree([]) == []


def test_tree_to_toc_roundtrip():
    toc = [[1, "A", 1], [2, "A.1", 2], [1, "B", 3]]
    assert [e[:3] for e in ops.tree_to_toc(ops.toc_to_tree(toc))] == toc


def test_tree_to_toc_drops_stale_target_point():
    tree = ops.toc_to_tree([[1, "A", 1, {"kind": 1, "to": pymupdf.Point(10, 20), "page": 0}]])
    tree[0].page = 2
    entry = ops.tree_to_toc(tree)[0]
    assert entry[2] == 3 and "to" not in entry[3]


def test_get_bookmarks(outline_doc):
    tree = ops.get_bookmarks(outline_doc)
    assert titles(tree) == [("Chapter 1", ["Section 1.1", "Section 1.2"]), ("Chapter 2", [])]
    assert tree[1].page == 3


def test_get_bookmarks_none(raw_text_doc):
    assert ops.get_bookmarks(raw_text_doc) == []


def test_set_bookmarks(outline_doc):
    tree = ops.get_bookmarks(outline_doc)
    ops.rename_bookmark(tree, (1,), "Second chapter")
    ops.set_bookmarks(outline_doc, tree)
    assert outline_doc.get_toc()[-1] == [1, "Second chapter", 4]


def test_set_bookmarks_invalid_page(outline_doc):
    with pytest.raises(InvalidInput):
        ops.set_bookmarks(outline_doc, [ops.Bookmark("bad", 99)])


def test_clone_tree_is_deep():
    tree = [ops.Bookmark("A", 0, [ops.Bookmark("B", 1)])]
    copy = ops.clone_tree(tree)
    copy[0].children[0].title = "changed"
    assert tree[0].children[0].title == "B"


def test_clone_tree_empty():
    assert ops.clone_tree([]) == []


def test_get_node():
    tree = ops.toc_to_tree([[1, "A", 1], [2, "A.1", 2]])
    assert ops.get_node(tree, (0, 0)).title == "A.1"


def test_get_node_bad_path():
    with pytest.raises(InvalidInput):
        ops.get_node([], (0,))
    with pytest.raises(InvalidInput):
        ops.get_node([ops.Bookmark("A", 0)], ())


def test_add_bookmark():
    tree = [ops.Bookmark("A", 0)]
    path = ops.add_bookmark(tree, "Child", 2, parent=(0,))
    assert path == (0, 0) and tree[0].children[0].page == 2
    assert ops.add_bookmark(tree, "First", 0, index=0) == (0,)


def test_add_bookmark_requires_title():
    with pytest.raises(InvalidInput):
        ops.add_bookmark([], "  ", 0)


def test_rename_bookmark():
    tree = [ops.Bookmark("A", 0)]
    ops.rename_bookmark(tree, (0,), " New ")
    assert tree[0].title == "New"


def test_rename_bookmark_empty_title():
    with pytest.raises(InvalidInput):
        ops.rename_bookmark([ops.Bookmark("A", 0)], (0,), "")


def test_set_bookmark_page():
    tree = [ops.Bookmark("A", 0)]
    ops.set_bookmark_page(tree, (0,), 4)
    assert tree[0].page == 4


def test_set_bookmark_page_bad_path():
    with pytest.raises(InvalidInput):
        ops.set_bookmark_page([], (3,), 1)


def test_delete_bookmark_removes_children():
    tree = ops.toc_to_tree([[1, "A", 1], [2, "A.1", 2], [1, "B", 3]])
    removed = ops.delete_bookmark(tree, (0,))
    assert removed.title == "A" and titles(tree) == [("B", [])]


def test_delete_bookmark_bad_path():
    with pytest.raises(InvalidInput):
        ops.delete_bookmark([ops.Bookmark("A", 0)], (5,))


def test_move_bookmark_between_parents():
    tree = ops.toc_to_tree([[1, "A", 1], [2, "A.1", 2], [1, "B", 3]])
    new_path = ops.move_bookmark(tree, (0, 0), (1,), 0)
    assert new_path == (1, 0) and titles(tree) == [("A", []), ("B", ["A.1"])]


def test_move_bookmark_into_itself_refused():
    tree = ops.toc_to_tree([[1, "A", 1], [2, "A.1", 2]])
    with pytest.raises(InvalidInput):
        ops.move_bookmark(tree, (0,), (0, 0), 0)


def test_indent_bookmark():
    tree = ops.toc_to_tree([[1, "A", 1], [1, "B", 2]])
    assert ops.indent_bookmark(tree, (1,)) == (0, 0)
    assert titles(tree) == [("A", ["B"])]


def test_indent_first_bookmark_refused():
    with pytest.raises(InvalidInput):
        ops.indent_bookmark([ops.Bookmark("A", 0)], (0,))


def test_outdent_bookmark():
    tree = ops.toc_to_tree([[1, "A", 1], [2, "A.1", 2], [1, "B", 3]])
    assert ops.outdent_bookmark(tree, (0, 0)) == (1,)
    assert [n.title for n in tree] == ["A", "A.1", "B"]


def test_outdent_top_level_refused():
    with pytest.raises(InvalidInput):
        ops.outdent_bookmark([ops.Bookmark("A", 0)], (0,))
