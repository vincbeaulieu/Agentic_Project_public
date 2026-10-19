"""Tests de livrer_v8. (a) Non-régression : la suite de livrer_v7 (qui rejoue celles des v4 à v6) est rejouée sur la v8.
(b) Corrections de la v8 (18 oct. 2026) :
 - le statut « document annexe » (contrôle des noms protégés) suit le nom de livrable demandé, et non le nom du fichier d'entrée :
   le rapport révisé remis depuis un fichier d'essai était traité en annexe, donc refusé pour les noms d'origine qu'il contient ;
   le défaut est d'abord prouvé présent sur la v7 (LC-032) ;
 - pages et images regardées déclarables par livrable (« Nom=1,2;Nom2=3 ») : un rapport et son journal, de longueurs différentes,
   se remettent ensemble ; une page déclarée pour l'un n'est pas exigée de l'autre."""
import os, sys, subprocess, unittest
from aide_tests_v2 import chemin_version
import test_livrer_v6 as T6
import test_livrer_v7 as T7

LIVRER8 = chemin_version('livrer', 8); LIVRER7 = chemin_version('livrer', 7)
T6.LIVRER = LIVRER8
PorteDocxV8, FicheTravailV8, NomAvecPointV8, TexteV8, VersionRevV8 = T6.PorteDocx, T6.FicheTravail, T6.NomAvecPoint, T6.Texte, T7.VersionRev


def fiches(d):
    P = os.path.join(d, '95_journal', 'portes')
    out = {}
    for f in sorted(x for x in os.listdir(P) if x.endswith('.md')):
        with open(os.path.join(P, f), encoding='utf-8') as g: out[f] = g.read()
    return out


class AnnexeSelonLeNomDemande(unittest.TestCase):
    """Source « Rapport_v1.0.0.docx » ; le livrable « Rapport » est remis depuis un fichier d'essai « essai_fin_v1.docx »."""
    def preparer(self, nom):
        d = T6.dossier(nom); e = os.path.join(d, '01_etape')
        return d, T6.docx(e, 'Rapport_reference_v1.docx'), T6.docx(e, 'essai_fin_v1.docx')

    def test_defaut_present_en_v7(self):
        d, ref, f = self.preparer('livrer8_annexe_v7')
        r = subprocess.run([sys.executable, LIVRER7, d, f + ':Rapport', '--sans-evaluation', '--reference', ref, '--porte-seule'], capture_output=True, text=True, timeout=600)
        self.assertIn('document annexe', r.stdout + r.stderr, 'le défaut doit être présent : le rapport est traité en annexe')

    def test_rapport_pas_annexe(self):
        d, ref, f = self.preparer('livrer8_annexe')
        c, s = T6.lancer(d, f + ':Rapport', '--sans-evaluation', '--reference', ref, '--pages-vues', '1')
        self.assertEqual(c, 0, s); self.assertNotIn('document annexe', s)
        self.assertEqual(T6.remis(d), ['Rapport_v2.0.0.docx', 'empreintes_livrables_v2.0.0.txt'])

    def test_autre_livrable_reste_annexe(self):
        d, ref, f = self.preparer('livrer8_annexe_journal')
        c, s = T6.lancer(d, f + ':Journal', '--sans-evaluation', '--reference', ref, '--pages-vues', '1')
        self.assertEqual(c, 0, s); self.assertIn('document annexe', s)


class PagesParLivrable(unittest.TestCase):
    def test_pages_par_livrable(self):
        d = T6.dossier('livrer8_pages'); e = os.path.join(d, '01_etape')
        ref = T6.docx(e, 'Rapport_reference_v1.docx'); a = T6.docx(e, 'A_v1.docx'); b = T6.docx(e, 'B_v1.docx')
        c, s = T6.lancer(d, a + ':Rapport', b + ':Journal', '--sans-evaluation', '--reference', ref, '--pages-vues', 'Rapport=1;Journal=1')
        self.assertEqual(c, 0, s); self.assertEqual(T6.remis(d), ['Journal_v2.0.0.docx', 'Rapport_v2.0.0.docx', 'empreintes_livrables_v2.0.0.txt'])

    def test_livrable_sans_pages_declarees_refuse(self):
        d = T6.dossier('livrer8_pages_manque'); e = os.path.join(d, '01_etape')
        ref = T6.docx(e, 'Rapport_reference_v1.docx'); a = T6.docx(e, 'A_v1.docx'); b = T6.docx(e, 'B_v1.docx')
        c, s = T6.lancer(d, a + ':Rapport', b + ':Journal', '--sans-evaluation', '--reference', ref, '--pages-vues', 'Rapport=1')
        self.assertNotEqual(c, 0, s); self.assertEqual(T6.remis(d), [])

    def test_page_hors_document_refusee(self):
        d = T6.dossier('livrer8_pages_hors'); e = os.path.join(d, '01_etape')
        ref = T6.docx(e, 'Rapport_reference_v1.docx'); a = T6.docx(e, 'A_v1.docx')
        c, s = T6.lancer(d, a + ':Rapport', '--sans-evaluation', '--reference', ref, '--pages-vues', 'Rapport=1,9')
        self.assertNotEqual(c, 0, s); self.assertEqual(T6.remis(d), [])


if __name__ == '__main__':
    unittest.main()
