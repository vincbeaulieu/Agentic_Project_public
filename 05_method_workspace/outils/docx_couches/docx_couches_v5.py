"""
OUTIL: docx_couches
VERSION: 5
RESUME: Docx en suivi : refuse les révisions d'un seul auteur (insertions, suppressions, marques de paragraphe, rangées, et depuis la v3 modifications de mise en forme suivies w:rPrChange et w:pPrChange) et décrit chaque paragraphe en couches comparables (texte, rPr, chaîne des révisions, marque, pPr ; un w:rPr ou w:pPr vide compte comme absent) ; compte les révisions par auteur ; liste les commentaires.
USAGE: python3 docx_couches_v5.py <docx> <auteur> <reference.docx>   (contrôle : refuser <auteur> dans <docx> redonne <reference>)
ENTREES: docx en suivi des modifications
SORTIES: « refus conforme » ou la liste des paragraphes en écart ; code 0/1
CATEGORIE: docx
BANC: tests/test_docx_couches_v5.py
REMPLACE: docx_couches_v4 (l'empreinte des propriétés comptait l'identifiant et la date d'une mise en forme suivie (rPrChange, pPrChange) : un run scindé par une passe, dont les morceaux reçoivent des identifiants neufs, différait de l'original après refus alors que rien d'autre n'avait changé ; identifiant et dates des éléments de révision exclus de l'empreinte ; trouvé par la renumérotation des références) ; v4 : docx_couches_v3 (les déplacements suivis d'un auteur n'étaient pas refusés : moveFrom gardé en texte supprimé, moveTo gardé, marques de paragraphe moveFrom / moveTo et plages de déplacement laissées ; le contrôle « refus = source » d'une passe avec déplacements échouait ; refuser rétablit maintenant le texte à la source (moveFrom déplié, texte rendu en w:t) et retire la copie déplacée (moveTo, paragraphe à marque moveTo) ; trouvé en préparant la renumérotation des références) ; v3 : docx_couches_v2 (les modifications de mise en forme suivies d'un auteur n'étaient pas refusées : après refus, une passe de mise en forme laissait ses tailles et propriétés de paragraphe, et le contrôle D3 « refus = source » échouait à tort ; un w:rPr ou w:pPr vide laissé par un refus comptait comme une différence) ; v2 : docx_couches_v1 (lancé en ligne de commande sans argument suffisant, affiche la ligne USAGE de son en-tête et sort avec le code 2, au lieu d'une trace ValueError de code 1 ; fonctions de la bibliothèque inchangées) ; v1 : 11_reevaluation/scripts/refuser_auteur_v1.py (même logique, en-tête standard et fonctions réutilisables)
"""
import sys, zipfile, hashlib, collections
from lxml import etree
WN = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W14 = 'http://schemas.microsoft.com/office/word/2010/wordml'
W15 = 'http://schemas.microsoft.com/office/word/2012/wordml'
def q(t, ns=WN): return '{%s}%s' % (ns, t)
def ln(e): return etree.QName(e).localname if isinstance(e.tag, str) else None
KEEP = ('commentRangeStart', 'commentRangeEnd', 'bookmarkStart', 'bookmarkEnd')
REV = ('ins', 'del', 'moveFrom', 'moveTo')


def deplier(e):
    par = e.getparent(); idx = par.index(e)
    for ch in list(e): par.insert(idx, ch); idx += 1
    par.remove(e)


def _plages(root, auteur):
    """Identifiants des plages de déplacement ouvertes par l'auteur (la fin de plage ne porte pas d'auteur)."""
    return {e.get(q('id')) for t in ('moveFromRangeStart', 'moveToRangeStart') for e in root.iter(q(t)) if e.get(q('author')) == auteur}


