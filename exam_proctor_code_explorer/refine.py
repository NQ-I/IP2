from pathlib import Path
p=Path(__file__).resolve().parent
f=p/'explorer.js'
s=f.read_text(encoding='utf-8-sig').replace("e>=.15?'UNCERTAIN'","e>=.20?'UNCERTAIN'")
f.write_text(s,encoding='utf-8')
f=p/'build_explorer.py'
s=f.read_text(encoding='utf-8-sig')
s=s.replace("BEFORE=manifest()\n(OUT/'source_baseline_resume.json').write_text(json.dumps(BEFORE,ensure_ascii=False,indent=2),encoding='utf-8')", "baseline_path=OUT/'source_baseline_resume.json'\nif baseline_path.exists():\n    BEFORE=json.loads(baseline_path.read_text(encoding='utf-8'))\nelse:\n    BEFORE=manifest()\n    baseline_path.write_text(json.dumps(BEFORE,ensure_ascii=False,indent=2),encoding='utf-8')")
f.write_text(s,encoding='utf-8')
