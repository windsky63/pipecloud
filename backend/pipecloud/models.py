from django.db import models


class Project(models.Model):
    project_name = models.CharField('项目名称', max_length=255)
    pipe_segment = models.CharField('可预制管段', max_length=120, blank=True)
    prefab_weld_count = models.IntegerField('可预制焊口数', default=0)
    completion_rate = models.DecimalField('完成率', max_digits=5, decimal_places=2, null=True, blank=True)
    start_date = models.DateField('开始日期', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['id']
        verbose_name = '项目'
        verbose_name_plural = '项目'
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(project_name=''),
                name='pipecloud_project_name_required',
            ),
        ]

    def __str__(self):
        return self.project_name or f'项目 {self.pk}'


class ProjectSchedulePolicy(models.Model):
    project = models.OneToOneField(
        Project,
        verbose_name='项目',
        related_name='schedule_policy',
        on_delete=models.CASCADE,
    )
    auto_rollover_enabled = models.BooleanField('启用未完成计划自动滚动', default=True)
    target_diameter = models.DecimalField('普通排产目标寸径', max_digits=10, decimal_places=2, default=260)
    rollover_max_diameter = models.DecimalField('滚动排产最大寸径', max_digits=10, decimal_places=2, default=300)
    orders_per_day = models.PositiveIntegerField('每日排产单数', default=3)
    skip_holidays = models.BooleanField('跳过节假日', default=True)
    holiday_dates = models.JSONField('节假日日期', default=list, blank=True)
    canceled_weekend_dates = models.JSONField('调休工作日', default=list, blank=True)
    cutting_lead_days = models.PositiveIntegerField('下料提前天数', default=1)
    anti_corrosion_lead_days = models.PositiveIntegerField('防腐提前天数', default=1)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '项目排产策略'
        verbose_name_plural = '项目排产策略'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(target_diameter__gt=0),
                name='pipecloud_schedule_target_diameter_positive',
            ),
            models.CheckConstraint(
                condition=models.Q(rollover_max_diameter__gte=models.F('target_diameter')),
                name='pipecloud_schedule_rollover_max_gte_target',
            ),
            models.CheckConstraint(
                condition=models.Q(orders_per_day__gt=0),
                name='pipecloud_schedule_orders_per_day_positive',
            ),
        ]

    def __str__(self):
        return f'{self.project} 排产策略'


class ProjectConstraint(models.Model):
    project = models.ForeignKey(
        Project,
        verbose_name='项目',
        related_name='business_constraints',
        on_delete=models.CASCADE,
    )
    rule_key = models.CharField('规则标识', max_length=120)
    enabled = models.BooleanField('是否启用', default=False)
    parameters = models.JSONField('规则参数', default=dict, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['project_id', 'rule_key']
        verbose_name = '项目约束'
        verbose_name_plural = '项目约束'
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'rule_key'],
                name='pipecloud_project_constraint_unique_rule',
            ),
        ]

    def __str__(self):
        return f'{self.project} - {self.rule_key}'


class ScheduledTaskRun(models.Model):
    STATUS_CHOICES = [
        ('running', '执行中'),
        ('succeeded', '成功'),
        ('failed', '失败'),
        ('skipped', '跳过'),
    ]

    project = models.ForeignKey(Project, verbose_name='项目', on_delete=models.CASCADE)
    task_name = models.CharField('任务名称', max_length=80)
    business_date = models.DateField('业务日期')
    status = models.CharField('执行状态', max_length=16, choices=STATUS_CHOICES, default='running')
    stats = models.JSONField('执行统计', default=dict, blank=True)
    error_message = models.TextField('错误信息', blank=True)
    started_at = models.DateTimeField('开始时间', auto_now_add=True)
    finished_at = models.DateTimeField('完成时间', null=True, blank=True)

    class Meta:
        ordering = ['-business_date', '-started_at']
        verbose_name = '定时任务执行记录'
        verbose_name_plural = '定时任务执行记录'
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'task_name', 'business_date'],
                name='pipecloud_scheduled_task_run_unique_day',
            ),
        ]

    def __str__(self):
        return f'{self.project} {self.task_name} {self.business_date} {self.status}'


class WeldRolloverLog(models.Model):
    project = models.ForeignKey(Project, verbose_name='项目', on_delete=models.CASCADE)
    task_run = models.ForeignKey(
        ScheduledTaskRun,
        verbose_name='任务执行记录',
        related_name='rollover_logs',
        on_delete=models.CASCADE,
    )
    weld_key = models.CharField('焊口唯一键', max_length=1000)
    weld_key_hash = models.CharField('焊口唯一键哈希', max_length=64)
    from_date = models.DateField('原计划日期')
    to_date = models.DateField('滚动后计划日期')
    diameter = models.DecimalField('寸径', max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        ordering = ['-from_date', 'to_date', 'id']
        verbose_name = '焊口滚动记录'
        verbose_name_plural = '焊口滚动记录'
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'weld_key_hash', 'from_date', 'to_date'],
                name='pipecloud_weld_rollover_unique_move',
            ),
        ]

    def __str__(self):
        return f'{self.project} {self.weld_key} {self.from_date} -> {self.to_date}'


class PlanRecord(models.Model):
    PLAN_TYPES = [
        ('anti-corrosion', '防腐'),
        ('cutting', '下料'),
        ('welding', '焊接'),
    ]

    project = models.ForeignKey(Project, verbose_name='项目', related_name='plan_records', on_delete=models.CASCADE)
    plan_key = models.CharField('计划类型', max_length=32, choices=PLAN_TYPES)
    plan_name = models.CharField('计划名称', max_length=32)
    plan_date = models.CharField('计划日期', max_length=8)
    plan_folder = models.CharField('计划文件夹', max_length=255)
    relative_path = models.CharField('相对路径', max_length=500)
    file_count = models.IntegerField('文件数量', default=0)
    folder_updated_at = models.FloatField('文件夹更新时间', default=0)
    files = models.JSONField('计划文件', default=list, blank=True)
    summary = models.JSONField('计划摘要', default=dict, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['-plan_date', '-folder_updated_at', 'plan_folder']
        verbose_name = '计划记录'
        verbose_name_plural = '计划记录'
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'plan_key', 'plan_folder'],
                name='pipecloud_plan_record_unique_folder',
            ),
        ]

    def __str__(self):
        return f'{self.project} {self.plan_name} {self.plan_folder}'


