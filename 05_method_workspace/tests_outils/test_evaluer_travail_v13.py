"""Tests de evaluer_travail_v13. (a) Non-régression : suite v12 rejouée sur la version 13 (et, par elle, les suites antérieures).
(b) Correction de la v13 (18 oct. 2026) : les artefacts que livrer écrit dans 95_journal/portes/porte_<Nom>_<horodatage>/ (pages rendues,
paquets XSD, format_v1.json et rendu_v1.json d'une porte à l'autre) ne sont plus jugés comme des fichiers de travail (N1, N2, N5) ; la
fiche porte_<Nom>_<horodatage>.md et tout autre fichier sans version restent signalés. Défaut prouvé d'abord présent sur la v12 (LC-032)."""
import os, sys, json, subprocess, unittest
from aide_tests_v2 import chemin_version, dossier_essai, chemin
import importlib.util
import test_evaluer_travail_v12 as T12

EVAL13 = chemin_version('evaluer_travail', 13); EVAL12 = chemin_version('evaluer_travail', 12)
spec = importlib.util.spec_from_file_location('cas_evaluer13', chemin('bancs', 'evaluer_travail', 'cas_v1.py'))
CAS = importlib.util.module_from_spec(spec); spec.loader.exec_module(CAS)


class SurV13:
    @classmethod
    def setUpClass(cls):
        T11 = T12.T11
        cls._s13 = (T12.EVAL12, T11.EVAL11, T11.T10.EVAL10, T11.T9.EVAL9, T11.T9.T5.EVAL, T11.T9.T7.EVAL7, T11.T9.T8.EVAL8)
        T12.EVAL12 = T11.EVAL11 = T11.T10.EVAL10 = T11.T9.EVAL9 = T11.T9.T5.EVAL = T11.T9.T7.EVAL7 = T11.T9.T8.EVAL8 = EVAL13

    @classmethod
    def tearDownClass(cls):
        T11 = T12.T11
        T12.EVAL12, T11.EVAL11, T11.T10.EVAL10, T11.T9.EVAL9, T11.T9.T5.EVAL, T11.T9.T7.EVAL7, T11.T9.T8.EVAL8 = cls._s13


class N3SurV13(SurV13, T12.N3SurV12): pass
class TemoinsSurV13(SurV13, T12.TemoinsSurV12): pass
class AnnexeSurV13(SurV13, T12.AnnexeSurV12): pass
class MiseEnFormeSurV13(SurV13, T12.MiseEnFormeSurV12): pass
class AcceptationSurV13(SurV13, T12.AcceptationSurV12):
    def test_version_interne(self): self.assertIn("OUTIL, VERSION = 'evaluer_travail', 13", open(EVAL13, encoding='utf-8').read())
class ReferenceSurV13(SurV13, T12.ReferenceSurV12): pass
class DeplacementSurV13(SurV13, T12.DeplacementSurV12):
    def test_passe_avec_deplacement_conforme(self): self.assertEqual(self.d3(EVAL13, self.dossier()), [])


def evaluer(outil, d):
    j = os.path.join(os.path.dirname(d), os.path.basename(d) + '_eval.json')
    if os.path.exists(j): os.remove(j)
    r = subprocess.run([sys.executable, outil, d, '--sans-xsd', '--sans-manifeste', '--json', j], capture_output=True, text=True, timeout=600)
    return {(c['regle'], c.get('chemin') or c.get('fichier')) for c in json.load(open(j))['constats']}, r


class ArtefactsDesPortes(unittest.TestCase):
    def dossier(self, nom):
        d = CAS._conforme(dossier_essai(nom))
        for ts in ('20261018_173147', '20261018_173308'):
            P = f'95_journal/portes/porte_Rapport_{ts}'
            CAS._ecrire(d, P + '.md', '# Porte\n')
            CAS._ecrire(d, P + '/rendu/page-001.png', ts)
            CAS._ecrire(d, P + '/xsd_paquets/Rapport_ab12/[Content_Types].xml', ts)
            CAS._ecrire(d, P + '/format_v1.json', '{"ts": "%s"}' % ts)
        CAS._ecrire(d, '01_analyse/sans_version.txt', 'x\n')      # témoin : un vrai fichier sans version reste signalé
        return d

    def regles(self, C, regle): return sorted(p for r, p in C if r == regle)

    def test_defaut_present_en_v12(self):
        C, r = evaluer(EVAL12, self.dossier('evaluer13_portes_v12'))
        self.assertTrue(any('95_journal/portes/porte_Rapport_20261018_173147/rendu/page-001.png' in (p or '') for p in self.regles(C, 'N1')), r.stdout + r.stderr)
        self.assertTrue(self.regles(C, 'N5'), 'N5 attendu sur format_v1.json en v12')

    def test_artefacts_exemptes_en_v13(self):
        C, r = evaluer(EVAL13, self.dossier('evaluer13_portes'))
        self.assertEqual([p for p in self.regles(C, 'N1') if 'portes' in (p or '')], [], r.stdout)
        self.assertEqual(self.regles(C, 'N2'), []); self.assertEqual(self.regles(C, 'N5'), [])
        self.assertTrue(any('sans_version.txt' in (p or '') for p in self.regles(C, 'N1')), 'le témoin hors porte doit rester signalé')


if __name__ == '__main__':
    unittest.main()
