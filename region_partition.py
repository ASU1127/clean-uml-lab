"""Alternative coordinate-free partitions with full terminal bookkeeping."""
import copy
from layout_ir import identifier

def propose(ir,policy):
    if policy not in ('families','parts','singletons'):raise ValueError('Unknown partition policy')
    t=copy.deepcopy(ir);regions=[];decisions=[];assigned=set()
    family={'families':'inheritance','parts':'composition'}.get(policy)
    for candidate in ir['region_candidates']:
        if candidate['reason']['kind']!=family:continue
        available=sorted(set(candidate['members'])-assigned)
        selected=len(available)>=2
        decisions.append(dict(candidate=candidate['id'],selected=selected,excluded_already_assigned=sorted(set(candidate['members'])&assigned),remaining_members=available))
        if selected:
            assigned.update(available)
            regions.append(dict(id=identifier('region_',available),members=available,proposal=candidate['id'],reason=family))
    for n in ir['facts']['nodes']:
        if n['id'] not in assigned:regions.append(dict(id=identifier('region_',[n['id']]),members=[n['id']],proposal=None,reason='unassigned_singleton'))
    regions.sort(key=lambda r:r['id'])
    owners={n:r['id'] for r in regions for n in r['members']}
    assert sorted(owners)==sorted(n['id'] for n in ir['facts']['nodes'])
    for c in t['connections']:
        c.update(source_region=owners[c['source_node']],target_region=owners[c['target_node']],internal=owners[c['source_node']]==owners[c['target_node']])
    for region in regions:
        region['internal_relations']=[c['relation'] for c in t['connections'] if c['internal'] and c['source_region']==region['id']]
        region['boundary_terminals']=[dict(relation=c['relation'],side=side,node=c[side+'_node'],peer_region=c[('target' if side=='source' else 'source')+'_region']) for c in t['connections'] if not c['internal'] for side in ('source','target') if c[side+'_region']==region['id']]
    t.update(regions=regions,membership_decisions=decisions,policy=policy+' only; singleton remainder')
    t['diagnostics'].update(region_count=len(regions),largest_region=max(len(r['members']) for r in regions),cross_region_relations=sum(not c['internal'] for c in t['connections']),overlapping_candidates=sum(bool(d['excluded_already_assigned']) for d in decisions))
    assert t['facts']==ir['facts'] and t['relations']==ir['relations'] and t['constraints']==ir['constraints']
    return t
