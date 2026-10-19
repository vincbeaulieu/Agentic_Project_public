"""Tests de auditer_espace_v3 : non-régression (toute la suite v2 rejouée sur la v3) ; dernier rapport de tests choisi par
l'horodatage de son nom et non par la date du fichier (sur le PC, la sauvegarde date tous les fichiers de la copie) ; tests à
relancer (A25) suivis d'un audit à l'autre jusqu'à un rapport postérieur au changement."""
import os, json, time, datetime, unittest, importlib.util
import test_auditer_espace_v2 as T2
from aide_tests_v1 import chemin_outil

SRC3 = chemin_outil('auditer_espace', 3)
spec = importlib.util.spec_from_file_location('auditer_espace_v3_essai', SRC3); AE3 = importlib.util.module_from_spec(spec); spec.loader.exec_module(AE3)


class SurV3:
    @classmethod
    def setUpClass(cls): cls._sauve = (T2.SRC, T2.AE); T2.SRC, T2.AE = SRC3, AE3

    @classmethod
    def tearDownClass(cls): T2.SRC, T2.AE = cls._sauve


class FonctionsV3(SurV3, T2.Fonctions): pass


class AuditsSuccessifsV3(SurV3, T2.AuditsSuccessifs): pass


class Nouveautes(SurV3, unittest.TestCase):
    def test_rapport_choisi_par_le_nom(self):
        R, outil, rev = T2.espace('audit_v3_nom'); rap = os.path.join(R, '00_competences_claude', 'tests', 'rapports')
        T2.w(os.path.join(rap, 'rapport_tests_20991231_235959.json'), json.dumps(dict(verdict='conforme')))
        T2.w(os.path.join(rap, 'rapport_tests_20200101_000000.json'), json.dumps(dict(verdict='echec', unitaires=dict(echecs=1), fumee=dict(echecs=0))))
        t = time.time(); os.utime(os.path.join(rap, 'rapport_tests_20991231_235959.json'), (t - 100, t - 100))   # le plus récent par le nom, le plus ancien par la date
        c, s, J = T2.auditer(R, outil, rev); self.assertEqual(c, 0, s)
        self.assertNotIn('A16', [k['code'] for k in J['constats']])

    def test_tests_a_relancer_suivis(self):
        R, outil, rev = T2.espace('audit_v3_a25'); cc = os.path.join(R, '00_competences_claude'); y = os.path.join(cc, 'outils', 'y', 'y_v2.py')
        a25 = lambda J: [k for k in J['constats'] if k['code'] == 'A25']
        c, s, J1 = T2.auditer(R, outil, rev); self.assertEqual(a25(J1), []); self.assertIsNone(J1['tests_a_relancer_depuis'])
        T2.w(y, T2.lire(y) + '# modif\n')
        c, s, J2 = T2.auditer(R, outil, rev); self.assertEqual(len(a25(J2)), 1); self.assertEqual(J2['tests_a_relancer_depuis'], J2['date'])
        c, s, J3 = T2.auditer(R, outil, rev)                                                  # rien de changé, aucun rapport : toujours à relancer
        self.assertEqual(len(a25(J3)), 1); self.assertEqual(a25(J3)[0]['depuis'], J2['date']); self.assertEqual(J3['tests_a_relancer_depuis'], J2['date'])
        time.sleep(1.1); ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        T2.w(os.path.join(cc, 'tests', 'rapports', f'rapport_tests_{ts}.json'), json.dumps(dict(verdict='conforme')))
        c, s, J4 = T2.auditer(R, outil, rev)
        self.assertEqual(a25(J4), []); self.assertIsNone(J4['tests_a_relancer_depuis'])
        self.assertIn('A25', [k['code'] for k in J4['resolus']])


if __name__ == '__main__':
    unittest.main()
