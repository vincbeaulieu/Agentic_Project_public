"""Tests de evaluer_travail_v8. (a) Non-régression : suites v7, v6 et v5 rejouées sur la version 8. (b) Correction : D3 « refus de la passe =
source » s'appuie sur docx_couches_v3, qui refuse aussi les modifications de mise en forme suivies (w:rPrChange, w:pPrChange) : une passe
de harmoniser_mise_en_forme v2 n'est plus déclarée non conforme à tort, et une vraie différence (texte changé hors révision) reste
signalée ; la constante VERSION interne vaut 8."""
import os, json, shutil, unittest
from aide_tests_v2 import dossier_essai, chemin_version, importer_version
import test_evaluer_travail_v5 as T5
import test_evaluer_travail_v6 as T6
import test_evaluer_travail_v7 as T7
import test_controler_mise_en_forme_v2 as TC

EVAL8 = chemin_version('evaluer_travail', 8)


class SurV8:
    @classmethod
    def setUpClass(cls): cls._s = (T5.EVAL, T7.EVAL7); T5.EVAL = EVAL8; T7.EVAL7 = EVAL8

    @classmethod
    def tearDownClass(cls): T5.EVAL, T7.EVAL7 = cls._s


class N3SurV8(SurV8, T5.N3): pass
class TemoinsSurV8(SurV8, T6.Temoins): pass
class AnnexeSurV8(SurV8, T7.DocumentAnnexe): pass


class MiseEnForme(SurV8, unittest.TestCase):
    def dossier(self, alterer=False):
        HM = importer_version('harmoniser_mise_en_forme', 2, 'harmoniser_v2_pour_eval8')
        p, run, ins, dele = TC.p, TC.run, TC.ins, TC.dele
        corps = (p(run('Avant.')) + p() + p(run('1 Contexte', None), 'Heading1') + p(run('Corps ') + ins('ajout'))
                 + p(dele('Paragraphe supprimé.'), marque_sup='Collègue A') + p(run('2 Méthode', None), 'Heading1'))
        d = T5.CAS._conforme(dossier_essai('eval8_mise_en_forme'))
        for f in os.listdir(d):
            if f.startswith('TRAVAIL_'): os.remove(os.path.join(d, f))
        T5.CAS._ecrire(d, 'TRAVAIL_v1.json', json.dumps(dict(sujet='essai', source='00_sources/Rapport_v1.0.0.docx', auteur_revisions='Harmonisation - Claude',
                                                             version_cible='2.0.0', couverture=None, auteurs_relecteurs=[])))
        src = TC.docx(os.path.join(d, '00_sources'), 'Rapport_v1.0.0.docx', corps)
        out = os.path.join(d, '98_livrables', 'Rapport_v2.0.0.docx'); self.assertEqual(HM.main([src, out]), 0)
        if alterer:                                                       # texte changé hors révision : le refus ne redonne pas la source
            import zipfile
            z = zipfile.ZipFile(out); parts = {n: z.read(n) for n in z.namelist()}; z.close()
            parts['word/document.xml'] = parts['word/document.xml'].replace('Corps '.encode(), 'Texte '.encode(), 1)
            os.remove(out)
            with zipfile.ZipFile(out, 'w') as zo:
                for n, b in parts.items(): zo.writestr(n, b)
        shutil.copy2(out, os.path.join(d, '99_livrables_modifiables', 'Rapport_v2.0.0.docx'))
        return d

    def d3(self, d):
        j = os.path.join(os.path.dirname(d), f'constats_{os.path.basename(d)}.json')
        T5.lancer(EVAL8, d, '--sans-xsd', '--sans-manifeste', '--json', j)
        with open(j, encoding='utf-8') as g: return [k for k in json.load(g)['constats'] if k['regle'] == 'D3']

    def test_passe_de_mise_en_forme_conforme(self):
        self.assertEqual(self.d3(self.dossier()), [])

    def test_vraie_difference_signalee(self):
        self.assertTrue(self.d3(self.dossier(alterer=True)))

    def test_version_interne(self):
        with open(EVAL8, encoding='utf-8') as g: s = g.read()
        self.assertIn("OUTIL, VERSION = 'evaluer_travail', 8", s); self.assertIn('import docx_couches_v3 as dc', s); self.assertNotIn('À DÉCRIRE', s)


if __name__ == '__main__':
    unittest.main()
