"""Tests unitaires de chercher_outil : les outils attendus sortent en tête pour des besoins typiques."""
import unittest
from aide_tests_v1 import importer
C = importer('chercher_outil')


class Recherche(unittest.TestCase):
    def premier(self, *q): return C.chercher(list(q), C.catalogue())[0][1]['outil']

    def test_besoins_typiques(self):
        self.assertEqual(self.premier('détecter', 'références', 'renvois', 'rapport'), 'detecteurs_rapport')
        self.assertEqual(self.premier('anonymiser', 'noms'), 'anonymiser')
        self.assertIn(self.premier('entraîner', 'classifieur'), ('entrainer_classifieur',))

    def test_rien(self):
        self.assertEqual(C.chercher(['zzzz'], C.catalogue()), [])


if __name__ == '__main__':
    unittest.main()
