"""Suite v5 (16 oct. 2026) : copie de la v4 ; Equivalence ne compare plus « etat_au » à la seconde près quand l'espace est vide (Python et JavaScript lisent alors l'horloge à des instants différents : test fragile, échec du 16 oct. à 18 h 56). Suite v4 (16 oct. 2026) : copie de la suite v2, qui rejoue la suite v3 (v1 indépendante de la date). Tests de tableau_de_bord_v2. (a) Non-régression : toute la suite v1 (cron, étapes, agents, génération, registre des dossiers
renommés) est rejouée sur la version 2. (b) Ajouts de la v2 :
- arrondi déterministe « moitié vers le haut », identique en Python et en JavaScript ;
- goulots avec paramètres, et un texte français et anglais pour chaque code émis ;
- bouton FR / EN : chaque texte fixe et chaque clé t('…') existe dans les deux langues ;
- ouvrier LM Studio : file absente, état et lots en entrée, goulots G-LM1 (y compris le statut « arrêté » mal décodé par
  PowerShell 5.1) et G-LM2 ;
- commande « brut » : format du serveur local (M, E dans l'ordre binaire des clés, F) ;
- équivalence de l'agrégateur JavaScript de la page et de collecter() sur un espace fictif (Node) ;
- page : bascule de langue, indicateur de mode, script valide (node --check)."""
import os, sys, re, json, glob, shutil, subprocess, unittest
from aide_tests_v2 import dossier_essai, chemin_version, chemin
import cc_lib_v4 as L4
import test_tableau_de_bord_v3 as T1   # suite v1 rendue indépendante de la date (v4)

OUTIL, V = 'tableau_de_bord', 2
CANDIDAT2 = chemin_version(OUTIL, V)
NODE = shutil.which('node')


class SurV2:
    """Rejoue une classe de la suite v1 avec la version 2 (le candidat copié dans l'espace fictif), puis restaure."""
    @classmethod
    def setUpClass(cls):
        cls._sauve = T1.CANDIDAT; T1.CANDIDAT = CANDIDAT2
        if hasattr(super(), 'setUpClass'): super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        T1.CANDIDAT = cls._sauve


class CronV1SurV2(SurV2, T1.Cron): pass
class EtapesV1SurV2(SurV2, T1.Etapes): pass
class AgentsV1SurV2(SurV2, T1.Agents): pass
class GenerationV1SurV2(SurV2, T1.Generation): pass
class RegistreV1SurV2(SurV2, T1.RegistreRenomme): pass


class BaseV2(SurV2, T1.Base):
    def setUp(self):
        """Comme T1.Base, mais l'espace est un sous-dossier 00_competences_claude d'un dossier Revision fictif propre au test :
        la file LM Studio (Revision/00_espace_cloud_claude/file_lmstudio) d'un test ne touche ainsi aucun autre test."""
        T1.CANDIDAT = CANDIDAT2
        self.rev = dossier_essai(f'{OUTIL}_v{V}'); self.cc = os.path.join(self.rev, '00_competences_claude'); os.makedirs(self.cc)
        self.defaut = T1.chemins(self.cc)
        sauve = (L4.RACINE_CC, os.environ.get('CC_BANC'))

        def restaurer():
            L4.RACINE_CC = sauve[0]
            if sauve[1] is None: os.environ.pop('CC_BANC', None)
            else: os.environ['CC_BANC'] = sauve[1]
        self.addCleanup(restaurer)
        L4.RACINE_CC = self.cc; os.environ.pop('CC_BANC', None)
        self.TB = T1.charger(self.cc)

    def evt(self, date, outil, type_, donnees):
        """Événement écrit à une date choisie (nom de fichier ordonné comme ceux de cc_lib)."""
        j = os.path.join(chemin('journal', racine=self.cc), date[:10]); n = date.replace('-', '').replace(':', '').replace('T', '_')[:15]
        T1.w(os.path.join(j, f'{n}_{outil}_v1_{abs(hash((date, outil, type_))) % 10**8:08d}.json'),
             json.dumps(dict(date=date, outil=outil, version=1, type=type_, donnees=donnees), ensure_ascii=False))

    def espace_complet(self):
        """Espace fictif riche : étapes (dont une « quand » au format court), essais, tests, mesures, agents, propositions, planificateur."""
        g = T1.Generation.preparer.__get__(self); src, es = g()
        TB = self.TB
        TB.ecrire_etape('point', 'T-1', note='à moitié', quand='2026-10-15 09:40')
        TB.ecrire_etape('debut', 'T-2', titre='Deuxième', categorie='rapport', quand='2026-10-15T09:05:30.250Z', tokens=40)
        TB.ecrire_etape('fin', 'T-2', quand='2026-10-15T09:50:00Z', note='fini')
        L4.evenement('auditer_espace', 4, 'audit', dict(verdict='conforme', n=3, liste=[1, 2], mesures=dict(duree_s=1.25)))
        L4.evenement('auditer_espace', 4, 'audit', dict(verdict='conforme', n=4, mesures=dict(duree_s=True)))     # booléen : pas une durée
        self.evt('2099-01-01T00:00:00Z', 'tester_outils', 'tests', dict(unitaires=5, unitaires_echecs=1, verdict='non conforme', banc=True))   # le dernier, d'essai
        TB.maj_agents([src])
        return src, es


