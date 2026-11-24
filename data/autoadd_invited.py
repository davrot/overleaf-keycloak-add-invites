import pymongo
from add_user import add_keycloak_user

container_name: str = "overleafmongo"
port: int = 27017

client = pymongo.MongoClient(container_name, port)
db = client.sharelatex
users = db.projectInvites

cursor = users.find()

for user in cursor:
#    print(user["email"])
    add_keycloak_user(user["email"])

client.close()
