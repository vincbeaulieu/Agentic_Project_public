"""Tests unitaires de banc_v3 (aucune suite précédente). Non-régression : cas lus dans la dernière version de cas_vN.py,
qualité (précision, rappel, F1), alignement, déterminisme, absence de LLM, compacité, résultat versionné et relu, dossier
d'exécution retiré seulement si tout est juste et déterministe, comparaison de deux versions, ligne de commande. Registre
central des dossiers : bancs et journal renommés par outils/_gestion/chemins_v1.json, lus et écrits sous leur nouveau nom.
Chaque essai tourne dans un espace fictif (tests/_test_execution/, par dossier_essai), sur un outil fictif ; la racine de
l'outil, son accès aux outils et le journal de cc_lib_v4 y sont redirigés le temps du test : rien n'est écrit dans l'espace réel."""
import os, io, sys, json, glob, runpy, contextlib, unittest
from unittest import mock
from aide_tests_v2 import dossier_essai, chemin_version, importer_version, chemin, chemins
import cc_lib_v1 as L1, cc_lib_v2 as L2, cc_lib_v4 as L4

B = importer_version('banc', 3)
OUTIL = 'outil_essai'
BANCS_RENOMME, JOURNAL_RENOMME = 'essais_comparatifs', 'evenements_consignes'   # noms fictifs d'un renommage

# Outil fictif : signale les fichiers vides d'un dossier (règle VIDE). v1 juste ; v2 se trompe (un faux positif, un faux
# négatif) ; v3 juste mais non déterministe (horodatage dans la sortie) ; v4 juste mais cite une bibliothèque de LLM.
_V1 = """import sys, os, json
d, s = sys.argv[1], sys.argv[2]
c = [dict(regle='VIDE', chemin=f) for f in sorted(os.listdir(d)) if os.path.getsize(os.path.join(d, f)) == 0]
with open(s, 'w', encoding='utf-8') as g: json.dump(dict(constats=c), g)
"""
SOURCES = {
    1: _V1,
    2: """import sys, os, json
d, s = sys.argv[1], sys.argv[2]
c = [dict(regle='VIDE', chemin=f) for f in sorted(os.listdir(d))
     if (os.path.getsize(os.path.join(d, f)) == 0 and not f.startswith('z')) or f.endswith('.log')]
with open(s, 'w', encoding='utf-8') as g: json.dump(dict(constats=c), g)
""",
    3: _V1.replace('import sys, os, json', 'import sys, os, json, time').replace('dict(constats=c)', 'dict(constats=c, horodatage=time.time_ns())'),
    4: '# repli envisagé : import anthropic\n' + _V1,
}
# Cas du banc : cas_v1 est périmé (il ferait échouer tout outil) ; le banc doit lire cas_v2, la dernière version.
CAS = {
    1: """CAS = [dict(nom='ancien', construire=lambda b: b, commande=lambda o, d, j: [o, d, j], attendu=[('VIDE', 'absent.txt')])]
""",
    2: """import os
def _fichiers(base, contenus):
    for nom, texte in contenus.items():
        with open(os.path.join(base, nom), 'w', encoding='utf-8') as f: f.write(texte)
    return base
def _cmd(outil, dossier, sortie): return [outil, dossier, sortie]
CAS = [
    dict(nom='un_vide', construire=lambda b: _fichiers(b, {'a.txt': '', 'b.txt': 'x'}), commande=_cmd, attendu=[('VIDE', 'a.txt')]),
    dict(nom='deux_vides', construire=lambda b: _fichiers(b, {'c.txt': '', 'notes.log': 'ligne', 'z.txt': ''}), commande=_cmd,
         attendu=[('VIDE', 'c.txt'), ('VIDE', 'z.txt')]),
]
""",
}


def _ecrire(f, texte):
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, 'x', encoding='utf-8') as g: g.write(texte)


def espace(nom, registre=None, versions=(1,)):
    """Espace de compétences fictif : registre des dossiers (facultatif), versions de l'outil fictif, cas du banc."""
    r = dossier_essai(nom)
    if registre: _ecrire(chemin('outils', '_gestion', 'chemins_v1.json', racine=r), json.dumps(dict(chemins=registre)))
    for v in versions: _ecrire(chemin('outils', OUTIL, f'{OUTIL}_v{v}.py', racine=r), SOURCES[v])
    for v, src in CAS.items(): _ecrire(chemin('bancs', OUTIL, f'cas_v{v}.py', racine=r), src)
    return r


def _outils_de(r):
    def chemin_outil(nom, version=None, ext='py'): return chemin('outils', nom, f'{nom}_v{version}.{ext}', racine=r)
    return chemin_outil


