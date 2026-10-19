"""Suite v3 (16 oct. 2026) : copie de la suite v1, rendue indépendante de la date du jour (dater_journal). Tests de tableau_de_bord_v1 sur un espace fictif isolé (tests/_test_execution/, par dossier_essai) : le candidat est copié dans
l'arbre fictif (outils/tableau_de_bord/) et son amorce y prend la racine de l'espace ; la racine de cc_lib_v4 (journal) est celle de
l'espace fictif le temps de chaque test. (a) Expressions cron : prochaines exécutions (liste, plage, pas, fuseau CRON_TZ, règle OU du
jour du mois et du jour de semaine), refus des expressions invalides ; la page calcule les mêmes dates que l'outil (Node, si présent).
(b) Étapes : début, point, fin, attente (raison pc), appariement et durée, refus (phase, catégorie, raison, titre, identifiant),
importation sans doublon. (c) Agents : lecture des transcriptions (messages comptés une fois), cache incrémental (fichier inchangé
repris, fichier modifié relu, pas de nouvelle version sans changement), vagues, traînard et libellé. (d) Collecte et génération :
résumés sûrs, attentes (propositions, sauvegardes, PC), goulots, planificateur (cron invalide signalé), page HTML aux données
intégrées, nouvelles versions seulement si le contenu change, événements de tenue du tableau exclus. (e) Registre central des
dossiers : tous les dossiers renommés ; sorties et entrées dans les dossiers renommés, aucun dossier créé sous son ancien nom."""
import os, sys, io, re, json, glob, shutil, datetime, itertools, contextlib, subprocess, importlib.util, unittest
from aide_tests_v2 import dossier_essai, chemin_version, chemin, chemins
import cc_lib_v4 as L4

OUTIL, V = 'tableau_de_bord', 1
CANDIDAT = chemin_version(OUTIL, V); _n = itertools.count()
UTC = datetime.timezone.utc


def w(f, texte):
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, 'w', encoding='utf-8') as g: g.write(texte)


def lire(f):
    with open(f, encoding='utf-8') as g: return g.read()


def t(s): return datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))


def charger(cc):
    d = os.path.join(cc, 'outils', OUTIL); os.makedirs(d, exist_ok=True)
    f = os.path.join(d, os.path.basename(CANDIDAT)); shutil.copyfile(CANDIDAT, f)
    s = importlib.util.spec_from_file_location(f'essai_{OUTIL}_{next(_n)}', f); m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m); return m


def ligne(ts, mid, ctx, out, outils=0, modele='claude-opus-5-5'):
    contenu = [dict(type='tool_use', name='Bash')] * outils + [dict(type='text', text='…')]
    return json.dumps(dict(type='assistant', timestamp=ts, message=dict(id=mid, model=modele, content=contenu,
                           usage=dict(input_tokens=ctx, cache_read_input_tokens=0, cache_creation_input_tokens=0, output_tokens=out))))



DATE_FIXE = '2026-10-15T11:00:00Z'


def dater_journal(cc):
    """Suite v3 : les événements écrits par L4.evenement portent la date réelle du jour ; la génération prenait alors « aujourd'hui »
    pour référence, et les étapes fictives du 15 oct. 2026 n'étaient plus « du jour » (G-AT1 absent, G-ET1 en trop) : le test
    échouait à partir du 16 oct. On fixe la date de ces événements à celle des étapes fictives."""
    for f in glob.glob(os.path.join(chemin('journal', racine=cc), '*', '*.json')):
        with open(f, encoding='utf-8') as g: d = json.load(g)
        if d.get('date') != DATE_FIXE:
            d['date'] = DATE_FIXE
            with open(f, 'w', encoding='utf-8') as g: g.write(json.dumps(d, ensure_ascii=False, sort_keys=True, default=str))

