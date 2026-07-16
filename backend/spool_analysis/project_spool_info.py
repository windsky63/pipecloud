import re

import pandas as pd

PREFAB_WELD_LIBRARY_NAME = '预制焊口库.xlsx'
INITIALIZATION_WELD_LIBRARY_NAME = '焊口初始化数据.xlsx'
PIPE_LIBRARY_NAME = '管子材料库.xlsx'
FITTING_LIBRARY_NAME = '管件法兰材料库.xlsx'


def clean_value(value):
    if isinstance(value, list):
        return [clean_value(item) for item in value]
    if isinstance(value, dict):
        return {key: clean_value(item) for key, item in value.items()}
    if pd.isna(value):
        return ''
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    if hasattr(value, 'item'):
        return value.item()
    return value


def to_number(value, default=0):
    if pd.isna(value) or value == '':
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read_project_spool_info_from_database(project, project_root, weld_source_key='prefab', structure_spool='__first__', include_model=False):
    from pipecloud.models import FittingMaterialRow, InitializationWeldRow, PipeMaterialRow, WeldLibraryRow

    requested_source = str(weld_source_key or '').strip().lower()
    selected_source = 'initialization' if requested_source == 'initialization' else 'prefab'
    if selected_source == 'initialization':
        weld_df, weld_source = _source_dataframe(project, 'initialization', 'welds', {'*': InitializationWeldRow})
        if not weld_df.empty:
            from pipecloud.services.db_storage import initialization_rows_with_compatibility
            weld_df = pd.DataFrame(initialization_rows_with_compatibility(weld_df.to_dict(orient='records')))
    else:
        weld_df, weld_source = _source_dataframe(project, 'library', 'weld-library', {'*': WeldLibraryRow})
    init_source = _latest_data_source(project, 'initialization', 'welds')
    pipe_df, pipe_source = _library_dataframe(project, 'pipe-library', PipeMaterialRow)
    fitting_df, fitting_source = _library_dataframe(project, 'fitting-library', FittingMaterialRow)
    idf_model = _latest_idf_model(project) if include_model else None
    payload = _spool_info_payload(
        project,
        weld_df,
        pipe_df,
        fitting_df,
        _database_file_payload(weld_source, init_source, pipe_source, fitting_source, selected_source),
        structure_spool=structure_spool,
        idf_model_payload=idf_model,
        include_model=include_model,
    )
    payload.update({
        'source': 'database',
        'weldSource': selected_source,
        'projectId': project.id,
        'projectName': project.project_name,
        'projectPipeSegment': project.pipe_segment,
        'projectRoot': f'database://project/{project.id}',
    })
    if idf_model:
        from pipecloud.services.idf_model_storage import idf_database_file_payload
        payload['modelFile'] = idf_database_file_payload(idf_model)
    return payload


def _latest_idf_model(project):
    from pipecloud.services.idf_model_storage import latest_ready_idf_model

    return latest_ready_idf_model(project)


def _sanitize_idf_components(components):
    return [
        {
            key: clean_value(value)
            for key, value in component.items()
            if key not in {'raw'}
        }
        for component in components
    ]


def _library_dataframe(project, source_key, model):
    return _source_dataframe(project, 'library', source_key, {'*': model})


def _source_dataframe(project, source_type, source_key, sheet_models):
    from pipecloud.models import DataSourceFile
    from pipecloud.services.db_storage import model_field_labels
    from pipecloud.services.project_tables import ensure_project_tables, using_project_tables

    ensure_project_tables(project)
    model = sheet_models.get('*') or next((item for item in sheet_models.values() if item is not None), None)
    with using_project_tables(project):
        source = DataSourceFile.objects.filter(
            project=project,
            source_type=source_type,
            source_key=source_key,
        ).order_by('-file_updated_at', '-id').first()
        if source is None or model is None:
            return pd.DataFrame(), source
        labels = model_field_labels(model)
        rows = list(
            model.objects
            .filter(project=project, source_file=source)
            .order_by('sheet_name', 'row_index')
            .values(*labels.keys())
        )
    if not rows:
        return pd.DataFrame(columns=list(labels.values())), source
    dataframe = pd.DataFrame(rows)
    dataframe = dataframe.rename(columns=labels)
    return dataframe.reindex(columns=list(labels.values()), fill_value=''), source


