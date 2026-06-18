import json
import requests
from django.conf import settings
from .models import *
from agents.models import *
import re
import zipfile
import io


class ManagerAgent:
    def adjust_difficulty(self, simulation, last_score):
        next_task = simulation.tasks.filter(is_completed=False).order_by('order').first()
        if not next_task:
            return
        if last_score > 90:
            next_task.instruction += " (Note: This is an advanced version of the task to challenge you.)"
            next_task.difficulty = 3
        elif last_score < 50:
            next_task.instruction += " (Note: I've simplified the requirements for this one to help you catch up.)"
            next_task.difficulty = 1
        next_task.save()


class BaseAgent:
    def __init__(self):
        self.keys = settings.OPENROUTER_API_KEYS
        self.models = [
            "openrouter/auto",
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemini-2.0-flash-exp:free",
        ]

    def _call_openrouter(self, messages, json_mode=False):
        for model in self.models:
            for key in self.keys:
                try:
                    payload = {"model": model, "messages": messages}
                    if json_mode:
                        payload["response_format"] = {"type": "json_object"}

                    response = requests.post(
                        url="https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {key}",
                            "HTTP-Referer": "http://localhost:8000",
                            "Content-Type": "application/json"
                        },
                        data=json.dumps(payload),
                        timeout=30
                    )
                    if response.status_code == 200:
                        content = response.json()['choices'][0]['message']['content']
                        print(f"[BaseAgent] Success with model: {model}")
                        print(content)
                        return self._clean_content(content)
                    else:
                        print(f"[BaseAgent] {model} error {response.status_code}: {response.text}")
                except Exception as e:
                    print(f"[BaseAgent] Exception with {model}: {e}")
                    continue
        return None

    def _clean_content(self, content):
        """Strip markdown fences and extract clean JSON string."""
        if not content:
            return content
        content = content.strip()
        # Remove markdown fences
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return content

    def _safe_parse_json(self, content):
        """
        Robustly parse JSON from model response.
        Handles: plain JSON, JSON in array, nested analysis keys.
        Always returns a dict or None.
        """
        if not content:
            return None
        try:
            parsed = json.loads(content)
            # If it's a list, take the first item
            if isinstance(parsed, list):
                parsed = parsed[0] if parsed else {}
            # If it has a single wrapper key like "analysis" or "response", unwrap it
            if isinstance(parsed, dict) and len(parsed) == 1:
                only_key = list(parsed.keys())[0]
                if only_key.lower() in ('analysis', 'response', 'result', 'data', 'output'):
                    return None  # This is a bad response, not real JSON
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            # Try to find JSON object inside the string
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
        return None


class ThinkerAgent(BaseAgent):
    def generate_project(self, role, education):
        prompt = """You are a project generator. Return ONLY a valid JSON object. No explanation. No markdown. No extra text.

The JSON must have EXACTLY this structure:
{
  "title": "Project title here",
  "description": "2-3 sentence project description here",
  "agents": {
    "hr_name": "Female HR manager name",
    "peer_name": "Male peer colleague name",
    "client_name": "Male client name"
  }
}

Generate a realistic industry project for role: """ + role + """

RULES:
- Return ONLY the JSON object above
- No analysis, no explanation, no extra keys
- description must be a plain string, not an object
- All names must be realistic professional names
- DO NOT wrap in array or add any other keys"""

        for attempt in range(3):
            response = self._call_openrouter(
                [{"role": "user", "content": prompt}],
                json_mode=True
            )
            result = self._safe_parse_json(response)
            if result and 'title' in result and 'description' in result and 'agents' in result:
                # Make sure description is a string, not a dict
                if isinstance(result['description'], dict):
                    result['description'] = result.get('title', role + ' Project') + ' — A professional simulation project.'
                # Make sure agents is a dict with required keys
                if isinstance(result.get('agents'), dict):
                    agents = result['agents']
                    if 'hr_name' in agents and 'peer_name' in agents and 'client_name' in agents:
                        return result
            print(f"[ThinkerAgent] Attempt {attempt+1} failed, retrying...")

        # Fallback if all attempts fail
        return {
            'title': f'{role} Simulation Project',
            'description': f'A professional {role} simulation project involving real-world tasks and challenges.',
            'agents': {
                'hr_name': 'Sarah Johnson',
                'peer_name': 'Alex Mayor',
                'client_name': 'Michael Chen'
            }
        }

    def generate_task_solution(self, project_title, task_instruction):
        prompt = f"""You are an Expert Lead. For the project '{project_title}', provide the perfect solution code for this task: '{task_instruction}'. Return ONLY the code solution."""
        return self._call_openrouter([{"role": "system", "content": prompt}])