class Cron(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.TB = charger(dossier_essai(f'{OUTIL}_v{V}_cron'))

    def iso(self, L): return [self.TB.iso(x) for x in L]

    def test_prochaines(self):
        p = self.TB.prochaines; d = t('2026-10-15T20:21:30Z')
        self.assertEqual(self.iso(p('7,22,37,52 * * * *', d, 3)), ['2026-10-15T20:22:00Z', '2026-10-15T20:37:00Z', '2026-10-15T20:52:00Z'])
        self.assertEqual(self.iso(p('49 11 * * *', d, 2)), ['2026-10-16T11:49:00Z', '2026-10-17T11:49:00Z'])
        self.assertEqual(self.iso(p('*/20 9-10 * * *', d, 7)), ['2026-10-16T09:00:00Z', '2026-10-16T09:20:00Z', '2026-10-16T09:40:00Z',
                                                                '2026-10-16T10:00:00Z', '2026-10-16T10:20:00Z', '2026-10-16T10:40:00Z', '2026-10-17T09:00:00Z'])
        self.assertEqual(self.iso(p('CRON_TZ=America/New_York 45 8 * * 1-5', d, 2)), ['2026-10-16T12:45:00Z', '2026-10-19T12:45:00Z'])   # jeudi soir → vendredi, lundi
        self.assertEqual(self.iso(p('0 0 1 * 1', d, 3, horizon_j=20)), ['2026-10-19T00:00:00Z', '2026-10-26T00:00:00Z', '2026-11-01T00:00:00Z'])   # jour du mois OU lundi
        self.assertEqual(p('0 0 1 * 1', d, 3), [t('2026-10-19T00:00:00Z')])                                  # horizon de 8 jours par défaut
        self.assertEqual(self.iso(p('0 0 * * 7', d, 1)), ['2026-10-18T00:00:00Z'])                          # 7 = dimanche
        self.assertEqual(self.iso(p('22 20 * * *', t('2026-10-15T20:22:00Z'), 1)), ['2026-10-16T20:22:00Z'])   # strictement après

    def test_refus(self):
        for e in ('61 * * * *', '* * *', 'a * * * *', '5-1 * * * *', '* * * 13 *', '*/0 * * * *'):
            with self.assertRaises(ValueError, msg=e): self.TB.analyser_cron(e)

    def test_page_et_outil_concordent(self):
        node = shutil.which('node')
        if not node: self.skipTest('Node absent')
        m = re.search(r'/\*CRON-DEBUT\*/(.*?)/\*CRON-FIN\*/', self.TB.GABARIT, re.S); self.assertTrue(m)
        E = ['7,22,37,52 * * * *', '49 11 * * *', '*/20 9-10 * * *', '0 0 1 * 1', 'CRON_TZ=America/New_York 45 8 * * 1-5', '15 */6 1-7 * *']
        d = '2026-10-15T20:21:30Z'; js = os.path.join(dossier_essai(f'{OUTIL}_v{V}_node'), 'cron_essai.js')
        w(js, m.group(1) + f"\nconst E = {json.dumps(E)};\nconsole.log(JSON.stringify(E.map(e => prochainesCron(e, new Date('{d}'), 4).map(x => x.toISOString().replace('.000', '')))));\n")
        r = subprocess.run([node, js], capture_output=True, text=True, timeout=60); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), [self.iso(self.TB.prochaines(e, t(d), 4)) for e in E])


class Base(unittest.TestCase):
    renommer = False

    def setUp(self):
        self.cc = dossier_essai(f'{OUTIL}_v{V}'); self.defaut = chemins(self.cc)
        if self.renommer:
            w(os.path.join(self.cc, 'outils', '_gestion', 'chemins_v1.json'),
              json.dumps(dict(chemins={k: v + '_renomme' for k, v in self.defaut.items() if k != 'outils'})))
        sauve = (L4.RACINE_CC, os.environ.get('CC_BANC'))

        def restaurer():
            L4.RACINE_CC = sauve[0]
            if sauve[1] is None: os.environ.pop('CC_BANC', None)
            else: os.environ['CC_BANC'] = sauve[1]
        self.addCleanup(restaurer)
        L4.RACINE_CC = self.cc; os.environ.pop('CC_BANC', None)     # espace fictif : événements « réels » de cet espace seulement
        self.TB = charger(self.cc)

    def main(self, *a):
        out = io.StringIO()
        with contextlib.redirect_stdout(out): code = self.TB.main(list(a))
        return code, out.getvalue()

    def agents_fictifs(self):
        """Trois agents : deux dans une vague (débuts à 60 s d'écart), un plus tard ; un message répété (même id) compté une fois."""
        src = os.path.join(self.cc, 'transcriptions', 'abcdef123456', 'subagents')
        w(os.path.join(src, 'agent-a1.jsonl'), '\n'.join([
            json.dumps(dict(type='user', timestamp='2026-10-15T10:00:00.100Z')), ligne('2026-10-15T10:01:00Z', 'm1', 100000, 500, 2),
            ligne('2026-10-15T10:01:00Z', 'm1', 100000, 500, 0), ligne('2026-10-15T10:10:00.500Z', 'm2', 350000, 1500, 1)]) + '\n')
        w(os.path.join(src, 'agent-a1.meta.json'), json.dumps(dict(description='Revue bloc 1', agentType='general-purpose')))
        w(os.path.join(src, 'agent-a2.jsonl'), '\n'.join([json.dumps(dict(type='user', timestamp='2026-10-15T10:01:00Z')),
                                                          ligne('2026-10-15T10:03:00Z', 'n1', 90000, 300, 1, 'claude-sonnet-5-5')]) + '\n')
        w(os.path.join(src, 'agent-a2.meta.json'), json.dumps(dict(description='Revue bloc 2')))
        w(os.path.join(src, 'agent-a3.jsonl'), '\n'.join([json.dumps(dict(type='user', timestamp='2026-10-15T12:00:00Z')),
                                                          ligne('2026-10-15T12:02:00Z', 'p1', 50000, 100)]) + '\n')
        return src


