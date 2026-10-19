"""Tests unitaires de catalogue v3 (registre central des dossiers, cc_lib_v4.chemin). Aucune suite précédente.
(a) Non-régression : sur un espace fictif aux noms par défaut, la v3 produit le même catalogue que la v2 (seule la ligne
« Généré par » change ; JSON identique, donc pas de nouvelle version) ; sur l'espace réel, lu sans rien écrire (écriture
et journal interceptés), mêmes contenus Markdown et JSON que la v2 tant que le registre réel garde les noms par défaut.
(b) Registre : dans un espace fictif dont outils/_gestion/chemins_v1.json renomme les dossiers du catalogue, des bancs et du
journal, la v3 lit le résultat de banc du dossier renommé (pas le leurre au nom par défaut) et écrit le catalogue et son
événement dans les dossiers renommés.
Les essais n'écrivent que dans tests/_test_execution/ (dossier_essai) ; aucun nom de dossier de l'espace n'est écrit en dur."""
import os, io, re, sys, json, glob, unittest, contextlib
from unittest import mock
sys.dont_write_bytecode = True          # aucun cache .pyc écrit hors de tests/ par les versions essayées
from aide_tests_v2 import dossier_essai, chemin_version, importer_version, chemin, chemins, RACINE_CC
import cc_lib_v4

OUTIL = 'catalogue'                     # nom de l'outil (homonyme de la clé du dossier), pas un chemin
RENOMMES = dict(catalogue='renomme_catalogue', bancs='renomme_bancs', journal='renomme_journal')
REGISTRE_DEFAUT = chemins(RACINE_CC) == cc_lib_v4.DEFAUT
ENTETE = '"""\nOUTIL: {o}\nVERSION: {v}\nRESUME: Outil fictif {o} : compte les mots.\nUSAGE: python3 {o}_v{v}.py <fichier>\n' \
         'ENTREES: fichier texte\nSORTIES: nombre de mots\nCATEGORIE: essai\nBANC: cas fixes\nREMPLACE: -\n"""\nprint(1)\n'


def muet(f):
    s = io.StringIO()
    with contextlib.redirect_stdout(s): f()
    return s.getvalue()


def ecrire(f, texte):
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, 'x', encoding='utf-8') as g: g.write(texte)


def lire(f):
    with open(f, encoding='utf-8') as g: return g.read()


def num(f): return int(re.search(r'_v(\d+)\.\w+$', f).group(1))
def rel(p, r): return os.path.relpath(p, r).replace(os.sep, '/')


def peupler_outils(r):
    """Outils fictifs : outil_a (v2 courante, v1 archivée), outil_b (en-tête incomplet), doc_c (document), ps_d (PowerShell)."""
    ecrire(chemin('outils', 'outil_a', 'outil_a_v2.py', racine=r), ENTETE.format(o='outil_a', v=2))
    ecrire(chemin('outils', 'outil_a', 'archive', 'outil_a_v1.py', racine=r), ENTETE.format(o='outil_a', v=1))
    ecrire(chemin('outils', 'outil_b', 'outil_b_v1.py', racine=r), '"""\nOUTIL: outil_b\nVERSION: 1\nRESUME: En-tête incomplet.\n"""\n')
    ecrire(chemin('outils', 'doc_c', 'doc_c_v1.md', racine=r), '# Document fictif (v1)\n\nTexte.\n')
    ecrire(chemin('outils', 'ps_d', 'ps_d_v1.ps1', racine=r), '# OUTIL: ps_d\n# VERSION: 1\n# RESUME: Script fictif.\nWrite-Host 1\n')
    os.makedirs(chemin('outils', '__pycache__', racine=r))


def resultat_banc(r, f1):
    """Résultat de banc de outil_a v2, dans le dossier des bancs que désigne le registre au moment de l'appel."""
    ecrire(chemin('bancs', 'outil_a', 'resultats', 'resultat_outil_a_v2_20261015_120000.json', racine=r), json.dumps(dict(
        qualite=dict(f1=f1), alignement=dict(cas_exacts=3, cas_total=4), rapidite=dict(duree_mediane_s=0.05),
        automatisation=dict(deterministe=True), date='2026-10-15T12:00:00Z')))


def v3(r):
    """Lance la v3 sur l'espace r : racine de l'outil et racine du journal (cc_lib_v4.evenement) remplacées le temps de l'appel."""
    M = importer_version(OUTIL, 3)
    with mock.patch.object(M, 'RACINE_CC', r), mock.patch.object(cc_lib_v4, 'RACINE_CC', r): return muet(M.main)


