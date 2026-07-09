from pathlib import Path

import pandas as pd
from typing import Set, Dict, Any, Tuple
from initialization.init_config import COLUMNS
from common_utils import prepare_output_file


class LinkResultFilter:
    """
    基于链路划分结果过滤焊口数据
    """

    def __init__(self, link_division_file: str, filtered_data_file: str):
        """
        初始化过滤器

        参数:
            link_division_file: 链路划分结果Excel文件路径
            filtered_data_file: 过滤后的数据文件路径（正常数据_排序的Excel）
        """
        self.link_division_file = link_division_file
        self.filtered_data_file = filtered_data_file
        self.link_results_df = None
        self.filtered_data_df = None

        self.nodes_to_remove: Set[str] = set()

        self.links_to_remove: Set[str] = set()

        self.successful_link_nodes: Set[str] = set()

        self.stats = {
            'total_links': 0,
            'valid_links': 0,
            'invalid_links': 0,
            'nodes_with_discard': 0,
            'total_discarded_nodes': 0,
            'links_with_discard': 0,
            'removed_nodes_in_filtered_data': 0,
            'removed_rows_in_filtered_data': 0,
            'removed_rows_by_invalid_links': 0,
            'removed_rows_by_validation': 0,  # 新增：后处理验证移除的行数
            'orphan_nodes_removed': 0  # 新增：移除的孤立节点数
        }

    def _read_excel_sheet(self, file_path, preferred_sheet):
        try:
            return pd.read_excel(file_path, sheet_name=preferred_sheet)
        except ValueError:
            xls = pd.ExcelFile(file_path)
            if not xls.sheet_names:
                raise ValueError(f'{file_path} 没有可读取的工作表')
            fallback_sheet = xls.sheet_names[0]
            print(f"  未找到工作表 {preferred_sheet}，改为读取 {fallback_sheet}")
            return pd.read_excel(xls, sheet_name=fallback_sheet)
        except Exception as error:
            raise RuntimeError(f'读取 {file_path} / {preferred_sheet} 失败: {error}') from error

    def load_data(self) -> bool:
        """加载链路划分结果和过滤后的数据"""
        try:
            self.link_results_df = self._read_excel_sheet(self.link_division_file, '链路划分结果')
            print(f"OK 成功加载链路划分结果: {len(self.link_results_df)} 条链路")

            print(f"  链路划分结果列: {list(self.link_results_df.columns)}")

            self.filtered_data_df = self._read_excel_sheet(self.filtered_data_file, '正常数据_排序')
            print(f"OK 成功加载过滤后的数据: {len(self.filtered_data_df)} 行")

            return True
        except Exception as e:
            print(f"FAILED 加载数据时出错: {e}")
            return False

    def analyze_link_results(self):
        """分析链路划分结果，提取需要移除的节点和链路"""
        if self.link_results_df is None:
            print("请先加载链路划分结果")
            return

        self.stats['total_links'] = len(self.link_results_df)

        print("\n" + "=" * 60)
        print("分析链路划分结果")
        print("=" * 60)

        invalid_link_conditions = [
            self.link_results_df['状态'] == '无法提取有效子序列',
            self.link_results_df['状态'] == '部分划分',
            self.link_results_df['状态'] == '无法划分'
        ]

        invalid_mask = pd.Series([False] * len(self.link_results_df))
        for condition in invalid_link_conditions:
            invalid_mask = invalid_mask | condition

        self.stats['invalid_links'] = invalid_mask.sum()
        self.stats['valid_links'] = self.stats['total_links'] - self.stats['invalid_links']

        for idx, row in self.link_results_df[invalid_mask].iterrows():
            link_key = f"{row['组名称']}_{row['链路序号']}"
            self.links_to_remove.add(link_key)

        print(f"\n1. 链路有效性分析:")
        print(f"   总链路数: {self.stats['total_links']}")
        print(f"   有效链路数: {self.stats['valid_links']}")
        print(f"   无效链路数: {self.stats['invalid_links']} (需要移除整条链路)")

        discard_mask = self.link_results_df['舍弃节点数'] > 0
        self.stats['links_with_discard'] = discard_mask.sum()

        for idx, row in self.link_results_df[discard_mask].iterrows():
            if row['舍弃节点索引'] and pd.notna(row['舍弃节点索引']):
                discard_indices_str = str(row['舍弃节点索引'])

                path_nodes_str = row['链路路径']
                path_nodes = path_nodes_str.split(' -> ') if pd.notna(path_nodes_str) else []

                discard_indices = []
                for idx_str in discard_indices_str.split(','):
                    try:
                        idx_val = int(idx_str.strip())
                        discard_indices.append(idx_val)
                    except:
                        pass

                for discard_idx in discard_indices:
                    if 0 <= discard_idx < len(path_nodes):
                        node = path_nodes[discard_idx]
                        self.nodes_to_remove.add(node)
                        self.stats['total_discarded_nodes'] += 1

        print(f"\n2. 舍弃节点分析:")
        print(f"   有舍弃节点的链路数: {self.stats['links_with_discard']}")
        print(f"   被舍弃的节点总数: {self.stats['total_discarded_nodes']}")
        print(f"   唯一被舍弃的节点数: {len(self.nodes_to_remove)}")

        if self.nodes_to_remove:
            print(f"\n   被舍弃的节点示例 (前20个):")
            for i, node in enumerate(list(self.nodes_to_remove)[:20]):
                print(f"     {i + 1}. {node}")

        if self.stats['invalid_links'] > 0:
            print(f"\n3. 无效链路详情:")
            invalid_links_df = self.link_results_df[invalid_mask]
            invalid_by_status = invalid_links_df['状态'].value_counts()
            for status, count in invalid_by_status.items():
                print(f"   {status}: {count} 条")

            print(f"\n   无效链路示例 (前10条):")
            for idx, row in invalid_links_df.head(10).iterrows():
                print(f"     {row['组名称']} - 链路{row['链路序号']}: {row['状态']} - {row['形状序列']}")

        self._extract_successful_link_nodes()

    def _extract_successful_link_nodes(self):
        """提取所有成功划分的链路中的节点"""
        if self.link_results_df is None:
            return

        successful_mask = ~self.link_results_df['状态'].isin(['无法提取有效子序列', '部分划分', '无法划分'])
        successful_links = self.link_results_df[successful_mask]

        for idx, row in successful_links.iterrows():
            path_nodes_str = row['链路路径']
            if pd.notna(path_nodes_str):
                path_nodes = path_nodes_str.split(' -> ')
                self.successful_link_nodes.update(path_nodes)

        print(f"\n4. 成功划分链路节点提取:")
        print(f"   成功划分的链路数: {len(successful_links)}")
        print(f"   成功划分链路中的唯一节点数: {len(self.successful_link_nodes)}")

    def filter_weld_data(self) -> pd.DataFrame:
        """根据分析结果过滤焊口数据"""
        if self.filtered_data_df is None:
            print("请先加载过滤后的数据")
            return None

        print("\n" + "=" * 60)
        print("过滤焊口数据")
        print("=" * 60)

        original_count = len(self.filtered_data_df)

        filtered_df = self.filtered_data_df.copy()

        filtered_df, removed_by_nodes = self._remove_discarded_nodes(filtered_df)

        filtered_df, removed_by_invalid_links = self._remove_invalid_links(filtered_df)

        filtered_df, removed_by_validation, orphan_nodes = self._validate_with_successful_links(filtered_df)

        final_count = len(filtered_df)
        total_removed = original_count - final_count

        print(f"\n4. 最终统计:")
        print(f"   原始数据行数: {original_count}")
        print(f"   最终数据行数: {final_count}")
        print(f"   总计移除行数: {total_removed} ({total_removed / original_count * 100:.2f}%)")

        self.stats['removed_rows_by_validation'] = removed_by_validation
        self.stats['removed_rows_in_filtered_data'] = removed_by_nodes
        self.stats['removed_rows_by_invalid_links'] = removed_by_invalid_links
        self.stats['orphan_nodes_removed'] = len(orphan_nodes)

        return filtered_df

    def _remove_discarded_nodes(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
        """移除包含舍弃节点的行"""
        mask_code1 = df['材料唯一码1'].astype(str).isin(self.nodes_to_remove)
        mask_code2 = df['材料唯一码2'].astype(str).isin(self.nodes_to_remove)
        rows_with_discarded_nodes = mask_code1 | mask_code2

        removed_count = rows_with_discarded_nodes.sum()
        filtered_df = df[~rows_with_discarded_nodes]

        print(f"\n1. 移除包含舍弃节点的数据:")
        print(f"   因包含舍弃节点移除的行数: {removed_count}")
        print(f"   实际被移除的唯一节点数: {len([n for n in self.nodes_to_remove if n in df.values])}")

        return filtered_df, removed_count

    def _remove_invalid_links(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
        """移除无效链路中的节点相关的焊口"""
        nodes_in_invalid_links = self._get_nodes_in_invalid_links()

        print(f"\n2. 分析无效链路中的节点:")
        print(f"   无效链路中的唯一节点数: {len(nodes_in_invalid_links)}")

        if not nodes_in_invalid_links:
            print("   没有无效链路节点需要移除")
            return df, 0

        mask_invalid_link1 = df['材料唯一码1'].astype(str).isin(nodes_in_invalid_links)
        mask_invalid_link2 = df['材料唯一码2'].astype(str).isin(nodes_in_invalid_links)
        rows_in_invalid_links = mask_invalid_link1 | mask_invalid_link2

        removed_count = rows_in_invalid_links.sum()
        filtered_df = df[~rows_in_invalid_links]

        print(f"   因无效链路移除的行数: {removed_count}")

        return filtered_df, removed_count

    def _validate_with_successful_links(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, int, Set[str]]:
        """
        后处理验证：只保留两端都在成功划分链路中的焊口

        返回:
            (过滤后的DataFrame, 移除的行数, 被移除的孤立节点集合)
        """
        if not self.successful_link_nodes:
            print("\n3. 后处理验证:")
            print("   警告: 没有成功划分的链路节点数据，跳过验证")
            return df, 0, set()

        print(f"\n3. 后处理验证（隐形链路过滤）:")
        print(f"   成功划分链路中的节点数: {len(self.successful_link_nodes)}")

        mask_code1_valid = df['材料唯一码1'].astype(str).isin(self.successful_link_nodes)
        mask_code2_valid = df['材料唯一码2'].astype(str).isin(self.successful_link_nodes)

        rows_valid = mask_code1_valid & mask_code2_valid
        rows_invalid = ~rows_valid

        removed_count = rows_invalid.sum()

        removed_df = df[rows_invalid]
        orphan_nodes = set()
        orphan_nodes.update(removed_df['材料唯一码1'].astype(str))
        orphan_nodes.update(removed_df['材料唯一码2'].astype(str))
        orphan_nodes = orphan_nodes - self.successful_link_nodes

        filtered_df = df[rows_valid]

        print(f"   后处理验证移除行数: {removed_count}")
        print(f"   发现孤立节点数: {len(orphan_nodes)}")

        if removed_count > 0:
            print(f"   这些行对应的焊口两端至少有一端不在任何成功划分的链路中")
            if len(orphan_nodes) > 0:
                print(f"   孤立节点示例 (前10个): {list(orphan_nodes)[:10]}")

        return filtered_df, removed_count, orphan_nodes

    def _get_nodes_in_invalid_links(self) -> Set[str]:
        """获取无效链路中的所有节点"""
        if self.link_results_df is None:
            return set()

        nodes = set()

        invalid_mask = self.link_results_df['状态'].isin(['无法提取有效子序列', '部分划分', '无法划分'])
        invalid_links = self.link_results_df[invalid_mask]

        for idx, row in invalid_links.iterrows():
            path_nodes_str = row['链路路径']
            if pd.notna(path_nodes_str):
                path_nodes = path_nodes_str.split(' -> ')
                for node in path_nodes:
                    nodes.add(node)

        print(f"   从{len(invalid_links)}条无效链路中提取了{len(nodes)}个唯一节点")

        return nodes

    def _build_stats_df(self, filtered_df: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame([
            ['总链路数', self.stats['total_links']],
            ['有效链路数', self.stats['valid_links']],
            ['无效链路数', self.stats['invalid_links']],
            ['有舍弃节点的链路数', self.stats['links_with_discard']],
            ['被舍弃的节点总数', self.stats['total_discarded_nodes']],
            ['唯一被舍弃的节点数', len(self.nodes_to_remove)],
            ['成功划分链路中的节点数', len(self.successful_link_nodes)],
            ['原始焊口数据行数', len(self.filtered_data_df)],
            ['最终焊口数据行数', len(filtered_df)],
            ['移除的焊口数据行数', len(self.filtered_data_df) - len(filtered_df)],
            ['移除比例(%)', (len(self.filtered_data_df) - len(filtered_df)) / len(self.filtered_data_df) * 100],
            ['其中: 舍弃节点移除', self.stats['removed_rows_in_filtered_data']],
            ['其中: 无效链路移除', self.stats['removed_rows_by_invalid_links']],
            ['其中: 后处理验证移除', self.stats['removed_rows_by_validation']],
            ['移除的孤立节点数', self.stats['orphan_nodes_removed']]
        ], columns=['统计项', '数值'])

    def _default_stats_output_file(self, output_file: str) -> str:
        output_path = Path(output_file)
        return str(output_path.with_name(f"{output_path.stem}_过滤统计{output_path.suffix}"))

    def save_filtered_data(self, output_file: str, stats_output_file: str = None, include_removed: bool = True):
        """
        保存过滤后的数据

        参数:
            output_file: 输出文件路径
            stats_output_file: 过滤统计输出文件路径
            include_removed: 是否同时保存被移除的数据
        """
        if self.filtered_data_df is None:
            print("请先加载数据并执行过滤")
            return False

        filtered_df = self.filter_weld_data()

        if filtered_df is None:
            return False

        stats_output_file = stats_output_file or self._default_stats_output_file(output_file)

        seq_col = COLUMNS['library_seq']
        if seq_col not in filtered_df.columns:
            filtered_df.insert(0, seq_col, range(1, len(filtered_df) + 1))

        try:
            prepare_output_file(output_file)
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                filtered_df.to_excel(writer, sheet_name='Sheet1', index=False)

            prepare_output_file(stats_output_file)
            with pd.ExcelWriter(stats_output_file, engine='openpyxl') as writer:
                stats_df = self._build_stats_df(filtered_df)
                stats_df.to_excel(writer, sheet_name='过滤统计', index=False)

                if self.nodes_to_remove:
                    discarded_nodes_df = pd.DataFrame(sorted(self.nodes_to_remove), columns=['被舍弃的节点'])
                    discarded_nodes_df.to_excel(writer, sheet_name='被舍弃的节点', index=False)

                if self.successful_link_nodes:
                    successful_nodes_df = pd.DataFrame(sorted(self.successful_link_nodes), columns=['成功链路中的节点'])
                    successful_nodes_df.to_excel(writer, sheet_name='成功链路节点白名单', index=False)

                if self.link_results_df is not None:
                    invalid_mask = self.link_results_df['状态'].isin(['无法提取有效子序列', '部分划分', '无法划分'])
                    invalid_links_df = self.link_results_df[invalid_mask]
                    if len(invalid_links_df) > 0:
                        invalid_links_df.to_excel(writer, sheet_name='无效链路', index=False)

                if include_removed:
                    removed_data = self._get_removed_data()
                    if len(removed_data) > 0:
                        removed_data.to_excel(writer, sheet_name='被移除的焊口数据', index=False)

            print(f"\nOK 过滤后的数据已保存到: {output_file}")
            print(f"OK 过滤统计已保存到: {stats_output_file}")
            print(f"  包含 {len(filtered_df)} 行有效数据")
            return True

        except Exception as e:
            print(f"FAILED 保存文件时出错: {e}")
            return False

    def _get_removed_data(self) -> pd.DataFrame:
        """获取所有被移除的数据"""
        if self.filtered_data_df is None:
            return pd.DataFrame()

        mask_code1 = self.filtered_data_df['材料唯一码1'].astype(str).isin(self.nodes_to_remove)
        mask_code2 = self.filtered_data_df['材料唯一码2'].astype(str).isin(self.nodes_to_remove)
        removed_by_nodes = self.filtered_data_df[mask_code1 | mask_code2]

        nodes_in_invalid = self._get_nodes_in_invalid_links()
        mask_invalid1 = self.filtered_data_df['材料唯一码1'].astype(str).isin(nodes_in_invalid)
        mask_invalid2 = self.filtered_data_df['材料唯一码2'].astype(str).isin(nodes_in_invalid)
        removed_by_invalid = self.filtered_data_df[mask_invalid1 | mask_invalid2]

        mask_code1_valid = self.filtered_data_df['材料唯一码1'].astype(str).isin(self.successful_link_nodes)
        mask_code2_valid = self.filtered_data_df['材料唯一码2'].astype(str).isin(self.successful_link_nodes)
        rows_valid = mask_code1_valid & mask_code2_valid
        removed_by_validation = self.filtered_data_df[~rows_valid]

        removed_data = pd.concat([removed_by_nodes, removed_by_invalid, removed_by_validation]).drop_duplicates()

        return removed_data

    def generate_report(self) -> Dict[str, Any]:
        """生成详细的过滤报告"""
        report = {
            '数据统计': {
                '总链路数': self.stats['total_links'],
                '有效链路数': self.stats['valid_links'],
                '无效链路数': self.stats['invalid_links'],
                '无效链路比例(%)': self.stats['invalid_links'] / self.stats['total_links'] * 100 if self.stats[
                                                                                                        'total_links'] > 0 else 0,
                '有舍弃节点的链路数': self.stats['links_with_discard'],
                '有舍弃节点链路比例(%)': self.stats['links_with_discard'] / self.stats['total_links'] * 100 if
                self.stats['total_links'] > 0 else 0,
                '被舍弃的节点总数': self.stats['total_discarded_nodes'],
                '唯一被舍弃的节点数': len(self.nodes_to_remove),
                '成功划分链路中的节点数': len(self.successful_link_nodes),
            },
            '焊口数据统计': {
                '原始焊口数据行数': len(self.filtered_data_df) if self.filtered_data_df is not None else 0,
                '最终焊口数据行数': 0,
                '移除的行数': 0,
                '移除比例(%)': 0,
                '舍弃节点移除行数': self.stats['removed_rows_in_filtered_data'],
                '无效链路移除行数': self.stats['removed_rows_by_invalid_links'],
                '后处理验证移除行数': self.stats['removed_rows_by_validation'],
                '移除的孤立节点数': self.stats['orphan_nodes_removed']
            },
            '被舍弃节点详情': {
                '节点列表': sorted(self.nodes_to_remove)[:50],
                '节点总数': len(self.nodes_to_remove)
            }
        }

        return report


def post_process_filter(link_division_file: str, filtered_data_file: str, output_file: str, stats_output_file: str = None):
    """
    后处理验证函数：对已生成的焊口数据进行二次过滤

    参数:
        link_division_file: 链路划分结果文件
        filtered_data_file: 待过滤的焊口数据文件
        output_file: 输出文件路径
        stats_output_file: 过滤统计输出文件路径
    """
    print("=" * 60)
    print("后处理验证 - 隐形链路过滤")
    print("=" * 60)

    filter_tool = LinkResultFilter(link_division_file, filtered_data_file)

    if not filter_tool.load_data():
        print("数据加载失败，程序退出")
        return False

    filter_tool.analyze_link_results()

    filter_tool.save_filtered_data(output_file, stats_output_file=stats_output_file, include_removed=True)

    report = filter_tool.generate_report()

    print("\n" + "=" * 60)
    print("后处理验证报告")
    print("=" * 60)

    print("\n【链路统计】")
    for key, value in report['数据统计'].items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")

    print("\n【过滤效果】")
    print(f"  后处理验证额外移除了 {report['焊口数据统计']['后处理验证移除行数']} 行数据")
    print(f"  这些数据属于完全无法划分的隐形链路")

    print("\n【过滤建议】")
    print("  1. 后处理验证采用了严格模式：只保留两端都在成功链路中的焊口")
    print("  2. 这确保了所有保留的焊口都属于有效链路")
    print("  3. 如果发现过度过滤，可以考虑使用宽松模式（至少一端在成功链路中）")

    return True


if __name__ == "__main__":
    post_process_filter(
        "链路划分结果.xlsx",
        "焊口数据_过滤结果_分组排序.xlsx",
        "自动焊口数据_后处理验证.xlsx",
        "自动焊口数据_后处理验证_过滤统计.xlsx",
    )

