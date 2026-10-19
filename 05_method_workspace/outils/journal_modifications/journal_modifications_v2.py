"""
OUTIL: journal_modifications
VERSION: 2
RESUME: Journal des modifications au format D14 (skill journal-modifications-d14) d'une passe appliquée par appliquer_suivi, construit sans saisie à partir des enregistrements de la passe : pour chaque point (POINTS des modules) une entrée « Problème / Information additionnelle / Solution et pourquoi / Modification « ancien » → « nouveau » (réduite aux mots qui changent) / Passage inséré ou supprimé / Texte d'origine conservé (N des M mots, %) », avec mandat (sources) et verdict ; bilan (opérations par type, mots insérés et supprimés, réponses), tableau des contrôles de l'essai (bilan JSON), jugements des écarts (dossier_ecarts), réponses aux fils et questions pour l'auteur. Sortie Markdown versionnée (nouvelle version seulement si le contenu change), à convertir en docx par md_vers_docx de la skill.
USAGE: python3 outils/journal_modifications.py <journal_essai.json> <dossiers_modules séparés par des virgules> <sortie.md|dossier> [--titre "…"] [--bilan <bilan_essai.json>] [--jugements <jugements.json>] [--questions <questions.md>] [--docx <docx de l'essai>]
ENTREES: journal JSON d'appliquer_suivi (operations avant/après, reponses, modules) ; modules Python des opérations (POINTS, OPS) ; facultatifs : bilan de l'essai, jugements des écarts, questions pour l'auteur (Markdown), docx de l'essai (sections des paragraphes)
SORTIES: <base>_vN.md (journal D14) ; événement dans journal/
CATEGORIE: revision_rapport
BANC: tests/test_journal_modifications_v2.py
REMPLACE: journal_modifications_v1 (mots insérés et supprimés du bilan comptés sur l'écart préfixe-suffixe : un fragment déplacé comptait tout le texte entre ses deux places ; désormais différence mot à mot (difflib), et chiffres du bilan de l'essai repris quand il est fourni) ; v1 : - (généralise skills_ressources_par_skill/journal-modifications-d14/scripts/journal_D14_pilote_v4.py, propre au pilote v8)
"""
import sys, os, re, json, zipfile, importlib.util, collections, difflib
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
for p in (os.path.join(O, '_compat'), O):
    if p not in sys.path: sys.path.insert(0, p)
from cc_lib_v4 import ecrire_versionne, evenement, importer   # noqa: E402
VERSION = 1
MOT = re.compile(r'\S+')


def opt(a, k, d=None): return a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else d


def reduire(avant, apres):
    """(ancien, nouveau) réduits aux mots qui changent : préfixe et suffixe communs retirés sur des frontières de mots."""
    A, B = avant.split(' '), apres.split(' ')
    i = 0
    while i < min(len(A), len(B)) and A[i] == B[i]: i += 1
    j = 0
    while j < min(len(A), len(B)) - i and A[-1 - j] == B[-1 - j]: j += 1
    return ' '.join(A[i:len(A) - j]), ' '.join(B[i:len(B) - j])


def conserves(avant, apres):
    """(mots d'origine conservés, mots d'origine) : plus longue sous-suite commune des mots."""
    a, b = MOT.findall(avant), MOT.findall(apres)
    if not a: return 0, 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for k, y in enumerate(b): cur.append(prev[k] + 1 if x == y else max(prev[k + 1], cur[k]))
        prev = cur
    return prev[-1], len(a)


def mots_changes(avant, apres):
    """(mots insérés, mots supprimés) par différence mot à mot : un fragment déplacé compte pour sa seule longueur."""
    a, b = MOT.findall(avant or ''), MOT.findall(apres or ''); ins = sup = 0
    for t, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if t in ('replace', 'delete'): sup += i2 - i1
        if t in ('replace', 'insert'): ins += j2 - j1
    return ins, sup


