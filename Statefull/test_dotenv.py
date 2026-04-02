import os
from dotenv import load_dotenv
import json

load_dotenv()
j_str = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
j = json.loads(j_str)
pk = j['private_key']
print("PK length:", len(pk))
print("PK start:", repr(pk[:50]))
print("Does it contain literal newlines?", '\n' in pk)
print("Does it contain escaped chars?", '\\n' in pk)