class Arrondi(BaseV2):
    def test_moitie_vers_le_haut(self):
        a = self.TB.arr
        self.assertEqual((a(2.5), a(3.5), a(0.5), a(-0.5)), (3, 4, 1, 0))
        self.assertEqual((a(1.005, 2), a(3.335, 2), a(200 / 60, 2)), (1.0, 3.34, 3.33))
        self.assertEqual((self.TB.fr(2.5, 0), self.TB.fr(79.75), self.TB.fr(3.0)), ('3', '79,8', '3'))

    def test_meme_arrondi_en_javascript(self):
        if not NODE: self.skipTest('Node absent')
        m = re.search(r'/\*AGREGER-DEBUT\*/(.*?)/\*AGREGER-FIN\*/', self.TB.GABARIT, re.S)
        X = [(2.5, 0), (0.125, 2), (1.005, 2), (3.335, 2), (200 / 60, 2), (79.75, 1), (-0.5, 0), (12345.6789, 2)]
        js = os.path.join(dossier_essai(f'{OUTIL}_v{V}_arrondi'), 'arrondi.js')
        T1.w(js, m.group(1) + f'\nconsole.log(JSON.stringify({json.dumps(X)}.map(([x, d]) => AG.arr(x, d))));\n')
        r = subprocess.run([NODE, js], capture_output=True, text=True, timeout=60); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), [self.TB.arr(x, d) for x, d in X])


class GoulotsEtLangues(BaseV2):
    def test_params_et_textes_dans_les_deux_langues(self):
        self.espace_complet(); D = self.TB.collecter(etat_sync=os.path.join(self.cc, 'etat_sync.json'), lmstudio=False)
        self.assertTrue(D['goulots'])
        for g in D['goulots']:
            self.assertIsInstance(g['params'], dict, g['code']); self.assertTrue(g['titre'] and g['preuve'] and g['piste'])
        codes = set(re.findall(r"g\('(G-[A-Z]{2}\d)'", open(CANDIDAT2, encoding='utf-8').read()))
        G = self.TB.GABARIT; fr = G[G.index('const GT = {'):G.index('en: {', G.index('const GT = {'))]; en = G[G.index('en: {', G.index('const GT = {')):G.index('}};', G.index('const GT = {'))]
        self.assertGreaterEqual(len(codes), 11)
        for c in codes:
            self.assertIn(f"'{c}'", fr, c); self.assertIn(f"'{c}'", en, c)
        self.assertIn('G-TE1', {g['code'] for g in D['goulots']})                        # derniers tests (même d'essai) non conformes

    def test_textes_fixes_et_cles(self):
        G = self.TB.GABARIT; js = G[G.index('const TXT = {'):G.index('const GT = {')]
        fr, en = js[js.index('fr: {'):js.index('en: {')], js[js.index('en: {'):]
        cles = set(re.findall(r'data-t="(\w+)"', G)) | set(re.findall(r"\bt\('(\w+)'", G))
        self.assertGreater(len(cles), 60)
        manque = [k for k in sorted(cles) if not re.search(r'\b' + k + r':', fr) or not re.search(r'\b' + k + r':', en)]
        self.assertEqual(manque, [])
        self.assertIn('data-lang="fr"', G); self.assertIn('data-lang="en"', G); self.assertIn('id="mode"', G)
        self.assertIn("localStorage.setItem('tdb-langue'", G)

    def test_script_valide(self):
        if not NODE: self.skipTest('Node absent')
        G = self.TB.GABARIT; s = G[G.index('<script>\n(function(){') + len('<script>\n'):G.rindex('</script>')]
        f = os.path.join(dossier_essai(f'{OUTIL}_v{V}_script'), 'page.js'); T1.w(f, s)
        r = subprocess.run([NODE, '--check', f], capture_output=True, text=True, timeout=60); self.assertEqual(r.returncode, 0, r.stderr)