class DataSourceFile(models.Model):
    project = models.ForeignKey(Project, verbose_name='项目', related_name='data_source_files', on_delete=models.CASCADE)
    source_type = models.CharField('来源类型', max_length=64)
    source_key = models.CharField('来源键', max_length=120)
    display_name = models.CharField('显示名称', max_length=255)
    relative_path = models.CharField('相对路径', max_length=500)
    file_size = models.BigIntegerField('文件大小', default=0)
    file_updated_at = models.FloatField('文件更新时间', default=0)
    sheet_names = models.JSONField('工作表名称', default=list, blank=True)
    sheet_columns = models.JSONField('工作表列', default=dict, blank=True)
    imported_at = models.DateTimeField('导入时间', auto_now=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        ordering = ['source_type', 'source_key', 'relative_path']
        verbose_name = '数据来源文件'
        verbose_name_plural = '数据来源文件'
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'source_type', 'source_key', 'relative_path'],
                name='pipecloud_data_source_file_unique',
            ),
        ]

    def __str__(self):
        return self.display_name


class ParserJob(models.Model):
    STATUS_CHOICES = [
        ('queued', '排队中'),
        ('running', '解析中'),
        ('completed', '已完成'),
        ('failed', '失败'),
        ('canceled', '已中断'),
    ]

    job_id = models.CharField('任务ID', max_length=64, unique=True)
    project = models.ForeignKey(Project, verbose_name='项目', related_name='parser_jobs', on_delete=models.CASCADE)
    file_type = models.CharField('文件类型', max_length=16)
    status = models.CharField('状态', max_length=24, choices=STATUS_CHOICES, default='queued')
    total = models.IntegerField('子任务总数', default=0)
    completed = models.IntegerField('完成子任务数', default=0)
    failed = models.IntegerField('失败子任务数', default=0)
    percent = models.IntegerField('进度百分比', default=0)
    current = models.CharField('当前进度', max_length=255, blank=True)
    message = models.TextField('消息', blank=True)
    batch_path = models.CharField('任务目录', max_length=500, blank=True)
    input_hash = models.CharField('输入哈希', max_length=64, db_index=True)
    input_files = models.JSONField('输入文件', default=list, blank=True)
    results = models.JSONField('解析结果', default=list, blank=True)
    errors = models.JSONField('错误信息', default=list, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '解析任务'
        verbose_name_plural = '解析任务'
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'file_type', 'input_hash'],
                name='pipecloud_parser_job_unique_input',
            ),
        ]

    def __str__(self):
        return f'{self.project} {self.file_type} {self.job_id}'


