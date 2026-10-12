"""One failed unqualified association/dependency; bounded full-label rescue."""
import copy
import math
from route_candidates import router
from bounded_routes import visible_scene
from route_metrics import measure
from path_labels import solve
from tree_layout import draw
from audit import audit_svg
from marker_labels import findings

LIMITS={'max_options':192,'max_label_solves':12,'solver_states':10000,
        'extra_bends':2,'total_length_factor':1.03,'longest_length_factor':1.05}

def longest(scene):
    return max((sum(math.dist(a,b) for a,b in zip(e['points'],e['points'][1:])) for e in scene['edges']),default=0)

def repair(graph,model,metrics,failure,changed=()):
    trace={'limits':LIMITS,'triggered':False,'accepted':False,'label_solves':0,'attempts':[]}
    failed=failure.get('failed_label')
    if not failed:return graph,trace
    index=int(failed.split('_')[1]);relation=model['relations'][index]
    if relation['kind'] not in ('association','dependency') or any(k.endswith('_qualifier') for k in relation):
        trace['unsupported_failure_kind']=relation['kind'];return graph,trace
    eid='edge_'+str(index);edge=next(e for e in graph['edges'] if e['id']==eid)
    trace.update(triggered=True,failed_label=failed,edge=eid)
    scene=visible_scene(model,graph);before=measure(scene);max_length=longest(scene);ranked=[]
    options=router(graph['children'],graph['edges'])(edge)
    for ps in options[:LIMITS['max_options']]:
        trial=copy.deepcopy(graph);moved=next(e for e in trial['edges'] if e['id']==eid)
        moved['sections']=[dict(startPoint=ps[0],bendPoints=ps[1:-1],endPoint=ps[-1])]
        view=visible_scene(model,trial);score=measure(view)
        if any(score[k]>before[k]+1e-6 for k in ('proper_crossings','other_contacts','shared_track_length')):continue
        if score['bends']>before['bends']+LIMITS['extra_bends'] or score['route_length']>before['route_length']*LIMITS['total_length_factor'] or longest(view)>max_length*LIMITS['longest_length_factor']:continue
        ranked.append(((score['proper_crossings'],score['bends'],score['route_length']),trial,score))
    ranked.sort(key=lambda item:item[0]);trace.update(options=len(options),geometry_feasible=len(ranked))
    for _,trial,score in ranked[:LIMITS['max_label_solves']]:
        note={};trace['label_solves']+=1
        ok=solve(trial,model=model,traverse=True,preserve_edges={e['id'] for e in graph['edges']} - set(changed) - {eid},limit=LIMITS['solver_states'],trace=note)
        attempt={'solved':ok,'solver':note,'geometry':score};trace['attempts'].append(attempt)
        if not ok:continue
        svg,_=draw(model,metrics,trial)
        if audit_svg(svg,model)['findings'] or findings(svg):
            attempt['final_geometry_failed']=True;continue
        trace['accepted']=True;return trial,trace
    return graph,trace
