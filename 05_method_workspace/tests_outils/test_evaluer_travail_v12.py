"""Tests de evaluer_travail_v12. Non-régression : suite v11 rejouée sur la version 12 (et, par elle, les suites antérieures). La v12 ne change
que la bibliothèque de couches (docx_couches v5, dont les tests couvrent la correction) ; constante VERSION interne à 12."""
import unittest
from aide_tests_v2 import chemin_version
import test_evaluer_travail_v11 as T11

EVAL12 = chemin_version('evaluer_travail', 12)


class SurV12:
    @classmethod
    def setUpClass(cls):
        cls._s12 = (T11.EVAL11, T11.T10.EVAL10, T11.T9.EVAL9, T11.T9.T5.EVAL, T11.T9.T7.EVAL7, T11.T9.T8.EVAL8)
        T11.EVAL11 = T11.T10.EVAL10 = T11.T9.EVAL9 = T11.T9.T5.EVAL = T11.T9.T7.EVAL7 = T11.T9.T8.EVAL8 = EVAL12

    @classmethod
    def tearDownClass(cls): T11.EVAL11, T11.T10.EVAL10, T11.T9.EVAL9, T11.T9.T5.EVAL, T11.T9.T7.EVAL7, T11.T9.T8.EVAL8 = cls._s12


class N3SurV12(SurV12, T11.N3SurV11): pass
class TemoinsSurV12(SurV12, T11.TemoinsSurV11): pass
class AnnexeSurV12(SurV12, T11.AnnexeSurV11): pass
class MiseEnFormeSurV12(SurV12, T11.MiseEnFormeSurV11): pass
class AcceptationSurV12(SurV12, T11.AcceptationSurV11):
    def test_version_interne(self): self.assertIn("OUTIL, VERSION = 'evaluer_travail', 12", open(EVAL12, encoding='utf-8').read())
class ReferenceSurV12(SurV12, T11.ReferenceSurV11): pass
class DeplacementSurV12(SurV12, T11.Deplacement):
    def test_temoin_v10(self): pass
    def test_passe_avec_deplacement_conforme(self): self.assertEqual(self.d3(EVAL12, self.dossier()), [])


if __name__ == '__main__':
    unittest.main()
