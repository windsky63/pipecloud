from initialization.init_config import COLUMNS, PATTERN_CONFIG
import pandas as pd


def generate_complete_patterns(original_patterns):
    def generate_sub_links(link_pattern):
        nodes = link_pattern.split('-')
        n = len(nodes)
        sub_links = set()
        for length in range(2, n):
            for start in range(n - length + 1):
                sub_links.add('-'.join(nodes[start:start + length]))
        return sub_links

    def reverse_link(link_pattern):
        return '-'.join(reversed(link_pattern.split('-')))

    def expand_patterns(patterns):
        current_set = set(patterns)
        all_links = set(current_set)
        while True:
            generated = set()
            for link in current_set:
                if len(link.split('-')) > 2:
                    generated.update(generate_sub_links(link))
            new_found = generated - all_links
            if not new_found:
                break
            all_links.update(new_found)
            current_set = all_links
        return all_links

    def add_reverse_links(patterns):
        result = set(patterns)
        for link in patterns:
            result.add(reverse_link(link))
        return result

    step1 = expand_patterns(original_patterns)
    step2 = add_reverse_links(step1)
    step3 = expand_patterns(step2)
    step4 = add_reverse_links(step3)
    return step4


class ShapeRuleMatcher:
    """Shape rule matcher."""

    def __init__(self):
        self.valid_patterns = generate_complete_patterns(PATTERN_CONFIG['original_patterns'])
        self.pattern_set = set(self.valid_patterns)
        self.trie = self._build_trie()
        self._valid_cache = {}
        self._valid_lengths = {len(p.split('-')) for p in self.valid_patterns}

    def _build_trie(self):
        trie = {}
        for pattern in self.valid_patterns:
            node = trie
            for shape in pattern.split('-'):
                node = node.setdefault(shape, {})
            node['#'] = True
        return trie

    def is_valid_shape(self, shape_sequence):
        if not shape_sequence:
            return False
        cached = self._valid_cache.get(shape_sequence)
        if cached is not None:
            return cached
        ok = shape_sequence in self.pattern_set
        self._valid_cache[shape_sequence] = ok
        return ok

    def get_valid_subpaths(self, shape_sequence):
        shapes = shape_sequence.split('-')
        n = len(shapes)
        valid_subpaths = set()
        for i in range(n):
            for j in range(i + 1, n + 1):
                if (j - i) not in self._valid_lengths:
                    continue
                sub_sequence = '-'.join(shapes[i:j])
                if self.is_valid_shape(sub_sequence):
                    valid_subpaths.add((i, j - 1))
        return list(valid_subpaths)

    def optimal_division(self, shape_sequence):
        if not shape_sequence:
            return []
        shapes = shape_sequence.split('-')
        n = len(shapes)
        dp = [(-1, []) for _ in range(n + 1)]
        dp[0] = (0, [])

        for i in range(n):
            if dp[i][0] >= 0:
                for j in range(i + 1, n + 1):
                    if (j - i) not in self._valid_lengths:
                        continue
                    sub_sequence = '-'.join(shapes[i:j])
                    if self.is_valid_shape(sub_sequence):
                        total_length = dp[i][0] + (j - i)
                        if total_length > dp[j][0]:
                            dp[j] = (total_length, dp[i][1] + [(i, j - 1)])
        return dp[n][1] if dp[n][0] > 0 else []

    def get_matched_pattern(self, shape_sequence):
        if not shape_sequence:
            return False, None
        return (True, shape_sequence) if shape_sequence in self.pattern_set else (False, None)

    def get_max_match_subpaths(self, shape_sequence):
        if not shape_sequence:
            return []
        shapes = shape_sequence.split('-')
        n = len(shapes)
        valid_intervals = []
        for i in range(n):
            for j in range(i + 1, n + 1):
                if (j - i) not in self._valid_lengths:
                    continue
                sub_sequence = '-'.join(shapes[i:j])
                if self.is_valid_shape(sub_sequence):
                    valid_intervals.append((i, j - 1))

        valid_intervals.sort(key=lambda x: (x[1] - x[0]), reverse=True)
        selected = []
        used = set()
        for start, end in valid_intervals:
            if any(idx in used for idx in range(start, end + 1)):
                continue
            selected.append((start, end))
            used.update(range(start, end + 1))
        selected.sort(key=lambda x: x[0])
        return selected

    def optimal_division_or_extract(self, shape_sequence):
        perfect_division = self.optimal_division(shape_sequence)
        if perfect_division:
            shapes = shape_sequence.split('-')
            covered = set()
            for start, end in perfect_division:
                covered.update(range(start, end + 1))
            if len(covered) == len(shapes):
                return perfect_division, True
        return self.get_max_match_subpaths(shape_sequence), False


