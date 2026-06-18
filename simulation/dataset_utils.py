"""

How it works:
  1. Takes the project title + description
  2. Extracts keywords and searches Kaggle for a matching dataset
  3. If a good match is found, downloads and returns it as a CSV
  4. If no match, generates realistic synthetic data using the AI
     based on the project description
  5. Returns (csv_bytes, filename) ready for a Django FileResponse
"""

import os
import re
import io
import json
import zipfile
import requests
import numpy as np
import pandas as pd
from django.conf import settings


# ─── Kaggle Search + Download ─────────────────────────────────────────────────

KAGGLE_API_URL = "https://www.kaggle.com/api/v1"


def get_kaggle_credentials():
    username = getattr(settings, 'KAGGLE_USERNAME', os.environ.get('KAGGLE_USERNAME'))
    key = getattr(settings, 'KAGGLE_KEY', os.environ.get('KAGGLE_KEY'))
    return username, key


def extract_keywords(title, description):
    stop = {
        'and', 'the', 'for', 'with', 'using', 'based', 'via', 'from',
        'into', 'will', 'this', 'that', 'are', 'has', 'have', 'been',
        'data', 'model', 'models', 'system', 'solution', 'project',
        'develop', 'build', 'create', 'end', 'to', 'a', 'an', 'of',
        'in', 'on', 'by', 'as', 'at', 'be', 'or', 'is', 'it',
    }
    text = f"{title} {description}".lower()
    words = re.findall(r'\b[a-z]{4,}\b', text)
    keywords = [w for w in words if w not in stop]
    freq = {}
    for w in keywords:
        freq[w] = freq.get(w, 0) + 1
    top = sorted(freq, key=freq.get, reverse=True)[:5]
    return ' '.join(top)