@contextlib.contextmanager
def dans(r):
    """Le module banc_v3 travaille dans l'espace fictif r (racine, outils, journal) ; rend la sortie standard capturée."""
    with mock.patch.object(B, 'CC', r), mock.patch.object(B, 'chemin_outil', _outils_de(r)), mock.patch.object(L4, 'RACINE_CC', r), \
            contextlib.redirect_stdout(io.StringIO()) as sortie:
        yield sortie


def lancer(r, *args):
    """Lance banc_v3 en ligne de commande (__main__) dans l'espace fictif r ; rend (code de sortie, sortie standard)."""
    src = chemin_version('banc', 3)
    with mock.patch.object(L1, 'RACINE_CC', r), mock.patch.object(L2, 'chemin_outil', _outils_de(r)), mock.patch.object(L4, 'RACINE_CC', r), \
            mock.patch.object(sys, 'argv', [src, *args]), contextlib.redirect_stdout(io.StringIO()) as sortie:
        try: runpy.run_path(src, run_name='__main__'); code = 0
        except SystemExit as e: code = e.code
    return code, sortie.getvalue()


def resultats(r, version):
    return sorted(glob.glob(chemin('bancs', OUTIL, 'resultats', f'resultat_{OUTIL}_v{version}_*.json', racine=r)))


def evenements(r):
    L = []
    for f in sorted(glob.glob(os.path.join(chemin('journal', racine=r), '*', '*_banc_v3_*.json'))):
        with open(f, encoding='utf-8') as g: L.append(dict(json.load(g), fichier=f))
    return L


def _json(x): return json.loads(json.dumps(x, ensure_ascii=False))


class Garde(unittest.TestCase):
    def tearDown(self):
        self.assertFalse(os.path.exists(chemin('bancs', OUTIL)), "un essai a écrit dans l'espace réel")


