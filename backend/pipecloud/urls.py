from importlib import import_module

from django.urls import path

file_parser_views = import_module('pipecloud.views.file_parser')
file_export_views = import_module('pipecloud.views.file_exports')
developer_views = import_module('pipecloud.views.developer')
factory_views = import_module('pipecloud.views.factory')
library_views = import_module('pipecloud.views.libraries')
plan_views = import_module('pipecloud.views.plans')
project_views = import_module('pipecloud.views.projects')
workflow_views = import_module('pipecloud.views.workflow')
upload_views = import_module('pipecloud.views.uploads')


urlpatterns = [
    path('developer/plan-rollover/', developer_views.run_plan_rollover, name='pipecloud-developer-plan-rollover'),
    path('developer/database/', developer_views.database_overview, name='pipecloud-developer-database-overview'),
    path('developer/database/clear/', developer_views.clear_database, name='pipecloud-developer-database-clear'),
    path('projects/', project_views.projects, name='pipecloud-projects'),
    path('projects/import/', project_views.import_projects, name='pipecloud-projects-import'),
    path('projects/export/', project_views.export_projects, name='pipecloud-projects-export'),
    path('projects/<int:project_id>/constraints/', project_views.project_constraints, name='pipecloud-project-constraints'),
    path('projects/<int:project_id>/welds/', project_views.project_weld_rows, name='pipecloud-project-weld-rows'),
    path('projects/<int:project_id>/welds/upload/', project_views.upload_project_weld_file, name='pipecloud-project-weld-upload'),
    path('projects/<int:project_id>/spools/', project_views.project_spool_info, name='pipecloud-project-spool-info'),
    path('projects/<int:project_id>/', project_views.project_detail, name='pipecloud-project-detail'),
    path('summary/', workflow_views.summary, name='pipecloud-summary'),
    path('files/', workflow_views.files, name='pipecloud-files'),
    path('files/export-tree/', file_export_views.project_file_tree, name='pipecloud-file-export-tree'),
    path('files/batch-export/', file_export_views.batch_export_project_files, name='pipecloud-file-batch-export'),
    path('files/batch-export/start/', file_export_views.start_batch_export, name='pipecloud-file-batch-export-start'),
    path('files/batch-export/status/', file_export_views.batch_export_status, name='pipecloud-file-batch-export-status'),
    path('files/batch-export/download/', file_export_views.download_batch_export, name='pipecloud-file-batch-export-download'),
    path('initialization/stats/', workflow_views.initialization_stats, name='pipecloud-initialization-stats'),
    path('initialization/sync/', workflow_views.sync_initialization_data, name='pipecloud-initialization-sync'),
    path('initialization/project-metrics/', workflow_views.update_initialization_project_metrics, name='pipecloud-initialization-project-metrics'),
    path('welding/dashboard/', workflow_views.welding_dashboard, name='pipecloud-welding-dashboard'),
    path('arrival/dashboard/', workflow_views.arrival_dashboard, name='pipecloud-arrival-dashboard'),
    path('anti-corrosion/dashboard/', workflow_views.anti_corrosion_dashboard, name='pipecloud-anti-corrosion-dashboard'),
    path('cutting/dashboard/', workflow_views.cutting_dashboard, name='pipecloud-cutting-dashboard'),
    path('factory/today-pipe-materials/', factory_views.today_pipe_materials, name='pipecloud-factory-today-pipe-materials'),
    path('arrival/files/', workflow_views.arrival_files, name='pipecloud-arrival-files'),
    path('arrival/today/', workflow_views.arrival_today, name='pipecloud-arrival-today'),
    path('arrival/file/', workflow_views.arrival_file_rows, name='pipecloud-arrival-file-rows'),
    path('arrival/upload/', workflow_views.upload_arrival_file, name='pipecloud-arrival-upload'),
    path('arrival/confirm-import/', workflow_views.confirm_arrival_import, name='pipecloud-arrival-confirm-import'),
    path('file-parser/parse/', file_parser_views.parse_uploaded_files, name='pipecloud-file-parser-parse'),
    path('file-parser/jobs/latest-result/', file_parser_views.latest_parser_result, name='pipecloud-file-parser-latest-result'),
    path('file-parser/jobs/<str:job_id>/cancel/', file_parser_views.cancel_parser_job, name='pipecloud-file-parser-job-cancel'),
    path('file-parser/jobs/<str:job_id>/', file_parser_views.parser_job_status, name='pipecloud-file-parser-job-status'),
    path('file-parser/upload-initialization/', file_parser_views.stage_initialization_upload, name='pipecloud-file-parser-upload-initialization'),
    path('file-parser/merge/', file_parser_views.merge_parser_results, name='pipecloud-file-parser-merge'),
    path('file-parser/confirm/', file_parser_views.confirm_initialization_file, name='pipecloud-file-parser-confirm'),
    path('file-parser/preview/', file_parser_views.parser_file_preview, name='pipecloud-file-parser-preview'),
    path('file-parser/model-preview/', file_parser_views.parser_model_preview, name='pipecloud-file-parser-model-preview'),
    path('file-parser/model-confirm/', file_parser_views.confirm_idf_model, name='pipecloud-file-parser-model-confirm'),
    path('file-parser/download/', file_parser_views.download_parsed_file, name='pipecloud-file-parser-download'),
    path('file-parser/download-all/', file_parser_views.download_parsed_files, name='pipecloud-file-parser-download-all'),
    path('uploads/<str:upload_key>/', upload_views.upload_files, name='pipecloud-upload-files'),
    path('libraries/', library_views.libraries, name='pipecloud-libraries'),
    path('libraries/<str:library_key>/', library_views.library_rows, name='pipecloud-library-rows'),
    path('libraries/<str:library_key>/save/', library_views.save_library_rows, name='pipecloud-library-save-rows'),
    path('anti-corrosion/pre-schedule/', workflow_views.anti_corrosion_pre_schedule_rows, name='pipecloud-anti-corrosion-pre-schedule-rows'),
    path('cutting/pre-schedule/', workflow_views.cutting_pre_schedule_rows, name='pipecloud-cutting-pre-schedule-rows'),
    path('cutting/visualization/', workflow_views.cutting_visualization, name='pipecloud-cutting-visualization'),
    path('schedule/future/', workflow_views.generate_future_schedule, name='pipecloud-generate-future-schedule'),
    path('schedule/stage/file/', workflow_views.staged_plan_file_rows, name='pipecloud-staged-plan-file-rows'),
    path('schedule/stage/commit/', workflow_views.commit_staged_plan, name='pipecloud-commit-staged-plan'),
    path('plans/<str:plan_key>/', plan_views.plan_rows, name='pipecloud-plan-rows'),
    path('plans/<str:plan_key>/move/', plan_views.move_plan_date, name='pipecloud-plan-move-date'),
    path('plans/<str:plan_key>/delete/', plan_views.delete_plan, name='pipecloud-plan-delete'),
    path('plans/<str:plan_key>/file/', plan_views.plan_file_rows, name='pipecloud-plan-file-rows'),
    path('plans/<str:plan_key>/file/save/', plan_views.save_plan_file_rows, name='pipecloud-plan-file-save-rows'),
    path('plans/<str:plan_key>/file/import/', plan_views.import_plan_patch_rows, name='pipecloud-plan-file-import-rows'),
    path('plans/<str:plan_key>/file/export/', plan_views.export_plan_patch_rows, name='pipecloud-plan-file-export-rows'),
    path('run/<str:action_key>/', workflow_views.run_action, name='pipecloud-run-action'),
]
