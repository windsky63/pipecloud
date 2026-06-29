import os
import re
import math
from pathlib import Path
import pandas as pd
import networkx as nx
import plotly.graph_objects as go

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_FILE_DIR = BACKEND_DIR / 'file' / 'parser'

# --- Utility Functions ---

def safe_float(s):
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0

_IDF_NUMBER_RE = re.compile(r'[+-]?\d+(?:\.\d+)?')

def parse_idf_component_line(line):
    """Parses an IDF component record into 14 logical columns."""
    segments = line.split(',')

    if len(segments) < 5:
        parts = line.split()
        if len(parts) >= 14:
            return parts[:14]
        raise ValueError(f"Unable to parse IDF component line: {line}")

    tail_parts = segments[-1].split()
    if len(tail_parts) != 2:
        raise ValueError(f"Unable to parse columns 13/14 from IDF component line: {line}")

    col12 = segments[-2].strip()
    col11 = segments[-3].strip()
    col10 = segments[-4].strip()

    left_with_col9 = ','.join(segments[:-4]).rstrip(' ,')
    col9_match = re.search(r'(\S+)\s*$', left_with_col9)
    if not col9_match:
        raise ValueError(f"Unable to parse column 9 from IDF component line: {line}")

    col9 = col9_match.group(1).strip().strip(',')
    left = left_with_col9[:col9_match.start()].rstrip()
    first_numbers = _IDF_NUMBER_RE.findall(left)
    if len(first_numbers) < 7:
        raise ValueError(f"Unable to parse leading columns from IDF component line: {line}")

    first8 = first_numbers[:8] if len(first_numbers) >= 8 else first_numbers[:7] + ['']
    return first8 + [col9, col10, col11, col12] + tail_parts

def read_file_with_fallback_encodings(file_path):
    """Reads a file trying common encodings."""
    for encoding in ['utf-8', 'gbk', 'ISO-8859-1']:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.readlines()
        except UnicodeDecodeError:
            continue
    print(f"Could not read file {file_path} with any of the attempted encodings.")
    return None

def adjust_material_description(description):
    """Cleans up raw material description strings AFTER decoding."""
    replacements = {
        'REDUCERASTM': 'REDUCER ASTM', 'ONEEND': 'ONE END', 'SWAGED': 'SW AGED',
        'ASTMA': 'ASTM A', 'SW AGED': 'SWAGED', 'DA SW': 'DASW', '5STD': '5 STD',
        'A234G': 'A234 G', 'A403G': 'A403 G', 'X SCH': 'XSCH', 'SCH X': 'SCHX',
        '321SW': '321 SW', '304SW': '304 SW', '9STD': '9 STD', 'TUDEDOUBLE': 'TUDE DOUBLE',
        'NECKFLANGE': 'NECK FLANGE', 'A105SW': 'A105 SW', 'A403WP': 'A403 WP',
        'GALVANIZEDNPT': 'GALVANIZED NPT', 'A182F': 'A182 F', 'B36. 19': 'B36.19',
        ' / ': '/', 'FLANGESTL': 'FLANGE STL'
    }
    for old, new in replacements.items():
        description = description.replace(old, new)
    return description

# --- Chinese Decoding Functions (Integrated from decode_material.py) ---

ignore_sequences = {'OS&Y'}

def decode_gb2312_from_ascii(text):
    result = []
    i = 0
    while i < len(text):
        char = text[i]
        ascii_code = ord(char)
        if 32 <= ascii_code <= 126 and i + 1 < len(text):
            next_char = text[i + 1]
            next_ascii = ord(next_char)
            if 32 <= next_ascii <= 126:
                try:
                    gb_byte1 = ascii_code + 0x80
                    gb_byte2 = next_ascii + 0x80
                    if 0xA1 <= gb_byte1 <= 0xFE and 0xA1 <= gb_byte2 <= 0xFE:
                        gb_bytes = bytes([gb_byte1, gb_byte2])
                        chinese_char = gb_bytes.decode('gb2312', errors='ignore')
                        if chinese_char:
                            result.append(chinese_char)
                            i += 2
                            continue
                except:
                    pass
        result.append(char)
        i += 1
    return ''.join(result)

def clean_decoded_text(text):
    if text.startswith('&~'):
        text = text[2:]
    if text.endswith(' &'):
        text = text[:-2]
    elif text.endswith('&'):
        text = text[:-1]
    return text.strip()

