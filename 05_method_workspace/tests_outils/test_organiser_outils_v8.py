"""Suite v8 (16 oct. 2026) : suite v7 rejouée sur la v8, plus la classe Catalogue (régénération après adoption). Tests de organiser_outils_v7 et du moteur _raccourci_v3, sur un espace de compétences fictif (copie isolée) :
organisation à plat -> un dossier par outil + archive ; raccourcis et compatibilité ; brouillon écrit dans candidat/ (le
raccourci garde la version adoptée), adoption qui le met en place, remise dans candidat/ si les tests échouent ; rejouer sur
une seconde copie, doublon identique rangé dans _gestion/doublons_rejouer/ ; changement de moteur : raccourcis de l'ancien
moteur régénérés, ancien moteur archivé ; dossier des tests et journal des anciennes bibliothèques par le registre des chemins ;
message d'usage sans argument."""
import os, sys, json, glob, shutil, subprocess, unittest
from aide_tests_v2 import dossier_essai, OUTILS, chemin_version

ENT = '"""\nOUTIL: {o}\nVERSION: {v}\nRESUME: essai\nUSAGE: -\nENTREES: -\nSORTIES: -\nCATEGORIE: essai\nBANC: -\nREMPLACE: {r}\n"""\n'
ORG = chemin_version('organiser_outils', 8); MOTEUR3 = os.path.join(OUTILS, '_raccourci_v3.py')
MOTEUR2 = next(f for f in (os.path.join(OUTILS, '_raccourci_v2.py'), os.path.join(OUTILS, '_raccourci', 'archive', '_raccourci_v2.py')) if os.path.exists(f))


def w(chemin, texte):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, 'w', encoding='utf-8') as g: g.write(texte)


def lire(chemin):
    with open(chemin, encoding='utf-8') as g: return g.read()


def espace(nom, moteur=MOTEUR3):
    rc = dossier_essai(nom); o = os.path.join(rc, 'outils'); os.makedirs(o)
    shutil.copy(moteur, o); shutil.copy(ORG, os.path.join(o, 'organiser_outils_v8.py'))
    w(os.path.join(o, 'a_v1.py'), ENT.format(o='a', v=1, r='-') + "if __name__ == '__main__': print('A1')\n")
    w(os.path.join(o, 'a_v2.py'), ENT.format(o='a', v=2, r='a_v1 (essai)') + "import b_v1\nif __name__ == '__main__': print('A2', b_v1.VAL)\n")
    w(os.path.join(o, 'b_v1.py'), ENT.format(o='b', v=1, r='-') + "VAL = 'B1'\n")
    return rc, o


def lancer(o, *a):
    r = subprocess.run([sys.executable] + list(a), capture_output=True, text=True, cwd=o, env=dict(os.environ, PYTHONPATH=''))
    return r.returncode, r.stdout + r.stderr


def organiser(o):
    """Organisation initiale à plat -> un dossier par outil ; renvoie le chemin de l'organiseur une fois rangé."""
    c, s = lancer(o, 'organiser_outils_v8.py', 'plan'); assert c == 0, s
    plan = sorted(os.listdir(os.path.join(o, '_gestion', 'plans')))[-1]
    c, s = lancer(o, 'organiser_outils_v8.py', 'appliquer', os.path.join('_gestion', 'plans', plan)); assert c == 0, s
    orgc = os.path.join('organiser_outils', 'organiser_outils_v8.py'); c, s = lancer(o, orgc, 'raccourcis'); assert c == 0, s
    return orgc


class Organisation(unittest.TestCase):
    def test_cycle_avec_candidat(self):
        rc, o = espace('org7_cycle'); orgc = organiser(o)
        c, s = lancer(o, orgc, 'verifier'); self.assertEqual(c, 0, s)
        self.assertEqual(lancer(o, 'a.py')[1].strip(), 'A2 B1')
        self.assertEqual(lancer(o, os.path.join('_compat', 'a_v1.py'))[1].strip(), 'A1')
        c, s = lancer(o, orgc, 'preparer', 'b'); self.assertEqual(c, 0, s)
        cand = os.path.join(o, 'b', 'candidat', 'b_v2.py'); self.assertTrue(os.path.exists(cand))
        self.assertFalse(os.path.exists(os.path.join(o, 'b', 'b_v2.py')))
        w(cand, lire(cand).replace("VAL = 'B1'", "VAL = 'B2'"))
        self.assertEqual(lancer(o, 'b.py')[0], 0); self.assertEqual(lancer(o, 'a.py')[1].strip(), 'A2 B1')    # brouillon jamais pris pour la version courante
        c, s = lancer(o, orgc, 'preparer', 'b'); self.assertNotEqual(c, 0)                                     # une seule candidate à la fois
        c, s = lancer(o, orgc, 'adopter', 'b', '--sans-tests'); self.assertNotEqual(c, 0)                    # « À DÉCRIRE »
        self.assertTrue(os.path.exists(cand))
        w(cand, lire(cand).replace('(À DÉCRIRE : ce qui change)', '(essai)'))
        c, s = lancer(o, orgc, 'adopter', 'b', '--sans-tests'); self.assertEqual(c, 0, s)
        self.assertTrue(os.path.exists(os.path.join(o, 'b', 'b_v2.py'))); self.assertTrue(os.path.exists(os.path.join(o, 'b', 'archive', 'b_v1.py')))
        self.assertFalse(os.path.exists(os.path.join(o, 'b', 'candidat')))
        c, s = lancer(o, orgc, 'verifier'); self.assertEqual(c, 0, s)
        # seconde copie (le « PC ») : rejouer, y compris un doublon identique des deux côtés
        rc2 = dossier_essai('org8_copie'); shutil.copytree(rc, os.path.join(rc2, 'cc')); o2 = os.path.join(rc2, 'cc', 'outils')
        os.rename(os.path.join(o2, 'b', 'archive', 'b_v1.py'), os.path.join(o2, 'b', 'b_v1.py'))
        shutil.copy(os.path.join(o2, 'b', 'b_v1.py'), os.path.join(o2, 'b', 'archive', 'b_v1.py'))            # doublon identique
        c, s = lancer(o2, orgc, 'rejouer'); self.assertEqual(c, 0, s); self.assertIn('1 doublon(s)', s)
        self.assertFalse(os.path.exists(os.path.join(o2, 'b', 'b_v1.py')))
        self.assertTrue(glob.glob(os.path.join(o2, '_gestion', 'doublons_rejouer', '*', 'outils', 'b', 'b_v1.py')))

    def test_usage(self):
        rc, o = espace('org7_usage')
        c, s = lancer(o, 'organiser_outils_v8.py'); self.assertEqual(c, 2); self.assertIn('preparer', s)


