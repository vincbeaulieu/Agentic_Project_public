"""
OUTIL: moteur_revision_multi
VERSION: 2
RESUME: Moteur lxml de révision Word en suivi des modifications, sûr en présence de révisions d'autres auteurs : texte de travail = vue « tout accepté » ; remplacement par diff de mots ; insertion et suppression de paragraphes et de lignes de tableau ; déplacements suivis ; réponses dans les fils ; jamais d'insertion à l'intérieur d'une révision d'un autre auteur (conteneur scindé) ; refuser nos révisions redonne le document reçu.
USAGE: from moteur_revision_multi_v1 import DocR  (d = DocR(docx, author='Reevaluation - Claude', init='RC'))
ENTREES: docx (tous auteurs)
SORTIES: objet document ; d.save(sortie)
CATEGORIE: docx
BANC: tests/test_moteur_revision_multi_v2.py
REMPLACE: moteur_revision_multi_v1 (un docx sans commentaire, aux parts de commentaires vides ou absentes, s'ouvre, se révise et s'enregistre ; les parts manquantes ne sont créées, avec type de contenu et relation, que si un commentaire ou une réponse est ajouté) ; v1 : 10_revision_01/scripts/revision_engine.py + revision_engine_v2.py + revision_engine_v8.py et 11_reevaluation revision_engine_reeval_v1.py (réunis en un seul fichier versionné, sans import de modules non versionnés)
"""
from lxml import etree
import copy
import re, copy, difflib
import re, copy, zipfile, random, datetime, html

# ===================== revision_engine_v1.py =====================

