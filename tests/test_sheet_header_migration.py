import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import sheets

class SheetHeaderMigrationTests(unittest.TestCase):
    def test_custom_header_survives_migration_within_cb_capacity(self):
        live = list(sheets.HEADERS[:74]) + ["Custom Owner Field"]
        writes = []
        class Request:
            def execute(self): return {}
        class Values:
            def update(self, **kwargs): writes.append(kwargs); return Request()
        class Spreadsheet:
            def values(self): return Values()
        class Service:
            def spreadsheets(self): return Spreadsheet()
        with patch.object(sheets, "get_values", return_value=[live]):
            sheets.ensure_headers(Service(), "sheet-id", "Content")
        self.assertEqual(len(writes), 1)
        migrated = writes[0]["body"]["values"][0]
        self.assertIn("Custom Owner Field", migrated)
        self.assertEqual(migrated[74], "Custom Owner Field")
        self.assertLessEqual(len(migrated), sheets._column_number(sheets.SHEET_LAST_COLUMN))

if __name__ == "__main__":
    unittest.main()
