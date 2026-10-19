"""Tests de reparer_fragments_v4. (a) Non-régression : suite v3 rejouée sur la version 4 (dont toute la suite v2). (b) Ajout de
la v4 : trou laissé par une phrase vidée (« par partie.  et la conclusion … », double espace puis minuscule), cas
synthétique (fragment « Les sections courtes sont regroupées … » collé en fin) ; une espace simple avant une minuscule
(abréviation, « cf. ») n'est pas un trou."""
import unittest
from aide_tests_v2 import chemin_version, importer_version
import test_reparer_fragments_v2 as T2
import test_reparer_fragments_v3 as T3

RF4 = importer_version('reparer_fragments', 4, 'reparer_fragments_v4_essai'); OUTIL4 = chemin_version('reparer_fragments', 4)


class SurV4:
    @classmethod
    def setUpClass(cls):
        cls._sauve = (T2.RF, T2.OUTIL, T3.RF3); T2.RF, T2.OUTIL, T3.RF3 = RF4, OUTIL4, RF4

    @classmethod
    def tearDownClass(cls):
        T2.RF, T2.OUTIL, T3.RF3 = cls._sauve


class ReparerV2SurV4(SurV4, T2.Reparer):
    pass


class ModuleV2SurV4(SurV4, T2.Module):
    pass


class TrouV3SurV4(SurV4, T3.TrouPonctuationPoint):
    pass


class PhraseVidee(unittest.TestCase):
    def test_cas_du_rapport(self):
        r, raison = RF4.reparer('Figure 1. Plan du document par partie.  et la conclusion en fin de texte ; '
                                'le glossaire est placé à la fin. Cette structure est décrite à l’étape 1 (audit).Les sections courtes sont regroupées au début')
        self.assertIsNone(raison, raison)
        self.assertEqual(r, 'Figure 1. Plan du document par partie. Les sections courtes sont regroupées au début '
                            'et la conclusion en fin de texte ; le glossaire est placé à la fin. Cette structure est décrite à l’étape 1 (audit).')

    def test_pas_de_faux_trou(self):
        self.assertEqual(RF4.trous('Voir cf. la figure, etc. et la suite.'), [])
        self.assertEqual(RF4.trous('Fin de phrase.  Nouvelle phrase.'), [])     # double espace avant une majuscule : pas un trou


if __name__ == '__main__':
    unittest.main()
