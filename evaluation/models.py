# evaluation/models.py
from django.db import models
from simulation.models import Simulation, Task

class TaskSubmission(models.Model):
    # Added related_name for easier querying in the template
    task = models.ForeignKey(Task, related_name='submissions', on_delete=models.CASCADE) 
    zip_file = models.FileField(upload_to='submissions/zips/')
    attempt_number = models.IntegerField(default=1) 
    is_success = models.BooleanField(default=False)
    
    # NEW FIELDS: Store the evaluation results for this specific try
    score = models.IntegerField(default=0)
    feedback = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.task.title} - Attempt {self.attempt_number}"

class SubmissionScreenshot(models.Model):
    submission = models.ForeignKey(TaskSubmission, related_name='screenshots', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='submissions/screenshots/')

class ProgressReport(models.Model):
    simulation = models.OneToOneField(Simulation, on_delete=models.CASCADE)
    overall_score = models.FloatField()
    technical_skills = models.JSONField() # Store breakdown as JSON
    communication_skills = models.JSONField()
    ai_feedback = models.TextField()