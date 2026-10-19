"""Tests unitaires de detecter_noms_v2 (première suite de l'outil) : non-régression des comportements principaux
(empreintes sans casse ni accents, texte des docx et xlsx, parcours des dossiers, exclusions, sortie JSON sans écrasement,
code de sortie, aucun nom affiché) ; registre central des dossiers : empreintes lues et événement écrit dans les dossiers
renommés d'un espace fictif. Noms fictifs uniquement."""
import os, io, sys, json, glob, zipfile, unittest, contextlib
from unittest import mock
from aide_tests_v2 import dossier_essai, importer_version, chemin, RACINE_CC
import cc_lib_v4 as L4
D = importer_version('detecter_noms', 2)
RENOMMES = dict(regles='consignes_renommees', journal='trace_renommee')


def lire(f):
    with open(f, encoding='utf-8') as g: return g.read()


def ecrire(f, contenu):
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, 'x', encoding='utf-8') as g: g.write(contenu if isinstance(contenu, str) else json.dumps(contenu))


def zip_xml(f, nom, texte):
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with zipfile.ZipFile(f, 'x') as z: z.writestr(nom, f'<?xml version="1.0" encoding="UTF-8"?><r><t>{texte}</t></r>')


@contextlib.contextmanager
def espace(nom, renommer=None):
    """Espace fictif (registre des dossiers facultatif, empreintes protégées) pris pour racine le temps du test ;
    l'outil y est chargé à neuf, et calcule donc sa racine comme d'habitude. Documents à examiner : <racine>/docs/."""
    r = dossier_essai(nom)
    if renommer: ecrire(chemin('outils', '_gestion', 'chemins_v1.json', racine=r), dict(chemins=renommer))
    ecrire(chemin('regles', 'noms_proteges_v1.json', racine=r), dict(empreintes=sorted({D.emp('Alice'), D.emp('Exemple')})))
    docs = os.path.join(r, 'docs')
    ecrire(os.path.join(docs, 'releve_v1.md'), 'Relu par Alice Exemple.')
    ecrire(os.path.join(docs, 'neutre_v1.txt'), 'Rien à signaler.')
    ecrire(os.path.join(docs, 'image.bin'), 'Alice')                          # extension non lue
    ecrire(os.path.join(docs, '__pycache__', 'cache_v1.md'), 'Alice')        # dossier ignoré
    ecrire(os.path.join(docs, 'sous', '.config', 'reglage_v1.md'), 'Alice')  # dossier ignoré
    with mock.patch.object(L4, 'RACINE_CC', r):
        yield r, docs, importer_version('detecter_noms', 2, alias='detecter_noms_v2_espace')


def lancer(m, *args):
    sortie = io.StringIO()
    with mock.patch.object(sys, 'argv', ['detecter_noms_v2.py', *args]), contextlib.redirect_stdout(sortie): code = m.main()
    return code, sortie.getvalue()


class Empreintes(unittest.TestCase):
    def test_insensible_casse_et_accents(self):
        self.assertEqual(D.emp('ÉXEMPLE'), D.emp('exemple')); self.assertNotEqual(D.emp('Alice'), D.emp('Exemple'))

    def test_racine_calculee_comme_avant(self):
        self.assertEqual(D.CC, RACINE_CC)


class Texte(unittest.TestCase):
    def test_docx_et_xlsx(self):
        d = dossier_essai('detecter_noms_texte')
        zip_xml(os.path.join(d, 'rapport_v1.docx'), 'word/document.xml', 'Alice Exemple')
        zip_xml(os.path.join(d, 'tableau_v1.xlsx'), 'xl/sharedStrings.xml', 'Exemple')
        self.assertIn('Alice Exemple', D.texte(os.path.join(d, 'rapport_v1.docx')))
        self.assertIn('Exemple', D.texte(os.path.join(d, 'tableau_v1.xlsx')))

    def test_zip_illisible_donne_texte_vide(self):
        d = dossier_essai('detecter_noms_illisible'); f = os.path.join(d, 'casse_v1.docx'); ecrire(f, 'pas un zip')
        self.assertEqual(D.texte(f), '')


class Detection(unittest.TestCase):
    def test_dossier_parcouru_noms_comptes_jamais_affiches(self):
        with espace('detecter_noms_dossier') as (r, docs, m):
            code, out = lancer(m, docs)
            self.assertEqual(code, 1)
            self.assertIn(f'    2  {os.path.join(docs, "releve_v1.md")}', out)
            self.assertIn('1 fichier(s) avec des noms protégés sur 2 examinés', out)
            self.assertNotIn('Alice', out); self.assertNotIn('Exemple', out)

    def test_aucun_nom_code_zero(self):
        with espace('detecter_noms_aucun') as (r, docs, m):
            code, out = lancer(m, os.path.join(docs, 'neutre_v1.txt'))
            self.assertEqual(code, 0); self.assertIn('0 fichier(s) avec des noms protégés sur 1 examinés', out)

    def test_exclure(self):
        with espace('detecter_noms_exclure') as (r, docs, m):
            self.assertEqual(lancer(m, docs, '--exclure', '*releve_v1.md')[0], 0)

    def test_sortie_json_sans_ecrasement(self):
        with espace('detecter_noms_json') as (r, docs, m):
            j = os.path.join(r, 'constats_v1.json')
            lancer(m, docs, '--json', j)
            self.assertEqual(json.loads(lire(j)), {os.path.join(docs, 'releve_v1.md'): 2})
            with self.assertRaises(FileExistsError): lancer(m, docs, '--json', j)

    def test_evenement_dans_le_journal_par_defaut(self):
        with espace('detecter_noms_journal') as (r, docs, m):
            lancer(m, docs)
            ev = glob.glob(chemin('journal', '*', '*_detecter_noms_v2_*.json', racine=r))
            self.assertEqual(len(ev), 1)
            self.assertEqual(json.loads(lire(ev[0]))['donnees']['fichiers_avec_noms'], 1)


class Registre(unittest.TestCase):
    def test_regles_et_journal_renommes(self):
        with espace('detecter_noms_registre', RENOMMES) as (r, docs, m):
            self.assertEqual(m.CC, r)
            code, out = lancer(m, docs)                                          # empreintes lues dans le dossier renommé
            self.assertEqual(code, 1); self.assertIn('1 fichier(s) avec des noms protégés sur 2 examinés', out)
            ev = glob.glob(chemin('journal', '*', '*_detecter_noms_v2_*.json', racine=r))
            self.assertEqual(len(ev), 1)                                          # événement écrit dans le journal renommé
            self.assertTrue(ev[0].startswith(os.path.join(r, 'trace_renommee') + os.sep))
            dossiers = sorted(d for d in os.listdir(r) if os.path.isdir(os.path.join(r, d)))
            self.assertEqual(dossiers, sorted(['consignes_renommees', 'trace_renommee', 'docs', os.path.basename(chemin('outils', racine=r))]))


if __name__ == '__main__':
    unittest.main()
