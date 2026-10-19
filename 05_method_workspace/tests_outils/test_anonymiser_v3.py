"""Tests unitaires de anonymiser_v3 : non-régression (cas de test_anonymiser_v1 rejoués contre v3, sans l'importer ; nouvelle
version de chaque fichier, sans écrasement) ; élision en majuscule (« D'X » donne « De Collègue A ») ; registre central des
dossiers : règles lues et événement écrit dans les dossiers renommés d'un espace fictif. Noms fictifs uniquement."""
import os, io, sys, json, glob, unittest, contextlib
from unittest import mock
from aide_tests_v2 import dossier_essai, importer_version, chemin, RACINE_CC
import cc_lib_v4 as L4
A = importer_version('anonymiser', 3)
RENOMMES = dict(regles='consignes_renommees', journal='trace_renommee')


def roles():
    return {A.emp('Alice'): 'Collègue A', A.emp('Exemple'): 'Collègue A', A.emp('Bruno'): 'Collègue B', A.emp('Fictif'): 'Collègue B',
            A.emp('Ugo'): 'Utilisateur', A.emp('Essai'): 'Utilisateur'}


def lire(f):
    with open(f, encoding='utf-8') as g: return g.read()


def ecrire(f, contenu):
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, 'x', encoding='utf-8') as g: g.write(contenu if isinstance(contenu, str) else json.dumps(contenu, ensure_ascii=False))


@contextlib.contextmanager
def espace(nom, renommer=None):
    """Espace fictif (registre des dossiers facultatif, règles d'anonymisation) pris pour racine le temps du test ;
    l'outil y est chargé à neuf, et calcule donc sa racine comme d'habitude."""
    r = dossier_essai(nom)
    if renommer: ecrire(chemin('outils', '_gestion', 'chemins_v1.json', racine=r), dict(chemins=renommer))
    ecrire(chemin('regles', 'roles_v1.json', racine=r), dict(roles=roles()))
    ecrire(chemin('regles', 'noms_proteges_v1.json', racine=r), dict(empreintes=sorted(roles())))
    with mock.patch.object(L4, 'RACINE_CC', r):
        yield r, importer_version('anonymiser', 3, alias='anonymiser_v3_espace')


def lancer(m, *fichiers):
    sortie = io.StringIO()
    with mock.patch.object(sys, 'argv', ['anonymiser_v3.py', *fichiers]), contextlib.redirect_stdout(sortie): m.main()
    return sortie.getvalue()


class NonRegression(unittest.TestCase):
    def test_nom_et_prenom_remplaces_par_un_seul_role(self):
        self.assertEqual(A.anonymiser('Relu par Alice Exemple hier.', roles()), 'Relu par Collègue A hier.')

    def test_deux_personnes_deux_roles(self):
        self.assertEqual(A.anonymiser('Alice Exemple et Bruno Fictif', roles()), 'Collègue A et Collègue B')

    def test_elision(self):
        self.assertEqual(A.anonymiser("demande d'Alice", roles()), 'demande de Collègue A')

    def test_elision_gardee_devant_voyelle(self):
        self.assertEqual(A.anonymiser("l'avis d'Ugo Essai", roles()), "l'avis d'Utilisateur")

    def test_insensible_casse_et_accents(self):
        self.assertEqual(A.emp('ÂLÎCE'), A.emp('alice'))

    def test_texte_sans_nom_inchange(self):
        t = 'Le pipeline traite les données.'
        self.assertEqual(A.anonymiser(t, roles()), t)

    def test_racine_calculee_comme_avant(self):
        self.assertEqual(A.CC, RACINE_CC)


class ElisionMajuscule(unittest.TestCase):
    def test_D_majuscule_garde_la_majuscule(self):
        self.assertEqual(A.anonymiser("D'Alice Exemple vient la remarque.", roles()), 'De Collègue A vient la remarque.')

    def test_apostrophe_typographique(self):
        self.assertEqual(A.anonymiser('Avis. D’Alice, rien.', roles()), 'Avis. De Collègue A, rien.')

    def test_D_majuscule_devant_voyelle_reste_elide(self):
        self.assertEqual(A.anonymiser("D'Ugo vient la remarque.", roles()), "D'Utilisateur vient la remarque.")


class Fichiers(unittest.TestCase):
    def test_nouvelle_version_sans_ecrasement(self):
        with espace('anonymiser_fichiers') as (r, m):
            f1 = os.path.join(r, 'note_v1.md'); ecrire(f1, "Relu par Alice Exemple, D'Alice aussi.\n")
            self.assertIn('note_v2.md (reste : 0)', lancer(m, f1))
            f2 = os.path.join(r, 'note_v2.md')
            self.assertEqual(lire(f2), 'Relu par Collègue A, De Collègue A aussi.\n')
            self.assertIn('existe déjà, ignoré', lancer(m, f1))                 # la v2 existe : pas d'écrasement
            self.assertEqual(lire(f2), 'Relu par Collègue A, De Collègue A aussi.\n')
            self.assertEqual(lire(f1), "Relu par Alice Exemple, D'Alice aussi.\n")

    def test_fichier_sans_version_ignore(self):
        with espace('anonymiser_sans_version') as (r, m):
            f = os.path.join(r, 'note.md'); ecrire(f, 'Alice')
            self.assertIn('ignoré (sans version simple _vN)', lancer(m, f))

    def test_json_reste_valide(self):
        with espace('anonymiser_json') as (r, m):
            f = os.path.join(r, 'fiche_v1.json'); ecrire(f, dict(relecture='Alice Exemple'))
            lancer(m, f)
            self.assertEqual(json.loads(lire(os.path.join(r, 'fiche_v2.json'))), dict(relecture='Collègue A'))

    def test_evenement_dans_le_journal_par_defaut(self):
        with espace('anonymiser_journal') as (r, m):
            f = os.path.join(r, 'note_v1.md'); ecrire(f, 'Alice')
            lancer(m, f)
            ev = glob.glob(chemin('journal', '*', '*_anonymiser_v3_*.json', racine=r))
            self.assertEqual(len(ev), 1)
            self.assertEqual(json.loads(lire(ev[0]))['donnees']['fichiers'], 1)


class Registre(unittest.TestCase):
    def test_regles_et_journal_renommes(self):
        with espace('anonymiser_registre', RENOMMES) as (r, m):
            self.assertEqual(m.CC, r)
            f = os.path.join(r, 'note_v1.md'); ecrire(f, 'Relu par Alice Exemple.\n')
            self.assertIn('note_v2.md (reste : 0)', lancer(m, f))               # règles lues dans le dossier renommé
            self.assertEqual(lire(os.path.join(r, 'note_v2.md')), 'Relu par Collègue A.\n')
            ev = glob.glob(chemin('journal', '*', '*_anonymiser_v3_*.json', racine=r))
            self.assertEqual(len(ev), 1)                                          # événement écrit dans le journal renommé
            self.assertTrue(ev[0].startswith(os.path.join(r, 'trace_renommee') + os.sep))
            dossiers = sorted(d for d in os.listdir(r) if os.path.isdir(os.path.join(r, d)))
            self.assertEqual(dossiers, sorted(['consignes_renommees', 'trace_renommee', os.path.basename(chemin('outils', racine=r))]))


if __name__ == '__main__':
    unittest.main()