class ParserSubtask(models.Model):
    STATUS_CHOICES = ParserJob.STATUS_CHOICES

    job = models.ForeignKey(ParserJob, verbose_name='解析任务', related_name='subtasks', on_delete=models.CASCADE)
    index = models.IntegerField('子任务序号')
    status = models.CharField('状态', max_length=24, choices=STATUS_CHOICES, default='queued')
    input_files = models.JSONField('输入文件', default=list, blank=True)
    file_count = models.IntegerField('文件数量', default=0)
    work_path = models.CharField('工作目录', max_length=500, blank=True)
    result_path = models.CharField('结果路径', max_length=500, blank=True)
    result_payload = models.JSONField('结果载荷', default=dict, blank=True)
    error = models.TextField('错误信息', blank=True)
    process_id = models.IntegerField('解析进程ID', null=True, blank=True)
    started_at = models.DateTimeField('开始时间', null=True, blank=True)
    finished_at = models.DateTimeField('完成时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['job', 'index']
        verbose_name = '解析子任务'
        verbose_name_plural = '解析子任务'
        constraints = [
            models.UniqueConstraint(
                fields=['job', 'index'],
                name='pipecloud_parser_subtask_unique_index',
            ),
        ]

    def __str__(self):
        return f'{self.job.job_id} #{self.index}'


class ParserArtifact(models.Model):
    project = models.ForeignKey(Project, verbose_name='项目', related_name='parser_artifacts', on_delete=models.CASCADE)
    job = models.ForeignKey(
        ParserJob,
        verbose_name='解析任务',
        related_name='artifacts',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    source = models.CharField('来源', max_length=24)
    filename = models.CharField('文件名', max_length=255)
    content = models.BinaryField('文件内容')
    file_size = models.BigIntegerField('文件大小', default=0)
    content_hash = models.CharField('内容哈希', max_length=64, db_index=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = '解析结果文件'
        verbose_name_plural = '解析结果文件'

    def __str__(self):
        return self.filename


class IdfModelVersion(models.Model):
    STATUS_CHOICES = [
        ('importing', '导入中'),
        ('ready', '可用'),
        ('failed', '失败'),
    ]

    job = models.OneToOneField(
        ParserJob,
        verbose_name='解析任务',
        related_name='idf_model',
        on_delete=models.CASCADE,
    )
    project = models.ForeignKey(
        Project,
        verbose_name='项目',
        related_name='idf_models',
        on_delete=models.CASCADE,
    )
    status = models.CharField('状态', max_length=24, choices=STATUS_CHOICES, default='importing')
    part_count = models.IntegerField('模型分片数', default=0)
    component_count = models.IntegerField('元件数量', default=0)
    weld_count = models.IntegerField('焊口数量', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-id']
        verbose_name = 'IDF模型版本'
        verbose_name_plural = 'IDF模型版本'
        indexes = [
            models.Index(fields=['project', 'status', '-updated_at'], name='pipecloud_idf_model_latest'),
        ]

    def __str__(self):
        return f'{self.project} IDF {self.job.job_id}'


class IdfModelPart(models.Model):
    model = models.ForeignKey(
        IdfModelVersion,
        verbose_name='模型版本',
        related_name='parts',
        on_delete=models.CASCADE,
    )
    subtask_index = models.IntegerField('子任务序号')
    metadata = models.JSONField('模型元数据', default=dict, blank=True)
    component_count = models.IntegerField('元件数量', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['model', 'subtask_index']
        verbose_name = 'IDF模型分片'
        verbose_name_plural = 'IDF模型分片'
        constraints = [
            models.UniqueConstraint(
                fields=['model', 'subtask_index'],
                name='pipecloud_idf_part_unique',
            ),
        ]


class IdfComponent(models.Model):
    model = models.ForeignKey(
        IdfModelVersion,
        verbose_name='模型版本',
        related_name='components',
        on_delete=models.CASCADE,
    )
    part = models.ForeignKey(
        IdfModelPart,
        verbose_name='模型分片',
        related_name='components',
        on_delete=models.CASCADE,
    )
    subtask_index = models.IntegerField('子任务序号')
    component_id = models.CharField('元件ID', max_length=255)
    component_type = models.CharField('元件类型', max_length=40, blank=True)
    pipeline_id = models.CharField('管线ID', max_length=255, blank=True)
    pipeline_name = models.CharField('管线号', max_length=255, blank=True)
    payload = models.JSONField('元件数据', default=dict)

    class Meta:
        ordering = ['model', 'subtask_index', 'id']
        verbose_name = 'IDF元件'
        verbose_name_plural = 'IDF元件'
        constraints = [
            models.UniqueConstraint(
                fields=['model', 'subtask_index', 'component_id'],
                name='pipecloud_idf_component_unique',
            ),
        ]
        indexes = [
            models.Index(
                fields=['model', 'subtask_index', 'component_id'],
                name='pipecloud_idf_component_find',
            ),
        ]


class IdfWeldLookup(models.Model):
    model = models.ForeignKey(
        IdfModelVersion,
        verbose_name='模型版本',
        related_name='weld_lookups',
        on_delete=models.CASCADE,
    )
    component = models.ForeignKey(
        IdfComponent,
        verbose_name='焊口元件',
        related_name='lookup_keys',
        on_delete=models.CASCADE,
    )
    line_key = models.CharField('标准化管线号', max_length=255)
    weld_key = models.CharField('标准化焊口号', max_length=120)

    class Meta:
        ordering = ['model', 'line_key', 'weld_key', 'id']
        verbose_name = 'IDF焊口索引'
        verbose_name_plural = 'IDF焊口索引'
        constraints = [
            models.UniqueConstraint(
                fields=['model', 'component', 'line_key', 'weld_key'],
                name='pipecloud_idf_weld_lookup_unique',
            ),
        ]
        indexes = [
            models.Index(
                fields=['model', 'line_key', 'weld_key'],
                name='pipecloud_idf_weld_find',
            ),
        ]


class WeldCommonData(models.Model):
    project = models.ForeignKey(Project, verbose_name='项目', on_delete=models.CASCADE)
    library_seq = models.CharField('库序号', max_length=120)
    wall_thickness = models.CharField('壁厚', max_length=80, blank=True)
    wall_thickness_no = models.CharField('壁厚号', max_length=80, blank=True)
    diameter = models.CharField('寸径', max_length=80, blank=True)
    outer_diameter = models.CharField('外径', max_length=80, blank=True)
    material = models.CharField('材质', max_length=120, blank=True)
    material_code_name = models.CharField('材质代号', max_length=120, blank=True)
    material_mark_1 = models.CharField('材料代号1', max_length=120, blank=True)
    material_mark_2 = models.CharField('材料代号2', max_length=120, blank=True)
    material_unique_1 = models.TextField('材料唯一码1', blank=True)
    material_unique_2 = models.TextField('材料唯一码2', blank=True)
    material_code_1 = models.CharField('材料代码1', max_length=120, blank=True)
    material_code_2 = models.CharField('材料代码2', max_length=120, blank=True)
    material_paint_1 = models.CharField('材料油漆1', max_length=120, blank=True)
    material_paint_2 = models.CharField('材料油漆2', max_length=120, blank=True)
    quantity_1 = models.CharField('数量1', max_length=80, blank=True)
    quantity_2 = models.CharField('数量2', max_length=80, blank=True)
    material_unit_1 = models.CharField('单位1', max_length=80, blank=True)
    material_unit_2 = models.CharField('单位2', max_length=80, blank=True)
    description_1 = models.TextField('描述1', blank=True)
    description_2 = models.TextField('描述2', blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['project', 'library_seq']
        verbose_name = '焊口公共数据'
        verbose_name_plural = '焊口公共数据'
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'library_seq'],
                name='pipecloud_weld_common_project_seq_unique',
            ),
        ]

    def __str__(self):
        return f'{self.project} {self.library_seq}'


class InitializationWeldRow(models.Model):
    project = models.ForeignKey(Project, verbose_name='项目', on_delete=models.CASCADE)
    source_file = models.ForeignKey(DataSourceFile, verbose_name='来源文件', on_delete=models.CASCADE)
    common_data = models.ForeignKey(
        WeldCommonData,
        verbose_name='公共数据',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='initialization_rows',
    )
    sheet_name = models.CharField('工作表', max_length=120, blank=True)
    row_index = models.IntegerField('行号', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    library_seq = models.CharField('库序号', max_length=80)
    unit = models.CharField('单元号', max_length=120, blank=True)
    pipeline = models.CharField('管线号', max_length=255, blank=True)
    segment_no = models.CharField('管段号', max_length=120, blank=True)
    joint_type = models.CharField('接头类型', max_length=120, blank=True)
    wall_thickness = models.CharField('壁厚', max_length=80, blank=True)
    nominal_diameter = models.CharField('公称直径', max_length=120, blank=True)
    diameter = models.CharField('寸径', max_length=80, blank=True)
    outer_diameter = models.CharField('外径', max_length=80, blank=True)
    weld_area = models.CharField('焊接区域', max_length=120, blank=True)
    weld_no_start = models.CharField('初始焊口号', max_length=120, blank=True)
    weld_no_final = models.CharField('最终焊口号', max_length=120, blank=True)
    material = models.CharField('材质', max_length=120, blank=True)
    material_type = models.CharField('材质代号', max_length=120, blank=True)
    material_mark_1 = models.CharField('材料代号1', max_length=120, blank=True)
    material_mark_2 = models.CharField('材料代号2', max_length=120, blank=True)
    material_code_1 = models.CharField('材料代码1', max_length=120, blank=True)
    material_code_2 = models.CharField('材料代码2', max_length=120, blank=True)
    material_paint_1 = models.CharField('材料油漆1', max_length=120, blank=True)
    material_paint_2 = models.CharField('材料油漆2', max_length=120, blank=True)
    description_1 = models.TextField('描述1', blank=True)
    description_2 = models.TextField('描述2', blank=True)
    material_unique_1 = models.TextField('材料唯一码1', blank=True)
    material_unique_2 = models.TextField('材料唯一码2', blank=True)
    quantity_1 = models.CharField('数量1', max_length=80, blank=True)
    quantity_2 = models.CharField('数量2', max_length=80, blank=True)
    material_unit_1 = models.CharField('单位1', max_length=80, blank=True)
    material_unit_2 = models.CharField('单位2', max_length=80, blank=True)
    weld_coordinate = models.CharField('焊点坐标', max_length=255, blank=True)

    class Meta:
        ordering = ['source_file', 'row_index']
        verbose_name = '焊口初始化数据'
        verbose_name_plural = '焊口初始化数据'
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'library_seq'],
                name='pipecloud_init_weld_project_seq_unique',
            ),
        ]
        indexes = [
            models.Index(
                fields=['project', 'pipeline', 'segment_no'],
                name='pipecloud_init_weld_find',
            ),
        ]


class InitializationWeldExtraData(models.Model):
    project = models.ForeignKey(
        Project,
        verbose_name='项目',
        on_delete=models.CASCADE,
        related_name='initialization_weld_extra_rows',
    )
    weld = models.OneToOneField(
        InitializationWeldRow,
        verbose_name='焊口',
        on_delete=models.CASCADE,
        related_name='extra_data',
    )
    library_seq = models.CharField('库序号', max_length=80)
    custom_fields = models.JSONField('自定义字段', default=dict, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['project', 'weld']
        verbose_name = '焊口初始化扩展数据'
        verbose_name_plural = '焊口初始化扩展数据'
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'library_seq'],
                name='pipecloud_init_extra_project_seq_unique',
            ),
        ]