def _latest_data_source(project, source_type, source_key):
    from pipecloud.models import DataSourceFile
    from pipecloud.services.project_tables import ensure_project_tables, using_project_tables

    ensure_project_tables(project)
    with using_project_tables(project):
        return DataSourceFile.objects.filter(
            project=project,
            source_type=source_type,
            source_key=source_key,
        ).order_by('-file_updated_at', '-id').first()


def _spool_info_payload(
    project,
    weld_df,
    pipe_df,
    fitting_df,
    files_payload,
    project_root='',
    source='database',
    structure_spool='__first__',
    idf_model_payload=None,
    include_model=False,
):
    if weld_df.empty:
        return {
            'source': source,
            'projectRoot': project_root,
            'files': files_payload,
            'total': 0,
            'unitCount': 0,
            'spools': [],
        }

    material_lookup = _build_material_lookup(pipe_df, fitting_df)
    spools = []
    spool_groups = _group_welds_by_unit_and_line(weld_df)

    grouped_spools = []
    for (unit_no, line_no), spool_df in spool_groups:
        first_row = spool_df.iloc[0] if len(spool_df.index) else {}
        segment_nos = _unique_text_values(spool_df, '管段号')
        resolved_unit_no = str(clean_value(unit_no) or clean_value(first_row.get('单元号', '')) or '未分单元')
        resolved_line_no = str(clean_value(line_no) or clean_value(first_row.get('管线号', '')) or '未分管线')
        spool_no = f'{resolved_unit_no} / {resolved_line_no}'
        grouped_spools.append((spool_no, resolved_unit_no, resolved_line_no, segment_nos, spool_df))

    grouped_spools.sort(key=lambda item: (item[1], item[2]))
    target_spool = str(structure_spool or '')
    if target_spool == '__first__' and grouped_spools:
        target_spool = grouped_spools[0][0]

    for spool_no, resolved_unit_no, resolved_line_no, segment_nos, spool_df in grouped_spools:
        include_details = spool_no == target_spool
        welds = [_weld_payload(row) for _, row in spool_df.iterrows()] if include_details else []
        materials = _spool_materials(spool_df, material_lookup) if include_details else []
        components, model_issues = ([], [])
        model_match_count = 0
        if include_details and include_model:
            components, model_issues, model_match_count = _spool_idf_components(spool_df, idf_model_payload)
        issues = _spool_issues(welds) if include_details else []
        issues.extend(model_issues)
        weld_count = len(spool_df.index)
        material_count = len(materials) if include_details else _spool_material_code_count(spool_df)
        spools.append({
            'spoolNo': spool_no,
            'unitNo': resolved_unit_no,
            'lineNo': resolved_line_no,
            'segmentNos': segment_nos,
            'segmentCount': len(segment_nos),
            'weldCount': weld_count,
            'completedCount': _completed_count(spool_df),
            'materialCount': material_count,
            'issueCount': len(issues),
            'inchDiameterTotal': _inch_diameter_total(spool_df),
            'welds': welds,
            'materials': materials,
            'components': components,
            'detailsLoaded': include_details,
            'structureLoaded': include_details,
            'issues': issues,
            'modelSource': 'idf' if model_match_count else '',
            'modelMatchCount': model_match_count,
        })

    return {
        'source': source,
        'projectRoot': project_root,
        'files': files_payload,
        'total': len(spools),
        'unitCount': len({spool['unitNo'] for spool in spools}),
        'spools': spools,
    }


def _group_welds_by_unit_and_line(weld_df):
    if '单元号' not in weld_df.columns:
        weld_df = weld_df.copy()
        weld_df['单元号'] = '未分单元'
    if '管线号' not in weld_df.columns:
        weld_df = weld_df.copy()
        weld_df['管线号'] = '未分管线'
    return weld_df.groupby(
        [
            weld_df['单元号'].fillna('未分单元'),
            weld_df['管线号'].fillna('未分管线'),
        ],
        dropna=False,
    )


