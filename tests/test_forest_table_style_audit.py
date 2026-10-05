import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('forest_audit', ROOT / 'scripts/audit_forest_tables_styles.py')
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class ForestAuditTest(unittest.TestCase):
    def test_current_tables_and_styles(self):
        result = AUDIT.audit(ROOT)
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['municipality_features_expected_from_zones'], 1911)
        self.assertEqual(len(result['split_municipalities']), 5)
        self.assertFalse(result['qgis_gui_verified'])

    def test_duplicate_code_is_detected(self):
        original = AUDIT.rows

        def changed(path):
            records = original(path)
            if path.name == 'municipality_forest_districts.csv':
                records[1]['municipality_code'] = records[0]['municipality_code']
            return records

        with patch.object(AUDIT, 'rows', side_effect=changed):
            result = AUDIT.audit(ROOT)
        self.assertIn('municipalities: duplicate identifiers', result['errors'])

    def test_mismatched_membership_is_detected(self):
        original = AUDIT.rows

        def changed(path):
            records = original(path)
            if path.name == 'municipality_forest_districts.csv':
                records[0]['basin_name'] = 'test mismatch'
            return records

        with patch.object(AUDIT, 'rows', side_effect=changed):
            result = AUDIT.audit(ROOT)
        self.assertIn('membership mismatch: 01101', result['errors'])


if __name__ == '__main__':
    unittest.main()