def find_encoded_blocks(s: str) -> list[str]:
    blocks = []
    end_of_search_area = len(s)
    while True:
        valid_end_pos = -1
        temp_search_end = end_of_search_area
        while True:
            candidate_end = s.rfind('&', 0, temp_search_end)
            if candidate_end == -1: break
            is_ignored = False
            for seq in ignore_sequences:
                try:
                    amp_index_in_seq = seq.index('&')
                    check_start = candidate_end - amp_index_in_seq
                    if check_start >= 0 and s[check_start : check_start + len(seq)] == seq:
                        is_ignored = True
                        break
                except ValueError: continue
            if not is_ignored:
                valid_end_pos = candidate_end
                break
            else:
                temp_search_end = candidate_end
        if valid_end_pos == -1: break
        start_pos = s.rfind('&~', 0, valid_end_pos)
        if start_pos != -1:
            block = s[start_pos : valid_end_pos + 1]
            blocks.insert(0, block)
            end_of_search_area = start_pos
        else:
            end_of_search_area = valid_end_pos
    return blocks

def process_material_description(material):
    if not material: return material
    patterns = find_encoded_blocks(material)
    decoded_parts = [{'original': p, 'decoded': decode_gb2312_from_ascii(p)} for p in patterns]
    reconstructed = material
    for part in sorted(decoded_parts, key=lambda x: len(x['original']), reverse=True):
        if part['decoded'] != part['original']:
            reconstructed = reconstructed.replace(part['original'], clean_decoded_text(part['decoded']))
    return reconstructed

# --- Parsing Functions ---

def parse_material_definitions(lines):
    """Parses all -20/-21 blocks, decodes them, and returns an ordered list."""
    materials = []
    i = 0
    while i < len(lines):
        line_lstrip = lines[i].lstrip()
        # An identifier must be followed by a space to be valid (e.g., "-20 ").
        if line_lstrip.startswith("-20 "):
            # Content starts after '-20 ' (4 chars)
            raw_code = line_lstrip[4:].strip()

            # --- Robustness Check ---
            if not raw_code:
                i += 1
                continue

            i += 1
            # Continuation lines must also be specific (e.g., "-1 ").
            while i < len(lines) and lines[i].lstrip().startswith("-1 "):
                raw_code += lines[i].lstrip()[3:].strip()
                i += 1
            
            raw_description = "N/A"
            if i < len(lines) and lines[i].lstrip().startswith("-21 "):
                desc = lines[i].lstrip()[4:].strip()
                i += 1
                while i < len(lines) and lines[i].lstrip().startswith("-1 "):
                    desc += lines[i].lstrip()[3:].strip()
                    i += 1
                raw_description = desc
            
            final_description = adjust_material_description(process_material_description(raw_description))
            materials.append({'code': raw_code, 'description': final_description})
        else:
            i += 1
    return materials

def parse_pipeline_info(lines):
    """Parses pipeline information from header lines."""
    pipeline_info = {"name": "UNKNOWN"}
    for line_idx, line in enumerate(lines):
        # lstrip to handle leading whitespace, check for '-6 ' specifically.
        line_lstrip = line.lstrip()
        # An identifier must be followed by a space to be valid.
        if line_lstrip.startswith('-6 '):
            # Name starts after the '-6 ' identifier (3 chars)
            raw_pipeline_name = line_lstrip[3:].strip()
            
            # Use a while loop to handle names that span multiple continuation lines.
            current_idx = line_idx + 1
            while current_idx < len(lines) and lines[current_idx].lstrip().startswith('-1 '):
                # Append the rest of the name from the continuation line
                raw_pipeline_name += lines[current_idx].lstrip()[3:].strip()
                current_idx += 1
            
            # Decode any potential Chinese characters in the pipeline name string.
            pipeline_info["name"] = process_material_description(raw_pipeline_name)
                
            break # Found the pipeline name header, no need to continue scanning the file
    return pipeline_info