class PlannerAgent(BaseAgent):
    def create_subtasks(self, simulation):
        prompt = """You are a project planner. Return ONLY a valid JSON object. No explanation. No markdown. No extra text.

The JSON must have EXACTLY this structure:
{
  "subtasks": [
    {
      "order": 1,
      "title": "Task title",
      "instruction": "Detailed task instruction",
      "assigned_agent": "HR",
      "requires_submission": false
    },
    {
      "order": 2,
      "title": "Task title",
      "instruction": "Detailed task instruction",
      "assigned_agent": "PEER",
      "requires_submission": true
    }
  ]
}

Create 5-7 tasks for this project: """ + simulation.project_title + """

RULES:
- Return ONLY the JSON object above
- subtasks must be an array of task objects
- assigned_agent must be exactly "HR", "PEER", or "CLIENT"
- requires_submission is true for coding/design tasks, false for discussion tasks
- First task should be HR onboarding (requires_submission: false)
- Middle tasks should be technical PEER tasks (requires_submission: true)
- Last task should be CLIENT review (requires_submission: false)
- DO NOT add analysis, explanation, or any other keys"""

        for attempt in range(3):
            response = self._call_openrouter(
                [{"role": "user", "content": prompt}],
                json_mode=True
            )
            result = self._safe_parse_json(response)

            if result and 'subtasks' in result and isinstance(result['subtasks'], list) and len(result['subtasks']) > 0:
                # Validate each subtask has required fields
                valid = True
                for t in result['subtasks']:
                    if not all(k in t for k in ['order', 'title', 'instruction']):
                        valid = False
                        break
                if valid:
                    for i, t in enumerate(result['subtasks']):
                        Task.objects.create(
                            simulation=simulation,
                            title=t.get('title', f'Task {i+1}'),
                            instruction=t.get('instruction', 'Follow the project instructions.'),
                            order=t.get('order', i+1),
                            requires_submission=t.get('requires_submission', False),
                            difficulty=t.get('difficulty', 1)
                        )
                    print(f"[PlannerAgent] Created {len(result['subtasks'])} tasks")
                    return True

            print(f"[PlannerAgent] Attempt {attempt+1} failed. Response: {response}")

        # Fallback tasks if all attempts fail
        print("[PlannerAgent] All attempts failed. Using fallback tasks.")
        fallback_tasks = [
            {"order": 1, "title": "Project Kickoff & Onboarding", "instruction": f"Welcome to the {simulation.project_title} project. Review the project scope, meet the team, and confirm your understanding of the objectives.", "assigned_agent": "HR", "requires_submission": False},
            {"order": 2, "title": "Requirements Analysis", "instruction": f"Analyse the requirements for {simulation.project_title}. Document the key functional and non-functional requirements.", "assigned_agent": "PEER", "requires_submission": True},
            {"order": 3, "title": "System Design", "instruction": f"Design the architecture for {simulation.project_title}. Create a design document covering components, data flow, and technology choices.", "assigned_agent": "PEER", "requires_submission": True},
            {"order": 4, "title": "Core Implementation", "instruction": f"Implement the core features of {simulation.project_title} based on your design. Submit your code in a ZIP file.", "assigned_agent": "PEER", "requires_submission": True},
            {"order": 5, "title": "Client Review & Handover", "instruction": f"Present your completed work on {simulation.project_title} to the client. Demonstrate the solution and address any feedback.", "assigned_agent": "CLIENT", "requires_submission": False},
        ]
        for t in fallback_tasks:
            Task.objects.create(
                simulation=simulation,
                title=t['title'],
                instruction=t['instruction'],
                order=t['order'],
                requires_submission=t['requires_submission'],
                difficulty=1
            )
        print("[PlannerAgent] Created 5 fallback tasks.")
        return True


