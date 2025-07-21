import requests, os
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

load_dotenv()
LINEAR_API_KEY = os.getenv("LINEAR_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# TEAM_ID is no longer needed

# 1. Fetch all teams
teams_query = """
query {
  teams {
    nodes {
      id
      name
    }
  }
}
"""

teams_resp = requests.post(
    "https://api.linear.app/graphql",
    json={"query": teams_query},
    headers={"Authorization": f"{LINEAR_API_KEY}"}
)
teams_data = teams_resp.json()
if "data" not in teams_data or not teams_data["data"].get("teams"):
    print("❌ Failed to retrieve teams data.")
    print("🔍 Response content:", teams_resp.text)
    exit(1)

teams = teams_data["data"]["teams"]["nodes"]

# 2. For each team, fetch issues and organize by person
one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
state_categories = [
    ("Updated in the last week", None),
    ("To Do", "To Do"),
    ("In Progress", "In Progress"),
    ("In Review", "In Review"),
    ("Ready for QA", "Ready for QA"),
]

# person_team_issues[person][team] = {category: [issues]}
person_team_issues = {}

for team in teams:
    team_id = team["id"]
    team_name = team["name"]
    # Fetch all issues for this team
    issues_query = """
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
    issues_resp = requests.post(
        "https://api.linear.app/graphql",
        json={"query": issues_query, "variables": {"teamId": team_id}},
        headers={"Authorization": f"{LINEAR_API_KEY}"}
    )
    issues_data = issues_resp.json()
    if "data" not in issues_data or not issues_data["data"].get("team"):
        print(f"❌ Failed to retrieve issues data for team {team_name}.")
        print("🔍 Response content:", issues_resp.text)
        continue
    issues = issues_data["data"]["team"]["issues"]["nodes"]

    for issue in issues:
        if not issue["assignee"] or not issue["assignee"]["name"]:
            continue  # skip unassigned
        assignee = issue["assignee"]["name"]
        updated_at = issue["updatedAt"]
        updated_at_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        state_name = issue["state"]["name"]
        # Initialize nested dicts
        if assignee not in person_team_issues:
            person_team_issues[assignee] = {}
        if team_name not in person_team_issues[assignee]:
            person_team_issues[assignee][team_name] = {cat: [] for cat, _ in state_categories}
        # Categorize
        if updated_at_dt > one_week_ago:
            person_team_issues[assignee][team_name]["Updated in the last week"].append(issue)
        elif state_name == "To Do":
            person_team_issues[assignee][team_name]["To Do"].append(issue)
        elif state_name == "In Progress":
            person_team_issues[assignee][team_name]["In Progress"].append(issue)
        elif state_name == "In Review":
            person_team_issues[assignee][team_name]["In Review"].append(issue)
        elif state_name == "Ready for QA":
            person_team_issues[assignee][team_name]["Ready for QA"].append(issue)

# 3. Format summary by person, then by team, then by category
summary_lines = []
for person in sorted(person_team_issues.keys()):
    summary_lines.append(f"\n👤 {person}:")
    for team_name in sorted(person_team_issues[person].keys()):
        summary_lines.append(f"  🏷️ Team: {team_name}")
        seen_issues = set()
        for cat, _ in state_categories:
            issues = person_team_issues[person][team_name][cat]
            # Avoid duplicates between categories
            filtered_issues = [
                issue for issue in issues
                if (issue["title"], issue["state"]["name"]) not in seen_issues
            ]
            if filtered_issues:
                summary_lines.append(f"    • {cat}:")
                for issue in filtered_issues:
                    summary_lines.append(f"      - [{issue['state']['name']}] {issue['title']} (updated {issue['updatedAt']})")
                    seen_issues.add((issue["title"], issue["state"]["name"]))
summary_text = "\n".join(summary_lines)

prompt = f"""
You are a technical assistant and highly experienced product manager at an AI startup. For each person, and for each team, summarize their issues, separated into:
1. Updated in the last week
2. To Do
3. In Progress
4. In Review
5. Ready for QA
Do not include unassigned issues. Avoid listing the same issue twice for a person. For each person, briefly describe what they worked on or have in progress.

Importantly: format the report in Slack Block Kit format, so that it can be posted to Slack.

Summary:
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