def refuser(root, auteur):
    n = collections.Counter()
    for tr in list(root.iter(q('tr'))):
        trpr = tr.find(q('trPr'))
        if trpr is None: continue
        if any(m.get(q('author')) == auteur for m in trpr.findall(q('ins'))):
            tr.getparent().remove(tr); n['ligne_ins'] += 1; continue
        for m in trpr.findall(q('del')):
            if m.get(q('author')) == auteur: trpr.remove(m); n['ligne_del'] += 1
    for ch in list(root.iter(q('rPrChange'))):                          # mise en forme d'un passage : anciennes propriétés rétablies
        if ch.get(q('author')) != auteur or ln(ch.getparent()) != 'rPr': continue
        rp = ch.getparent(); ancien = ch.find(q('rPr'))
        for x in list(rp): rp.remove(x)
        for x in (list(ancien) if ancien is not None else []): rp.append(x)
        n['rPrChange'] += 1
    for ch in list(root.iter(q('pPrChange'))):                          # propriétés de paragraphe : anciennes rétablies (marque et section gardées)
        if ch.get(q('author')) != auteur or ln(ch.getparent()) != 'pPr': continue
        ppr = ch.getparent(); ancien = ch.find(q('pPr'))
        for x in list(ppr):
            if ln(x) not in ('rPr', 'sectPr'): ppr.remove(x)
        for k, x in enumerate(list(ancien) if ancien is not None else []): ppr.insert(k, x)
        n['pPrChange'] += 1
    pl = _plages(root, auteur)
    for t in ('moveFromRangeStart', 'moveFromRangeEnd', 'moveToRangeStart', 'moveToRangeEnd'):     # v4 : plages de déplacement
        for e in list(root.iter(q(t))):
            if e.get(q('author')) == auteur or (ln(e).endswith('End') and e.get(q('id')) in pl): e.getparent().remove(e)
    for p in list(root.iter(q('p'))):
        ppr = p.find(q('pPr')); rp = ppr.find(q('rPr')) if ppr is not None else None
        if rp is None: continue
        for m in list(rp):
            if ln(m) == 'moveFrom' and m.get(q('author')) == auteur: rp.remove(m); n['par_moveFrom'] += 1; continue
            if ln(m) == 'moveTo' and m.get(q('author')) == auteur: m.tag = q('ins'); n['par_moveTo'] += 1      # copie déplacée : retirée comme un paragraphe inséré
            if ln(m) == 'ins' and m.get(q('author')) == auteur:
                prev = p.getprevious()
                for x in [x for x in p.iter() if ln(x) in KEEP]:
                    x.getparent().remove(x)
                    if prev is not None and ln(prev) == 'p': prev.append(x)
                p.getparent().remove(p); n['par_ins'] += 1; break
            if ln(m) == 'del' and m.get(q('author')) == auteur: rp.remove(m); n['par_del'] += 1
    for e in list(root.iter(q('ins'), q('moveTo'))):
        if e.getparent() is None or ln(e.getparent()) in ('rPr', 'trPr') or e.get(q('author')) != auteur: continue
        for x in [x for x in e.iter() if ln(x) in KEEP]:
            x.getparent().remove(x); e.addprevious(x)
        e.getparent().remove(e); n['ins'] += 1
    for e in list(root.iter(q('del'), q('moveFrom'))):
        if e.getparent() is None or ln(e.getparent()) in ('rPr', 'trPr') or e.get(q('author')) != auteur: continue
        for t in e.iter(q('delText')):
            if not any(ln(a) in ('del', 'moveFrom') and a is not e for a in t.iterancestors()): t.tag = q('t')
        for t in e.iter(q('delInstrText')):
            if not any(ln(a) in ('del', 'moveFrom') and a is not e for a in t.iterancestors()): t.tag = q('instrText')
        deplier(e); n[ln(e)] += 1
    return dict(n)


def _canon(e):
    """Empreinte de propriétés (rPr ou pPr), sans rsid ni style de référence de commentaire ; un rPr vide (dans un pPr) est retiré ; vide = ''."""
    c = etree.fromstring(etree.tostring(e))
    for x in c.iter():
        for a in list(x.attrib):
            if 'rsid' in a: del x.attrib[a]
        if isinstance(x.tag, str) and ln(x).endswith('Change'):            # v5 : identifiant et dates d'une révision : métadonnées, pas contenu
            for a in list(x.attrib):
                if etree.QName(a).localname in ('id', 'date', 'dateUtc'): del x.attrib[a]
    for x in list(c):
        if ln(x) == 'rStyle' and x.get(q('val')) in ('CommentReference', 'Marquedecommentaire'): c.remove(x)
        elif ln(x) == 'rPr' and len(x) == 0 and not x.attrib: c.remove(x)
    if len(c) == 0 and not c.attrib: return ''
    return hashlib.md5(etree.tostring(c, method='c14n')).hexdigest()[:8]


