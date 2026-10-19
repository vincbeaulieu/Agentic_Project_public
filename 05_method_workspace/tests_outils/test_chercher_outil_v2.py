"""Tests unitaires de chercher_outil, v2 de la suite : + racines communes et nom de l'outil."""
import unittest
from aide_tests_v1 import importer
from test_chercher_outil_v1 import Recherche        # tests de la v1 de la suite, toujours valables
C = importer('chercher_outil')


class Racines(unittest.TestCase):
    def test_racine(self):
        self.assertTrue(C.racine('anonymisation', 'anonymiser')); self.assertFalse(C.racine('tests', 'texte'))

    def test_organisation(self):
        self.assertEqual(C.chercher(['organiser', 'versions', 'archive'], C.catalogue())[0][1]['outil'], 'organiser_outils')


if __name__ == '__main__':
    unittest.main()