def parse_components(lines):
    """
    Parses all components from the geometry section.
    Returns a list of all component dictionaries found.
    """
    all_components = []
    in_geometry_section = False
    pipe_opening_weld_skeys = {'TESO', 'TERF', 'TSSO', 'TSRF'}
    
    for i, line in enumerate(lines):
        # We use lstrip to handle potential indentation.
        line_lstrip = line.lstrip()

        # An identifier must be followed by a space to be valid (e.g., "-20 ").
        if in_geometry_section and line_lstrip.startswith('-20 '):
            in_geometry_section = False
        # The geometry section begins with a line starting with '-6 '
        elif line_lstrip.startswith('-6 '):
            in_geometry_section = True
        
        if not in_geometry_section:
            continue

        # Parse the component into 14 logical IDF columns.
        try:
            parts = parse_idf_component_line(line_lstrip)
        except ValueError:
            continue

        # This block needs to be robust. A failure to parse non-critical info
        # like SKEY should not prevent the whole component from being processed.
        try:
            identifier = int(parts[0])
            # Skip non-component lines that might be in the geometry section
            if identifier <= 0:
                continue

            start_coord = tuple(round(safe_float(c), 3) for c in parts[1:4])
            end_coord = tuple(round(safe_float(c), 3) for c in parts[4:7])
            
            # A component is only "geometric" if it has distinct start/end coordinates
            is_geometric = start_coord != (0.0, 0.0, 0.0) or end_coord != (0.0, 0.0, 0.0)
            if not is_geometric:
                start_coord, end_coord = None, None

            spec = parts[7]
            material_index = int(parts[8].split(',')[0])

        except (ValueError, IndexError):
            # This line does not match the expected component format.
            continue

        # --- Robust SKEY Parsing (v2) ---
        # This logic is designed to find the SKEY even if it's embedded within a
        # comma-separated string in one of the columns (e.g., "0,FLSO,").
        skey = None
        skey_found = False
        try:
            # Search within the typical SKEY columns (10-14)
            for part in parts[9:14]:
                # 1. First, check if the part itself is a valid SKEY
                cleaned_part = part.strip(',').strip()
                if 2 <= len(cleaned_part) <= 4 and cleaned_part.isalpha() and cleaned_part.isupper():
                    skey = cleaned_part
                    skey_found = True
                    break

                # 2. If not, split the part by comma and check the sub-parts
                sub_parts = part.split(',')
                if len(sub_parts) > 1:
                    for sub_part in sub_parts:
                        cleaned_sub_part = sub_part.strip()
                        if 2 <= len(cleaned_sub_part) <= 4 and cleaned_sub_part.isalpha() and cleaned_sub_part.isupper():
                            skey = cleaned_sub_part
                            skey_found = True
                            break
                if skey_found:
                    break
        except IndexError:
            pass # SKEY remains None if parsing fails

        component = {
            'line_number': i + 1,
            'identifier': identifier,
            'start_coord': start_coord,
            'end_coord': end_coord,
            'spec': spec,
            'material_index': material_index,
            'skey': skey
        }

        # Per user request: if column 11 contains specific flags, mark for non-quantification.
        ignore_flags = {'1000000', '1100000', '1200000'}
        if len(parts) > 10 and parts[10] in ignore_flags:
            component['is_ignored'] = True
        else:
            component['is_ignored'] = False

        # Flag pipe opening weld markers so their quantity is handled later.
        # A component is such a marker if its identifier is 45/46/47 and SKEY is in this set.
        if identifier in {45, 46, 47} and skey in pipe_opening_weld_skeys:
            component['is_stub_or_marker'] = True
        else:
            component['is_stub_or_marker'] = False

        if identifier == 115:
            try:
                # For bolts, quantity is in column 11 and length in column 13.
                # These are based on user feedback and typical IDF structures.
                if len(parts) > 10:
                    bolt_quantity_str = parts[10].strip(',')
                    component['bolt_quantity'] = int(bolt_quantity_str)
                if len(parts) > 12:
                    bolt_length_str = parts[12].strip(',')
                    component['bolt_length'] = int(bolt_length_str)
            except (ValueError): # IndexError is implicitly handled by the len checks
                # If parsing fails, these fields won't be added, and downstream
                # logic will use defaults (quantity=1, spec=diameter).
                pass
        
        # Check for a following '0-line' which indicates a second spec for reducers at boundaries.
        # Some files place one or more negative records (for example -30/-1/-39) between the
        # main component line and the associated 0-line, so scan forward until the next
        # non-negative component record.
        look_ahead_idx = i + 1
        while look_ahead_idx < len(lines):
            next_line_lstrip = lines[look_ahead_idx].lstrip()
            if not next_line_lstrip:
                look_ahead_idx += 1
                continue

            next_identifier_token = next_line_lstrip.split()[0]
            if next_identifier_token.startswith('-'):
                look_ahead_idx += 1
                continue

            try:
                next_parts = parse_idf_component_line(next_line_lstrip)
                # A '0-line' has identifier 0 and material_index 0.
                if len(next_parts) >= 9 and next_identifier_token == '0' and next_parts[8] == '0':
                    zeroline_spec = safe_float(next_parts[7])
                    if zeroline_spec > 0:
                        component['zeroline_spec'] = zeroline_spec
                # Whether this positive record is a matching 0-line or a new component, stop scanning.
                break
            except (ValueError, IndexError):
                break

        all_components.append(component)
            
    return all_components

def create_topology_graph(components):
    """
    Creates a directed graph from the list of parsed components to represent pipeline flow.
    """
    # Using a DiGraph to preserve the "flow" direction from the IDF file order.
    # An edge u -> v means the component flows from coordinate u to v.
    graph = nx.DiGraph()

    for comp in components:
        # We only add geometric components to the graph for visualization
        u = comp.get('start_coord')
        v = comp.get('end_coord')
        # Filter out invalid or zero-coordinate connections
        if u and v and u != v and u != (0.0, 0.0, 0.0) and v != (0.0, 0.0, 0.0):
            graph.add_edge(u, v, data=comp)
    return graph

# --- Analysis Functions ---

