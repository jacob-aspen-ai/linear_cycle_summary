import requests, os
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

load_dotenv()
LINEAR_API_KEY = os.getenv("LINEAR_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "").strip()

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
    headers={"Authorization": f"Bearer {LINEAR_API_KEY}"}
)
teams_data = teams_resp.json()
if "data" not in teams_data or not teams_data["data"].get("teams"):
    print("❌ Failed to retrieve teams data.")
    print("🔍 Response content:", teams_resp.text)
    exit(1)

teams = teams_data["data"]["teams"]["nodes"]

# 2. For each team, fetch issues and organize by person
one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
week_start = one_week_ago.strftime("%b %d")
week_end = datetime.now(timezone.utc).strftime("%b %d")
updated_label = f"Updated {week_start} – {week_end}"
# Custom state order for sorting recently updated issues
status_order = ["Backlog", "To do", "In Progress", "In Review", "Ready for QA", "Done"]
state_categories = [
    (updated_label, None),
    ("To Do", "To do"),
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
        headers={"Authorization": f"Bearer {LINEAR_API_KEY}"}
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
        if state_name in ("Duplicate", "Canceled"):
            continue
        # Initialize nested dicts
        if assignee not in person_team_issues:
            person_team_issues[assignee] = {}
        if team_name not in person_team_issues[assignee]:
            person_team_issues[assignee][team_name] = {cat: [] for cat, _ in state_categories}
        # Categorize
        if updated_at_dt > one_week_ago:
            person_team_issues[assignee][team_name][updated_label].append(issue)
        elif state_name == "To Do":
            person_team_issues[assignee][team_name]["To Do"].append(issue)
        elif state_name == "In Progress":
            person_team_issues[assignee][team_name]["In Progress"].append(issue)
        elif state_name == "In Review":
            person_team_issues[assignee][team_name]["In Review"].append(issue)
        elif state_name == "Ready for QA":
            person_team_issues[assignee][team_name]["Ready for QA"].append(issue)

print("🔍 SLACK_WEBHOOK_URL:", SLACK_WEBHOOK_URL)

for person in sorted(person_team_issues.keys()):
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{person} – Week of {week_start}–{week_end}",
                "emoji": False
            }
        },
        {"type": "divider"}
    ]

    for team_name in sorted(person_team_issues[person].keys()):
        team_data = person_team_issues[person][team_name]
        if not any(team_data[cat] for cat, _ in state_categories):
            continue  # Skip if no issues for any category

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{team_name}*"
            }
        })

        seen_issues = set()
        for cat, _ in state_categories:
            issues = team_data[cat]
            filtered_issues = [
                issue for issue in issues
                if (issue["title"], issue["state"]["name"]) not in seen_issues
            ]
            if cat == updated_label:
                filtered_issues.sort(key=lambda i: status_order.index(i["state"]["name"]) if i["state"]["name"] in status_order else len(status_order))
            if not filtered_issues:
                continue

            label = "Recently Updated" if cat == updated_label else cat
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*• {label}:*"
                }
            })

            issue_lines = "\n".join(
                f"> • [{issue['state']['name']}] {issue['title']}"
                for issue in filtered_issues
            )
            if len(issue_lines) > 2900:
                issue_lines = issue_lines[:2900] + "\n> ...more"
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": issue_lines
                }
            })
            seen_issues.update((issue["title"], issue["state"]["name"]) for issue in filtered_issues)

    if SLACK_WEBHOOK_URL:
        resp = requests.post(SLACK_WEBHOOK_URL, json={"blocks": blocks})
        if resp.status_code != 200:
            print("❌ Slack POST failed")
            print("Status code:", resp.status_code)
            print("Response body:", resp.text)
        else:
            print(f"✅ Posted summary for {person} to Slack.")
    
from pprint import pprint
# pprint(blocks)  # Removed since blocks list no longer exists
