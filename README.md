# VirtuWork Pro 🚀

> **AI-Powered Workplace Simulation Platform**  
> Simulate real-world job experiences with AI agents acting as your HR, Peer, and Client; complete tasks, get evaluated, and earn a verified certificate.

---

## 📌 Table of Contents

- [About the Project](#about-the-project)
- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Setup](#environment-setup)
- [Database Setup](#database-setup)
- [Running the Project](#running-the-project)
- [How It Works](#how-it-works)
- [AI Agents](#ai-agents)
- [Known Issues](#known-issues)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## About the Project

**VirtuWork Pro** is a Django-based web application that simulates a professional workplace environment using AI. When a user starts a simulation, the platform:

1. Assigns them a real-world project based on their chosen job role.
2. Breaks the project into 5-7 milestone tasks.
3. Provides three AI agents (HR, Peer, Client) that they can chat with for guidance.
4. Evaluates submitted work and gives scores and feedback.
5. Generates a final performance report and a downloadable verified certificate.

The goal is to help students, freshers, and career switchers build practical experience in a risk-free, AI-guided environment.

---

## Key Features

- 🤖 **AI Project Generation** -- ThinkerAgent designs a unique project for every simulation
- 📋 **Task Breakdown** -- PlannerAgent creates 5–7 logical milestones with submission requirements
- 💬 **Three AI Chat Agents** -- HR (onboarding), Peer (technical guidance), Client (business requirements)
- 📁 **Task Submission & Evaluation** -- Upload ZIP files, get scored by AI with detailed feedback
- 📊 **Performance Report** -- Radar chart with scores for Communication, Technical, Problem Solving
- 🏆 **Verified Certificate** -- QR code certificate generated on project completion
- 📧 **Email OTP Verification** -- Secure signup with Gmail SMTP OTP
- 🔑 **Forgot Password Flow** -- OTP-based password reset
- 📥 **Auto Dataset Download** -- AI-generated or Kaggle-matched CSV datasets per project
- ⚡ **Fast Loading** -- Background threading so simulations initialize in ~15 seconds
- ☁️ **Cloud Database** -- Aiven MySQL for multi-device access

---

## Tech Stack

- Backend -- Django 5.0 (Python) 
- Database -- MySQL (Aiven Cloud) 
- AI / LLM -- OpenRouter API (Gemini Flash, LLaMA 3.3, Auto) 
- Frontend -- Tailwind CSS, Chart.js, Vanilla JS 
- PDF Generation -- Playwright (Chromium) 
- Email -- Gmail SMTP 
- Data Generation -- NumPy, Pandas 
- Deployment (planned) -- Render + Aiven 

---

## Project Structure

```
virtuwork_pro/
├── core/                   # Auth, signup, login, dashboard, profile
│   ├── models.py           # UserProfile model
│   ├── views.py            # All core views, including OTP, forgot password
│   └── templates/
├── simulation/             # Main simulation logic
│   ├── models.py           # Simulation, Task, Profile models
│   ├── views.py            # Simulation views + background threading
│   ├── agents.py           # All AI agents (Thinker, Planner, Conversation, Evaluator, Performance)
│   └── dataset_utils.py    # Auto dataset generation / Kaggle fetch
├── agents/                 # Conversation and message models
│   └── models.py           # Conversation, Message, SharedSummary
├── evaluation/             # Task submission and progress report models
│   └── models.py           # TaskSubmission, ProgressReport
├── templates/              # All HTML templates
│   ├── index.html
│   ├── login.html
│   ├── signup.html
│   ├── verify_otp.html
│   ├── forgot_password.html
│   ├── reset_password.html
│   ├── dashboard.html
│   ├── loading.html
│   ├── simulation_chat.html
│   ├── final_report.html
│   ├── certificate.html
│   ├── profile.html
│   └── ...
├── virtuwork_pro/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── requirements.txt
├── manage.py
└── ca.pem                  # Aiven SSL certificate (not committed to git)
```

---

## Getting Started

### Prerequisites

- Python 3.10 or higher
- MySQL (local) or an Aiven cloud MySQL account
- An [OpenRouter](https://openrouter.ai) account and API key
- A Gmail account with an [App Password](https://myaccount.google.com/apppasswords) enabled

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/virtuwork-pro.git
cd virtuwork-pro/virtuwork_pro
```

### 2. Create a Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Playwright Browsers

```bash
playwright install chromium
```

---

## Environment Setup

Create a `.env` file in the `virtuwork_pro/` directory (same folder as `settings.py`) and add the following:

```env
# Django
SECRET_KEY=your-secret-key-here
DEBUG=True

# Database (Aiven MySQL)
DB_NAME=defaultdb
DB_USER=avnadmin
DB_PASSWORD=your-aiven-password
DB_HOST=your-aiven-host.aivencloud.com
DB_PORT=22326
DB_SSL_CA=C:/path/to/ca.pem

# OpenRouter API
OPENROUTER_API_KEY=sk-or-v1-your-key-here

# Gmail SMTP
EMAIL_HOST_USER=your-gmail@gmail.com
EMAIL_HOST_PASSWORD=your-16-char-app-password

# Optional: Kaggle (for real datasets)
# KAGGLE_USERNAME=your-kaggle-username
# KAGGLE_KEY=your-kaggle-api-key
```

Then update `settings.py` to read from `.env` using `python-decouple`:

```python
from decouple import config

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT'),
        'OPTIONS': {'ssl': {'ca': config('DB_SSL_CA')}}
    }
}

OPENROUTER_API_KEYS = [config('OPENROUTER_API_KEY')]

EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
```

---

## Database Setup

### Using Aiven (Cloud MySQL)

1. Sign up at [aiven.io](https://aiven.io) and create a free MySQL service
2. Download the `ca.pem` SSL certificate from the Aiven dashboard
3. Place `ca.pem` in your project root
4. Add your Aiven credentials to `.env`

### Using Local MySQL

```env
DB_HOST=localhost
DB_PORT=3306
DB_SSL_CA=  # leave empty for local
```

Update `settings.py` to skip SSL when `DB_SSL_CA` is empty:

```python
options = {}
ssl_ca = config('DB_SSL_CA', default='')
if ssl_ca:
    options = {'ssl': {'ca': ssl_ca}}

DATABASES = {
    'default': {
        ...
        'OPTIONS': options
    }
}
```

### Run Migrations

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

---

## Running the Project

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000` in your browser.

---

## How It Works

### User Flow

```
Register → Email OTP Verification → Login
    ↓
Dashboard → Create Simulation (choose job role)
    ↓
Loading Screen (AI builds project in background ~15s)
    ↓
Simulation Chat (HR / Peer / Client tabs)
    ↓
Project Overview → Download Dataset → Complete Tasks
    ↓
Submit ZIP → AI Evaluates → Score + Feedback
    ↓
All Tasks Done → End Simulation → Final Report
    ↓
Performance Radar Chart → Certificate → Download PDF
```

### Simulation Initialization (Background Threading)

When a user creates a simulation, Django immediately returns the loading page and starts the AI setup in a background thread. The loading page polls `/simulation/check-ready/<id>/` every 3 seconds until the AI finishes.

This means the user sees the loading animation instantly rather than waiting for a blocked HTTP response.

---

## AI Agents

| Agent | Role | Responsibilities |
|---|---|---|
| **ThinkerAgent** | Project Designer | Generates project title, description, and agent names |
| **PlannerAgent** | Task Creator | Breaks project into 5-7 milestone tasks |
| **ConversationAgent (HR)** | HR Manager | Onboarding, admin questions, team intro |
| **ConversationAgent (Peer)** | Technical Colleague | Code hints, technical guidance, task help |
| **ConversationAgent (Client)** | Client Stakeholder | Business requirements, feedback, expectations |
| **TaskEvaluatorAgent** | Technical Evaluator | Scores submitted ZIP files against task requirements |
| **PerformanceAgent** | Career Coach | Generates final report with scores and recommendations |
| **SummarizerAgent** | Chat Summarizer | Summarizes conversations every 10 messages |

All agents use [OpenRouter](https://openrouter.ai) with a model priority list:
1. `google/gemini-2.0-flash-exp:free` (fastest)
2. `meta-llama/llama-3.3-70b-instruct:free`
3. `openrouter/auto`

---

## Known Issues

- Free-tier Aiven MySQL can be slow under heavy load, so consider upgrading or migrating to Railway
- OpenRouter free models occasionally return malformed JSON; the agents have retry logic and fallbacks to handle this
- Playwright PDF generation requires Chromium to be installed separately via `playwright install chromium`
- `ca.pem` path must be an absolute path on Windows

---

## Roadmap

- [ ] Deploy to Render.com
- [ ] Mobile-responsive simulation chat UI
- [ ] Admin dashboard for monitoring simulations
- [ ] Multiple simulation roles in one session
- [ ] Leaderboard across users
- [ ] LinkedIn certificate sharing integration
- [ ] Move secrets fully to environment variables

---

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

1. Fork the repository
2. Create your feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'Add your feature'`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

---

## License

This project is licensed under the MIT License. See `LICENSE` for details.

---

## Acknowledgements

- [OpenRouter](https://openrouter.ai) for free LLM API access
- [Aiven](https://aiven.io) for free cloud MySQL
- [Tailwind CSS](https://tailwindcss.com) for styling
- [Chart.js](https://chartjs.org) for the radar chart
- [Playwright](https://playwright.dev) for PDF generation

---

*Built with ❤️ by the VirtuWork Team*
