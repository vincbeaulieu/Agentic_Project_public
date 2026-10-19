"""Tests unitaires de anonymiser : remplacement par rôle à partir d'empreintes (aucun nom réel dans ce test : nom fictif)."""
import unittest
from aide_tests_v1 import importer
A = importer('anonymiser')


class Anonymiser(unittest.TestCase):
    def setUp(self):
        self.roles = {A.emp('Zorglub'): 'Collègue Z', A.emp('Bidulle'): 'Collègue Z'}

    def test_nom_et_prenom_remplaces_par_un_seul_role(self):
        self.assertEqual(A.anonymiser('Relu par Zorglub Bidulle hier.', self.roles), 'Relu par Collègue Z hier.')

    def test_elision(self):
        self.assertEqual(A.anonymiser("demande d'Zorglub", self.roles), 'demande de Collègue Z')

    def test_insensible_casse_et_accents(self):
        self.assertEqual(A.emp('ZÖRGLUB'), A.emp('zorglub'))

    def test_texte_sans_nom_inchange(self):
        t = 'Le pipeline traite les données.'
        self.assertEqual(A.anonymiser(t, self.roles), t)


if __name__ == '__main__':
    unittest.main()