def _unique_text_values(dataframe, column):
    if column not in dataframe.columns:
        return []
    values = []
    seen = set()
    for value in dataframe[column].tolist():
        text = str(clean_value(value)).strip()
        if text and text not in seen:
            seen.add(text)
            values.append(text)
    return values


def _database_file_payload(weld_source, init_source, pipe_source, fitting_source, selected_source):
    return {
        'weldLibrary': _single_database_payload(weld_source, PREFAB_WELD_LIBRARY_NAME if selected_source == 'prefab' else INITIALIZATION_WELD_LIBRARY_NAME),
        'initializationLibrary': _single_database_payload(init_source, INITIALIZATION_WELD_LIBRARY_NAME),
        'pipeLibrary': _single_database_payload(pipe_source, PIPE_LIBRARY_NAME),
        'fittingLibrary': _single_database_payload(fitting_source, FITTING_LIBRARY_NAME),
    }


def _single_database_payload(source, name):
    return {
        'name': source.display_name if source else name,
        'path': source.relative_path if source else f'database://missing/{name}',
        'exists': source is not None,
        'size': source.file_size if source else 0,
        'updatedAt': source.file_updated_at if source else None,
    }


def _build_material_lookup(pipe_df, fitting_df):
    lookup = {}
    _append_material_lookup(
        lookup,
        pipe_df,
        stock_column='库存数量（米）',
        default_unit='米',
        default_category='管子',
    )
    _append_material_lookup(
        lookup,
        fitting_df,
        stock_column='库存数量',
        default_unit='个',
        default_category='管件/法兰',
    )
    return lookup


def _append_material_lookup(lookup, dataframe, stock_column, default_unit, default_category):
    if dataframe.empty or '材料代码' not in dataframe.columns:
        return
    for _, row in dataframe.iterrows():
        code = str(clean_value(row.get('材料代码', ''))).strip()
        if not code:
            continue
        entry = lookup.setdefault(code, {
            'materialCode': code,
            'description': clean_value(row.get('材料描述', '')),
            'category': clean_value(row.get('材料分类', '')) or default_category,
            'name': clean_value(row.get('名称', '')),
            'spec': clean_value(row.get('规格', '')),
            'thickness': clean_value(row.get('壁厚', '')),
            'material': clean_value(row.get('材质', '')),
            'unit': clean_value(row.get('单位', '')) or default_unit,
            'stockQty': 0,
            'sources': set(),
        })
        entry['stockQty'] += to_number(row.get(stock_column, 0))
        source_file = clean_value(row.get('来源入库单文件', ''))
        if source_file:
            entry['sources'].add(str(source_file))


def _weld_payload(row):
    initial_no = clean_value(row.get('初始焊口号', ''))
    final_no = clean_value(row.get('最终焊口号', ''))
    return {
        'libraryIndex': clean_value(row.get('库序号', '')),
        'unitNo': clean_value(row.get('单元号', '')),
        'lineNo': clean_value(row.get('管线号', '')),
        'spoolNo': clean_value(row.get('管段号', '')),
        'jointType': clean_value(row.get('接头类型', '')),
        'wallThickness': clean_value(row.get('壁厚', '')),
        'inchDiameter': clean_value(row.get('寸径', '')),
        'outerDiameter': clean_value(row.get('外径', '')),
        'weldingArea': clean_value(row.get('焊接区域', '')),
        'initialWeldNo': initial_no,
        'finalWeldNo': final_no or initial_no,
        'material': clean_value(row.get('材质', '')),
        'materialCodeName': clean_value(row.get('材质代号', '')),
        'weldingMethod': clean_value(row.get('焊接方式', '')),
        'completed': _is_truthy(row.get('是否完成', False)),
        'priority': clean_value(row.get('优先级', '')),
        'materialCode1': clean_value(row.get('材料代码1', '')),
        'materialCode2': clean_value(row.get('材料代码2', '')),
        'materialMark1': clean_value(row.get('材料代号1', '')),
        'materialMark2': clean_value(row.get('材料代号2', '')),
        'description1': clean_value(row.get('描述1', '')),
        'description2': clean_value(row.get('描述2', '')),
        'qty1': clean_value(row.get('数量1', '')),
        'qty2': clean_value(row.get('数量2', '')),
    }


