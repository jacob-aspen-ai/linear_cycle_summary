import requests

headers = {
    "Authorization": "lin_api_Bm5IzUnGZxLsXlXbIIEXU5NLBfxXddVbZ6jsML51",
    "Content-Type": "application/json"
}

query = {
    "query": """
    query {
      teams {
        nodes {
          id
          name
          key
        }
      }
    }
    """
}

response = requests.post("https://api.linear.app/graphql", json=query, headers=headers)
print(response.json())