"""Bounded local workbook inspection. Cells are data, never instructions."""
from datetime import date, datetime
from pathlib import Path
import re
import zipfile
from openpyxl import load_workbook
from pydantic import ValidationError

from .project_mapping import load_mapping, normalized, column_mapping, transform, fingerprint
from openpyxl.utils import get_column_letter


def _parse_project_sheet(path, profile=None):
    from ..agents.project_creation import DraftFields
    profile = profile or load_mapping()
    path = Path(path)
    if path.suffix.lower() != '.xlsx' or not 0 < path.stat().st_size <= 20 * 1024 * 1024:
        raise ValueError('Upload an XLSX workbook between 1 byte and 20 MB')
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 2000 or sum(entry.file_size for entry in entries) > 80 * 1024 * 1024:
                raise ValueError('Workbook expanded size exceeds the safe limit')
    except zipfile.BadZipFile as error:
        raise ValueError('This file is not a valid XLSX workbook') from error
    book = load_workbook(path, read_only=True, data_only=False, keep_links=False)
    try:
        try:
            sheet = book.worksheets[profile.sheet] if isinstance(profile.sheet,int) else book[profile.sheet]
        except (IndexError,KeyError) as error:
            raise ValueError('The configured project worksheet was not found') from error
        if (sheet.max_column or 0) > 100 or (sheet.max_row or 0) > 2000:
            raise ValueError('The first sheet exceeds 2,000 rows or 100 columns')
        rows=[]
        for row_number,row in enumerate(sheet.iter_rows(),1):
            if row_number>2000 or len(row)>100:raise ValueError('The project sheet exceeds 2,000 rows or 100 columns')
            rows.append(row)
        width=max((len(row) for row in rows),default=0)
        header_number=profile.header_row
        if header_number is None and profile.data_start_row is None:
            for number,row in enumerate(rows[:30],1):
                names={normalized(cell.value) for cell in row if cell.value is not None}
                # A recognized name header anchors discovery. Code may be unlabeled.
                if names & {normalized(alias) for alias in profile.fields['name'].aliases}:
                    header_number=number;break
            if header_number is None:
                raise ValueError('No project headers found. Configure aliases, header_row, or data_start_row for a headerless sheet.')
        start=profile.data_start_row or (header_number+1 if header_number else 1)
        header_values=[cell.value for cell in rows[header_number-1]] if header_number and header_number<=len(rows) else []
        header_values += [None]*(width-len(header_values))
        names=[normalized(value) for value in header_values]
        if len([name for name in names if name])!=len(set(name for name in names if name)):
            raise ValueError('Duplicate column names in the project register')
        mapping,methods,mapping_warnings=column_mapping(header_values,rows[start-1:start+9],profile)
        if not any(field in mapping for field in ('code','name')):
            raise ValueError('Map at least a project name or code before importing a register')
        headers=[str(value).strip() if value is not None else 'Column '+get_column_letter(index+1) for index,value in enumerate(header_values)]
        evidence={field:{'column':get_column_letter(index+1),'header':header_values[index] if index<len(header_values) else None,'method':methods[field]} for field,index in mapping.items()}
        projects=[];codes=set()
        for row_number,row in enumerate(rows[start-1:],start):
            values=[cell.value for cell in row]
            if not any(value is not None and str(value).strip() for value in values):continue
            def value_at(index):
                return values[index] if index < len(values) else None
            if not any(value_at(mapping[field]) is not None for field in ('code', 'name') if field in mapping):
                continue
            source = {}
            warnings = list(mapping_warnings)
            fields = {'revised_finish': None}
            for index, header in enumerate(headers):
                value = value_at(index)
                if isinstance(value, (datetime, date)):
                    value = value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
                if isinstance(value, str) and len(value) > 4000:
                    raise ValueError(f'Row {row_number} contains text longer than 4,000 characters')
                if header:
                    source[header] = value
            for field, index in mapping.items():
                value = value_at(index)
                if value is None or value == '':
                    continue
                if row[index].data_type in {'f', 'e'}:
                    warnings.append(f'{headers[index]} is a formula or error; enter its verified value in the draft.')
                    continue
                if isinstance(value, (date, datetime)):
                    value = value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
                try:
                    value=transform(value,field,row[index],header_values[index] if index<len(header_values) else '',profile)
                except (ValueError,TypeError,OverflowError) as error:
                    warnings.append(f'{headers[index] if index<len(headers) else field}: {error}. Enter its verified value in the draft.')
                    continue
                if field in {'code', 'status'}:
                    value = str(value).strip().upper() if field == 'code' else str(value).strip().lower()
                try:
                    fields.update(DraftFields.model_validate({field: value}).model_dump(exclude_unset=True))
                except ValidationError:
                    warnings.append(f'{headers[index]} needs correction before creation.')
            code = fields.get('code')
            if code and code in codes:
                raise ValueError(f'Duplicate project code {code} in the first sheet')
            if code:
                codes.add(code)
            if any('aed' in normalized(header) for header in headers) and 'contract_value_usd' not in fields:
                warnings.append('Source amounts are AED. Provide a verified USD contract value; no currency conversion has been applied.')
            if 'client id' in names and not fields.get('client'):
                warnings.append('Client ID is preserved below. Provide the client name.')
            projects.append({'fields': fields, 'source': {'sheet': sheet.title, 'row': row_number, 'values': source, 'mapping': evidence, 'mapping_profile': profile.model_dump(), 'mapping_fingerprint': fingerprint(profile)}, 'warnings': warnings})
            if len(projects) > 100:
                raise ValueError('Upload at most 100 projects per workbook')
        if not projects:
            raise ValueError('No project rows found in the first sheet. Include Project ID / code and Project name headers.')
        return projects
    finally:
        book.close()