class InitializationMaterialRow(models.Model):
    project = models.ForeignKey(Project, verbose_name='项目', on_delete=models.CASCADE)
    source_file = models.ForeignKey(DataSourceFile, verbose_name='来源文件', on_delete=models.CASCADE)
    sheet_name = models.CharField('工作表', max_length=120, blank=True)
    row_index = models.IntegerField('行号', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    unit = models.CharField('单元号', max_length=120, blank=True)
    pipeline = models.CharField('管线号', max_length=255, blank=True)
    material_description = models.TextField('材料描述', blank=True)
    material_code = models.CharField('材料代码', max_length=120, blank=True)
    specification = models.CharField('规格', max_length=255, blank=True)
    record_id = models.TextField('record id', blank=True)
    skey = models.CharField('skey', max_length=120, blank=True)
    material_seq = models.CharField('序号', max_length=80, blank=True)
    quantity = models.CharField('数量', max_length=80, blank=True)
    unit_name = models.CharField('单位', max_length=80, blank=True)
    no_material_flag = models.CharField('不出料标识', max_length=80, blank=True)
    opening_weld_no_material = models.CharField('开口焊不计料', max_length=80, blank=True)

    class Meta:
        ordering = ['source_file', 'row_index']
        verbose_name = 'IDF解析材料'
        verbose_name_plural = 'IDF解析材料'
        indexes = [
            models.Index(
                fields=['project', 'material_code'],
                name='pipecloud_init_material_code',
            ),
        ]


class WeldLibraryRow(models.Model):
    project = models.ForeignKey(Project, verbose_name='项目', on_delete=models.CASCADE)
    source_file = models.ForeignKey(DataSourceFile, verbose_name='来源文件', on_delete=models.CASCADE)
    common_data = models.ForeignKey(
        WeldCommonData,
        verbose_name='公共数据',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='weld_library_rows',
    )
    sheet_name = models.CharField('工作表', max_length=120, blank=True)
    row_index = models.IntegerField('行号', default=0)
    library_seq = models.CharField('库序号', max_length=80, blank=True)
    unit = models.CharField('单元号', max_length=120, blank=True)
    unit_name = models.CharField('单元名称', max_length=255, blank=True)
    pipeline = models.CharField('管线号', max_length=255, blank=True)
    segment_no = models.CharField('管段号', max_length=120, blank=True)
    joint_type = models.CharField('接头类型', max_length=120, blank=True)
    wall_thickness = models.CharField('壁厚', max_length=80, blank=True)
    wall_thickness_no = models.CharField('壁厚号', max_length=80, blank=True)
    diameter = models.CharField('寸径', max_length=80, blank=True)
    outer_diameter = models.CharField('外径', max_length=80, blank=True)
    weld_area = models.CharField('焊接区域', max_length=120, blank=True)
    material = models.CharField('材质', max_length=120, blank=True)
    material_code_name = models.CharField('材质代号', max_length=120, blank=True)
    weld_no_start = models.CharField('初始焊口号', max_length=120, blank=True)
    weld_no_final = models.CharField('最终焊口号', max_length=120, blank=True)
    material_mark_1 = models.CharField('材料代号1', max_length=120, blank=True)
    material_mark_2 = models.CharField('材料代号2', max_length=120, blank=True)
    material_unique_1 = models.TextField('材料唯一码1', blank=True)
    material_unique_2 = models.TextField('材料唯一码2', blank=True)
    material_code_1 = models.CharField('材料代码1', max_length=120, blank=True)
    material_code_2 = models.CharField('材料代码2', max_length=120, blank=True)
    material_paint_1 = models.CharField('材料油漆1', max_length=120, blank=True)
    material_paint_2 = models.CharField('材料油漆2', max_length=120, blank=True)
    quantity_1 = models.CharField('数量1', max_length=80, blank=True)
    quantity_2 = models.CharField('数量2', max_length=80, blank=True)
    material_unit_1 = models.CharField('单位1', max_length=80, blank=True)
    material_unit_2 = models.CharField('单位2', max_length=80, blank=True)
    description_1 = models.TextField('描述1', blank=True)
    description_2 = models.TextField('描述2', blank=True)
    welding_mode = models.CharField('焊接方式', max_length=120, blank=True)
    material_arrival_status = models.BooleanField('材料到货状态', default=False)
    material_anti_corrosion_status = models.BooleanField('材料防腐状态', default=False)
    material_cutting_status = models.BooleanField('材料下料状态', default=False)
    completed_flag = models.BooleanField('材料焊接状态', default=False)
    priority = models.CharField('优先级', max_length=80, blank=True)

    class Meta:
        ordering = ['project', 'row_index']
        verbose_name = '预制焊口库'
        verbose_name_plural = '预制焊口库'


class WeldPreScheduleRow(models.Model):
    project = models.ForeignKey(Project, verbose_name='项目', on_delete=models.CASCADE)
    source_file = models.ForeignKey(DataSourceFile, verbose_name='来源文件', on_delete=models.CASCADE)
    common_data = models.ForeignKey(
        WeldCommonData,
        verbose_name='公共数据',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='pre_schedule_rows',
    )
    sheet_name = models.CharField('工作表', max_length=120, blank=True)
    row_index = models.IntegerField('行号', default=0)
    library_seq = models.CharField('库序号', max_length=80, blank=True)
    unit = models.CharField('单元号', max_length=120, blank=True)
    unit_name = models.CharField('单元名称', max_length=255, blank=True)
    pipeline = models.CharField('管线号', max_length=255, blank=True)
    segment_no = models.CharField('管段号', max_length=120, blank=True)
    joint_type = models.CharField('接头类型', max_length=120, blank=True)
    wall_thickness = models.CharField('壁厚', max_length=80, blank=True)
    wall_thickness_no = models.CharField('壁厚号', max_length=80, blank=True)
    diameter = models.CharField('寸径', max_length=80, blank=True)
    outer_diameter = models.CharField('外径', max_length=80, blank=True)
    weld_area = models.CharField('焊接区域', max_length=120, blank=True)
    material = models.CharField('材质', max_length=120, blank=True)
    material_code_name = models.CharField('材质代号', max_length=120, blank=True)
    weld_no_start = models.CharField('初始焊口号', max_length=120, blank=True)
    weld_no_final = models.CharField('最终焊口号', max_length=120, blank=True)
    material_mark_1 = models.CharField('材料代号1', max_length=120, blank=True)
    material_mark_2 = models.CharField('材料代号2', max_length=120, blank=True)
    material_unique_1 = models.TextField('材料唯一码1', blank=True)
    material_unique_2 = models.TextField('材料唯一码2', blank=True)
    material_code_1 = models.CharField('材料代码1', max_length=120, blank=True)
    material_code_2 = models.CharField('材料代码2', max_length=120, blank=True)
    material_paint_1 = models.CharField('材料油漆1', max_length=120, blank=True)
    material_paint_2 = models.CharField('材料油漆2', max_length=120, blank=True)
    quantity_1 = models.CharField('数量1', max_length=80, blank=True)
    quantity_2 = models.CharField('数量2', max_length=80, blank=True)
    material_unit_1 = models.CharField('单位1', max_length=80, blank=True)
    material_unit_2 = models.CharField('单位2', max_length=80, blank=True)
    description_1 = models.TextField('描述1', blank=True)
    description_2 = models.TextField('描述2', blank=True)
    welding_mode = models.CharField('焊接方式', max_length=120, blank=True)
    material_arrival_status = models.BooleanField('材料到货状态', default=False)
    material_anti_corrosion_status = models.BooleanField('材料防腐状态', default=False)
    material_cutting_status = models.BooleanField('材料下料状态', default=False)
    completed_flag = models.BooleanField('材料焊接状态', default=False)
    priority = models.CharField('优先级', max_length=80, blank=True)
    pre_schedule_seq = models.CharField('预排产序号', max_length=120, blank=True)
    anti_corrosion_area = models.CharField('防腐面积', max_length=80, blank=True)
    anti_corrosion_order_no = models.CharField('防腐委托单号', max_length=120, blank=True)
    anti_corrosion_date = models.CharField('防腐日期', max_length=8, blank=True)
    pre_schedule_status = models.CharField('预排产状态', max_length=120, blank=True)
    pre_schedule_reason = models.TextField('不可预排产原因', blank=True)

    class Meta:
        ordering = ['project', 'row_index']
        verbose_name = '焊口预排产匹配结果'
        verbose_name_plural = '焊口预排产匹配结果'


class WeldStatusRow(models.Model):
    project = models.ForeignKey(Project, verbose_name='项目', on_delete=models.CASCADE)
    library_seq = models.CharField('库序号', max_length=120)
    priority = models.CharField('优先级', max_length=80, blank=True)
    material_arrival_status = models.BooleanField('材料到货状态', default=False)
    material_anti_corrosion_status = models.BooleanField('材料防腐状态', default=False)
    material_cutting_status = models.BooleanField('材料下料状态', default=False)
    completed_flag = models.BooleanField('材料焊接状态', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['project', 'library_seq']
        verbose_name = '焊口状态'
        verbose_name_plural = '焊口状态'
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'library_seq'],
                name='pipecloud_weld_status_project_seq_unique',
            ),
        ]