def _is_truthy(value):
    if isinstance(value, bool):
        return value
    text = str(clean_value(value)).strip().lower()
    return text in {'true', '1', 'yes', 'y', '是', '已完成', '完成'}


def _spool_materials(spool_df, material_lookup):
    materials = {}
    for _, row in spool_df.iterrows():
        weld_no = clean_value(row.get('最终焊口号', '')) or clean_value(row.get('初始焊口号', ''))
        for side in ('1', '2'):
            code = str(clean_value(row.get(f'材料代码{side}', ''))).strip()
            if not code:
                continue
            entry = materials.setdefault(code, _base_material_payload(code, material_lookup.get(code)))
            entry['requiredQty'] += to_number(row.get(f'数量{side}', 0))
            description = clean_value(row.get(f'描述{side}', ''))
            if description and not entry['description']:
                entry['description'] = description
            if weld_no:
                entry['weldNos'].add(str(weld_no))

    result = []
    for entry in materials.values():
        entry['requiredQty'] = round(entry['requiredQty'], 3)
        entry['stockQty'] = round(entry['stockQty'], 3)
        entry['shortageQty'] = round(max(entry['requiredQty'] - entry['stockQty'], 0), 3)
        entry['inStock'] = entry['shortageQty'] <= 0
        entry['sources'] = sorted(entry['sources'])
        entry['weldNos'] = sorted(entry['weldNos'])
        result.append(entry)
    result.sort(key=lambda item: item['materialCode'])
    return result


def _spool_material_code_count(spool_df):
    codes = set()
    for _, row in spool_df.iterrows():
        for side in ('1', '2'):
            code = str(clean_value(row.get(f'材料代码{side}', ''))).strip()
            if code:
                codes.add(code)
    return len(codes)


def _completed_count(spool_df):
    if '是否完成' not in spool_df.columns:
        return 0
    return int(sum(1 for value in spool_df['是否完成'].tolist() if _is_truthy(value)))


def _inch_diameter_total(spool_df):
    if '寸径' not in spool_df.columns:
        return 0
    return round(sum(to_number(value) for value in spool_df['寸径'].tolist()), 3)


def _base_material_payload(code, inventory):
    if inventory:
        return {
            **inventory,
            'sources': set(inventory['sources']),
            'requiredQty': 0,
            'weldNos': set(),
        }
    return {
        'materialCode': code,
        'description': '',
        'category': '未知',
        'name': '',
        'spec': '',
        'thickness': '',
        'material': '',
        'unit': '',
        'stockQty': 0,
        'sources': set(),
        'requiredQty': 0,
        'weldNos': set(),
    }


def _spool_issues(welds):
    issues = []
    for weld in welds:
        if not weld.get('finalWeldNo'):
            issues.append({'level': 'warning', 'message': '存在未编号焊口'})
            break
    return issues


