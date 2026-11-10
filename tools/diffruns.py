import json,sys,difflib
a,b,vol,page=sys.argv[1:5]
def L(r): return [l['text'] for l in json.load(open(f'data/raw/{r}/{vol}/p{int(page):03d}.json'))['parsed']['lines']]
for x in difflib.unified_diff(L(a),L(b),a,b,n=0,lineterm=''): print(x)
