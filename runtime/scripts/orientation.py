"""Keep inheritance directions when ordinary BFS orientation creates a cycle."""
def inheritance_safe_rank(model,rank):
 ids=sorted(rank);links={i:set() for i in ids};indeg=dict.fromkeys(ids,0)
 for r in model['relations']:
  a,b=r['source'],r['target']
  if a==b:continue
  if r['kind'] in ('generalization','realization'):a,b=b,a
  elif (rank[a],a)>(rank[b],b):a,b=b,a
  if b not in links[a]:links[a].add(b);indeg[b]+=1
 ready=sorted(i for i in ids if indeg[i]==0);seen=[]
 for a in ready:
  seen.append(a)
  for b in sorted(links[a]):
   indeg[b]-=1
   if indeg[b]==0:ready.append(b)
 if len(seen)==len(ids):return rank
 # Only inheritance is directionally constrained. Other edges may be reversed
 # for layout, with semanticReverse restoring original UML source/target.
 children={i:set() for i in ids};family={i:set() for i in ids};indeg=dict.fromkeys(ids,0)
 for r in model['relations']:
  if r['kind'] not in ('generalization','realization'):continue
  parent,child=r['target'],r['source'];family[parent].add(child);family[child].add(parent)
  if child not in children[parent]:children[parent].add(child);indeg[child]+=1
 priority={};visited=set()
 for start in ids:
  if start in visited:continue
  component=[start];visited.add(start)
  for n in component:
   for x in sorted(family[n]):
    if x not in visited:visited.add(x);component.append(x)
  level=min(rank[x] for x in component)
  for x in component:priority[x]=level
 ordered={};ready={i for i in ids if indeg[i]==0}
 while ready:
  a=min(ready,key=lambda x:(priority[x],rank[x],x));ready.remove(a);ordered[a]=len(ordered)
  for b in sorted(children[a]):
   indeg[b]-=1
   if indeg[b]==0:ready.add(b)
 if len(ordered)!=len(ids):raise ValueError('Cyclic inheritance constraints')
 return ordered


def relation_distance_rank(model,root=None):
 """Experimental layout distances, not UML semantic strengths or standards."""
 import heapq
 costs={'association':1,'aggregation':.75,'composition':.75,
        'generalization':.5,'realization':.5,'dependency':4}
 adjacency={n['id']:{} for n in model['nodes']}
 for r in model['relations']:
  a,b=r['source'],r['target'];cost=costs[r['kind']]
  adjacency[a][b]=min(cost,adjacency[a].get(b,float('inf')))
  adjacency[b][a]=adjacency[a][b]
 distances={}
 while len(distances)<len(adjacency):
  start=root if root is not None and root not in distances else max(
   (n for n in adjacency if n not in distances),key=lambda n:(len(adjacency[n]),n))
  queue=[(0,start)]
  while queue:
   distance,n=heapq.heappop(queue)
   if n in distances:continue
   distances[n]=distance
   for other,cost in sorted(adjacency[n].items()):
    if other not in distances:heapq.heappush(queue,(distance+cost,other))
 return inheritance_safe_rank(model,distances)
