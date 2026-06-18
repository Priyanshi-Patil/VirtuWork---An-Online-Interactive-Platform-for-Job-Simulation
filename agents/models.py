from django.db import models
from simulation.models import Simulation

class Conversation(models.Model):
    AGENT_CHOICES = [('HR', 'HR'), ('CLIENT', 'Client'), ('PEER', 'Peer')]
    
    simulation = models.ForeignKey(Simulation, on_delete=models.CASCADE)
    agent_type = models.CharField(max_length=10, choices=AGENT_CHOICES)
    session_id = models.CharField(max_length=100, unique=True) # For OpenRouter tracking

class Message(models.Model):
    conversation = models.ForeignKey(Conversation, related_name='messages', on_delete=models.CASCADE)
    sender = models.CharField(max_length=20) # 'User' or Agent Name
    text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

class SharedSummary(models.Model):
    simulation = models.ForeignKey(Simulation, on_delete=models.CASCADE)
    summary_text = models.TextField()
    last_message_count = models.IntegerField(default=0) # Tracks the 10-15 message chunks