"""Read explicit text edits from a generated native file and its fact model.

Geometry is intentionally discarded for a new layout. Unsupported structural
edits fail explicitly rather than silently retaining stale source semantics.
"""
import base64,copy,json,re,urllib.parse,xml.etree.ElementTree as ET,zlib
from pathlib import Path
from compile_model import compile_model
from type_bindings import normalize_model,NAME
from notation import namespace,node_title

MAX_XML=8*1024*1024

def graph_xml(path,page=None):
    data=Path(path).read_bytes()
    if len(data)>MAX_XML:raise ValueError('draw.io file exceeds the 8 MiB input limit')
    def parse(data):
        if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('XML entities are not supported')
        return ET.fromstring(data)
    root=parse(data)
    if root.tag=='mxGraphModel':return root
    if root.tag!='mxfile':raise ValueError('expected mxfile or mxGraphModel')
    pages=root.findall('diagram')
    if page is not None:pages=[p for p in pages if page in (p.get('id'),p.get('name'))]
    if len(pages)!=1:raise ValueError('select exactly one draw.io page using --page')
    diagram=pages[0]
    graph=diagram.find('mxGraphModel')
    if graph is not None:return graph
    packed=(diagram.text or '').strip()
    if not packed:raise ValueError('draw.io page is empty')
    if packed.startswith('<'):return parse(packed.encode('utf-8'))
    raw=base64.b64decode(packed,validate=True)
    decoder=zlib.decompressobj(-15)
    unpacked=decoder.decompress(raw,MAX_XML+1)
    if len(unpacked)>MAX_XML or decoder.unconsumed_tail or not decoder.eof:raise ValueError('compressed graph exceeds limit or is incomplete')
    text=urllib.parse.unquote(unpacked.decode('utf-8'),encoding='utf-8',errors='strict')
    if len(text.encode('utf-8'))>MAX_XML:raise ValueError('decoded graph exceeds limit')
    graph=parse(text.encode('utf-8'))
    if graph.tag!='mxGraphModel':raise ValueError('compressed page is not a graph model')
    return graph

def read_cells(graph):
    parents={c:p for p in graph.iter() for c in p}
    cells={}
    for c in graph.iter('mxCell'):
        attrs=dict(c.attrib)
        wrapper=parents.get(c)
        if wrapper is not None and wrapper.tag in ('object','UserObject'):
            attrs={**wrapper.attrib,**attrs}
            attrs['value']=wrapper.get('label',attrs.get('value',''))
        cid=attrs.get('id')
        if not cid or cid in cells:raise ValueError('missing or duplicate native cell identity')
        cells[cid]=attrs
    return cells

def style(cell):return dict(part.split('=',1) for part in cell.get('style','').split(';') if '=' in part)

def rename_member_types(text,replacements):
    """Rename unambiguous owned types, only in typed positions, never fields."""
    tokens=re.compile(NAME+r'|::|[.<>,\[\]]')
    def type_text(value):
        found=list(tokens.finditer(value));last=0
        for t in found:
            if value[last:t.start()].strip():raise ValueError('unsupported member type during classifier rename')
            last=t.end()
        if value[last:].strip() or not found:raise ValueError('unsupported member type during classifier rename')
        edits=[];index=0
        def expression():
            nonlocal index
            if index>=len(found) or not re.fullmatch(NAME,found[index].group()):raise ValueError('type name expected during classifier rename')
            first=index;parts=[found[index].group()];index+=1;separator='.'
            while index<len(found) and found[index].group() in ('.','::'):
                separator=found[index].group();index+=1
                if index>=len(found) or not re.fullmatch(NAME,found[index].group()):raise ValueError('qualified type name expected')
                parts.append(found[index].group());index+=1
            name='.'.join(parts)
            if name in replacements:
                replacement=replacements[name]
                if replacement is None:raise ValueError('ambiguous owned type rename: '+name)
                edits.append((found[first].start(),found[index-1].end(),separator.join(replacement)))
            if index<len(found) and found[index].group()=='<':
                index+=1;expression()
                while index<len(found) and found[index].group()==',':index+=1;expression()
                if index>=len(found) or found[index].group()!='>':raise ValueError('generic closing bracket expected')
                index+=1
            while index<len(found) and found[index].group()=='[':
                index+=1
                if index>=len(found) or found[index].group()!=']':raise ValueError('array closing bracket expected')
                index+=1
        expression()
        if index!=len(found):raise ValueError('unsupported member type tail during classifier rename')
        for start,end,value2 in reversed(edits):value=value[:start]+value2+value[end:]
        return value
    def typed(part):
        head,sep,tail=part.partition(':')
        if not sep or not head.strip():raise ValueError('typed member required for automatic type rename')
        return head+sep+type_text(tail)
    if '(' not in text:return typed(text)
    match=re.fullmatch(r'([^()]+)\(([^()]*)\)(\s*:\s*.+)',text)
    if not match:raise ValueError('typed method signature required for automatic type rename')
    params=match.group(2);depth=0;start=0;chunks=[]
    for i,c in enumerate(params):
        if c=='<':depth+=1
        elif c=='>':depth-=1
        elif c==',' and depth==0:chunks.append(typed(params[start:i]));start=i+1
    if params.strip():chunks.append(typed(params[start:]))
    prefix,_,result=match.group(3).partition(':')
    return match.group(1)+'('+','.join(chunks)+')'+prefix+':'+type_text(result)

