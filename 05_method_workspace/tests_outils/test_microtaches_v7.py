"""Tests unitaires de microtaches_v7 : non-régression (cas de test_microtaches_v1 rejoués contre v7, sans l'importer ; generer,
echantillon, combiner, evaluer sur un espace fictif) ; dossiers de bloc : dernière version de chaque bloc au lieu du motif figé
dossier_B*_v2.md ; registre central des dossiers : rôles lus et événement écrit dans les dossiers renommés. Noms fictifs."""
import os, io, sys, json, glob, zipfile, unittest, contextlib
from unittest import mock
from aide_tests_v2 import dossier_essai, importer_version, importer, chemin, RACINE_CC
import cc_lib_v4 as L4
M = importer_version('microtaches', 7)
EMP = importer('anonymiser').emp                       # empreinte de l'anonymiseur que microtaches utilise
RENOMMES = dict(regles='consignes_renommees', journal='trace_renommee')
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
SUPPRIMEE = 'Alice Exemple a mesuré 128 valeurs dans la série initiale.'


def lire(f):
    with open(f, encoding='utf-8') as g: return g.read()


def ecrire(f, contenu):
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, 'x', encoding='utf-8') as g: g.write(contenu if isinstance(contenu, str) else json.dumps(contenu, ensure_ascii=False))


def fil(n, texte, genre='fil_relecteur'):
    return f'### Fil {n} ({genre}) — ¶0 1A2B3C4D Méthode\n- [1] **Collègue B** 2026-10-02 : {texte}\n- [2] **CC-Claude** 2026-10-03 : Fait : traité.\n\n'


