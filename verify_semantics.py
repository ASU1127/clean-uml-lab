"""Bounded semantic and notation probes, before locked-source layout calls."""
import copy,json,sys,xml.etree.ElementTree as ET
from pathlib import Path
HOME=Path(__file__).resolve().parent
sys.path.insert(0,str(HOME/'runtime/scripts'))
from compile_model import compile_model
from clean_uml import canonical
from notation import node_title,namespace
from lane_layout import measurements
from tree_layout import tree_graph,draw
from audit import audit_svg
from qualifier_layout import geometry
from drawio_export import export_drawio
from check_exports import verify

def node(ident,**optional):return dict(id=ident,name=ident,kind='class',members=[],**optional)

def run(output):
    output.mkdir(parents=True,exist_ok=False);checks=[]
    base=dict(nodes=[node('Bank',visibility='public'),node('Person')],relations=[dict(kind='association',source='Bank',target='Person',source_qualifier=dict(kind='attribute',name='accountNo'),target_multiplicity='0..1',navigability='->')])
    raw=copy.deepcopy(base);compile_model(base,validate_only=True);assert base==raw;checks.append('validation does not mutate input')
    package_model=copy.deepcopy(base);package_model['package']=['bank.main'];package_model['nodes'][1]['package']=['bank.customers'];package_model['relations'][0]['target_ordered']=False
    normalized=canonical(package_model)
    assert normalized['package']==['bank.main']
    assert node_title(normalized,normalized['nodes'][0])=='+ bank::main::Bank'
    assert namespace(normalized,normalized['nodes'][1])==['bank','customers']
    checks.append('namespace default, absolute override, visibility and explicit unordered preserved')
    duplicates=dict(nodes=[node('one'),node('two')],relations=[])
    for n,p in zip(duplicates['nodes'],['a','b']):n.update(name='Entity',package=[p])
    compile_model(duplicates,validate_only=True);checks.append('same simple classifier name in distinct packages accepted')
    invalid=[]
    for label,change in [
        ('unknown ordering',lambda m:m['relations'][0].update(target_ordered='true')),
        ('unknown visibility',lambda m:m['nodes'][0].update(visibility='protected')),
        ('package traversal',lambda m:m.update(package=['../../bad'])),
        ('qualifier markup',lambda m:m['relations'][0].update(source_qualifier=dict(kind='attribute',name='[[x]]'))),
        ('unknown qualifier type',lambda m:m['relations'][0].update(source_qualifier=dict(kind='type',name='String'))),
        ('dependency qualifier',lambda m:m['relations'][0].update(kind='dependency',navigability='--')),
        ('duplicate qualified name',lambda m:m['nodes'][1].update(id='other',name='Bank'))]:
        m=copy.deepcopy(base);change(m)
        try:compile_model(m,validate_only=True)
        except (ValueError,KeyError,TypeError):invalid.append(label)
        else:raise AssertionError('invalid semantics accepted: '+label)
    checks.append('seven malformed or unsupported declaration forms rejected')
    try:compile_model(base)
    except ValueError as e:assert 'PlantUML text serialization' in str(e)
    else:raise AssertionError('qualifier was silently dropped from PlantUML serialization')
    checks.append('unsupported PlantUML serialization rejects instead of losing qualifier')
    layout_nodes={'Bank':dict(id='Bank',x=200,y=200,width=220,height=80),'Person':dict(id='Person',x=800,y=800,width=160,height=60)}
    size={'source':dict(width=104,height=28)}
    ports=[((310,200),(330,24)),((310,280),(380,600)),((200,240),(24,300)),((420,240),(740,300))]
    for p,q in ports:
        ps,qualifiers=geometry(base,layout_nodes,base['relations'][0],[p,q],size)
        assert len(ps)==2 and math_distance(ps[0],p)>0
        assert qualifiers['source']['classifier']=='Bank'
    checks.append('all four attachment faces allow diagonal exit without an extra elbow')
    metric_items={}
    for item in measurements(base):metric_items[item['key']]=dict(width=len(item['text'])*8)
    metrics=dict(items=metric_items)
    g=tree_graph(base,metrics)
    g.update(width=700,height=500)
    for n,pos in zip(g['children'],[(200,60),(300,320)]):n.update(x=pos[0],y=pos[1])
    a,b=g['children'];p=dict(x=a['x']+a['width']/2,y=a['y']+a['height']);q=dict(x=b['x']+b['width']/2,y=b['y'])
    e=g['edges'][0];e.update(semanticReverse=False,sources=['Bank'],targets=['Person']);e['sections']=[dict(startPoint=p,endPoint=q)]
    for label in e.get('labels',[]):label.update(x=450,y=280)
    svg,scene=draw(base,metrics,g);audit=audit_svg(svg,base);assert not audit['findings'],audit
    path=output/'authored-diagonal.drawio';path.write_bytes(export_drawio(base,scene,svg));verify(path,base)
    (output/'authored-diagonal.svg').write_bytes(svg)
    root=ET.fromstring(svg);widget=root.find('.//*[@class="qualifier"]');widget.find('{http://www.w3.org/2000/svg}rect').set('y','5')
    assert any(f['code']=='qualifier_detached_from_classifier' for f in audit_svg(ET.tostring(root),base)['findings'])
    root=ET.fromstring(svg);widget=root.find('.//*[@class="qualifier"]');root.find('.//*[@id="edge_0"]').remove(widget)
    assert any(f['code']=='missing_qualifier' for f in audit_svg(ET.tostring(root),base)['findings'])
    checks.append('SVG audit detects detached and missing rectangles; independent XML semantic check passes')
    (output/'verification.json').write_text(json.dumps(dict(checks=checks,invalid_inputs=invalid,status='passed',scope='Authored notation/validation probes; no native layout engine or human-preference claim'),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(status='passed',checks=len(checks),invalid_inputs=len(invalid))))

def math_distance(a,b):return ((a[0]-b[0])**2+(a[1]-b[1])**2)**.5
if __name__=='__main__':run(Path(sys.argv[1]))
