"""Bounded label-only clearance against rendered polygon marker envelopes."""
import copy,re,xml.etree.ElementTree as ET
from tree_layout import draw
from audit import audit_svg

NS='{http://www.w3.org/2000/svg}'

def overlaps(a,b):
 return min(a[2],b[2])>max(a[0],b[0]) and min(a[3],b[3])>max(a[1],b[1])

def marker_areas(root,margin=4):
 markers=[]
 for group in root.findall(NS+'g'):
  if group.get('class')!='link':continue
  for widget in group.findall(NS+'g'):
   if widget.get('class')!='qualifier':continue
   rect=widget.find(NS+'rect');x,y,w,h=(float(rect.get(k)) for k in ('x','y','width','height'))
   markers.append((group.get('id'),(x-margin,y-margin,x+w+margin,y+h+margin)))
  for polygon in group.findall(NS+'polygon'):
   pts=[tuple(map(float,p.split(','))) for p in polygon.get('points').split()]
   markers.append((group.get('id'),(min(p[0] for p in pts)-margin,min(p[1] for p in pts)-margin,max(p[0] for p in pts)+margin,max(p[1] for p in pts)+margin)))
  for path in group.findall(NS+'path'):
   if path.get('data-marker')!='navigability':continue
   numbers=list(map(float,re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?',path.get('d',''))))
   pts=list(zip(numbers[::2],numbers[1::2]))
   markers.append((group.get('id'),(min(p[0] for p in pts)-margin,min(p[1] for p in pts)-margin,max(p[0] for p in pts)+margin,max(p[1] for p in pts)+margin)))
 return markers

def root_findings(root,markers):
 out=[]
 for group in root.findall(NS+'g'):
  if group.get('class')!='link':continue
  for t in group.findall(NS+'text'):
   x,y,w=map(float,(t.get('x'),t.get('y'),t.get('textLength')))
   box=(x,y-14,x+w,y+3)
   for marker,area in markers:
    if overlaps(box,area):out.append({'label_edge':group.get('id'),'text':t.text,'marker_edge':marker})
 return out

def findings(svg,margin=4):
 root=ET.fromstring(svg)
 return root_findings(root,marker_areas(root,margin))

class LabelScene:
 """Reuse the exact renderer tree only for flat, label-only translations."""
 def __init__(self,svg,g):
  if any('children' in n for n in g['children']) or any(e.get('container') not in (None,'root') for e in g['edges']):
   raise ValueError('Label scene reuse requires flat root geometry')
  self.root=ET.fromstring(svg);self.markers=marker_areas(self.root)
  groups={group.get('id'):group for group in self.root.findall(NS+'g') if group.get('class')=='link'}
  self.labels={}
  for edge in g['edges']:
   texts=groups[edge['id']].findall(NS+'text');cursor=0
   for label in edge.get('labels',[]):
    count=len(label['lines']);items=texts[cursor:cursor+count];cursor+=count
    if [t.text for t in items]!=label['lines'] or label['id'] in self.labels:
     raise ValueError('Renderer text does not match the label identity')
    self.labels[label['id']]=items
   if cursor!=len(texts):raise ValueError('Unmapped renderer text')
 def place(self,ident,x,y):
  for j,t in enumerate(self.labels[ident]):
   # Preserve structured_layout.draw's arithmetic and string formatting.
   t.set('x',str(x+0));t.set('y',str(y+0+14+18*j))
 def findings(self):return root_findings(self.root,self.markers)
 def bytes(self):return ET.tostring(self.root,encoding='utf-8',xml_declaration=True)

def improve_reference(model,metrics,g):
 """At most 24 px translation; retain node, route and semantic label identity."""
 svg,_=draw(model,metrics,g);before=findings(svg);current=before;events=[]
 for edge in list(g['edges']):
  for label in list(edge.get('labels',[])):
   if not any(f['label_edge']==edge['id'] and f['text'] in label['lines'] for f in current):continue
   accepted=False
   for distance in (4,8,12,16,20,24):
    for dx,dy in ((distance,0),(-distance,0),(0,distance),(0,-distance)):
     trial=copy.deepcopy(g)
     candidate=next(l for e in trial['edges'] for l in e.get('labels',[]) if l['id']==label['id'])
     candidate['x']+=dx;candidate['y']+=dy
     if candidate['x']<0 or candidate['y']<0 or candidate['x']+candidate['width']>g['width'] or candidate['y']+candidate['height']>g['height']:continue
     rendered,_=draw(model,metrics,trial);after=findings(rendered)
     oldkeys={(f['label_edge'],f['text'],f['marker_edge']) for f in current}
     newkeys={(f['label_edge'],f['text'],f['marker_edge']) for f in after}
     if len(after)<len(current) and newkeys<=oldkeys and not audit_svg(rendered,model)['findings']:
      g=trial;current=after;accepted=True;events.append({'label':label['id'],'status':'accepted','dx':dx,'dy':dy});break
    if accepted:break
   if not accepted:events.append({'label':label['id'],'status':'unresolved'})
 return g,{'before':before,'after':findings(draw(model,metrics,g)[0]),'adjustments':events,'scope':'4px padded polygon AABB; conservative clearance, not glyph collision; open dependency markers excluded'}

def improve(model,metrics,g,reuse_scene=True):
 """Same bounded search and independent final audit, without full trial draws."""
 if not reuse_scene:return improve_reference(model,metrics,g)
 svg,_=draw(model,metrics,g)
 try:scene=LabelScene(svg,g)
 except (ValueError,KeyError):return improve_reference(model,metrics,g)
 before=findings(svg);current=before;events=[]
 for edge in list(g['edges']):
  for label in list(edge.get('labels',[])):
   if not any(f['label_edge']==edge['id'] and f['text'] in label['lines'] for f in current):continue
   original=next(l for e in g['edges'] for l in e.get('labels',[]) if l['id']==label['id'])
   oldkeys={(f['label_edge'],f['text'],f['marker_edge']) for f in current};accepted=False
   for distance in (4,8,12,16,20,24):
    for dx,dy in ((distance,0),(-distance,0),(0,distance),(0,-distance)):
     x,y=original['x']+dx,original['y']+dy
     if x<0 or y<0 or x+original['width']>g['width'] or y+original['height']>g['height']:continue
     scene.place(label['id'],x,y);after=scene.findings()
     newkeys={(f['label_edge'],f['text'],f['marker_edge']) for f in after}
     if len(after)<len(current) and newkeys<=oldkeys and not audit_svg(scene.bytes(),model)['findings']:
      trial=copy.deepcopy(g)
      candidate=next(l for e in trial['edges'] for l in e.get('labels',[]) if l['id']==label['id'])
      candidate['x'],candidate['y']=x,y;g=trial;current=after;accepted=True
      events.append({'label':label['id'],'status':'accepted','dx':dx,'dy':dy});break
     scene.place(label['id'],original['x'],original['y'])
    if accepted:break
   if not accepted:events.append({'label':label['id'],'status':'unresolved'})
 # Use a fresh, complete renderer pass for the public result and later audits.
 return g,{'before':before,'after':findings(draw(model,metrics,g)[0]),'adjustments':events,'scope':'4px padded polygon AABB; conservative clearance, not glyph collision; open dependency markers excluded'}