WN = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W14 = 'http://schemas.microsoft.com/office/word/2010/wordml'
W15 = 'http://schemas.microsoft.com/office/word/2012/wordml'
MN = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
XMLNS = 'http://www.w3.org/XML/1998/namespace'
def q(t): return '{%s}%s' % (WN, t)
def ln(e): return etree.QName(e).localname if isinstance(e.tag, str) else None
AUTHOR = 'Correction - Claude'; INIT = 'CC'
WORD = re.compile(r'\w', re.U)
# Parts des commentaires : (racine ouvrante, fermeture, type de contenu, type de relation). Une part absente (ou vide) n'est
# créée à l'enregistrement que si un commentaire ou une réponse a été ajouté.
_CT = 'application/vnd.openxmlformats-officedocument.wordprocessingml.'
PARTS_CM = {
    'word/comments.xml': (f'<w:comments xmlns:w="{WN}" xmlns:w14="{W14}" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" mc:Ignorable="w14">',
                          '</w:comments>', _CT + 'comments+xml', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments'),
    'word/commentsExtended.xml': (f'<w15:commentsEx xmlns:w15="{W15}">', '</w15:commentsEx>', _CT + 'commentsExtended+xml',
                                  'http://schemas.microsoft.com/office/2011/relationships/commentsExtended'),
    'word/commentsIds.xml': ('<w16cid:commentsIds xmlns:w16cid="http://schemas.microsoft.com/office/word/2016/wordml/cid">', '</w16cid:commentsIds>',
                             _CT + 'commentsIds+xml', 'http://schemas.microsoft.com/office/2016/09/relationships/commentsIds'),
    'word/commentsExtensible.xml': ('<w16cex:commentsExtensible xmlns:w16cex="http://schemas.microsoft.com/office/word/2018/wordml/cex">',
                                    '</w16cex:commentsExtensible>', _CT + 'commentsExtensible+xml',
                                    'http://schemas.microsoft.com/office/2018/08/relationships/commentsExtensible'),
    'word/people.xml': (f'<w15:people xmlns:w15="{W15}">', '</w15:people>', _CT + 'people+xml', 'http://schemas.microsoft.com/office/2011/relationships/people')}
def squelette(n): return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n' + PARTS_CM[n][0] + PARTS_CM[n][1]

class Doc:
    def __init__(self, path, author=AUTHOR, init=INIT):
        self.zin = zipfile.ZipFile(path)
        self.doc = etree.fromstring(self.zin.read('word/document.xml'))
        self.body = self.doc.find(q('body'))
        self.author, self.init = author, init
        self.now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        allxml = b''.join(self.zin.read(n) for n in self.zin.namelist() if n.endswith('.xml'))
        self.used_para = {x.decode().upper() for x in re.findall(rb'paraId="([0-9A-Fa-f]{8})"', allxml)}
        self.used_dur = {x.decode().upper() for x in re.findall(rb'durableId="([0-9A-Fa-f]{8})"', allxml)}
        self.rev = max((int(x) for x in re.findall(rb'w:id="(-?\d+)"', allxml)), default=0) + 1000
        noms = set(self.zin.namelist())
        lu = {n: (self.zin.read(n).decode('utf-8') if n in noms else '') for n in PARTS_CM}
        self.parts_cm = {n: (x if x.strip() else None) for n, x in lu.items()}   # None : part absente ou vide
        self.cm_xml = self.parts_cm['word/comments.xml'] or squelette('word/comments.xml')
        self.cmroot = etree.fromstring(self.cm_xml.encode())
        self.comments = {c.get(q('id')): c for c in self.cmroot.iter(q('comment'))}
        self.last_para = {k: c.findall(q('p'))[-1].get('{%s}paraId' % W14) for k, c in self.comments.items()}
        self.ext_xml = self.parts_cm['word/commentsExtended.xml'] or squelette('word/commentsExtended.xml')
        ext = etree.fromstring(self.ext_xml.encode())
        self.parent_of_para = {x.get('{%s}paraId' % W15): x.get('{%s}paraIdParent' % W15) for x in ext}
        self.para2id = {v: k for k, v in self.last_para.items()}
        self.next_cid = max((int(k) for k in self.comments), default=-1) + 1
        self.new_c, self.new_ex, self.new_ids, self.new_cx = [], [], [], []
        self.reindex()
    def reindex(self):
        self.plist = [p for p in self.body.iter(q('p')) if 'Fallback' not in [ln(a) for a in p.iterancestors()]]
        self.byid = {p.get('{%s}paraId' % W14): p for p in self.plist}
    def P(self, pid): return self.byid[pid]
    # ---- ids
    def rev_id(self):
        self.rev += 1; return str(self.rev)
    def newhex(self, used):
        while True:
            h = f'{random.randint(0x100000, 0x7FFFFFFE):08X}'
            if h not in used: used.add(h); return h
    def mk(self, tag, **attrs):
        e = etree.Element(q(tag))
        for a, v in attrs.items(): e.set(q(a), v)
        return e
    def track(self, tag): return self.mk(tag, id=self.rev_id(), author=self.author, date=self.now)
    # ---- texte visible
    @staticmethod
    def owner_p(r): return next(r.iterancestors(q('p')))
    @staticmethod
    def in_del(r): return any(ln(a) == 'del' for a in r.iterancestors())
    def our_ins(self, r):
        for a in r.iterancestors():
            if ln(a) == 'ins' and a.get(q('author')) == self.author: return a
            if ln(a) == 'p': return None
        return None
    def runs_of(self, p):
        return [r for r in p.iter(q('r')) if self.owner_p(r) is p and not self.in_del(r)
                and not any(ln(a) == 'oMath' for a in r.iterancestors())]
    @staticmethod
    def pieces(r):
        out = []
        for ch in r:
            n = ln(ch)
            if n == 't': out.append((ch, ch.text or ''))
            elif n == 'tab': out.append((ch, '\t'))
            elif n in ('br', 'cr'): out.append((ch, '\n'))
            elif n == 'rPr': continue
            else: out.append((ch, ''))
        return out
    def layout(self, p):
        sp = []; pos = 0
        for r in self.runs_of(p):
            L = sum(len(t) for _, t in self.pieces(r)); sp.append((r, pos, pos + L)); pos += L
        return sp
    def ptext(self, p): return ''.join(t for r in self.runs_of(p) for _, t in self.pieces(r))
    def text(self, pid): return self.ptext(self.P(pid))
    def split_run(self, r, k):
        nr = copy.deepcopy(r); pr, npr = self.pieces(r), self.pieces(nr); pos = 0
        for (ch, t), (nch, nt) in zip(pr, npr):
            a, b = pos, pos + len(t)
            if len(t) == 0:
                if a < k: nr.remove(nch)
                else: r.remove(ch)
            elif b <= k: nr.remove(nch)
            elif a >= k: r.remove(ch)
            else:
                ch.text = t[:k - a]; nch.text = t[k - a:]
                ch.set('{%s}space' % XMLNS, 'preserve'); nch.set('{%s}space' % XMLNS, 'preserve')
            pos = b
        r.addnext(nr)
    def boundary(self, p, pos):
        for r, a, b in self.layout(p):
            if a < pos < b: self.split_run(r, pos - a); return
    @staticmethod
    def base_rpr(r):
        rp = r.find(q('rPr'))
        if rp is None: return None
        rp = copy.deepcopy(rp)
        for st in rp.findall(q('rStyle')):
            if st.get(q('val')) in ('CommentReference', 'Marquedecommentaire'): rp.remove(st)
        for x in rp.findall(q('rPrChange')): rp.remove(x)
        return rp
    def text_run(self, text, rpr):
        r = self.mk('r')
        if rpr is not None: r.append(copy.deepcopy(rpr))
        parts = text.split('\t')
        for k, part in enumerate(parts):
            if k: r.append(self.mk('tab'))
            if part:
                t = etree.SubElement(r, q('t')); t.text = part; t.set('{%s}space' % XMLNS, 'preserve')
        return r
    def delete_run(self, r):
        oi = self.our_ins(r)
        if oi is not None:
            self._rescue(r); r.getparent().remove(r)
            if len(oi) == 0: oi.getparent().remove(oi)
            return
        for t in r.iter(q('t')): t.tag = q('delText')
        for t in r.iter(q('instrText')): t.tag = q('delInstrText')
        d = self.track('del'); r.addprevious(d); d.append(r)
    def first_text_rpr(self, p):
        for r in self.runs_of(p):
            if any(ln(c) == 't' and (c.text or '').strip() for c in r): return self.base_rpr(r)
        return None
    @staticmethod
    def norm_find(hay, needle):
        k = hay.find(needle)
        if k >= 0: return k, k + len(needle)
        NOR = {' ': ' ', ' ': ' ', '’': "'"}
        h2 = ''.join(NOR.get(c, c) for c in hay); n2 = ''.join(NOR.get(c, c) for c in needle)
        k = h2.find(n2)
        return (k, k + len(n2)) if k >= 0 else None
    @staticmethod
    def trim_common(a, b):
        i = 0
        while i < min(len(a), len(b)) and a[i] == b[i]: i += 1
        while i > 0 and WORD.match(a[i - 1]) and (i < len(a) and WORD.match(a[i]) or i < len(b) and WORD.match(b[i])): i -= 1
        j = 0
        while j < min(len(a), len(b)) - i and a[len(a) - 1 - j] == b[len(b) - 1 - j]: j += 1
        while j > 0 and WORD.match(a[len(a) - j]) and ((len(a) - j - 1 >= i and WORD.match(a[len(a) - j - 1])) or (len(b) - j - 1 >= i and WORD.match(b[len(b) - j - 1]))): j -= 1
        return i, j
    def replace(self, pid, ancien, nouveau, count=1):
        p = self.P(pid); txt = self.ptext(p)
        f = self.norm_find(txt, ancien)
        if f is None: raise ValueError(f'ancien introuvable dans {pid}: {ancien[:60]!r}')
        s0, e0 = f; old = txt[s0:e0]
        i, j = self.trim_common(old, nouveau)
        s, e = s0 + i, e0 - j
        newmid = nouveau[i:len(nouveau) - j] if j else nouveau[i:]
        if s == e and not newmid: return 'aucun changement'
        self.boundary(p, s); self.boundary(p, e)
        lay = self.layout(p)
        inside = [r for r, a, b in lay if a >= s and b <= e and b > a]
        prev = [r for r, a, b in lay if b == s and b > a]
        rpr_src = max(inside, key=lambda r: sum(len(t) for _, t in self.pieces(r))) if inside else (prev[-1] if prev else (lay[0][0] if lay else None))
        rpr = self.base_rpr(rpr_src) if rpr_src is not None else None
        anchor = inside[-1] if inside else (prev[-1] if prev else None)
        for r in inside: self.delete_run(r)
        if newmid:
            ins = self.track('ins'); ins.append(self.text_run(newmid, rpr))
            if anchor is not None and anchor.getparent() is not None and ln(anchor.getparent()) == 'ins':
                # ancre déjà dans une insertion : le nouveau run s'insère sans nouvel enveloppe
                anchor.addnext(self.text_run(newmid, rpr)); return 'ok'
            if anchor is not None:
                tgt = anchor; par = anchor.getparent()
                if par is not None and ln(par) == 'del': tgt = par
                if tgt.getparent() is None:
                    # run retiré (notre propre insertion) : insérer à la position du run précédent encore présent
                    prev2 = [r for r, a, b in lay if b <= s and r.getparent() is not None]
                    if prev2:
                        t2 = prev2[-1]; par2 = t2.getparent()
                        if ln(par2) == 'ins': t2.addnext(self.text_run(newmid, rpr)); return 'ok'
                        t2 = par2 if ln(par2) == 'del' else t2; t2.addnext(ins)
                    else:
                        nxt = [r for r, a, b in lay if a >= e and r.getparent() is not None]
                        if nxt:
                            t2 = nxt[0]; par2 = t2.getparent()
                            if ln(par2) == 'ins': t2.addprevious(self.text_run(newmid, rpr)); return 'ok'
                            t2 = par2 if ln(par2) == 'del' else t2; t2.addprevious(ins)
                        else:
                            ppr = p.find(q('pPr')); (ppr.addnext(ins) if ppr is not None else p.insert(0, ins))
                else: tgt.addnext(ins)
            else:
                nxt = [r for r, a, b in lay if a == s]
                if nxt:
                    t = nxt[0]; par = t.getparent()
                    if ln(par) == 'ins': t.addprevious(self.text_run(newmid, rpr)); return 'ok'
                    t = par if ln(par) == 'del' else t; t.addprevious(ins)
                else:
                    ppr = p.find(q('pPr')); (ppr.addnext(ins) if ppr is not None else p.insert(0, ins))
        return 'ok'
    def replace_all(self, ancien, nouveau, pids=None):
        n = 0
        for p in list(self.plist):
            pid = p.get('{%s}paraId' % W14)
            if pids is not None and pid not in pids: continue
            while ancien in self.ptext(p):
                before = self.ptext(p)
                self.replace(pid, ancien, nouveau)
                if self.ptext(p) == before: break
                n += 1
        return n
    def new_paragraph(self, modele, texte=None, rpr_from=None):
        np_ = self.mk('p'); ppr = modele.find(q('pPr'))
        if ppr is not None:
            ppr = copy.deepcopy(ppr)
            for x in ppr.findall(q('sectPr')) + ppr.findall(q('pPrChange')): ppr.remove(x)
            rp = ppr.find(q('rPr'))
            if rp is None: rp = self.mk('rPr'); ppr.append(rp)
            for x in list(rp):
                if ln(x) in ('ins', 'del'): rp.remove(x)
            rp.insert(0, self.track('ins'))
        else:
            ppr = self.mk('pPr'); rp = etree.SubElement(ppr, q('rPr')); rp.append(self.track('ins'))
        np_.append(ppr)
        np_.set('{%s}paraId' % W14, self.newhex(self.used_para)); np_.set('{%s}textId' % W14, '77777777')
        if texte is not None:
            rpr = self.first_text_rpr(rpr_from if rpr_from is not None else modele)
            ins = self.track('ins'); ins.append(self.text_run(texte, rpr)); np_.append(ins)
        return np_
    def insert_after(self, pid, texte, modele_pid=None, rpr_pid=None):
        anc = self.P(pid); mod = self.P(modele_pid) if modele_pid else anc
        np_ = self.new_paragraph(mod, texte, self.P(rpr_pid) if rpr_pid else None)
        anc.addnext(np_); self.reindex(); return np_.get('{%s}paraId' % W14)
    def insert_before(self, pid, texte, modele_pid=None, rpr_pid=None):
        anc = self.P(pid); mod = self.P(modele_pid) if modele_pid else anc
        np_ = self.new_paragraph(mod, texte, self.P(rpr_pid) if rpr_pid else None)
        anc.addprevious(np_); self.reindex(); return np_.get('{%s}paraId' % W14)
    def delete_paragraph(self, pid):
        p = self.P(pid)
        for r in self.runs_of(p): self.delete_run(r)
        ppr = p.find(q('pPr'))
        if ppr is None: ppr = self.mk('pPr'); p.insert(0, ppr)
        rp = ppr.find(q('rPr'))
        if rp is None: rp = self.mk('rPr'); ppr.append(rp)
        rp.insert(0, self.track('del'))
    # ---- accepter / refuser les révisions d'un paragraphe (tous auteurs)
    KEEP = ('commentRangeStart', 'commentRangeEnd', 'bookmarkStart', 'bookmarkEnd')
    def _rescue(self, e):
        """Avant de retirer e : sort les marqueurs de commentaire/signet et les runs commentReference juste avant e."""
        for x in list(e.iter()):
            if x is e: continue
            if ln(x) in self.KEEP or (ln(x) == 'r' and x.find(q('commentReference')) is not None):
                x.getparent().remove(x); e.addprevious(x)
    @staticmethod
    def _unwrap(e):
        par = e.getparent(); idx = par.index(e)
        for ch in list(e): par.insert(idx, ch); idx += 1
        par.remove(e)
    def mark(self, p):
        ppr = p.find(q('pPr'))
        if ppr is not None and ppr.find(q('rPr')) is not None:
            rp = ppr.find(q('rPr'))
            if rp.find(q('ins')) is not None: return 'ins'
            if rp.find(q('del')) is not None: return 'del'
        return None
    def _clear_mark(self, p):
        ppr = p.find(q('pPr'))
        if ppr is not None and ppr.find(q('rPr')) is not None:
            rp = ppr.find(q('rPr'))
            for x in rp.findall(q('ins')) + rp.findall(q('del')): rp.remove(x)
    def accept(self, pid):
        p = self.P(pid); m = self.mark(p)
        for d in [x for x in p.iter(q('del')) if ln(x.getparent()) != 'rPr']: self._rescue(d); d.getparent().remove(d)
        for i in [x for x in p.iter(q('ins')) if ln(x.getparent()) != 'rPr']: self._unwrap(i)
        for x in [x for x in p.iter() if ln(x) in ('rPrChange', 'pPrChange')]: x.getparent().remove(x)
        self._clear_mark(p)
        if m == 'del':
            # marque de paragraphe supprimée : fusion avec le suivant si contenu, sinon retrait
            content = [c for c in p if ln(c) != 'pPr']
            nxt = p.getnext()
            if content and nxt is not None and ln(nxt) == 'p':
                ppr = nxt.find(q('pPr')); idx = 1 if ppr is not None else 0
                for c in content: nxt.insert(idx, c); idx += 1
            self._rescue_para(p); p.getparent().remove(p)
        self.reindex()
    def _rescue_para(self, p):
        keep = [x for x in p.iter() if ln(x) in self.KEEP or (ln(x) == 'r' and x.find(q('commentReference')) is not None)]
        if not keep: return
        nb = p.getprevious() if p.getprevious() is not None and ln(p.getprevious()) == 'p' else p.getnext()
        for x in keep:
            x.getparent().remove(x)
            if nb is not None: nb.append(x)
    def reject(self, pid):
        p = self.P(pid); m = self.mark(p)
        for i in [x for x in p.iter(q('ins')) if ln(x.getparent()) != 'rPr']:
            self._rescue(i); par = i.getparent(); par.remove(i)
            if ln(par) == 'oMath' and len(par) == 0: par.getparent().remove(par)
        for d in [x for x in p.iter(q('del')) if ln(x.getparent()) != 'rPr']:
            for t in d.iter(q('delText')): t.tag = q('t')
            for t in d.iter(q('delInstrText')): t.tag = q('instrText')
            self._unwrap(d)
        for x in [x for x in p.iter() if ln(x) in ('rPrChange', 'pPrChange')]:
            par = x.getparent()
            if ln(par) in ('rPr', 'pPr'):
                old = x.find(q('rPr')) if ln(x) == 'rPrChange' else x.find(q('pPr'))
                for c in list(par):
                    if c is not x: par.remove(c)
                if old is not None:
                    for c in list(old): par.append(c)
            par.remove(x)
        self._clear_mark(p)
        if m == 'ins':
            content = [c for c in p if ln(c) != 'pPr']
            prev = p.getprevious()
            if content and prev is not None and ln(prev) == 'p':
                for c in content: prev.append(c)
            self._rescue_para(p); p.getparent().remove(p)
        self.reindex()
    def has_revisions(self, pid):
        p = self.P(pid)
        return any(ln(x) in ('ins', 'del') for x in p.iter() if ln(x.getparent()) != 'rPr') or self.mark(p) is not None
    # ---- commentaires
    def root_of(self, cid):
        pid = self.last_para[cid]
        while self.parent_of_para.get(pid): pid = self.parent_of_para[pid]
        return self.para2id[pid]
    def comment_text(self, cid):
        return '\n'.join(''.join(t.text or '' for t in p.iter(q('t'))) for p in self.comments[cid].findall(q('p')))
    def anchor_pid(self, cid):
        st = self.doc.find('.//' + q('commentRangeStart') + f'[@{{{WN}}}id="{cid}"]')
        if st is None: st = self.doc.find('.//' + q('commentReference') + f'[@{{{WN}}}id="{cid}"]')
        return next(st.iterancestors(q('p'))).get('{%s}paraId' % W14) if st is not None else None
    def anchor_pids(self, cid):
        st = self.doc.find('.//' + q('commentRangeStart') + f'[@{{{WN}}}id="{cid}"]')
        en = self.doc.find('.//' + q('commentRangeEnd') + f'[@{{{WN}}}id="{cid}"]')
        if st is None or en is None: return [self.anchor_pid(cid)]
        p0, p1 = next(st.iterancestors(q('p'))), next(en.iterancestors(q('p')))
        out = []; started = False
        for p in self.plist:
            if p is p0: started = True
            if started: out.append(p.get('{%s}paraId' % W14))
            if p is p1: break
        return out
    def _para_xml(self, pid, text, first=False, bold=False):
        t = html.escape(text, quote=False)
        s = f'<w:p w14:paraId="{pid}" w14:textId="77777777"><w:pPr><w:pStyle w:val="CommentText"/></w:pPr>'
        if first: s += '<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:annotationRef/></w:r>'
        s += f'<w:r>{"<w:rPr><w:b/></w:rPr>" if bold else ""}<w:t xml:space="preserve">{t}</w:t></w:r></w:p>'
        return s
    def _refrun(self, cid):
        r = self.mk('r'); rp = etree.SubElement(r, q('rPr')); st = etree.SubElement(rp, q('rStyle')); st.set(q('val'), 'CommentReference')
        cr = etree.SubElement(r, q('commentReference')); cr.set(q('id'), str(cid)); return r
    def _marker(self, tag, cid): return self.doc.find('.//' + q(tag) + f'[@{{{WN}}}id="{cid}"]')
    def reply(self, cid, lines):
        """Réponse dans le fil du commentaire cid (rattachée à la racine)."""
        root = self.root_of(cid)
        nid = self.next_cid; self.next_cid += 1
        pids = [self.newhex(self.used_para) for _ in lines]
        body_xml = ''.join(self._para_xml(pids[k], l, first=(k == 0), bold=(k == 0)) for k, l in enumerate(lines))
        self.new_c.append(f'<w:comment w:id="{nid}" w:author="{self.author}" w:date="{self.now}" w:initials="{self.init}">{body_xml}</w:comment>')
        self.new_ex.append(f'<w15:commentEx w15:paraId="{pids[-1]}" w15:paraIdParent="{self.last_para[root]}" w15:done="0"/>')
        d = self.newhex(self.used_dur)
        self.new_ids.append(f'<w16cid:commentId w16cid:paraId="{pids[-1]}" w16cid:durableId="{d}"/>')
        self.new_cx.append(f'<w16cex:commentExtensible w16cex:durableId="{d}" w16cex:dateUtc="{self.now}"/>')
        st, en, rf = self._marker('commentRangeStart', cid), self._marker('commentRangeEnd', cid), self._marker('commentReference', cid)
        if st is None or en is None or rf is None:
            st, en, rf = self._marker('commentRangeStart', root), self._marker('commentRangeEnd', root), self._marker('commentReference', root)
        if st is not None and en is not None:
            st.addnext(self.mk('commentRangeStart', id=str(nid))); en.addprevious(self.mk('commentRangeEnd', id=str(nid)))
        rf.getparent().addnext(self._refrun(nid))
        return nid
    def thread_ids(self, cid):
        root = self.root_of(cid)
        return [k for k in self.comments if self.root_of(k) == root]
    def resolve_thread(self, cid):
        """Marque tout le fil (racine + réponses, y compris celles ajoutées dans cette session) comme résolu (w15:done="1")."""
        root = self.root_of(cid)
        paras = {self.last_para[k] for k in self.thread_ids(cid)}
        if not hasattr(self, 'resolved_paras'): self.resolved_paras = set()
        self.resolved_paras |= paras
        for pa in paras:
            self.ext_xml = re.sub(r'(<w15:commentEx\b[^>]*w15:paraId="%s"[^>]*?)\s*w15:done="\d"' % pa, r'\1 w15:done="1"', self.ext_xml)
            if re.search(r'<w15:commentEx\b[^>]*w15:paraId="%s"[^>]*w15:done="1"' % pa, self.ext_xml) is None:
                self.ext_xml = re.sub(r'(<w15:commentEx\b[^>]*w15:paraId="%s"[^>]*?)(\s*/>)' % pa, r'\1 w15:done="1"\2', self.ext_xml)
        self.new_ex = [re.sub(r'w15:done="0"', 'w15:done="1"', x) if re.search(r'w15:paraIdParent="(%s)"' % '|'.join(paras), x) else x for x in self.new_ex]
        return root
    def new_comment(self, pid, lines):
        """Nouveau commentaire sur le paragraphe entier pid."""
        p = self.P(pid); nid = self.next_cid; self.next_cid += 1
        pids = [self.newhex(self.used_para) for _ in lines]
        body_xml = ''.join(self._para_xml(pids[k], l, first=(k == 0), bold=(k == 0)) for k, l in enumerate(lines))
        self.new_c.append(f'<w:comment w:id="{nid}" w:author="{self.author}" w:date="{self.now}" w:initials="{self.init}">{body_xml}</w:comment>')
        self.new_ex.append(f'<w15:commentEx w15:paraId="{pids[-1]}" w15:done="0"/>')
        d = self.newhex(self.used_dur)
        self.new_ids.append(f'<w16cid:commentId w16cid:paraId="{pids[-1]}" w16cid:durableId="{d}"/>')
        self.new_cx.append(f'<w16cex:commentExtensible w16cex:durableId="{d}" w16cex:dateUtc="{self.now}"/>')
        ppr = p.find(q('pPr'))
        st = self.mk('commentRangeStart', id=str(nid)); (ppr.addnext(st) if ppr is not None else p.insert(0, st))
        p.append(self.mk('commentRangeEnd', id=str(nid))); p.append(self._refrun(nid))
        return nid
    # ---- sauvegarde
    def save(self, out):
        def ins_before(xml, closing, items):
            if not items: return xml
            k = xml.rfind(closing)
            if k < 0:                                                    # racine vide auto-fermante : <x …/> -> <x …></x>
                j = xml.rfind('/>'); assert j > 0; xml = xml[:j] + '>' + closing + xml[j + 2:]; k = xml.rfind(closing)
            return xml[:k] + ''.join(items) + xml[k:]
        ajout = bool(self.new_c)                                         # parts manquantes créées seulement dans ce cas
        src = dict(self.parts_cm, **{'word/comments.xml': self.cm_xml, 'word/commentsExtended.xml': self.ext_xml})
        parts = {'word/document.xml': etree.tostring(self.doc, xml_declaration=True, encoding='UTF-8', standalone=True)}
        for n, items in (('word/comments.xml', self.new_c), ('word/commentsExtended.xml', self.new_ex),
                         ('word/commentsIds.xml', self.new_ids), ('word/commentsExtensible.xml', self.new_cx)):
            if self.parts_cm[n] is not None or ajout:
                parts[n] = ins_before(src[n] or squelette(n), PARTS_CM[n][1], items).encode('utf-8')
        pp = self.parts_cm['word/people.xml'] or (squelette('word/people.xml') if ajout else None)
        if pp is not None:
            if self.author not in pp:
                pp = ins_before(pp, '</w15:people>', [f'<w15:person w15:author="{self.author}"><w15:presenceInfo w15:providerId="None" w15:userId="{self.author}"/></w15:person>'])
            parts['word/people.xml'] = pp.encode()
        crees = [n for n in PARTS_CM if self.parts_cm[n] is None and n in parts]
        noms = self.zin.namelist()
        if crees and '[Content_Types].xml' in noms:                     # type de contenu des parts créées
            x = self.zin.read('[Content_Types].xml').decode('utf-8')
            x = ins_before(x, '</Types>', [f'<Override PartName="/{n}" ContentType="{PARTS_CM[n][2]}"/>' for n in crees if f'PartName="/{n}"' not in x])
            parts['[Content_Types].xml'] = x.encode('utf-8')
        rels = 'word/_rels/document.xml.rels'
        if crees and rels in noms:                                       # relation document -> part créée
            x = self.zin.read(rels).decode('utf-8'); k = max((int(i) for i in re.findall(r'Id="rId(\d+)"', x)), default=0); ajouts = []
            for n in crees:
                cible = n.split('/', 1)[1]
                if re.search(r'Target="(/word/)?%s"' % re.escape(cible), x) is None:
                    k += 1; ajouts.append(f'<Relationship Id="rId{k}" Type="{PARTS_CM[n][3]}" Target="{cible}"/>')
            parts[rels] = ins_before(x, '</Relationships>', ajouts).encode('utf-8')
        with zipfile.ZipFile(out, 'w') as zo:
            for info in self.zin.infolist():
                data = parts.get(info.filename, self.zin.read(info.filename))
                zi = zipfile.ZipInfo(info.filename, date_time=info.date_time); zi.compress_type = info.compress_type; zi.external_attr = info.external_attr
                zo.writestr(zi, data)
            dt = self.zin.getinfo('word/document.xml').date_time
            for n in crees:
                if n not in noms:
                    zi = zipfile.ZipInfo(n, date_time=dt); zi.compress_type = zipfile.ZIP_DEFLATED; zo.writestr(zi, parts[n])

# ===================== revision_engine_v2.py =====================

TOK = re.compile(r'\w+|\s+|[^\w\s]', re.U)
PLAIN_DROP = ('highlight', 'shd')


def est_gras(rpr):
    if rpr is None: return False
    b = rpr.find(q('b'))
    return b is not None and b.get(q('val')) not in ('0', 'false')


class Doc2(Doc):
    def nettoyer_rpr(self, rp):
        if rp is None: return None
        rp = copy.deepcopy(rp)
        had_hl = rp.find(q('highlight')) is not None
        for t in PLAIN_DROP:
            for x in rp.findall(q(t)): rp.remove(x)
        if had_hl:
            for x in rp.findall(q('color')): rp.remove(x)
        for x in rp.findall(q('ins')) + rp.findall(q('del')): rp.remove(x)
        return rp

    def replace_span(self, pid, s, e, nouveau):
        p = self.P(pid)
        if s == e and not nouveau: return 'rien'
        self.boundary(p, s); self.boundary(p, e)
        lay = self.layout(p)
        inside = [r for r, a, b in lay if a >= s and b <= e and b > a]
        prev = [r for r, a, b in lay if b == s and b > a]
        nxt = [r for r, a, b in lay if a == e and b > a]
        if inside:
            nongras = [r for r in inside if not est_gras(r.find(q('rPr')))]
            pool = nongras if nongras else inside
            src = max(pool, key=lambda r: sum(len(t) for _, t in self.pieces(r)))
        else:
            cands = [x for x in (prev[-1] if prev else None, nxt[0] if nxt else None) if x is not None]
            if len(cands) == 2 and est_gras(cands[0].find(q('rPr'))) and not est_gras(cands[1].find(q('rPr'))):
                src = cands[1]
            else:
                src = cands[0] if cands else (lay[0][0] if lay else None)
        rpr = self.nettoyer_rpr(self.base_rpr(src)) if src is not None else None
        anchor = inside[-1] if inside else None
        for r in inside: self.delete_run(r)
        if not nouveau: return 'ok'
        newrun = self.text_run(nouveau, rpr)
        # point d'insertion : après le dernier run supprimé (ou son w:del), sinon après le run précédent, sinon avant le suivant
        def place_after(t):
            par = t.getparent()
            if par is not None and ln(par) == 'ins' and par.get(q('author')) == self.author:
                t.addnext(newrun); return True
            tgt = par if par is not None and ln(par) in ('del', 'ins') else t
            ins = self.track('ins'); ins.append(newrun); tgt.addnext(ins); return True
        def place_before(t):
            par = t.getparent()
            if par is not None and ln(par) == 'ins' and par.get(q('author')) == self.author:
                t.addprevious(newrun); return True
            tgt = par if par is not None and ln(par) in ('del', 'ins') else t
            ins = self.track('ins'); ins.append(newrun); tgt.addprevious(ins); return True
        if anchor is not None and anchor.getparent() is not None:
            return 'ok' if place_after(anchor) else 'ko'
        # notre propre insertion supprimée : chercher un voisin encore présent
        before = [r for r, a, b in lay if b <= s and r.getparent() is not None]
        after = [r for r, a, b in lay if a >= e and r.getparent() is not None]
        if before: place_after(before[-1]); return 'ok'
        if after: place_before(after[0]); return 'ok'
        ppr = p.find(q('pPr')); ins = self.track('ins'); ins.append(newrun)
        (ppr.addnext(ins) if ppr is not None else p.insert(0, ins)); return 'ok'

    @staticmethod
    def ops_diff(a, b):
        """Opérations (s, e, nouveau) sur a pour obtenir b, au niveau des mots, fusionnées si séparées par peu de chose."""
        ta, tb = TOK.findall(a), TOK.findall(b)
        assert ''.join(ta) == a and ''.join(tb) == b
        sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
        ops = sm.get_opcodes()
        # positions en caractères
        pa = [0]
        for t in ta: pa.append(pa[-1] + len(t))
        pb = [0]
        for t in tb: pb.append(pb[-1] + len(t))
        chg = []
        for tag, i1, i2, j1, j2 in ops:
            if tag == 'equal': continue
            chg.append([i1, i2, j1, j2])
        # fusion des changements séparés par un segment égal court (≤ 2 jetons non mots, ou 1 mot court)
        fus = []
        for c in chg:
            if fus:
                i1p, i2p, j1p, j2p = fus[-1]
                gap = ta[i2p:c[0]]
                petit = (len(gap) <= 2 and not any(re.match(r'\w{4,}', g) for g in gap)) or (len(gap) <= 3 and sum(1 for g in gap if re.match(r'\w', g)) <= 1 and all(len(g) <= 3 for g in gap))
                if petit:
                    fus[-1] = [i1p, c[1], j1p, c[3]]; continue
            fus.append(list(c))
        return [(pa[i1], pa[i2], ''.join(tb[j1:j2])) for i1, i2, j1, j2 in fus]

    def appliquer_texte(self, pid, nouveau):
        cur = self.text(pid)
        if cur == nouveau: return 0
        ops = self.ops_diff(cur, nouveau)
        for s, e, nv in sorted(ops, key=lambda o: -o[0]):
            self.replace_span(pid, s, e, nv)
        got = self.text(pid)
        if got != nouveau:
            raise AssertionError(f'appliquer_texte {pid} : écart\nattendu {nouveau!r}\nobtenu  {got!r}')
        return len(ops)

    # ---- tableaux
    def tr_of(self, pid):
        return next(self.P(pid).iterancestors(q('tr')))

    def supprimer_lignes(self, trs):
        for tr in trs:
            trpr = tr.find(q('trPr'))
            if trpr is None:
                trpr = self.mk('trPr')
                tblprex = tr.find(q('tblPrEx'))
                (tblprex.addnext(trpr) if tblprex is not None else tr.insert(0, trpr))
            trpr.append(self.track('del'))
            for p in tr.iter(q('p')):
                for r in self.runs_of(p): self.delete_run(r)
        self.reindex()

    def inserer_ligne_apres(self, tr_modele, textes):
        tr = copy.deepcopy(tr_modele)
        # retirer marques, commentaires et signets copiés
        for x in list(tr.iter()):
            if ln(x) in ('commentRangeStart', 'commentRangeEnd', 'bookmarkStart', 'bookmarkEnd', 'proofErr'):
                x.getparent().remove(x)
        for r in list(tr.iter(q('r'))):
            if r.find(q('commentReference')) is not None: r.getparent().remove(r)
        trpr = tr.find(q('trPr'))
        if trpr is None:
            trpr = self.mk('trPr'); tblprex = tr.find(q('tblPrEx'))
            (tblprex.addnext(trpr) if tblprex is not None else tr.insert(0, trpr))
        for x in trpr.findall(q('ins')) + trpr.findall(q('del')): trpr.remove(x)
        trpr.append(self.track('ins'))
        tcs = tr.findall(q('tc'))
        assert len(tcs) == len(textes), (len(tcs), len(textes))
        for tc, texte in zip(tcs, textes):
            ps = tc.findall(q('p'))
            p0 = ps[0]
            for extra in ps[1:]: tc.remove(extra)
            rpr = None
            for r in p0.iter(q('r')):
                if r.find(q('t')) is not None: rpr = self.nettoyer_rpr(self.base_rpr(r)); break
            for c in list(p0):
                if ln(c) != 'pPr': p0.remove(c)
            ppr = p0.find(q('pPr'))
            if ppr is None: ppr = self.mk('pPr'); p0.insert(0, ppr)
            rp = ppr.find(q('rPr'))
            if rp is None: rp = self.mk('rPr'); ppr.append(rp)
            for x in rp.findall(q('ins')) + rp.findall(q('del')): rp.remove(x)
            rp.insert(0, self.track('ins'))
            p0.set('{%s}paraId' % W14, self.newhex(self.used_para)); p0.set('{%s}textId' % W14, '77777777')
            ins = self.track('ins'); ins.append(self.text_run(texte, rpr)); p0.append(ins)
        tr_modele.addnext(tr); self.reindex()
        return [p.get('{%s}paraId' % W14) for p in tr.iter(q('p'))]

# ===================== revision_engine_v8.py =====================

MN = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
MATH = {'acc', 'bar', 'box', 'borderBox', 'd', 'eqArr', 'f', 'func', 'groupChr', 'limLow', 'limUpp', 'm', 'nary',
        'phant', 'rad', 'sPre', 'sSub', 'sSubSup', 'sSup', 'r'}
DESCENDRE_W = {'hyperlink', 'fldSimple', 'smartTag', 'customXml', 'dir', 'bdo'}
MARQUEURS = ('commentRangeStart', 'commentRangeEnd', 'bookmarkStart', 'bookmarkEnd')


def ns(e): return etree.QName(e).namespace if isinstance(e.tag, str) else None


class DocV8(Doc2):
    def __init__(self, path, author='Correction - Claude', init='CC'):
        super().__init__(path, author, init)
        self.n_move = 0
        self.deplacements = []   # journal technique des déplacements

    # ---------- utilitaires
    def top(self, pid):
        x = self.P(pid)
        while x.getparent() is not self.body: x = x.getparent()
        return x

    def bloc(self, pid1, pid2):
        a, b = self.top(pid1), self.top(pid2)
        els, x = [], a
        while True:
            els.append(x)
            if x is b: break
            x = x.getnext()
            assert x is not None, 'bloc non contigu'
        return els

    @staticmethod
    def _ref_run(x):
        return ln(x) == 'r' and ns(x) == WN and x.find(q('commentReference')) is not None

    def _enveloppable(self, x):
        if ns(x) == WN and ln(x) == 'r': return not self._ref_run(x)
        if ns(x) == MN and ln(x) in MATH: return True
        return False

    def _envelopper(self, parent, tag, convertir):
        """Regroupe les enfants « run » consécutifs de parent dans un élément de suivi ; descend dans les conteneurs."""
        groupe = []
        def fermer():
            if not groupe: return
            w = self.track(tag)
            groupe[0].addprevious(w)
            for g in groupe: w.append(g)
            if convertir:
                for t in w.iter(q('t')): t.tag = q('delText')
                for t in w.iter(q('instrText')): t.tag = q('delInstrText')
            groupe.clear()
        for x in list(parent):
            if not isinstance(x.tag, str): continue
            if self._enveloppable(x):
                groupe.append(x); continue
            fermer()
            if ns(x) == WN and ln(x) in DESCENDRE_W: self._envelopper(x, tag, convertir)
            elif ns(x) == WN and ln(x) == 'sdt':
                c = x.find(q('sdtContent'))
                if c is not None: self._envelopper(c, tag, convertir)
            elif ns(x) == MN and ln(x) in ('oMathPara', 'oMath'): self._envelopper(x, tag, convertir)
        fermer()

    def _marque_par(self, p, tag):
        ppr = p.find(q('pPr'))
        if ppr is None: ppr = self.mk('pPr'); p.insert(0, ppr)
        rp = ppr.find(q('rPr'))
        if rp is None:
            rp = self.mk('rPr')
            fin = [c for c in ppr if ln(c) in ('sectPr', 'pPrChange')]
            (fin[0].addprevious(rp) if fin else ppr.append(rp))
        for k in ('ins', 'del', 'moveFrom', 'moveTo'):
            for m in rp.findall(q(k)): rp.remove(m)
        rp.insert(0, self.track(tag))

    def _apres_ppr(self, p, e):
        ppr = p.find(q('pPr'))
        (ppr.addnext(e) if ppr is not None else p.insert(0, e))

    def _nouveaux_ids(self, e):
        for p in ([e] if ln(e) == 'p' else []) + list(e.iter(q('p'))):
            if p.get('{%s}paraId' % W14):
                p.set('{%s}paraId' % W14, self.newhex(self.used_para)); p.set('{%s}textId' % W14, '77777777')

    def _ids_complets(self, els):
        """Commentaires et signets dont tous les marqueurs sont dans els (ils partiront avec le bloc)."""
        vus = {}
        for e in els:
            for x in e.iter():
                if not isinstance(x.tag, str): continue
                if ln(x) in MARQUEURS: vus.setdefault((ln(x).replace('Start', '').replace('End', ''), x.get(q('id'))), set()).add(ln(x))
                elif ln(x) == 'commentReference': vus.setdefault(('commentRange', x.get(q('id'))), set()).add('ref')
        ok = set()
        for (k, i), s in vus.items():
            if k == 'commentRange' and {'commentRangeStart', 'commentRangeEnd', 'ref'} <= s: ok.add((k, i))
            if k == 'bookmark' and {'bookmarkStart', 'bookmarkEnd'} <= s: ok.add((k, i))
        return ok

    @staticmethod
    def _cle(x):
        if ln(x) in MARQUEURS: return (ln(x).replace('Start', '').replace('End', ''), x.get(q('id')))
        if ln(x) == 'r' and x.find(q('commentReference')) is not None: return ('commentRange', x.find(q('commentReference')).get(q('id')))
        return None

    def _retirer_marqueurs(self, e, garder):
        """garder=True : retire les marqueurs NON complets ; garder=False : retire les marqueurs complets."""
        for x in list(e.iter()):
            if not isinstance(x.tag, str): continue
            k = self._cle(x)
            if k is None: continue
            if (k in self._complets) != garder: x.getparent().remove(x)

    # ---------- déplacement suivi
    def move_block(self, pid1, pid2, pid_dest, ou='apres'):
        els = self.bloc(pid1, pid2)
        for e in els:
            for p in ([e] if ln(e) == 'p' else []) + list(e.iter(q('p'))):
                ppr = p.find(q('pPr'))
                assert ppr is None or ppr.find(q('sectPr')) is None, 'saut de section dans le bloc déplacé'
        dest = self.top(pid_dest)
        assert all(dest is not e for e in els), 'destination dans le bloc'
        self._complets = self._ids_complets(els)
        copies = [copy.deepcopy(e) for e in els]
        src_ids = [p.get('{%s}paraId' % W14) for e in els for p in ([e] if ln(e) == 'p' else []) + list(e.iter(q('p')))]
        for c in copies:
            self._retirer_marqueurs(c, garder=True); self._nouveaux_ids(c)
        for e in els: self._retirer_marqueurs(e, garder=False)
        dst_ids = [p.get('{%s}paraId' % W14) for c in copies for p in ([c] if ln(c) == 'p' else []) + list(c.iter(q('p')))]
        # groupes de paragraphes consécutifs = une plage de déplacement chacun (même nom à la source et à la destination)
        ngrp, i = 0, 0
        while i < len(els):
            if ln(els[i]) == 'tbl': i += 1; continue
            while i + 1 < len(els) and ln(els[i + 1]) == 'p': i += 1
            ngrp += 1; i += 1
        noms = ['move%05d' % (self.n_move + k + 1) for k in range(ngrp)]
        self.n_move += ngrp
        def traiter(liste, cote):
            tag_p = 'moveFrom' if cote == 'src' else 'moveTo'
            conv = cote == 'src'
            i, g = 0, 0
            while i < len(liste):
                e = liste[i]
                if ln(e) == 'tbl':
                    for tr in e.iter(q('tr')):
                        trpr = tr.find(q('trPr'))
                        if trpr is None:
                            trpr = self.mk('trPr'); tpe = tr.find(q('tblPrEx'))
                            (tpe.addnext(trpr) if tpe is not None else tr.insert(0, trpr))
                        trpr.append(self.track('del' if cote == 'src' else 'ins'))
                    for p in e.iter(q('p')):
                        self._marque_par(p, 'del' if cote == 'src' else 'ins')
                        self._envelopper(p, 'del' if cote == 'src' else 'ins', conv)
                    i += 1; continue
                j = i
                while j + 1 < len(liste) and ln(liste[j + 1]) == 'p': j += 1
                grp = liste[i:j + 1]
                nom = noms[g]; g += 1
                rid = self.rev_id()
                for p in grp:
                    self._marque_par(p, tag_p)
                    self._envelopper(p, tag_p, conv)
                deb = self.mk(tag_p + 'RangeStart', id=rid, author=self.author, date=self.now, name=nom)
                fin = self.mk(tag_p + 'RangeEnd', id=rid)
                self._apres_ppr(grp[0], deb); grp[-1].append(fin)
                i = j + 1
        traiter(els, 'src'); traiter(copies, 'dst')
        if ou == 'apres':
            for c in reversed(copies): dest.addnext(c)
        else:
            for c in copies: dest.addprevious(c)
        self.reindex()
        m = dict(zip(src_ids, dst_ids))
        self.deplacements.append(dict(de=src_ids, vers=dst_ids, dest=pid_dest, ou=ou))
        return m

    # ---------- divers
    def remplir(self, pid, texte, pid_rpr):
        p = self.P(pid)
        assert self.ptext(p) == '', 'cellule non vide'
        rpr = self.nettoyer_rpr(self.first_text_rpr(self.P(pid_rpr)))
        ins = self.track('ins'); ins.append(self.text_run(texte, rpr)); p.append(ins)

# ===================== revision_engine_reeval_v1.py =====================

AUTEUR = 'Reevaluation - Claude'
REV_TAGS = ('ins', 'del', 'moveFrom', 'moveTo')
CONTENEURS_STOP = ('p', 'hyperlink', 'smartTag', 'sdtContent', 'fldSimple', 'customXml', 'dir', 'bdo')


class DocR(DocV8):
    def __init__(self, path, author=AUTEUR, init='RC'):
        super().__init__(path, author, init)

    # ---------- scission d'un conteneur de révision
    def _clone_vide(self, e):
        c = etree.Element(e.tag)
        for k, v in e.attrib.items(): c.set(k, v)
        if c.get(q('id')) is not None: c.set(q('id'), self.rev_id())
        return c

    def _scinder_apres(self, cont, enfant):
        """Les frères qui suivent enfant dans cont passent dans un clone de cont placé juste après cont."""
        suite = []
        x = enfant.getnext()
        while x is not None:
            suite.append(x); x = x.getnext()
        if not suite: return
        c = self._clone_vide(cont)
        for s in suite: c.append(s)
        cont.addnext(c)

    def _scinder_avant(self, cont, enfant):
        avant = []
        x = enfant.getprevious()
        while x is not None:
            avant.insert(0, x); x = x.getprevious()
        if not avant: return
        c = self._clone_vide(cont)
        for s in avant: c.append(s)
        cont.addprevious(c)

    def _point_insertion(self, noeud, cote):
        """Remonte de noeud jusqu'à un niveau hors de tout conteneur de révision, en scindant les conteneurs.
        Retourne (cible, mode) : mode 'dans_notre_ins' (ajouter le run à côté de cible) ou 'libre' (ajouter un w:ins)."""
        cur = noeud
        while True:
            par = cur.getparent()
            if par is None or ln(par) in CONTENEURS_STOP: return cur, 'libre'
            if ln(par) == 'ins' and par.get(q('author')) == self.author: return cur, 'dans_notre_ins'
            if ln(par) in REV_TAGS:
                (self._scinder_apres if cote == 'apres' else self._scinder_avant)(par, cur)
                cur = par; continue
            return cur, 'libre'

    def _placer(self, newrun, ref, cote):
        cible, mode = self._point_insertion(ref, cote)
        if mode == 'dans_notre_ins':
            (cible.addnext if cote == 'apres' else cible.addprevious)(newrun); return
        ins = self.track('ins'); ins.append(newrun)
        (cible.addnext if cote == 'apres' else cible.addprevious)(ins)

    # ---------- remplacement sur la vue « tout accepté »
    def replace_span(self, pid, s, e, nouveau):
        p = self.P(pid)
        if s == e and not nouveau: return 'rien'
        self.boundary(p, s); self.boundary(p, e)
        lay = self.layout(p)
        inside = [r for r, a, b in lay if a >= s and b <= e and b > a]
        prev = [r for r, a, b in lay if b == s and b > a]
        nxt = [r for r, a, b in lay if a == e and b > a]
        if inside:
            nongras = [r for r in inside if not est_gras(r.find(q('rPr')))]
            pool = nongras if nongras else inside
            src = max(pool, key=lambda r: sum(len(t) for _, t in self.pieces(r)))
        else:
            cands = [x for x in (prev[-1] if prev else None, nxt[0] if nxt else None) if x is not None]
            if len(cands) == 2 and est_gras(cands[0].find(q('rPr'))) and not est_gras(cands[1].find(q('rPr'))):
                src = cands[1]
            else:
                src = cands[0] if cands else (lay[0][0] if lay else None)
        rpr = self.nettoyer_rpr(self.base_rpr(src)) if src is not None else None
        for r in inside: self.delete_run(r)
        if not nouveau: return 'ok'
        newrun = self.text_run(nouveau, rpr)
        # ancre : dernier run supprimé encore présent (dans notre w:del), sinon voisin présent
        vivants_in = [r for r in inside if r.getparent() is not None]
        if vivants_in:
            self._placer(newrun, vivants_in[-1], 'apres'); return 'ok'
        before = [r for r, a, b in lay if b <= s and r.getparent() is not None]
        after = [r for r, a, b in lay if a >= e and r.getparent() is not None]
        if before: self._placer(newrun, before[-1], 'apres'); return 'ok'
        if after: self._placer(newrun, after[0], 'avant'); return 'ok'
        ppr = p.find(q('pPr')); ins = self.track('ins'); ins.append(newrun)
        (ppr.addnext(ins) if ppr is not None else p.insert(0, ins)); return 'ok'

    def delete_run(self, r):
        oi = self.our_ins(r)
        if oi is not None:
            self._rescue(r); r.getparent().remove(r)
            if len(oi) == 0: oi.getparent().remove(oi)
            return
        for t in r.iter(q('t')): t.tag = q('delText')
        for t in r.iter(q('instrText')): t.tag = q('delInstrText')
        d = self.track('del'); r.addprevious(d); d.append(r)

    # ---------- marques de paragraphe
    def _rpr_marque(self, p):
        ppr = p.find(q('pPr'))
        if ppr is None: ppr = self.mk('pPr'); p.insert(0, ppr)
        rp = ppr.find(q('rPr'))
        if rp is None:
            rp = self.mk('rPr')
            fin = [c for c in ppr if ln(c) in ('sectPr', 'pPrChange')]
            (fin[0].addprevious(rp) if fin else ppr.append(rp))
        return ppr, rp

    def marque_supprimee(self, p):
        ppr = p.find(q('pPr'))
        rp = ppr.find(q('rPr')) if ppr is not None else None
        return rp is not None and rp.find(q('del')) is not None

    def _marquer_del(self, p):
        """Ajoute notre w:del à la marque de paragraphe, sans toucher aux marques des autres auteurs."""
        ppr, rp = self._rpr_marque(p)
        assert ppr.find(q('sectPr')) is None, 'marque portant un saut de section'
        if rp.find(q('del')) is not None: return 'deja'
        ins = rp.find(q('ins'))
        d = self.track('del')
        (ins.addnext(d) if ins is not None else rp.insert(0, d))
        return 'ok'

    def notre_paragraphe(self, p):
        ppr = p.find(q('pPr')); rp = ppr.find(q('rPr')) if ppr is not None else None
        m = rp.find(q('ins')) if rp is not None else None
        return m is not None and m.get(q('author')) == self.author

    def delete_paragraph(self, pid):
        p = self.P(pid)
        if self.notre_paragraphe(p):
            self._rescue_para(p); p.getparent().remove(p); self.reindex(); return 'retire'
        for r in self.runs_of(p): self.delete_run(r)
        dern_cellule = ln(p.getparent()) == 'tc' and p.getparent().findall(q('p'))[-1] is p
        if not dern_cellule: self._marquer_del(p)
        self.reindex(); return 'ok'

    # ---------- lignes de tableau
    def supprimer_ligne_multi(self, pid):
        tr = self.tr_of(pid)
        trpr = tr.find(q('trPr'))
        if trpr is None:
            trpr = self.mk('trPr'); tpe = tr.find(q('tblPrEx'))
            (tpe.addnext(trpr) if tpe is not None else tr.insert(0, trpr))
        if trpr.find(q('del')) is not None: raise ValueError('ligne déjà supprimée par un autre auteur')
        ins = trpr.find(q('ins')); d = self.track('del')
        (ins.addnext(d) if ins is not None else trpr.append(d))
        textes = []
        for p in tr.iter(q('p')):
            textes.append(self.ptext(p))
            for r in self.runs_of(p): self.delete_run(r)
            if not (ln(p.getparent()) == 'tc' and p.getparent().findall(q('p'))[-1] is p): self._marquer_del(p)
        self.reindex()
        return textes
