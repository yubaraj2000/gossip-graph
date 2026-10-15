from falkordb import FalkorDB

client = FalkorDB(host="localhost", port=6379)
graph = client.select_graph("social")

res = graph.ro_query("MATCH (u:User {name:'Alice'})-[:FRIENDS_WITH]->(f) RETURN f.name")
print("Alice's friends:", res.result_set)

res = graph.ro_query("MATCH (u:User {name:'Bob'})-[:CREATED]->(p:Post) RETURN p.content")
print("Bob's posts:", res.result_set)