def charger_points(modules, dossiers):
    P, Ops = {}, {}
    for d in dossiers:
        if d not in sys.path: sys.path.insert(0, d)
    for m in modules:
        f = next((os.path.join(d, m + '.py') for d in dossiers if os.path.exists(os.path.join(d, m + '.py'))), None)
        if not f: raise SystemExit(f'module introuvable : {m}')
        s = importlib.util.spec_from_file_location(f'jm_{m}', f); mod = importlib.util.module_from_spec(s); s.loader.exec_module(mod)
        for p in getattr(mod, 'POINTS', []): P[p['id']] = dict(p, module=m)
        for o in mod.OPS: Ops[o['id']] = dict(o, module=m)
    return P, Ops


def sections(docx):
    if not docx or not os.path.exists(docx): return {}
    DR = importer('detecteurs_rapport')
    return {p['pid']: p['section'] for p in DR.vues(zipfile.ZipFile(docx))}


def cite(t, n=500): t = re.sub(r'\s+', ' ', t or '').strip(); return t if len(t) <= n else t[:n - 1] + '…'


def entree(pid, P, ops, sec):
    p = P.get(pid, dict(id=pid, point='', demande='', raison='', sources=[]))
    types = sorted({o['type'] for o in ops}); lieux = sorted({sec.get(o.get('paraId'), '') for o in ops if sec.get(o.get('paraId'))})
    L = [f"#### {pid} · {lieux[0] if lieux else '—'} · {', '.join(types) or '—'}",
         f"*Mandat* : {', '.join(p.get('sources') or []) or '—'}. *Verdict* : {p.get('verdict', '—')}.",
         f"- **Problème** : {cite(p.get('point'))}",
         f"- **Information additionnelle et complémentaire non présente** : {cite(p.get('info')) if p.get('info') else 'aucune'}",
         f"- **Solution et pourquoi** : {cite(p.get('demande'))} {cite(p.get('raison'))}".rstrip()]
    gardes, total = 0, 0
    for o in ops:
        if o['type'] == 'remplacer':
            a, b = reduire(o.get('avant', ''), o.get('apres', ''))
            if a and b: L.append(f"- **Modification** : « {cite(a, 300)} » → « {cite(b, 300)} »")
            elif a: L.append(f"- **Passage supprimé** : « {cite(a, 300)} »")
            elif b: L.append(f"- **Passage inséré** : « {cite(b, 300)} »")
            g, t = conserves(o.get('avant', ''), o.get('apres', '')); gardes += g; total += t
        elif o['type'] in ('inserer_apres', 'inserer_avant'):
            L.append(f"- **Paragraphe inséré** : « {cite(o.get('texte'), 300)} »")
        elif o['type'] == 'supprimer_par':
            L.append(f"- **Paragraphe supprimé** : « {cite(o.get('avant'), 300)} »"); total += len(MOT.findall(o.get('avant', '')))
        else:
            L.append(f"- **Opération** : {o['type']}")
    if total: L.append(f"- **Texte d'origine** : {gardes} des {total} mots conservés ({round(100 * gardes / total)} %)")
    elif ops and all(o['type'].startswith('inserer') for o in ops): L.append("- **Texte d'origine** : 100 % (insertion seulement)")
    return L + ['']


