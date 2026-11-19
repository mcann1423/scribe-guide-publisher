"""Local, static Scribe guide publisher. Never communicates with a web server."""
from __future__ import annotations
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import urllib.parse
import urllib.request

DEFAULT_EXPORTS = Path(r'H:\HTML\Exports')
DEFAULT_OUTPUT = Path(r'H:\HTML\luna\tech-services\help-guides')
STATE_NAME = '.scribe-publisher-state.json'
ALLOWED_TAGS = {'p','div','span','h1','h2','h3','h4','h5','h6','b','strong','i','em','ul','ol','li','br','blockquote','pre','code','table','thead','tbody','tr','td','th','hr','a','img'}
VOID = {'br','hr','img'}
DROP = {'script','style','iframe','object','embed','form','svg','math','video','audio','button','input','textarea','select','template','noscript'}
RESERVED = {'index','guide-style','con','prn','aux','nul',*(f'com{i}' for i in range(1,10)),*(f'lpt{i}' for i in range(1,10))}
MAX_IMAGE = 25 * 1024 * 1024
IMAGE_HOSTS = {'colony-recorder.s3.us-west-1.amazonaws.com'}

CSS = '''*{box-sizing:border-box}body{font:17px/1.6 system-ui,sans-serif;color:#17263b;background:#f2f5f9;margin:0}main{max-width:920px;margin:2rem auto;padding:2rem;background:white;border-radius:12px;box-shadow:0 4px 24px #17335418}h1,h2,h3{line-height:1.2;color:#12345a}h1{font-size:2rem}a{color:#075b9d}img{display:block;max-width:100%;height:auto;border:1px solid #d4dee8;border-radius:6px}p.scribe-step-text{font-weight:600;margin-top:2rem}p.scribe-screenshot-container{margin:1rem 0 2rem}input{font:inherit;padding:.65rem;width:100%;border:1px solid #aabbd0;border-radius:6px}li{margin:.5rem 0}nav{margin-bottom:1.5rem}@media(max-width:650px){main{margin:0;padding:1.2rem;border-radius:0}}@media print{body{background:white}main{box-shadow:none;margin:0;padding:0}nav,.search{display:none}img{break-inside:avoid}}'''

def guide_id(filename: str) -> str:
    name = Path(filename).stem
    value = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    if not value or value in RESERVED or len(value) > 100:
        raise ValueError('Filename cannot produce a safe guide name; rename the export.')
    return value

def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.scribe-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f: f.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def document(title, content):
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + html.escape(title) + '</title><link rel="stylesheet" href="guide-style.css"></head><body><main>' + content + '</main></body></html>')

