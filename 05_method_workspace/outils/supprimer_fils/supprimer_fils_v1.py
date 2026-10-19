"""
OUTIL: supprimer_fils
VERSION: 1
RESUME: Docx : supprime des fils de commentaires entiers (commentaire racine et toutes ses réponses), proprement dans toutes les parties : comments.xml, commentsExtended.xml (commentEx), commentsIds.xml (commentId), commentsExtensible.xml (commentExtensible), et dans le corps, les notes, en-têtes et pieds de page les marqueurs commentRangeStart / commentRangeEnd et les références (run retiré s'il ne porte plus rien ; conteneur de révision vide retiré). Les autres fils, people.xml et le texte restent intacts. Contrôle intégré : chaque commentaire restant garde ses marqueurs et sa référence, aucune référence ni marqueur ne vise un commentaire absent, les fils restants sont identiques (texte, auteur, date, parent).
USAGE: python3 supprimer_fils_v1.py <entree.docx> <sortie.docx> --fils <fichier.json>   (liste JSON des identifiants des commentaires racines, ou {"racines": [...]})
ENTREES: docx commenté ; liste des racines des fils à supprimer
SORTIES: <sortie.docx> (nouveau fichier, jamais écrasé : code 3 s'il existe) ; bilan (fils, commentaires, marqueurs, références retirés) ; code 0, 1 si le contrôle intégré échoue (sortie gardée pour examen), 2 usage, 4 racine inconnue ou qui n'est pas une racine
CATEGORIE: docx
BANC: tests/test_supprimer_fils_v1.py
REMPLACE: -
"""
import sys, os, re, json, zipfile, collections
from lxml import etree

VERSION = 1; OUTIL = 'supprimer_fils'
WN = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W14 = 'http://schemas.microsoft.com/office/word/2010/wordml'
W15 = 'http://schemas.microsoft.com/office/word/2012/wordml'
W16CID = 'http://schemas.microsoft.com/office/word/2016/wordml/cid'
W16CEX = 'http://schemas.microsoft.com/office/word/2018/wordml/cex'
def q(t, ns=WN): return '{%s}%s' % (ns, t)
def ln(e): return etree.QName(e).localname if isinstance(e.tag, str) else None
TEXTE = re.compile(r'^word/(document|footnotes|endnotes|header\d*|footer\d*)\.xml$')
REV = ('ins', 'del', 'moveFrom', 'moveTo')


def ser(r): return etree.tostring(r, xml_declaration=True, encoding='UTF-8', standalone=True)


def fils(F):
    """{id: dict(auteur, date, texte, parent, racine, paraids)} d'après comments.xml et commentsExtended.xml."""
    if 'word/comments.xml' not in F: return {}
    com = etree.fromstring(F['word/comments.xml'])
    par = {}
    if 'word/commentsExtended.xml' in F:
        par = {c.get(q('paraId', W15)): c.get(q('paraIdParent', W15)) for c in etree.fromstring(F['word/commentsExtended.xml']).iter(q('commentEx', W15))}
    out, dernier = {}, {}
    for c in com.iter(q('comment')):
        ps = c.findall(q('p')); i = c.get(q('id'))
        dernier[i] = ps[-1].get(q('paraId', W14)) if ps else None
        out[i] = dict(auteur=c.get(q('author')), date=c.get(q('date')), paraids=[p.get(q('paraId', W14)) for p in ps],
                      texte='\n'.join(''.join(t.text or '' for t in p.iter(q('t'))) for p in ps))
    d2i = {v: k for k, v in dernier.items() if v}
    for k in out: out[k]['parent'] = d2i.get(par.get(dernier[k]))
    for k in out:
        r = k; vu = set()
        while out[r]['parent'] and r not in vu: vu.add(r); r = out[r]['parent']
        out[k]['racine'] = r
    return out


def ancrages(F):
    """{id: Counter(start, end, ref)} sur toutes les parties de texte."""
    a = collections.defaultdict(collections.Counter)
    for nom in F:
        if not TEXTE.match(nom): continue
        r = etree.fromstring(F[nom])
        for t, k in (('commentRangeStart', 'start'), ('commentRangeEnd', 'end'), ('commentReference', 'ref')):
            for e in r.iter(q(t)): a[e.get(q('id'))][k] += 1
    return a


