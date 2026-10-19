"""Tests unitaires de file_lmstudio (version courante), v2 de la suite : + emplacement de la file locale calculé depuis la racine de l'espace."""
import os, json, unittest
from aide_tests_v1 import importer, dossier_essai
from test_file_lmstudio_v1 import Depot            # les tests de la v1 de la suite restent valables


class Emplacement(unittest.TestCase):
    def test_file_locale_a_cote_de_l_espace(self):
        F = importer('file_lmstudio')
        self.assertEqual(os.path.dirname(os.path.dirname(F.LOCALE)), os.path.dirname(F.RACINE_CC))
        self.assertTrue(F.LOCALE.endswith(os.path.join('00_espace_cloud_claude', 'file_lmstudio')))


if __name__ == '__main__':
    unittest.main()