def image_type(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return '.png'
    if data.startswith(b'\xff\xd8\xff'): return '.jpg'
    if data.startswith((b'GIF87a', b'GIF89a')): return '.gif'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP': return '.webp'
    raise ValueError('Unsupported image format; expected PNG, JPEG, GIF or WebP.')

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = urllib.parse.urlsplit(newurl)
        if parts.scheme != 'https' or parts.hostname not in IMAGE_HOSTS or parts.username or parts.password or parts.port not in (None, 443):
            raise ValueError('Image redirect is not to an approved Scribe image host.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def download_image(url, source_dir):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme in ('https','http'):
        # Never publish or fetch credentials provided in URLs.
        if parts.username or parts.password: raise ValueError('Image URL contains credentials.')
        if parts.scheme != 'https' or parts.hostname not in IMAGE_HOSTS or parts.port not in (None, 443):
            raise ValueError('Image URL is not on an approved Scribe image host.')
        req = urllib.request.Request(url, headers={'User-Agent':'ScribeGuidePublisher/1.0'})
        with urllib.request.build_opener(SafeRedirect()).open(req, timeout=30) as response:
            final = urllib.parse.urlsplit(response.geturl())
            if final.scheme != 'https' or final.hostname not in IMAGE_HOSTS: raise ValueError('Unsupported image redirect.')
            data = response.read(MAX_IMAGE+1)
    elif not parts.scheme and not parts.netloc:
        # Relative files must remain within export directory.
        target = (source_dir / urllib.parse.unquote(parts.path)).resolve()
        if not target.is_relative_to(source_dir.resolve()): raise ValueError('Image path escapes export folder.')
        with target.open('rb') as f: data = f.read(MAX_IMAGE+1)
    else: raise ValueError('Unsupported image source: '+url[:100])
    if len(data)>MAX_IMAGE: raise ValueError('Image exceeds 25 MB limit.')
    return data, image_type(data)

class Convert(HTMLParser):
    def __init__(self, source_dir, ident, fetch=download_image):
        super().__init__(convert_charrefs=True)
        self.source_dir, self.ident, self.fetch = source_dir, ident, fetch
        self.output=[]; self.images={}; self.skip=0; self.stack=[]; self.title=''; self.title_depth=0; self.warnings=[]
    def handle_starttag(self, tag, attrs):
        tag=tag.lower(); attrs=dict(attrs)
        if self.skip:
            if tag not in VOID and tag not in {'input','embed'}: self.skip+=1
            return
        classes=attrs.get('class','').split()
        if tag in DROP or any(c in ('scribe-author','scribe-footer') for c in classes):
            if tag not in VOID and tag not in {'input','embed'}: self.skip=1
            return
        if tag not in ALLOWED_TAGS: return
        if tag=='h1' and not self.title: self.title_depth=1
        elif self.title_depth and tag not in VOID: self.title_depth+=1
        clean=[]
        if classes:
            safe=' '.join(c for c in classes if re.fullmatch(r'[A-Za-z0-9_-]+',c))
            if safe: clean.append(('class',safe))
        if tag=='a':
            href=attrs.get('href',''); url=urllib.parse.urlsplit(href)
            if url.scheme in ('http','https','mailto') and not url.username and not url.password: clean.append(('href',href))
            elif href.startswith('#'): clean.append(('href',href))
            elif href: self.warnings.append('Removed non-web or relative link: '+href[:100])
        if tag=='img':
            src=attrs.get('src')
            if not src: raise ValueError('An image has no source.')
            data, ext=self.fetch(src,self.source_dir)
            name=f'image-{len(self.images)+1:03d}'+ext
            self.images[name]=data
            clean.extend([('src',f'images/{self.ident}/{name}'),('alt',attrs.get('alt',''))])
            if not attrs.get('alt'): self.warnings.append('Screenshot has no alt text; review accessibility.')
        self.output.append('<'+tag+''.join(' '+k+'="'+html.escape(v,quote=True)+'"' for k,v in clean)+'>')
        if tag not in VOID: self.stack.append(tag)
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID: self.handle_endtag(tag)
    def handle_endtag(self,tag):
        tag=tag.lower()
        if self.skip:
            if tag not in VOID and tag not in {'input','embed'}: self.skip-=1
            return
        if self.title_depth: self.title_depth-=1
        if tag in self.stack:
            while self.stack:
                last=self.stack.pop(); self.output.append('</'+last+'>')
                if last==tag: break
    def handle_data(self,data):
        if self.skip: return
        if self.title_depth: self.title+=data
        self.output.append(html.escape(data))
    def finish(self):
        while self.stack: self.output.append('</'+self.stack.pop()+'>')
        return ''.join(self.output)

class Publisher:
    def __init__(self,exports=DEFAULT_EXPORTS,output=DEFAULT_OUTPUT,state=None,fetch=download_image):
        self.exports=Path(exports); self.output=Path(output); self.state_path=Path(state) if state else self.exports/STATE_NAME; self.fetch=fetch
        if self.output.exists() and self.output.is_symlink(): raise ValueError('Output folder cannot be a symbolic link.')
        if (self.output/'images').is_symlink(): raise ValueError('Images folder cannot be a symbolic link.')
        if self.output.resolve()==self.exports.resolve() or self.output.resolve().is_relative_to(self.exports.resolve()) or self.exports.resolve().is_relative_to(self.output.resolve()): raise ValueError('Export and output directories must not overlap.')
        self.state=self._load()
        if self.state.get('output') and Path(self.state['output']).resolve() != self.output.resolve(): raise ValueError('This export folder is already associated with a different output folder. Use another export folder or restore the intended output path.')
    def _load(self):
        if not self.state_path.exists(): return {'version':1,'output':str(self.output.resolve()),'guides':{},'removals':[], 'owned': False}
        data=json.loads(self.state_path.read_text(encoding='utf-8'))
        if data.get('version')!=1 or not isinstance(data.get('guides'),dict) or not isinstance(data.get('removals'),list): raise ValueError('Publisher state is invalid; restore its backup.')
        # The state is only a record, never authority to delete arbitrary paths.
        for ident, rec in data['guides'].items():
            if guide_id(ident+'.html')!=ident or not isinstance(rec,dict): raise ValueError('Invalid guide state.')
        return data
    def _save(self): atomic_write(self.state_path, json.dumps(self.state,ensure_ascii=False,indent=2).encode('utf-8'))
    def _check_links(self, ident=None):
        paths = [self.output, self.output/'images', self.state_path]
        paths += [self.output/name for name in ('index.html','guide-style.css','guide-search.js')]
        if ident: paths += [self.output/(ident+'.html'), self.output/'images'/ident]
        if any(p.is_symlink() for p in paths): raise ValueError('A managed path is a symbolic link; refusing to modify it.')
    def _snapshot_index(self):
        return {name:(self.output/name).read_bytes() if (self.output/name).exists() else None for name in ('index.html','guide-style.css','guide-search.js')}
    def _restore_index(self, snapshot):
        for name, data in snapshot.items():
            path=self.output/name
            if data is None:
                if path.exists(): path.unlink()
            else: atomic_write(path,data)
    def exports_list(self):
        return sorted((p for p in self.exports.iterdir() if p.is_file() and p.suffix.lower() in ('.html','.htm')),key=lambda p:p.name.casefold()) if self.exports.is_dir() else []
    def save_pasted_export(self, filename, content):
        """Save pasted HTML as an original export, without touching published output."""
        name = Path(filename).name
        if name != filename or not name or Path(name).suffix.lower() not in ('.html', '.htm'):
            raise ValueError('Export filename must be a simple name ending in .html or .htm.')
        guide_id(name)
        if not isinstance(content, str) or not content.strip():
            raise ValueError('Paste the exported HTML before publishing.')
        self.exports.mkdir(parents=True, exist_ok=True)
        target = self.exports / name
        if target.is_symlink():
            raise ValueError('Export filename is a symbolic link; refusing to replace it.')
        atomic_write(target, content.encode('utf-8'))
        return target
    def _check_owned(self, ident, source):
        rec=self.state['guides'].get(ident)
        if rec and rec['source'].casefold()!=source.name.casefold(): raise ValueError('Filename collides with published guide '+rec['source'])
        if not rec and ((self.output/(ident+'.html')).exists() or (self.output/'images'/ident).exists()): raise ValueError('Output already exists and is not managed by this tool; refusing to overwrite.')
        for other in self.exports_list():
            if other.name.casefold()!=source.name.casefold():
                try: same=guide_id(other.name)==ident
                except ValueError: same=False
                if same: raise ValueError('Filename collides with export '+other.name+'; rename one.')
    def claim_output(self):
        self._check_links()
        if self.state.get('owned'): return
        for name in ('index.html','guide-style.css','guide-search.js'):
            if (self.output/name).exists(): raise ValueError('Cannot take ownership: '+name+' already exists in the output folder. Choose a dedicated empty folder.')
        self.state['owned']=True; self._save()
    def publish(self, source):
        source=Path(source)
        if source.parent.resolve()!=self.exports.resolve() or not source.is_file() or source.suffix.lower() not in ('.htm','.html'): raise ValueError('Select an HTML file directly in the export folder.')
        ident=guide_id(source.name); self._check_links(ident); self._check_owned(ident,source)
        self.claim_output()
        parser=Convert(source.parent,ident,self.fetch)
        parser.feed(source.read_text(encoding='utf-8-sig')); parser.close(); content=parser.finish()
        title=parser.title.strip() or source.stem
        page=document(title,'<nav><a href="index.html">← All help guides</a></nav>'+content)
        # Fully stage guide and downloads before changing an existing publication.
        self.output.mkdir(parents=True,exist_ok=True); (self.output/'images').mkdir(exist_ok=True)
        oldrec=self.state['guides'].get(ident); pagepath=self.output/(ident+'.html'); imgpath=self.output/'images'/ident
        if oldrec and imgpath.exists():
            expected=set(oldrec.get('images',[]))
            if imgpath.is_symlink() or any(p.name not in expected or not p.is_file() or p.is_symlink() for p in imgpath.iterdir()): raise ValueError('Image folder contains unmanaged files; refusing to replace it.')
        with tempfile.TemporaryDirectory(prefix='.scribe-stage-',dir=self.output) as temp:
            temp=Path(temp); staged=temp/'new'; staged.mkdir()
            for name,data in parser.images.items(): (staged/name).write_bytes(data)
            oldimages=temp/'old'; oldpage=pagepath.read_bytes() if pagepath.exists() else None
            oldstate=json.loads(json.dumps(self.state)); oldindex=self._snapshot_index()
            try:
                if imgpath.exists(): os.replace(imgpath,oldimages)
                os.replace(staged,imgpath)
                atomic_write(pagepath,page.encode('utf-8'))
                self.state['guides'][ident]={'source':source.name,'title':title,'images':list(parser.images)}
                self._save(); self.render_index()
            except Exception:
                if imgpath.exists(): shutil.rmtree(imgpath)
                if oldimages.exists(): os.replace(oldimages,imgpath)
                if oldpage is not None: atomic_write(pagepath,oldpage)
                elif pagepath.exists(): pagepath.unlink()
                self.state=oldstate; self._save(); self._restore_index(oldindex)
                raise
        return parser.warnings
    def unpublish(self,ident):
        if ident not in self.state['guides']: raise ValueError('Guide is not published.')
        self._check_links(ident)
        # Refuse to delete files that were not generated by this tool.
        page=self.output/(ident+'.html'); images=self.output/'images'/ident
        if images.is_symlink(): raise ValueError('Refusing to remove a linked image folder.')
        expected=set(self.state['guides'][ident].get('images', []))
        if images.exists() and any(p.name not in expected or not p.is_file() or p.is_symlink() for p in images.iterdir()): raise ValueError('Image folder contains unmanaged files; refusing to remove it.')
        # Stage removal; restore the previous site and state on a normal failure.
        oldstate=json.loads(json.dumps(self.state)); oldindex=self._snapshot_index()
        self.output.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.scribe-stage-',dir=self.output) as tmp:
            tmp=Path(tmp); savedpage=tmp/'page'; savedimages=tmp/'images'
            try:
                # Save notice first so an interrupted run never silently loses it.
                for path in [ident+'.html','images/'+ident+'/']:
                    if path not in self.state['removals']: self.state['removals'].append(path)
                self._save()
                if page.exists(): os.replace(page,savedpage)
                if images.exists(): os.replace(images,savedimages)
                del self.state['guides'][ident]; self._save(); self.render_index()
            except Exception:
                if savedpage.exists(): os.replace(savedpage,page)
                if savedimages.exists(): os.replace(savedimages,images)
                self.state=oldstate; self._save(); self._restore_index(oldindex)
                raise
    def render_index(self):
        self.output.mkdir(parents=True,exist_ok=True)
        # index and CSS are generated only after explicit first-run ownership confirmation.
        guides=sorted(self.state['guides'].items(),key=lambda item:item[1]['title'].casefold())
        links=''.join('<li><a href="'+html.escape(i,quote=True)+'.html">'+html.escape(r['title'])+'</a></li>' for i,r in guides)
        content='<h1>Help Guides</h1><p>Browse our step-by-step guides.</p><label class="search" for="search">Search guides</label><input class="search" id="search" type="search" placeholder="Search by title"><ul id="guides">'+links+'</ul><p id="empty" hidden>No matching guides.</p><script src="guide-search.js" defer></script>'
        for name,data in [('index.html',document('Help Guides',content)),('guide-style.css',CSS),('guide-search.js',"const q=document.getElementById('search'), rows=[...document.querySelectorAll('#guides li')], empty=document.getElementById('empty');q.addEventListener('input',()=>{let n=0;rows.forEach(r=>{r.hidden=!r.textContent.toLowerCase().includes(q.value.toLowerCase());if(!r.hidden)n++});empty.hidden=n!==0});")]:
            atomic_write(self.output/name,data.encode('utf-8'))
