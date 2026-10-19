"""Tests de creer_travail_v1 : création d'un dossier de travail conforme (six sous-dossiers, sources copiées en lecture seule avec
empreintes SHA-256, TRAVAIL_v1.json, LISEZMOI_v1.md, événement de journal redirigé vers le dossier d'essai) ; valeurs par défaut sans
source ; options (auteur, couverture, relecteurs aux segments vides ignorés) ; rejeu qui n'écrase ni la fiche, ni le LISEZMOI, ni une
source déjà copiée, ni les fichiers ajoutés par l'auteur ; nouvelle source au rejeu (copiée en lecture seule, mais sans empreinte :
défaut signalé par un test en échec attendu) ; erreurs de ligne de commande (code 2, source absente)."""
import os, sys, glob, json, hashlib, subprocess, unittest
from aide_tests_v2 import dossier_essai, chemin_version, OUTILS

OUTIL = chemin_version('creer_travail', 1)
SOUS = ('00_sources', '01_plan', '90_scripts', '95_journal', '98_livrables', '99_livrables_modifiables')
# L'outil écrit un événement dans le journal de l'espace : le lanceur en redirige la racine vers le dossier d'essai (argument 1).
LANCEUR = ("import sys, runpy, cc_lib_v1; cc_lib_v1.JOURNAL = sys.argv[1]; sys.argv[:] = sys.argv[2:]; "
           "runpy.run_path(sys.argv[0], run_name='__main__')")


def sha(chemin):
    with open(chemin, 'rb') as f: return hashlib.sha256(f.read()).hexdigest()


def lire(chemin):
    with open(chemin, encoding='utf-8') as f: return f.read()


def ecrire(chemin, contenu):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, 'wb') as f: f.write(contenu if isinstance(contenu, bytes) else contenu.encode('utf-8'))
    return chemin


def lecture_seule(chemin):
    return os.stat(chemin).st_mode & 0o222 == 0


class Base(unittest.TestCase):
    def setUp(self):
        self.d = dossier_essai('creer_travail'); self.racine = os.path.join(self.d, 'a', 'b', 'racine_neuve')   # racine inexistante
        self.journal = os.path.join(self.d, 'evenements_essai')
        self.doc = ecrire(os.path.join(self.d, 'entrees', 'rapport_v1.docx'), b'PK contenu docx synthetique')
        self.csv = ecrire(os.path.join(self.d, 'entrees', 'donnees.csv'), 'a;b\n1;2\n')

    def lancer(self, *args):
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS]))
        return subprocess.run([sys.executable, '-c', LANCEUR, self.journal, OUTIL, *args], capture_output=True, text=True, env=env)

    def creer(self, nom='07_sujet', *extra, sujet='Revue du rapport', version='2.0.0'):
        return self.lancer(self.racine, nom, '--sujet', sujet, '--version-cible', version, *extra)

    def evenements(self):
        return [json.loads(lire(f)) for f in sorted(glob.glob(os.path.join(self.journal, '*', '*.json')))]

    def dossier(self, nom='07_sujet'):
        return os.path.join(self.racine, nom)


class Creation(Base):
    def test_creation_complete(self):
        r = self.creer('07_sujet', '--couverture', '0', '23', '--relecteurs', 'Collègue A;Collègue B', '--source', self.doc, self.csv)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('dossier prêt', r.stdout)
        D = self.dossier()
        for s in SOUS: self.assertTrue(os.path.isdir(os.path.join(D, s)), s)
        for src in (self.doc, self.csv):                                        # copie (la source reste en place), en lecture seule
            copie = os.path.join(D, '00_sources', os.path.basename(src))
            self.assertTrue(os.path.exists(src)); self.assertEqual(sha(copie), sha(src)); self.assertTrue(lecture_seule(copie))
        fsha = os.path.join(D, '00_sources', 'sha256_sources_v1.txt')
        self.assertEqual(lire(fsha), f'{sha(self.doc)}  00_sources/rapport_v1.docx\n{sha(self.csv)}  00_sources/donnees.csv\n')
        self.assertTrue(lecture_seule(fsha))
        T = json.loads(lire(os.path.join(D, 'TRAVAIL_v1.json')))
        self.assertTrue(T.pop('auteur_revisions').startswith('Reevaluation'))
        self.assertEqual(T, dict(sujet='Revue du rapport', source='00_sources/rapport_v1.docx', version_cible='2.0.0', couverture=[0, 23],
                                 auteurs_relecteurs=['Collègue A', 'Collègue B']))
        self.assertTrue(lire(os.path.join(D, 'LISEZMOI_v1.md')).startswith('# 07_sujet : Revue du rapport\n'))
        ev = self.evenements()                                                  # un seul événement, dans le journal d'essai
        self.assertEqual([(e['outil'], e['type']) for e in ev], [('creer_travail', 'creation')])
        self.assertEqual((ev[0]['donnees']['dossier'], ev[0]['donnees']['sources']), ('07_sujet', ['rapport_v1.docx', 'donnees.csv']))

    def test_sans_source_valeurs_par_defaut(self):
        r = self.creer('08_vide')
        self.assertEqual(r.returncode, 0, r.stderr)
        D = self.dossier('08_vide')
        self.assertEqual(os.listdir(os.path.join(D, '00_sources')), [])         # ni copie ni fichier d'empreintes
        T = json.loads(lire(os.path.join(D, 'TRAVAIL_v1.json')))
        self.assertIsNone(T['source']); self.assertIsNone(T['couverture']); self.assertEqual(T['auteurs_relecteurs'], [])
        self.assertTrue(T['auteur_revisions'].startswith('Reevaluation'))
        self.assertEqual(self.evenements()[0]['donnees']['sources'], [])

    def test_options_auteur_couverture_relecteurs(self):
        r = self.creer('09_options', '--auteur', 'Collègue C', '--couverture', '2', '40', '--relecteurs', ';Collègue A;;Collègue B;')
        self.assertEqual(r.returncode, 0, r.stderr)
        T = json.loads(lire(os.path.join(self.dossier('09_options'), 'TRAVAIL_v1.json')))
        self.assertEqual((T['auteur_revisions'], T['couverture']), ('Collègue C', [2, 40]))
        self.assertEqual(T['auteurs_relecteurs'], ['Collègue A', 'Collègue B'])     # segments vides ignorés


