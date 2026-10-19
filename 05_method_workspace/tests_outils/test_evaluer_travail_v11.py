"""Tests de evaluer_travail_v11. (a) Non-régression : suite v10 rejouée sur la version 11 (et, par elle, v9, v8…). (b) Correction : une passe
avec déplacements suivis (moteur_revision_multi v3) est jugée sur « refus de la passe = source » avec docx_couches v4 : aucun constat D3 ;
témoin : la v10 (docx_couches v3) signale D3 à tort. La constante VERSION interne vaut 11."""
import os, json, shutil, unittest
from aide_tests_v2 import dossier_essai, chemin_version
import test_evaluer_travail_v10 as T10
import test_evaluer_travail_v9 as T9
import test_moteur_revision_multi_v3 as TM

EVAL11 = chemin_version('evaluer_travail', 11); EVAL10 = chemin_version('evaluer_travail', 10)


class SurV11:
    @classmethod
    def setUpClass(cls):
        cls._s11 = (T10.EVAL10, T9.EVAL9, T9.T5.EVAL, T9.T7.EVAL7, T9.T8.EVAL8)
        T10.EVAL10 = T9.EVAL9 = T9.T5.EVAL = T9.T7.EVAL7 = T9.T8.EVAL8 = EVAL11

    @classmethod
    def tearDownClass(cls): T10.EVAL10, T9.EVAL9, T9.T5.EVAL, T9.T7.EVAL7, T9.T8.EVAL8 = cls._s11


class N3SurV11(SurV11, T10.N3SurV10): pass
class TemoinsSurV11(SurV11, T10.TemoinsSurV10): pass
class AnnexeSurV11(SurV11, T10.AnnexeSurV10): pass
class MiseEnFormeSurV11(SurV11, T10.MiseEnFormeSurV10): pass
class AcceptationSurV11(SurV11, T10.AcceptationSurV10):
    def test_version_interne(self): self.assertIn("OUTIL, VERSION = 'evaluer_travail', 11", open(EVAL11, encoding='utf-8').read())
class ReferenceSurV11(SurV11, T10.ReferenceMiseEnForme): pass


class Deplacement(unittest.TestCase):
    def dossier(self):
        d = T9.T5.CAS._conforme(dossier_essai('eval11_deplacement'))
        for f in os.listdir(d):
            if f.startswith('TRAVAIL_'): os.remove(os.path.join(d, f))
        T9.T5.CAS._ecrire(d, 'TRAVAIL_v1.json', json.dumps(dict(sujet='essai', source='00_sources/Rapport_v1.0.0.docx', auteur_revisions=TM.AUTEUR,
                                                                version_cible='2.0.0', couverture=None, auteurs_relecteurs=[])))
        src = TM.docx_deplacement(os.path.join(d, '00_sources'), 'Rapport_v1.0.0.docx')
        D = TM.M3.DocR(src, author=TM.AUTEUR, init='EC'); D.move_block('000000B2', '000000B2', '000000B3', 'apres')
        out = os.path.join(d, '98_livrables', 'Rapport_v2.0.0.docx'); D.save(out)
        shutil.copy2(out, os.path.join(d, '99_livrables_modifiables', 'Rapport_v2.0.0.docx'))
        return d

    def d3(self, ev, d):
        j = os.path.join(os.path.dirname(d), f'constats_{os.path.basename(d)}_{os.path.basename(ev)}.json')
        T9.T5.lancer(ev, d, '--sans-xsd', '--sans-manifeste', '--json', j)
        with open(j, encoding='utf-8') as g: return [k for k in json.load(g)['constats'] if k['regle'] in ('D2', 'D3', 'D5')]

    def test_passe_avec_deplacement_conforme(self):
        self.assertEqual(self.d3(EVAL11, self.dossier()), [])

    def test_temoin_v10(self):
        self.assertTrue(self.d3(EVAL10, self.dossier()))


if __name__ == '__main__':
    unittest.main()