class NonRegression(Garde):
    def test_racine_et_bibliotheque(self):
        self.assertEqual(B.CC, L1.RACINE_CC); self.assertTrue(os.path.isdir(chemin('outils', racine=B.CC)))
        self.assertIs(B.chemin, L4.chemin); self.assertIs(B.evenement, L4.evenement)   # journal résolu par le registre

    def test_outil_juste_resultat_versionne(self):
        r = espace('banc_juste')
        with dans(r): res = B.evaluer_version(OUTIL, '1')
        self.assertEqual((res['outil'], res['version'], res['fichier_cas']), (OUTIL, '1', 'cas_v2.py'))   # dernière version des cas
        self.assertEqual(res['qualite'], dict(precision=1.0, rappel=1.0, f1=1.0))
        self.assertEqual(res['alignement'], dict(cas_exacts=2, cas_total=2, taux=1.0))
        self.assertEqual(res['automatisation'], dict(deterministe=True, sans_llm=True))
        self.assertEqual(res['compacite'], dict(lignes_code=4, octets_code=len(SOURCES[1].encode())))
        self.assertEqual([(c['cas'], c['vrais_positifs'], c['faux_positifs'], c['faux_negatifs'], c['deterministe']) for c in res['cas']],
                         [('un_vide', 1, [], [], True), ('deux_vides', 2, [], [], True)])
        for cle in ('rapidite', 'ressources', 'consultees'): self.assertTrue(res[cle])
        f = resultats(r, 1); self.assertEqual(len(f), 1)
        with open(f[0], encoding='utf-8') as g: self.assertEqual(json.load(g), _json(res))
        ev = evenements(r); self.assertEqual(len(ev), 1)
        self.assertEqual((ev[0]['outil'], ev[0]['version'], ev[0]['type']), ('banc', 3, 'banc'))
        self.assertEqual(ev[0]['donnees'], dict(outil=OUTIL, version='1', f1=1.0, alignement=1.0, deterministe=True,
                                                duree=res['rapidite']['duree_mediane_s'], banc=True))
        self.assertEqual(os.listdir(chemin('bancs', OUTIL, '_execution', racine=r)), [])   # tout juste : exécution retirée

    def test_faux_positifs_et_faux_negatifs(self):
        r = espace('banc_erreurs', versions=(2,))
        with dans(r): res = B.evaluer_version(OUTIL, '2')
        self.assertEqual(res['qualite'], dict(precision=0.6667, rappel=0.6667, f1=0.6667))
        self.assertEqual(res['alignement'], dict(cas_exacts=1, cas_total=2, taux=0.5))
        c = {x['cas']: x for x in res['cas']}
        self.assertEqual((c['un_vide']['faux_positifs'], c['un_vide']['faux_negatifs']), ([], []))
        self.assertEqual(c['deux_vides']['vrais_positifs'], 1)
        self.assertEqual(c['deux_vides']['faux_positifs'], [('VIDE', 'notes.log')])
        self.assertEqual(c['deux_vides']['faux_negatifs'], [('VIDE', 'z.txt')])
        ex = os.listdir(chemin('bancs', OUTIL, '_execution', racine=r))   # erreurs : exécution gardée pour l'examen
        self.assertEqual(len(ex), 1); self.assertTrue(ex[0].endswith('_v2'))

    def test_determinisme_mesure(self):
        r = espace('banc_aleatoire', versions=(3,))
        with dans(r): res = B.evaluer_version(OUTIL, '3')
        self.assertEqual(res['qualite']['f1'], 1.0); self.assertFalse(res['automatisation']['deterministe'])
        self.assertEqual([c['deterministe'] for c in res['cas']], [False, False])
        self.assertEqual(len(os.listdir(chemin('bancs', OUTIL, '_execution', racine=r))), 1)   # non déterministe : gardée

    def test_llm_detecte(self):
        r = espace('banc_llm', versions=(4,))
        with dans(r): res = B.evaluer_version(OUTIL, '4')
        self.assertEqual(res['qualite']['f1'], 1.0); self.assertFalse(res['automatisation']['sans_llm'])
        self.assertEqual(res['compacite']['lignes_code'], 4)   # la ligne de commentaire n'est pas comptée

    def test_dernier_resultat(self):
        r = espace('banc_dernier')
        with dans(r): self.assertIsNone(B.dernier_resultat(OUTIL, '1'))   # aucun résultat encore
        _ecrire(chemin('bancs', OUTIL, 'resultats', f'resultat_{OUTIL}_v1_20000101_000000.json', racine=r), json.dumps(dict(version='ancien')))
        _ecrire(chemin('bancs', OUTIL, 'resultats', f'resultat_{OUTIL}_v10_29991231_235959.json', racine=r), json.dumps(dict(version='10')))
        with dans(r): res = B.evaluer_version(OUTIL, '1'); d = B.dernier_resultat(OUTIL, '1')
        self.assertEqual(d, _json(res))   # le plus récent de la version 1, pas celui de la version 10

    def test_comparer(self):
        r = espace('banc_comparer_oui', versions=(1, 2))
        with dans(r) as s: code = B.comparer(OUTIL, '2', '1')
        L = s.getvalue().splitlines()
        self.assertEqual(code, 0); self.assertEqual(L[-1], 'ADOPTER v1')
        self.assertTrue(L[0].startswith('ancienne v2 : F1 0.667 ')); self.assertTrue(L[1].startswith('nouvelle v1 : F1 1.000 '))
        ev = [e for e in evenements(r) if e['type'] == 'comparaison']
        self.assertEqual([e['donnees'] for e in ev], [dict(outil=OUTIL, ancienne='2', nouvelle='1', adopter=True, banc=True)])
        r = espace('banc_comparer_non', versions=(1, 2))
        with dans(r) as s: code = B.comparer(OUTIL, '1', '2')
        self.assertEqual(code, 1)
        self.assertEqual(s.getvalue().splitlines()[-1], 'NE PAS ADOPTER v2 (qualité, alignement ou déterminisme en baisse)')
        r = espace('banc_comparer_aleatoire', versions=(1, 3))
        with dans(r): self.assertEqual(B.comparer(OUTIL, '1', '3'), 1)   # même F1, mais non déterministe

    def test_resume(self):
        r = dict(version='7', qualite=dict(f1=0.5, precision=0.25, rappel=1.0), alignement=dict(cas_exacts=1, cas_total=4),
                 rapidite=dict(duree_mediane_s=0.012), ressources=dict(cpu_median_s=0.01, rss_max_ko=9000),
                 consultees=dict(octets_lus_median=1234), compacite=dict(lignes_code=42), automatisation=dict(deterministe=True, sans_llm=False))
        self.assertEqual(B.resume(r), 'v7 : F1 0.500 (P 0.250, R 1.000) · cas exacts 1/4 · 0.012 s · CPU 0.01 s · RSS 9000 Ko · '
                                      'lus 1234 o · 42 lignes · déterministe True · sans LLM False')

    def test_cas_ou_outil_absent(self):
        r = espace('banc_absents')
        with dans(r), self.assertRaises(SystemExit) as e: B.charger_cas('outil_sans_cas')
        self.assertTrue(str(e.exception.code).startswith('aucun fichier de cas : '))
        rep = dossier_essai('banc_absents_execution')
        with dans(r):
            _, cas = B.charger_cas(OUTIL)
            with self.assertRaises(SystemExit) as e: B.executer(OUTIL, 9, cas[0], rep, 1)
        self.assertTrue(str(e.exception.code).startswith('outil absent : '))

    def test_ligne_de_commande(self):
        r = espace('banc_commande', versions=(1, 2))
        code, out = lancer(r, OUTIL, '1,2')
        L = out.splitlines()
        self.assertEqual(code, 0); self.assertEqual(len(L), 3)
        self.assertTrue(L[0].startswith('v1 : F1 1.000 ')); self.assertTrue(L[1].startswith('v2 : F1 0.667 '))
        self.assertTrue(L[2].startswith("    deux_vides FP [('VIDE', 'notes.log')] FN [('VIDE', 'z.txt')]"))
        self.assertEqual((len(resultats(r, 1)), len(resultats(r, 2))), (1, 1))
        code, out = lancer(espace('banc_commande_comparer', versions=(1, 2)), OUTIL, '--comparer', '2', '1')
        self.assertEqual((code, out.splitlines()[-1]), (0, 'ADOPTER v1'))
        code, out = lancer(espace('banc_commande_refus', versions=(1, 2)), OUTIL, '--comparer', '1', '2')
        self.assertEqual(code, 1)


