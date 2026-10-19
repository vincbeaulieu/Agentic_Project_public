"""Tests unitaires de delegation_v3 (reprend toute la suite de delegation_v2, plus la classe HorsSchema). Non-régression : ouvrir, resultat et type (champs exigés,
écriture versionnée sans écrasement, « inchangé » si le contenu ne change pas, événements du journal) ; verifier (code de
sortie, problèmes signalés, dernière version de chaque fichier) ; bilan (tableau des résultats, types de tâches, à reprendre,
nouvelle version seulement si le contenu change). Registre central des dossiers : délégations, types de tâches et journal
renommés par outils/_gestion/chemins_v1.json, lus et écrits sous leur nouveau nom. Chaque essai tourne dans un espace fictif
(tests/_test_execution/, par dossier_essai) : la racine de l'outil et le journal de cc_lib_v4 y sont redirigés le temps du test."""
import os, io, sys, glob, json, contextlib, unittest
from unittest import mock
from aide_tests_v2 import dossier_essai, importer_version, chemin, chemins
import cc_lib_v1 as L1, cc_lib_v4 as L4

D = importer_version('delegation', 3)
DELEG_RENOMME, TACHES_RENOMME, JOURNAL_RENOMME = 'suivi_agents', 'types_de_travaux', 'evenements_consignes'   # noms fictifs
MESURES_A = dict(qualite=1.0, alignement=1.0, duree_min=12, tokens=3400, outils_appels=20, octets_sortie=900, part_automatique=0.5)
MESURES_B = dict(qualite=0.8, alignement=0.9, duree_min=7, tokens=1200, outils_appels=9, octets_sortie=400, part_automatique=0.25)


def delegation(id='D-9001', type_tache='type_essai', agents=('agent-a', 'agent-b'), evaluateur='python3 evaluateur_essai_v1.py', brief='brief_essai_v1.md'):
    return dict(id=id, date='2026-10-15', type_tache=type_tache, brief=brief, schema_sortie='{"constats": []}', evaluateur=evaluateur,
                agents=[dict(nom=a, modele='modele-local', perimetre='bloc 1') for a in agents], dossier='99_essai')


def resultat(agent, id='D-9001', verdict='BILAN conforme', mesures=MESURES_A):
    return dict(id=id, agent=agent, verdict_evaluateur=verdict, mesures=mesures, constats=[], remarques='')


def type_tache(etapes=(('compter', 'automatisee', 'outil_essai'), ('juger', 'non_automatisable', None)), nom='type_essai'):
    return dict(type=nom, description='Type de tâche fictif.', schema_sortie='{}', evaluateur='python3 evaluateur_essai_v1.py',
                etapes_automatisables=[dict(etape=e, statut=s, **({'outil': o} if o else {})) for e, s, o in etapes])


def espace(nom, registre=None):
    r = dossier_essai(nom)
    if registre:
        g = chemin('outils', '_gestion', racine=r); os.makedirs(g)
        with open(os.path.join(g, 'chemins_v1.json'), 'x', encoding='utf-8') as f: json.dump(dict(chemins=registre), f)
    os.makedirs(os.path.join(r, 'saisies'))
    return r


def saisie(r, obj):
    """Fichier JSON d'entrée de l'outil, dans le sous-dossier « saisies » de l'espace fictif (un nouveau fichier par appel)."""
    d = os.path.join(r, 'saisies'); f = os.path.join(d, f'saisie_{len(os.listdir(d)) + 1}.json')
    with open(f, 'x', encoding='utf-8') as g: json.dump(obj, g, ensure_ascii=False)
    return f


def lancer(r, *args):
    """Lance delegation_v3 (main) dans l'espace fictif r ; rend (code de sortie, sortie standard)."""
    with mock.patch.object(D, 'CC', r), mock.patch.object(L4, 'RACINE_CC', r), mock.patch.object(sys, 'argv', ['delegation_v3.py', *args]), \
            contextlib.redirect_stdout(io.StringIO()) as s:
        try: D.main(); code = 0
        except SystemExit as e: code = e.code
    return code, s.getvalue()


def evenements(r):
    L = []
    for f in sorted(glob.glob(os.path.join(chemin('journal', racine=r), '*', '*_delegation_v3_*.json'))):
        with open(f, encoding='utf-8') as g: L.append(dict(json.load(g), fichier=f))
    return L


def lire(f):
    with open(f, encoding='utf-8') as g: return g.read()


def peupler(r):
    """Une délégation complète : deux agents, deux résultats, type de tâche décrit sans étape à faire."""
    for o, cmd in ((delegation(), 'ouvrir'), (resultat('agent-a'), 'resultat'),
                   (resultat('agent-b', verdict='BILAN : 2 occurrence(s)', mesures=MESURES_B), 'resultat'), (type_tache(), 'type')):
        code, _ = lancer(r, cmd, saisie(r, o)); assert code == 0


