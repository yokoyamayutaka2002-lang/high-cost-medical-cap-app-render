import unittest
from webapp.app import build_income_map


class TestIncomeMap(unittest.TestCase):
    def test_r7_under70_has_only_letters(self):
        m = build_income_map()
        # get list of codes for R7 under70
        codes = [c for c, _ in m.get('R7', {}).get('under70', [])]
        expected = ['A', 'I', 'U', 'E', 'O']
        # Order matters as in CSV; compare as sets for robustness
        self.assertEqual(set(codes), set(expected), f'R7 under70 codes mismatch: {codes}')


if __name__ == '__main__':
    unittest.main()
