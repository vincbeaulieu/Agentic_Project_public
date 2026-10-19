"""Tests unitaires de chercher_outil v3 (registre central des dossiers, cc_lib_v4.chemin).
(a) Non-régression : cas des suites v1 et v2 rejoués contre la v3 ; même catalogue lu, mêmes classements et même sortie
que la v2 tant que le registre réel garde les noms par défaut (la v2 ne connaît qu'eux).
(b) Registre : l'outil, copié dans un espace fictif dont outils/_gestion/chemins_v1.json renomme le catalogue et le journal,
y trouve sa racine par son amorce, lit la dernière version du catalogue renommé (pas le leurre au nom par défaut) et écrit
son événement dans le journal renommé.
Les essais n'écrivent que dans tests/_test_execution/ (dossier_essai) ; aucun nom de dossier de l'espace n'est écrit en dur."""
import os, io, sys, json, glob, shutil, unittest, contextlib, importlib.util
from unittest import mock
sys.dont_write_bytecode = True          # aucun cache .pyc écrit hors de tests/ par les versions essayées
from aide_tests_v2 import dossier_essai, chemin_version, importer_version, chemin, chemins, RACINE_CC
import cc_lib_v1, cc_lib_v4

C3 = importer_version('chercher_outil', 3)
BASE = 'catalogue_outils'               # nom des fichiers du catalogue (<BASE>_vN.json), pas un nom de dossier
RENOMMES = dict(catalogue='renomme_catalogue', journal='renomme_journal')
REGISTRE_DEFAUT = chemins(RACINE_CC) == cc_lib_v4.DEFAUT
REQUETES = [['détecter', 'références', 'renvois', 'rapport'], ['anonymiser', 'noms'], ['entraîner', 'classifieur'],
            ['organiser', 'versions', 'archive'], ['registre', 'versions', 'outils'], ['zzzz']]


def muet(f):
    """Exécute f() et rend ce qu'elle a affiché."""
    s = io.StringIO()
    with contextlib.redirect_stdout(s): f()
    return s.getvalue()


def ecrire_json(f, donnees):
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, 'x', encoding='utf-8') as g: json.dump(donnees, g, ensure_ascii=False)


def fiche(outil, resume):
    return dict(outil=outil, version='1', categorie='essai', resume=resume, usage='', entrees='', sorties='')


class Recherche(unittest.TestCase):
    """Cas de test_chercher_outil_v1, rejoués contre la v3."""
    def premier(self, *q): return C3.chercher(list(q), C3.catalogue())[0][1]['outil']

    def test_besoins_typiques(self):
        self.assertEqual(self.premier('détecter', 'références', 'renvois', 'rapport'), 'detecteurs_rapport')
        self.assertEqual(self.premier('anonymiser', 'noms'), 'anonymiser')
        self.assertIn(self.premier('entraîner', 'classifieur'), ('entrainer_classifieur',))

    def test_rien(self):
        self.assertEqual(C3.chercher(['zzzz'], C3.catalogue()), [])


class Racines(unittest.TestCase):
    """Cas de test_chercher_outil_v2, rejoués contre la v3."""
    def test_racine(self):
        self.assertTrue(C3.racine('anonymisation', 'anonymiser')); self.assertFalse(C3.racine('tests', 'texte'))

    def test_organisation(self):
        self.assertEqual(C3.chercher(['organiser', 'versions', 'archive'], C3.catalogue())[0][1]['outil'], 'organiser_outils')


