import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from app_document_campaigns.services.media_archive import (
    MediaPathError,
    breadcrumbs,
    directory_entries,
    directory_tree,
    iter_media_files,
    normalize_media_path,
    remote_folder_for,
    resolve_media_source,
)


class MediaArchivePathTests(SimpleTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.media_root = Path(self.temp_dir.name)
        (self.media_root / "app_documents_campaigns" / "book_loi" / "BOOK-10" / "final").mkdir(parents=True)
        (self.media_root / "app_documents_campaigns" / "book_loi" / "BOOK-10" / "final" / "book.xlsx").write_bytes(b"xlsx")
        (self.media_root / "other").mkdir()
        (self.media_root / "other" / "proof.pdf").write_bytes(b"pdf")
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_root,
            MICROSOFT_GRAPH_STORAGE_MEDIA_PREFIX="app_documents_campaigns",
        )
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        self.temp_dir.cleanup()

    def test_rejects_parent_and_absolute_paths(self):
        for value in ("../outside", "folder/../../outside", "/etc/passwd"):
            with self.subTest(value=value), self.assertRaises(MediaPathError):
                normalize_media_path(value)

    def test_resolves_and_lists_a_folder_recursively(self):
        source = resolve_media_source("app_documents_campaigns/book_loi/BOOK-10")

        files = list(iter_media_files(source))

        self.assertTrue(source.is_dir)
        self.assertEqual(files[0][0], "app_documents_campaigns/book_loi/BOOK-10/final/book.xlsx")

    def test_remote_folder_preserves_media_path_without_duplicate_prefix(self):
        self.assertEqual(
            remote_folder_for("app_documents_campaigns/book_loi/BOOK-10/final/book.xlsx"),
            "app_documents_campaigns/book_loi/BOOK-10/final",
        )
        self.assertEqual(remote_folder_for("other/proof.pdf"), "app_documents_campaigns/other")

    def test_directory_browser_data_contains_tree_entries_and_breadcrumbs(self):
        tree = directory_tree(current_path="app_documents_campaigns/book_loi/BOOK-10/final")
        entries = directory_entries("app_documents_campaigns/book_loi/BOOK-10/final")
        crumbs = breadcrumbs("app_documents_campaigns/book_loi/BOOK-10/final")

        self.assertEqual(tree["name"], "media")
        self.assertTrue(tree["is_open"])
        app_node = next(node for node in tree["children"] if node["name"] == "app_documents_campaigns")
        self.assertTrue(app_node["is_open"])
        self.assertFalse(next(node for node in tree["children"] if node["name"] == "other")["is_open"])
        self.assertEqual(entries[0]["name"], "book.xlsx")
        self.assertEqual(crumbs[-1], {"name": "final", "path": "app_documents_campaigns/book_loi/BOOK-10/final"})

    def test_symbolic_link_cannot_be_selected(self):
        target = self.media_root / "other" / "proof.pdf"
        link = self.media_root / "proof-link.pdf"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Filesystem does not support symbolic links")

        with self.assertRaisesRegex(MediaPathError, "symbolic link"):
            resolve_media_source("proof-link.pdf")
