"""
OUTIL: dossier_ecarts
VERSION: 2
RESUME: Constitue, à partir d'un croisement demandes × révision (croiser_demandes), les dossiers de jugement des écarts choisis, regroupés par section : pour chaque demande, son type, le statut annoncé, le texte de la demande, le fil de commentaire d'origine, le paragraphe d'ancrage en vue d'origine et en vue acceptée, la différence mot à mot (supprimé, inséré), les informations vérifiables (renvois [n], nombres, sigles) absentes de tout le document accepté et la meilleure reprise ailleurs (part des mots retrouvée) ; gabarit de jugement à valeurs fermées ; puis (sous-commande « bilan ») contrôle d'un fichier de jugements (chaque écart jugé, verdict permis, motif présent) et résumé.
USAGE: python3 outils/dossier_ecarts.py constituer <docx> <croisement.json> <microtaches.jsonl> <sortie_dossier> [--codes E1,E3] [--max 600]  |  bilan <croisement.json> <jugements.json> [--codes E1,E3]  |  chercher <docx> <regex> [--vue acc|ori] [--max 20] [--largeur 160]
ENTREES: docx révisé (en suivi des modifications) ; croisement_demandes_vN.json {id: {type, ancre:{index}, section:{nom}, ecarts, priorite, statut_annonce}} ; microtaches_vN.jsonl (id, texte, fil) ; jugements_ecarts_vN.json {id: {verdict, motif, correctif}}
SORTIES: <sortie>/dossier_ecarts_vN.md et dossier_ecarts_vN.json (versionnés, jamais réécrits) ; bilan : résumé, code 1 si un écart n'est pas jugé ou si un verdict n'est pas permis ; événement dans journal/
CATEGORIE: revision_rapport
BANC: tests/test_dossier_ecarts_v2.py
REMPLACE: dossier_ecarts_v1 (détecteurs chargés dans leur version courante (cc_lib_v4.importer) et non plus dans une version figée devenue inutilisable après le renommage des dossiers) ; v1 : -
"""
import sys, os, re, json, zipfile, difflib, collections
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
for p in (os.path.join(O, '_compat'), O):
    if p not in sys.path: sys.path.insert(0, p)
VERSION = 2
VERDICTS = {'conforme': "la révision règle le point (rien à faire)",
            'a_restaurer': "texte supprimé à tort : le rétablir (refus de la suppression)",
            'a_completer': "demande en partie seulement traitée : compléter",
            'a_corriger': "la révision introduit une erreur ou traite autre chose : corriger",
            'question_auteur': "décision de l'auteur nécessaire : question dans le fil",
            'hors_portee': "demande hors de cette passe (attente, décision, autre document)"}


def opt(a, k, d=None): return a[a.index(k) + 1] if k in a else d


def charger_json(f):
    with open(f, encoding='utf-8') as g: return json.load(g)


def lire_jsonl(f):
    with open(f, encoding='utf-8') as g: return [json.loads(l) for l in g if l.strip()]


def differences(ori, acc, maxi=600):
    """Différence mot à mot : [-supprimé-] {+inséré+} ; le texte commun est abrégé."""
    a, b = ori.split(), acc.split(); out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == 'equal':
            s = a[i1:i2]; out.append(' '.join(s) if len(s) <= 12 else ' '.join(s[:5]) + ' … ' + ' '.join(s[-5:]))
        else:
            if i2 > i1: out.append('[-' + ' '.join(a[i1:i2]) + '-]')
            if j2 > j1: out.append('{+' + ' '.join(b[j1:j2]) + '+}')
    t = ' '.join(out); return t if len(t) <= maxi else t[:maxi] + ' …'


CLES = re.compile(r'\[\d+(?:[,–-]\s*\d+)*\]|\b\d+(?:[.,]\d+)?\s*%?|\b[A-Z][A-Z0-9]{1,}(?:-[A-Z0-9]+)*\b')


def cles(s):
    """Informations vérifiables d'un texte : renvois [n], nombres, sigles."""
    return {c.strip() for c in CLES.findall(s) if c.strip()}


def perdues(ori, acc_doc):
    """Informations du texte d'origine absentes de tout le document accepté (renvois, nombres, sigles)."""
    return sorted(c for c in cles(ori) if c not in acc_doc)


def ailleurs(P, k, tok):
    """Paragraphe accepté (autre que k) qui reprend le plus de mots du texte d'origine de k : (indice, couverture, extrait)."""
    T = set(tok(P[k]['ori']))
    if len(T) < 4: return None
    best = max(((len(T & set(tok(p['acc']))) / len(T), p['i']) for p in P if p['i'] != k and p['acc'].strip() and not p['toc']), default=None)
    if not best or best[0] == 0: return None
    return dict(index=best[1], couverture=round(best[0], 2), extrait=P[best[1]]['acc'][:300])


def fils(z):
    """{id de commentaire: texte} pour retrouver le fil d'origine d'une demande."""
    from cc_lib_v4 import importer; DR = importer('detecteurs_rapport')
    return {k: v['texte'] for k, v in DR.commentaires(z).items()}


