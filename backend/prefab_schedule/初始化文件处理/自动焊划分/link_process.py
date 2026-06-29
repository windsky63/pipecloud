from collections import defaultdict
from shape_engine import ShapeRuleMatcher
from link_extractor import LinkExtractor
from 初始化文件处理.自动焊划分.auto_weld_split_config import COLUMNS, VERBOSE
from common_utils import prepare_output_file
from pandas import DataFrame, ExcelWriter


def _log(*args, **kwargs):
    if VERBOSE:
        print(*args, **kwargs)


def process_single_group(df_group, group_name, max_p_length=12):
    """
    对单个组进行链路提取（增强版）
    会先检查无效形状并切分路径，然后验证P长度并进一步切分
    """
    _log(f"\n处理组: {group_name}")
    _log(f"  数据量: {len(df_group)}行")

    # 创建链路提取器
    extractor = LinkExtractor(df_group)
    extractor.set_p_validator(max_p_length)

    _log(f"  图节点数: {len(extractor.graph)}")
    _log(f"  图边数: {sum(len(v) for v in extractor.graph.values()) // 2}")

    if not extractor.graph:
        _log(f"  警告：该组没有有效的材料连接")
        return []

    # 提取所有原始路径
    all_paths = extractor.extract_all_paths()

    if not all_paths:
        _log(f"  警告：未能提取到任何路径")
        return []

    _log(f"  提取到 {len(all_paths)} 条原始链路")

    # 创建形状规则匹配器
    matcher = ShapeRuleMatcher()

    # 处理每条路径，先切分再匹配，然后验证P长度
    all_results = []
    final_paths = []  # 存储切分后的最终路径

    for path_idx, path_info in enumerate(all_paths):
        path = path_info['nodes']
        shapes = path_info['shapes']

        # 过滤掉无效的路径
        if all(s == '?' for s in shapes):
            _log(f"    原始链路 {path_idx + 1}: 无效形状序列，跳过")
            continue

        if len(path) < 2:
            _log(f"    原始链路 {path_idx + 1}: 单节点，跳过")
            continue

        shape_sequence = '-'.join(shapes)
        _log(f"\n    原始链路 {path_idx + 1}: {' -> '.join(path)}")
        _log(f"      完整形状序列: {shape_sequence}")

        # 检查是否包含无效形状
        has_invalid, invalid_shape = extractor.has_invalid_shapes(shape_sequence)

        if has_invalid:
            _log(f"      发现无效形状: {invalid_shape}，需要切分")
            # 切分路径
            split_paths = extractor.split_path_by_invalid_shapes(path, shapes)

            if split_paths:
                _log(f"      切分为 {len(split_paths)} 个子路径（基于无效形状）")
                for sp_idx, split_path in enumerate(split_paths):
                    split_path['original_path_index'] = path_idx + 1
                    split_path['split_index'] = sp_idx + 1
                    split_path['parent_path'] = path_info
                    final_paths.append(split_path)
            else:
                _log(f"      切分后无有效子路径，跳过")
        else:
            # 无无效形状，直接使用原路径
            path_info['original_path_index'] = path_idx + 1
            path_info['split_index'] = 1
            path_info['split_by'] = 'none'
            final_paths.append(path_info)

    # 对最终路径进行P长度验证和进一步切分
    _log(f"\n  开始对 {len(final_paths)} 条最终链路进行P长度验证")

    p_split_paths = []

    for fp_idx, path_info in enumerate(final_paths):
        path = path_info['nodes']
        shapes = path_info['shapes']

        # 检查P长度
        total_p_length, p_details = extractor.p_validator.calculate_total_p_length(
            shapes, path, extractor.df_group
        )

        _log(f"\n    检查P长度: 总长度={total_p_length}, 限制={max_p_length}")
        if p_details:
            _log(f"      P位置详情: {[(i, info['length']) for i, info in p_details.items()]}")

        if total_p_length > max_p_length:
            _log(f"      P长度超限，需要进一步切分")

            # 根据P长度切分
            p_split_result = extractor.p_validator.split_by_p_length(
                shapes, path, p_details, extractor.df_group
            )

            for sp_idx, sub_path in enumerate(p_split_result):
                # 只保留长度>=2的子路径
                if len(sub_path['nodes']) >= 2:
                    new_path_info = {
                        'nodes': sub_path['nodes'],
                        'shapes': sub_path['shapes'],
                        'type': path_info['type'],
                        'original_path_index': path_info.get('original_path_index', fp_idx + 1),
                        'split_index': f"{path_info.get('split_index', 1)}-{sp_idx + 1}",
                        'split_by': 'p_length',
                        'parent_path': path_info,
                        'p_length_subpath': sub_path['total_p_length']
                    }
                    p_split_paths.append(new_path_info)
                else:
                    _log(f"        跳过长度<2的子路径: {sub_path['nodes']}")
        else:
            # P长度符合要求，直接使用
            path_info['split_by'] = path_info.get('split_by', 'none')
            path_info['total_p_length'] = total_p_length
            p_split_paths.append(path_info)

    _log(f"\n  P长度切分后得到 {len(p_split_paths)} 条最终链路")

    # 对最终路径进行形状规则匹配
    _log(f"\n  开始对 {len(p_split_paths)} 条最终链路进行规则匹配")

    for fp_idx, path_info in enumerate(p_split_paths):
        path = path_info['nodes']
        shapes = path_info['shapes']
        shape_sequence = '-'.join(shapes)

        _log(f"\n    最终链路 {fp_idx + 1}: {' -> '.join(path)}")
        _log(f"      形状序列: {shape_sequence}")
        _log(f"      链路类型: {path_info['type']}")
        _log(f"      切分原因: {path_info.get('split_by', 'none')}")
        if 'total_p_length' in path_info:
            _log(f"      P总长度: {path_info['total_p_length']}/{max_p_length}")

        # 检查是否符合规则或需要划分
        matched, matched_pattern = matcher.get_matched_pattern(shape_sequence)

        if matched:
            _log(f"      结果: 符合规则 OK (匹配模式: {matched_pattern})")

            all_results.append({
                'group': group_name,
                'path_index': fp_idx + 1,
                'original_path_index': path_info.get('original_path_index', fp_idx + 1),
                'split_index': path_info.get('split_index', 1),
                'split_by': path_info.get('split_by', 'none'),
                'path': ' -> '.join(path),
                'path_nodes': path,
                'shape_sequence': shape_sequence,
                'shapes_list': shapes,
                'is_valid': True,
                'division_type': '直接符合',
                'division': [shape_sequence],
                'sub_paths': [{'sub_sequence': shape_sequence, 'sub_path': path,
                               'matched_pattern': matched_pattern}],
                'path_type': path_info['type'],
                'matched_pattern': matched_pattern,
                'was_split': path_info.get('split_index', 1) != 1 or path_info.get('split_by') != 'none',
                'discarded_nodes': [],
                'total_p_length': path_info.get('total_p_length', 0),
                'p_length_limit': max_p_length
            })
        else:
            # 先尝试完美划分
            division = matcher.optimal_division(shape_sequence)

            if division:
                # 检查是否完美覆盖
                shapes_list = shape_sequence.split('-')
                covered = set()
                for start, end in division:
                    for i in range(start, end + 1):
                        covered.add(i)

                is_perfect = (len(covered) == len(shapes_list))

                if is_perfect:
                    _log(f"      结果: 需要划分（完美覆盖）")
                else:
                    _log(f"      结果: 需要划分（部分覆盖）")

                sub_paths = []
                used_indices = set()

                for start, end in division:
                    sub_seq = '-'.join(shapes_list[start:end + 1])
                    sub_path = path[start:end + 1]
                    sub_matched, sub_pattern = matcher.get_matched_pattern(sub_seq)
                    sub_paths.append({
                        'sub_sequence': sub_seq,
                        'sub_path': sub_path,
                        'matched_pattern': sub_pattern,
                        'start_index': start,
                        'end_index': end
                    })

                    for i in range(start, end + 1):
                        used_indices.add(i)

                    _log(f"        子路径: {sub_seq} -> {' -> '.join(sub_path)}")

                # 找出被舍弃的节点
                discarded_indices = set(range(len(shapes_list))) - used_indices
                if discarded_indices:
                    discarded_shapes = [shapes_list[i] for i in sorted(discarded_indices)]
                    discarded_nodes = [path[i] for i in sorted(discarded_indices)]
                    _log(
                        f"        舍弃节点: {', '.join(f'{n}({s})' for n, s in zip(discarded_nodes, discarded_shapes))}")

                all_results.append({
                    'group': group_name,
                    'path_index': fp_idx + 1,
                    'original_path_index': path_info.get('original_path_index', fp_idx + 1),
                    'split_index': path_info.get('split_index', 1),
                    'split_by': path_info.get('split_by', 'none'),
                    'path': ' -> '.join(path),
                    'path_nodes': path,
                    'shape_sequence': shape_sequence,
                    'shapes_list': shapes,
                    'is_valid': is_perfect,  # 完美覆盖才算有效
                    'division_type': '完美划分' if is_perfect else '部分划分',
                    'division': division,
                    'sub_paths': sub_paths,
                    'path_type': path_info['type'],
                    'was_split': path_info.get('split_index', 1) != 1 or path_info.get('split_by') != 'none',
                    'discarded_nodes': list(discarded_indices) if discarded_indices else [],
                    'total_p_length': path_info.get('total_p_length', 0),
                    'p_length_limit': max_p_length
                })
            else:
                # 无法完美划分，尝试提取最大匹配子序列
                max_match_subpaths = matcher.get_max_match_subpaths(shape_sequence)

                if max_match_subpaths:
                    _log(f"      结果: 提取有效子序列（舍弃无法匹配的节点）")

                    shapes_list = shape_sequence.split('-')
                    sub_paths = []
                    used_indices = set()

                    for start, end in max_match_subpaths:
                        sub_seq = '-'.join(shapes_list[start:end + 1])
                        sub_path = path[start:end + 1]
                        sub_matched, sub_pattern = matcher.get_matched_pattern(sub_seq)
                        sub_paths.append({
                            'sub_sequence': sub_seq,
                            'sub_path': sub_path,
                            'matched_pattern': sub_pattern,
                            'start_index': start,
                            'end_index': end
                        })

                        for i in range(start, end + 1):
                            used_indices.add(i)

                        _log(f"        有效子路径: {sub_seq} -> {' -> '.join(sub_path)}")

                    # 找出被舍弃的节点
                    discarded_indices = set(range(len(shapes_list))) - used_indices
                    if discarded_indices:
                        discarded_shapes = [shapes_list[i] for i in sorted(discarded_indices)]
                        discarded_nodes = [path[i] for i in sorted(discarded_indices)]
                        _log(
                            f"        舍弃节点: {', '.join(f'{n}({s})' for n, s in zip(discarded_nodes, discarded_shapes))}")

                    all_results.append({
                        'group': group_name,
                        'path_index': fp_idx + 1,
                        'original_path_index': path_info.get('original_path_index', fp_idx + 1),
                        'split_index': path_info.get('split_index', 1),
                        'split_by': path_info.get('split_by', 'none'),
                        'path': ' -> '.join(path),
                        'path_nodes': path,
                        'shape_sequence': shape_sequence,
                        'shapes_list': shapes,
                        'is_valid': True,  # 提取到的子序列是有效的
                        'division_type': '提取有效子序列',
                        'division': max_match_subpaths,
                        'sub_paths': sub_paths,
                        'path_type': path_info['type'],
                        'was_split': path_info.get('split_index', 1) != 1 or path_info.get('split_by') != 'none',
                        'discarded_nodes': list(discarded_indices) if discarded_indices else [],
                        'total_p_length': path_info.get('total_p_length', 0),
                        'p_length_limit': max_p_length
                    })
                else:
                    _log(f"      结果: 无法提取任何有效子序列 FAILED")
                    all_results.append({
                        'group': group_name,
                        'path_index': fp_idx + 1,
                        'original_path_index': path_info.get('original_path_index', fp_idx + 1),
                        'split_index': path_info.get('split_index', 1),
                        'split_by': path_info.get('split_by', 'none'),
                        'path': ' -> '.join(path),
                        'path_nodes': path,
                        'shape_sequence': shape_sequence,
                        'shapes_list': shapes,
                        'is_valid': False,
                        'division_type': '无法提取有效子序列',
                        'division': [],
                        'sub_paths': [],
                        'path_type': path_info['type'],
                        'was_split': path_info.get('split_index', 1) != 1 or path_info.get('split_by') != 'none',
                        'discarded_nodes': [],
                        'total_p_length': path_info.get('total_p_length', 0),
                        'p_length_limit': max_p_length
                    })

    return all_results