def calculate_node_specs(graph):
    """Calculates the primary specification for each connection point (node) in the graph."""
    node_specs = {}
    for node in graph.nodes():
        # Logic to determine the representative spec for a node.
        # This is crucial for correctly identifying reducer specs later.
        
        # 1. Look at outgoing edges first. The largest spec of an outgoing pipe
        # usually defines the "main" run size at a branch point (like a Tee).
        out_specs = {int(safe_float(d['data']['spec'])) for _, _, d in graph.out_edges(node, data=True) if safe_float(d['data']['spec']) > 0}
        
        taken_spec_val = None
        if out_specs:
            taken_spec_val = max(out_specs)
        else:
            # 2. If there are no outgoing edges (it's an endpoint), use the incoming spec.
            in_specs = {int(safe_float(d['data']['spec'])) for _, _, d in graph.in_edges(node, data=True) if safe_float(d['data']['spec']) > 0}
            if in_specs:
                taken_spec_val = max(in_specs) # Use max in case of multiple inputs, though rare.
        
        if taken_spec_val is not None:
            node_specs[node] = taken_spec_val
            
    return node_specs

def calculate_final_specs(all_components, graph):
    """
    Performs a detailed analysis to determine the final, correct specification string
    for every component, handling special cases like reducers and tees.
    Returns a map of {line_number: final_spec_string}.
    """
    node_specs = calculate_node_specs(graph)
    final_specs_map = {}

    # Define the set of component IDs that should never be treated as reducers.
    non_reducer_ids = {100, 105, 107, 110, 115, 125}

    # --- Step 1: More robustly identify tee nodes and their calculated specs ---
    tee_nodes = {}  # Maps a tee's central node coordinate to its calculated spec string

    # Find potential tee center nodes by looking at where tee-like components meet.
    potential_tee_nodes = {}
    tee_components = [c for c in all_components if c.get('identifier') in {45, 46, 47} and c.get('start_coord')]
    
    for comp in tee_components:
        # A component's start or end point can be a tee center.
        if comp.get('start_coord'):
            potential_tee_nodes.setdefault(comp['start_coord'], []).append(comp)
        if comp.get('end_coord'):
             # Avoid double-counting if start and end are the same (point component)
            if comp['start_coord'] != comp['end_coord']:
                potential_tee_nodes.setdefault(comp['end_coord'], []).append(comp)

    for node, comps_at_node in potential_tee_nodes.items():
        # A tee must have multiple components meeting at the node.
        if len(comps_at_node) < 2 or node in tee_nodes:
            continue

        # Per user suggestion: A true tee does not have a "marker" component 
        # (where start_coord == end_coord). If one exists, it's a stub-in point
        # that should have already been processed, so we skip it here.
        if any(c.get('start_coord') == c.get('end_coord') for c in comps_at_node):
            continue

        # Collect specs of all tee-related components connected at this node
        specs = {safe_float(c['spec']) for c in comps_at_node if safe_float(c['spec']) > 0}

        if len(specs) > 1:  # More than one unique spec indicates a reducing tee
            main_spec = max(specs)
            branch_spec = min(specs)
            
            # This check handles cases like 150x100x80 crosses where we just want the main reduction.
            other_specs = {s for s in specs if s != main_spec}
            if other_specs:
                branch_spec = min(other_specs)

            if main_spec != branch_spec:
                tee_spec_str = f"{int(main_spec)}X{int(branch_spec)}"
                tee_nodes[node] = tee_spec_str

    # --- Step 1.5: Handle special stub-in reducers (e.g., ID 40/41/42) ---
    stub_in_specs = {} # Maps a branch component's line_number to its reducer spec

    # Group components by start coordinate for efficient lookup
    coords_to_comps_stub = {}
    for comp in all_components:
        if comp.get('start_coord'):
            coords_to_comps_stub.setdefault(comp['start_coord'], []).append(comp)

    # Iterate through connection points to find the specific stub-in pattern
    for node, comps_at_node in coords_to_comps_stub.items():
        # Pattern: One or more 'set-on' markers (ID 40 or 42) and one or more 'stub-in' branches (ID 41)
        markers = [c for c in comps_at_node if c.get('identifier') in {40, 42} and c.get('start_coord') == c.get('end_coord')]
        branches = [b for b in comps_at_node if b.get('identifier') == 41 and b.get('start_coord') != b.get('end_coord')]

        if markers and branches:
            # Assume all markers at a point define the same main pipe spec
            main_spec = safe_float(markers[0]['spec'])
            
            # For each branch found at this point, calculate its reducer spec
            for branch_comp in branches:
                branch_spec = safe_float(branch_comp['spec'])
                if main_spec > 0 and branch_spec > 0 and main_spec != branch_spec:
                    reducer_spec_str = f"{int(main_spec)}X{int(branch_spec)}"
                    stub_in_specs[branch_comp['line_number']] = reducer_spec_str

    # --- Step 2: Main loop to determine final spec for all components ---
    for comp in all_components:
        # For pipe opening weld marker components, always use their original spec
        # and do not attempt to calculate a reducer spec for them.
        if comp.get('is_stub_or_marker', False):
            final_specs_map[comp['line_number']] = comp['spec']
            continue

        final_spec_str = comp['spec']  # Default to original spec
        u, v = comp['start_coord'], comp['end_coord']
        identifier = comp['identifier']
        line_number = comp['line_number']

        is_handled_by_rule = False
        # Priority 1: Check for special stub-in reducers (40/41/42)
        if line_number in stub_in_specs:
            final_spec_str = stub_in_specs[line_number]
            is_handled_by_rule = True

        # Priority 2: Check for tee geometry (45/46/47)
        if not is_handled_by_rule and identifier in {45, 46, 47}:
            if u in tee_nodes:
                final_spec_str = tee_nodes[u]
                is_handled_by_rule = True
            elif v in tee_nodes:
                final_spec_str = tee_nodes[v]
                is_handled_by_rule = True
        
        # Priority 3: If not handled by a specific rule, check for a generic reducer
        if not is_handled_by_rule and identifier not in non_reducer_ids:
            is_reducer_from_graph = False
            if u and v and u in node_specs and v in node_specs:
                spec_u = node_specs[u]
                spec_v = node_specs[v]
                if spec_u != spec_v:
                    final_spec_str = f"{int(max(spec_u, spec_v))}X{int(min(spec_u, spec_v))}"
                    is_reducer_from_graph = True
            
            # Fallback for boundary reducers using the '0-line' spec.
            if not is_reducer_from_graph and 'zeroline_spec' in comp:
                own_spec = safe_float(comp['spec'])
                zeroline_spec = comp['zeroline_spec']
                if own_spec > 0 and zeroline_spec > 0 and own_spec != zeroline_spec:
                    final_spec_str = f"{int(max(own_spec, zeroline_spec))}X{int(min(own_spec, zeroline_spec))}"
        
        final_specs_map[comp['line_number']] = final_spec_str
        
    return final_specs_map