def _spool_idf_components(spool_df, idf_model_payload):
    if not idf_model_payload:
        return [], [{'level': 'warning', 'message': '未找到已完成的 IDF 解析模型，结构模型暂不可用'}], 0

    from django.db.models import Q
    from pipecloud.models import IdfComponent, IdfWeldLookup

    if not idf_model_payload.component_count:
        return [], [{'level': 'warning', 'message': '最新 IDF 解析模型中没有可渲染元件'}], 0

    requested_lookup_keys = _spool_weld_lookup_keys(spool_df)
    if not requested_lookup_keys:
        return [], [{'level': 'warning', 'message': '当前管段没有可用于匹配 IDF 模型的焊口号'}], 0

    lookup_query = Q()
    for line_key, weld_key in requested_lookup_keys:
        lookup_query |= Q(line_key=line_key, weld_key=weld_key)
    lookup_rows = list(
        IdfWeldLookup.objects
        .select_related('component')
        .filter(lookup_query, model=idf_model_payload)
    )
    matched_components = {}
    for lookup in lookup_rows:
        matched_components[lookup.component_id] = lookup.component
    matched_welds = list(matched_components.values())

    if not matched_welds:
        return [], [{
            'level': 'warning',
            'message': f'IDF 模型中未匹配到当前管段的 {len(requested_lookup_keys)} 个焊口定位键',
        }], 0

    selected_refs = set()
    for weld in matched_welds:
        selected_refs.add((weld.subtask_index, weld.component_id))
        for component_id in weld.payload.get('connectedComponentIds') or []:
            selected_refs.add((weld.subtask_index, str(component_id)[:255]))

    component_query = Q()
    for subtask_index, component_id in selected_refs:
        component_query |= Q(subtask_index=subtask_index, component_id=component_id)
    selected_components = list(
        IdfComponent.objects
        .filter(component_query, model=idf_model_payload)
        .values_list('payload', flat=True)
    ) if selected_refs else []

    issues = []
    matched_lookup_keys = {
        (lookup.line_key, lookup.weld_key)
        for lookup in lookup_rows
    } & requested_lookup_keys
    missed_count = max(len(requested_lookup_keys) - len(matched_lookup_keys), 0)
    if missed_count:
        issues.append({
            'level': 'warning',
            'message': f'当前管段有 {missed_count} 个管线/焊口组合未在 IDF 模型中匹配到',
        })
    if not selected_components:
        issues.append({
            'level': 'warning',
            'message': '已匹配到 IDF 焊口，但没有找到焊口相连的可渲染元件',
        })

    return _sanitize_idf_components(selected_components), issues, len(matched_welds)


def _spool_weld_lookup_keys(spool_df):
    keys = set()
    for _, row in spool_df.iterrows():
        line_values = _scope_value_variants(row.get('管线号', ''))
        for column in ('最终焊口号', '初始焊口号'):
            weld_values = _weld_no_variants(row.get(column, ''))
            keys.update(
                (line_value, weld_value)
                for line_value in line_values
                for weld_value in weld_values
                if line_value and weld_value
            )
    return keys


def _weld_no_variants(value):
    text = str(clean_value(value)).strip()
    if not text:
        return set()
    compact = re.sub(r'\s+', '', text).upper()
    variants = {compact}
    alnum = re.sub(r'[^0-9A-Z]+', '', compact)
    if alnum:
        variants.add(alnum)
    for item in list(variants):
        if item.isdigit():
            variants.add(str(int(item)))
        match = re.search(r'(\d+(?:/\d+)?(?:-\d+)?)$', item)
        if match:
            variants.add(match.group(1).lstrip('0') or '0')
    return {item for item in variants if item}


def _scope_value_variants(value):
    text = str(clean_value(value)).strip()
    if not text:
        return set()
    compact = re.sub(r'\s+', '', text).upper()
    normalized = re.sub(r'[^0-9A-Z\u4E00-\u9FFF]+', '', compact)
    return {item for item in {compact, normalized} if item}


def _dataframe_text_set(dataframe, column):
    if column not in dataframe.columns:
        return set()
    return {
        str(clean_value(value)).strip().upper()
        for value in dataframe[column].tolist()
        if str(clean_value(value)).strip()
    }


def _idf_component_matches_scope(component, line_values, unit_values):
    if not line_values and not unit_values:
        return True
    component_line = str(component.get('pipelineName') or component.get('lineNo') or '').strip().upper()
    component_unit = str(component.get('unitName') or component.get('unitNo') or '').strip().upper()
    line_ok = not line_values or component_line in line_values or any(value and (value in component_line or component_line in value) for value in line_values)
    unit_ok = not unit_values or component_unit in unit_values or any(value and (value in component_unit or component_unit in value) for value in unit_values)
    return line_ok and unit_ok


