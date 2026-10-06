"""產生交付校驗與工程收據；只寫 ignored dist/output 與本輪文件。"""
from pathlib import Path
import hashlib
import importlib.metadata as metadata
import json
import subprocess

root = Path(__file__).resolve().parents[1]
out = root / 'output/packaging'
bundle = root / 'dist/baldr'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
reports = {}
for name in ('portable_probe', 'portable_journey_probe', 'portable_entry_probe', 'portable_cli_probe', 'portable_configured_probe'):
    case = Path((out / f'{name}_case.txt').read_text(encoding='utf-8'))
    report_path = case / ('probe.json' if name == 'portable_probe' else f'{name}.json')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    assert report['status'] == 'passed', report
    durable = out / 'reports' / report_path.name
    durable.parent.mkdir(parents=True, exist_ok=True)
    durable.write_bytes(report_path.read_bytes())
    (durable.parent / f'{name}_process.json').write_bytes((case/'process.json').read_bytes())
    reports[name] = dict(case=str(case), report=str(durable), sha256=sha(durable.read_bytes()))
guide = (root / 'docs/07_guides/PORTABLE_WINDOWS.md').read_text(encoding='utf-8')
guide = guide.replace('[完整手冊](APPLICATION_MANUAL.md)', '原 repository 的 docs/07_guides/APPLICATION_MANUAL.md 完整手冊')
(bundle / 'README.md').write_text(guide, encoding='utf-8')
files = [p for p in bundle.rglob('*') if p.is_file() and p.name not in ('SHA256SUMS.txt', 'BUILD_INFO.json')]
assert not any(p.suffix.lower() in ('.db', '.sqlite', '.joblib', '.pkl', '.xml') or p.name.startswith('.env') for p in files)
info = dict(version='2026.10.06', exe=str(bundle/'baldr.exe'), folder_required=True,
    exe_sha256=sha((bundle/'baldr.exe').read_bytes()), exe_bytes=(bundle/'baldr.exe').stat().st_size,
    file_count=len(files), bytes=sum(p.stat().st_size for p in files), reports=reports,
    dependencies={p:metadata.version(p) for p in ('PyInstaller','pyinstaller-hooks-contrib','PySide6','scipy','scikit-learn','TA-Lib','numpy','joblib')},
    source_base_dev='e6cee8804558f008cd032e47432cd1083cb9795e',
    original_main_parent='a8c81bf534952cdf35d35a57d9e367c0fa10c817',
    unsigned=True, native_human_verified=False, original_task_changed=False,
    private_model_verified=False)
info['production_source_sha256_lf'] = {name:sha((root/name).read_bytes().replace(b'\r\n',b'\n'))
    for name in ('baldr_launcher.py','packaging/baldr.spec',
                 'analysis_module/technical_analysis/technical_indicators.py',
                 'app_module/update_status_timeline.py',
                 'app_module/runtime_services/scheduled_operations_service.py')}
(bundle/'BUILD_INFO.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
files.append(bundle/'BUILD_INFO.json')
(bundle/'SHA256SUMS.txt').write_text('\n'.join(f'{sha(p.read_bytes())}  {p.relative_to(bundle).as_posix()}' for p in sorted(files))+'\n',encoding='utf-8')
(out/'delivery.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(info,ensure_ascii=False))