def search_kaggle_datasets(query, username, key, max_results=5):
    try:
        resp = requests.get(
            f"{KAGGLE_API_URL}/datasets/list",
            params={'search': query, 'sortBy': 'relevance', 'fileType': 'csv'},
            auth=(username, key),
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        return resp.json()[:max_results]
    except Exception:
        return []


def download_kaggle_dataset(dataset_ref, username, key):
    try:
        owner, slug = dataset_ref.split('/')
        resp = requests.get(
            f"{KAGGLE_API_URL}/datasets/{owner}/{slug}/download",
            auth=(username, key),
            timeout=30,
            stream=True,
        )
        if resp.status_code != 200:
            return None, None

        zip_bytes = io.BytesIO(resp.content)
        with zipfile.ZipFile(zip_bytes) as z:
            csv_files = [f for f in z.namelist() if f.endswith('.csv')]
            if not csv_files:
                return None, None
            csv_files.sort(key=lambda f: z.getinfo(f).file_size, reverse=True)
            filename = csv_files[0].split('/')[-1]
            csv_bytes = z.read(csv_files[0])
            return csv_bytes, filename
    except Exception:
        return None, None


# ─── Fallback Generic Dataset ─────────────────────────────────────────────────

def _make_fallback_dataframe(n_rows):
    """Returns a plain DataFrame (not a tuple)."""
    np.random.seed(42)
    return pd.DataFrame({
        'id': range(1, n_rows + 1),
        'feature_1': np.random.uniform(0, 100, n_rows).round(2),
        'feature_2': np.random.uniform(0, 100, n_rows).round(2),
        'feature_3': np.random.randint(0, 10, n_rows),
        'category': np.random.choice(['A', 'B', 'C', 'D'], n_rows),
        'label': np.random.choice([0, 1], n_rows),
    })


def _df_to_csv_bytes(df):
    """Convert a DataFrame to UTF-8 encoded CSV bytes."""
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue().encode('utf-8')


# ─── AI Schema Builder ────────────────────────────────────────────────────────

def _build_dataframe_from_schema(schema, n_rows):
    """Build a pandas DataFrame from the AI-designed schema."""
    np.random.seed(42)
    data = {}

    for col in schema.get('columns', []):
        name = col['name']
        col_type = col.get('type', 'float')
        col_range = col.get('range', '')

        if col_type == 'int':
            try:
                lo, hi = map(int, str(col_range).split('-'))
            except Exception:
                lo, hi = 0, 100
            data[name] = np.random.randint(lo, hi + 1, n_rows)

        elif col_type == 'float':
            try:
                lo, hi = map(float, str(col_range).split('-'))
            except Exception:
                lo, hi = 0.0, 1.0
            data[name] = np.round(np.random.uniform(lo, hi, n_rows), 3)

        elif col_type == 'category':
            try:
                choices = [v.strip() for v in str(col_range).split(',')]
                if not choices or choices == ['']:
                    choices = ['A', 'B', 'C']
            except Exception:
                choices = ['A', 'B', 'C']
            data[name] = np.random.choice(choices, n_rows)

        elif col_type == 'bool':
            data[name] = np.random.choice([0, 1], n_rows)

        elif col_type == 'text':
            data[name] = [f"{name}_{i}" for i in range(n_rows)]

        else:
            data[name] = np.random.uniform(0, 1, n_rows).round(3)

    # Make binary target column correlated with numeric features
    target = schema.get('target_column')
    if target and target in data:
        col_def = next((c for c in schema['columns'] if c['name'] == target), None)
        if col_def and col_def.get('type') == 'bool':
            numeric_cols = [
                k for k, v in data.items()
                if k != target and isinstance(
                    v[0] if hasattr(v, '__getitem__') else v,
                    (int, float, np.integer, np.floating)
                )
            ]
            if numeric_cols:
                scores = np.zeros(n_rows)
                for nc in numeric_cols[:5]:
                    arr = np.array(data[nc], dtype=float)
                    arr_norm = (arr - arr.min()) / (arr.max() - arr.min() + 1e-9)
                    scores += arr_norm
                scores = scores / len(numeric_cols[:5])
                data[target] = (scores > np.random.uniform(0.3, 0.7, n_rows)).astype(int)

    return pd.DataFrame(data)


# ─── AI-Powered Synthetic Data Generator ─────────────────────────────────────

def generate_synthetic_data(title, description, n_rows=1000):
    """
    Calls the AI via OpenRouter to design a dataset schema,
    then generates synthetic data matching the project requirements.
    Always returns (csv_bytes, filename).
    """
    api_keys = getattr(settings, 'OPENROUTER_API_KEYS', [])
    fallback_filename = re.sub(r'[^a-z0-9_]', '_', title.lower())[:40] + '_dataset.csv'

    if not api_keys:
        return _df_to_csv_bytes(_make_fallback_dataframe(n_rows)), fallback_filename

    api_key = api_keys[0] if isinstance(api_keys, list) else api_keys

    prompt = f"""You are a data scientist. Given this ML project, design a realistic CSV dataset schema.

Project Title: {title}
Project Description: {description}

Respond ONLY with a JSON object in this exact format (no markdown, no explanation):
{{
  "filename": "dataset_name.csv",
  "columns": [
    {{"name": "col_name", "type": "int|float|category|text|bool", "description": "what it represents", "range": "min-max or list of values"}},
    ...
  ],
  "target_column": "column_name_to_predict",
  "n_rows": {n_rows}
}}

Rules:
- Include 10-20 columns relevant to the project
- Always include an ID column
- Always include a target/label column
- Make column ranges realistic and domain-appropriate
- For category columns, list 3-6 possible values separated by commas in the range field
"""

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openrouter/auto",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )

        if resp.status_code != 200:
            return _df_to_csv_bytes(_make_fallback_dataframe(n_rows)), fallback_filename

        content = resp.json()['choices'][0]['message']['content'].strip()
        # Strip markdown fences if present
        content = re.sub(r'```json|```', '', content).strip()
        schema = json.loads(content)

        df = _build_dataframe_from_schema(schema, n_rows)
        filename = schema.get('filename', fallback_filename)
        # Sanitise filename
        filename = re.sub(r'[^a-z0-9_\-.]', '_', filename.lower())
        return _df_to_csv_bytes(df), filename

    except Exception:
        return _df_to_csv_bytes(_make_fallback_dataframe(n_rows)), fallback_filename


# ─── Main Entry Point ─────────────────────────────────────────────────────────

def get_dataset_for_project(project_title, project_description):
    """
    Main function called from the Django view.
    Always returns (csv_bytes: bytes, filename: str).
    """
    username, key = get_kaggle_credentials()
    kaggle_available = bool(username and key)

    # Step 1: Try Kaggle if credentials are configured
    if kaggle_available:
        query = extract_keywords(project_title, project_description)
        datasets = search_kaggle_datasets(query, username, key)

        if datasets:
            best = datasets[0]
            ref = best.get('ref') or f"{best.get('ownerName')}/{best.get('currentDatasetVersionNumber')}"
            csv_bytes, filename = download_kaggle_dataset(ref, username, key)
            if csv_bytes and filename:
                safe_name = re.sub(r'[^a-z0-9_\-.]', '_', filename.lower())
                return csv_bytes, safe_name

    # Step 2: Generate synthetic data via AI (always returns correct types)
    return generate_synthetic_data(project_title, project_description, n_rows=1000)