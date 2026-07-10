from contextlib import contextmanager

from pipecloud.models import (
    ArrivalMaterialRow,
    ArrivalOrderRow,
    DataSourceFile,
    FittingMaterialRow,
    InitializationMaterialRow,
    InitializationWeldRow,
    InitializationWeldExtraData,
    MasterScheduleRow,
    MaterialMatchDetailRow,
    PipeMaterialRow,
    PlanRecord,
    WeldingPlanRow,
    WeldLibraryRow,
    WeldPreScheduleRow,
)


PROJECT_SCOPED_MODELS = [
    PlanRecord,
    DataSourceFile,
    InitializationWeldRow,
    InitializationWeldExtraData,
    InitializationMaterialRow,
    WeldLibraryRow,
    WeldPreScheduleRow,
    MaterialMatchDetailRow,
    PipeMaterialRow,
    FittingMaterialRow,
    ArrivalOrderRow,
    ArrivalMaterialRow,
    WeldingPlanRow,
    MasterScheduleRow,
]


def project_table_name(project_or_id, model):
    return model._meta.db_table


def project_table_names(project_or_id):
    return {model: model._meta.db_table for model in PROJECT_SCOPED_MODELS}


@contextmanager
def using_project_tables(project_or_id):
    yield project_table_names(project_or_id)


def ensure_project_tables(project_or_id):
    return project_table_names(project_or_id)


def drop_project_tables(project_or_id):
    return None