def construire(J, P, Ops, sec, titre, bilan=None, jug=None, questions=None):
    par_point = collections.OrderedDict()
    for o in J.get('operations', []):
        par_point.setdefault(o.get('point') or o['id'], []).append(o)
    types = collections.Counter(o['type'] for o in J.get('operations', []))
    ins = sup = 0
    for o in J.get('operations', []):
        if o['type'] == 'remplacer':
            i, s_ = mots_changes(o.get('avant', ''), o.get('apres', '')); ins += i; sup += s_
        elif o['type'].startswith('inserer'): ins += len(MOT.findall(o.get('texte', '')))
        elif o['type'] == 'supprimer_par': sup += len(MOT.findall(o.get('avant', '')))
    if bilan and isinstance(bilan.get('mots_inseres'), int): ins, sup = bilan['mots_inseres'], bilan.get('mots_supprimes', sup)
    verd = collections.Counter(P.get(k, {}).get('verdict', '—') for k in par_point)
    L = [f'# {titre}', '', f"Source : `{os.path.basename(J.get('source', ''))}` · auteur des révisions : {J.get('auteur', '')} · passe du {J.get('date', '')[:10]} · modules : {J.get('modules', '')}.", '',
         '## 1. Bilan', '',
         '| Élément | Valeur |', '|---|---|',
         f'| Points traités | {len(par_point)} |', f'| Opérations | {sum(types.values())} ({", ".join(f"{k} {v}" for k, v in sorted(types.items()))}) |',
         f'| Mots insérés / supprimés | {ins} / {sup} |', f'| Réponses aux fils | {len(J.get("reponses", []))} |',
         f'| Verdicts | {", ".join(f"{k} {v}" for k, v in sorted(verd.items()))} |', '']
    if bilan:
        L += ['### Contrôles de la passe', '', '| Contrôle | Résultat |', '|---|---|',
              f"| V1 refus de nos révisions = document reçu, V2 schéma des points, V3 réponses, V5 couverture | {'conforme' if not bilan.get('ecarts') else 'écarts : ' + ', '.join(bilan['ecarts'])} |",
              f"| V8 nouveaux problèmes (détecteurs) | {bilan.get('nouveaux_problemes', '—')} ; constats du document reçu résolus : {bilan.get('constats_rev1_resolus', '—')} |",
              f"| Bilan | {bilan.get('bilan', '—')} |", '']
    L += ['## 2. Entrées', '']
    for pid, ops in par_point.items(): L += entree(pid, P, ops, sec)
    if J.get('reponses'):
        L += ['## 3. Réponses aux fils', '', '| Fil | Réponse |', '|---|---|'] + [f"| {r.get('fil')} | {cite(r.get('texte'), 400)} |" for r in J['reponses']] + ['']
    if jug:
        J2 = jug.get('jugements', jug); c = collections.Counter(v.get('verdict') for v in J2.values())
        L += ['## 4. Jugements des écarts', '', f"{len(J2)} écart(s) jugé(s) : " + ', '.join(f'{k} {v}' for k, v in sorted(c.items())) + '.', '',
              '| Écart | Verdict | Motif |', '|---|---|---|'] + [f"| {k} | {v.get('verdict')} | {cite(v.get('motif'), 400)} |" for k, v in sorted(J2.items())] + ['']
    if questions: L += ['## 5. Questions et décisions pour l’auteur', '', questions.strip(), '']
    return '\n'.join(L)


def main(a):
    if len(a) < 3: print('USAGE: ' + __doc__.split('USAGE: ')[1].split('\n')[0]); return 2
    fj, dossiers, out = a[0], a[1].split(','), a[2]
    with open(fj, encoding='utf-8') as g: J = json.load(g)
    P, Ops = charger_points([m for m in J.get('modules', '').split(',') if m], dossiers)
    def lire(k, js=True):
        f = opt(a, k)
        if not f: return None
        with open(f, encoding='utf-8') as g: return json.load(g) if js else g.read()
    md = construire(J, P, Ops, sections(opt(a, '--docx') or J.get('sortie')), opt(a, '--titre', 'Journal des modifications'),
                    lire('--bilan'), lire('--jugements'), lire('--questions', False))
    if out.endswith('.md'): d, base = os.path.dirname(out) or '.', re.sub(r'_v\d+$', '', os.path.basename(out)[:-3])
    else: d, base = out, 'journal_modifications'
    f, cree = ecrire_versionne(d, base, 'md', md)
    evenement('journal_modifications', VERSION, 'journal', dict(points=md.count('\n#### '), nouveau=cree))
    print(f, '' if cree else '(inchangé)'); return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