class SummarizerAgent:
    def __init__(self):
        self.keys = settings.OPENROUTER_API_KEYS
        self.models = [
            "openrouter/auto",
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemini-2.0-flash-exp:free",
        ]

    def _call_openrouter(self, messages):
        for model in self.models:
            for key in self.keys:
                try:
                    response = requests.post(
                        url="https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {key}",
                            "HTTP-Referer": "http://localhost:8000",
                            "Content-Type": "application/json"
                        },
                        data=json.dumps({"model": model, "messages": messages}),
                        timeout=30
                    )
                    if response.status_code == 200:
                        print(f"[SummarizerAgent] Success with model: {model}")
                        return response.json()['choices'][0]['message']['content']
                    else:
                        print(f"[SummarizerAgent] {model} error {response.status_code}")
                except Exception as e:
                    print(f"[SummarizerAgent] Exception: {e}")
                    continue
        return "Summary generation failed."

    def summarize_chat(self, conversation):
        messages = conversation.messages.all().order_by('-timestamp')[:15]
        text_to_summarize = "\n".join([f"{m.sender}: {m.text}" for m in reversed(messages)])
        prompt = f"Summarize the following workplace conversation concisely. Focus on user progress and blockers:\n\n{text_to_summarize}"
        response_text = self._call_openrouter([{"role": "system", "content": prompt}])
        SharedSummary.objects.create(simulation=conversation.simulation, content=response_text)