def process_all_groups(df, max_p_length=12):
    """
    按管线号和预制组件分组，对每组进行链路提取

    参数:
        df: 已经按管线号和预制组件排序的数据
        max_p_length: P形状的最大允许总长度，默认12

    返回:
        所有组的处理结果
    """
    _log("\n" + "=" * 60)
    _log("开始对各组进行链路提取")
    _log(f"P长度限制: {max_p_length}")
    _log("=" * 60)

    all_results = []

    # 按管线号和预制组件分组
    grouped = df.groupby([COLUMNS['pipeline'], COLUMNS['segment_no']])

    for (pipeline, segment_no), group_df in grouped:
        group_name = f"{pipeline}_{segment_no}"

        # 处理当前组
        results = process_single_group(group_df, group_name, max_p_length)

        if results:
            all_results.extend(results)

    # 输出总结
    _log("\n" + "=" * 60)
    _log("链路提取总结")
    _log("=" * 60)

    valid_count = sum(1 for r in all_results if r['is_valid'])
    perfect_division_count = sum(1 for r in all_results if r['division_type'] == '完美划分')
    extract_count = sum(1 for r in all_results if r['division_type'] == '提取有效子序列')
    invalid_count = sum(1 for r in all_results if r['division_type'] in ['无法提取有效子序列', '部分划分'])
    split_count = sum(1 for r in all_results if r.get('was_split', False))

    # 统计因P长度超限而切分的链路
    p_split_count = sum(1 for r in all_results if r.get('split_by') == 'p_length')
    shape_split_count = sum(1 for r in all_results if r.get('split_by') == 'invalid_shape')

    _log(f"总计处理链路: {len(all_results)}条")
    _log(f"  直接符合规则: {valid_count}条")
    _log(f"  通过完美划分符合: {perfect_division_count}条")
    _log(f"  提取有效子序列: {extract_count}条")
    _log(f"  无法符合规则: {invalid_count}条")
    _log(f"  经过切分处理: {split_count}条")
    _log(f"    - 因形状无效切分: {shape_split_count}条")
    _log(f"    - 因P长度超限切分: {p_split_count}条")

    # 按链路类型统计
    type_stats = defaultdict(int)
    for r in all_results:
        type_stats[r.get('path_type', 'unknown')] += 1

    _log(f"\n链路类型统计:")
    for path_type, count in type_stats.items():
        _log(f"  {path_type}: {count}条")

    # 显示一些形状序列示例
    _log(f"\n形状序列示例（前10条）:")
    for i, r in enumerate(all_results[:10]):
        _log(f"  {i + 1}. {r['shape_sequence']} (P总长度: {r.get('total_p_length', 0)})")

    return all_results


