# Generated migration for ai_engine app

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

	initial = True

	dependencies = [
		migrations.swappable_dependency(settings.AUTH_USER_MODEL),
		('documents', '0001_initial'),
		('conversations', '0001_initial'),
	]

	operations = [
		migrations.CreateModel(
			name='DocumentChunk',
			fields=[
				('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
				('sequence_index', models.PositiveIntegerField()),
				('content', models.TextField()),
				('token_count', models.PositiveIntegerField()),
				('embedding', models.BinaryField(blank=True, null=True)),
				('metadata', models.JSONField(blank=True, default=dict)),
				('created_at', models.DateTimeField(auto_now_add=True)),
				('updated_at', models.DateTimeField(auto_now=True)),
				('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chunks', to='documents.document')),
				('document_owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='document_chunks', to=settings.AUTH_USER_MODEL)),
			],
			options={
				'ordering': ['document', 'sequence_index'],
			},
		),
		migrations.CreateModel(
			name='QueryLog',
			fields=[
				('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
				('query_text', models.TextField()),
				('query_embedding', models.BinaryField(blank=True, null=True)),
				('retrieved_chunk_ids', models.JSONField(blank=True, default=list)),
				('llm_response', models.TextField()),
				('llm_model', models.CharField(default='stub', max_length=100)),
				('latency_ms', models.PositiveIntegerField()),
				('token_usage', models.JSONField(blank=True, default=dict)),
				('created_at', models.DateTimeField(auto_now_add=True)),
				('conversation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ai_queries', to='conversations.conversation')),
				('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ai_queries', to=settings.AUTH_USER_MODEL)),
			],
			options={
				'ordering': ['-created_at'],
			},
		),
		migrations.AddIndex(
			model_name='documentchunk',
			index=models.Index(fields=['document', 'sequence_index'], name='ai_engine_d_documen_idx'),
		),
		migrations.AddIndex(
			model_name='documentchunk',
			index=models.Index(fields=['document_owner'], name='ai_engine_d_documen_owner_idx'),
		),
	]