class LMStudio(BaseV2):
    def file(self):
        F = os.path.join(self.rev, '00_espace_cloud_claude', 'file_lmstudio')
        os.makedirs(os.path.join(F, 'entree'), exist_ok=True); os.makedirs(os.path.join(F, 'journal'), exist_ok=True)
        return F

    def test_absente(self):
        self.assertIsNone(self.TB.lire_lmstudio(os.path.join(self.cc, 'pas_de_file')))

    def test_etat_lots_et_goulots(self):
        F = self.file(); T1.w(os.path.join(F, 'entree', 'lot1.jsonl'), '{}\n'); T1.w(os.path.join(F, 'entree', 'note.txt'), 'x')
        lm = self.TB.lire_lmstudio(F); self.assertEqual(lm, dict(etat=None, lots_entree=1))
        codes = lambda lm: [g['code'] for g in self.TB.collecter(etat_sync=None, lmstudio=lm)['goulots'] if g['code'].startswith('G-LM')]
        self.assertEqual(codes(lm), ['G-LM1'])
        for st in ('arrêté', 'arrÃªtÃ©'):                                              # accents mal décodés par PowerShell 5.1
            with open(os.path.join(F, 'journal', 'etat.json'), 'w', encoding='utf-8-sig') as g: json.dump(dict(statut=st, raison_arret='file vide', en_attente=0), g)
            self.assertEqual(codes(self.TB.lire_lmstudio(F)), ['G-LM1'])
        T1.w(os.path.join(F, 'journal', 'etat.json'), json.dumps(dict(statut='attente de LM Studio', en_attente=4)))
        lm = self.TB.lire_lmstudio(F); self.assertEqual(codes(lm), ['G-LM2'])
        D = self.TB.collecter(etat_sync=None, lmstudio=lm); self.assertEqual(D['lmstudio']['etat']['en_attente'], 4)
        self.assertEqual([g for g in D['goulots'] if g['code'] == 'G-LM2'][0]['params'], dict(en_attente=4))
        T1.w(os.path.join(F, 'journal', 'etat.json'), json.dumps(dict(statut='actif', en_attente=2)))
        self.assertEqual(codes(self.TB.lire_lmstudio(F)), [])


class Brut(BaseV2):
    def test_format(self):
        self.espace_complet(); f = os.path.join(self.cc, 'brut.txt')
        code, _ = self.main('brut', '--sortie', f); self.assertEqual(code, 0)
        L = open(f, encoding='utf-8').read().split('\n'); self.assertEqual(L[-1], '')
        meta = json.loads(L[0].split('\t', 1)[1]); E = [l.split('\t') for l in L if l.startswith('E\t')]
        cles = [e[1] for e in E]; self.assertEqual(cles, sorted(cles)); self.assertEqual(meta['curseur'], cles[-1]); self.assertEqual(meta['n'], len(E))
        self.assertTrue(all(len(e) == 3 and json.loads(e[2])['outil'] for e in E))
        F = {l.split('\t')[1]: l.split('\t') for l in L if l.startswith('F\t')}
        self.assertEqual(sorted(F), ['agents', 'planificateur', 'registre'])
        self.assertTrue(F['planificateur'][2].endswith('planificateur_v1.json')); json.loads(F['registre'][3])