def save_link_division_results(results, output_file_path):
    """
    保存链路划分结果到Excel
    """
    if not results:
        _log("没有链路划分结果可保存")
        return False

    # 转换为DataFrame
    rows = []
    for r in results:
        if r['division']:
            # 处理直接符合的情况
            if r['division_type'] == '直接符合':
                division_display = r['shape_sequence']
                detailed_display = r['shape_sequence']
                # 添加匹配模式信息
                if 'matched_pattern' in r:
                    match_info = f"匹配模式: {r['matched_pattern']}"
                    detailed_display = f"{detailed_display} [{match_info}]"
            # 处理划分或提取的情况
            else:
                division_parts = []
                detailed_parts = []
                for s in r['sub_paths']:
                    division_parts.append(s['sub_sequence'])
                    sub_match_info = ""
                    if 'matched_pattern' in s:
                        sub_match_info = f"[匹配: {s['matched_pattern']}]"
                    detailed_parts.append(f"{s['sub_sequence']}({'->'.join(s['sub_path'])}){sub_match_info}")
                division_display = ' -> '.join(division_parts)
                detailed_display = ' ; '.join(detailed_parts)
        else:
            division_display = '无法划分'
            detailed_display = ''

        rows.append({
            '组名称': r['group'],
            '链路序号': r['path_index'],
            '原始链路序号': r.get('original_path_index', ''),
            '切分序号': r.get('split_index', ''),
            '切分原因': r.get('split_by', '无'),
            '是否切分': '是' if r.get('was_split', False) else '否',
            '链路类型': r.get('path_type', ''),
            '链路路径': r['path'],
            '节点数': len(r['path_nodes']),
            '形状序列': r['shape_sequence'],
            '形状序列长度': len(r['shape_sequence'].split('-')),
            'P总长度': r.get('total_p_length', 0),
            'P长度限制': r.get('p_length_limit', 12),
            '划分结果': division_display,
            '详细划分': detailed_display,
            '状态': r['division_type'],
            '匹配模式': r.get('matched_pattern', '') if r.get('is_valid') else '',
            '舍弃节点数': len(r.get('discarded_nodes', [])),
            '舍弃节点索引': ','.join(map(str, r.get('discarded_nodes', []))) if r.get('discarded_nodes') else '',
            '有效子路径数': len(r.get('sub_paths', []))
        })

    result_df = DataFrame(rows)

    try:
        prepare_output_file(output_file_path)
        with ExcelWriter(output_file_path, engine='openpyxl') as writer:
            result_df.to_excel(writer, sheet_name='链路划分结果', index=False)

            # 添加统计信息sheet
            summary = result_df.groupby('状态').size().reset_index(name='数量')
            summary['占比'] = summary['数量'] / len(result_df) * 100
            summary.to_excel(writer, sheet_name='统计摘要', index=False)

            # 按切分原因统计
            if '切分原因' in result_df.columns:
                split_reason_summary = result_df.groupby('切分原因').size().reset_index(name='数量')
                split_reason_summary.to_excel(writer, sheet_name='按切分原因统计', index=False)

            # 按P长度统计
            if 'P总长度' in result_df.columns:
                p_length_over = result_df[result_df['P总长度'] > result_df['P长度限制']]
                if not p_length_over.empty:
                    p_length_over.to_excel(writer, sheet_name='P长度超限链路', index=False)

            # 按链路类型统计
            type_summary = result_df.groupby('链路类型').size().reset_index(name='数量')
            type_summary.to_excel(writer, sheet_name='按链路类型统计', index=False)

            # 按切分状态统计
            if '是否切分' in result_df.columns:
                split_summary = result_df.groupby('是否切分').size().reset_index(name='数量')
                split_summary.to_excel(writer, sheet_name='按切分状态统计', index=False)

            # 添加按组分统计
            group_summary = result_df.groupby('组名称').agg({
                '链路序号': 'count',
                '状态': lambda x: (x == '直接符合').sum()
            }).rename(columns={'链路序号': '总链路数', '状态': '直接符合数'})
            group_summary['通过完美划分数'] = result_df.groupby('组名称').apply(
                lambda x: (x['状态'] == '完美划分').sum()
            )
            group_summary['提取子序列数'] = result_df.groupby('组名称').apply(
                lambda x: (x['状态'] == '提取有效子序列').sum()
            )
            group_summary['无法处理数'] = result_df.groupby('组名称').apply(
                lambda x: ((x['状态'] == '无法提取有效子序列') | (x['状态'] == '部分划分')).sum()
            )
            group_summary['切分数'] = result_df.groupby('组名称').apply(
                lambda x: (x['是否切分'] == '是').sum()
            )
            group_summary['P长度超限数'] = result_df.groupby('组名称').apply(
                lambda x: (x['P总长度'] > x['P长度限制']).sum() if 'P总长度' in x.columns else 0
            )
            group_summary.to_excel(writer, sheet_name='按组统计')

            # 添加形状序列统计
            shape_stats = result_df['形状序列'].value_counts().head(50).reset_index()
            shape_stats.columns = ['形状序列', '出现次数']
            shape_stats.to_excel(writer, sheet_name='形状序列统计', index=False)

            # 添加匹配模式统计
            if '匹配模式' in result_df.columns:
                pattern_stats = result_df[result_df['匹配模式'] != '']['匹配模式'].value_counts().reset_index()
                pattern_stats.columns = ['匹配模式', '出现次数']
                pattern_stats.to_excel(writer, sheet_name='匹配模式统计', index=False)

            _log(f"\n链路划分结果已保存到: {output_file_path}")
            _log(f"  保存 {len(result_df)} 条链路记录")
            _log(f"  其中 {len(result_df[result_df['P总长度'] > result_df['P长度限制']])} 条链路P长度超限")
        return True
    except Exception as e:
        _log(f"保存链路划分结果时出错: {e}")
        return False
