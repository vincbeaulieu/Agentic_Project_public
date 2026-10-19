"""Tests unitaires de cc_lib (v1 et v2, via les raccourcis de compatibilité) : noms et versions, écriture versionnée sans écrasement, registre au format de organiser_outils (v2 de la suite : le registre a changé de format)."""
import os, json, unittest
from aide_tests_v1 import dossier_essai, OUTILS
import cc_lib_v1 as L
import cc_lib_v2 as L2


class Noms(unittest.TestCase):
    def test_version_est_le_dernier_jeton(self):
        self.assertEqual(L.analyser_nom('plan_v8_fusion_v5.py')['ver'], '5')
        self.assertEqual(L.analyser_nom('microtaches_v6.py')['nom'], 'microtaches')

    def test_semver_et_variante(self):
        d = L.analyser_nom('Rapport_v9.0.0_lecture.docx')
        self.assertEqual((d['ver'], d['variante'], d['forme']), ('9.0.0', 'lecture', 'semver'))

    def test_horodatage(self):
        self.assertEqual(L.analyser_nom('essai_20261015_1200.json')['forme'], 'horodatage')

    def test_sans_version(self):
        self.assertIsNone(L.analyser_nom('LISEZMOI.md'))


class EcritureVersionnee(unittest.TestCase):
    def test_nouvelle_version_seulement_si_changement(self):
        d = dossier_essai('ecrire_versionne')
        p1, c1 = L.ecrire_versionne(d, 'f', 'txt', 'a')
        p2, c2 = L.ecrire_versionne(d, 'f', 'txt', 'a')
        p3, c3 = L.ecrire_versionne(d, 'f', 'txt', 'b')
        self.assertTrue(c1); self.assertFalse(c2); self.assertTrue(c3)
        self.assertEqual(os.path.basename(p3), 'f_v2.txt')
        self.assertEqual(open(p1).read(), 'a')                   # la v1 n'est jamais réécrite

    def test_derniere_version(self):
        d = dossier_essai('derniere_version')
        for c in 'abc': L.ecrire_versionne(d, 'g', 'txt', c)
        self.assertTrue(L.derniere_version(d, 'g', 'txt').endswith('g_v3.txt'))


class Registre(unittest.TestCase):
    def test_courant_et_chemin_existent(self):
        for nom in ('detecteurs_rapport', 'microtaches', 'evaluer_travail'):
            self.assertTrue(os.path.exists(L2.chemin_outil(nom)), nom)

    def test_version_archivee_trouvee(self):
        R = L2.registre()
        arch = [(n, r['archivees'][0]) for n, r in R.items() if r.get('archivees') and 'py' in (r.get('courant') or {})]
        self.assertTrue(arch)
        n, v = arch[0]
        self.assertIn(os.path.join(n, 'archive'), L2.chemin_outil(n, v))

    def test_registre_coherent_avec_les_dossiers(self):
        for n, r in L2.registre().items():
            for f in r['fichiers']: self.assertTrue(os.path.exists(os.path.join(os.path.dirname(OUTILS), f)), f)


if __name__ == '__main__':
    unittest.main()