def _spool_components(spool_df):
    material_points = {}
    weld_components = []
    synthetic_points = _synthetic_weld_coordinates(spool_df)
    missing_coordinate_count = 0
    for index, row in spool_df.iterrows():
        point = synthetic_points.get(index)
        weld_no = clean_value(row.get('最终焊口号', '')) or clean_value(row.get('初始焊口号', ''))
        if point is None:
            missing_coordinate_count += 1
            continue
        weld_components.append({
            'id': f'weld-{index}',
            'type': 'weld',
            'materialMark': 'W',
            'displayStart': point,
            'start': point,
            'spec': clean_value(row.get('外径', '')) or clean_value(row.get('寸径', '')),
            'label': str(weld_no or ''),
        })
        for side in ('1', '2'):
            unique = str(clean_value(row.get(f'材料唯一码{side}', ''))).strip()
            code = str(clean_value(row.get(f'材料代码{side}', ''))).strip()
            mark = str(clean_value(row.get(f'材料代号{side}', ''))).strip()
            key = unique or code or f'{mark}:{index}:{side}'
            if not key:
                continue
            entry = material_points.setdefault(key, {
                'id': key,
                'materialUnique': unique,
                'materialCode': code,
                'materialMark': mark,
                'description': clean_value(row.get(f'描述{side}', '')),
                'quantity': clean_value(row.get(f'数量{side}', '')),
                'spec': clean_value(row.get('外径', '')) or clean_value(row.get('寸径', '')),
                'syntheticLength': _component_layout_length(row, side),
                'points': [],
                'weldNos': [],
            })
            if point not in entry['points']:
                entry['points'].append(point)
            if weld_no:
                entry['weldNos'].append(str(weld_no))

    components = []
    for entry in material_points.values():
        points = entry.pop('points')
        if len(points) >= 2:
            points = _sort_points(points)
            component = {
                **entry,
                'id': f'material-{len(components) + 1}',
                'type': _component_type_from_material(entry['materialMark'], entry['description'], entry['materialCode']),
                'start': points[0],
                'end': points[-1],
            }
            if component['type'] == 'elbow' and len(points) >= 3:
                component['segments'] = [
                    {'start': points[i], 'end': points[i + 1]}
                    for i in range(len(points) - 1)
                ]
            components.append(component)
        elif points:
            point = points[0]
            length = max(to_number(entry.get('syntheticLength')), 0.6)
            components.append({
                **entry,
                'id': f'material-symbol-{len(components) + 1}',
                'type': _component_type_from_material(entry['materialMark'], entry['description'], entry['materialCode']),
                'start': point,
                'end': [round(point[0] + length, 3), point[1], point[2]],
                'hideInModel': False,
            })

    issues = []
    if synthetic_points:
        issues.append({
            'level': 'warning',
            'message': '结构模型使用材料数量、公称/外径和焊口连接关系生成的拓扑坐标，未使用初始化焊点坐标作为元件坐标',
        })
    if missing_coordinate_count:
        issues.append({
            'level': 'warning',
            'message': f'有 {missing_coordinate_count} 道焊口无法根据材料连接关系生成拓扑坐标，结构模型未完整显示',
        })
    components.extend(weld_components)
    return components, issues


def _synthetic_weld_coordinates(spool_df):
    material_graph = {}
    edge_rows = {}
    material_rows = {}
    for index, row in spool_df.iterrows():
        left = _material_key(row, '1', index)
        right = _material_key(row, '2', index)
        if not left or not right:
            continue
        edge_rows[index] = (left, right, row)
        material_graph.setdefault(left, []).append((right, index))
        material_graph.setdefault(right, []).append((left, index))
        material_rows.setdefault(left, (row, '1'))
        material_rows.setdefault(right, (row, '2'))

    if not edge_rows:
        return {}

    coordinates = {}
    visited_edges = set()
    component_offset = 0.0
    for start in sorted(material_graph, key=lambda key: (len(material_graph.get(key, [])), key)):
        if all(edge_index in visited_edges for _, edge_index in material_graph.get(start, [])):
            continue
        start_point = [round(component_offset, 3), 0.0, 0.0]
        _layout_material_graph(
            start,
            None,
            start_point,
            [1.0, 0.0, 0.0],
            material_graph,
            material_rows,
            coordinates,
            visited_edges,
        )
        if coordinates:
            max_x = max(point[0] for point in coordinates.values())
            component_offset = max_x + 3.0
    return coordinates