class NonRegression(unittest.TestCase):
    def test_espace_fictif_meme_catalogue_que_v2(self):
        r = dossier_essai('v2_v3_catalogue'); peupler_outils(r); resultat_banc(r, 0.9)
        M2, e2 = importer_version(OUTIL, 2), mock.Mock()
        with mock.patch.object(M2, 'RACINE_CC', r), mock.patch.object(M2, 'evenement', e2): muet(M2.main)
        s3 = v3(r)
        cdir = chemin('catalogue', racine=r)
        md = sorted(glob.glob(os.path.join(cdir, '*.md')), key=num); js = glob.glob(os.path.join(cdir, '*.json'))
        self.assertEqual(len(md), 2); self.assertEqual(len(js), 1)            # JSON identique : pas de nouvelle version
        a, b = lire(md[0]).splitlines(), lire(md[1]).splitlines()
        self.assertEqual([i for i, (x, y) in enumerate(zip(a, b)) if x != y], [2]); self.assertEqual(len(a), len(b))
        self.assertEqual(re.sub(r'_v\d+\.py', '', a[2]), re.sub(r'_v\d+\.py', '', b[2])); self.assertIn('_v3.py', b[2])
        with open(js[0], encoding='utf-8') as g: J = {o['outil']: o for o in json.load(g)}
        self.assertEqual(sorted(J), ['doc_c', 'outil_a', 'outil_b', 'ps_d'])
        a = J['outil_a']
        self.assertEqual((a['version'], a['archivees'], a['versions'], a['banc']['f1'], a['banc']['cas']), ('2', 1, ['1', '2'], 0.9, '3/4'))
        self.assertEqual(a['raccourci'], rel(chemin('outils', 'outil_a.py', racine=r), r))
        self.assertEqual(a['fichier'], os.path.relpath(chemin('outils', 'outil_a', 'outil_a_v2.py', racine=r), os.path.dirname(r)))
        self.assertEqual(J['doc_c']['raccourci'], rel(chemin('outils', 'doc_c', racine=r), r) + '/')
        self.assertEqual(J['doc_c']['categorie'], 'document'); self.assertEqual(J['ps_d']['resume'], 'Script fictif.')
        self.assertIn('4 outils ; 1 en-tête(s) incomplet(s)', s3); self.assertIn('nouvelle version', s3); self.assertIn('outil_b', s3)
        e2.assert_called_once(); self.assertEqual(e2.call_args[0][:3], (OUTIL, 2, OUTIL))
        ev = glob.glob(chemin('journal', '*', '*.json', racine=r)); self.assertEqual(len(ev), 1)
        with open(ev[0], encoding='utf-8') as g: e = json.load(g)
        self.assertEqual((e['outil'], e['version'], e['type']), (OUTIL, 3, OUTIL))
        self.assertEqual(e['donnees'], dict(e2.call_args[0][3], nouveau=True, fichier=os.path.basename(md[1]), banc=True))
        self.assertIn('inchangé', v3(r)); self.assertEqual(len(glob.glob(os.path.join(cdir, '*'))), 3)   # déterministe

    @unittest.skipUnless(REGISTRE_DEFAUT, 'registre réel non par défaut : la v2 ne le connaît pas')
    def test_espace_reel_meme_contenu_que_v2(self):
        sortie = {}
        def capter(v):
            def ecrire_versionne(dossier, base, ext, contenu):
                sortie[v, ext] = (dossier, contenu); return os.path.join(dossier, f'{base}_v0.{ext}'), False
            return ecrire_versionne
        for v in (2, 3):
            M = importer_version(OUTIL, v)
            with mock.patch.object(M, 'ecrire_versionne', capter(v)), mock.patch.object(M, 'evenement', mock.Mock()): muet(M.main)
        self.assertEqual(sortie[3, 'md'][0], chemin('catalogue', racine=RACINE_CC))
        self.assertEqual(sortie[3, 'json'], sortie[2, 'json'])
        a, b = sortie[2, 'md'][1].splitlines(), sortie[3, 'md'][1].splitlines()
        self.assertEqual(a[:2] + a[3:], b[:2] + b[3:]); self.assertGreater(len(json.loads(sortie[3, 'json'][1])), 10)


class Registre(unittest.TestCase):
    def test_dossiers_renommes(self):
        r = dossier_essai('registre_catalogue'); peupler_outils(r); outils = {os.path.basename(chemin('outils', racine=r))}
        resultat_banc(r, 0.1)                                                     # leurre, au nom par défaut (pas encore de registre)
        leurres = set(os.listdir(r)) - outils
        ecrire(chemin('outils', '_gestion', 'chemins_v1.json', racine=r), json.dumps(dict(chemins=RENOMMES)))
        for k, v in RENOMMES.items(): self.assertEqual(chemin(k, racine=r), os.path.join(r, v))
        resultat_banc(r, 0.9)                                                     # dossier renommé
        s = v3(r)
        self.assertIn('4 outils', s)
        self.assertEqual(set(os.listdir(r)), outils | leurres | set(RENOMMES.values()))   # rien d'écrit sous un nom par défaut
        md = glob.glob(chemin('catalogue', '*.md', racine=r)); js = glob.glob(chemin('catalogue', '*.json', racine=r))
        self.assertEqual((len(md), len(js)), (1, 1))
        with open(js[0], encoding='utf-8') as g: J = {o['outil']: o for o in json.load(g)}
        self.assertEqual(J['outil_a']['banc']['f1'], 0.9); self.assertIn('F1 0.9, 3/4 cas', lire(md[0]))
        ev = glob.glob(chemin('journal', '*', '*.json', racine=r)); self.assertEqual(len(ev), 1)
        with open(ev[0], encoding='utf-8') as g: e = json.load(g)
        self.assertEqual((e['outil'], e['version'], e['donnees']['fichier']), (OUTIL, 3, os.path.basename(md[0])))


class Entete(unittest.TestCase):
    def test_banc_et_remplace(self):
        e = cc_lib_v4.lire_entete(chemin_version(OUTIL, 3))
        self.assertEqual(e['VERSION'], '3')
        self.assertEqual(e['BANC'], 'tests/' + os.path.basename(__file__))   # chemin logique (clé « tests »), stable si le dossier est renommé
        self.assertTrue(e['REMPLACE'].startswith(f"{OUTIL}_v2 (noms de dossiers de l'espace écrits en dur, remplacés par le registre central cc_lib_v4.chemin) ; v2 : {OUTIL}_v1 ("))


if __name__ == '__main__':
    unittest.main()
