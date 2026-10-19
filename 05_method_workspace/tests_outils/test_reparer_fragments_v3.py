"""Tests de reparer_fragments_v3. (a) Non-régression : toute la suite v2 (sigle répété collé, fragment collé après un point,
dernière phrase sans ponctuation, trou en début de paragraphe, refus, module d'opérations et aperçu sur un docx d'essai) est
rejouée sur la version 3. (b) Ajout de la v3 : trou « ponctuation intérieure suivie d'un point » (« ; . », « , . », « : . »),
cas réel du rapport (« établi dans ses principes ; . Il décrit … essais.quatre choix restent à arrêter (§17.1) ») ; un tel
motif déjà présent dans la vue d'origine n'est pas pris pour un trou ; un point-virgule suivi d'un mot n'est pas un trou."""
import unittest
from aide_tests_v2 import chemin_version, importer_version
import test_reparer_fragments_v2 as T2

RF3 = importer_version('reparer_fragments', 3, 'reparer_fragments_v3_essai'); OUTIL3 = chemin_version('reparer_fragments', 3)


class SurV3:
    """Rejoue une classe de la suite v2 avec la version 3 (module et exécutable), puis restaure."""
    @classmethod
    def setUpClass(cls):
        cls._sauve = (T2.RF, T2.OUTIL); T2.RF, T2.OUTIL = RF3, OUTIL3

    @classmethod
    def tearDownClass(cls):
        T2.RF, T2.OUTIL = cls._sauve


class ReparerV2SurV3(SurV3, T2.Reparer):
    pass


class ModuleV2SurV3(SurV3, T2.Module):
    pass


class TrouPonctuationPoint(unittest.TestCase):
    def ok(self, avant, apres, ori=None):
        r, raison = RF3.reparer(avant, ori); self.assertIsNone(raison, raison); self.assertEqual(r, apres)

    def test_cas_du_rapport(self):
        self.ok('Le plan est établi dans ses principes ; . Il décrit les étapes et réduit les écarts relevés sur les essais.quatre choix restent à arrêter (§17.1)',
                'Le plan est établi dans ses principes ; quatre choix restent à arrêter (§17.1). Il décrit les étapes et réduit les écarts relevés sur les essais.')

    def test_virgule_et_deux_points(self):
        self.ok('La correction est faite, . Elle tient.sans perte', 'La correction est faite, sans perte. Elle tient.')
        self.ok('Trois cas sont retenus : . Le reste est écarté.les séries A et B', 'Trois cas sont retenus : les séries A et B. Le reste est écarté.')

    def test_pas_de_faux_trou(self):
        self.assertEqual(RF3.trous('Une liste ; puis la suite. Fin.'), [])
        self.assertEqual(RF3.reparer('Un trou ; . ancien.Fragment', ori='Un trou ; . ancien.')[1], 'aucun trou')   # déjà dans l'origine

    def test_v2_ne_le_voyait_pas(self):
        self.assertEqual(T2.RF.reparer('Établi ; . Il décrit.quatre choix')[1] if T2.RF is not RF3 else 'aucun trou', 'aucun trou')


if __name__ == '__main__':
    unittest.main()