def build_component_category_map():
    """
    Component category definitions follow the ordering in isogen_info_2005.
    If one identifier appears in multiple definitions, keep the first one.
    """
    ordered_definitions = [
        ([0], "Additional Bore"),
        ([3], "Text Positioning"),
        ([30, 31], "Bend"),
        ([35, 36], "Elbow"),
        ([40, 41, 42], "Olet"),
        ([45, 46, 47], "Tee"),
        ([50, 51, 52, 53], "Cross"),
        ([55], "Reducer"),
        ([60, 61, 62], "Teed Reducer"),
        ([65], "Reducing Flange"),
        ([70, 71, 72], "Tee Bend"),
        ([75, 76], "Angle Valve"),
        ([80, 81, 82], "3 Way Valve"),
        ([85, 86, 87, 88], "4 Way Valve"),
        ([90], "Instrument Dial"),
        ([90, 93], "Instrument"),
        ([90, 91, 93], "3 Way Instrument"),
        ([90, 91, 92, 93], "4 Way Instrument"),
        ([95, 96], "Misc Component"),
        ([100], "Pipe"),
        ([101], "Fixed Length Pipe"),
        ([102], "Fixed Length Pipe Block"),
        ([103], "Variable Length Pipe Block"),
        ([104], "Gap"),
        ([105], "Flange"),
        ([106], "Lap Joint Stub End"),
        ([107], "Blind Flange"),
        ([110], "Gasket"),
        ([111], "Hygenic Connector"),
        ([112], "Hygenic Backing Nut"),
        ([113], "Hygenic Clamp"),
        ([114], "Hygenic Misc Component"),
        ([115], "Bolt"),
        ([120], "Weld"),
        ([125], "Cap"),
        ([126], "Coupling"),
        ([127], "Union"),
        ([130], "Valve"),
        ([132, 133], "Trap"),
        ([134], "Safety Disc"),
        ([136, 137], "Filter"),
        ([140], "Instrument Balloon"),
        ([150], "Pipe Support"),
        ([148], "Drawing Split Point"),
        ([149], "Location Record"),
        ([151], "Reference Dimension Primary"),
        ([152], "Reference Dimension Skewed"),
        ([153], "Referenced Item"),
        ([160], "Additional Material Item"),
        ([161], "Additional Material Item"),
        ([200], "Tapped Branch Start"),
        ([201], "Tapped Branch End"),
        ([300], "Large Coordinate Offset Metric"),
        ([301], "Large Coordinate Offset Imperial"),
        ([501], "Alternative Fitting Symbol Parameters"),
        ([502], "Alternative Fitting Symbol Definition"),
        ([999], "End of File Marker"),
    ]

    category_map = {}
    for identifiers, category in ordered_definitions:
        for identifier in identifiers:
            category_map.setdefault(identifier, category)
    return category_map


COMPONENT_CATEGORY_MAP = build_component_category_map()


def get_component_category(identifier):
    return COMPONENT_CATEGORY_MAP.get(identifier, "Unknown")