class Etapes(Base):
    def test_debut_point_fin_et_attente(self):
        TB = self.TB
        TB.ecrire_etape('debut', 'T-1', titre='Rapport : jugements', categorie='rapport', quand='2026-10-15T10:00:00Z', tokens=1200)
        TB.ecrire_etape('point', 'T-1', note='moitié faite', quand='2026-10-15T10:30:00Z')
        TB.ecrire_etape('fin', 'T-1', quand='2026-10-15T11:15:00Z', resultat='partiel', tokens=300)
        TB.ecrire_etape('attente', 'A-pc', titre='PC injoignable', raison='pc', quand='2026-10-15T10:20:00Z')
        Et = {s['id']: s for s in TB.etapes_de(TB.evenements())}
        s = Et['T-1']
        self.assertEqual((s['debut'], s['fin'], s['duree_s'], s['resultat'], s['tokens'], s['categorie']),
                         ('2026-10-15T10:00:00Z', '2026-10-15T11:15:00Z', 4500, 'partiel', 1500, 'rapport'))
        self.assertEqual([p['note'] for p in s['points']], ['moitié faite'])
        a = Et['A-pc']; self.assertEqual((a['categorie'], a['raison'], a['fin'], a['duree_s']), ('attente', 'pc', None, None))
        self.assertTrue(all(os.path.dirname(os.path.dirname(f)) == chemin('journal', racine=self.cc)
                            for f in glob.glob(os.path.join(chemin('journal', racine=self.cc), '*', '*.json'))))

    def test_refus(self):
        TB = self.TB
        for k in (dict(phase='commence', id_='X', titre='t'), dict(phase='debut', id_='X', titre='t', categorie='inconnue'),
                  dict(phase='attente', id_='X', titre='t', raison='lune'), dict(phase='debut', id_='X'),
                  dict(phase='debut', id_='un id avec espaces', titre='t'), dict(phase='fin', id_='X', resultat='bof')):
            with self.assertRaises(SystemExit, msg=str(k)): TB.ecrire_etape(**k)
        with self.assertRaises(ValueError): TB.ecrire_etape('debut', 'X', titre='t', quand='hier')
        self.assertEqual(self.main()[0], 2)

    def test_importer_sans_doublon(self):
        f = os.path.join(self.cc, 'etapes.json')
        w(f, json.dumps(dict(etapes=[dict(id='R-1', titre='Reconstituée', categorie='outils', debut='2026-10-15T08:00:00Z', fin='2026-10-15T08:40:00Z'),
                                     dict(id='A-1', titre='Attente', categorie='attente', raison='utilisateur', debut='2026-10-15T09:00:00Z')])))
        self.assertEqual(self.TB.importer_etapes(f), 3); self.assertEqual(self.TB.importer_etapes(f), 0)
        Et = {s['id']: s for s in self.TB.etapes_de(self.TB.evenements())}
        self.assertEqual((Et['R-1']['source'], Et['R-1']['duree_s']), ('reconstitue', 2400))
        self.assertEqual((Et['A-1']['categorie'], Et['A-1']['raison']), ('attente', 'utilisateur'))
        code, out = self.main('importer_etapes', f); self.assertEqual(code, 0); self.assertIn('0 événement', out)


