from collections import defaultdict
from 初始化文件处理.自动焊划分.auto_weld_split_config import VERBOSE
from shape_engine import ShapeValidator, PLengthValidator
import pandas as pd


def _log(*args, **kwargs):
    if VERBOSE:
        print(*args, **kwargs)


class LinkExtractor:
    """
    链路提取器（增强版）
    基于每行数据作为端点，建立连接关系，提取所有链路和完整形状序列
    """

    def __init__(self, df_group):
        """
        初始化链路提取器

        参数:
            df_group: 组内的DataFrame，包含焊口连接关系
        """
        self.df_group = df_group
        self.graph = defaultdict(set)  # 无向图
        self.code_to_shape = {}  # 材料唯一码 -> 形状（所有形状，包括P、E、F、T、R等）
        self.node_degree = defaultdict(int)  # 节点度数
        self.shape_validator = ShapeValidator()  # 添加形状验证器
        self.p_validator = None  # P长度验证器，稍后初始化

        self._build_graph()
        self._extract_shapes()

    def set_p_validator(self, max_p_length=12):
        """设置P长度验证器"""
        self.p_validator = PLengthValidator(max_p_length)

    def _build_graph(self):
        """从焊口数据构建连接图"""
        for idx, row in self.df_group.iterrows():
            code1 = row.get('材料唯一码1')
            code2 = row.get('材料唯一码2')

            if pd.notna(code1) and pd.notna(code2):
                code1_str = str(code1).strip()
                code2_str = str(code2).strip()

                if code1_str and code2_str:
                    self.graph[code1_str].add(code2_str)
                    self.graph[code2_str].add(code1_str)

                    self.node_degree[code1_str] += 1
                    self.node_degree[code2_str] += 1

    def _extract_shapes(self):
        """提取每个材料唯一码对应的形状（提取所有形状，不限制类型）"""
        for idx, row in self.df_group.iterrows():
            code1 = row.get('材料唯一码1')
            code2 = row.get('材料唯一码2')

            material_code1 = row.get('材料代号1', '')
            if pd.notna(material_code1) and isinstance(material_code1, str):
                shape = material_code1.strip()
                if shape and pd.notna(code1):  # 只要形状不为空就记录
                    self.code_to_shape[str(code1)] = shape

            material_code2 = row.get('材料代号2', '')
            if pd.notna(material_code2) and isinstance(material_code2, str):
                shape = material_code2.strip()
                if shape and pd.notna(code2):  # 只要形状不为空就记录
                    self.code_to_shape[str(code2)] = shape

    def find_endpoints(self):
        """
        找出所有端点（度数为1的节点）
        """
        endpoints = [node for node, degree in self.node_degree.items() if degree == 1]
        return endpoints

    def find_longest_path_from_endpoint(self, start_node, visited_global=None):
        """
        从端点出发找最长路径

        返回: (路径节点列表, 路径形状序列)
        """
        if start_node not in self.graph:
            return [], []

        visited = set()
        if visited_global:
            visited = visited_global.copy()

        def dfs(current, path, shapes):
            path.append(current)
            visited.add(current)

            shape = self.code_to_shape.get(current, '?')
            shapes.append(shape)

            neighbors = [n for n in self.graph.get(current, []) if n not in visited]

            if not neighbors:
                return path.copy(), shapes.copy()

            best_path = path.copy()
            best_shapes = shapes.copy()

            for neighbor in neighbors:
                sub_path, sub_shapes = dfs(neighbor, path.copy(), shapes.copy())
                if len(sub_path) > len(best_path):
                    best_path = sub_path
                    best_shapes = sub_shapes

            return best_path, best_shapes

        path, shapes = dfs(start_node, [], [])
        return path, shapes

    def extract_all_paths(self):
        """
        提取所有链路
        策略：
        1. 找出所有端点
        2. 从每个端点出发找最长路径
        3. 标记已访问的节点
        4. 处理剩余的未访问节点（环或孤立分支）
        5. 处理分支节点（度数>2的节点，分支单独作为链路）
        """
        all_paths = []
        visited_nodes = set()

        endpoints = self.find_endpoints()
        _log(f"    找到 {len(endpoints)} 个端点")

        for endpoint in endpoints:
            if endpoint in visited_nodes:
                continue

            path, shapes = self.find_longest_path_from_endpoint(endpoint, visited_nodes)

            if len(path) >= 2:
                for node in path:
                    visited_nodes.add(node)

                all_paths.append({
                    'nodes': path,
                    'shapes': shapes,
                    'type': 'endpoint_path'
                })
                _log(f"      端点路径: {' -> '.join(path)} ({len(path)}个节点)")
                _log(f"        形状序列: {'-'.join(shapes)}")

        remaining_nodes = set(self.graph.keys()) - visited_nodes

        if remaining_nodes:
            _log(f"    处理剩余节点: {len(remaining_nodes)}个")

            remaining_graph = {node: self.graph[node] for node in remaining_nodes}
            components = self._find_connected_components(remaining_graph)

            for comp in components:
                if len(comp) == 1:
                    node = list(comp)[0]
                    shape = self.code_to_shape.get(node, '?')
                    all_paths.append({
                        'nodes': [node],
                        'shapes': [shape],
                        'type': 'isolated_node'
                    })
                    visited_nodes.add(node)
                else:
                    path_info = self._handle_remaining_component(comp, remaining_graph)
                    if path_info:
                        for node in path_info['nodes']:
                            visited_nodes.add(node)
                        all_paths.append(path_info)
                        _log(f"      剩余路径: {' -> '.join(path_info['nodes'])} ({len(path_info['nodes'])}个节点)")
                        _log(f"        形状序列: {'-'.join(path_info['shapes'])}")


        return all_paths

    def _find_connected_components(self, graph_dict):
        """找出连通分量"""
        visited = set()
        components = []

        for node in graph_dict:
            if node not in visited:
                component = set()
                queue = [node]
                visited.add(node)

                while queue:
                    curr = queue.pop(0)
                    component.add(curr)
                    for neighbor in graph_dict.get(curr, []):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)

                components.append(component)

        return components

    def _handle_remaining_component(self, component, graph_dict):
        """处理剩余的连通分量（可能是环或链）"""
        endpoints = []

        for node in component:
            degree = len(graph_dict.get(node, []))
            if degree == 1:
                endpoints.append(node)

        if endpoints:
            best_path = []
            best_shapes = []

            for endpoint in endpoints:
                path, shapes = self._find_path_in_component(endpoint, component, graph_dict)
                if len(path) > len(best_path):
                    best_path = path
                    best_shapes = shapes

            return {
                'nodes': best_path,
                'shapes': best_shapes,
                'type': 'remaining_path'
            }

        if component:
            start_node = list(component)[0]
            path, shapes = self._traverse_cycle(start_node, component, graph_dict)
            return {
                'nodes': path,
                'shapes': shapes,
                'type': 'cycle'
            }

        return None

    def _find_path_in_component(self, start_node, component, graph_dict):
        """在连通分量中找最长路径"""
        visited = set()

        def dfs(current, path, shapes):
            path.append(current)
            visited.add(current)

            shape = self.code_to_shape.get(current, '?')
            shapes.append(shape)

            neighbors = [n for n in graph_dict.get(current, []) if n in component and n not in visited]

            if not neighbors:
                return path.copy(), shapes.copy()

            best_path = path.copy()
            best_shapes = shapes.copy()

            for neighbor in neighbors:
                sub_path, sub_shapes = dfs(neighbor, path.copy(), shapes.copy())
                if len(sub_path) > len(best_path):
                    best_path = sub_path
                    best_shapes = sub_shapes

            return best_path, best_shapes

        return dfs(start_node, [], [])

    def _traverse_cycle(self, start_node, component, graph_dict):
        """遍历环状结构"""
        path = [start_node]
        shapes = [self.code_to_shape.get(start_node, '?')]

        current = start_node
        prev = None

        while True:
            neighbors = [n for n in graph_dict.get(current, []) if n in component and n != prev]
            if not neighbors:
                break

            next_node = neighbors[0]
            path.append(next_node)
            shapes.append(self.code_to_shape.get(next_node, '?'))

            prev = current
            current = next_node

            if current == start_node and len(path) > 2:
                break

        return path, shapes

    def has_invalid_shapes(self, shape_sequence):
        """检查形状序列中是否包含不允许的形状"""
        shapes = shape_sequence.split('-')
        for shape in shapes:
            if not self.shape_validator.is_allowed_shape(shape):
                return True, shape
        return False, None

    def split_path_by_invalid_shapes(self, path_nodes, path_shapes):
        """
        根据无效形状切分路径

        返回: 多个有效的子路径列表
        """
        shape_sequence = '-'.join(path_shapes)

        sub_sequences = self.shape_validator.split_by_separators(shape_sequence, path_nodes)

        valid_sub_paths = []

        for sub_seq in sub_sequences:
            if sub_seq.get('is_separator', False):
                _log(f"        发现分隔符: {sub_seq['separator_shape']}，在此处切断")
                continue

            if len(sub_seq['node_sequence']) >= 2:
                valid_sub_paths.append({
                    'nodes': sub_seq['node_sequence'],
                    'shapes': sub_seq['shape_sequence'].split('-'),
                    'type': 'split_subpath',
                    'split_by': 'invalid_shape'
                })

        return valid_sub_paths

