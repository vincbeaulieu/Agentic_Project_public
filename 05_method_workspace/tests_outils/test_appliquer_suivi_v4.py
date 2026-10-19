"""Tests de appliquer_suivi_v4. (a) Non-régression : la suite v3 (qui rejoue v1 et v2) est rejouée sur la version 4.
(b) Correction de la v4 (18 oct. 2026) : une rangée insérée juste après l'en-tête d'un tableau copiait l'en-tête (gras, ligne
d'en-tête répétée) ; avec « modele », elle copie la rangée désignée et reste placée après « apres ». Le défaut est d'abord prouvé
présent sur la v3 (LC-032) : sans rangée modèle, la rangée insérée porte w:b et w:tblHeader."""
import os, sys, zipfile, subprocess, unittest
from aide_tests_v2 import dossier_essai, chemin_version, importer_version, OUTILS
import test_appliquer_suivi_v1 as T1
import test_appliquer_suivi_v2 as T2
import test_appliquer_suivi_v3 as T3

AS4 = importer_version('appliquer_suivi', 4, 'appliquer_suivi_v4_essai'); OUTIL4 = chemin_version('appliquer_suivi', 4)
OUTIL3 = chemin_version('appliquer_suivi', 3)


class SurV4:
    @classmethod
    def setUpClass(cls):
        cls._sauve = (T1.AS, T1.OUTIL, T2.AS2, T2.OUTIL2, T3.OUTIL3)
        T1.AS, T1.OUTIL, T2.AS2, T2.OUTIL2, T3.OUTIL3 = AS4, OUTIL4, AS4, OUTIL4, OUTIL4

    @classmethod
    def tearDownClass(cls):
        T1.AS, T1.OUTIL, T2.AS2, T2.OUTIL2, T3.OUTIL3 = cls._sauve


class RemplacementSurV4(SurV4, T1.RemplacementTolerant):
    pass


class LigneSurV4(SurV4, T1.LigneDeCommande):
    def test_sans_argument_message_usage(self): pass


class UsageSurV4(SurV4, T2.Corrige):
    def test_entete_a_jour(self):
        with open(OUTIL4, encoding='utf-8') as f: s = f.read()
        self.assertIn('VERSION: 4\n', s); self.assertIn('BANC: tests/test_appliquer_suivi_v4.py\n', s); self.assertNotIn('À DÉCRIRE', s)
        self.assertIn('USAGE: python3 appliquer_suivi_v4.py ', s)


class SansCommentairesSurV4(SurV4, T3.SansCommentaires):
    def test_defaut_present_en_v2(self): pass     # prouvé par la suite v3


WN, W14 = T1.WN, T1.W14
NS = f'xmlns:w="{WN}" xmlns:w14="{W14}"'
def cellule(pid, texte, gras=False):
    b = '<w:b/>' if gras else ''
    return f'<w:tc><w:p w14:paraId="{pid}"><w:r><w:rPr>{b}<w:sz w:val="20"/></w:rPr><w:t>{texte}</w:t></w:r></w:p></w:tc>'
TABLEAU = ('<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/></w:tblPr><w:tblGrid><w:gridCol w:w="2000"/><w:gridCol w:w="3000"/></w:tblGrid>'
           '<w:tr><w:trPr><w:tblHeader/></w:trPr>' + cellule('0000A001', 'Terme', True) + cellule('0000A002', 'Définition', True) + '</w:tr>'
           '<w:tr>' + cellule('0000B001', 'Bruit') + cellule('0000B002', 'Définition du bruit') + '</w:tr></w:tbl>')
def module(modele):
    m = f", modele='0000B001'" if modele else ''
    return f"OPS = [dict(id='L-1', type='inserer_ligne', apres='0000A001', textes=['Arbre', 'Définition de l’arbre'], cle='l1'{m})]\n"


def lancer(outil, nom, modele):
    d = dossier_essai('appliquer_suivi4_' + nom)
    with zipfile.ZipFile(os.path.join(d, 'entree_v1.docx'), 'w') as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr('word/document.xml', f'<w:document {NS}><w:body><w:p w14:paraId="0000000A"><w:bookmarkStart w:id="0" w:name="r"/><w:bookmarkEnd w:id="0"/>'
                                        f'<w:r><w:t>Glossaire</w:t></w:r></w:p>{TABLEAU}<w:p w14:paraId="0000000B"><w:r><w:t>Fin.</w:t></w:r></w:p></w:body></w:document>')
    with open(os.path.join(d, f'ops_{nom}.py'), 'w', encoding='utf-8') as g: g.write(module(modele))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS, d]))
    r = subprocess.run([sys.executable, outil, f'ops_{nom}', os.path.join(d, 'entree_v1.docx'), os.path.join(d, 'sortie_v1.docx'),
                        os.path.join(d, 'journal_v1.json'), '--auteur', 'Collègue B', '--initiales', 'CB'], capture_output=True, text=True, env=env, timeout=120)
    return r, d


def rangees(d):
    from lxml import etree
    root = etree.fromstring(zipfile.ZipFile(os.path.join(d, 'sortie_v1.docx')).read('word/document.xml'))
    out = []
    for tr in root.iter('{%s}tr' % WN):
        t = ''.join(x.text or '' for x in tr.iter('{%s}t' % WN))
        out.append((t, tr.find('.//{%s}tblHeader' % WN) is not None, tr.find('.//{%s}b' % WN) is not None))
    return out


class RangeeModele(unittest.TestCase):
    def test_defaut_present_en_v3(self):
        r, d = lancer(OUTIL3, 'v3', modele=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        R = rangees(d)
        self.assertEqual(R[1][0], 'ArbreDéfinition de l’arbre')
        self.assertTrue(R[1][1] and R[1][2], 'le défaut doit être présent : la rangée insérée copie l’en-tête')

    def test_modele_copie_la_rangee_designee(self):
        r, d = lancer(OUTIL4, 'v4', modele=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        R = rangees(d)
        self.assertEqual([x[0] for x in R], ['TermeDéfinition', 'ArbreDéfinition de l’arbre', 'BruitDéfinition du bruit'])
        self.assertFalse(R[1][1]); self.assertFalse(R[1][2])
        doc = zipfile.ZipFile(os.path.join(d, 'sortie_v1.docx')).read('word/document.xml').decode('utf-8')
        self.assertIn('w:author="Collègue B"', doc)

    def test_sans_modele_comportement_v3(self):
        r, d = lancer(OUTIL4, 'v4_sans', modele=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(rangees(d)[1][1])


if __name__ == '__main__':
    unittest.main()
