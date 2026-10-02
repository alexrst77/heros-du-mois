from pathlib import Path
import json, re, shutil, argparse
from xml.sax.saxutils import escape
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
import fitz
parser=argparse.ArgumentParser()
parser.add_argument('manifest',type=Path)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
ROOT=Path(__file__).resolve().parent
manifest=args.manifest.resolve()
book=json.loads(manifest.read_text(encoding='utf-8'))
work=args.output.resolve().parent/'render-work'
(work/'assets').mkdir(parents=True,exist_ok=True)
def asset(rel):
 p=(manifest.parent/rel).resolve()
 if not p.is_relative_to(manifest.parent):raise ValueError('Asset outside manifest folder')
 if not p.is_file():raise ValueError(f'Missing asset: {rel}')
 return str(p)
if len(book['spreads'])!=9 or len(book['pages'])!=18:raise ValueError('Expected 9 spreads and 18 story pages')
S=595.2756
pdfmetrics.registerFont(TTFont('Story',str(ROOT/'fonts/DejaVuSerif.ttf')))
pdfmetrics.registerFont(TTFont('StoryBold',str(ROOT/'fonts/DejaVuSerif-Bold.ttf')))
texts=[p['text'] for p in book['pages']]; paths=[asset(p) for p in book['spreads']]
for p in paths:
 im=Image.open(p)
 if abs(im.width/im.height-2)>0.02:raise ValueError('Spread must be 2:1; do not silently crop characters')
def jpeg(source, name):
 dest=work/'assets'/name
 if Image.open(source).format=='JPEG':shutil.copyfile(source,dest)
 else:Image.open(source).convert('RGB').save(dest,quality=95,subsampling=0,optimize=True)
 return str(dest)
paths=[jpeg(p,f'spread-{i+1}.jpg') for i,p in enumerate(paths)]
cover=jpeg(asset(book['cover']),'cover.jpg')
out=args.output.resolve();out.parent.mkdir(parents=True,exist_ok=True)
c=canvas.Canvas(str(out),pagesize=(S,S),pageCompression=1)
c.setTitle(book['title']);c.setAuthor(book['collection']);c.setSubject('Une aventure illustrée à lire ensemble • 4–7 ans')
# Cover and final back cover are included in the 20-page count.
c.drawImage(cover,0,0,S,S);c.showPage()
for idx,txt in enumerate(texts):
 spread=idx//2;half=idx%2
 p=paths[spread];im=Image.open(p);w,h=im.size
 scale=max(2*S/w,S/h);dw,dh=w*scale,h*scale
 c.drawImage(p,(2*S-dw)/2-half*S,(S-dh)/2,dw,dh)
 night=True
 color=book['pages'][idx]['veil']
 ink=book['pages'][idx]['ink']
 # Continuous, smoothly fading local veil; no rectangular text panel.
 veil=Image.new('RGBA',(2,900))
 rgb=tuple(int(color[k:k+2],16) for k in (1,3,5))
 for row in range(900):
  y=225*(1-row/899)
  t=max(0,min(1,(y-135)/90))
  alpha=.96*(1-t*t*(3-2*t))
  for col in range(2):veil.putpixel((col,row),rgb+(round(alpha*255),))
 c.drawImage(ImageReader(veil),0,0,S,225,mask='auto')
 c.setFillAlpha(1)
 style=ParagraphStyle('body',fontName='Story',fontSize=14.8,leading=21,textColor=HexColor(ink))
 para=Paragraph(escape(txt),style);pw,ph=para.wrap(S-90,160)
 if ph>147:raise ValueError(f'Text overflow on page {idx+2}; shorten text, do not shrink type')
 para.drawOn(c,45,43)
 c.setFillColor(HexColor(ink));c.setFont('Story',8);c.drawCentredString(S/2,19,str(idx+2))
 c.showPage()
# Back cover, image and quiet integrated synopsis.
p=paths[7];im=Image.open(p);w,h=im.size;scale=S/h
c.drawImage(p,S-w*scale,0,w*scale,S)
c.setFillColor(HexColor(book['backColor']));c.setFillAlpha(.84);c.rect(0,0,S,S,fill=1,stroke=0);c.setFillAlpha(1)
c.setFillColor(HexColor('#EAD49D'));c.setFont('Story',12);c.drawCentredString(S/2,520,book['collection'].upper())
style=ParagraphStyle('backtitle',fontName='StoryBold',fontSize=29,leading=38,textColor=HexColor('#FFF4DC'),alignment=1)
p=Paragraph('<br/>'.join(escape(t) for t in book['backTitle']),style);_,h=p.wrap(S-100,140);p.drawOn(c,50,370)
style=ParagraphStyle('back',fontName='Story',fontSize=16,leading=25,textColor=HexColor('#FFF4DC'),alignment=1)
p=Paragraph('<br/><br/>'.join(escape(t) for t in book['backText']),style);_,h=p.wrap(S-130,240);p.drawOn(c,65,325-h)
c.setStrokeColor(HexColor('#DCC38C'));c.setLineWidth(.7);c.line(245,112,350,112)
c.setFont('Story',11);c.drawCentredString(S/2,85,'Une aventure à lire ensemble • '+book['ageLabel'])
c.setFont('Story',9);c.drawCentredString(S/2,62,book['title'])
c.showPage();c.save()
doc=fitz.open(out);assert len(doc)==20
for i,p in enumerate(doc):
 if 0<i<19:assert len(p.get_text())>70
 pix=p.get_pixmap(matrix=fitz.Matrix(.7,.7));pix.save(str(work/f'page-{i+1:02}.png'))
for start in [0,10]:
 sheet=Image.new('RGB',(1500,640),'#c5c5c5');d=ImageDraw.Draw(sheet)
 for j in range(10):
  im=Image.open(work/f'page-{start+j+1:02}.png').convert('RGB');im.thumbnail((295,295));x=(j%5)*300;y=(j//5)*320;sheet.paste(im,(x,y));d.text((x+8,y+298),str(start+j+1),fill='black')
 sheet.save(work/f'contact-{start}.jpg',quality=90)
print(json.dumps({'pdf':str(out),'pages':len(doc),'bytes':out.stat().st_size}))
