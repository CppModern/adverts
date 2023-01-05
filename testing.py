import os
import tempfile
import csv
users = [{"username": "ok", "id": "89900"}]
# file = tempfile.NamedTemporaryFile(newline="", mode="r+")
file = open("users.csv", "w+", newline="")
fieldnames = ["username", "id"]
writer = csv.DictWriter(file, fieldnames=fieldnames)
writer.writeheader()
writer.writerows(users)
print(900)
#file.close()
#file = open("users.csv", newline="")
reader = csv.DictReader(file, fieldnames=fieldnames)
for r in reader:
    print(r["username"])
file.close()
os.remove("users.csv")
