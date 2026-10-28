import os
import sys
import logging
from datetime import datetime, timezone

import pandas as pd
import requests
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


# -----------------------------
# Configuration
# -----------------------------
GITHUB_API_URL = "https://api.github.com/search/repositories"
SEARCH_QUERY = os.getenv("GITHUB_SEARCH_QUERY", "data engineering")
RESULT_LIMIT = int(os.getenv("GITHUB_RESULT_LIMIT", "100"))

SQL_SERVER = os.getenv("SQL_SERVER", r".\SQLEXPRESS")
SQL_DATABASE = os.getenv("SQL_DATABASE", "GitHubData")
SQL_DRIVER = os.getenv("SQL_DRIVER", "ODBC Driver 17 for SQL Server")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def extract_repositories(query: str, limit: int) -> pd.DataFrame:
    """Extract repository records from the GitHub Search API."""
    logger.info("Requesting GitHub repositories for query: %s", query)

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": min(limit, 100),
    }

    response = requests.get(
        GITHUB_API_URL,
        headers=headers,
        params=params,
        timeout=30,
    )
    response.raise_for_status()

    payload = response.json()
    repositories = payload.get("items", [])

    rows = []
    for repo in repositories[:limit]:
        rows.append(
            {
                "repository_id": repo.get("id"),
                "name": repo.get("name"),
                "full_name": repo.get("full_name"),
                "description": repo.get("description"),
                "language": repo.get("language"),
                "stars": repo.get("stargazers_count"),
                "forks": repo.get("forks_count"),
                "open_issues": repo.get("open_issues_count"),
                "created_at": repo.get("created_at"),
                "html_url": repo.get("html_url"),
                "extracted_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        )

    df = pd.DataFrame(rows)
    logger.info("Extracted %s repository records.", len(df))
    return df


def transform_repositories(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and prepare repository records before loading them."""
    if df.empty:
        logger.warning("No repositories returned by the API.")
        return df

    # Remove rows that do not have a repository ID or full name.
    df = df.dropna(subset=["repository_id", "full_name"]).copy()

    # Ensure numeric fields have numeric types.
    numeric_columns = ["repository_id", "stars", "forks", "open_issues"]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0).astype("int64")

    # Normalize text fields and replace missing descriptions/languages.
    for column in ["name", "full_name", "html_url"]:
        df[column] = df[column].fillna("").astype(str).str.strip()

    df["description"] = df["description"].fillna("").astype(str).str.strip()
    df["language"] = df["language"].fillna("Not specified").astype(str).str.strip()

    # Standardize timestamps as text to avoid SQL Server datetime parsing issues.
    df["created_at"] = pd.to_datetime(
        df["created_at"], errors="coerce", utc=True
    ).dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    df = df.drop_duplicates(subset=["repository_id"])
    df = df.sort_values(by="stars", ascending=False)

    logger.info("Transformed data; %s unique records remain.", len(df))
    return df


def create_sql_engine():
    """Create a SQL Server connection using Windows Authentication."""
    connection_url = URL.create(
        "mssql+pyodbc",
        query={
            "odbc_connect": (
                "DRIVER={" + SQL_DRIVER + "};"
                "SERVER=" + SQL_SERVER + ";"
                "DATABASE=" + SQL_DATABASE + ";"
                "Trusted_Connection=yes;"
                "TrustServerCertificate=yes;"
            )
        },
    )
    return create_engine(connection_url, fast_executemany=True)


def load_repositories(df: pd.DataFrame) -> None:
    """Load repository records into SQL Server, updating existing IDs."""
    if df.empty:
        logger.warning("No data to load.")
        return

    engine = create_sql_engine()

    # Create the destination table if it does not exist.
    create_table_sql = """
    IF OBJECT_ID('dbo.github_repositories', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.github_repositories (
            repository_id BIGINT NOT NULL PRIMARY KEY,
            name NVARCHAR(255) NULL,
            full_name NVARCHAR(500) NOT NULL,
            description NVARCHAR(MAX) NULL,
            language NVARCHAR(100) NULL,
            stars BIGINT NULL,
            forks BIGINT NULL,
            open_issues BIGINT NULL,
            created_at NVARCHAR(40) NULL,
            html_url NVARCHAR(1000) NULL,
            extracted_at_utc NVARCHAR(50) NULL
        );
    END;
    """

    with engine.begin() as connection:
        connection.execute(text(create_table_sql))

        # Use a temporary staging table to avoid duplicate-key errors.
        df.to_sql(
            "github_repositories_staging",
            con=connection,
            schema="dbo",
            if_exists="replace",
            index=False,
            chunksize=500,
        )

        # Update records already present in the target table.
        connection.execute(text("""
            UPDATE target
            SET
                target.name = source.name,
                target.full_name = source.full_name,
                target.description = source.description,
                target.language = source.language,
                target.stars = source.stars,
                target.forks = source.forks,
                target.open_issues = source.open_issues,
                target.created_at = source.created_at,
                target.html_url = source.html_url,
                target.extracted_at_utc = source.extracted_at_utc
            FROM dbo.github_repositories AS target
            INNER JOIN dbo.github_repositories_staging AS source
                ON target.repository_id = source.repository_id;
        """))

        # Insert records that do not exist yet.
        connection.execute(text("""
            INSERT INTO dbo.github_repositories (
                repository_id, name, full_name, description, language,
                stars, forks, open_issues, created_at, html_url, extracted_at_utc
            )
            SELECT
                source.repository_id, source.name, source.full_name,
                source.description, source.language, source.stars,
                source.forks, source.open_issues, source.created_at,
                source.html_url, source.extracted_at_utc
            FROM dbo.github_repositories_staging AS source
            WHERE NOT EXISTS (
                SELECT 1
                FROM dbo.github_repositories AS target
                WHERE target.repository_id = source.repository_id
            );
        """))

        connection.execute(text("DROP TABLE dbo.github_repositories_staging;"))

        row_count = connection.execute(
            text("SELECT COUNT(*) FROM dbo.github_repositories;")
        ).scalar_one()

    engine.dispose()
    logger.info("Load completed. Total records in destination table: %s", row_count)


def main() -> int:
    try:
        repositories = extract_repositories(SEARCH_QUERY, RESULT_LIMIT)
        cleaned_repositories = transform_repositories(repositories)
        load_repositories(cleaned_repositories)
        logger.info("Pipeline completed successfully.")
        return 0
    except requests.RequestException as exc:
        logger.error("GitHub API request failed: %s", exc)
        return 1
    except Exception:
        logger.exception("Pipeline failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