def analyze_bom(all_components, material_map, pipeline_name, filename, final_specs_map, unit_name):
    """
    Analyzes all components to produce a BOM, using pre-calculated specs.
    """
    bom_entries = []

    for comp in all_components:
        # 1. Filter out materials with index 0
        if comp['material_index'] == 0:
            continue

        # Get the final spec from the pre-calculated map
        final_spec_str = final_specs_map.get(comp['line_number'], comp['spec'])
        u, v = comp['start_coord'], comp['end_coord']
        
        # --- Quantity Calculation ---
        quantity = 1
        # Per user request: if a component is marked as ignored, its quantity should be 0.
        if comp.get('is_ignored', False):
            quantity = 0
        # Per new requirement: if component is a stub-in marker or stub, quantity is 0.
        elif comp.get('is_stub_or_marker', False):
            quantity = 0
        elif comp['identifier'] == 100 and u and v: # Pipe with coordinates
            distance = math.sqrt(sum([(a - b)**2 for a, b in zip(u, v)]))
            # Per user: original coordinate value / 100 = value in mm.
            # So, distance must be divided by (100 * 1000) to get meters.
            quantity = round(distance / 100000, 3)

        elif comp['identifier'] == 115 and 'bolt_quantity' in comp:
            quantity = comp['bolt_quantity']

        # --- Spec Formatting ---
        # Handle special formatting for bolts (ID: 115) to be M{diameter}X{length}
        if comp['identifier'] == 115 and 'bolt_length' in comp:
            bolt_diameter = safe_float(final_spec_str)
            bolt_length = safe_float(comp['bolt_length'])
            if bolt_diameter > 0 and bolt_length > 0:
                final_spec_str = f"M{int(bolt_diameter)}X{int(bolt_length)}"

        # --- Material Information ---
        # The material_index is 1-based. It's used as a key in our 1-based material_map.
        mat_info = material_map.get(comp['material_index'], {'description': 'UNKNOWN', 'code': 'UNKNOWN'})

        bom_entries.append({
            'identifier': comp['identifier'],
            '管线号': pipeline_name,
            '单元名称': unit_name,
            '文件名': filename,
            '材料描述': mat_info['description'],
            '原材料代码': mat_info['code'],
            '更改后材料代码': '', # Leave empty
            '序号': comp['material_index'],
            '规格': final_spec_str,
            'skey': comp.get('skey'), # Add SKEY to the BOM entry
            'quantity': quantity
        })

    return bom_entries

# --- Visualization Function ---

