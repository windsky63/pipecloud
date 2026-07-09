import re

from django.db import transaction
from django.db.models import Count

from pipecloud.models import (
    IdfComponent,
    IdfModelPart,
    IdfModelVersion,
    IdfWeldLookup,
)


IDF_COMPONENT_BATCH_SIZE = 1000


def scope_value_variants(value):
    text = str(value or '').strip()
    if not text:
        return set()
    compact = re.sub(r'\s+', '', text).upper()
    normalized = re.sub(r'[^0-9A-Z\u4E00-\u9FFF]+', '', compact)
    return {item for item in {compact, normalized} if item}


def weld_no_variants(value):
    text = str(value or '').strip()
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


def component_lookup_keys(component):
    line_values = scope_value_variants(
        component.get('pipelineName')
        or component.get('lineNo')
        or component.get('weldOwnerPipelineName')
    )
    weld_values = set()
    for field in ('weldNo', 'weldRawNo', 'label'):
        weld_values.update(weld_no_variants(component.get(field, '')))
    return {
        (line_value, weld_value)
        for line_value in line_values
        for weld_value in weld_values
        if line_value and weld_value
    }


@transaction.atomic
def initialize_idf_model(job):
    model, _created = IdfModelVersion.objects.update_or_create(
        job=job,
        defaults={
            'project': job.project,
            'status': 'importing',
            'part_count': 0,
            'component_count': 0,
            'weld_count': 0,
        },
    )
    model.parts.all().delete()
    return model


@transaction.atomic
def store_idf_model_part(model_id, subtask_index, payload):
    model = IdfModelVersion.objects.get(pk=model_id)
    IdfModelPart.objects.filter(model=model, subtask_index=subtask_index).delete()

    components = payload.get('components') or []
    metadata = {key: value for key, value in payload.items() if key != 'components'}
    part = IdfModelPart.objects.create(
        model=model,
        subtask_index=subtask_index,
        metadata=metadata,
        component_count=len(components),
    )

    component_rows = []
    for row_index, component in enumerate(components, start=1):
        component_id = str(component.get('id') or f'__row_{row_index}')
        component_rows.append(IdfComponent(
            model=model,
            part=part,
            subtask_index=subtask_index,
            component_id=component_id[:255],
            component_type=str(component.get('type') or '')[:40],
            pipeline_id=str(component.get('pipelineId') or '')[:255],
            pipeline_name=str(
                component.get('pipelineName')
                or component.get('lineNo')
                or component.get('weldOwnerPipelineName')
                or ''
            )[:255],
            payload=component,
        ))
    IdfComponent.objects.bulk_create(component_rows, batch_size=IDF_COMPONENT_BATCH_SIZE)

    stored_components = {
        item.component_id: item
        for item in IdfComponent.objects.filter(part=part)
    }
    lookup_rows = []
    for component in components:
        if component.get('type') != 'weld':
            continue
        component_id = str(component.get('id') or '')[:255]
        stored_component = stored_components.get(component_id)
        if not stored_component:
            continue
        for line_key, weld_key in component_lookup_keys(component):
            lookup_rows.append(IdfWeldLookup(
                model=model,
                component=stored_component,
                line_key=line_key[:255],
                weld_key=weld_key[:120],
            ))
    IdfWeldLookup.objects.bulk_create(
        lookup_rows,
        batch_size=IDF_COMPONENT_BATCH_SIZE,
        ignore_conflicts=True,
    )
    return part


@transaction.atomic
def finalize_idf_model(model_id):
    model = IdfModelVersion.objects.select_for_update().get(pk=model_id)
    counts = model.components.aggregate(component_count=Count('id'))
    model.status = 'ready'
    model.part_count = model.parts.count()
    model.component_count = counts['component_count'] or 0
    model.weld_count = model.components.filter(component_type='weld').count()
    model.save(update_fields=[
        'status',
        'part_count',
        'component_count',
        'weld_count',
        'updated_at',
    ])
    IdfModelVersion.objects.filter(project=model.project).exclude(pk=model.pk).delete()
    return model


def fail_idf_model(model_id):
    IdfModelVersion.objects.filter(pk=model_id).update(status='failed')


def idf_model_part_payload(model, subtask_index):
    part = model.parts.get(subtask_index=subtask_index)
    payload = dict(part.metadata or {})
    payload['components'] = list(
        part.components.order_by('id').values_list('payload', flat=True)
    )
    return payload


def latest_ready_idf_model(project):
    return (
        IdfModelVersion.objects
        .select_related('job')
        .filter(project=project, status='ready')
        .order_by('-updated_at', '-id')
        .first()
    )


def idf_database_file_payload(model):
    if not model:
        return None
    return {
        'name': 'IDF模型数据库',
        'path': f'database://idf-model/{model.id}',
        'exists': True,
        'jobId': model.job.job_id,
        'componentCount': model.component_count,
        'weldCount': model.weld_count,
        'updatedAt': model.updated_at.isoformat(timespec='seconds') if model.updated_at else '',
    }
