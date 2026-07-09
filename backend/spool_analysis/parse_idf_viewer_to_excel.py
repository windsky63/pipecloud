import os
import sys
from pathlib import Path
import uuid

import pandas as pd

import idf_pipe_viewer_parser as viewer


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = BACKEND_DIR / "file" / "parser"
OUTPUT_FILE_NAME = "IDF拓扑材料表.xlsx"

MATERIAL_COLUMNS = [
    "单元号",
    "管线号",
    "材料描述",
    "材料代码",
    "规格",
    "record id",
    "skey",
    "序号",
    "数量",
    "单位",
    "不出料标识",
    "开口焊不计料",
]

WELD_COLUMNS = [
    "库序号",
    "单元号",
    "管线号",
    "焊口号",
    "公称直径",
    "寸径",
    "焊接类型",
    "材料描述1",
    "材料代码1",
    "材料唯一码1",
    "数量1",
    "单位1",
    "材料描述2",
    "材料代码2",
    "材料唯一码2",
    "数量2",
    "单位2",
    "焊点坐标",
]


def parse_input_dir(input_dir: Path, project_name: str) -> dict:
    idf_files = viewer.find_idf_files(input_dir)
    if not idf_files:
        raise FileNotFoundError(f"No .idf files found in {input_dir}")

    models = [
        viewer.apply_model_unit_context(viewer.parse_idf(path), unit_name)
        for unit_name, unit_files in viewer.group_idf_files_by_unit(input_dir)
        for path in unit_files
    ]
    viewer.apply_global_pipe_material_rules(models)
    model = viewer.merge_models(models, project_name)
    viewer.assign_material_unique_codes(model)
    return model


def write_excel(model: dict, output_path: Path) -> None:
    material_rows = viewer.build_material_table_rows(model)
    weld_rows = viewer.build_weld_table_rows(model)
    for row in weld_rows:
        row["库序号"] = f"IDF-{uuid.uuid4().hex.upper()}"

    material_df = pd.DataFrame(material_rows, columns=MATERIAL_COLUMNS)
    weld_df = pd.DataFrame(weld_rows, columns=WELD_COLUMNS)
    summary_df = pd.DataFrame([{
        "项目名称": model.get("projectName", ""),
        "管线数量": len(model.get("pipelines") or []),
        "元件数量": len(model.get("components") or []),
        "材料行数": len(material_rows),
        "焊口行数": len(weld_rows),
    }])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        material_df.to_excel(writer, sheet_name="材料表", index=False)
        weld_df.to_excel(writer, sheet_name="焊口表", index=False)
        summary_df.to_excel(writer, sheet_name="解析概况", index=False)


def write_model_to_database(model: dict) -> None:
    model_id = os.environ.get("PIPECLOUD_IDF_MODEL_ID")
    part_index = os.environ.get("PIPECLOUD_IDF_MODEL_PART_INDEX")
    if not model_id or not part_index:
        raise RuntimeError("Missing IDF model database target")

    backend_path = str(BACKEND_DIR)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

    import django

    django.setup()
    from pipecloud.services.idf_model_storage import store_idf_model_part

    store_idf_model_part(int(model_id), int(part_index), model)


def main() -> None:
    input_dir = Path(os.environ.get("PIPECLOUD_PARSER_INPUT_DIR") or DEFAULT_INPUT_DIR)
    output_dir = Path(os.environ.get("PIPECLOUD_PARSER_OUTPUT_DIR") or input_dir)
    project_name = os.environ.get("PIPECLOUD_PARSER_PROJECT_NAME") or input_dir.name or "IDF解析结果"

    viewer.set_current_parse_options(viewer.ParserOptions())
    model = parse_input_dir(input_dir, project_name)

    output_path = output_dir / OUTPUT_FILE_NAME
    write_excel(model, output_path)
    write_model_to_database(model)

    print(f"Wrote {output_path}")
    print(
        "Stored IDF model part "
        f"{os.environ.get('PIPECLOUD_IDF_MODEL_PART_INDEX')} in database"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"IDF viewer parser failed: {error}", file=sys.stderr)
        raise