class Moteur(unittest.TestCase):
    def test_changement_de_moteur(self):
        rc, o = espace('org7_moteur', moteur=MOTEUR2); orgc = organiser(o)
        self.assertIn('_raccourci_v2', lire(os.path.join(o, 'a.py')))
        shutil.copy(MOTEUR3, o)                                                                                # nouveau moteur
        c, s = lancer(o, orgc, 'raccourcis'); self.assertEqual(c, 0, s)
        self.assertIn('_raccourci_v3', lire(os.path.join(o, 'a.py'))); self.assertIn('_raccourci_v3', lire(os.path.join(o, '_compat', 'a_v1.py')))
        self.assertTrue(os.path.exists(os.path.join(o, '_raccourci', 'archive', '_raccourci_v2.py')))
        self.assertFalse(os.path.exists(os.path.join(o, '_raccourci_v2.py')))
        self.assertTrue(glob.glob(os.path.join(o, '_gestion', 'raccourcis_retires', '*_moteur', 'a.py')))
        self.assertEqual(lancer(o, 'a.py')[1].strip(), 'A2 B1')
        c, s = lancer(o, orgc, 'verifier'); self.assertEqual(c, 0, s)

    def test_journal_des_anciennes_bibliotheques(self):
        rc, o = espace('org7_journal'); organiser(o)
        w(os.path.join(o, '_gestion', 'chemins_v1.json'), json.dumps(dict(chemins=dict(journal='journal_des_evenements'))))
        w(os.path.join(o, 'vieille_lib', 'vieille_lib_v1.py'), "import os\nRACINE_CC = '/nulle/part'\nJOURNAL = os.path.join(RACINE_CC, 'journal')\n")
        w(os.path.join(o, 'cc_lib_v1.py'), "RACINE_CC = '/nulle/part'\nJOURNAL = '/nulle/part/journal'\n")
        os.makedirs(os.path.join(o, 'cc_lib')); os.rename(os.path.join(o, 'cc_lib_v1.py'), os.path.join(o, 'cc_lib', 'cc_lib_v1.py'))
        lancer(o, os.path.join('organiser_outils', 'organiser_outils_v8.py'), 'raccourcis')
        code = "import sys; sys.path.insert(0, '.'); import _raccourci_v3 as R; m = R.importer('cc_lib', 1); print(m.JOURNAL)"
        c, s = lancer(o, '-c', code); self.assertEqual(c, 0, s)
        self.assertEqual(s.strip(), os.path.join(rc, 'journal_des_evenements'))



class Catalogue(unittest.TestCase):
    def test_regenere_apres_adoption(self):
        rc, o = espace('org8_catalogue')
        w(os.path.join(o, 'catalogue_v1.py'), ENT.format(o='catalogue', v=1, r='-') + "if __name__ == '__main__': print('catalogue_outils_v9.md (essai)')\n")
        orgc = organiser(o); c, s = lancer(o, orgc, 'preparer', 'b'); self.assertEqual(c, 0, s)
        cand = os.path.join(o, 'b', 'candidat', 'b_v2.py'); w(cand, lire(cand).replace('(À DÉCRIRE : ce qui change)', '(essai)'))
        c, s = lancer(o, orgc, 'adopter', 'b', '--sans-tests'); self.assertEqual(c, 0, s)
        self.assertIn('catalogue : catalogue_outils_v9.md (essai)', s)

    def test_absent_dit_pourquoi(self):
        rc, o = espace('org8_sans_catalogue'); orgc = organiser(o)
        c, s = lancer(o, orgc, 'preparer', 'b'); cand = os.path.join(o, 'b', 'candidat', 'b_v2.py')
        w(cand, lire(cand).replace('(À DÉCRIRE : ce qui change)', '(essai)'))
        c, s = lancer(o, orgc, 'adopter', 'b', '--sans-tests'); self.assertEqual(c, 0, s)
        self.assertIn('catalogue : outil absent de cet espace, non régénéré', s)

if __name__ == '__main__':
    unittest.main()
