"""Tests de auditer_espace_v4 : non-régression (suites v2 et v3 rejouées sur la v4) ; registre central des chemins : dans un
espace fictif dont le registre renomme les dossiers des tests, des revues et du journal, l'audit lit les tests et écrit ses
revues dans les dossiers renommés, n'en recrée aucun sous l'ancien nom, et exclut de l'arbre le journal renommé."""
import os, json, glob, unittest
import test_auditer_espace_v2 as T2
import test_auditer_espace_v3 as T3
from aide_tests_v2 import chemin_version, importer_version

SRC4 = chemin_version('auditer_espace', 4); AE4 = importer_version('auditer_espace', 4)


class SurV4:
    @classmethod
    def setUpClass(cls): cls._sauve = (T2.SRC, T2.AE); T2.SRC, T2.AE = SRC4, AE4

    @classmethod
    def tearDownClass(cls): T2.SRC, T2.AE = cls._sauve


class FonctionsV4(SurV4, T2.Fonctions): pass
class AuditsSuccessifsV4(SurV4, T2.AuditsSuccessifs): pass
class NouveautesV3SurV4(SurV4, T3.Nouveautes): pass


class Registre(SurV4, unittest.TestCase):
    def test_dossiers_renommes(self):
        R, outil, _ = T2.espace('audit_v4_registre'); cc = os.path.join(R, '00_competences_claude')
        os.rename(os.path.join(cc, 'tests'), os.path.join(cc, 'tests_des_outils'))
        os.makedirs(os.path.join(cc, 'journal_des_evenements', '2026-10-15'))
        T2.w(os.path.join(cc, 'journal_des_evenements', '2026-10-15', 'evt.json'), '{}')
        T2.w(os.path.join(cc, 'outils', '_gestion', 'chemins_v1.json'),
             json.dumps(dict(chemins=dict(tests='tests_des_outils', revues='revues_des_audits', journal='journal_des_evenements'))))
        rev = os.path.join(cc, 'revues_des_audits')
        c, s, J = T2.auditer(R, outil, rev); self.assertEqual(c, 0, s)
        self.assertFalse(os.path.exists(os.path.join(cc, 'revues')))
        self.assertFalse(os.path.exists(os.path.join(cc, 'tests')))
        self.assertNotIn('A06', [k for k, _ in T2.codes(J, '00_competences_claude/outils/x')])        # test trouvé dans le dossier renommé
        self.assertFalse(any('journal_des_evenements' in p for p in J['arbre']['ajoutes']))          # journal exclu de l'arbre
        self.assertTrue(glob.glob(os.path.join(rev, 'etat', 'etat_audit_essai_*.json')))


if __name__ == '__main__':
    unittest.main()