def supprimer(F, racines):
    """Supprime les fils dont les racines sont données ; F : {nom de partie: octets}, modifié en place ; retourne le bilan."""
    C = fils(F); racines = set(racines)
    inconnues = [r for r in racines if r not in C or C[r]['racine'] != r]
    if inconnues: raise KeyError(f'racines inconnues ou qui ne sont pas des racines : {sorted(inconnues)[:10]}')
    ids = {k for k, v in C.items() if v['racine'] in racines}
    pids = {p for k in ids for p in C[k]['paraids'] if p}
    n = collections.Counter(fils=len(racines), commentaires=len(ids))
    com = etree.fromstring(F['word/comments.xml'])
    for c in list(com.iter(q('comment'))):
        if c.get(q('id')) in ids: com.remove(c)
    F['word/comments.xml'] = ser(com)
    durables = set()
    if 'word/commentsIds.xml' in F:
        r = etree.fromstring(F['word/commentsIds.xml'])
        for e in list(r):
            if e.get(q('paraId', W16CID)) in pids: durables.add(e.get(q('durableId', W16CID))); r.remove(e); n['commentId'] += 1
        F['word/commentsIds.xml'] = ser(r)
    if 'word/commentsExtended.xml' in F:
        r = etree.fromstring(F['word/commentsExtended.xml'])
        for e in list(r):
            if e.get(q('paraId', W15)) in pids: r.remove(e); n['commentEx'] += 1
        F['word/commentsExtended.xml'] = ser(r)
    if 'word/commentsExtensible.xml' in F:
        r = etree.fromstring(F['word/commentsExtensible.xml'])
        for e in list(r):
            if e.get(q('durableId', W16CEX)) in durables: r.remove(e); n['commentExtensible'] += 1
        F['word/commentsExtensible.xml'] = ser(r)
    for nom in [x for x in F if TEXTE.match(x)]:
        r = etree.fromstring(F[nom]); chg = False
        for t in ('commentRangeStart', 'commentRangeEnd'):
            for e in list(r.iter(q(t))):
                if e.get(q('id')) in ids: e.getparent().remove(e); n[t] += 1; chg = True
        for e in list(r.iter(q('commentReference'))):
            if e.get(q('id')) not in ids: continue
            run = e.getparent(); run.remove(e); n['commentReference'] += 1; chg = True
            if ln(run) == 'r' and all(ln(x) == 'rPr' for x in run):
                cont = run.getparent(); cont.remove(run)
                while cont is not None and ln(cont) in REV and len(cont) == 0:
                    p = cont.getparent(); p.remove(cont); cont = p
        if chg: F[nom] = ser(r)
    return dict(n), ids


def controler(avant, apres, ids):
    """Contrôle intégré : fils restants identiques, ancrages complets, aucune référence orpheline."""
    Ca, Cb = fils(avant), fils(apres); E = []
    for k, v in Ca.items():
        if k in ids:
            if k in Cb: E.append(f'commentaire {k} encore présent')
            continue
        if k not in Cb: E.append(f'commentaire {k} perdu'); continue
        for x in ('auteur', 'date', 'texte', 'parent', 'racine'):
            if Cb[k][x] != v[x]: E.append(f'commentaire {k} : {x} modifié')
    Aa, Ab = ancrages(avant), ancrages(apres)
    for k in set(Ab) - set(Cb): E.append(f'marqueur ou référence {k} sans commentaire')
    for k in Cb:
        if Ab.get(k) != Aa.get(k): E.append(f'ancrage du commentaire {k} modifié : {dict(Aa.get(k, {}))} → {dict(Ab.get(k, {}))}')
    return E


def traiter(entree, sortie, racines):
    if os.path.exists(sortie): raise FileExistsError(sortie)
    z = zipfile.ZipFile(entree); infos = z.infolist(); F = {i.filename: z.read(i.filename) for i in infos}; avant = dict(F)
    bilan, ids = supprimer(F, racines)
    E = controler(avant, F, ids)
    with zipfile.ZipFile(sortie, 'x', zipfile.ZIP_DEFLATED) as zo:
        for i in infos: zo.writestr(i, F[i.filename])
    return bilan, E


def main(a=None):
    a = sys.argv[1:] if a is None else a
    if len(a) < 4 or '--fils' not in a: print('USAGE: ' + __doc__.split('USAGE: ')[1].split('\n')[0]); return 2
    entree, sortie = a[0], a[1]
    if os.path.exists(sortie): print(f'existe déjà, jamais écrasé : {sortie}'); return 3
    L = json.load(open(a[a.index('--fils') + 1], encoding='utf-8')); L = L['racines'] if isinstance(L, dict) else L
    try: bilan, E = traiter(entree, sortie, [str(x) for x in L])
    except KeyError as e: print(e); return 4
    print('supprimé : ' + ', '.join(f'{k} {v}' for k, v in sorted(bilan.items())))
    print('contrôle : conforme' if not E else f'contrôle : {len(E)} écart(s)'); [print('  ', x) for x in E[:30]]
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '_compat'))
        from cc_lib_v4 import evenement
        evenement(OUTIL, VERSION, 'suppression', dict(fils=bilan.get('fils', 0), commentaires=bilan.get('commentaires', 0), ecarts=len(E)))
    except Exception: pass
    return 1 if E else 0


if __name__ == '__main__':
    sys.exit(main())
