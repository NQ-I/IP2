from pathlib import Path
import ast, re, json, hashlib, html
import content
OUT=Path(__file__).resolve().parent
SRC=OUT.parent/'exam_proctor_final_2026-main'
assert SRC.is_dir() and not OUT.is_relative_to(SRC)
SKIP={'node_modules','.git','__pycache__','.venv','venv','env','build','dist','.pytest_cache','models','recordings','evidence','uploads','instance','data','datasets','logs'}
def inventory():
    return sorted(p for p in SRC.rglob('*') if p.is_file() and not any(x in SKIP for x in p.relative_to(SRC).parts) and p.suffix.lower() in {'.py','.js','.html','.css','.md','.ini','.yaml','.yml','.bat'} or p.is_file() and p.parent==SRC and p.name=='requirements.txt')
def manifest():
    return {p.relative_to(SRC).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inventory()}
baseline_path=OUT/'source_baseline_resume.json'
if baseline_path.exists():
    BEFORE=json.loads(baseline_path.read_text(encoding='utf-8'))
else:
    BEFORE=manifest()
    baseline_path.write_text(json.dumps(BEFORE,ensure_ascii=False,indent=2),encoding='utf-8')
def safe(line):
    if re.search(r'(secret_key|api_key|private.key|password\s*=|database_uri|://[^\s/]+:[^\s/]+@)',line,re.I): return '# [سطر إعداد حساس محجوب]'
    return line
files=[]
for i,s in enumerate(content.SPECS):
    path,group,summary,why,deep,concepts=s
    lines=(SRC/path).read_text(encoding='utf-8-sig').splitlines()
    functions=[]; imports=[]; routes=[]
    if path.endswith('.py'):
        tree=ast.parse('\n'.join(lines))
        for n in ast.walk(tree):
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                functions.append({'name':n.name,'line':n.lineno,'end':n.end_lineno,'kind':'Class' if isinstance(n,ast.ClassDef) else 'Function','note':content.FUNCTION_NOTES.get(n.name,'هذا تعريف موجود بالمصدر. راجع المقتطف وعلاقة الملف؛ الشرح التفصيلي لهذه الدالة لم يُرحّل للمستكشف بعد.')})
            if isinstance(n,(ast.Import,ast.ImportFrom)):
                imports.append({'line':n.lineno,'text':safe(lines[n.lineno-1])})
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
                for d in n.decorator_list:
                    if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr in {'route','get','post','put','delete','patch'}:
                        routes.append({'line':d.lineno,'text':lines[d.lineno-1].strip(),'function':n.name})
    else:
        for ln,line in enumerate(lines,1):
            m=re.search(r'\b(?:async\s+)?function\s+(\w+)\s*\(|\bclass\s+(\w+)',line)
            if m: functions.append({'name':m.group(1) or m.group(2),'line':ln,'end':min(ln+16,len(lines)),'kind':'JavaScript','note':content.FUNCTION_NOTES.get(m.group(1) or m.group(2),'تعريف JavaScript موثق بالمقتطف. راجع شرح مسؤولية الملف وروابط رحلات التنفيذ.')})
    functions.sort(key=lambda n:n['line'])
    snippets=[]
    for n in functions:
        start=n['line']; snippets.append({'name':n['name'],'line':start,'code':'\n'.join(safe(x) for x in lines[start-1:min(n['end'],start+13)])})
    if not snippets or path.endswith('.html'):
        anchors=[j for j,l in enumerate(lines) if re.search(r'<form|fetch\(|addEventListener|onmessage|postMessage|AI_ASYNC|init_app',l)]
        if not anchors: anchors=[0]
        for a in anchors[:8]: snippets.append({'name':'مقتطف '+str(a+1),'line':a+1,'code':'\n'.join(safe(x) for x in lines[a:a+10])})
    files.append(dict(id=i,path=path,group=group,summary=summary,why=why,deep=deep,concepts=concepts.split(','),lines=len(lines),functions=functions,imports=imports,routes=routes,snippets=snippets))
by={f['path']:f for f in files}
def ref(path,name):
    f=by[path]
    match=next((n for n in f['functions'] if n['name']==name),None)
    if match:return match['line']
    for i,l in enumerate((SRC/path).read_text(encoding='utf-8-sig').splitlines(),1):
        if name in l:return i
    return None
flows=[]
for title,subtitle,steps in content.FLOWS:
    flows.append({'title':title,'subtitle':subtitle,'steps':[dict(path=p,name=n,input=a,output=b,kind=k,limit=g,line=ref(p,n)) for p,n,a,b,k,g in steps]})
issues=[dict(id=f'ISSUE-{i:03}',title=t,priority=p,path=f,line=l,evidence=e,impact=a,test=v) for i,(t,p,f,l,e,a,v) in enumerate(content.ISSUES,1)]
remaining=[p for p in BEFORE if p not in by]
data=dict(files=files,concepts=content.CONCEPTS,issues=issues,edges=content.EDGES,flows=flows,remaining=remaining,inventory=len(BEFORE),source=str(SRC),riskRef='core/risk.py:23–27، 92–148',build='2026-10-20')
(OUT/'explorer_data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
template=(OUT/'shell.html').read_text(encoding='utf-8')
js=(OUT/'explorer.js').read_text(encoding='utf-8')
encoded=json.dumps(data,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
(OUT/'index.html').write_text(template.replace('/*__APP__*/',js).replace('/*__DATA__*/',encoded),encoding='utf-8')
after=manifest()
result={'unchanged_since_resume':BEFORE==after,'baseline_files':len(BEFORE),'changed':[p for p in BEFORE if BEFORE[p]!=after.get(p)],'completed_files':len(files),'issues':len(issues),'flows':len(flows),'unresolved_flow_refs':[(f['title'],s['name']) for f in flows for s in f['steps'] if s['line'] is None],'limitation':'No pre-interruption baseline or Git history available. Comparison starts at this resumed build. Hash scope: source/text inventory, excluding private/generated/binary directories.'}
(OUT/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