class Registre(Garde):
    """outils/_gestion/chemins_v1.json renomme les bancs et le journal : le banc lit et écrit sous les nouveaux noms."""
    REGISTRE = dict(bancs=BANCS_RENOMME, journal=JOURNAL_RENOMME)

    def setUp(self):
        self.vide = dossier_essai('banc_registre_defauts')   # espace sans registre : noms par défaut

    def test_ecriture_sous_les_noms_du_registre(self):
        r = espace('banc_registre', registre=self.REGISTRE)
        self.assertEqual(chemin('bancs', racine=r), os.path.join(r, BANCS_RENOMME))
        with dans(r): res = B.evaluer_version(OUTIL, '1')
        self.assertEqual((res['fichier_cas'], res['qualite']['f1']), ('cas_v2.py', 1.0))
        f = glob.glob(os.path.join(r, BANCS_RENOMME, OUTIL, 'resultats', f'resultat_{OUTIL}_v1_*.json')); self.assertEqual(len(f), 1)
        self.assertTrue(os.path.isdir(os.path.join(r, BANCS_RENOMME, OUTIL, '_execution')))
        ev = evenements(r); self.assertEqual(len(ev), 1)
        self.assertTrue(ev[0]['fichier'].startswith(os.path.join(r, JOURNAL_RENOMME) + os.sep))
        for cle in self.REGISTRE: self.assertFalse(os.path.exists(os.path.join(r, chemins(self.vide)[cle])), cle)   # ancien nom jamais créé

    def test_lecture_sous_les_noms_du_registre(self):
        r = espace('banc_registre_lecture', registre=self.REGISTRE)
        ancien = os.path.join(r, chemins(self.vide)['bancs'], OUTIL)   # leurres sous l'ancien nom : à ignorer
        _ecrire(os.path.join(ancien, 'cas_v9.py'), CAS[1])
        _ecrire(os.path.join(ancien, 'resultats', f'resultat_{OUTIL}_v1_29991231_235959.json'), json.dumps(dict(version='leurre')))
        with dans(r):
            fcas, cas = B.charger_cas(OUTIL)
            self.assertEqual(fcas, os.path.join(r, BANCS_RENOMME, OUTIL, 'cas_v2.py')); self.assertEqual(len(cas), 2)
            self.assertIsNone(B.dernier_resultat(OUTIL, '1'))
            res = B.evaluer_version(OUTIL, '1'); self.assertEqual(B.dernier_resultat(OUTIL, '1'), _json(res))

    def test_ligne_de_commande_sous_les_noms_du_registre(self):
        r = espace('banc_registre_commande', registre=self.REGISTRE, versions=(1, 2))
        code, out = lancer(r, OUTIL, '--comparer', '2', '1')
        self.assertEqual((code, out.splitlines()[-1]), (0, 'ADOPTER v1'))
        self.assertEqual(len(glob.glob(os.path.join(r, BANCS_RENOMME, OUTIL, 'resultats', '*.json'))), 2)
        self.assertEqual(sorted(e['type'] for e in evenements(r)), ['banc', 'banc', 'comparaison'])
        self.assertTrue(all(e['fichier'].startswith(os.path.join(r, JOURNAL_RENOMME) + os.sep) for e in evenements(r)))


if __name__ == '__main__':
    unittest.main()