class ShapeValidator:
    """Shape validator and separator splitter."""

    def __init__(self):
        matcher = ShapeRuleMatcher()
        self.allowed_shapes = set()
        for pattern in matcher.valid_patterns:
            self.allowed_shapes.update(pattern.split('-'))
        self.separator_shapes = {'R'}

    def is_allowed_shape(self, shape):
        return shape in self.allowed_shapes

    def is_separator(self, shape):
        return shape in self.separator_shapes or not self.is_allowed_shape(shape)

    def split_by_separators(self, shape_sequence, node_sequence=None):
        shapes = shape_sequence.split('-')
        nodes = node_sequence if node_sequence else [f'node_{i}' for i in range(len(shapes))]
        sub_sequences, current_shapes, current_nodes = [], [], []

        for i, shape in enumerate(shapes):
            if self.is_separator(shape):
                if current_shapes:
                    sub_sequences.append({'shape_sequence': '-'.join(current_shapes), 'node_sequence': current_nodes, 'separator_before': shape, 'separator_after': None})
                    current_shapes, current_nodes = [], []
                sub_sequences.append({'shape_sequence': shape, 'node_sequence': [nodes[i]], 'is_separator': True, 'separator_shape': shape})
            else:
                current_shapes.append(shape)
                current_nodes.append(nodes[i])

        if current_shapes:
            sub_sequences.append({'shape_sequence': '-'.join(current_shapes), 'node_sequence': current_nodes, 'separator_before': None, 'separator_after': None})
        return sub_sequences


class PLengthValidator:
    """P shape length validator."""

    def __init__(self, max_p_length=12):
        self.max_p_length = max_p_length

    def _build_p_length_map(self, df_group):
        node_to_length = {}
        for _, row in df_group.iterrows():
            code1 = row.get(COLUMNS['material_unique_1'])
            material_code1 = row.get(COLUMNS['material_no_1'], '')
            quantity1 = row.get(COLUMNS['qty_1'], 0)
            if pd.notna(code1) and pd.notna(material_code1) and str(material_code1).strip() == 'P':
                try:
                    node_to_length[str(code1).strip()] = float(quantity1) if pd.notna(quantity1) else 0
                except (ValueError, TypeError):
                    node_to_length[str(code1).strip()] = 0

            code2 = row.get(COLUMNS['material_unique_2'])
            material_code2 = row.get(COLUMNS['material_no_2'], '')
            quantity2 = row.get(COLUMNS['qty_2'], 0)
            if pd.notna(code2) and pd.notna(material_code2) and str(material_code2).strip() == 'P':
                try:
                    node_to_length[str(code2).strip()] = float(quantity2) if pd.notna(quantity2) else 0
                except (ValueError, TypeError):
                    node_to_length[str(code2).strip()] = 0
        return node_to_length

    def get_p_lengths_from_shapes_and_nodes(self, shapes_list, path_nodes, df_group):
        node_to_length = self._build_p_length_map(df_group)
        p_lengths, p_details = [], {}
        for i, (shape, node) in enumerate(zip(shapes_list, path_nodes)):
            if shape == 'P' and node in node_to_length:
                length = node_to_length[node]
                p_lengths.append(length)
                p_details[i] = {'node': node, 'shape': shape, 'length': length, 'index': i}
            else:
                p_lengths.append(0)
        return p_lengths, p_details

    def calculate_total_p_length(self, shapes_list, path_nodes, df_group):
        _, p_details = self.get_p_lengths_from_shapes_and_nodes(shapes_list, path_nodes, df_group)
        return sum(info['length'] for info in p_details.values()), p_details

    def is_within_limit(self, shapes_list, path_nodes, df_group):
        total_length, p_details = self.calculate_total_p_length(shapes_list, path_nodes, df_group)
        return total_length <= self.max_p_length, total_length, p_details

    def split_by_p_length(self, shapes_list, path_nodes, p_details, df_group):
        if not p_details:
            return [{'nodes': path_nodes, 'shapes': shapes_list, 'start_idx': 0, 'end_idx': len(path_nodes) - 1, 'total_p_length': 0}]

        sorted_p_indices = sorted(p_details.keys())
        sub_paths, current_start, current_p_length = [], 0, 0

        for p_idx in sorted_p_indices:
            p_len = p_details[p_idx]['length']
            if current_p_length + p_len > self.max_p_length and current_p_length > 0:
                split_end = p_idx
                if split_end > current_start:
                    sub_paths.append({'nodes': path_nodes[current_start:split_end], 'shapes': shapes_list[current_start:split_end], 'start_idx': current_start, 'end_idx': split_end - 1, 'total_p_length': current_p_length})
                current_start, current_p_length = p_idx, p_len
            else:
                current_p_length += p_len

        if current_start < len(path_nodes):
            sub_paths.append({'nodes': path_nodes[current_start:], 'shapes': shapes_list[current_start:], 'start_idx': current_start, 'end_idx': len(path_nodes) - 1, 'total_p_length': current_p_length})
        return sub_paths

