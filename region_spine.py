"""A coordinate-free spanning skeleton used only for regional placement.

Every UML relation is still routed and exported; omitted skeleton links only
stop constraining region ranks. No business-role inference is performed.
"""
from collections import defaultdict, deque

WEIGHTS={'generalization':10,'realization':10,'composition':8,'aggregation':5,'association':3,'dependency':1}

def links(model, owners, root=None):
    evidence=defaultdict(list)
    degree=defaultdict(int)
    hard=set()
    for r in model['relations']:
        a,b=owners[r['source']],owners[r['target']]
        if a==b:continue
        pair=tuple(sorted((a,b)))
        evidence[pair].append(r['kind'])
        degree[a]+=WEIGHTS[r['kind']];degree[b]+=WEIGHTS[r['kind']]
        if r['kind'] in ('generalization','realization'):hard.add((b,a))
    parent={rid:rid for rid in set(owners.values())}
    def find(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]];x=parent[x]
        return x
    chosen=[]
    for a,b in sorted(evidence,key=lambda p:(-max(WEIGHTS[k] for k in evidence[p]),-sum(WEIGHTS[k] for k in evidence[p]),p)):
        x,y=find(a),find(b)
        if x!=y:parent[x]=y;chosen.append((a,b))
    adjacency=defaultdict(list)
    for a,b in chosen:adjacency[a].append(b);adjacency[b].append(a)
    roots=sorted(parent,key=lambda n:(n!=owners.get(root),-degree[n],n))
    seen=set();result=[];selected_roots=[]
    for start in roots:
        if start in seen:continue
        selected_roots.append(start);seen.add(start);queue=deque([start])
        while queue:
            a=queue.popleft()
            for b in sorted(adjacency[a]):
                if b in seen:continue
                seen.add(b);queue.append(b)
                # Declared parent-above-child constraints override traversal.
                result.append((b,a) if (b,a) in hard else (a,b))
    result=sorted(set(result)|hard)
    return result,dict(policy='maximum spanning forest; strongest UML relation, then multiplicity of region links; degree-selected root; all cross-region generalization constraints retained',roots=selected_roots,placement_links=len(result),all_region_pairs=len(evidence),omitted_from_placement=len(evidence)-len(chosen),fact_relations_omitted=0)