def create_and_save_3d_plot(graph, plot_filename, pipeline_name, material_map, final_specs_map):
    """
    Creates and saves an interactive 3D plot of the topology graph.
    Returns True on success, False on failure (e.g., no geometric data).
    """
    if graph.number_of_edges() == 0:
        return False

    # Pre-calculate all node specs for hover text
    node_specs = calculate_node_specs(graph)

    # 1. Create Edge Traces (Visible line and invisible hover-target)
    edge_x, edge_y, edge_z = [], [], []
    mid_x, mid_y, mid_z = [], [], []
    edge_hover_texts = []
    
    for edge in graph.edges(data=True):
        x0, y0, z0 = edge[0]
        x1, y1, z1 = edge[1]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
        edge_z.extend([z0, z1, None])
        
        # Data for the hover text on the edge.
        # Instead of a single midpoint, we create a series of interpolated points
        # along the line to make the entire segment hoverable.
        comp = edge[2]['data']
        
        # Get final calculated spec for hover text
        final_spec = final_specs_map.get(comp['line_number'], comp['spec']) # Fallback to original

        material_index = comp.get('material_index')
        mat_info = material_map.get(material_index, {'description': 'N/A', 'code': 'N/A'})

        hover_text = (f"<b>元件信息</b><br>"
                      f"行号: {comp.get('line_number', 'N/A')}<br>"
                      f"ID: {comp.get('identifier', 'N/A')}<br>"
                      f"SKEY: {comp.get('skey', 'N/A')}<br>"
                      f"规格: {final_spec}<br>"
                      f"序号: {material_index or 'N/A'}<br>"
                      f"<b>材料描述:</b> {mat_info['description']}<br>"
                      f"<b>原材料代码:</b> {mat_info['code']}")

        # Create 10 interpolated points for each edge to serve as hover targets
        num_points = 10
        for i in range(num_points + 1):
            t = i / float(num_points)
            inter_x = x0 + t * (x1 - x0)
            inter_y = y0 + t * (y1 - y0)
            inter_z = z0 + t * (z1 - z0)
            mid_x.append(inter_x)
            mid_y.append(inter_y)
            mid_z.append(inter_z)
            edge_hover_texts.append(hover_text)

    edge_trace = go.Scatter3d(x=edge_x, y=edge_y, z=edge_z, mode='lines', line=dict(color='grey', width=5), hoverinfo='none')
    # The invisible trace for hover text. Size can be smaller now that there are many points.
    edge_hover_trace = go.Scatter3d(x=mid_x, y=mid_y, z=mid_z, mode='markers', marker=dict(size=3, color='rgba(0,0,0,0)'), hoverinfo='text', text=edge_hover_texts)

    # 2. Create Node Trace
    node_x, node_y, node_z = [], [], []
    node_text = []
    for node in graph.nodes():
        x, y, z = node
        node_x.append(x)
        node_y.append(y)
        node_z.append(z)
        
        # --- Combined Hover Text Logic ---
        # 1. Get the pre-calculated representative spec for the node
        taken_spec_val = node_specs.get(node)
        specs_str = str(taken_spec_val) if taken_spec_val is not None else 'N/A'
        
        # 2. Build the full hover text string
        text = f'<b>坐标:</b> ({x}, {y}, {z})<br><b>取用规格:</b> {specs_str}<br>'
        text += '--------------------<br><b>连接元件:</b><br>'

        # 3. Append details of all connected components (both in and out)
        all_incident_edges = list(graph.in_edges(node, data=True)) + list(graph.out_edges(node, data=True))
        for _, _, data in all_incident_edges:
            comp = data['data']
            text += (f" - ID: {comp.get('identifier', 'N/A')}, "
                     f"行号: {comp.get('line_number', 'N/A')}, "
                     f"SKEY: {comp.get('skey', 'N/A')}, "
                     f"规格: {comp.get('spec', 'N/A')}, "
                     f"序号: {comp.get('material_index', 'N/A')}<br>")

        node_text.append(text)

    node_trace = go.Scatter3d(
        x=node_x, y=node_y, z=node_z,
        mode='markers',
        hoverinfo='text',
        text=node_text,
        marker=dict(
            showscale=False, 
            color='skyblue', # Per user request
            size=4,          # Per user request: smaller
            symbol='circle', 
            opacity=0.6      # Per user request: more transparent
        )
    )

    # 3. Create Figure and Save
    fig = go.Figure(data=[edge_trace, node_trace, edge_hover_trace])
    fig.update_layout(
        title=f"管线 {pipeline_name} 的三维交互拓扑图",
        scene=dict(xaxis_title='X 轴', yaxis_title='Y 轴', zaxis_title='Z 轴', aspectmode='data'),
        margin=dict(l=0, r=0, b=0, t=40),
        hoverlabel=dict(bgcolor="white", font_size=12)
    )
    fig.write_html(plot_filename)
    return True

# --- Reporting Function ---

def generate_processing_report(processing_log):
    """Generates a comprehensive Excel report on the processing status of all files."""
    output_report_file = '处理状态总览.xlsx'

    if not processing_log:
        print("\n未处理任何文件，不生成状态报告。")
        return

    print(f"\n处理完成，正在生成状态总览报告: {output_report_file}")
    
    df_report = pd.DataFrame(processing_log)
    df_report = df_report.sort_values(by=['管线号', '文件名']).reset_index(drop=True)
    
    with pd.ExcelWriter(output_report_file, engine='xlsxwriter') as writer:
        df_report.to_excel(writer, sheet_name='处理状态总览', index=False)

        # Auto-adjust columns width for better readability
        worksheet = writer.sheets['处理状态总览']
        for idx, col in enumerate(df_report):
            series = df_report[col]
            max_len = max((
                series.astype(str).map(len).max(),
                len(str(series.name))
            )) + 1
            worksheet.set_column(idx, idx, max_len)

    print(f"☑ 成功生成报告: {output_report_file}")

# --- Main Execution ---