def import_edits(path,source_model,page=None):
    # The caller supplies the exact companion model.json, whose relation order
    # is the order used by edge_N. Never guess indices from the original prompt.
    model,_=normalize_model(source_model)
    compile_model(model,validate_only=True)
    original=copy.deepcopy(model)
    cells=read_cells(graph_xml(path,page))
    trace=[];known={'0','1'};renamed={}
    def get(cid):
        if cid not in cells:raise ValueError('native structural edit is unsupported; missing '+cid)
        known.add(cid);return cells[cid]
    model.pop('package',None)
    for node,old in zip(model['nodes'],original['nodes']):
        cid='node_'+node['id'];container=get(cid)
        if container.get('vertex')!='1' or container.get('parent')!='1':raise ValueError('classifier grouping/structural edits are unsupported: '+cid)
        oldns=namespace(original,old)
        if 'package' in old or 'package' in original:
            if json.loads(container.get('cleanUmlNamespace','null'))!=oldns:raise ValueError('namespace metadata changed independently of its visible title')
        if container.get('cleanUmlVisibility')!=old.get('visibility'):raise ValueError('visibility metadata changed independently of its visible title')
        header_count=2 if node['kind'] in ('interface','enum') else 1
        title_cell=get(cid+'_text_'+str(header_count-1));title=title_cell.get('value','').strip()
        visibility=None
        if title.startswith('+ '):visibility='public';title=title[2:]
        elif title.startswith('- '):visibility='private';title=title[2:]
        if '\n' in title or '\r' in title:raise ValueError('classifier title must be one explicit qualified name')
        parts=title.split('::');node['name']=parts[-1]
        if len(parts)>1:node['package']=parts[:-1]
        else:node.pop('package',None)
        if visibility:node['visibility']=visibility
        else:node.pop('visibility',None)
        if (int(style(title_cell).get('fontStyle','0'))&2!=0)!=(node['kind']=='abstract'):raise ValueError('classifier kind/font semantics changed; update JSON explicitly')
        if header_count==2:
            stereotype=get(cid+'_text_0').get('value')
            if stereotype!=('«interface»' if node['kind']=='interface' else '«enumeration»'):raise ValueError('classifier stereotype change is unsupported')
        ordered=[i for i,m in enumerate(old['members']) if '(' not in m]+[i for i,m in enumerate(old['members']) if '(' in m]
        edited={}
        for number,index in enumerate(ordered,header_count):
            row=get(cid+'_text_'+str(number))
            if row.get('parent')!=cid:raise ValueError('member ownership changed')
            edited[index]=[line.strip() for line in row.get('value','').splitlines() if line.strip()]
        node['members']=[m for index in range(len(old['members'])) for m in edited[index]]
        for key in ('name','package','visibility','members'):
            before=oldns if key=='package' else old.get(key)
            after=namespace(model,node) if key=='package' else node.get(key)
            if before!=after:trace.append(dict(element=cid,field=key,before=before,after=after))
        oldparts=oldns+[old['name']];newparts=node.get('package',[])+[node['name']]
        if oldparts!=newparts:renamed[node['id']]=(oldparts,newparts)
        for c in cells.values():
            if c.get('parent')==cid and '_separator_' in c['id']:known.add(c['id'])
    replacements={}
    for ident,(oldparts,newparts) in renamed.items():
        replacements['.'.join(oldparts)]=newparts
        same=[n for n in original['nodes'] if n['name']==oldparts[-1]]
        replacements[oldparts[-1]]=([newparts[-1]] if oldparts[:-1]==newparts[:-1] else newparts) if len(same)==1 else None
    for node in model['nodes']:
        if node['kind']=='enum':continue
        for i,text in enumerate(node['members']):
            # Untyped text has no type position to rename. Typed positions use
            # a grammar so a field/parameter name is never globally replaced.
            if replacements and ':' in text and any(re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',text.split(':',1)[1]) for name in replacements):
                bound=rename_member_types(text,replacements)
                if bound!=text:
                    node['members'][i]=bound
                    trace.append(dict(element='node_'+node['id'],field='member_type_reference',index=i,before=text,after=bound))
    for i,relation in enumerate(model['relations']):
        eid='edge_'+str(i);edge=get(eid)
        if edge.get('edge')!='1':raise ValueError('relationship is not an edge')
        expected={'startArrow':'none','endArrow':'none','dashed':'0'}
        kind=relation['kind']
        if kind in ('generalization','realization'):expected.update(endArrow='block',endFill='0')
        if kind=='dependency':expected.update(endArrow='open')
        if kind in ('dependency','realization'):expected['dashed']='1'
        if kind in ('composition','aggregation'):expected.update(startArrow='diamondThin',startFill=str(int(kind=='composition')))
        if relation.get('navigability') in ('<-','<->'):expected['startArrow']='open'
        if relation.get('navigability') in ('->','<->'):expected['endArrow']='open'
        actual=style(edge)
        for key,value in expected.items():
            current=actual.get(key,'0' if key=='dashed' else None)
            if value=='diamondThin' and current=='diamond':continue
            if current!=value:raise ValueError('relationship marker/kind edit is unsupported: '+eid+'/'+key)
        for side in ('source','target'):
            owner='node_'+relation[side];terminal=owner
            if side+'_qualifier' in relation:
                terminal=eid+'_qualifier_'+side;q=get(terminal)
                if q.get('cleanUmlAssociation')!=eid or q.get('cleanUmlEnd')!=side or q.get('cleanUmlClassifier')!=owner:raise ValueError('qualifier ownership metadata changed')
                if q.get('parent')!=owner:
                    anchor=get(q.get('parent'))
                    if anchor.get('parent')!=owner or anchor.get('cleanUmlQualifierAnchor')!=terminal:raise ValueError('qualifier attachment ownership changed')
                before=relation[side+'_qualifier']['name'];after=q.get('value','')
                relation[side+'_qualifier']['name']=after
                if before!=after:trace.append(dict(element=eid,field=side+'_qualifier.name',before=before,after=after))
            if edge.get(side)!=terminal:raise ValueError('relationship reconnection is unsupported: '+eid+'/'+side)
            if edge.get('cleanUml'+side.title()) not in (None,owner):raise ValueError('logical relationship endpoint changed')
            if side+'_ordered' in relation and edge.get('cleanUml'+side.title()+'Ordered')!=str(relation[side+'_ordered']).lower():raise ValueError('ordering metadata changed independently of its visible label')
        for side in ('source','target','center'):
            keys=(['label'] if 'label' in relation else []) if side=='center' else [k for k in (side+'_role',side+'_multiplicity',side+'_ordered') if k in relation]
            if not keys:continue
            lid=eid+'_label_'+side;group=get(lid)
            if group.get('parent')!=eid:raise ValueError('relationship label ownership changed')
            for number,key in enumerate(keys):
                label=get(lid+'_text_'+str(number))
                if label.get('parent')!=lid:raise ValueError('relationship text group changed')
                value=label.get('value','').strip();before=relation[key]
                if key.endswith('_ordered'):
                    if value not in ('{ordered}','{unordered}'):raise ValueError('ordered label must be explicit')
                    value=value=='{ordered}'
                if value=='':relation.pop(key)
                else:relation[key]=value
                if before!=value:trace.append(dict(element=eid,field=key,before=before,after=value))
    extra=set(cells)-known
    if extra:raise ValueError('unrecognized native objects; do not silently drop '+', '.join(sorted(extra)[:8]))
    compile_model(model,validate_only=True)
    return model,dict(scope='Explicit text edits and unambiguous owned type renames from the matching exported model. Original UML identities and relationship kind/endpoints are retained. Structural edits fail explicitly; native positions are discarded for relayout.',edits=trace,classifiers=len(model['nodes']),relations=len(model['relations']),page=page)