class Garde(unittest.TestCase):
    def tearDown(self):
        self.assertFalse(glob.glob(chemin('delegations', 'D-9*_v*.json')) + glob.glob(chemin('taches', 'type_essai_v*.json')),
                         "un essai a écrit dans l'espace réel")


class NonRegression(Garde):
    def test_racine_et_bibliotheque(self):
        self.assertEqual(D.CC, L1.RACINE_CC); self.assertTrue(os.path.isdir(chemin('outils', racine=D.CC)))
        self.assertIs(D.chemin, L4.chemin); self.assertIs(D.evenement, L4.evenement)   # journal résolu par le registre
        self.assertEqual(D.dossiers(), (chemin('delegations', racine=D.CC), chemin('taches', racine=D.CC)))

    def test_ouvrir(self):
        r = espace('deleg_ouvrir'); o = delegation()
        code, out = lancer(r, 'ouvrir', saisie(r, o))
        f = chemin('delegations', 'D-9001_v1.json', racine=r)
        self.assertEqual((code, out), (0, 'écrit ' + os.path.relpath(f, r) + '\n'))
        self.assertEqual(lire(f), json.dumps(o, ensure_ascii=False, indent=1, sort_keys=True) + '\n')
        ev = evenements(r); self.assertEqual(len(ev), 1)
        self.assertEqual((ev[0]['outil'], ev[0]['version'], ev[0]['type']), ('delegation', 3, 'ouverture'))
        self.assertEqual(ev[0]['donnees'], dict(id='D-9001', type='type_essai', agents=['agent-a', 'agent-b'], banc=True))

    def test_ouvrir_sans_ecrasement(self):
        r = espace('deleg_versions')
        lancer(r, 'ouvrir', saisie(r, delegation()))
        v1 = chemin('delegations', 'D-9001_v1.json', racine=r); avant = lire(v1)
        code, out = lancer(r, 'ouvrir', saisie(r, delegation()))   # même contenu : rien de nouveau
        self.assertEqual((code, out), (0, 'inchangé ' + os.path.relpath(v1, r) + '\n'))
        self.assertEqual(len(evenements(r)), 1)
        code, out = lancer(r, 'ouvrir', saisie(r, delegation(agents=('agent-a', 'agent-b', 'agent-c'))))
        v2 = chemin('delegations', 'D-9001_v2.json', racine=r)
        self.assertEqual(out, 'écrit ' + os.path.relpath(v2, r) + '\n'); self.assertEqual(lire(v1), avant)   # v1 intacte
        self.assertEqual(len(evenements(r)), 2)

    def test_champs_manquants(self):
        r = espace('deleg_champs')
        o = {k: v for k, v in delegation().items() if k != 'evaluateur'}
        self.assertEqual(lancer(r, 'ouvrir', saisie(r, o)), ("champs manquants : ['evaluateur']", ''))
        o = {k: v for k, v in resultat('agent-a').items() if k not in ('mesures', 'constats')}
        self.assertEqual(lancer(r, 'resultat', saisie(r, o))[0], "champs manquants : ['mesures', 'constats']")
        o = {k: v for k, v in type_tache().items() if k != 'etapes_automatisables'}
        self.assertEqual(lancer(r, 'type', saisie(r, o))[0], "champs manquants : ['etapes_automatisables']")
        for d in (chemin('delegations', racine=r), chemin('taches', racine=r)): self.assertFalse(os.path.exists(d), d)   # rien d'écrit
        self.assertEqual(evenements(r), [])

    def test_resultat(self):
        r = espace('deleg_resultat')
        code, out = lancer(r, 'resultat', saisie(r, resultat('agent-a')))
        f = chemin('delegations', 'D-9001_agent-a_resultat_v1.json', racine=r)
        self.assertEqual((code, out), (0, 'écrit ' + os.path.relpath(f, r) + '\n'))
        ev = evenements(r); self.assertEqual(len(ev), 1); self.assertEqual(ev[0]['type'], 'resultat')
        self.assertEqual(ev[0]['donnees'], dict(id='D-9001', agent='agent-a', verdict='BILAN conforme', mesures=MESURES_A, banc=True))

    def test_type(self):
        r = espace('deleg_type')
        code, out = lancer(r, 'type', saisie(r, type_tache()))
        f = chemin('taches', 'type_essai_v1.json', racine=r)
        self.assertEqual((code, out), (0, 'écrit ' + os.path.relpath(f, r) + '\n'))
        self.assertEqual(json.loads(lire(f)), type_tache()); self.assertEqual(evenements(r), [])   # pas d'événement pour un type

    def test_verifier_conforme(self):
        r = espace('deleg_verifier'); peupler(r)
        self.assertEqual(lancer(r, 'verifier'), (0, '1 délégations, 2 résultats, 1 types ; à reprendre : 0\n'))

    def test_verifier_a_reprendre(self):
        r = espace('deleg_verifier_pb')
        lancer(r, 'ouvrir', saisie(r, delegation(type_tache='type_absent')))
        lancer(r, 'resultat', saisie(r, resultat('agent-a')))
        lancer(r, 'ouvrir', saisie(r, delegation(id='D-9002', agents=('agent-c',), evaluateur='')))
        lancer(r, 'type', saisie(r, type_tache()))
        code, out = lancer(r, 'verifier')
        taches = os.path.relpath(chemin('taches', racine=r), r)
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), ['2 délégations, 1 résultats, 1 types ; à reprendre : 4',
                                            '   D-9001 : pas de résultat pour agent-b',
                                            f'   D-9001 : type de tâche type_absent non décrit ({taches}/)',
                                            '   D-9002 : sans évaluateur',
                                            '   D-9002 : pas de résultat pour agent-c'])

    def test_verifier_etapes_a_automatiser(self):
        r = espace('deleg_a_faire'); peupler(r)
        lancer(r, 'type', saisie(r, type_tache(etapes=(('juger', 'a_faire', None), ('relire', 'a_faire', None), ('compter', 'automatisee', 'x')))))
        code, out = lancer(r, 'verifier')   # étapes à automatiser : signalées, non bloquantes
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ['1 délégations, 2 résultats, 1 types ; à reprendre : 1',
                                            '   type type_essai : 2 étape(s) à automatiser : juger ; relire'])

    def test_dernieres_versions(self):
        r = espace('deleg_dernieres'); peupler(r)
        lancer(r, 'ouvrir', saisie(r, delegation(agents=('agent-a', 'agent-d'))))   # v2 : agent-d sans résultat
        self.assertEqual(lancer(r, 'verifier')[0], 1)
        lancer(r, 'ouvrir', saisie(r, delegation(agents=('agent-a',))))   # v3 : seul agent-a, qui a un résultat
        self.assertTrue(os.path.exists(chemin('delegations', 'D-9001_v3.json', racine=r)))
        self.assertEqual(lancer(r, 'verifier'), (0, '1 délégations, 2 résultats, 1 types ; à reprendre : 0\n'))

    def test_bilan(self):
        r = espace('deleg_bilan'); peupler(r)
        code, out = lancer(r, 'bilan')
        f = chemin('delegations', 'bilan_delegations_v1.md', racine=r)
        self.assertEqual((code, out), (0, 'bilan_delegations_v1.md nouvelle version\n'))
        attendu = ['# Bilan des délégations', '', 'Généré par `outils/delegation_v3.py bilan`.', '',
                   '| Délégation | Agent | Verdict de l’évaluateur | Qualité | Alignement | Durée (min) | Tokens | Part automatique |',
                   '|---|---|---|---|---|---|---|---|',
                   '| D-9001 | agent-a | BILAN conforme | 1.0 | 1.0 | 12 | 3400 | 0.5 |',
                   '| D-9001 | agent-b | BILAN : 2 occurrence(s) | 0.8 | 0.9 | 7 | 1200 | 0.25 |',
                   '', '## Types de tâches et automatisation', '',
                   '### type_essai', 'Type de tâche fictif.', '- [automatisee] compter — `outil_essai`', '- [non_automatisable] juger', '',
                   '## À reprendre', '']
        self.assertEqual(lire(f), '\n'.join(attendu) + '\n')
        self.assertEqual(lancer(r, 'bilan'), (0, 'bilan_delegations_v1.md inchangé\n'))   # même contenu : pas de v2
        lancer(r, 'resultat', saisie(r, resultat('agent-b')))   # nouveau résultat de agent-b : le bilan change
        self.assertEqual(lancer(r, 'bilan'), (0, 'bilan_delegations_v2.md nouvelle version\n'))
        self.assertIn('| D-9001 | agent-b | BILAN conforme | 1.0 |', lire(chemin('delegations', 'bilan_delegations_v2.md', racine=r)))
        self.assertEqual(lire(f), '\n'.join(attendu) + '\n')   # v1 intacte