def _chaine(e, p):
    out = []
    for a in e.iterancestors():
        if a is p: break
        if ln(a) in REV: out.append((ln(a), a.get(q('author')), a.get(q('date'))))
    return tuple(out)


def couches(root):
    res = []
    for p in root.iter(q('p')):
        if any(ln(a) == 'Fallback' for a in p.iterancestors()): continue
        segs = []
        for t in p.iter(q('t'), q('delText'), q('instrText'), q('delInstrText'), q('tab'), q('br')):
            if next(t.iterancestors(q('p'))) is not p: continue
            r = t.getparent()
            if ln(r) != 'r': continue
            txt = (t.text or '') if ln(t) in ('t', 'delText', 'instrText', 'delInstrText') else ('\t' if ln(t) == 'tab' else '\n')
            rp = r.find(q('rPr'))
            key = (ln(t).replace('del', '').lower(), _canon(rp) if rp is not None else '', _chaine(r, p))
            if segs and segs[-1][0] == key: segs[-1][1] += txt
            else: segs.append([key, txt])
        ppr = p.find(q('pPr')); m = ()
        if ppr is not None and ppr.find(q('rPr')) is not None:
            m = tuple((ln(x), x.get(q('author')), x.get(q('date'))) for x in ppr.find(q('rPr')) if ln(x) in REV)
        res.append((p.get('{%s}paraId' % W14), m, _canon(ppr) if ppr is not None else '', tuple((k, v) for k, v in segs)))
    return res


def comparer_refus(docx, auteur, reference):
    root = etree.fromstring(zipfile.ZipFile(docx).read('word/document.xml'))
    n = refuser(root, auteur)
    a = couches(root); b = couches(etree.fromstring(zipfile.ZipFile(reference).read('word/document.xml')))
    ecarts = [] if len(a) == len(b) else [f'nombre de paragraphes {len(a)} / {len(b)}']
    for x, y in zip(a, b):
        if x != y: ecarts.append(y[0])
    return n, ecarts


def revisions_par_auteur(docx):
    root = etree.fromstring(zipfile.ZipFile(docx).read('word/document.xml'))
    c = collections.Counter()
    for t in REV + ('rPrChange', 'pPrChange'):
        for e in root.iter(q(t)): c[(t, e.get(q('author')))] += 1
    return c


def commentaires(docx):
    z = zipfile.ZipFile(docx)
    if 'word/comments.xml' not in z.namelist(): return {}
    com = etree.fromstring(z.read('word/comments.xml'))
    out = {}
    par = {}
    if 'word/commentsExtended.xml' in z.namelist():
        ext = etree.fromstring(z.read('word/commentsExtended.xml'))
        par = {c.get(q('paraId', W15)): c.get(q('paraIdParent', W15)) for c in ext.iter(q('commentEx', W15))}
    last = {}
    for c in com.iter(q('comment')):
        ps = c.findall(q('p'))
        last[c.get(q('id'))] = ps[-1].get(q('paraId', W14)) if ps else None
        out[c.get(q('id'))] = dict(auteur=c.get(q('author')), date=c.get(q('date')),
                                   texte='\n'.join(''.join(t.text or '' for t in p.iter(q('t'))) for p in ps))
    l2id = {v: k for k, v in last.items()}
    for k in out:
        out[k]['parent'] = l2id.get(par.get(last[k]))
    for k in out:
        r = k; seen = set()
        while out[r]['parent'] and r not in seen: seen.add(r); r = out[r]['parent']
        out[k]['racine'] = r
    return out


if __name__ == '__main__':
    if len(sys.argv) < 4: print('USAGE: ' + __doc__.split('USAGE: ')[1].split('\n')[0]); sys.exit(2)
    docx, auteur, ref = sys.argv[1:4]
    n, ec = comparer_refus(docx, auteur, ref)
    print('refusé :', n); print('refus conforme' if not ec else f'ÉCART ({len(ec)}) : {ec[:20]}')
    sys.exit(0 if not ec else 1)