@unittest.skipUnless(REGISTRE_DEFAUT, 'registre réel non par défaut : la v2 ne le connaît pas')
class MemeResultatQueV2(unittest.TestCase):
    def setUp(self): self.C2 = importer_version('chercher_outil', 2)

    def test_catalogue_et_classements(self):
        cat = C3.catalogue(); self.assertEqual(cat, self.C2.catalogue())
        for q in REQUETES: self.assertEqual(C3.chercher(q, cat), self.C2.chercher(q, cat), q)

    def test_sortie_principale(self):
        for argv in (['anonymiser', 'noms'], ['organiser', 'versions', '--n', '3', '--json'], ['zzzz']):
            e1, e4 = mock.Mock(), mock.Mock()
            with mock.patch.object(sys, 'argv', ['chercher_outil'] + argv), mock.patch.object(cc_lib_v1, 'evenement', e1):
                s2 = muet(self.C2.main)
            with mock.patch.object(sys, 'argv', ['chercher_outil'] + argv), mock.patch.object(cc_lib_v4, 'evenement', e4):
                s3 = muet(C3.main)
            self.assertEqual(s3, s2, argv); e1.assert_called_once(); e4.assert_called_once()
            self.assertEqual(e4.call_args[0][:3], ('chercher_outil', 3, 'recherche'))
            self.assertEqual(e4.call_args[0][3], dict(e1.call_args[0][3]))


class Registre(unittest.TestCase):
    def test_catalogue_et_journal_renommes(self):
        r = dossier_essai('chercher_outil_registre'); outils = {os.path.basename(chemin('outils', racine=r))}
        # leurre au nom par défaut (pas encore de registre), de version plus haute : il ne doit pas être lu
        ecrire_json(chemin('catalogue', f'{BASE}_v9.json', racine=r), [fiche('outil_leurre', 'zyxfictif leurre')])
        leurres = set(os.listdir(r))
        ecrire_json(chemin('outils', '_gestion', 'chemins_v1.json', racine=r), dict(chemins=RENOMMES))
        for k, v in RENOMMES.items(): self.assertEqual(chemin(k, racine=r), os.path.join(r, v))
        ecrire_json(chemin('catalogue', f'{BASE}_v1.json', racine=r), [fiche('outil_ancien', 'zyxfictif ancien')])
        ecrire_json(chemin('catalogue', f'{BASE}_v2.json', racine=r), [fiche('outil_renomme', 'zyxfictif renomme')])
        # outil copié dans l'arbre fictif : son amorce y trouve la racine de l'espace fictif
        dest = chemin('outils', 'chercher_outil', 'candidat', racine=r); os.makedirs(dest)
        f = shutil.copy(chemin_version('chercher_outil', 3), dest)
        s = importlib.util.spec_from_file_location('chercher_outil_v3_copie_essai', f); C = importlib.util.module_from_spec(s)
        with mock.patch.object(sys, 'path', list(sys.path)): s.loader.exec_module(C)
        self.assertEqual(C.RACINE_CC, r)
        self.assertEqual([o['outil'] for o in C.catalogue()], ['outil_renomme'])           # dernière version, dossier renommé
        with mock.patch.object(sys, 'argv', ['chercher_outil', 'zyxfictif', '--json']), mock.patch.object(cc_lib_v4, 'RACINE_CC', r):
            sortie = muet(C.main)
        self.assertEqual([x['outil'] for x in json.loads(sortie)], ['outil_renomme'])
        ev = glob.glob(chemin('journal', '*', '*.json', racine=r)); self.assertEqual(len(ev), 1)
        with open(ev[0], encoding='utf-8') as g: e = json.load(g)
        self.assertEqual((e['outil'], e['version'], e['type']), ('chercher_outil', 3, 'recherche'))
        self.assertEqual((e['donnees']['requete'], e['donnees']['resultats']), ('zyxfictif', 1))
        self.assertEqual(set(os.listdir(r)), outils | leurres | set(RENOMMES.values()))   # journal par défaut jamais créé


class Entete(unittest.TestCase):
    def test_banc_et_remplace(self):
        e = cc_lib_v4.lire_entete(chemin_version('chercher_outil', 3))
        self.assertEqual(e['VERSION'], '3')
        self.assertEqual(e['BANC'], 'tests/' + os.path.basename(__file__))   # chemin logique (clé « tests »), stable si le dossier est renommé
        self.assertTrue(e['REMPLACE'].startswith("chercher_outil_v2 (noms de dossiers de l'espace écrits en dur, remplacés par le registre central cc_lib_v4.chemin) ; v2 : chercher_outil_v1 ("))


if __name__ == '__main__':
    unittest.main()
