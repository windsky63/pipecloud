import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from openpyxl import Workbook

from pipecloud.models import ParserArtifact, ParserJob, ParserSubtask, Project


class LatestParserResultTests(TestCase):
    def setUp(self):
        self.parser_root = tempfile.TemporaryDirectory()
        self.parser_root_patch = patch(
            'pipecloud.views.common.FILE_PARSER_ROOT',
            Path(self.parser_root.name),
        )
        self.parser_root_patch.start()
        self.project = Project.objects.create(project_name='恢复解析结果测试')

    def tearDown(self):
        self.parser_root_patch.stop()
        self.parser_root.cleanup()

    def create_result_file(self, relative_path):
        path = Path(self.parser_root.name) / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'parser-result')

    def create_job(self, job_id, status, results):
        return ParserJob.objects.create(
            job_id=job_id,
            project=self.project,
            file_type='pcf',
            status=status,
            input_hash=f'{job_id}-hash',
            results=results,
        )

    def test_returns_latest_completed_result_for_selected_project(self):
        expected_result = {
            'sourceName': 'latest.pcf',
            'filename': 'latest.xlsx',
            'stagedPath': 'missing/latest.xlsx',
        }
        self.create_result_file('missing/latest.xlsx')
        self.create_result_file('missing/older.xlsx')
        self.create_job('older-completed', 'completed', [{
            'sourceName': 'older.pcf',
            'filename': 'older.xlsx',
            'stagedPath': 'missing/older.xlsx',
        }])
        self.create_job('latest-completed', 'completed', [expected_result])
        self.create_job('newer-running', 'running', [])

        response = self.client.get(
            '/api/pipecloud/file-parser/jobs/latest-result/',
            {'project_id': self.project.id},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['jobId'], 'latest-completed')
        self.assertEqual(payload['results'], [expected_result])

    def test_skips_completed_result_when_preview_file_is_missing(self):
        self.create_job('missing-completed', 'completed', [{
            'filename': 'missing.xlsx',
            'stagedPath': 'missing/missing.xlsx',
        }])

        response = self.client.get(
            '/api/pipecloud/file-parser/jobs/latest-result/',
            {'project_id': self.project.id},
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn('暂无可恢复', response.json()['error'])

    def test_returns_not_found_when_project_has_no_completed_result(self):
        self.create_job('running-only', 'running', [])

        response = self.client.get(
            '/api/pipecloud/file-parser/jobs/latest-result/',
            {'project_id': self.project.id},
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn('暂无可恢复', response.json()['error'])

    def test_cancel_running_parser_job(self):
        job = self.create_job('running-job', 'running', [])
        ParserSubtask.objects.create(
            job=job,
            index=1,
            status='queued',
            file_count=1,
        )

        response = self.client.post(
            '/api/pipecloud/file-parser/jobs/running-job/cancel/',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'canceled')
        job.refresh_from_db()
        self.assertEqual(job.status, 'canceled')
        self.assertEqual(job.subtasks.get(index=1).status, 'canceled')

    def test_cancel_completed_parser_job_is_noop(self):
        job = self.create_job('completed-job', 'completed', [{'filename': 'done.xlsx'}])

        response = self.client.post(
            '/api/pipecloud/file-parser/jobs/completed-job/cancel/',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'completed')
        job.refresh_from_db()
        self.assertEqual(job.status, 'completed')


class ParserPreviewAndDownloadTests(TestCase):
    def setUp(self):
        self.parser_root = tempfile.TemporaryDirectory()
        self.parser_root_patch = patch(
            'pipecloud.views.common.FILE_PARSER_ROOT',
            Path(self.parser_root.name),
        )
        self.parser_root_patch.start()
        self.project = Project.objects.create(project_name='数据库解析制品测试')

    def tearDown(self):
        self.parser_root_patch.stop()
        self.parser_root.cleanup()

    def create_workbook(self, relative_path, sheet_names):
        path = Path(self.parser_root.name) / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        workbook = Workbook()
        workbook.active.title = sheet_names[0]
        for sheet_name in sheet_names[1:]:
            workbook.create_sheet(sheet_name)
        for worksheet in workbook.worksheets:
            worksheet.append(['名称', '数量'])
            worksheet.append([worksheet.title, 1])
        workbook.save(path)
        return path

    def test_switches_preview_sheet_using_staged_path(self):
        self.create_workbook('含 空格/解析结果.xlsx', ['材料表', '焊口表'])

        response = self.client.get('/api/pipecloud/file-parser/preview/', {
            'stagedPath': '含 空格/解析结果.xlsx',
            'sheet': '焊口表',
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['preview']['sheet'], '焊口表')
        self.assertEqual(payload['preview']['sheets'], ['材料表', '焊口表'])

    def test_downloads_all_preview_files_as_zip(self):
        self.create_workbook('one/结果.xlsx', ['Sheet1'])
        self.create_workbook('two/结果.xlsx', ['Sheet1'])

        response = self.client.post(
            '/api/pipecloud/file-parser/download-all/',
            data=json.dumps({
                'stagedPaths': ['one/结果.xlsx', 'two/结果.xlsx'],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')
        self.assertGreater(len(response.content), 0)

    def test_download_all_reports_expired_preview_file(self):
        response = self.client.post(
            '/api/pipecloud/file-parser/download-all/',
            data=json.dumps({'stagedPaths': ['missing.xlsx']}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('已失效', response.json()['error'])

    def test_previews_and_downloads_database_artifact_without_disk_file(self):
        path = self.create_workbook('temporary/数据库结果.xlsx', ['材料表', '焊口表'])
        content = path.read_bytes()
        artifact = ParserArtifact.objects.create(
            project=self.project,
            source='parse',
            filename=path.name,
            content=content,
            file_size=len(content),
            content_hash='test-hash',
        )
        path.unlink()

        preview_response = self.client.get('/api/pipecloud/file-parser/preview/', {
            'artifactId': artifact.id,
            'sheet': '焊口表',
        })
        download_response = self.client.get('/api/pipecloud/file-parser/download/', {
            'artifactId': artifact.id,
        })

        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(preview_response.json()['preview']['sheet'], '焊口表')
        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response.content, content)
