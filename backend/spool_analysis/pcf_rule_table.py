"""PCF rule table distilled from the local 'PCF Reference Guide.pdf'.

This module separates:
1. physical/component records from Section 12 component sheets
2. information items from Section 5 / Other Information Items
3. end-connection / end-position continuation records

The goal is to make upper-area rewrite logic use a positive whitelist for
"real component blocks" instead of relying on an incomplete skip blacklist.
"""

PDF_COMPONENT_TYPES = {
    'BEND',
    'BOLT',
    'CAP',
    'CLAMP',
    'CONNECTOR',
    'COUPLING',
    'CROSS',
    'CROSS-SET-ON',
    'CROSS-STUB',
    'ELBOLET',
    'ELBOW',
    'ELBOW-REDUCING',
    'FILTER',
    'FILTER-ANGLE',
    'FILTER-OFFSET',
    'FILTER-RETURN',
    'FLANGE',
    'FLANGE-BLIND',
    'FLANGE-REDUCING-CONCENTRIC',
    'FLANGE-REDUCING-ECCENTRIC',
    'GAP',
    'GASKET',
    'INSTRUMENT',
    'INSTRUMENT-3WAY',
    'INSTRUMENT-4WAY',
    'INSTRUMENT-ANGLE',
    'INSTRUMENT-BALLOON',
    'INSTRUMENT-DIAL',
    'INSTRUMENT-EXTERNAL',
    'INSTRUMENT-OFFSET',
    'INSTRUMENT-RETURN',
    'INSTRUMENT-TEE',
    'LAPJOINT-RING',
    'LAPJOINT-STUBEND',
    'MISC-COMPONENT',
    'MISC-COMPONENT-ANGLE',
    'MISC-COMPONENT-OFFSET',
    'MISC-COMPONENT-RETURN',
    'MISC-HYGIENIC',
    'MULTI-PORT-COMPONENT',
    'NOZZLE',
    'NUT',
    'OLET',
    'PENETRATION-PLATE',
    'PIPE',
    'PIPE-BLOCK-FIXED',
    'PIPE-BLOCK-VARIABLE',
    'PIPE-FIXED',
    'REDUCER-CONCENTRIC',
    'REDUCER-CONCENTRIC-TEED',
    'REDUCER-ECCENTRIC',
    'REDUCER-ECCENTRIC-TEED',
    'REINFORCEMENT-PAD',
    'SAFETY-DISC',
    'SUPPORT',
    'TEE',
    'TEE-SET-ON',
    'TEE-STUB',
    'TRAP',
    'TRAP-ANGLE',
    'TRAP-OFFSET',
    'TRAP-RETURN',
    'UNION',
    'VALVE',
    'VALVE-3WAY',
    'VALVE-4WAY',
    'VALVE-ANGLE',
    'VALVE-MULTIWAY',
    'WELD',
    'Y-PIECE-FABRICATED',
    'Y-PIECE-FITTING',
}

# Explicit top-level information items from the guide.
PDF_INFORMATION_ITEM_TYPES = {
    'BIP-IDENTIFIER',
    'FLOW-ARROW',
    'FLOOR-SYMBOL',
    'INDUCTION-END',
    'INDUCTION-START',
    'INSULATION-SYMBOL',
    'ISO-SPLIT-POINT',
    'MESSAGE',
    'MESSAGE-CIRCLE',
    'MESSAGE-DIAMOND',
    'MESSAGE-DOUBLE-CIRCLE',
    'MESSAGE-ELLIPSE',
    'MESSAGE-POINTED',
    'MESSAGE-ROUND',
    'MESSAGE-SQUARE',
    'MESSAGE-TRIANGLE',
    'WALL-SYMBOL',
}

# Connection/termination identifiers described as information items or associated items.
PDF_CONNECTION_ITEM_TYPES = {
    'END-CONNECTION-CORE',
    'END-CONNECTION-EQUIPMENT',
    'END-CONNECTION-JACKET',
    'END-CONNECTION-PIPELINE',
    'END-POSITION-CLOSED',
    'END-POSITION-DRAIN',
    'END-POSITION-NULL',
    'END-POSITION-OPEN',
    'END-POSITION-VENT',
}

# Local project dialect noise seen in exports, not physical material instances.
PROJECT_NON_MATERIAL_TYPES = {
    'MATERIALS',
    'TEXT',
}

# Components that should never go through "missing code => delete block".
COMPONENTS_EXEMPT_FROM_CODE_REQUIREMENT = {
    'WELD',
}

PHYSICAL_COMPONENT_TYPES = PDF_COMPONENT_TYPES - COMPONENTS_EXEMPT_FROM_CODE_REQUIREMENT
NON_MATERIAL_BLOCK_TYPES = (
    PDF_INFORMATION_ITEM_TYPES
    | PDF_CONNECTION_ITEM_TYPES
    | PROJECT_NON_MATERIAL_TYPES
    | COMPONENTS_EXEMPT_FROM_CODE_REQUIREMENT
)

HEADER_FIELD_NAMES = {
    'ISOGEN-FILES',
    'UNITS-BORE',
    'UNITS-CO-ORDS',
    'UNITS-WEIGHT',
    'UNITS-BOLT-DIA',
    'UNITS-BOLT-LENGTH',
    'UNITS-BOLT-QUANTITY',
    'UNITS-PIPELENGTH',
    'PIPELINE-REFERENCE',
    'PIPING-SPEC',
    'TRACING-SPEC',
    'INSULATION-SPEC',
    'PAINTING-SPEC',
    'PROJECT-IDENTIFIER',
    'LINE-ID',
    'REVISION',
    'DATE-DMY',
    'DATE-MDY',
    'DATE-YMD',
    'MESSAGE',
}

HEADER_FIELD_PREFIXES = (
    'ATTRIBUTE',
    'ITEM-ATTRIBUTE',
    'MISC-SPEC',
    'SPOOL-ATTRIBUTE',
    'PIPELINE-ATTRIBUTE',
)


def normalize_component_type(component_type):
    return str(component_type or '').strip().upper()


def is_physical_component_type(component_type):
    return normalize_component_type(component_type) in PHYSICAL_COMPONENT_TYPES


def is_non_material_block_type(component_type):
    return normalize_component_type(component_type) in NON_MATERIAL_BLOCK_TYPES


def get_expected_code_prefix(component_type):
    return 'BOLT-ITEM-CODE' if normalize_component_type(component_type) == 'BOLT' else 'ITEM-CODE'


def is_header_field_name(name):
    normalized = normalize_component_type(name)
    if normalized in HEADER_FIELD_NAMES:
        return True
    return any(normalized.startswith(prefix) for prefix in HEADER_FIELD_PREFIXES)