class ConversationAgent:
    def __init__(self, role_type):
        self.keys = settings.OPENROUTER_API_KEYS
        self.role_type = role_type
        self.models = [
            "openrouter/auto",
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemini-2.0-flash-exp:free",
        ]

    def _call_openrouter(self, messages):
        for model in self.models:
            for key in self.keys:
                try:
                    response = requests.post(
                        url="https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {key}",
                            "HTTP-Referer": "http://localhost:8000",
                            "Content-Type": "application/json"
                        },
                        data=json.dumps({"model": model, "messages": messages}),
                        timeout=30
                    )
                    if response.status_code == 200:
                        print(f"[ConversationAgent] Success with model: {model}")
                        return response.json()['choices'][0]['message']['content']
                    else:
                        print(f"[ConversationAgent] {model} error {response.status_code}: {response.text}")
                except Exception as e:
                    print(f"[ConversationAgent] Exception with {model}: {e}")
                    continue
        return "I'm having trouble connecting right now. Please try again in a moment."

    def get_response(self, simulation, user_message):
        current_task = simulation.tasks.filter(is_completed=False).order_by('order').first()
        total_tasks = simulation.tasks.count()

        conversation = Conversation.objects.get(simulation=simulation, agent_type=self.role_type)
        own_history = conversation.messages.all().order_by('-timestamp')[:6]
        history_str = "\n".join([f"{m.sender}: {m.text}" for m in reversed(own_history)])
        already_greeted = conversation.messages.filter(sender=self.role_type).count() > 0

        if self.role_type == 'HR':
            agent_name = simulation.hr_name
        elif self.role_type == 'PEER':
            agent_name = simulation.peer_name
        else:
            agent_name = simulation.client_name

        if total_tasks == 0:
            current_task_title = "Project initializing"
            current_task_instruction = "Tasks are still being set up."
        elif current_task:
            current_task_title = current_task.title
            current_task_instruction = current_task.instruction
        else:
            current_task_title = "All tasks completed"
            current_task_instruction = "All tasks are done. Congratulate the user warmly."

        if self.role_type == 'HR':
            role_scope = f"""You are {agent_name}, the HR Manager for this project.

YOUR ONLY RESPONSIBILITIES:
- Welcome the user and handle onboarding questions
- Explain team structure, company culture, and administrative processes
- Answer questions about roles, timelines, and project background

WHAT YOU MUST NEVER DO:
- Do not describe how to complete tasks technically
- Do not repeat project milestones or task steps
- Do not discuss Slack, Drives, or external tools unless the user specifically asks
- Do not repeat anything you already said in the conversation history"""

        elif self.role_type == 'PEER':
            role_scope = f"""You are {agent_name}, the senior technical peer/colleague on this project.

YOUR ONLY RESPONSIBILITIES:
- Help the user understand the technical requirements of the current task: "{current_task_title}"
- Give hints, code guidance, and technical advice when asked
- Review the user's approach and suggest improvements

WHAT YOU MUST NEVER DO:
- Do not repeat the task instructions word for word
- Do not discuss onboarding or administrative items
- Do not repeat anything you already said in the conversation history
- Do not complete the task for the user — only guide"""

        else:
            role_scope = f"""You are {agent_name}, the client stakeholder for this project.

YOUR ONLY RESPONSIBILITIES:
- Explain business requirements and what success looks like from a client perspective
- Give feedback on deliverables when asked
- Clarify the business context behind the current task: "{current_task_title}"

WHAT YOU MUST NEVER DO:
- Do not describe code, libraries, or technical steps
- Do not discuss team communication tools or onboarding processes
- Do not repeat anything you already said in the conversation history"""

        greeting_rule = (
            f"IMPORTANT: You have already greeted the user. Do NOT greet them again or re-introduce yourself. Respond naturally to their message."
            if already_greeted else
            f"You are speaking to the user for the first time. Introduce yourself briefly as {agent_name} and ask how you can help."
        )

        system_prompt = f"""
{role_scope}

PROJECT: {simulation.project_title}
CURRENT TASK: {current_task_title}

{greeting_rule}

CONVERSATION HISTORY (your chat only):
{history_str}

RESPONSE RULES:
1. Keep your reply to 2-4 sentences maximum.
2. Be natural and conversational.
3. Never copy-paste task instructions verbatim.
4. Never mention tools like Slack, Google Drive, or GitHub unless the user brings them up first.
5. Never say the project is complete unless current task is 'All tasks completed'.
6. Stay strictly in your role.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        return self._call_openrouter(messages)


class TaskEvaluatorAgent:
    def __init__(self):
        self.keys = settings.OPENROUTER_API_KEYS
        self.models = [
            "openrouter/auto",
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemini-2.0-flash-exp:free",
        ]

    def _call_openrouter(self, messages):
        for model in self.models:
            for key in self.keys:
                try:
                    response = requests.post(
                        url="https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {key}",
                            "HTTP-Referer": "http://localhost:8000",
                            "Content-Type": "application/json"
                        },
                        data=json.dumps({"model": model, "messages": messages}),
                        timeout=45
                    )
                    if response.status_code == 200:
                        print(f"[TaskEvaluatorAgent] Success with model: {model}")
                        return response.json()['choices'][0]['message']['content']
                    else:
                        print(f"[TaskEvaluatorAgent] {model} error {response.status_code}")
                except Exception as e:
                    print(f"[TaskEvaluatorAgent] Exception: {e}")
                    continue
        return "SCORE: 0 | FEEDBACK: Connection error during evaluation."

    def evaluate(self, simulation, task, zip_file):
        file_contents = ""
        file_list = []
        try:
            with zipfile.ZipFile(zip_file) as z:
                for file_name in z.namelist():
                    if not file_name.endswith('/'):
                        file_list.append(file_name)
                        with z.open(file_name) as f:
                            file_contents += f"\n--- File: {file_name} ---\n"
                            file_contents += f.read().decode('utf-8', errors='ignore')[:5000]
        except Exception as e:
            return f"SCORE: 0 | FEEDBACK: Error reading ZIP: {str(e)}"

        prompt = f"""You are a Senior Technical Lead evaluating a candidate's submission.

