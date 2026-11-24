import pymongo

container_name:str = "overleafmongo"
port: int = 27017

client = pymongo.MongoClient(container_name, port)
db = client.sharelatex
projects = db.projects

cursor = projects.find()

for project in cursor:
    print(project['imageName'])

client.close()



