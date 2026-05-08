import json
import os

email_list = []
staff_count = 0

with open("staff/staff_contacts.txt") as file:
  content = file.read()
  words = content.split() # default whitepsace delimiter
  
for word in words:
  if "@" in word:
    staff_count+= 1
    clean_email = word
    email_list.append(clean_email)

data = {
    "staff_emails": email_list
}
  
with open("staff/emails.json", "w") as file:
  json.dump(data, file, indent=4) # saves to json as a list under "staff_emails"
  
# debug
'''print(email_list)
print(f"Staff Count: {staff_count}")'''
