import requests, os
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

load_dotenv()
LINEAR_API_KEY = os.getenv("LINEAR_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
TEAM_ID = os.getenv("TEAM_ID")

# Fetch all issues for the team
query = """
query TeamIssues($teamId: String!) {
  team(id: $teamId) {
    issues(first: 200) {
      nodes {
        title
        state { name }
        assignee { name }
        updatedAt
      }
    }
  }
}
"""

resp = requests.post(
    "https://api.linear.app/graphql",
    json={"query": query, "variables": {"teamId": TEAM_ID}},
    headers={"Authorization": f"{LINEAR_API_KEY}"}
)
data = resp.json()

if "data" not in data or not data["data"].get("team"):
    print("❌ Failed to retrieve issues data.")
    print("🔍 Response content:", resp.text)
    exit(1)

issues = data["data"]["team"]["issues"]["nodes"]

one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
recent_issues = []
for issue in issues:
    updated_at = issue["updatedAt"]
    updated_at_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    if updated_at_dt > one_week_ago:
        recent_issues.append(issue)

# Group by assignee
by_person = {}
for issue in recent_issues:
    assignee = issue["assignee"]["name"] if issue["assignee"] else "Unassigned"
    by_person.setdefault(assignee, []).append(issue)

# Format summary by person
summary_lines = []
for person, person_issues in by_person.items():
    summary_lines.append(f"\n👤 {person}:")
    for issue in person_issues:
        summary_lines.append(f"  - [{issue['state']['name']}] {issue['title']} (updated {issue['updatedAt']})")
summary_text = "\n".join(summary_lines)

prompt = f"""
You are a technical assistant and highly experienced product manager at an AI startup. Summarize the following Linear issues, grouped by person, and only include issues that were updated in the past week. For each person, briefly describe what they worked on or updated.

Issues updated in the past week, grouped by assignee:
{summary_text}
"""

print(summary_text)

client = OpenAI(api_key=OPENAI_API_KEY)
completion = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": prompt}]
)
summary = completion.choices[0].message.content

if SLACK_WEBHOOK_URL:
    requests.post(SLACK_WEBHOOK_URL, json={"text": summary})
else:
    print(summary)
