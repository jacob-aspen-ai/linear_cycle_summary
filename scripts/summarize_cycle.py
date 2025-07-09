import requests, os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
LINEAR_API_KEY = os.getenv("LINEAR_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
TEAM_ID = os.getenv("TEAM_ID")
CYCLE_NUMBER = os.getenv("CYCLE_NUMBER")
if CYCLE_NUMBER is not None:
    CYCLE_NUMBER = int(CYCLE_NUMBER)
else:
    # Try to get the current active cycle
    active_cycle_query = """
    query GetActiveCycle($teamId: ID!) {
      cycles(
        filter: {
          team: { id: { eq: $teamId } }
          isActive: { eq: true }
        }
        first: 1
        orderBy: updatedAt
      ) {
        nodes {
          number
        }
      }
    }
    """
    cycle_resp = requests.post(
        "https://api.linear.app/graphql",
        json={"query": active_cycle_query, "variables": {"teamId": TEAM_ID}},
        headers={"Authorization": f"{LINEAR_API_KEY}"}
    )
    try:
        node = cycle_resp.json()["data"]["cycles"]["nodes"][0]
        CYCLE_NUMBER = node["number"]
        print("✅ Detected active cycle number:", CYCLE_NUMBER)
    except (KeyError, IndexError, TypeError):
        # Fallback to the most recently completed cycle
        print("⚠️ No active cycle found. Trying fallback to latest completed cycle...")
        fallback_query = """
        query GetCompletedCycle($teamId: ID!) {
          cycles(
            filter: {
              team: { id: { eq: $teamId } }
              completedAt: { neq: null }
            }
            first: 1
            orderBy: completedAt
          ) {
            nodes {
              number
            }
          }
        }
        """
        fallback_resp = requests.post(
            "https://api.linear.app/graphql",
            json={"query": fallback_query, "variables": {"teamId": TEAM_ID}},
            headers={"Authorization": f"{LINEAR_API_KEY}"}
        )
        try:
            node = fallback_resp.json()["data"]["cycles"]["nodes"][0]
            CYCLE_NUMBER = node["number"]
            print("✅ Fallback to completed cycle number:", CYCLE_NUMBER)
        except (KeyError, IndexError, TypeError) as e:
            print("❌ Failed to retrieve any cycle number:", e)
            print("🔍 Response content:", fallback_resp.text)
            exit(1)

query = """
query CycleIssues($teamId: ID!, $cycleNumber: Float!) {
  cycles(filter: {team: {id: {eq: $teamId}}, number: {eq: $cycleNumber}}) {
    nodes {
      issues {
        nodes {
          title
          state { name }
          assignee { name }
        }
      }
    }
  }
}
"""

resp = requests.post(
    "https://api.linear.app/graphql",
    json={"query": query, "variables": {"teamId": "f578e495-6741-45d0-bde7-54633219be25", "cycleNumber": CYCLE_NUMBER}},
    headers={"Authorization": f"{LINEAR_API_KEY}"}
)
data = resp.json()

if "data" not in data:
    print("❌ Failed to retrieve issues data.")
    print("🔍 Response content:", resp.text)
    exit(1)

issues = data["data"]["cycles"]["nodes"][0]["issues"]["nodes"]

formatted = []
for issue in issues:
    title = issue["title"]
    state = issue["state"]["name"]
    assignee = issue["assignee"]["name"] if issue["assignee"] else "Unassigned"
    formatted.append(f"- [{state}] {title} — {assignee}")
issue_list = "\n".join(formatted)

prompt = f"""
You are a technical assistant and highly experienced product manager at an AI startup. Summarize this Linear cycle.

Group into:
🚀 Features shipped 
⚠️ SEVs/incidents handled 
🔁 Carried over  
🧠 Team focus  

Make sure to note who completed what. Make it concise and engaging.

Issues:
{issue_list}
"""
print(issue_list) 

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