class Agents(Base):
    def test_lecture_cache_et_vagues(self):
        src = self.agents_fictifs(); TB = self.TB
        f1, c1, lus, repris, A = TB.maj_agents([src]); self.assertTrue(c1); self.assertEqual((lus, repris, len(A)), (3, 0, 3))
        a1 = A['abcdef12/agent-a1']
        self.assertEqual((a1['debut'], a1['fin'], a1['duree_s']), ('2026-10-15T10:00:00Z', '2026-10-15T10:10:00Z', 600))
        self.assertEqual((a1['contexte_max'], a1['sortie'], a1['appels'], a1['appels_outils']), (350000, 2000, 2, 3))
        self.assertEqual((a1['description'], a1['modele']), ('Revue bloc 1', 'claude-opus-5-5'))
        self.assertEqual(os.path.dirname(f1), chemin('revues', 'tableau_de_bord', racine=self.cc))
        f2, c2, lus, repris, _ = TB.maj_agents([src]); self.assertFalse(c2); self.assertEqual((f2, lus, repris), (f1, 0, 3))   # rien de relu
        with open(os.path.join(src, 'agent-a3.jsonl'), 'a', encoding='utf-8') as g: g.write(ligne('2026-10-15T12:20:00Z', 'p2', 60000, 50) + '\n')
        f3, c3, lus, repris, A = TB.maj_agents([src]); self.assertTrue(c3); self.assertEqual((lus, repris), (1, 2)); self.assertNotEqual(f3, f1)
        self.assertEqual(A['abcdef12/agent-a3']['duree_s'], 1200)
        shutil.rmtree(os.path.dirname(src))                                            # session disparue : l'historique reste dans le cache
        _, c4, lus, repris, A = TB.maj_agents([src]); self.assertFalse(c4); self.assertEqual(len(A), 3)
        Vg = TB.vagues([dict(a) for a in A.values()])
        self.assertEqual([v['n'] for v in Vg], [2, 1]); self.assertEqual(Vg[0]['libelle'], 'Revue bloc')
        self.assertEqual((Vg[0]['mur_s'], Vg[0]['max_s'], Vg[0]['lourds']), (600, 600, 1))

    def test_trainard(self):
        A = [dict(id=f'a{i}', description=f'Lot {i}', debut=f'2026-10-15T10:0{i}:00Z', fin='2026-10-15T10:30:00Z', duree_s=d, contexte_max=1000,
                  sortie=1, traites=2, modele='m') for i, d in enumerate((60, 60, 200))]
        v = self.TB.vagues(A)[0]; self.assertEqual((v['n'], v['ratio'], v['trainard']), (3, round(200 / 60, 2), 'Lot 2'))
        self.assertEqual(self.TB.libelle(['A2 révision', 'B3 réduction']), 'A2 révision (+1)')