def parse_project_register(path, profile=None):
    """Inspect every worksheet, then join project-level facts by explicit identity."""
    profile=profile or load_mapping()
    path=Path(path)
    # Validate archive limits before asking openpyxl to load it.
    if path.suffix.lower()!='.xlsx' or not 0<path.stat().st_size<=20*1024*1024:
        raise ValueError('Upload an XLSX workbook between 1 byte and 20 MB')
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist())>2000 or sum(i.file_size for i in archive.infolist())>80*1024*1024:
            raise ValueError('Workbook expanded size exceeds the safe limit')
    book=load_workbook(path,read_only=True,data_only=False,keep_links=False)
    tables=[];clients={};client_sources={};scanned=[];total=0;kv_candidates=[]
    try:
        if len(book.worksheets)>100:raise ValueError('Workbook exceeds 100 worksheets')
        for sheet in book:
            rows=[]
            for number,row in enumerate(sheet.iter_rows(),1):
                total+=len(row)
                if number>2000 or len(row)>100 or total>200000:
                    raise ValueError('Workbook exceeds 2,000 rows per sheet, 100 columns, or 200,000 total cells')
                if any(isinstance(cell.value,str) and len(cell.value)>4000 for cell in row):raise ValueError('Workbook contains text longer than 4,000 characters in one cell')
                rows.append(row)
            scanned.append(sheet.title)
            if (sheet.title==profile.sheet or book.worksheets.index(sheet)==profile.sheet) and (profile.header_row or profile.data_start_row):
                selected=profile.model_copy(deep=True);selected.sheet=sheet.title;tables.append(selected);continue
            # Project detail sheets often store one label/value pair per row.
            aliases={normalized(alias):field for field,rule in profile.fields.items() for alias in rule.aliases}
            pairs=[(i,row,aliases.get(normalized(row[0].value))) for i,row in enumerate(rows,1) if len(row)>=2 and row[0].value is not None and aliases.get(normalized(row[0].value))]
            if len(pairs)>=2 and any(field in {'code','name'} for _,_,field in pairs):
                from ..agents.project_creation import DraftFields
                fields={'revised_finish':None};values={};evidence={};warnings=[]
                for i,row,field in pairs:
                    label=str(row[0].value);value=row[1].value;values[label]=str(value) if isinstance(value,(date,datetime)) else value
                    if row[1].data_type in {'f','e'} or value is None:continue
                    if isinstance(value,(date,datetime)):value=value.date().isoformat() if isinstance(value,datetime) else value.isoformat()
                    try:
                        value=transform(value,field,row[1],label,profile)
                        if field in {'code','status'}:value=str(value).strip().upper() if field=='code' else str(value).strip().lower()
                        fields.update(DraftFields.model_validate({field:value}).model_dump(exclude_unset=True))
                        evidence[field]={'column':'B','header':label,'method':'label/value pair','cell':f'B{i}'}
                    except (ValueError,TypeError):warnings.append(f'{label} needs review before creation.')
                kv_candidates.append({'fields':fields,'source':{'sheet':sheet.title,'row':pairs[0][0],'values':values,'mapping':evidence},'warnings':warnings})
                continue
            # Client directories can resolve a master-register client ID, never by row position.
            for number,row in enumerate(rows[:30],1):
                names=[normalized(c.value) for c in row]
                if 'client id' in names and ('client name' in names or 'client' in names or 'name' in names):
                    ci=names.index('client id');ni=names.index('client name') if 'client name' in names else names.index('client') if 'client' in names else names.index('name')
                    for source_number,source_row in enumerate(rows[number:],number+1):
                        if max(ci,ni)>=len(source_row):continue
                        key=source_row[ci].value;value=source_row[ni].value
                        if key and value and source_row[ni].data_type not in {'f','e'}:
                            clients.setdefault(str(key).strip(),set()).add(str(value).strip())
                            client_sources.setdefault(str(key).strip(),[]).append({'sheet':sheet.title,'row':source_number,'values':{'Client ID':key,'Client name':value},'mapping':{'client':{'column':get_column_letter(ni+1),'header':names[ni],'method':'Client ID join'}}})
                if 'client id' in names and not any('project' in name or 'job' in name for name in names):break
                aliases={normalized(a) for field in ('code','name') for a in profile.fields[field].aliases}
                if not set(names)&aliases:continue
                # Activity/invoice/resource dates are not project start/end dates.
                detail=any(any(token in name.split() for token in ('activity','task','invoice','employee','resource','manpower')) for name in names)
                if detail:break
                selected=profile.model_copy(deep=True)
                selected.sheet=sheet.title;selected.header_row=number;selected.data_start_row=None
                if sheet.title!=profile.sheet and book.worksheets.index(sheet)!=profile.sheet:
                    for rule in selected.fields.values():rule.column=None
                tables.append(selected);break
            else:
                if (sheet.title==profile.sheet or book.worksheets.index(sheet)==profile.sheet) and profile.data_start_row:
                    selected=profile.model_copy(deep=True);selected.sheet=sheet.title;tables.append(selected)
    finally:book.close()
    candidates=list(kv_candidates)
    for selected in tables:
        candidates.extend(_parse_project_sheet(path,selected))
    if not candidates:raise ValueError('No project-level register found in the workbook. Configure its field mappings or layout.')
    projects={};conflicts={};names_to_codes={}
    for item in candidates:
        if item['fields'].get('code') and item['fields'].get('name'):
            names_to_codes.setdefault(item['fields']['name'].casefold(),set()).add(item['fields']['code'])
    for item in candidates:
        fields=item['fields'];code=fields.get('code');name=fields.get('name')
        if not code and name:
            matches=list(names_to_codes.get(name.casefold(),set()))
            code=matches[0] if len(matches)==1 else None
        key=code or ('name:'+name.casefold() if name else None)
        if not key:continue
        source=item['source'];source['mapping_profile']=profile.model_dump();source['mapping_fingerprint']=fingerprint(profile)
        if key not in projects:
            projects[key]=item;source['records']=[{'sheet':source['sheet'],'row':source['row'],'values':source['values'],'mapping':source['mapping']}];conflicts[key]=set()
        else:
            target=projects[key];target['source']['records'].append({'sheet':source['sheet'],'row':source['row'],'values':source['values'],'mapping':source['mapping']})
            for field,value in fields.items():
                if value is None or field in conflicts[key]:continue
                before=target['fields'].get(field)
                if before is None:target['fields'][field]=value
                elif before!=value:
                    target['fields'][field]=None;conflicts[key].add(field)
                    target['warnings'].append(f'Conflicting {field} values across worksheets. Review the original records and enter the correct value.')
            target['warnings'].extend(item['warnings'])
    for key,item in projects.items():
        ids={str(value).strip() for record in item['source']['records'] for header,value in record['values'].items() if normalized(header)=='client id' and value}
        if not item['fields'].get('client') and 'client' not in conflicts[key] and len(ids)==1:
            values=clients.get(next(iter(ids)),set())
            if len(values)==1:
                item['fields']['client']=next(iter(values))
                item['source']['records'].extend(client_sources[next(iter(ids))])
                item['warnings']=[warning for warning in item['warnings'] if warning!='Client ID is preserved below. Provide the client name.']
                item['warnings'].append('Client name resolved from the workbook client directory using Client ID.')
            elif len(values)>1:item['warnings'].append('Client directory has conflicting names for this Client ID. Enter the verified client name.')
        item['source']['worksheets_scanned']=scanned
        item['warnings']=list(dict.fromkeys(item['warnings']))
    if len(projects)>100:raise ValueError('Upload at most 100 projects per workbook')
    return list(projects.values())