class Rejeu(Base):
    def test_rejeu_n_ecrase_rien(self):
        self.assertEqual(self.creer('07_sujet', '--source', self.doc).returncode, 0)
        D = self.dossier(); fiche, lisez = os.path.join(D, 'TRAVAIL_v1.json'), os.path.join(D, 'LISEZMOI_v1.md')
        ecrire(fiche, '{"sujet": "modifié par l\'auteur"}'); ecrire(lisez, '# note de l\'auteur\n')
        ecrire(os.path.join(D, '90_scripts', 'mon_script.py'), 'print(1)\n')
        copie = os.path.join(D, '00_sources', 'rapport_v1.docx'); avant = sha(copie)
        fsha = os.path.join(D, '00_sources', 'sha256_sources_v1.txt'); lignes = lire(fsha)
        ecrire(self.doc, b'PK source remplacee apres coup')                     # la source d'origine change entre-temps
        r = self.creer('07_sujet', '--source', self.doc, sujet='Autre sujet', version='9.0.0')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(lire(fiche), '{"sujet": "modifié par l\'auteur"}'); self.assertEqual(lire(lisez), '# note de l\'auteur\n')
        self.assertEqual(sha(copie), avant); self.assertEqual(lire(fsha), lignes)   # source déjà copiée et empreintes intactes
        self.assertTrue(os.path.exists(os.path.join(D, '90_scripts', 'mon_script.py')))
        self.assertGreaterEqual(len(self.evenements()), 1)                       # le rejeu journalise aussi sa création

    def test_rejeu_nouvelle_source_copiee_en_lecture_seule(self):
        self.assertEqual(self.creer('07_sujet', '--source', self.doc).returncode, 0)
        self.assertEqual(self.creer('07_sujet', '--source', self.doc, self.csv).returncode, 0)
        copie = os.path.join(self.dossier(), '00_sources', 'donnees.csv')
        self.assertEqual(sha(copie), sha(self.csv)); self.assertTrue(lecture_seule(copie))

    @unittest.expectedFailure
    def test_rejeu_nouvelle_source_a_son_empreinte(self):
        # Défaut : au rejeu, une source ajoutée est copiée mais le fichier d'empreintes existant n'est pas complété (ni une nouvelle
        # version écrite) : la nouvelle source reste en lecture seule dans 00_sources sans empreinte enregistrée.
        self.creer('07_sujet', '--source', self.doc); self.creer('07_sujet', '--source', self.doc, self.csv)
        self.assertIn('00_sources/donnees.csv', lire(os.path.join(self.dossier(), '00_sources', 'sha256_sources_v1.txt')))


class Erreurs(Base):
    def test_sans_argument_ou_option_obligatoire(self):
        for args in ((), (self.racine, '07_sujet'), (self.racine, '07_sujet', '--sujet', 'S'), ('--sujet', 'S', '--version-cible', '1.0.0')):
            r = self.lancer(*args)
            self.assertEqual(r.returncode, 2, args); self.assertIn('usage', r.stderr.lower())
        self.assertFalse(os.path.exists(self.racine))                           # rien n'est créé quand les arguments sont incomplets

    def test_couverture_incomplete_refusee(self):
        r = self.creer('07_sujet', '--couverture', '3')
        self.assertEqual(r.returncode, 2); self.assertIn('couverture', r.stderr)

    def test_source_absente(self):
        r = self.creer('07_sujet', '--source', os.path.join(self.d, 'entrees', 'inexistant.docx'))
        self.assertNotEqual(r.returncode, 0); self.assertIn('inexistant.docx', r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.dossier(), 'TRAVAIL_v1.json')))   # pas de fiche annonçant une source absente


if __name__ == '__main__':
    unittest.main()
