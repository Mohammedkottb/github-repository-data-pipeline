# GitHub Repository Data Pipeline

A Python project that collects repository data from the GitHub API, processes it using Pandas, and stores it in Microsoft SQL Server.

## What I learned

-Getting data from the GitHub API using Python and requests

-Cleaning and organizing data with pandas

-Connecting Python to SQL Server using SQLAlchemy and pyodbc

-Creating database tables and inserting or updating repository records

-Handling duplicate records and basic errors

-Using Git to track changes and GitHub to publish the project

## Pipeline

1.Extract: Get repository data from the GitHub Search API.

2.Transform: Clean the data, handle missing values, convert numeric fields, format dates, and remove duplicate records.

3.Load: Store the processed data in SQL Server. Create the target table if it does not exist, update existing repositories, and insert new ones.

## Requirements

Before running the project, make sure you have:

-Python 3.10 or later

-Microsoft SQL Server

-Microsoft ODBC Driver for SQL Server

-A database named GitHubData, or another database configured in the environment settings

-Git

## Setup on Windows

Open PowerShell in the project folder and follow these steps.

### 1. Create and activate a virtual environment

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install Python dependencies

```powershell
python -m pip install -r requirements.txt
```

### 3. Configure the database

Create the database in SQL Server if it does not already exist:

```sql
CREATE DATABASE GitHubData;
```

The default connection uses Windows Authentication. If your SQL Server instance or ODBC driver has a different name, set the environment variables before running the script. For example:

```powershell
$env:SQL_SERVER = ".\SQLEXPRESS"
$env:SQL_DATABASE = "GitHubData"
$env:SQL_DRIVER = "ODBC Driver 17 for SQL Server"
```

Use the ODBC driver version installed on your computer. Do not commit credentials or secrets to GitHub.

### 4. Run the pipeline

```powershell
python main.py
```

Optional search settings:

```powershell
$env:GITHUB_SEARCH_QUERY = "python data engineering"
$env:GITHUB_RESULT_LIMIT = "100"
python main.py
```

The GitHub Search API currently returns up to 100 results per request in this example. Unauthenticated requests are subject to GitHub API rate limits.

## Example SQL queries

Count repositories by programming language:

```sql
SELECT language, COUNT(*) AS repository_count
FROM dbo.github_repositories
GROUP BY language
ORDER BY repository_count DESC;
```

Find the most-starred repositories:

```sql
SELECT TOP 10 full_name, language, stars, forks, html_url
FROM dbo.github_repositories
ORDER BY stars DESC;
```

## Limitations and next improvements

- This project collects a single page of search results per run.
- It does not yet use a scheduler or an orchestration platform.
- API rate limits may affect repeated runs.
- Add tests, configuration validation, pagination, and automated execution as future improvements.

## Resume description (use after you have run and verified the project)

**GitHub Repository Data Pipeline | Python, Pandas, REST API, SQL Server**
- Extracted repository metadata from the GitHub Search API using Python.
- Cleaned, transformed, and deduplicated data using Pandas.
- Loaded records into SQL Server and implemented update/insert logic to avoid duplicate repository IDs.
