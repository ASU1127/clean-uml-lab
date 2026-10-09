"""Verify semantic editable export independently of the layout score."""
import xml.etree.ElementTree as ET
import json
from notation import node_title,namespace,end_lines

def verify(path,model):
    cells={c.get('id'):c for c in ET.parse(path).iter('mxCell')}
    assert sum(c.get('edge')=='1' for c in cells.values())==len(model['relations'])
    assert sorted(c.get('id') for c in cells.values() if c.get('vertex')=='1' and c.get('parent')=='1')==sorted('node_'+n['id'] for n in model['nodes'])
    def style(c):return dict(s.split('=',1) for s in c.get('style','').split(';') if '=' in s)
    for n in model['nodes']:
        children=[c for c in cells.values() if c.get('parent')=='node_'+n['id']]
        values=[c.get('value','') for c in children]
        title=node_title(model,n)
        assert title in values and all(m in values for m in n['members'])
        header=next(c for c in children if c.get('value')==title)
        if 'package' in n or 'package' in model:assert json.loads(cells['node_'+n['id']].get('cleanUmlNamespace'))==namespace(model,n)
        if 'visibility' in n:assert cells['node_'+n['id']].get('cleanUmlVisibility')==n['visibility']
        assert (int(style(header)['fontStyle'])&2!=0)==(n['kind']=='abstract')
        assert ('«interface»' in values)==(n['kind']=='interface')
        assert ('«enumeration»' in values)==(n['kind']=='enum')
    for i,r in enumerate(model['relations']):
        eid='edge_'+str(i);e=cells[eid]
        for side in ('source','target'):
            expected='node_'+r[side]
            if side+'_qualifier' in r:
                qid=eid+'_qualifier_'+side;q=cells[qid]
                assert q.get('value')==r[side+'_qualifier']['name']
                if q.get('parent')!=expected:
                    anchor=cells[q.get('parent')]
                    assert anchor.get('parent')==expected and anchor.get('cleanUmlQualifierAnchor')==qid
                    assert anchor.find('mxGeometry').get('relative')=='1'
                assert q.get('cleanUmlClassifier')==expected and q.get('cleanUmlAssociation')==eid and q.get('cleanUmlEnd')==side
                assert e.get('cleanUml'+side.title())==expected
                expected=qid
            assert e.get(side)==expected
            if side+'_ordered' in r:assert e.get('cleanUml'+side.title()+'Ordered')==str(r[side+'_ordered']).lower()
        s=style(e)
        if r['kind'] in ('generalization','realization'):
            assert s['endArrow']=='block' and s['endFill']=='0'
            assert (s.get('dashed')=='1')==(r['kind']=='realization')
        elif r['kind'] in ('composition','aggregation'):
            assert s['startArrow'] in ('diamond','diamondThin') and s['startFill']==str(int(r['kind']=='composition'))
        elif r['kind']=='dependency':assert s['endArrow']=='open' and s['dashed']=='1'
        if r.get('navigability') in ('<-','<->'):assert s['startArrow']=='open'
        if r.get('navigability') in ('->','<->'):assert s['endArrow']=='open'
        for side in ('source','target','center'):
            expected=([r['label']] if r.get('label') else []) if side=='center' else end_lines(r,side)
            if not expected:continue
            lid=eid+'_label_'+side;assert cells[lid].get('parent')==eid
            assert [c.get('value') for c in cells.values() if c.get('parent')==lid]==expected
    return dict(nodes=len(model['nodes']),relations=len(model['relations']),node_kinds_members_relation_ends_labels_markers='passed')
