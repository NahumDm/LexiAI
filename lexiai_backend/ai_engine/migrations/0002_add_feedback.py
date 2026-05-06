# Generated migration for ai_engine app - add QueryFeedback and retrieval_confidence

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

	dependencies = [
		('ai_engine', '0001_initial'),
		migrations.swappable_dependency(settings.AUTH_USER_MODEL),
	]

	operations = [
		migrations.AddField(
			model_name='querylog',
			name='retrieval_confidence',
			field=models.FloatField(blank=True, default=0.0, help_text='Average similarity score of retrieved chunks (0.0-1.0)'),
		),
		migrations.CreateModel(
			name='QueryFeedback',
			fields=[
				('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
				('rating', models.CharField(
					choices=[('up', 'Helpful'), ('down', 'Not Helpful')],
					max_length=10,
				)),
				('comment', models.TextField(blank=True, help_text='Optional feedback comment from user')),
				('created_at', models.DateTimeField(auto_now_add=True)),
				('updated_at', models.DateTimeField(auto_now=True)),
				('query_log', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='feedback', to='ai_engine.querylog')),
				('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='query_feedback', to=settings.AUTH_USER_MODEL)),
			],
			options={
				'ordering': ['-created_at'],
				'verbose_name_plural': 'Query Feedback',
			},
		),
		migrations.AddIndex(
			model_name='querylog',
			index=models.Index(fields=['retrieval_confidence'], name='ai_engine_q_retr_conf_idx'),
		),
		migrations.AddIndex(
			model_name='querylog',
			index=models.Index(fields=['created_at'], name='ai_engine_q_created_idx'),
		),
		migrations.AddIndex(
			model_name='queryfeedback',
			index=models.Index(fields=['user', 'created_at'], name='ai_engine_qf_user_created_idx'),
		),
	]