class Registre(Garde):
    """outils/_gestion/chemins_v1.json renomme les délégations, les types de tâches et le journal : l'outil lit et écrit sous
    les nouveaux noms, jamais sous les anciens."""
    REGISTRE = dict(delegations=DELEG_RENOMME, taches=TACHES_RENOMME, journal=JOURNAL_RENOMME)

    def setUp(self):
        self.vide = dossier_essai('deleg_registre_defauts')   # espace sans registre : noms par défaut

    def test_ecriture_sous_les_noms_du_registre(self):
        r = espace('deleg_registre', registre=self.REGISTRE)
        with mock.patch.object(D, 'CC', r): self.assertEqual(D.dossiers(), (os.path.join(r, DELEG_RENOMME), os.path.join(r, TACHES_RENOMME)))
        self.assertEqual(lancer(r, 'ouvrir', saisie(r, delegation())), (0, 'écrit ' + os.path.join(DELEG_RENOMME, 'D-9001_v1.json') + '\n'))
        self.assertEqual(lancer(r, 'resultat', saisie(r, resultat('agent-a')))[1],
                         'écrit ' + os.path.join(DELEG_RENOMME, 'D-9001_agent-a_resultat_v1.json') + '\n')
        self.assertEqual(lancer(r, 'type', saisie(r, type_tache()))[1], 'écrit ' + os.path.join(TACHES_RENOMME, 'type_essai_v1.json') + '\n')
        for f in (os.path.join(r, DELEG_RENOMME, 'D-9001_v1.json'), os.path.join(r, DELEG_RENOMME, 'D-9001_agent-a_resultat_v1.json'),
                  os.path.join(r, TACHES_RENOMME, 'type_essai_v1.json')):
            self.assertTrue(os.path.isfile(f), f)
        ev = evenements(r); self.assertEqual(sorted(e['type'] for e in ev), ['ouverture', 'resultat'])
        self.assertTrue(all(e['fichier'].startswith(os.path.join(r, JOURNAL_RENOMME) + os.sep) for e in ev))
        for cle in self.REGISTRE: self.assertFalse(os.path.exists(os.path.join(r, chemins(self.vide)[cle])), cle)   # ancien nom jamais créé

    def test_lecture_sous_les_noms_du_registre(self):
        r = espace('deleg_registre_lecture', registre=self.REGISTRE); peupler(r)
        ancien = os.path.join(r, chemins(self.vide)['delegations']); os.makedirs(ancien)   # leurre sous l'ancien nom : à ignorer
        with open(os.path.join(ancien, 'D-9009_v1.json'), 'x', encoding='utf-8') as g: json.dump(delegation(id='D-9009', evaluateur=''), g)
        self.assertEqual(lancer(r, 'verifier'), (0, '1 délégations, 2 résultats, 1 types ; à reprendre : 0\n'))
        self.assertEqual(lancer(r, 'bilan'), (0, 'bilan_delegations_v1.md nouvelle version\n'))
        self.assertTrue(os.path.isfile(os.path.join(r, DELEG_RENOMME, 'bilan_delegations_v1.md')))
        self.assertEqual(os.listdir(ancien), ['D-9009_v1.json'])   # rien d'écrit sous l'ancien nom
        lancer(r, 'ouvrir', saisie(r, delegation(id='D-9003', type_tache='type_absent', agents=('agent-a',))))
        lancer(r, 'resultat', saisie(r, resultat('agent-a', id='D-9003')))
        code, out = lancer(r, 'verifier')   # le message désigne le dossier des types sous son nouveau nom
        self.assertEqual(code, 0); self.assertIn(f'   D-9003 : type de tâche type_absent non décrit ({TACHES_RENOMME}/)', out.splitlines())