def preparer(r):
    """Docx révisé (une phrase supprimée) et dossiers d'agents : bloc B1 en v2 (périmée) et v3, bloc B3 en v1 seulement."""
    corps = ('<w:p><w:r><w:t xml:space="preserve">Le protocole décrit la méthode. </w:t></w:r>'
             f'<w:del w:id="1" w:author="Collègue B"><w:r><w:delText>{SUPPRIMEE}</w:delText></w:r></w:del></w:p>')
    docx = os.path.join(r, 'rapport_v1.docx')
    with zipfile.ZipFile(docx, 'x') as z:
        z.writestr('word/document.xml', f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{W}"><w:body>{corps}</w:body></w:document>')
    dd = os.path.join(r, 'agents')
    ecrire(os.path.join(dd, 'dossier_B1_v2.md'), '## Fils\n\n' + fil(12, 'Demande périmée de la v2.') + '## Fin\n')
    ecrire(os.path.join(dd, 'dossier_B1_v3.md'), '## Fils\n\n' + fil(12, "Remplacer par la mesure d'Alice Exemple.") + fil(13, 'repère', 'repere_transcript') + '## Fin\n')
    ecrire(os.path.join(dd, 'dossier_B3_v1.md'), '## Transcript\n\n### T4 — 00:12:30 ¶0 1A2B3C4D Méthode\n- Collègue B (résumé) : préciser la méthode de mesure.\n\n## Fin\n')
    return docx, dd, os.path.join(r, 'sortie')


@contextlib.contextmanager
def espace(nom, renommer=None):
    """Espace fictif (registre des dossiers facultatif, rôles d'anonymisation) pris pour racine le temps du test ;
    l'outil y est chargé à neuf, et calcule donc sa racine comme d'habitude."""
    r = dossier_essai(nom)
    if renommer: ecrire(chemin('outils', '_gestion', 'chemins_v1.json', racine=r), dict(chemins=renommer))
    ecrire(chemin('regles', 'roles_v1.json', racine=r), dict(roles={EMP('Alice'): 'Collègue A', EMP('Exemple'): 'Collègue A'}))
    with mock.patch.object(L4, 'RACINE_CC', r):
        yield r, importer_version('microtaches', 7, alias='microtaches_v7_espace')


def taches(m, docx, dd, out):
    sortie = io.StringIO()
    with contextlib.redirect_stdout(sortie): m.generer([docx, dd, out])
    return json.loads(sortie.getvalue()), {x['id']: x for x in M.charger(os.path.join(out, 'microtaches_v1.jsonl'))}


class RegleRemplacement(unittest.TestCase):
    def d(self, t): return {'type': 'MT-DEMANDE', 'texte': t}

    def test_cas_F310_pas_X_mais_Y(self):   # leçon LC-008 : « ce n'est pas X qu'il faut indiquer ici mais Y » = remplacement
        self.assertEqual(M.regle(self.d("c'est pas l'objectif du projet qu'il faut indiquer ici mais l'objectif du rapport"), 'supprimer'), ('modifier', 'R-REMPLACEMENT'))

    def test_une_phrase_suffit(self):
        self.assertEqual(M.regle(self.d('À retirer : redondant. Une phrase suffit : outils, reproductible.'), 'supprimer')[0], 'modifier')

    def test_question_simple_inchangee(self):
        self.assertEqual(M.regle(self.d('Pas français'), 'question'), ('question', None))

    def test_modifier_jamais_degrade(self):
        self.assertEqual(M.regle(self.d('remplacer par X'), 'modifier'), ('modifier', None))


class RegleManque(unittest.TestCase):
    def p(self, a, b): return {'type': 'MT-PRESENCE', 'a': a, 'b': b}

    def test_reference_perdue_rend_partiel(self):
        self.assertEqual(M.regle(self.p('Exigence A [1] et exigence B [2].', 'Exigence A [1].'), 'oui'), ('partiel', 'R-MANQUE'))

    def test_nombre_perdu_rend_partiel(self):
        self.assertEqual(M.regle(self.p('Série de 128 mesures.', 'Série de mesures.'), 'oui')[0], 'partiel')

    def test_tout_present_reste_oui(self):
        self.assertEqual(M.regle(self.p('Série de 128 mesures [3].', 'La série (128 mesures) [3].'), 'oui'), ('oui', None))


class Valeur(unittest.TestCase):
    def test_json_et_brut(self):
        self.assertEqual(M.valeur('{"r": "non"}'), 'non'); self.assertEqual(M.valeur('partiel'), 'partiel'); self.assertIsNone(M.valeur('???'))

    def test_racine_calculee_comme_avant(self):
        self.assertEqual(M.CC, RACINE_CC)


class DossiersBlocs(unittest.TestCase):
    def test_derniere_version_de_chaque_bloc(self):
        dd = dossier_essai('microtaches_blocs')
        for n in ('dossier_B1_v2.md', 'dossier_B1_v3.md', 'dossier_B2_v1.md', 'dossier_B10_v9.md', 'dossier_B10_v10.md',
                  'dossier_B3_brouillon.md', 'points_B1_v1.json'):
            ecrire(os.path.join(dd, n), '')
        self.assertEqual([os.path.basename(f) for f in M.dossiers_blocs(dd)], ['dossier_B1_v3.md', 'dossier_B10_v10.md', 'dossier_B2_v1.md'])

    def test_aucun_dossier(self):
        self.assertEqual(M.dossiers_blocs(dossier_essai('microtaches_blocs_vide')), [])


class Generer(unittest.TestCase):
    def test_taches_depuis_la_derniere_version_des_blocs(self):
        with espace('microtaches_generer') as (r, m):
            res, T = taches(m, *preparer(r))
            self.assertEqual(res['par_type'], {'MT-DEMANDE': 2, 'MT-PRESENCE': 1}); self.assertTrue(res['cree'])
            self.assertEqual(T['D-B1-F12']['texte'], 'Remplacer par la mesure de Collègue A.')     # v3, anonymisée
            self.assertEqual(T['D-B3-T4']['texte'], 'préciser la méthode de mesure.')             # bloc sans v2
            self.assertNotIn('D-B1-F13', T)                                                         # repère ignoré
            p = [x for x in T.values() if x['type'] == 'MT-PRESENCE'][0]
            self.assertEqual(p['a'], 'Collègue A a mesuré 128 valeurs dans la série initiale.')
            self.assertEqual(p['det']['nombres_disparus'], ['128'])

    def test_meme_contenu_pas_de_nouvelle_version(self):
        with espace('microtaches_versions') as (r, m):
            docx, dd, out = preparer(r)
            taches(m, docx, dd, out); res, _ = taches(m, docx, dd, out)
            self.assertFalse(res['cree']); self.assertEqual(sorted(os.listdir(out)), ['microtaches_v1.jsonl'])
            ev = glob.glob(chemin('journal', '*', '*_microtaches_v7_*.json', racine=r))
            self.assertEqual(len(ev), 2)


class Echantillon(unittest.TestCase):
    def test_stable_et_stratifie(self):
        d = dossier_essai('microtaches_echantillon'); f = os.path.join(d, 'microtaches_v1.jsonl')
        T = [dict(id=f'D-B1-F{i}', type='MT-DEMANDE', genre='fil_relecteur', texte='x') for i in range(5)]
        T += [dict(id=f'D-B1-T{i}', type='MT-DEMANDE', texte='x') for i in range(5)] + [dict(id=f'P-{i}', type='MT-PRESENCE', a='a', b='b') for i in range(5)]
        ecrire(f, ''.join(json.dumps(x) + '\n' for x in T))
        with contextlib.redirect_stdout(io.StringIO()): M.echantillon([f, '2', os.path.join(d, 'e1')]); M.echantillon([f, '2', os.path.join(d, 'e2')])
        E1, E2 = M.charger(os.path.join(d, 'e1', 'echantillon_v1.jsonl')), M.charger(os.path.join(d, 'e2', 'echantillon_v1.jsonl'))
        self.assertEqual(E1, E2); self.assertEqual(len(E1), 6)                  # 2 par strate : fil, segment, présence


class CombinerEvaluer(unittest.TestCase):
    def test_combiner_ajoute_la_ligne_des_regles(self):
        d = dossier_essai('microtaches_combiner')
        ecrire(os.path.join(d, 'microtaches_v1.jsonl'), json.dumps(dict(id='D-B1-F12', type='MT-DEMANDE', texte='Remplacer par la valeur mesurée.')) + '\n')
        ecrire(os.path.join(d, 'resultats_v1.json'), [['m1', 'D-B1-F12', '{"r": "supprimer"}', 100, 5]])
        with contextlib.redirect_stdout(io.StringIO()): M.combiner([os.path.join(d, 'resultats_v1.json'), os.path.join(d, 'microtaches_v1.jsonl'), os.path.join(d, 'out')])
        self.assertEqual(json.loads(lire(os.path.join(d, 'out', 'resultats_combines_v1.json'))),
                         [['m1', 'D-B1-F12', 'supprimer', 100, 5], ['regles+m1', 'D-B1-F12', 'modifier', 100, 5]])

    def test_evaluer_exactitude_par_type(self):
        with espace('microtaches_evaluer') as (r, m):
            ecrire(os.path.join(r, 'resultats_v1.json'), [['m1', 'P-1', 'oui', 10, 1], ['m1', 'D-1', '{"r": "modifier"}', 20, 2]])
            ecrire(os.path.join(r, 'references_v1.json'), dict(references={'P-1': 'oui', 'D-1': 'supprimer'}))
            with contextlib.redirect_stdout(io.StringIO()): m.evaluer([os.path.join(r, 'resultats_v1.json'), os.path.join(r, 'references_v1.json'), os.path.join(r, 'out')])
            res = json.loads(lire(os.path.join(r, 'out', 'banc_local_v1.json')))
            self.assertEqual(res['MT-PRESENCE|m1']['exactitude'], 1.0); self.assertEqual(res['MT-DEMANDE|m1']['exactitude'], 0.0)
            self.assertEqual(len(glob.glob(chemin('journal', '*', '*_microtaches_v*.json', racine=r))), 1)


class Registre(unittest.TestCase):
    def test_regles_et_journal_renommes(self):
        with espace('microtaches_registre', RENOMMES) as (r, m):
            self.assertEqual(m.CC, r)
            self.assertEqual(m.ROLES, {EMP('Alice'): 'Collègue A', EMP('Exemple'): 'Collègue A'})   # rôles lus dans le dossier renommé
            res, T = taches(m, *preparer(r))
            self.assertEqual(T['D-B1-F12']['texte'], 'Remplacer par la mesure de Collègue A.')
            ev = glob.glob(chemin('journal', '*', '*_microtaches_v7_*.json', racine=r))
            self.assertEqual(len(ev), 1)                                          # événement écrit dans le journal renommé
            self.assertTrue(ev[0].startswith(os.path.join(r, 'trace_renommee') + os.sep))
            dossiers = sorted(d for d in os.listdir(r) if os.path.isdir(os.path.join(r, d)))
            self.assertEqual(dossiers, sorted(['consignes_renommees', 'trace_renommee', 'agents', 'sortie', os.path.basename(chemin('outils', racine=r))]))


if __name__ == '__main__':
    unittest.main()