def constituer(a):
    docx, fcr, fmt, out = a[:4]; codes = set((opt(a, '--codes', 'E1,E3')).split(',')); maxi = int(opt(a, '--max', 600))
    from cc_lib_v4 import importer; DR = importer('detecteurs_rapport')
    from cc_lib_v1 import ecrire_versionne, evenement
    z = zipfile.ZipFile(docx); P = DR.vues(z); C = fils(z); acc_doc = '\n'.join(p['acc'] for p in P)
    cr = charger_json(fcr); X = {x['id']: x for x in lire_jsonl(fmt)}
    choisis = {i: r for i, r in cr.items() if codes & set(r.get('ecarts') or [])}
    par_sec = collections.defaultdict(list)
    for i, r in sorted(choisis.items(), key=lambda kv: (kv[1]['ancre']['index'], kv[0])): par_sec[r['section']['nom']].append(i)
    J = {}; md = [f'# Dossier de jugement des écarts ({", ".join(sorted(codes))}) — {len(choisis)} demande(s), {len(par_sec)} section(s)', '',
                  f'Source : `{os.path.basename(docx)}` ; croisement : `{os.path.basename(fcr)}`.', '',
                  'Verdicts permis : ' + ' ; '.join(f'`{k}` ({v})' for k, v in VERDICTS.items()) + '.', '']
    for s, ids in par_sec.items():
        md += [f'## {s} ({len(ids)})', '']
        for i in ids:
            r = cr[i]; x = X.get(i, {}); k = r['ancre']['index']; p = P[k]
            fil = x.get('fil'); com = C.get(fil, '') if fil else ''
            e = dict(id=i, section=s, ecarts=r['ecarts'], type=r['type'], statut_annonce=r.get('statut_annonce'), index=k, paraId=p.get('pid'),
                     demande=x.get('texte', ''), fil=fil, commentaire=com[:1500], origine=p['ori'], acceptee=p['acc'],
                     difference=differences(p['ori'], p['acc'], maxi), supprime=r['ancre'].get('supprime'), couverture_ailleurs=r['ancre'].get('couverture_ailleurs'),
                     perdues=perdues(p['ori'], acc_doc), ailleurs=ailleurs(P, k, DR.tokens))
            J[i] = e
            md += [f"### {i} — {', '.join(r['ecarts'])} — type « {r['type']} » — ¶{k}" + (f" — statut annoncé : {r['statut_annonce']}" if r.get('statut_annonce') else ''), '',
                   f"- **Demande** : {e['demande'][:800]}"]
            if com and com.strip() != e['demande'].strip(): md += [f"- **Fil {fil}** : {com[:800]}"]
            md += [f"- **Différence** (rev. → acceptée) : {e['difference']}",
                   f"- **Paragraphe accepté** : {p['acc'][:maxi] or '(supprimé)'}",
                   f"- **Informations absentes de tout le document accepté** : {', '.join(e['perdues']) or 'aucune'}",
                   f"- **Meilleure reprise ailleurs** : " + (f"¶{e['ailleurs']['index']} ({round(100 * e['ailleurs']['couverture'])} % des mots) : {e['ailleurs']['extrait']}" if e['ailleurs'] else 'aucune'),
                   '- **Jugement** : verdict = … ; motif = … ; correctif = …', '']
    ch_md, _ = ecrire_versionne(out, 'dossier_ecarts', 'md', '\n'.join(md) + '\n')
    ch_js, _ = ecrire_versionne(out, 'dossier_ecarts', 'json', json.dumps(dict(codes=sorted(codes), demandes=J), ensure_ascii=False, indent=1))
    evenement('dossier_ecarts', VERSION, 'constituer', dict(demandes=len(J), sections=len(par_sec), codes=sorted(codes)))
    print(ch_md); print(ch_js); print(f'{len(J)} demande(s) en {len(par_sec)} section(s)')


def chercher(a):
    """Recherche d'une expression régulière dans une vue du document (acceptée par défaut, ou d'origine) : ¶, section, extrait."""
    from cc_lib_v4 import importer; DR = importer('detecteurs_rapport')
    docx, rx = a[:2]; vue = opt(a, '--vue', 'acc'); n = int(opt(a, '--max', 20)); larg = int(opt(a, '--largeur', 160))
    R = re.compile(rx, re.I); P = DR.vues(zipfile.ZipFile(docx)); k = 0
    for p in P:
        if p['toc']: continue
        for m in R.finditer(p[vue]):
            s = max(0, m.start() - larg // 2); print(f"¶{p['i']} [{p['section'][:50]}] …{p[vue][s:s + larg]}…"); k += 1
            if k >= n: return 0
    print(f'{k} occurrence(s)') if k else print('aucune occurrence'); return 0


def bilan(a):
    fcr, fj = a[:2]; codes = set((opt(a, '--codes', 'E1,E3')).split(','))
    cr = charger_json(fcr); J = charger_json(fj); J = J.get('jugements', J)
    attendus = sorted(i for i, r in cr.items() if codes & set(r.get('ecarts') or []))
    manq = [i for i in attendus if i not in J]; mauvais = [i for i, j in J.items() if j.get('verdict') not in VERDICTS]
    sans_motif = [i for i, j in J.items() if not (j.get('motif') or '').strip()]
    hors = [i for i in J if i not in cr]
    cpt = collections.Counter(j.get('verdict') for i, j in J.items() if i in attendus)
    print(f'{len(attendus)} écart(s) attendus ; jugés : {len(attendus) - len(manq)} ; ' + ', '.join(f'{k} {v}' for k, v in sorted(cpt.items())))
    for t, L in (('non jugés', manq), ('verdict non permis', mauvais), ('sans motif', sans_motif), ('inconnus du croisement', hors)):
        if L: print(f'  {t} : ' + ', '.join(L[:30]))
    ok = not (manq or mauvais or sans_motif or hors)
    print('BILAN CONFORME' if ok else 'BILAN NON CONFORME'); return 0 if ok else 1


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a or a[0] not in ('constituer', 'bilan', 'chercher'): print(__doc__.split('USAGE: ')[1].split('\n')[0]); sys.exit(2)
    r = {'constituer': constituer, 'bilan': bilan, 'chercher': chercher}[a[0]](a[1:]); sys.exit(r or 0)
