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


class InitializationWeldRow(models.Model):
    project = models.ForeignKey(Project, verbose_name='项目', on_delete=models.CASCADE)
    source_file = models.ForeignKey(DataSourceFile, verbose_name='来源文件', on_delete=models.CASCADE)
    sheet_name = models.CharField('工作表', max_length=120, blank=True)
    row_index = models.IntegerField('行号', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    library_seq = models.CharField('库序号', max_length=80, blank=True)
    creator = models.CharField('创建人(必填)', max_length=120, blank=True)
    created_time_text = models.CharField('创建时间(必填)', max_length=120, blank=True)
    data_status = models.CharField('数据状态', max_length=80, blank=True)
    custom_page_no = models.CharField('自定义页码', max_length=80, blank=True)
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
    wps_no = models.CharField('WPS号', max_length=120, blank=True)
    material = models.CharField('材质', max_length=120, blank=True)
    material_code_name = models.CharField('材质代号', max_length=120, blank=True)
    inspection_code = models.CharField('抽检代号', max_length=120, blank=True)
    weld_no_start = models.CharField('初始焊口号', max_length=120, blank=True)
    weld_no_final = models.CharField('最终焊口号', max_length=120, blank=True)
    cover_date = models.CharField('盖面日期', max_length=120, blank=True)
    weld_method = models.CharField('焊接方法', max_length=120, blank=True)
    weld_position = models.CharField('焊接位置', max_length=120, blank=True)
    root_weld = models.CharField('打底', max_length=120, blank=True)
    cover_weld = models.CharField('盖面', max_length=120, blank=True)
    original_root_weld = models.CharField('原打底', max_length=120, blank=True)
    original_cover_weld = models.CharField('原盖面', max_length=120, blank=True)
    material_mark_1 = models.CharField('材料代号1', max_length=120, blank=True)
    material_mark_2 = models.CharField('材料代号2', max_length=120, blank=True)
    heat_no_a = models.CharField('炉批号A', max_length=120, blank=True)
    heat_no_b = models.CharField('炉批号B', max_length=120, blank=True)
    material_unique_1 = models.TextField('材料唯一码1', blank=True)
    material_unique_2 = models.TextField('材料唯一码2', blank=True)
    material_code_1 = models.CharField('材料代码1', max_length=120, blank=True)
    material_code_2 = models.CharField('材料代码2', max_length=120, blank=True)
    material_paint_1 = models.CharField('材料油漆1', max_length=120, blank=True)
    material_paint_2 = models.CharField('材料油漆2', max_length=120, blank=True)
    quantity_1 = models.CharField('数量1', max_length=80, blank=True)
    quantity_2 = models.CharField('数量2', max_length=80, blank=True)
    description_1 = models.TextField('描述1', blank=True)
    description_2 = models.TextField('描述2', blank=True)
    completed_flag = models.CharField('是否完成', max_length=80, blank=True)
    priority = models.CharField('优先级', max_length=80, blank=True)
    schedule_order_no = models.CharField('排产单号', max_length=120, blank=True)
    change_order_no = models.CharField('变更单号', max_length=120, blank=True)
    change_date = models.CharField('变更日期', max_length=120, blank=True)
    change_type = models.CharField('变更类型', max_length=120, blank=True)
    drawing_page = models.CharField('图纸页次', max_length=120, blank=True)
    pressure_test_package = models.CharField('试压包号', max_length=120, blank=True)
    weld_coordinate = models.CharField('焊点坐标', max_length=255, blank=True)
    zone_info = models.CharField('分区信息', max_length=255, blank=True)
    pressure_pipe_grade = models.CharField('压力管道等级', max_length=120, blank=True)
    auto_weld_segment = models.CharField('自动焊管段', max_length=120, blank=True)
    auto_weld_joint = models.CharField('自动焊口', max_length=120, blank=True)
    revision = models.CharField('版次', max_length=80, blank=True)
    need_heat_treatment = models.CharField('是否需热处理', max_length=80, blank=True)
    fitup_date = models.CharField('组对日期', max_length=120, blank=True)
    fitter = models.CharField('组对管工', max_length=120, blank=True)
    schedule_date = models.CharField('排产日期', max_length=120, blank=True)
    is_flange_weld = models.CharField('是否法兰口', max_length=80, blank=True)
    root_weld_date = models.CharField('打底日期', max_length=120, blank=True)
    data_id = models.CharField('数据ID(不可修改)', max_length=120, blank=True)
    data_title = models.CharField('数据标题', max_length=255, blank=True)
    owner = models.CharField('拥有者(必填)', max_length=120, blank=True)
    department = models.CharField('所属部门(必填)', max_length=120, blank=True)
    required_updated_time = models.CharField('修改时间(必填)', max_length=120, blank=True)
    init_note = models.TextField('初始化备注', blank=True)

    class Meta:
        ordering = ['source_file', 'row_index']
        verbose_name = '焊口初始化数据'
        verbose_name_plural = '焊口初始化数据'


class WeldLibraryRow(models.Model):
    project = models.ForeignKey(Project, verbose_name='项目', on_delete=models.CASCADE)
    source_file = models.ForeignKey(DataSourceFile, verbose_name='来源文件', on_delete=models.CASCADE)
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
    description_1 = models.TextField('描述1', blank=True)
    description_2 = models.TextField('描述2', blank=True)
    welding_mode = models.CharField('焊接方式', max_length=120, blank=True)
    completed_flag = models.BooleanField('是否完成', default=False)
    priority = models.CharField('优先级', max_length=80, blank=True)

    class Meta:
        ordering = ['project', 'row_index']
        verbose_name = '预制焊口库'
        verbose_name_plural = '预制焊口库'


class WeldPreScheduleRow(models.Model):
    project = models.ForeignKey(Project, verbose_name='项目', on_delete=models.CASCADE)
    source_file = models.ForeignKey(DataSourceFile, verbose_name='来源文件', on_delete=models.CASCADE)
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
    description_1 = models.TextField('描述1', blank=True)
    description_2 = models.TextField('描述2', blank=True)
    welding_mode = models.CharField('焊接方式', max_length=120, blank=True)
    completed_flag = models.CharField('是否完成', max_length=80, blank=True)
    priority = models.CharField('优先级', max_length=80, blank=True)
    pre_schedule_seq = models.CharField('预排产序号', max_length=120, blank=True)
    pre_schedule_status = models.CharField('预排产状态', max_length=120, blank=True)
    pre_schedule_reason = models.TextField('不可预排产原因', blank=True)

    class Meta:
        ordering = ['project', 'row_index']
        verbose_name = '焊口预排产匹配结果'
        verbose_name_plural = '焊口预排产匹配结果'


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
    source_arrival_file = models.CharField('来源入库单文件', max_length=255, blank=True)
    arrival_date = models.CharField('入库日期', max_length=80, blank=True)
    stock_qty = models.CharField('库存数量（米）', max_length=80, blank=True)
    original_length = models.CharField('原始米数', max_length=80, blank=True)
    remaining_length = models.CharField('剩余米数', max_length=80, blank=True)
    cut_lengths = models.TextField('已切割长度列表', blank=True)
    loss_lengths = models.TextField('切割损耗列表', blank=True)
    consumed_lengths = models.TextField('实际占用长度列表', blank=True)
    heat_no = models.CharField('炉批号', max_length=120, blank=True)
    library_kind = models.CharField('材料库类型', max_length=40, default='pipe')

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
    library_kind = models.CharField('材料库类型', max_length=40, default='fitting')

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
    sheet_name = models.CharField('工作表', max_length=120, blank=True)
    row_index = models.IntegerField('行号', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    cut_order_no = models.CharField('下料排产单号', max_length=120, blank=True)
    weld_order_no = models.CharField('焊接排产单号', max_length=120, blank=True)
    cut_date = models.CharField('下料日期', max_length=120, blank=True)
    weld_date = models.CharField('焊接日期', max_length=120, blank=True)
    source_sheet = models.CharField('来源工作表', max_length=120, blank=True)
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
    completed_flag = models.CharField('是否完成', max_length=80, blank=True)
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
