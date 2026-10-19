"""Tests de evaluer_travail_v6. (a) Non-régression : suite v5 (N3 : version des livrables ; livrer_v3) rejouée sur la version 6.
(b) Ajout : fichiers témoins vides (« .garder », « .gitkeep ») non suivis — aucun N1, E3 ni E4 dans 98_livrables et
99_livrables_modifiables, aucun E5 quand ils disparaissent d'un manifeste ; un « .garder » non vide reste suivi (N1)."""
import os, json, time, unittest
from aide_tests_v2 import dossier_essai, chemin_version
import test_evaluer_travail_v5 as T5

EVAL6 = chemin_version('evaluer_travail', 6)


class SurV6:
    @classmethod
    def setUpClass(cls): cls._sauve = T5.EVAL; T5.EVAL = EVAL6

    @classmethod
    def tearDownClass(cls): T5.EVAL = cls._sauve


class N3SurV6(SurV6, T5.N3):
    pass


class Temoins(SurV6, unittest.TestCase):
    def test_garder_vides_non_suivis(self):
        d = T5.CAS._conforme(dossier_essai('eval6_temoins'))
        for s in ('98_livrables', '99_livrables_modifiables', '01_etape'): T5.CAS._ecrire(d, f'{s}/.garder', '')
        T5.CAS._ecrire(d, '01_etape/.gitkeep', '')
        K, s = T5.constats(d); self.assertEqual(K, set(), s)

    def test_garder_non_vide_suivi(self):
        d = T5.CAS._conforme(dossier_essai('eval6_temoin_plein')); T5.CAS._ecrire(d, '01_etape/.garder', 'contenu')
        K, s = T5.constats(d); self.assertIn(('N1', '01_etape/.garder'), K, s)

    def test_pas_de_E5_quand_un_temoin_disparait(self):
        d = T5.CAS._conforme(dossier_essai('eval6_e5')); T5.CAS._ecrire(d, '98_livrables/.garder', '')
        j = os.path.join(os.path.dirname(d), 'c1.json'); c, s = T5.lancer(EVAL6, d, '--sans-xsd', '--json', j)       # écrit un manifeste
        man = [f for f in os.listdir(os.path.join(d, '95_journal', 'manifestes'))]; self.assertTrue(man, s)
        M = json.load(open(os.path.join(d, '95_journal', 'manifestes', sorted(man)[-1]), encoding='utf-8'))['fichiers']
        M['98_livrables/.garder'] = ['e3b0c44298fc1c14', 0]                                                        # manifeste ancien qui le listait
        f = os.path.join(d, '95_journal', 'manifestes', 'manifeste_20990101_000000.json')
        with open(f, 'w', encoding='utf-8') as g: json.dump(dict(fichiers=M), g)
        os.remove(os.path.join(d, '98_livrables', '.garder')); time.sleep(1.1)       # manifestes horodatés à la seconde
        j2 = os.path.join(os.path.dirname(d), 'c2.json'); c, s = T5.lancer(EVAL6, d, '--sans-xsd', '--json', j2); self.assertTrue(os.path.exists(j2), s)
        K = {(k['regle'], k['chemin']) for k in json.load(open(j2, encoding='utf-8'))['constats']}
        self.assertNotIn(('E5', '98_livrables/.garder'), K)


if __name__ == '__main__':
    unittest.main()
