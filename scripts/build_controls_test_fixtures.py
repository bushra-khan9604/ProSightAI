"""Normalize the existing demonstration pack for isolated SQL tests; no database calls."""
import json
from pathlib import Path

from prosight.controls.workbooks import parse, merge_files, validate
from prosight.ingestion.excel import preview_workbook

root = Path(__file__).resolve().parents[1]
folders = sorted((root / 'outputs/project-dataset-20260912/projects').iterdir())
projects = {
    folder.name: preview_workbook(folder / 'upload_now/Project Master.xlsx', folder.name)['projects'][0]
    for folder in folders if folder.is_dir()
}


def resolve(term):
    return next((code for code, project in projects.items() if term in (code, project['name'])), None)


fixtures = []
for folder in folders:
    project = projects[folder.name]
    content = merge_files([parse(path, folder.name, resolve) for path in sorted(folder.rglob('*.xlsx'))])
    overview = (content.get('Overview') or [{}])[0]
    cutoff = overview.get('data_date', project['reporting_date'])
    fixtures.append({
        'project': project, 'content': content, 'validation': validate(content, project, cutoff),
        'metadata': {'reporting_date': cutoff, 'construction_cutoff': overview.get('construction_finish'),
                     'financial_cutoff': overview.get('financial_asof') or cutoff, 'synthetic': True},
    })
output = root / 'outputs/controls-sql-test/fixtures.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(fixtures, default=str), encoding='utf-8')
print(f'Prepared {len(fixtures)} isolated test fixtures: {output}')
