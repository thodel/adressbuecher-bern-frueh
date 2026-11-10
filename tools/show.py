import json,sys
r=json.load(open(sys.argv[1])); o=r['parsed']
print('finish',r['finish_reason'],'printed',o.get('printed_page'),'head',o.get('running_head'),'cont',o.get('first_entry_continues'),o.get('last_entry_continues'))
if '-l' in sys.argv:
    for l in o['lines']: print(f"{l['n']:3} {l['text']}")
F=['surname','forename','title','occupation','address','quarter','street','house_no','origin','birth_year','place','note']
for e in o['entries']:
    print(f"L{e['line_from']}-{e['line_to']} [{e.get('kind')}] h={e.get('heading')} | "+' | '.join(f"{k}={e[k]}" for k in F if e.get(k)))
    if '-t' in sys.argv: print('     T:',e.get('text'), ('\n     HH: '+e['household']) if e.get('household') else '')