class Generation(Base):
    def preparer(self):
        TB = self.TB; src = self.agents_fictifs()
        os.environ['CC_BANC'] = 'tests'; L4.evenement('outil_x', 1, 'essai', dict(n=1)); os.environ.pop('CC_BANC')
        L4.evenement('tester_outils', 3, 'tests', dict(unitaires=10, unitaires_echecs=0, verdict='conforme', mesures=dict(duree_s=2.5)))
        L4.evenement('detecter_noms', 2, 'detection', dict(noms=['Personne Fictive'], texte='phrase libre à ne pas montrer', n=1))
        TB.ecrire_etape('debut', 'T-1', titre='Travail', categorie='outils', quand='2026-10-15T09:00:00Z')
        TB.ecrire_etape('attente', 'A-pc', titre='PC injoignable', raison='pc', quand='2026-10-15T09:30:00Z')
        w(chemin('taches', 'planificateur_v1.json', racine=self.cc), json.dumps(dict(taches=[
            dict(id='r', nom='Revue', cron='49 11 * * *', besoin_pc=True), dict(id='x', nom='Cassée', cron='99 * * * *')])))
        w(chemin('propositions', 'registre_propositions_v1.json', racine=self.cc), json.dumps(dict(propositions={
            'S-a-v1': dict(type='skill', objet='skill a', evenements=[dict(evenement='proposee', date='2026-10-10 10:00')]),
            'S-b-v1': dict(type='skill', objet='skill b', evenements=[dict(evenement='proposee', date='2026-10-10 10:00'), dict(evenement='acceptee', date='2026-10-11 10:00')]),
            'L-1': dict(type='lecon', objet='leçon', evenements=[dict(evenement='modification_demandee', date='2026-10-14 10:00')])})))
        es = os.path.join(self.cc, 'etat_sync.json')
        w(es, json.dumps(dict(base='manifeste_pc_20261015_192944.txt', attente={'20261015_180255': dict(copies=[['a', 'h'], ['b', 'h']])})))
        dater_journal(self.cc)
        return src, es

    def test_generer_page_et_versions(self):
        src, es = self.preparer(); TB = self.TB
        code, out = self.main('generer', '--source', src, '--etat-sync', es); self.assertEqual(code, 0, out)
        R = chemin('revues', 'tableau_de_bord', racine=self.cc)
        h1 = os.path.join(R, 'tableau_de_bord_v1.html'); d1 = os.path.join(R, 'donnees_tableau_v1.json')
        self.assertTrue(os.path.exists(h1) and os.path.exists(d1))
        page = lire(h1); m = re.search(r'<script type="application/json" id="donnees">(.*?)</script>', page, re.S)
        D = json.loads(m.group(1)); self.assertEqual(D, json.loads(lire(d1)))
        self.assertIn('<title>Tableau de bord du flux</title>', page); self.assertNotIn('__DONNEES__', page)
        self.assertNotIn('Personne Fictive', page); self.assertNotIn('phrase libre', page)                   # résumés sûrs seulement
        det = [e for e in D['journal_recent'] if e.get('outil') == 'detecter_noms'][0]['resume']; self.assertEqual(det, dict(n=1, noms='1 él.'))
        self.assertEqual(D['planificateur']['erreurs'][0][:6], 'x : ch')
        self.assertTrue([x for x in D['planificateur']['taches'] if x['id'] == 'x'][0]['cron_invalide'])
        self.assertEqual(sorted(p['id'] for p in D['attentes']['propositions']), ['L-1', 'S-a-v1'])
        self.assertEqual(D['attentes']['pc'], dict(injoignable=True, depuis='2026-10-15T09:30:00Z', etape='A-pc'))
        sv = D['attentes']['sauvegardes']; self.assertEqual((len(sv['non_confirmees']), sv['non_confirmees'][0]['fichiers'], sv['derniere_complete']),
                                                             (1, 2, '2026-10-15T19:29:44Z'))
        codes = {g['code'] for g in D['goulots']}; self.assertTrue({'G-SY1', 'G-PR1', 'G-AG2', 'G-OU1', 'G-AT1'} <= codes, codes)
        self.assertEqual(D['tests'][-1]['verdict'], 'conforme'); self.assertEqual(D['totaux']['essais'], 1)
        self.assertEqual(len(D['agents']), 3); self.assertNotIn('taille', D['agents'][0])
        code, out = self.main('generer', '--source', src, '--etat-sync', es)                       # rien de neuf : mêmes versions
        self.assertIn('(inchangée)', out); self.assertFalse(os.path.exists(os.path.join(R, 'tableau_de_bord_v2.html')))
        self.TB.ecrire_etape('fin', 'T-1', quand='2026-10-15T12:00:00Z')
        self.main('generer', '--source', src, '--etat-sync', es); self.assertTrue(os.path.exists(os.path.join(R, 'tableau_de_bord_v2.html')))
        types = [json.loads(lire(f))['type'] for f in glob.glob(os.path.join(chemin('journal', racine=self.cc), '*', '*.json'))]
        self.assertGreaterEqual(types.count('generation'), 3)

    def test_etat_et_cron_en_ligne(self):
        src, es = self.preparer(); self.TB.maj_agents([src])
        code, out = self.main('etat', '--etat-sync', es); self.assertEqual(code, 0)
        self.assertIn('en cours : T-1', out); self.assertIn('G-SY1', out); self.assertIn('planifié : Revue', out)
        code, out = self.main('cron', '0 12 * * *', '--n', '2'); self.assertEqual(len(out.split()), 2)


class RegistreRenomme(Generation):
    renommer = True

    def test_dossiers_renommes(self):
        src, es = self.preparer(); self.main('generer', '--source', src, '--etat-sync', es)
        R = chemin('revues', 'tableau_de_bord', racine=self.cc); self.assertTrue(R.endswith('_renomme' + os.sep + 'tableau_de_bord'))
        self.assertTrue(os.path.exists(os.path.join(R, 'tableau_de_bord_v1.html')))
        D = json.loads(lire(os.path.join(R, 'donnees_tableau_v1.json')))
        self.assertTrue(D['planificateur']['source'].startswith(self.defaut['taches'] + '_renomme/'))
        self.assertEqual(len(D['attentes']['propositions']), 2)
        for k, v in self.defaut.items():
            if k != 'outils': self.assertFalse(os.path.exists(os.path.join(self.cc, v)), f'dossier créé sous son ancien nom : {v}')


if __name__ == '__main__':
    unittest.main()
