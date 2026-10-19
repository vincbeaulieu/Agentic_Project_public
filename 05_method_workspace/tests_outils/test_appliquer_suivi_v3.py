"""Tests de appliquer_suivi_v3. (a) Non-régression : les suites v1 et v2 (remplacement tolérant, ligne de commande nominale, révision
d'un autre auteur préservée, échecs explicites « ÉCHEC <id> », sortie existante non écrasée, message d'usage) sont rejouées sur la
version 3. (b) Correction de la v3 (18 oct. 2026) : un document sans aucune partie de commentaires (cas de la v6.0.12-rev1 du rapport)
est traité ; la v2, fondée sur moteur_revision_multi_v1, échouait (KeyError word/comments.xml) : le défaut est d'abord prouvé présent
sur la v2 (LC-032), puis absent sur la v3."""
import os, sys, zipfile, subprocess, unittest
from aide_tests_v2 import dossier_essai, chemin_version, importer_version, OUTILS
import test_appliquer_suivi_v1 as T1
import test_appliquer_suivi_v2 as T2

AS3 = importer_version('appliquer_suivi', 3, 'appliquer_suivi_v3_essai'); OUTIL3 = chemin_version('appliquer_suivi', 3)
OUTIL2 = chemin_version('appliquer_suivi', 2)


class SurV3:
    """Rejoue une classe des suites v1 et v2 avec la version 3, puis restaure."""
    @classmethod
    def setUpClass(cls):
        cls._sauve = (T1.AS, T1.OUTIL, T2.AS2, T2.OUTIL2)
        T1.AS, T1.OUTIL, T2.AS2, T2.OUTIL2 = AS3, OUTIL3, AS3, OUTIL3

    @classmethod
    def tearDownClass(cls):
        T1.AS, T1.OUTIL, T2.AS2, T2.OUTIL2 = cls._sauve


class RemplacementSurV3(SurV3, T1.RemplacementTolerant):
    pass


class LigneSurV3(SurV3, T1.LigneDeCommande):
    def test_sans_argument_message_usage(self): pass   # couvert par UsageSurV3


class UsageSurV3(SurV3, T2.Corrige):
    def test_entete_a_jour(self):
        with open(OUTIL3, encoding='utf-8') as f: s = f.read()
        self.assertIn('VERSION: 3\n', s); self.assertIn('BANC: tests/test_appliquer_suivi_v3.py\n', s); self.assertNotIn('À DÉCRIRE', s)
        self.assertIn('USAGE: python3 appliquer_suivi_v3.py ', s); self.assertIn('moteur_revision_multi_v5', s)


WN, W14 = T1.WN, T1.W14
NS = f'xmlns:w="{WN}" xmlns:w14="{W14}"'
MODULE = ("OPS = [dict(id='E-1', type='remplacer', cible='0000000A', couples=[('Le chat dort.', 'Le chat joue.')])]\n")


def ecrire_sans_commentaires(f):
    with zipfile.ZipFile(f, 'w') as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr('word/document.xml', f'<w:document {NS}><w:body><w:p w14:paraId="0000000A"><w:bookmarkStart w:id="0" w:name="repere"/><w:bookmarkEnd w:id="0"/>'
                                        '<w:r><w:t xml:space="preserve">Le chat dort.</w:t></w:r></w:p>'
                                        '<w:p w14:paraId="0000000B"><w:r><w:t>Fin.</w:t></w:r></w:p></w:body></w:document>')


def lancer(outil, nom):
    d = dossier_essai('appliquer_suivi3_' + nom); ecrire_sans_commentaires(os.path.join(d, 'entree_v1.docx'))
    with open(os.path.join(d, f'ops_{nom}.py'), 'w', encoding='utf-8') as g: g.write(MODULE)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS, d]))
    r = subprocess.run([sys.executable, outil, f'ops_{nom}', os.path.join(d, 'entree_v1.docx'), os.path.join(d, 'sortie_v1.docx'),
                        os.path.join(d, 'journal_v1.json'), '--auteur', 'Collègue B', '--initiales', 'CB'],
                       capture_output=True, text=True, env=env, timeout=120)
    return r, d


class SansCommentaires(unittest.TestCase):
    def test_defaut_present_en_v2(self):
        r, d = lancer(OUTIL2, 'v2')
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("no item named 'word/comments.xml'", r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(d, 'sortie_v1.docx')))

    def test_document_sans_commentaires_traite(self):
        r, d = lancer(OUTIL3, 'v3')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        doc = zipfile.ZipFile(os.path.join(d, 'sortie_v1.docx')).read('word/document.xml').decode('utf-8')
        self.assertIn('w:author="Collègue B"', doc); self.assertIn('joue', doc); self.assertIn('dort', doc)   # dort en w:delText
        self.assertTrue(os.path.exists(os.path.join(d, 'journal_v1.json')))


if __name__ == '__main__':
    unittest.main()
