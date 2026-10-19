"""
OUTIL: detecteurs_rapport
VERSION: 3
RESUME: Détecteurs déterministes (v3 : + DR-08, DR-09) pour la révision d'un rapport Word en suivi (vue d'origine = tout refusé, vue acceptée = tout accepté) : DR-01 références [n] orphelines ou manquantes ; DR-02 renvois internes cassés (§, section, tableau, figure, annexe) ; DR-03 information possiblement unique supprimée ; DR-04 typographie introduite par les révisions ; DR-05 listes à ponctuation incohérente ; DR-06 variantes de termes ; DR-07 demande de remplacement dont le texte demandé est absent (leçon LC-008). « nouveau » = absent de la vue d'origine (créé par les révisions).
USAGE: python3 detecteurs_rapport_v3.py <docx> [--json <constats.json>] [--md <rapport.md>] [--termes <groupes.json>] [--seuil-unique 0.5]
ENTREES: docx (révisions de tous auteurs) ; facultatif : groupes de variantes [[« courriel », « e-mail »], …]
SORTIES: constats {regle, paraId, index, section, nouveau, detail} ; résumé par règle ; événement dans journal/
CATEGORIE: revision_rapport
BANC: bancs/detecteurs_rapport/
REMPLACE: detecteurs_rapport_v2 (+ DR-08 suggestion d'un collègue neutralisée à moitié : son insertion supprimée par Claude, sa suppression laissée, d'où un trou dans la vue acceptée ; + DR-09 texte cassé créé par les révisions : déterminant suivi d'une ponctuation ou d'un verbe, mot collé après un point, fragment collé en fin de paragraphe, sigle doublé collé, « , (§ », mot répété ; auteurs des fils remplacés par leur rôle)
"""
import sys, os, re, json, zipfile, collections, time
from lxml import etree
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import evenement, derniere_version, RACINE_CC
from anonymiser_v1 import anonymiser
ROLES = json.load(open(derniere_version(os.path.join(RACINE_CC, 'regles'), 'roles', 'json'), encoding='utf-8'))['roles']

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W14 = 'http://schemas.microsoft.com/office/word/2010/wordml'
def q(t, ns=W): return '{%s}%s' % (ns, t)
def ln(e): return etree.QName(e).localname if isinstance(e.tag, str) else None
SUPPR, INSER = ('del', 'moveFrom'), ('ins', 'moveTo')
MOTS_VIDES = set('''alors au aucun aussi autre avant avec avoir bon car ce cela ces cet cette ceux chaque ci comme comment dans des du donc dont
elle elles en encore entre est et été être eu fait faire fois font hors ici il ils je juste la le les leur leurs lui ma mais me même mes moins
mon ne ni nos notre nous on ont ou où par parce pas peu peut plus pour pourquoi quand que quel quelle quelles quels qui sa sans se ses seul
seulement si sien son sont sous soit sur ta tandis te tel telle tes ton tous tout toute toutes très tu un une vos votre vous vu ça ainsi afin
lors selon puis dont leurs celle celui ceux cette depuis doit doivent être sera seront peuvent pouvant ainsi elle cela'''.split())
TOKEN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9][A-Za-zÀ-ÖØ-öø-ÿ0-9\-']*")


def vues(z):
    d = etree.fromstring(z.read('word/document.xml'))
    styles = etree.fromstring(z.read('word/styles.xml')) if 'word/styles.xml' in z.namelist() else None
    noms = {}
    if styles is not None:
        for s in styles.iter(q('style')):
            n = s.find(q('name')); noms[s.get(q('styleId'))] = n.get(q('val')) if n is not None else ''
    P = []; section = '(début)'
    for i, p in enumerate(d.iter(q('p'))):
        st = p.find(q('pPr') + '/' + q('pStyle')); style = noms.get(st.get(q('val')), st.get(q('val'))) if st is not None else ''
        acc, ori = [], []
        for t in p.iter(q('t'), q('delText'), q('tab')):
            if next(t.iterancestors(q('p'))) is not p: continue
            txt = '\t' if ln(t) == 'tab' else (t.text or '')
            anc = [ln(a) for a in t.iterancestors() if ln(a) in SUPPR + INSER]
            if not any(a in SUPPR for a in anc): acc.append(txt)
            if not any(a in INSER for a in anc): ori.append(txt)
        rp = p.find(q('pPr') + '/' + q('rPr'))
        marque_del = rp is not None and rp.find(q('del')) is not None
        marque_ins = rp is not None and rp.find(q('ins')) is not None
        a, o = ''.join(acc), ''.join(ori)
        titre = bool(re.match(r'(heading|titre)\s*\d', style or '', re.I))
        if titre and (a.strip() or o.strip()): section = (a.strip() or o.strip())[:80]
        coms = [c.get(q('id')) for c in p.iter(q('commentRangeStart'))]
        P.append(dict(i=i, pid=p.get(q('paraId', W14)), style=style or '', titre=titre, acc=a, ori=o, section=section,
                      supprime=(marque_del and not a.strip()), insere=(marque_ins and not o.strip()), coms=coms,
                      liste='list' in (style or '').lower(), toc=bool(re.match(r'(toc|tdm)\s*\d', style or '', re.I))))
    return P


def commentaires(z):
    if 'word/comments.xml' not in z.namelist(): return {}
    c = etree.fromstring(z.read('word/comments.xml'))
    return {x.get(q('id')): dict(auteur=x.get(q('author')), texte='\n'.join(''.join(t.text or '' for t in p.iter(q('t'))) for p in x.findall(q('p'))))
            for x in c.iter(q('comment'))}


def tokens(s):
    return [t.lower().strip("-'") for t in TOKEN.findall(s) if len(t) >= 4 and t.lower() not in MOTS_VIDES or re.search(r'\d', t)]


def phrases(s):
    return [x.strip() for x in re.split(r'(?<=[.!?;])\s+(?=[A-ZÀ-Ö«(\[])', s) if x.strip()]


def main():
    a = sys.argv[1:]; src = a[0]
    jout = a[a.index('--json') + 1] if '--json' in a else None
    mout = a[a.index('--md') + 1] if '--md' in a else None
    seuil = float(a[a.index('--seuil-unique') + 1]) if '--seuil-unique' in a else 0.5
    groupes = json.load(open(a[a.index('--termes') + 1], encoding='utf-8')) if '--termes' in a else [['courriel', 'e-mail']]
    t0 = time.time()
    z = zipfile.ZipFile(src); P = vues(z); C = []
    def constat(r, p, detail, nouveau):
        C.append(dict(regle=r, paraId=p['pid'], index=p['i'], section=p['section'], nouveau=bool(nouveau), detail=detail))
    # ---------- zones : références
    idx_ref = next((p['i'] for p in P if p['titre'] and re.match(r'^\s*R[ée]f[ée]rences\s*$', p['acc'] or p['ori'])), None)
    def dans_refs(p): return idx_ref is not None and p['i'] > idx_ref and re.match(r'^\s*\[\d+\]', p['acc'] or p['ori'])
    corps = [p for p in P if not p['toc'] and not dans_refs(p)]
    CIT = re.compile(r'\[(\d+)\](?:\s*[–-]\s*\[(\d+)\])?')
    def cites(texte):
        s = set()
        for m in CIT.finditer(texte):
            x = int(m.group(1)); y = int(m.group(2)) if m.group(2) else x
            s.update(range(x, y + 1) if 0 <= y - x < 50 else [x, y])
        return s
    liste_refs = {}
    for p in P:
        if dans_refs(p):
            m = re.match(r'^\s*\[(\d+)\]', p['acc'] or p['ori'])
            if m and (p['acc'].strip()): liste_refs[int(m.group(1))] = p
    cit_acc, cit_ori = collections.defaultdict(list), collections.defaultdict(list)
    for p in corps:
        for n in cites(p['acc']): cit_acc[n].append(p)
        for n in cites(p['ori']): cit_ori[n].append(p)
    for n, p in sorted(liste_refs.items()):
        if n not in cit_acc:
            constat('DR-01', p, f'[{n}] dans la liste des références mais citée nulle part', nouveau=n in cit_ori)
    for n, ps in sorted(cit_acc.items()):
        if liste_refs and n not in liste_refs: constat('DR-01', ps[0], f'[{n}] citée mais absente de la liste des références', nouveau=n not in cit_ori)
    # ---------- DR-02 renvois
    def cibles(vue):
        sec, tab, fig, ann = set(), set(), set(), set()
        for p in P:
            t = (p[vue] or '').strip()
            if not t or p['toc']: continue
            if p['titre']:
                m = re.match(r'^(\d+(?:\.\d+)*)\s', t)
                if m:
                    parts = m.group(1).split('.')
                    for k in range(1, len(parts) + 1): sec.add('.'.join(parts[:k]))
                m = re.match(r'^Annexe\s+([A-Z])\b', t)
                if m: ann.add(m.group(1))
                m = re.match(r'^([A-Z]\.\d+(?:\.\d+)*)\s', t)
                if m:
                    parts = m.group(1).split('.')
                    for k in range(2, len(parts) + 1): sec.add('.'.join(parts[:k]))
                    ann.add(parts[0])
            m = re.match(r'^Tableau\s+([A-Z]?\.?\d+)\s*[:.–—-]', t)
            if m: tab.add(m.group(1))
            m = re.match(r'^Figure\s+([A-Z]?\.?\d+)\s*[:.–—-]', t)
            if m: fig.add(m.group(1))
        return sec, tab, fig, ann
    ca, co = cibles('acc'), cibles('ori')
    RENV = [('section', re.compile(r'§\s?([A-D]?\.?\d+(?:\.\d+)*)|\bsections?\s+(\d+(?:\.\d+)*)(?:\s*(?:à|et|–|-)\s*(\d+(?:\.\d+)*))?')),
            ('tableau', re.compile(r'\b[Tt]ableaux?\s+([A-Z]?\.?\d+)(?:\s*(?:,|et|à)\s*([A-Z]?\.?\d+))?')),
            ('figure', re.compile(r'\b[Ff]igures?\s+([A-Z]?\.?\d+)(?:\s*(?:,|et|à)\s*([A-Z]?\.?\d+))?')),
            ('annexe', re.compile(r'\b[Aa]nnexes?\s+([A-D])\b(?!\.\d)'))]
    def verifier_renvois(texte, cib):
        sec, tab, fig, ann = cib; out = []
        for genre, rx in RENV:
            for m in rx.finditer(texte):
                for g in [x for x in m.groups() if x]:
                    g = g.rstrip('.')
                    ok = (g in sec if genre == 'section' else g in tab if genre == 'tableau' else g in fig if genre == 'figure' else g in ann)
                    if genre == 'section' and not ok and re.match(r'^[A-D]$', g): ok = g in ann
                    if not ok: out.append(f'{genre} {g}')
        return out
    if any(ca):
        for p in corps:
            if p['titre'] or not p['acc'].strip() or re.match(r'^(Tableau|Figure)\s+\S+\s*[:.–—-]', p['acc'].strip()): continue
            casses = verifier_renvois(p['acc'], ca)
            if casses:
                avant = set(verifier_renvois(p['ori'], co)) if p['ori'].strip() else set()
                for x in sorted(set(casses)): constat('DR-02', p, f'renvoi vers {x} introuvable dans la vue acceptée', nouveau=x not in avant)
    # ---------- DR-03 information possiblement unique supprimée
    acc_phr = [(p, s) for p in P if not p['toc'] for s in phrases(p['acc'])]
    index = collections.defaultdict(set)
    for k, (p, s) in enumerate(acc_phr):
        for t in set(tokens(s)): index[t].add(k)
    tous_acc = set(index)
    for p in P:
        if p['toc'] or not p['ori'].strip(): continue
        sa = set(phrases(p['acc']))
        for s in phrases(p['ori']):
            if s in sa or s in p['acc']: continue
            T = set(tokens(s))
            if len(T) < 4: continue
            cpt = collections.Counter(k for t in T for k in index.get(t, ()))
            best = max(cpt.values()) / len(T) if cpt else 0.0
            nombres = sorted(t for t in T if re.search(r'\d', t) and t not in tous_acc)
            if best < seuil or nombres:
                constat('DR-03', p, f'phrase supprimée, couverture max ailleurs {best:.2f}' + (f' ; nombres disparus {nombres}' if nombres else '') + f' : « {s[:160]} »', nouveau=True)
    # ---------- DR-04 typographie introduite
    TYPO = [(re.compile(r'\S[;:?!](?=\s|$)'), 'pas d’espace avant ; : ? !'), (re.compile(r'  +'), 'double espace'),
            (re.compile(r'\s[,.](?=\s|$)'), 'espace avant , ou .'), (re.compile(r'«\S'), 'pas d’espace après «'),
            (re.compile(r'\S»'), 'pas d’espace avant »'), (re.compile(r'\b(\w{2,})\s+\1\b', re.I), 'mot répété')]
    for p in P:
        if p['toc'] or p['acc'] == p['ori'] or not p['acc'].strip(): continue
        for rx, nom in TYPO:
            na = len([m for m in rx.finditer(p['acc']) if not re.match(r'\d:\d', p['acc'][max(0, m.start()):m.end() + 1])])
            no = len([m for m in rx.finditer(p['ori']) if not re.match(r'\d:\d', p['ori'][max(0, m.start()):m.end() + 1])])
            if na > no: constat('DR-04', p, f'{nom} (×{na - no})', nouveau=True)
        for o, f_ in (('(', ')'), ('«', '»'), ('[', ']')):
            if p['acc'].count(o) != p['acc'].count(f_) and p['ori'].count(o) == p['ori'].count(f_):
                constat('DR-04', p, f'{o}{f_} non appariés', nouveau=True)
    # ---------- DR-05 listes à ponctuation incohérente (listes touchées)
    groupe = []
    def fermer():
        items = [x for x in groupe if x['acc'].strip()]
        if len(items) >= 3 and any(x['acc'] != x['ori'] for x in groupe):
            fins = [x['acc'].rstrip()[-1:] for x in items]
            n_pt = sum(1 for f in fins if f == '.')
            if 2 <= n_pt < len(items):
                for x, f in zip(items, fins):
                    if f not in '.:;': constat('DR-05', x, 'élément de liste sans ponctuation finale (les autres finissent par un point)', nouveau=x['acc'] != x['ori'])
        groupe.clear()
    for p in P:
        if p['liste'] and not p['toc']: groupe.append(p)
        else: fermer()
    fermer()
    # ---------- DR-06 variantes de termes
    texte_acc = '\n'.join(p['acc'] for p in corps)
    for g in groupes:
        n = {v: len(re.findall(r'(?<![\w-])' + re.escape(v) + r'(?![\w-])', texte_acc)) for v in g}
        if sum(1 for v in n.values() if v) > 1:
            C.append(dict(regle='DR-06', paraId=None, index=None, section=None, nouveau=False, detail='variantes : ' + ', '.join(f'« {k} » ×{v}' for k, v in n.items())))
    traits = collections.Counter(m.group(0).lower() for m in re.finditer(r'\b\w{2,}(?:-\w{2,}){1,3}\b', texte_acc))
    for t, nb in sorted(traits.items()):
        sans = t.replace('-', ' ')
        ns = len(re.findall(r'\b' + re.escape(sans) + r'\b', texte_acc.lower()))
        if ns: C.append(dict(regle='DR-06', paraId=None, index=None, section=None, nouveau=False, detail=f'« {t} » ×{nb} et « {sans} » ×{ns}'))
    # ---------- DR-07 demandes de remplacement (LC-008)
    com = commentaires(z)
    DEM = re.compile(r"(pas\s+(?:l['’]|le |la |les |de |d['’]|du |des )?.{0,80}?qu['’]il faut.{0,60}?mais|plut[ôo]t que|remplac\w+ par|il faut (?:indiquer|mettre|écrire|préciser)|[àa] la place|→|->)", re.I | re.S)
    par_com = collections.defaultdict(list)
    for p in P:
        for c in p['coms']: par_com[c].append(p)
    for cid, c in com.items():
        if 'Claude' in (c['auteur'] or '') or cid not in par_com: continue
        m = DEM.search(c['texte'])
        if not m: continue
        p = par_com[cid][0]
        suite = c['texte'][m.end():]
        cible = re.split(r'[.\n]', suite.split(':', 1)[1] if ':' in suite[:80] else suite)[0]
        T = set(tokens(cible))
        voisins = ' '.join(x['acc'] for x in P[max(0, p['i'] - 3):p['i'] + 8])
        V = set(tokens(voisins))
        couv = len(T & V) / len(T) if T else 1.0
        ancre_supprimee = p['supprime'] or (p['ori'].strip() and not p['acc'].strip())
        if (ancre_supprimee and couv < 0.5) or (T and couv < 0.3):
            constat('DR-07', p, f'fil {cid} ({anonymiser(c["auteur"], ROLES)}) demande un remplacement ; texte demandé présent à {couv:.0%} près de l’ancre'
                    + (' ; ancre supprimée' if ancre_supprimee else '') + f' : « {c["texte"][:140]} »', nouveau=True)
    # ---------- DR-08 suggestion de collègue neutralisée à moitié (trou dans la vue acceptée)
    doc = etree.fromstring(z.read('word/document.xml')); claude = lambda x: 'Claude' in (x or '')
    def tx(e): return ''.join((t.text or '') for t in e.iter(q('t'), q('delText')))
    for p, xp in zip(P, doc.iter(q('p'))):
        if not p['acc'].strip(): continue
        seg = []
        for e in xp:
            n = ln(e)
            if n == 'r': seg.append(('r', None, None, tx(e)))
            elif n in ('ins', 'del'):
                ds = [x for x in e.iter(q('del')) if x is not e]
                seg.append((n, e.get(q('author')), ds[0].get(q('author')) if ds and tx(e) == ''.join(tx(x) for x in ds) else None, tx(e)))
        garde = lambda x: x[0] == 'r' or (x[0] == 'ins' and not x[2])
        for k, sg in enumerate(seg):
            if not (sg[0] == 'ins' and not claude(sg[1]) and claude(sg[2]) and sg[3].strip()): continue
            g = next((j for j in range(k - 1, -1, -1) if garde(seg[j]) and seg[j][3]), None)
            dr = next((j for j in range(k + 1, len(seg)) if garde(seg[j]) and seg[j][3]), None)
            if g is None or dr is None or seg[g][0] != 'r' or seg[dr][0] != 'r': continue
            entre = seg[g + 1:dr]
            dl = [v for v in entre if v[0] == 'del' and not claude(v[1]) and v[3].strip()]
            if dl and not any(v[0] == 'ins' and claude(v[1]) for v in entre):
                constat('DR-08', p, f'suggestion de {anonymiser(sg[1] or "", ROLES)} « {dl[0][3][:40]} » → « {sg[3][:40]} » : insertion supprimée par Claude, suppression laissée ; '
                        f'vue acceptée : « {seg[g][3][-40:]}⟦⟧{seg[dr][3][:40]} »', nouveau=True)
    # ---------- DR-09 texte cassé créé par les révisions
    CASSE = [('déterminant + ponctuation', re.compile(r"\b(?:des|les|la|le|du|aux|au|ces|ses|leurs?)\s+[(),.;:»]", re.I)),
             ('déterminant + verbe', re.compile(r"\b(?:les|des|ces)\s+(?:sont|ont|étaient|seront)\b", re.I)),
             ('mot collé après un point', re.compile(r"[a-zà-ÿ]{3,}\.[a-zà-ÿ]{2,}")),
             ('fragment collé en fin de paragraphe', re.compile(r"[.!?)]([A-Za-zÀ-ÿ]{2,})\s*$")),
             ('sigle doublé collé', re.compile(r"\b([A-Z]{2,})\1\b")),
             ('virgule avant renvoi', re.compile(r",\s+\(§")),
             ('mot répété', re.compile(r"\b(\w{3,})\s+\1\b", re.I))]
    for p in P:
        if p['toc'] or not p['acc'].strip(): continue
        for nom, rx in CASSE:
            for m in rx.finditer(p['acc']):
                ctx = p['acc'][max(0, m.start() - 40):m.end() + 30]
                if ctx.strip() in p['ori']: continue
                if nom == 'mot collé après un point' and re.search(r'(www|http|\.(?:py|xlsx|docx|csv|json|md|txt)\b|\b(?:e\.g|i\.e|etc)\.)', ctx, re.I): continue
                constat('DR-09', p, f'{nom} : « {ctx.strip()} »', nouveau=True)
    # ---------- sorties
    par = collections.Counter(c['regle'] for c in C); nouv = collections.Counter(c['regle'] for c in C if c['nouveau'])
    C.sort(key=lambda c: (c['regle'], c['index'] if c['index'] is not None else -1, c['detail']))
    res = dict(outil='detecteurs_rapport', version=3, source=os.path.basename(src), constats=C,
               resume={r: dict(total=par[r], nouveaux=nouv[r]) for r in sorted(par)})
    duree = round(time.time() - t0, 2)
    if jout:
        with open(jout, 'x', encoding='utf-8') as f: json.dump(res, f, ensure_ascii=False, indent=1)
    if mout:
        L = [f'# Détecteurs déterministes : {os.path.basename(src)}', '', '| Règle | Constats | Créés par les révisions |', '|---|---|---|']
        L += [f'| {r} | {par[r]} | {nouv[r]} |' for r in sorted(par)] + ['']
        for r in sorted(par):
            L.append(f'## {r}')
            for c in [x for x in C if x['regle'] == r][:400]:
                L.append(f"- {'**nouveau** ' if c['nouveau'] else ''}¶{c['index']} {c['paraId'] or ''} ({(c['section'] or '')[:40]}) : {c['detail']}")
            L.append('')
        with open(mout, 'x', encoding='utf-8') as f: f.write('\n'.join(L))
    evenement('detecteurs_rapport', 3, 'detection', dict(source=os.path.basename(src), resume=res['resume'], duree_s=duree))
    print(f"{len(C)} constats en {duree} s :", ', '.join(f"{r} {par[r]} ({nouv[r]} nouveaux)" for r in sorted(par)))


if __name__ == '__main__':
    main()