PROJECT CONTEXT:
Role: {simulation.role_title}
Project: {simulation.project_title}
Current Task: {task.title}
Task Instructions: {task.instruction}

REFERENCE GOLD STANDARD:
{simulation.expected_output_template}

USER'S SUBMITTED FILES: {", ".join(file_list)}
USER'S CODE CONTENT:
{file_contents}

EVALUATION CRITERIA:
1. COMPLETENESS: Did the user provide the expected files?
2. LOGIC: Does the code perform the requested task?
3. ACCURACY: How closely does the logic match the Reference Gold Standard?
4. BEST PRACTICES: Usage of appropriate libraries and clean code.

STRICT RULE: Only evaluate against the CURRENT task: {task.title}.
The feedback should be in second person.

OUTPUT FORMAT (strictly follow):
SCORE: [0-100] | FEEDBACK: [2-3 sentences explaining the grade]"""

        return self._call_openrouter([{"role": "system", "content": prompt}])


class PerformanceAgent:
    def __init__(self):
        self.keys = settings.OPENROUTER_API_KEYS
        self.models = [
            "openrouter/auto",
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemini-2.0-flash-exp:free",
        ]

    def _call_openrouter(self, messages):
        for model in self.models:
            for key in self.keys:
                try:
                    response = requests.post(
                        url="https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {key}",
                            "HTTP-Referer": "http://localhost:8000",
                            "Content-Type": "application/json"
                        },
                        data=json.dumps({"model": model, "messages": messages}),
                        timeout=60
                    )
                    if response.status_code == 200:
                        print(f"[PerformanceAgent] Success with model: {model}")
                        return response.json()['choices'][0]['message']['content']
                    else:
                        print(f"[PerformanceAgent] {model} error {response.status_code}")
                except Exception as e:
                    print(f"[PerformanceAgent] Exception: {e}")
                    continue
        return "{}"

    def generate_final_report(self, simulation):
        tasks = simulation.tasks.all().order_by('id')
        task_breakdown = []

        for task in tasks:
            sub = task.submissions.all().order_by('-created_at').first()
            if not task.requires_submission:
                status, score, feedback = "Information Only", "N/A", "This task was instructional."
            elif not sub:
                status, score, feedback = "Missing", 0, "No submissions made yet."
            else:
                status, score, feedback = "Completed", sub.score, sub.feedback
            task_breakdown.append({"title": task.title, "score": score, "feedback": feedback, "status": status})

        completed_tasks = simulation.tasks.filter(is_completed=True)
        task_summary = "\n".join([f"Task: {t.title} | Score: {t.score}" for t in completed_tasks])
        all_messages = Message.objects.filter(conversation__simulation=simulation).order_by('timestamp')
        chat_transcript = "\n".join([f"{m.sender}: {m.text}" for m in all_messages])

        prompt = f"""You are a Senior Career Coach. Analyze this simulation performance.
Project: {simulation.project_title}
Transcript: {chat_transcript}
Task Scores: {task_summary}

Return ONLY a valid JSON object with NO extra text, NO markdown, NO explanation:
{{
    "overall_performace": 75,
    "communication_score": 80,
    "technical_score": 70,
    "problem_solving_score": 75,
    "summary": "Detailed overall feedback here",
    "strengths": ["strength 1", "strength 2", "strength 3"],
    "weaknesses": ["weakness 1", "weakness 2"]
}}

Replace the example numbers with real scores based on the transcript and task scores above.
All scores must be integers between 0 and 100."""

        response_text = self._call_openrouter([{"role": "system", "content": prompt}])

        try:
            with open("output.txt", "w") as file:
                file.write(response_text)
        except Exception:
            pass

        try:
            cleaned = response_text.replace('```json', '').replace('```', '').strip()
            report_data = json.loads(cleaned)
            report_data['task_breakdown'] = task_breakdown
            return report_data
        except Exception:
            return {"summary": "Error generating report.", "task_breakdown": task_breakdown}