def _layout_material_graph(material_key, incoming_edge, incoming_point, direction, graph, material_rows, coordinates, visited_edges):
    neighbors = [(next_key, edge_index) for next_key, edge_index in graph.get(material_key, []) if edge_index not in visited_edges]
    if incoming_edge is None:
        if not neighbors:
            return
        first_next, first_edge = neighbors[0]
        coordinates[first_edge] = incoming_point
        visited_edges.add(first_edge)
        _layout_material_graph(first_next, first_edge, incoming_point, direction, graph, material_rows, coordinates, visited_edges)
        neighbors = [(next_key, edge_index) for next_key, edge_index in graph.get(material_key, []) if edge_index not in visited_edges]

    row, side = material_rows.get(material_key, ({}, '1'))
    length = _component_layout_length(row, side)
    spread = _branch_directions(direction, len(neighbors))
    for item_index, (next_key, edge_index) in enumerate(neighbors):
        next_direction = spread[item_index] if item_index < len(spread) else direction
        next_point = [
            round(incoming_point[0] + next_direction[0] * length, 3),
            round(incoming_point[1] + next_direction[1] * length, 3),
            round(incoming_point[2] + next_direction[2] * length, 3),
        ]
        coordinates[edge_index] = next_point
        visited_edges.add(edge_index)
        _layout_material_graph(next_key, edge_index, next_point, next_direction, graph, material_rows, coordinates, visited_edges)


def _branch_directions(direction, count):
    if count <= 1:
        return [direction]
    options = [
        direction,
        [0.0, 1.0, 0.0],
        [0.0, -1.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.0, 0.0, -1.0],
    ]
    return options[:count]


def _material_key(row, side, row_index):
    unique = str(clean_value(row.get(f'材料唯一码{side}', ''))).strip()
    code = str(clean_value(row.get(f'材料代码{side}', ''))).strip()
    mark = str(clean_value(row.get(f'材料代号{side}', ''))).strip()
    return unique or code or (f'{mark}:{row_index}:{side}' if mark else '')


def _component_layout_length(row, side):
    mark = str(clean_value(row.get(f'材料代号{side}', ''))).strip().upper()
    quantity = to_number(row.get(f'数量{side}', 0))
    diameter = to_number(row.get('外径', 0)) or to_number(row.get('寸径', 0)) * 25.4
    diameter_length = max(diameter / 1000, 0.3)
    if mark == 'P' and quantity > 0:
        return max(quantity, diameter_length)
    if quantity > 0 and mark == 'P':
        return quantity
    if mark in {'E', 'EL'}:
        return diameter_length * 1.6
    if mark in {'T', 'LT', 'RT', 'RLT'}:
        return diameter_length * 1.35
    if mark in {'F', 'FL'}:
        return diameter_length * 0.65
    if mark == 'R':
        return diameter_length * 1.0
    if mark == 'C':
        return diameter_length * 0.55
    return max(quantity, diameter_length * 0.8)


def _sort_points(points):
    if len(points) <= 2:
        return points
    ranges = []
    for axis in range(3):
        values = [point[axis] for point in points]
        ranges.append(max(values) - min(values))
    axis = ranges.index(max(ranges))
    return sorted(points, key=lambda point: point[axis])


def _component_type_from_material(mark, description='', material_code=''):
    mark_text = str(mark or '').strip().upper()
    text = f'{mark_text} {description or ""} {material_code or ""}'.upper()
    if mark_text == 'P' or text.startswith('P '):
        return 'pipe'
    if mark_text in {'E', 'EL'} or 'ELB' in text or '弯头' in text:
        return 'elbow'
    if mark_text in {'F', 'FL'} or 'FLANGE' in text or '法兰' in text:
        return 'flange'
    if mark_text in {'T', 'LT', 'RT', 'RLT'} or 'TEE' in text or '三通' in text:
        return 'branch'
    if mark_text == 'R' or 'REDUCER' in text or '大小头' in text or '异径' in text:
        return 'reducer'
    if mark_text == 'C' or 'CAP' in text or '管帽' in text:
        return 'cap'
    if 'VALVE' in text or '阀' in text:
        return 'valve'
    if 'GASKET' in text or '垫片' in text:
        return 'gasket'
    return 'component'