class Equivalence(BaseV2):
    """L'agrégateur JavaScript de la page (mode direct) donne exactement les données de collecter() sur les mêmes fichiers."""
    def comparer(self, lm=None):
        if not NODE: self.skipTest('Node absent')
        f = os.path.join(self.cc, 'brut.txt'); self.main('brut', '--sortie', f)
        page = os.path.join(self.cc, 'page.html'); T1.w(page, self.TB.GABARIT)
        harnais = os.path.join(self.cc, 'harnais.js')
        T1.w(harnais, """const fs = require('fs'); const [, , page, brut] = process.argv; const g = fs.readFileSync(page, 'utf8');
const cron = g.slice(g.indexOf('/*CRON-DEBUT*/'), g.indexOf('/*CRON-FIN*/')), ag = g.slice(g.indexOf('/*AGREGER-DEBUT*/'), g.indexOf('/*AGREGER-FIN*/'));
const f = new Function('texte', 'conf', cron + '\\n' + ag + '\\nconst B = AG.nouveauBrut(); AG.lireBrut(texte, B); conf.analyserCron = analyserCron; return AG.agreger(B, conf);');
process.stdout.write(JSON.stringify(f(fs.readFileSync(brut, 'utf8'), JSON.parse(fs.readFileSync(0, 'utf8')))));""")
        P = json.loads(json.dumps(self.TB.collecter(etat_sync=None, lmstudio=lm if lm is not None else None)))
        conf = dict(seuils=self.TB.SEUILS, categories=list(self.TB.CATEGORIES), outil=P['outil'])
        r = subprocess.run([NODE, harnais, page, f], input=json.dumps(conf), capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr); J = json.loads(r.stdout)
        for g in P['goulots']:
            for k in ('titre', 'preuve', 'piste'): g.pop(k)
        self.assertEqual(len(P['planificateur'].pop('erreurs')), len(J['planificateur'].pop('erreurs')))
        if not P['etapes'] and not P['agents']:                 # v5 : espace vide, « etat_au » = maintenant, lu par Python puis par Node
            import datetime
            ta, tb = (datetime.datetime.strptime(x.pop('etat_au'), '%Y-%m-%dT%H:%M:%SZ') for x in (P, J))
            self.assertLessEqual(abs((tb - ta).total_seconds()), 5)
        for k in sorted(set(P) | set(J)): self.assertEqual(P.get(k), J.get(k), k)
        return P

    def test_espace_complet(self):
        self.espace_complet(); P = self.comparer()
        self.assertGreaterEqual(len(P['goulots']), 4); self.assertEqual(len(P['agents']), 3); self.assertTrue(P['tests'])
        self.assertIn('T-2', [s['id'] for s in P['etapes']]); self.assertEqual([s for s in P['etapes'] if s['id'] == 'T-2'][0]['duree_s'], 2670)   # début 09:05:30.250 tronqué à la seconde

    def test_avec_file_lmstudio(self):
        self.espace_complet()
        F = os.path.join(self.rev, '00_espace_cloud_claude', 'file_lmstudio'); os.makedirs(os.path.join(F, 'journal'))
        os.makedirs(os.path.join(F, 'entree')); T1.w(os.path.join(F, 'entree', 'a.jsonl'), '{}\n')
        T1.w(os.path.join(F, 'journal', 'etat.json'), json.dumps(dict(statut='arrêté', raison_arret='file vide', traites=3)))
        P = self.comparer(); self.assertEqual(P['lmstudio']['lots_entree'], 1); self.assertIn('G-LM1', [g['code'] for g in P['goulots']])

    def test_espace_vide(self):
        P = self.comparer(lm=False); self.assertEqual((P['etapes'], P['agents'], P['goulots']), ([], [], []))


if __name__ == '__main__':
    unittest.main()