class MaterialMatchDetailRow(models.Model):
    project = models.ForeignKey(Project, verbose_name='项目', on_delete=models.CASCADE)
    source_file = models.ForeignKey(DataSourceFile, verbose_name='来源文件', on_delete=models.CASCADE)
    sheet_name = models.CharField('工作表', max_length=120, blank=True)
    row_index = models.IntegerField('行号', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    pre_schedule_seq = models.CharField('预排产序号', max_length=120, blank=True)
    library_seq = models.CharField('库序号', max_length=120, blank=True)
    priority = models.CharField('优先级', max_length=80, blank=True)
    unit = models.CharField('单元号', max_length=120, blank=True)
    pipeline = models.CharField('管线号', max_length=255, blank=True)
    segment_no = models.CharField('管段号', max_length=120, blank=True)
    weld_no_start = models.CharField('初始焊口号', max_length=120, blank=True)
    weld_no_final = models.CharField('最终焊口号', max_length=120, blank=True)
    material_type = models.CharField('材料类型', max_length=120, blank=True)
    material_code = models.CharField('材料代码', max_length=120, blank=True)
    material_unique = models.TextField('材料唯一码', blank=True)
    required_qty = models.CharField('需求数量', max_length=80, blank=True)
    matched_qty = models.CharField('匹配数量', max_length=80, blank=True)
    shortage_qty = models.CharField('缺料数量', max_length=80, blank=True)
    matched_inventory_key = models.CharField('匹配库存标识', max_length=255, blank=True)
    match_result = models.CharField('匹配结果', max_length=120, blank=True)
    match_note = models.TextField('匹配说明', blank=True)

    class Meta:
        ordering = ['project', 'row_index']
        verbose_name = '材料匹配明细'
        verbose_name_plural = '材料匹配明细'


class PipeMaterialRow(models.Model):
    project = models.ForeignKey(Project, verbose_name='项目', on_delete=models.CASCADE)
    source_file = models.ForeignKey(DataSourceFile, verbose_name='来源文件', on_delete=models.CASCADE)
    sheet_name = models.CharField('工作表', max_length=120, blank=True)
    row_index = models.IntegerField('行号', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    pipe_no = models.CharField('管子序号', max_length=120, blank=True)
    material_code = models.CharField('材料代码', max_length=120, blank=True)
    material_description = models.TextField('材料描述', blank=True)
    inspection_result = models.CharField('共检结果', max_length=120, blank=True)
    material_category = models.CharField('材料分类', max_length=120, blank=True)
    name = models.CharField('名称', max_length=120, blank=True)
    material = models.CharField('材质', max_length=120, blank=True)
    specification = models.CharField('规格', max_length=120, blank=True)
    wall_thickness = models.CharField('壁厚', max_length=80, blank=True)
    material_full_name = models.CharField('材质全称', max_length=255, blank=True)
    material_standard = models.CharField('材质标准号', max_length=120, blank=True)
    spec_wall = models.CharField('规格*壁厚', max_length=120, blank=True)
    unit = models.CharField('单位', max_length=40, blank=True)
    need_anti_corrosion = models.CharField('是否需防腐', max_length=80, blank=True)
    anti_corrosion_status = models.CharField('防腐状态', max_length=80, blank=True)
    unit_area = models.CharField('单位面积', max_length=80, blank=True)
    anti_corrosion_area = models.CharField('防腐面积', max_length=80, blank=True)
    source_arrival_file = models.CharField('来源入库单文件', max_length=255, blank=True)
    arrival_date = models.CharField('入库日期', max_length=80, blank=True)
    stock_qty = models.CharField('库存数量（米）', max_length=80, blank=True)
    anti_corrosion_stock_qty = models.CharField('防腐库存数量', max_length=80, blank=True)
    locked_qty = models.CharField('锁定数量', max_length=80, blank=True)
    coated_locked_qty = models.CharField('已防腐锁定数量', max_length=80, blank=True)
    uncoated_locked_qty = models.CharField('未防腐锁定数量', max_length=80, blank=True)
    used_qty = models.CharField('已使用数量', max_length=80, blank=True)
    original_length = models.CharField('原始米数', max_length=80, blank=True)
    remaining_length = models.CharField('剩余米数', max_length=80, blank=True)
    cut_lengths = models.TextField('已切割长度列表', blank=True)
    loss_lengths = models.TextField('切割损耗列表', blank=True)
    consumed_lengths = models.TextField('实际占用长度列表', blank=True)
    heat_no = models.CharField('炉批号', max_length=120, blank=True)
    class Meta:
        ordering = ['project', 'row_index']
        verbose_name = '管子材料库'
        verbose_name_plural = '管子材料库'


class FittingMaterialRow(models.Model):
    project = models.ForeignKey(Project, verbose_name='项目', on_delete=models.CASCADE)
    source_file = models.ForeignKey(DataSourceFile, verbose_name='来源文件', on_delete=models.CASCADE)
    sheet_name = models.CharField('工作表', max_length=120, blank=True)
    row_index = models.IntegerField('行号', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    material_code = models.CharField('材料代码', max_length=120, blank=True)
    stock_qty = models.CharField('库存数量', max_length=80, blank=True)
    anti_corrosion_stock_qty = models.CharField('防腐库存数量', max_length=80, blank=True)
    locked_qty = models.CharField('锁定数量', max_length=80, blank=True)
    coated_locked_qty = models.CharField('已防腐锁定数量', max_length=80, blank=True)
    uncoated_locked_qty = models.CharField('未防腐锁定数量', max_length=80, blank=True)
    used_qty = models.CharField('已使用数量', max_length=80, blank=True)
    source_arrival_file = models.CharField('来源入库单文件', max_length=255, blank=True)
    arrival_date = models.CharField('入库日期', max_length=80, blank=True)
    material_category = models.CharField('材料分类', max_length=120, blank=True)
    name = models.CharField('名称', max_length=120, blank=True)
    material = models.CharField('材质', max_length=120, blank=True)
    specification = models.CharField('规格', max_length=120, blank=True)
    wall_thickness = models.CharField('壁厚', max_length=80, blank=True)
    unit = models.CharField('单位', max_length=40, blank=True)
    material_description = models.TextField('材料描述', blank=True)
    material_full_name = models.CharField('材质全称', max_length=255, blank=True)
    need_anti_corrosion = models.CharField('是否需防腐', max_length=80, blank=True)
    unit_area = models.CharField('单位面积', max_length=80, blank=True)
    anti_corrosion_area = models.CharField('防腐面积', max_length=80, blank=True)
    class Meta:
        ordering = ['project', 'row_index']
        verbose_name = '管件法兰材料库'
        verbose_name_plural = '管件法兰材料库'


class ArrivalOrderRow(models.Model):
    project = models.ForeignKey(Project, verbose_name='项目', on_delete=models.CASCADE)
    source_file = models.ForeignKey(DataSourceFile, verbose_name='来源文件', on_delete=models.CASCADE)
    sheet_name = models.CharField('工作表', max_length=120, blank=True)
    row_index = models.IntegerField('行号', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    created_time_text = models.CharField('创建时间', max_length=120, blank=True)
    updated_time_text = models.CharField('修改时间', max_length=120, blank=True)
    order_no = models.CharField('入库单号', max_length=120, blank=True)
    arrival_time = models.CharField('到场时间', max_length=120, blank=True)
    supplier = models.CharField('供应商', max_length=255, blank=True)
    rfi_no = models.CharField('共检单号（RFI单号）', max_length=120, blank=True)
    unit = models.CharField('单元号', max_length=120, blank=True)
    unit_name = models.CharField('单元名称', max_length=255, blank=True)
    contract_no = models.CharField('预算号/合同号', max_length=120, blank=True)
    purchase_note = models.TextField('采购备注', blank=True)
    arrival_weight = models.CharField('到货单登记重量/吨', max_length=80, blank=True)
    shipment_date = models.CharField('发货日期', max_length=120, blank=True)
    child_row_count = models.CharField('子表处理数量', max_length=80, blank=True)
    table_name = models.CharField('表名', max_length=120, blank=True)
    category = models.CharField('分类', max_length=120, blank=True)
    certificate_scan = models.CharField('质保书扫描件', max_length=255, blank=True)

    class Meta:
        ordering = ['project', 'source_file', 'row_index']
        verbose_name = '入库单主表'
        verbose_name_plural = '入库单主表'


class ArrivalMaterialRow(models.Model):
    project = models.ForeignKey(Project, verbose_name='项目', on_delete=models.CASCADE)
    source_file = models.ForeignKey(DataSourceFile, verbose_name='来源文件', on_delete=models.CASCADE)
    sheet_name = models.CharField('工作表', max_length=120, blank=True)
    row_index = models.IntegerField('行号', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    material_code_ncc = models.CharField('材料代码（NCC文本）', max_length=120, blank=True)
    certificate_no = models.CharField('质保书编号', max_length=120, blank=True)
    heat_no = models.CharField('炉批号', max_length=120, blank=True)
    shipment_qty = models.CharField('发货数量（米/根）', max_length=80, blank=True)
    pipe_count = models.CharField('管子支数', max_length=80, blank=True)
    material_description = models.TextField('材料描述', blank=True)
    actual_arrival_qty = models.CharField('实际到货数量', max_length=80, blank=True)
    actual_arrival_count = models.CharField('实际到货支数', max_length=80, blank=True)
    inspection_result = models.CharField('共检结果', max_length=120, blank=True)
    rejected_qty = models.CharField('不合格数量', max_length=80, blank=True)
    accepted_qty = models.CharField('合格数量', max_length=80, blank=True)
    rectification_qty = models.CharField('整改数量', max_length=80, blank=True)
    issue_category = models.CharField('问题分类', max_length=120, blank=True)
    issue_description = models.TextField('问题描述', blank=True)
    note = models.TextField('备注', blank=True)
    material_category = models.CharField('材料分类', max_length=120, blank=True)
    name = models.CharField('名称', max_length=120, blank=True)
    material = models.CharField('材质', max_length=120, blank=True)
    specification = models.CharField('规格', max_length=120, blank=True)
    wall_thickness = models.CharField('壁厚', max_length=80, blank=True)
    material_full_name = models.CharField('材质全称', max_length=255, blank=True)
    material_standard = models.CharField('材质标准号', max_length=120, blank=True)
    spec_wall = models.CharField('规格*壁厚', max_length=120, blank=True)
    unit = models.CharField('单位', max_length=40, blank=True)
    need_anti_corrosion = models.CharField('是否需防腐', max_length=80, blank=True)

    class Meta:
        ordering = ['project', 'source_file', 'row_index']
        verbose_name = '入库单材料明细'
        verbose_name_plural = '入库单材料明细'


class WeldingPlanRow(models.Model):
    project = models.ForeignKey(Project, verbose_name='项目', on_delete=models.CASCADE)
    source_file = models.ForeignKey(DataSourceFile, verbose_name='来源文件', on_delete=models.CASCADE)
    common_data = models.ForeignKey(
        WeldCommonData,
        verbose_name='公共数据',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='welding_plan_rows',
    )
    sheet_name = models.CharField('工作表', max_length=120, blank=True)
    row_index = models.IntegerField('行号', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    cut_order_no = models.CharField('下料排产单号', max_length=120, blank=True)
    weld_order_no = models.CharField('焊接排产单号', max_length=120, blank=True)
    cut_date = models.CharField('下料日期', max_length=120, blank=True)
    weld_date = models.CharField('焊接日期', max_length=120, blank=True)
    source_sheet = models.CharField('来源工作表', max_length=120, blank=True)
    production_start_stage = models.CharField('生产开始阶段', max_length=32, blank=True)
    production_start_date = models.CharField('生产开始日期', max_length=8, blank=True)
    priority = models.CharField('优先级', max_length=80, blank=True)
    material_arrival_status = models.BooleanField('材料到货状态', default=False)
    material_anti_corrosion_status = models.BooleanField('材料防腐状态', default=False)
    material_cutting_status = models.BooleanField('材料下料状态', default=False)
    anti_corrosion_order_no = models.CharField('防腐委托单号', max_length=120, blank=True)
    anti_corrosion_date = models.CharField('防腐日期', max_length=8, blank=True)
    library_seq = models.CharField('库序号', max_length=120, blank=True)
    material_unique_1 = models.TextField('材料唯一码1', blank=True)
    material_unique_2 = models.TextField('材料唯一码2', blank=True)
    material_code_1 = models.CharField('材料代码1', max_length=120, blank=True)
    material_code_2 = models.CharField('材料代码2', max_length=120, blank=True)
    material_mark_1 = models.CharField('材料代号1', max_length=120, blank=True)
    material_mark_2 = models.CharField('材料代号2', max_length=120, blank=True)
    quantity_1 = models.CharField('数量1', max_length=80, blank=True)
    quantity_2 = models.CharField('数量2', max_length=80, blank=True)
    unit_name_1 = models.CharField('单位1', max_length=40, blank=True)
    unit_name_2 = models.CharField('单位2', max_length=40, blank=True)
    material_paint_1 = models.CharField('材料油漆1', max_length=120, blank=True)
    material_paint_2 = models.CharField('材料油漆2', max_length=120, blank=True)
    description_1 = models.TextField('描述1', blank=True)
    description_2 = models.TextField('描述2', blank=True)
    completed_flag = models.CharField('材料焊接状态', max_length=80, blank=True)
    unit = models.CharField('单元号', max_length=120, blank=True)
    pipeline = models.CharField('管线号', max_length=255, blank=True)
    segment_no = models.CharField('管段号', max_length=120, blank=True)
    weld_no_start = models.CharField('初始焊口号', max_length=120, blank=True)
    weld_no_final = models.CharField('最终焊口号', max_length=120, blank=True)
    diameter = models.CharField('寸径', max_length=80, blank=True)
    wall_thickness = models.CharField('壁厚', max_length=80, blank=True)
    material = models.CharField('材质', max_length=120, blank=True)
    plan_folder = models.CharField('计划文件夹', max_length=120, blank=True)
    plan_date = models.CharField('计划日期', max_length=8, blank=True)

    class Meta:
        ordering = ['project', 'source_file', 'sheet_name', 'row_index']
        verbose_name = '管段焊口表'
        verbose_name_plural = '管段焊口表'


class AntiCorrosionMaterialOrderRow(models.Model):
    project = models.ForeignKey(Project, verbose_name='项目', on_delete=models.CASCADE)
    source_file = models.ForeignKey(DataSourceFile, verbose_name='来源文件', on_delete=models.CASCADE)
    sheet_name = models.CharField('工作表', max_length=120, blank=True)
    row_index = models.IntegerField('行号', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    anti_corrosion_order_no = models.CharField('防腐委托单号', max_length=120, blank=True)
    commission_date = models.CharField('委托日期', max_length=120, blank=True)
    material_type = models.CharField('材料类型', max_length=120, blank=True)
    material_code = models.CharField('材料代码', max_length=120, blank=True)
    material_unique = models.TextField('材料唯一码', blank=True)
    commission_qty = models.DecimalField('委托数量', max_digits=20, decimal_places=4, default=0)
    weld_demand_qty = models.DecimalField('焊口需求数量', max_digits=20, decimal_places=4, default=0)
    matched_qty = models.DecimalField('匹配数量', max_digits=20, decimal_places=4, default=0)
    unit_area = models.DecimalField('单位面积', max_digits=20, decimal_places=6, default=0)
    commission_area = models.DecimalField('委托面积', max_digits=20, decimal_places=4, default=0)
    completed_area = models.DecimalField('已完成面积', max_digits=20, decimal_places=4, default=0)
    related_library_seqs = models.TextField('关联库序号', blank=True)
    related_pre_schedule_seqs = models.TextField('关联预排产序号', blank=True)
    matched_resource = models.CharField('匹配库存标识', max_length=255, blank=True)
    material_library_type = models.CharField('材料库类型', max_length=120, blank=True)
    material_description = models.TextField('材料描述', blank=True)
    unit = models.CharField('单位', max_length=40, blank=True)
    material = models.CharField('材质', max_length=120, blank=True)
    specification = models.CharField('规格', max_length=120, blank=True)
    wall_thickness = models.CharField('壁厚', max_length=80, blank=True)

    class Meta:
        ordering = ['project', 'source_file', 'sheet_name', 'row_index']
        verbose_name = '防腐材料单'
        verbose_name_plural = '防腐材料单'


class MasterScheduleRow(models.Model):
    STAGE_CHOICES = [
        ('anti-corrosion', '防腐'),
        ('cutting', '下料'),
        ('welding', '焊接'),
    ]

    project = models.ForeignKey(Project, verbose_name='项目', on_delete=models.CASCADE)
    common_data = models.ForeignKey(
        WeldCommonData,
        verbose_name='公共数据',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='master_schedule_rows',
    )
    library_seq = models.CharField('库序号', max_length=120)
    production_start_stage = models.CharField('生产开始阶段', max_length=32, choices=STAGE_CHOICES, blank=True)
    production_start_date = models.CharField('生产开始日期', max_length=8, blank=True)
    priority = models.CharField('优先级', max_length=80, blank=True)
    material_arrival_status = models.BooleanField('材料到货状态', default=False)
    material_anti_corrosion_status = models.BooleanField('材料防腐状态', default=False)
    material_cutting_status = models.BooleanField('材料下料状态', default=False)
    anti_corrosion_order_no = models.CharField('防腐委托单号', max_length=120, blank=True)
    anti_corrosion_date = models.CharField('防腐日期', max_length=8, blank=True)
    cut_order_no = models.CharField('下料排产单号', max_length=120, blank=True)
    cut_date = models.CharField('下料日期', max_length=8, blank=True)
    weld_order_no = models.CharField('焊接排产单号', max_length=120, blank=True)
    weld_date = models.CharField('焊接日期', max_length=8, blank=True)
    source_sheet = models.CharField('来源工作表', max_length=120, blank=True)
    unit = models.CharField('单元号', max_length=120, blank=True)
    pipeline = models.CharField('管线号', max_length=255, blank=True)
    segment_no = models.CharField('管段号', max_length=120, blank=True)
    weld_no_start = models.CharField('初始焊口号', max_length=120, blank=True)
    weld_no_final = models.CharField('最终焊口号', max_length=120, blank=True)
    diameter = models.CharField('寸径', max_length=80, blank=True)
    wall_thickness = models.CharField('壁厚', max_length=80, blank=True)
    material = models.CharField('材质', max_length=120, blank=True)
    completed_flag = models.BooleanField('材料焊接状态', default=False)
    stage_payload = models.JSONField('阶段计划数据', default=dict, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['project', 'library_seq']
        verbose_name = '排产计划库'
        verbose_name_plural = '排产计划库'
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'library_seq'],
                name='pipecloud_master_schedule_unique_library_seq',
            ),
        ]


class OperationLog(models.Model):
    user_name = models.CharField('用户', max_length=150, default='匿名用户')
    action = models.CharField('操作', max_length=255)
    method = models.CharField('请求方法', max_length=12)
    path = models.CharField('请求路径', max_length=500)
    project_id_value = models.PositiveBigIntegerField('项目 ID', null=True, blank=True)
    project_name = models.CharField('项目名称', max_length=255, blank=True)
    status_code = models.PositiveSmallIntegerField('响应状态码', default=200)
    succeeded = models.BooleanField('是否成功', default=True)
    detail = models.JSONField('操作详情', default=dict, blank=True)
    ip_address = models.GenericIPAddressField('IP 地址', null=True, blank=True)
    user_agent = models.TextField('用户代理', blank=True)
    created_at = models.DateTimeField('操作时间', auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = '用户操作日志'
        verbose_name_plural = '用户操作日志'