class HorsSchema(Garde):
    """v3 : le dossier des types (clé « taches ») contient aussi le planificateur et des étapes reconstituées, qui ne sont pas des
    types de tâches. v2 plantait (KeyError « etapes_automatisables ») ; v3 les ignore et les signale, sans erreur."""
    def test_fichier_hors_schema_signale_sans_planter(self):
        r = espace('hors_schema'); peupler(r)
        dt = chemin('taches', racine=r)
        with open(os.path.join(dt, 'planificateur_v1.json'), 'x', encoding='utf-8') as g: json.dump(dict(note='plan', taches=[]), g)
        code, out = lancer(r, 'verifier')
        self.assertEqual(code, 0, out)
        self.assertIn('hors schéma', out); self.assertIn('planificateur', out)
        self.assertIn('1 types', out)
        code, out = lancer(r, 'bilan'); self.assertEqual(code, 0, out)

    def test_delegation_sans_agents_signalee(self):
        r = espace('sans_agents'); peupler(r)
        d = delegation(id='D-9002'); d.pop('agents')
        dd = chemin('delegations', racine=r)
        with open(os.path.join(dd, 'D-9002_v1.json'), 'x', encoding='utf-8') as g: json.dump(d, g)
        code, out = lancer(r, 'verifier')
        self.assertIn('D-9002 : sans liste d’agents', out)

if __name__ == '__main__':
    unittest.main()