def main():
    """Main function to process all IDF files and generate a single Excel report."""
    start_folder = os.environ.get('PIPECLOUD_PARSER_INPUT_DIR') or str(DEFAULT_FILE_DIR)
    output_folder = os.environ.get('PIPECLOUD_PARSER_OUTPUT_DIR') or start_folder
    os.makedirs(output_folder, exist_ok=True)
    output_excel_file = os.path.join(output_folder, 'IDF拓扑材料表.xlsx')
    output_graph_folder = os.path.join(output_folder, 'topology_graphs')
    generate_topology_graph = False
    generate_processing_overview = False

    if generate_topology_graph and not os.path.exists(output_graph_folder):
        os.makedirs(output_graph_folder)

    all_bom_entries = []
    processing_log = []

    for root, dirs, files in os.walk(start_folder):
        # Exclude the output graph directory from being traversed
        if generate_topology_graph and output_graph_folder in dirs:
            dirs.remove(output_graph_folder)
        
        unit_name = os.path.basename(root)
        # Sort files for consistent processing order
        for filename in sorted(files):
            # Make the check case-insensitive to include both .idf and .IDF
            if not filename.lower().endswith(".idf"):
                continue

            file_path = os.path.join(root, filename)

            # Initialize log entry first, assuming failure until proven otherwise
            log_entry = {
                '管线号': '解析失败', '文件名': filename, '图形生成': '否', 
                '材料表生成': '否', '备注': '未知错误'
            }

            lines = read_file_with_fallback_encodings(file_path)
            if not lines:
                log_entry['备注'] = '文件读取失败'
            else:
                try:
                    pipeline_info = parse_pipeline_info(lines)
                    log_entry['管线号'] = pipeline_info['name']

                    ordered_material_defs = parse_material_definitions(lines)
                    material_map = {i + 1: material for i, material in enumerate(ordered_material_defs)}
                    
                    all_components = parse_components(lines)
                    
                    # Geometry correction for complex connections is no longer needed per new requirements.
                    # all_components = preprocess_branch_connections(all_components)

                    graph = create_topology_graph(all_components)
                    final_specs_map = calculate_final_specs(all_components, graph)
                    
                    if generate_topology_graph:
                        plot_filename = os.path.join(output_graph_folder, f"{os.path.splitext(filename)[0]}.html")
                        if create_and_save_3d_plot(graph, plot_filename, pipeline_info['name'], material_map, final_specs_map):
                            log_entry['图形生成'] = '是'
                    else:
                        log_entry['图形生成'] = '关闭'

                    # Generate BOM entries but don't mark as success yet.
                    bom_for_file = analyze_bom(all_components, material_map, pipeline_info['name'], filename, final_specs_map, unit_name)
                    if bom_for_file:
                        all_bom_entries.extend(bom_for_file)
                    
                    log_entry['备注'] = '成功' # Set success message
                except Exception as e:
                    log_entry['备注'] = f"处理时发生错误: {e}"
            
            processing_log.append(log_entry)
            # A single, simple status line per file. Left-align filename for readability.
            print(f"已处理: {log_entry['文件名']:<50} | 状态: {log_entry['备注']}")

    # --- Post-processing Verification and Reporting ---

    successful_bom_files = set()
    if all_bom_entries:
        df = pd.DataFrame(all_bom_entries)
        
        grouping_keys = ['管线号', '单元名称', '文件名', '材料描述', '原材料代码', '更改后材料代码', '序号', '规格', 'skey']

        def aggregate_bom(group):
            """
            Custom aggregation function for the BOM. This version is designed to be
            compatible with future pandas changes by not operating on grouping keys.
            It calculates the final quantity and returns a Series with the new
            quantity and all related record ids, which pandas then merges with
            the grouping keys.
            """
            record_ids = "/".join(str(int(item)) for item in sorted(group['identifier'].dropna().unique()))
            
            # If any item in the group is a pipe, treat as pipe material and sum lengths.
            if (group['identifier'] == 100).any():
                quantity = group.loc[group['identifier'] == 100, 'quantity'].sum()
            # Otherwise, it's a fitting group, so sum the counts.
            else:
                quantity = group['quantity'].sum()
            
            return pd.Series({'quantity': quantity, 'record id': record_ids})
        
        # Apply the custom aggregation logic, explicitly disabling inclusion of grouping
        # keys in the applied function to align with future pandas behavior and
        # silence the DeprecationWarning. We also set dropna=False to ensure that
        # components without an SKEY (NaN) are still included in the final BOM.
        final_bom_df = df.groupby(
            grouping_keys, as_index=False, dropna=False
        ).apply(aggregate_bom, include_groups=False)
        
        # Get the set of filenames that actually made it into the final BOM
        if '文件名' in final_bom_df.columns:
            successful_bom_files = set(final_bom_df['文件名'].unique())

        final_bom_df = final_bom_df.sort_values(by=['管线号', '序号'], ascending=True)
        final_bom_df.rename(columns={'quantity': '数量'}, inplace=True)
        
        # Reorder columns and drop helper aggregation fields if they are not part of the final output.
        final_columns_order = ['管线号', '单元名称', '材料描述', '原材料代码', '规格', 'record id', 'skey', '序号', '更改后材料代码', '文件名', '数量']
        # Ensure all columns exist before trying to order them
        final_bom_df = final_bom_df.reindex(columns=final_columns_order)

        final_bom_df.to_excel(output_excel_file, index=False, sheet_name='Materials')
        print(f"\nProcessing complete. Final Bill of Materials saved to: {output_excel_file}")
    else:
        print("\n未处理任何有效的物料清单数据。")

    # Now, update the log based on the final, verified results
    for log_entry in processing_log:
        if log_entry['文件名'] in successful_bom_files:
            log_entry['材料表生成'] = '是'

    if generate_processing_overview:
        generate_processing_report(processing_log)
    else:
        print("已关闭处理概况总览输出。")

if __name__ == "__main__":
    try:
        import plotly
    except ImportError:
        print("Required library 'plotly' not found. Please run: pip install plotly")
        print("Additionally, 'xlsxwriter' is needed for report generation: pip install xlsxwriter")
    main() 
