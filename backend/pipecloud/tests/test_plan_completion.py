from django.test import TestCase

from pipecloud.models import (
    AntiCorrosionMaterialOrderRow,
    DataSourceFile,
    MaterialMatchDetailRow,
    MasterScheduleRow,
    PipeMaterialRow,
    Project,
    WeldingPlanRow,
    WeldStatusRow,
)
from pipecloud.services.plan_completion import sync_project_plan_completion


class PlanCompletionSyncTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(project_name='完成同步测试项目')

    def create_anti_corrosion_material_source(self):
        return DataSourceFile.objects.create(
            project=self.project,
            source_type='plan',
            source_key='anti-corrosion:20260714:防腐材料单.xlsx',
            display_name='防腐材料单.xlsx',
            relative_path='database://plan/anti-corrosion/20260714/防腐材料单.xlsx',
            sheet_names=['Sheet1'],
            sheet_columns={'Sheet1': []},
        )

    def test_completed_anti_corrosion_material_area_sets_related_weld_status(self):
        source = self.create_anti_corrosion_material_source()
        MasterScheduleRow.objects.create(
            project=self.project,
            library_seq='W1',
            material_anti_corrosion_status=False,
        )
        AntiCorrosionMaterialOrderRow.objects.create(
            project=self.project,
            source_file=source,
            sheet_name='Sheet1',
            row_index=1,
            commission_area='12.5000',
            completed_area='12.5000',
            related_library_seqs='W1',
        )

        stats = sync_project_plan_completion(self.project, 'anti-corrosion', business_date='20260714')

        self.assertEqual(stats['completedCount'], 1)
        master = MasterScheduleRow.objects.get(project=self.project, library_seq='W1')
        self.assertIs(master.material_anti_corrosion_status, True)
        status = WeldStatusRow.objects.get(project=self.project, library_seq='W1')
        self.assertIs(status.material_anti_corrosion_status, True)

    def test_completed_anti_corrosion_material_updates_pipe_inventory_status(self):
        source = self.create_anti_corrosion_material_source()
        library_source = DataSourceFile.objects.create(
            project=self.project,
            source_type='library',
            source_key='anti-pipe-library',
            display_name='防腐管子材料库',
            relative_path='database://library/anti-pipe-library',
        )
        pipe = PipeMaterialRow.objects.create(
            project=self.project,
            source_file=library_source,
            pipe_no='P-1',
            stock_qty='12',
            locked_qty='5',
            uncoated_locked_qty='5',
            coated_locked_qty='0',
            used_qty='0',
            anti_corrosion_status='防腐未完成',
            anti_corrosion_stock_qty='0',
        )
        AntiCorrosionMaterialOrderRow.objects.create(
            project=self.project,
            source_file=source,
            material_type='管子',
            matched_resource='P-1',
            commission_qty='12',
            commission_area='12',
            completed_area='12',
        )

        stats = sync_project_plan_completion(self.project, 'anti-corrosion', business_date='20260714')

        pipe.refresh_from_db()
        self.assertEqual(pipe.anti_corrosion_status, '已完成')
        self.assertEqual(pipe.anti_corrosion_stock_qty, '7')
        self.assertEqual(pipe.coated_locked_qty, '5')
        self.assertEqual(pipe.uncoated_locked_qty, '0')
        self.assertEqual(stats['changedMaterialRows'], 1)

    def test_unfinished_anti_corrosion_material_area_does_not_set_status(self):
        source = self.create_anti_corrosion_material_source()
        MasterScheduleRow.objects.create(
            project=self.project,
            library_seq='W1',
            material_anti_corrosion_status=False,
        )
        AntiCorrosionMaterialOrderRow.objects.create(
            project=self.project,
            source_file=source,
            sheet_name='Sheet1',
            row_index=1,
            commission_area='12.5000',
            completed_area='8.0000',
            related_library_seqs='W1',
        )

        stats = sync_project_plan_completion(self.project, 'anti-corrosion', business_date='20260714')

        self.assertEqual(stats['completedCount'], 0)
        master = MasterScheduleRow.objects.get(project=self.project, library_seq='W1')
        self.assertIs(master.material_anti_corrosion_status, False)

    def test_completed_material_row_splits_all_supported_library_seq_separators(self):
        source = self.create_anti_corrosion_material_source()
        for library_seq in ['W1', 'W2', 'W3']:
            MasterScheduleRow.objects.create(
                project=self.project,
                library_seq=library_seq,
                material_anti_corrosion_status=False,
            )
        AntiCorrosionMaterialOrderRow.objects.create(
            project=self.project,
            source_file=source,
            sheet_name='Sheet1',
            row_index=1,
            commission_area='12.5000',
            completed_area='12.5000',
            related_library_seqs='W1、W2，W3',
        )

        stats = sync_project_plan_completion(self.project, 'anti-corrosion', business_date='20260714')

        self.assertEqual(stats['matchedCount'], 3)
        self.assertEqual(stats['completedCount'], 3)
        self.assertEqual(stats['changedMasterRows'], 3)
        self.assertEqual(stats['changedStatusRows'], 3)
        self.assertEqual(stats['updatedCount'], 3)
        self.assertEqual(
            WeldStatusRow.objects.filter(project=self.project, material_anti_corrosion_status=True).count(),
            3,
        )

    def test_welding_completion_moves_locked_pipe_quantity_to_used(self):
        material_source = DataSourceFile.objects.create(
            project=self.project,
            source_type='library',
            source_key='anti-pipe-library',
            display_name='防腐管子材料库',
            relative_path='database://library/anti-pipe-library',
        )
        pipe = PipeMaterialRow.objects.create(
            project=self.project,
            source_file=material_source,
            pipe_no='P-1',
            locked_qty='5',
            coated_locked_qty='5',
            uncoated_locked_qty='0',
            used_qty='0',
            anti_corrosion_status='已完成',
        )
        match_source = DataSourceFile.objects.create(
            project=self.project,
            source_type='pre-schedule',
            source_key='material-locking',
            display_name='材料匹配锁定结果',
            relative_path='database://pre-schedule/material-locking',
        )
        MaterialMatchDetailRow.objects.create(
            project=self.project,
            source_file=match_source,
            library_seq='W1',
            material_type='防腐管子',
            matched_inventory_key='P-1',
            matched_qty='5',
            match_result='可预排产',
            match_note='占用5米',
        )
        WeldStatusRow.objects.create(
            project=self.project,
            library_seq='W1',
            material_anti_corrosion_status=True,
            completed_flag=False,
        )
        plan_source = DataSourceFile.objects.create(
            project=self.project,
            source_type='plan',
            source_key='welding:20260714:管段焊口表.xlsx',
            display_name='管段焊口表.xlsx',
            relative_path='database://plan/welding/20260714',
            sheet_names=['Sheet1'],
        )
        WeldingPlanRow.objects.create(
            project=self.project,
            source_file=plan_source,
            sheet_name='Sheet1',
            library_seq='W1',
            completed_flag='已完成',
        )

        stats = sync_project_plan_completion(self.project, 'welding', business_date='20260714')

        pipe.refresh_from_db()
        self.assertEqual(pipe.locked_qty, '0')
        self.assertEqual(pipe.used_qty, '5')
        self.assertEqual(pipe.coated_locked_qty, '0')
        self.assertEqual(stats['changedMaterialRows'], 1)
